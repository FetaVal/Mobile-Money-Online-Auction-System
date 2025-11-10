from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import hashlib
import json

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name

class Item(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('sold', 'Sold'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('private', 'Private'),
        ('off_sale', 'Off Sale'),
    ]
    
    CREATED_VIA_CHOICES = [
        ('web', 'Web'),
        ('ussd', 'USSD'),
    ]
    
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='items_selling')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    title = models.CharField(max_length=200)
    description = models.TextField()
    starting_price = models.DecimalField(max_digits=12, decimal_places=2)
    current_price = models.DecimalField(max_digits=12, decimal_places=2)
    min_increment = models.DecimalField(max_digits=12, decimal_places=2, default=10000)
    buy_now_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    created_via = models.CharField(max_length=10, choices=CREATED_VIA_CHOICES, default='web')
    requires_media_followup = models.BooleanField(default=False)
    
    main_image = models.ImageField(upload_to='items/main/', null=True, blank=True)
    image1 = models.ImageField(upload_to='items/', null=True, blank=True)
    image2 = models.ImageField(upload_to='items/', null=True, blank=True)
    image3 = models.ImageField(upload_to='items/', null=True, blank=True)
    image4 = models.ImageField(upload_to='items/', null=True, blank=True)
    
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    condition = models.CharField(max_length=50, default='New')
    location = models.CharField(max_length=200, blank=True)
    
    free_shipping = models.BooleanField(default=False)
    pickup_available = models.BooleanField(default=True)
    shipping_cost_base = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    seller_city = models.CharField(max_length=100, blank=True)
    seller_area = models.CharField(max_length=100, blank=True)
    
    view_count = models.IntegerField(default=0)
    bid_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='items_won')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
    
    def time_remaining(self):
        if self.status != 'active':
            return None
        remaining = self.end_time - timezone.now()
        if remaining.total_seconds() <= 0:
            return "Ended"
        days = remaining.days
        hours, remainder = divmod(remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m {seconds}s"
    
    def is_ending_soon(self):
        if self.status != 'active':
            return False
        remaining = self.end_time - timezone.now()
        return 0 < remaining.total_seconds() <= 3600
    
    def is_recently_added(self):
        return (timezone.now() - self.created_at).days < 7
    
    def calculate_shipping_cost(self, buyer_city, buyer_area):
        """Calculate shipping cost based on seller and buyer locations"""
        if self.free_shipping:
            return 0
        
        if not buyer_city:
            return self.shipping_cost_base
        
        if self.seller_city == buyer_city:
            if self.seller_area == buyer_area:
                return 5000
            else:
                return 10000
        else:
            try:
                cost = ShippingCost.objects.get(
                    from_city=self.seller_city, 
                    to_city=buyer_city
                )
                return cost.cost
            except ShippingCost.DoesNotExist:
                return self.shipping_cost_base if self.shipping_cost_base > 0 else 25000

class ShippingLocation(models.Model):
    """Cities and areas for shipping across different countries"""
    country = models.CharField(max_length=2, default='UG')
    city = models.CharField(max_length=100)
    area = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['country', 'city', 'area']
        unique_together = ('country', 'city', 'area')
    
    def __str__(self):
        return f"{self.area}, {self.city} ({self.country})"

class ShippingCost(models.Model):
    """Shipping costs between cities in Uganda"""
    from_city = models.CharField(max_length=100)
    to_city = models.CharField(max_length=100)
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_days = models.IntegerField(default=2)
    
    class Meta:
        unique_together = ('from_city', 'to_city')
        ordering = ['from_city', 'to_city']
    
    def __str__(self):
        return f"{self.from_city} → {self.to_city}: UGX {self.cost}"

class Bid(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='bids')
    bidder = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bids_placed')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    bid_time = models.DateTimeField(auto_now_add=True)
    is_winning = models.BooleanField(default=False)
    
    payment_method = models.CharField(max_length=50, default='web')
    payment_reference = models.CharField(max_length=100, blank=True)
    
    class Meta:
        ordering = ['-bid_time']
        
    def __str__(self):
        return f"{self.bidder.username} - {self.amount} on {self.item.title}"

class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Cart - {self.user.username}"
    
    def total(self):
        return sum(item.item.current_price for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('cart', 'item')
    
    def __str__(self):
        return f"{self.item.title} in {self.cart.user.username}'s cart"

class Review(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]
    
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_given')
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_received')
    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField()
    review_image = models.ImageField(upload_to='reviews/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ('item', 'reviewer')
    
    def __str__(self):
        return f"{self.rating}⭐ by {self.reviewer.username} for {self.item.title}"

class TransactionLog(models.Model):
    transaction_id = models.CharField(max_length=100, unique=True)
    transaction_type = models.CharField(max_length=50)
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50)
    payment_reference = models.CharField(max_length=200, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    data = models.JSONField(default=dict)
    
    previous_hash = models.CharField(max_length=64, blank=True)
    current_hash = models.CharField(max_length=64, blank=True)
    
    class Meta:
        ordering = ['id']
    
    def calculate_hash(self):
        data_string = f"{self.pk}{self.transaction_id}{self.timestamp}{self.amount}{self.previous_hash}{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(data_string.encode()).hexdigest()
    
    def __str__(self):
        return f"{self.transaction_type} - {self.transaction_id}"

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=TransactionLog)
def set_transaction_hash(sender, instance, created, **kwargs):
    if created and not instance.current_hash:
        last_transaction = TransactionLog.objects.exclude(pk=instance.pk).order_by('-id').first()
        if last_transaction:
            instance.previous_hash = last_transaction.current_hash
        instance.current_hash = instance.calculate_hash()
        TransactionLog.objects.filter(pk=instance.pk).update(
            previous_hash=instance.previous_hash,
            current_hash=instance.current_hash
        )

class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=3, unique=True)
    currency = models.CharField(max_length=3)
    currency_symbol = models.CharField(max_length=10)
    flag_emoji = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)
    
    local_payment_methods = models.JSONField(default=list)
    
    class Meta:
        verbose_name_plural = "Countries"
        ordering = ['name']
    
    def __str__(self):
        return self.name

class FraudAlert(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fraud_alerts')
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True)
    alert_type = models.CharField(max_length=100)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    description = models.TextField()
    data = models.JSONField(default=dict)
    
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='fraud_alerts_resolved')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.alert_type} - {self.user.username} ({self.severity})"

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages_sent')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages_received')
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name='messages')
    
    content = models.TextField()
    image = models.ImageField(upload_to='messages/', null=True, blank=True)
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['sender', 'recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.sender.username} → {self.recipient.username}: {self.content[:50]}"
    
    @classmethod
    def get_conversation(cls, user1, user2, item=None):
        """Get all messages between two users, optionally filtered by item"""
        query = cls.objects.filter(
            models.Q(sender=user1, recipient=user2) | 
            models.Q(sender=user2, recipient=user1)
        )
        if item:
            query = query.filter(item=item)
        return query.order_by('created_at')
    
    @classmethod
    def get_conversations_for_user(cls, user):
        """Get all conversations for a user with the latest message"""
        from django.db.models import Q, Max, OuterRef, Subquery
        
        # Get the latest message for each conversation
        latest_messages = cls.objects.filter(
            Q(sender=user) | Q(recipient=user)
        ).values('sender', 'recipient').annotate(
            latest=Max('created_at')
        )
        
        conversations = {}
        for msg_info in latest_messages:
            sender_id = msg_info['sender']
            recipient_id = msg_info['recipient']
            
            # Determine the other user
            other_user_id = recipient_id if sender_id == user.id else sender_id
            
            if other_user_id not in conversations:
                # Get the latest message
                latest_msg = cls.objects.filter(
                    Q(sender=user, recipient_id=other_user_id) |
                    Q(sender_id=other_user_id, recipient=user)
                ).order_by('-created_at').first()
                
                if latest_msg:
                    other_user = User.objects.get(id=other_user_id)
                    unread_count = cls.objects.filter(
                        sender_id=other_user_id,
                        recipient=user,
                        is_read=False
                    ).count()
                    
                    conversations[other_user_id] = {
                        'other_user': other_user,
                        'latest_message': latest_msg,
                        'unread_count': unread_count
                    }
        
        # Sort by latest message time
        return sorted(
            conversations.values(),
            key=lambda x: x['latest_message'].created_at,
            reverse=True
        )

class BidCooldown(models.Model):
    COOLDOWN_TYPE_CHOICES = [
        ('soft_challenge', 'Soft Challenge Required'),
        ('hard_cooldown', 'Hard Cooldown'),
        ('captcha_failed', 'CAPTCHA Failed'),
        ('suspended', 'Suspended'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bid_cooldowns')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='bid_cooldowns', null=True, blank=True)
    cooldown_type = models.CharField(max_length=20, choices=COOLDOWN_TYPE_CHOICES, default='hard_cooldown')
    reason = models.TextField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    captcha_required = models.BooleanField(default=False)
    captcha_passed = models.BooleanField(default=False)
    failed_attempts = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'item', 'is_active', 'expires_at']),
            models.Index(fields=['expires_at', 'is_active']),
        ]
    
    def __str__(self):
        item_info = f" on {self.item.title}" if self.item else " (global)"
        return f"{self.user.username} - {self.get_cooldown_type_display()}{item_info} until {self.expires_at}"
    
    def is_expired(self):
        return timezone.now() >= self.expires_at
    
    def deactivate(self):
        self.is_active = False
        self.save(update_fields=['is_active'])
    
    @classmethod
    def cleanup_expired(cls):
        """Deactivate expired cooldowns"""
        expired = cls.objects.filter(
            is_active=True,
            expires_at__lte=timezone.now()
        )
        count = expired.update(is_active=False)
        return count
    
    @classmethod
    def get_active_cooldown(cls, user, item=None):
        """Get active cooldown for user on specific item or globally"""
        cls.cleanup_expired()
        query = cls.objects.filter(
            user=user,
            is_active=True,
            expires_at__gt=timezone.now()
        )
        if item:
            query = query.filter(models.Q(item=item) | models.Q(item__isnull=True))
        else:
            query = query.filter(item__isnull=True)
        return query.order_by('-created_at').first()
    
    @classmethod
    def has_active_cooldown(cls, user, item=None):
        """Check if user has any active cooldown"""
        return cls.get_active_cooldown(user, item) is not None
