from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
import secrets
import pyotp

class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('follower', 'following')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='Uganda')
    
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    bio = models.TextField(blank=True)
    
    rating_sum = models.IntegerField(default=0)
    rating_count = models.IntegerField(default=0)
    
    mobile_money_number = models.CharField(max_length=20, blank=True)
    mobile_money_provider = models.CharField(max_length=20, blank=True, choices=[
        ('mtn', 'MTN Mobile Money'),
        ('airtel', 'Airtel Money'),
    ])
    
    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(null=True, blank=True)
    
    last_seen = models.DateTimeField(null=True, blank=True)
    
    hide_phone_number = models.BooleanField(default=False)
    
    is_seller = models.BooleanField(default=False)
    seller_status = models.CharField(max_length=20, choices=[
        ('none', 'Not Applied'),
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='none')
    seller_application_date = models.DateTimeField(null=True, blank=True)
    seller_approval_date = models.DateTimeField(null=True, blank=True)
    
    business_name = models.CharField(max_length=200, blank=True)
    business_type = models.CharField(max_length=100, blank=True, choices=[
        ('individual', 'Individual Seller'),
        ('small_business', 'Small Business'),
        ('company', 'Registered Company'),
        ('wholesaler', 'Wholesaler'),
        ('manufacturer', 'Manufacturer'),
    ])
    business_registration_number = models.CharField(max_length=100, blank=True)
    national_id_number = models.CharField(max_length=50, blank=True)
    national_id_front = models.ImageField(upload_to='id_verification/front/', null=True, blank=True)
    national_id_back = models.ImageField(upload_to='id_verification/back/', null=True, blank=True)
    
    bank_account_name = models.CharField(max_length=200, blank=True)
    bank_account_number = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=100, blank=True, choices=[
        ('stanbic', 'Stanbic Bank'),
        ('dfcu', 'DFCU Bank'),
        ('centenary', 'Centenary Bank'),
        ('equity', 'Equity Bank'),
        ('absa', 'Absa Bank'),
        ('standard_chartered', 'Standard Chartered'),
        ('barclays', 'Barclays Bank'),
        ('other', 'Other'),
    ])
    
    years_of_experience = models.IntegerField(null=True, blank=True)
    business_description = models.TextField(blank=True)
    product_categories = models.TextField(blank=True)
    
    rejection_reason = models.TextField(blank=True)
    
    # Admin Bypass Permissions (for trusted users or exceptions)
    is_trusted_user = models.BooleanField(default=False, help_text="Mark user as trusted (shows in admin dashboard)")
    bypass_account_age_check = models.BooleanField(default=False, help_text="Allow high-value bids regardless of account age")
    bypass_rapid_bidding_check = models.BooleanField(default=False, help_text="Exempt from rapid bidding detection and CAPTCHA challenges")
    bypass_fraud_detection = models.BooleanField(default=False, help_text="Fraud alerts logged but won't block bids")
    bypass_all_restrictions = models.BooleanField(default=False, help_text="Bypass ALL security checks (use with extreme caution)")
    bypass_notes = models.TextField(blank=True, help_text="Admin notes explaining why bypass was granted")
    bypass_granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='bypass_grants')
    bypass_granted_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def average_rating(self):
        if self.rating_count == 0:
            return 0
        return round(self.rating_sum / self.rating_count, 1)
    
    def is_online(self):
        from django.utils import timezone
        from datetime import timedelta
        
        if not self.last_seen:
            return False
        
        return timezone.now() - self.last_seen < timedelta(minutes=5)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    is_active = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username}'s Wallet - UGX {self.balance}"
    
    def deposit(self, amount, description='Deposit', transaction_type='deposit', payment_method=''):
        from django.db import transaction
        
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=self.pk)
            
            wallet.balance += Decimal(str(amount))
            wallet.save(update_fields=['balance', 'updated_at'])
            
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type=transaction_type,
                amount=amount,
                balance_after=wallet.balance,
                description=description,
                payment_method=payment_method,
                status='completed'
            )
            
            self.balance = wallet.balance
        
        return True
    
    def withdraw(self, amount, description='Withdrawal', payment_method=''):
        from django.db import transaction
        
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=self.pk)
            
            if wallet.balance < Decimal(str(amount)):
                raise ValueError("Insufficient balance")
            if wallet.is_locked:
                raise ValueError("Wallet is locked")
            
            wallet.balance -= Decimal(str(amount))
            wallet.save(update_fields=['balance', 'updated_at'])
            
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='withdrawal',
                amount=amount,
                balance_after=wallet.balance,
                description=description,
                payment_method=payment_method,
                status='completed'
            )
            
            self.balance = wallet.balance
        
        return True
    
    def can_withdraw(self, amount):
        return not self.is_locked and self.balance >= Decimal(str(amount))

class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('sale', 'Sale'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    
    description = models.TextField()
    payment_method = models.CharField(max_length=50, blank=True)
    payment_reference = models.CharField(max_length=200, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    metadata = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        sign = '+' if self.transaction_type in ['deposit', 'sale', 'refund'] else '-'
        return f"{sign}UGX {self.amount} - {self.transaction_type}"

@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        Wallet.objects.create(user=instance)

class LoginAttempt(models.Model):
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    
    success = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=100, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['username', '-timestamp']),
            models.Index(fields=['ip_address', '-timestamp']),
        ]
    
    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{status} login attempt for {self.username} at {self.timestamp}"
    
    @classmethod
    def is_locked_out(cls, username):
        from django.conf import settings
        
        lockout_duration = getattr(settings, 'LOGIN_LOCKOUT_DURATION', 15)
        attempt_limit = getattr(settings, 'LOGIN_ATTEMPT_LIMIT', 5)
        
        cutoff_time = timezone.now() - timedelta(minutes=lockout_duration)
        
        recent_failures = cls.objects.filter(
            username=username,
            success=False,
            timestamp__gte=cutoff_time
        ).count()
        
        return recent_failures >= attempt_limit
    
    @classmethod
    def get_lockout_time_remaining(cls, username):
        from django.conf import settings
        
        lockout_duration = getattr(settings, 'LOGIN_LOCKOUT_DURATION', 15)
        attempt_limit = getattr(settings, 'LOGIN_ATTEMPT_LIMIT', 5)
        
        cutoff_time = timezone.now() - timedelta(minutes=lockout_duration)
        
        first_failure = cls.objects.filter(
            username=username,
            success=False,
            timestamp__gte=cutoff_time
        ).order_by('timestamp').first()
        
        if not first_failure:
            return 0
        
        lockout_end = first_failure.timestamp + timedelta(minutes=lockout_duration)
        time_remaining = (lockout_end - timezone.now()).total_seconds() / 60
        
        return max(0, int(time_remaining))
    
    @classmethod
    def clear_attempts(cls, username):
        from django.conf import settings
        
        lockout_duration = getattr(settings, 'LOGIN_LOCKOUT_DURATION', 15)
        cutoff_time = timezone.now() - timedelta(minutes=lockout_duration)
        
        cls.objects.filter(
            username=username,
            timestamp__gte=cutoff_time
        ).delete()

class EmailOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_otps')
    code = models.CharField(max_length=6)
    
    purpose = models.CharField(max_length=20, choices=[
        ('login', 'Login Verification'),
        ('sensitive', 'Sensitive Action'),
        ('recovery', 'Account Recovery'),
    ], default='login')
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['code', 'used']),
        ]
    
    def __str__(self):
        return f"OTP for {self.user.username} - {self.purpose}"
    
    @property
    def is_used(self):
        return self.used
    
    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at
    
    def mark_as_used(self):
        self.used = True
        self.used_at = timezone.now()
        self.save(update_fields=['used', 'used_at'])
    
    @classmethod
    def generate_code(cls, user, purpose='login', validity_minutes=5, ip_address=None, user_agent=''):
        from django.core.mail import send_mail
        from django.conf import settings
        
        # Delete ALL previous unused OTPs for this user/purpose to ensure single-use enforcement
        cls.objects.filter(
            user=user,
            purpose=purpose,
            used=False
        ).delete()
        
        code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        
        expires_at = timezone.now() + timedelta(minutes=validity_minutes)
        
        otp = cls.objects.create(
            user=user,
            code=code,
            purpose=purpose,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Send email with OTP code
        subject = f'AuctionHub - Your verification code is {code}'
        message = f'''
Hello {user.username},

Your AuctionHub verification code is: {code}

This code will expire in {validity_minutes} minutes.

If you didn't request this code, please ignore this email.

Best regards,
The AuctionHub Team
        '''
        
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Failed to send OTP email: {e}")
        
        return otp
    
    @classmethod
    def verify_code(cls, user, code, purpose='login'):
        try:
            otp = cls.objects.get(
                user=user,
                code=code,
                purpose=purpose,
                used=False
            )
            
            if otp.is_valid():
                otp.mark_as_used()
                return True, "Code verified successfully"
            else:
                return False, "Code has expired"
        except cls.DoesNotExist:
            return False, "Invalid code"

class TwoFactorAuth(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='two_factor')
    
    enabled = models.BooleanField(default=False)
    method = models.CharField(max_length=20, choices=[
        ('email', 'Email OTP'),
        ('totp', 'Authenticator App'),
    ], default='email')
    
    secret_key = models.CharField(max_length=32, blank=True)
    totp_secret = models.CharField(max_length=32, blank=True)
    backup_codes = models.JSONField(default=list)
    
    enabled_at = models.DateTimeField(null=True, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Two-Factor Authentication'
        verbose_name_plural = 'Two-Factor Authentications'
    
    def __str__(self):
        status = "Enabled" if self.enabled else "Disabled"
        return f"2FA for {self.user.username} - {status}"
    
    def generate_secret(self):
        self.secret_key = pyotp.random_base32()
        self.save(update_fields=['secret_key'])
        return self.secret_key
    
    def get_totp_uri(self):
        if not self.secret_key:
            self.generate_secret()
        
        totp = pyotp.TOTP(self.secret_key)
        return totp.provisioning_uri(
            name=self.user.email,
            issuer_name='AuctionHub'
        )
    
    def verify_totp(self, code):
        if not self.secret_key:
            return False
        
        totp = pyotp.TOTP(self.secret_key)
        return totp.verify(code)
    
    def generate_backup_codes(self, count=10):
        codes = [secrets.token_hex(4).upper() for _ in range(count)]
        self.backup_codes = codes
        self.save(update_fields=['backup_codes'])
        return codes
    
    def use_backup_code(self, code):
        # Ensure backup_codes is a list (JSONField sometimes returns string)
        codes = self.backup_codes if isinstance(self.backup_codes, list) else []
        
        if code.upper() in codes:
            codes.remove(code.upper())
            self.backup_codes = codes
            self.save(update_fields=['backup_codes'])
            return True
        return False
