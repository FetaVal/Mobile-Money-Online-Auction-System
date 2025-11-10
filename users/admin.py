from django.contrib import admin
from .models import UserProfile
from django.utils import timezone

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone_number', 'city', 'country', 'is_verified', 'is_trusted_user', 'has_bypass_permissions', 'average_rating']
    list_filter = ['is_verified', 'is_trusted_user', 'bypass_all_restrictions', 'bypass_account_age_check', 'bypass_rapid_bidding_check', 'bypass_fraud_detection', 'country', 'mobile_money_provider']
    search_fields = ['user__username', 'phone_number', 'user__email']
    readonly_fields = ['rating_sum', 'rating_count', 'created_at', 'updated_at', 'bypass_granted_at']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'phone_number', 'address', 'city', 'country', 'profile_picture', 'bio')
        }),
        ('Verification & Status', {
            'fields': ('is_verified', 'verification_date', 'last_seen', 'hide_phone_number')
        }),
        ('Seller Information', {
            'fields': ('is_seller', 'seller_status', 'business_name', 'business_type', 'business_description', 
                      'seller_application_date', 'seller_approval_date', 'rejection_reason'),
            'classes': ('collapse',)
        }),
        ('Payment & Banking', {
            'fields': ('mobile_money_number', 'mobile_money_provider', 'bank_account_name', 
                      'bank_account_number', 'bank_name'),
            'classes': ('collapse',)
        }),
        ('⚡ Admin Bypass Permissions', {
            'fields': ('is_trusted_user', 'bypass_all_restrictions', 'bypass_account_age_check', 
                      'bypass_rapid_bidding_check', 'bypass_fraud_detection', 'bypass_notes', 
                      'bypass_granted_by', 'bypass_granted_at'),
            'description': 'Grant special permissions to trusted users. Use with caution!'
        }),
        ('Ratings & Statistics', {
            'fields': ('rating_sum', 'rating_count'),
            'classes': ('collapse',)
        }),
    )
    
    def has_bypass_permissions(self, obj):
        """Show if user has any bypass permissions"""
        return (obj.bypass_all_restrictions or obj.bypass_account_age_check or 
                obj.bypass_rapid_bidding_check or obj.bypass_fraud_detection)
    has_bypass_permissions.boolean = True
    has_bypass_permissions.short_description = 'Has Bypasses'
    
    def save_model(self, request, obj, form, change):
        """Auto-track who granted bypass permissions"""
        if change:
            # Check if any bypass field was just enabled
            original = UserProfile.objects.get(pk=obj.pk)
            bypass_fields = ['bypass_all_restrictions', 'bypass_account_age_check', 
                           'bypass_rapid_bidding_check', 'bypass_fraud_detection']
            
            for field in bypass_fields:
                if getattr(obj, field) and not getattr(original, field):
                    # A bypass was just granted
                    obj.bypass_granted_by = request.user
                    obj.bypass_granted_at = timezone.now()
                    break
        
        super().save_model(request, obj, form, change)
