from django.contrib import admin
from .models import Payment, USSDSession

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_id', 'user', 'amount', 'payment_method', 'status', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['payment_id', 'user__username', 'transaction_reference']
    readonly_fields = ['payment_id', 'created_at', 'updated_at']

@admin.register(USSDSession)
class USSDSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'phone_number', 'current_menu', 'is_active', 'last_activity']
    list_filter = ['is_active', 'current_menu', 'created_at']
    search_fields = ['session_id', 'phone_number']
