from django.db import models
from django.contrib.auth.models import User
from auctions.models import Item
import uuid

class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('mtn', 'MTN Mobile Money'),
        ('airtel', 'Airtel Money'),
        ('mpesa', 'M-Pesa'),
        ('card', 'Credit/Debit Card'),
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
        ('ussd', 'USSD'),
        ('web', 'Web'),
    ]
    
    payment_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    phone_number = models.CharField(max_length=20, blank=True)
    transaction_reference = models.CharField(max_length=200, blank=True)
    
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.payment_method} - {self.amount} ({self.status})"

class USSDSession(models.Model):
    STAGE_CHOICES = [
        ('main_menu', 'Main Menu'),
        ('item_selection', 'Item Selection'),
        ('item_details', 'Item Details'),
        ('bid_entry', 'Bid Entry'),
        ('pin_entry', 'PIN Entry'),
        ('confirmation', 'Confirmation'),
        ('completed', 'Completed'),
        ('listing_title', 'Listing Title'),
        ('listing_description', 'Listing Description'),
        ('listing_category', 'Listing Category'),
        ('listing_price', 'Listing Price'),
        ('listing_duration', 'Listing Duration'),
        ('listing_review', 'Listing Review'),
        ('listing_confirm', 'Listing Confirm'),
    ]
    
    NETWORK_CHOICES = [
        ('mtn', 'MTN Mobile Money'),
        ('airtel', 'Airtel Money'),
    ]
    
    session_id = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='ussd_sessions')
    phone_number = models.CharField(max_length=20)
    network = models.CharField(max_length=20, choices=NETWORK_CHOICES, default='mtn')
    
    current_menu = models.CharField(max_length=50, default='main')
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='main_menu')
    
    selected_item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name='ussd_sessions')
    bid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    last_message = models.TextField(blank=True)
    session_data = models.JSONField(default=dict)
    
    demo_mode = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"USSD Session - {self.network.upper()} - {self.phone_number}"
