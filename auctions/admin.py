from django.contrib import admin
from .models import Category, Item, Bid, Cart, CartItem, Review, TransactionLog, FraudAlert, Country, BidCooldown

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'seller', 'category', 'current_price', 'status', 'end_time']
    list_filter = ['status', 'category', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['view_count', 'bid_count', 'created_at', 'updated_at']

@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ['bidder', 'item', 'amount', 'bid_time', 'is_winning']
    list_filter = ['bid_time', 'is_winning']
    search_fields = ['bidder__username', 'item__title']

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at', 'updated_at']
    search_fields = ['user__username']

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'item', 'added_at']
    search_fields = ['cart__user__username', 'item__title']

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['reviewer', 'item', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['reviewer__username', 'item__title']

@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'transaction_type', 'user', 'amount', 'timestamp']
    list_filter = ['transaction_type', 'payment_method', 'timestamp']
    search_fields = ['transaction_id', 'user__username']
    readonly_fields = ['transaction_id', 'timestamp', 'previous_hash', 'current_hash']

@admin.register(FraudAlert)
class FraudAlertAdmin(admin.ModelAdmin):
    list_display = ['user', 'alert_type', 'severity', 'is_resolved', 'created_at']
    list_filter = ['severity', 'is_resolved', 'created_at']
    search_fields = ['user__username', 'alert_type']

@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['flag_emoji', 'name', 'code', 'currency', 'currency_symbol', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']

@admin.register(BidCooldown)
class BidCooldownAdmin(admin.ModelAdmin):
    list_display = ['user', 'item', 'cooldown_type', 'is_active', 'expires_at', 'created_at']
    list_filter = ['cooldown_type', 'is_active', 'created_at']
    search_fields = ['user__username', 'item__title', 'reason']
    readonly_fields = ['created_at']
    list_select_related = ['user', 'item']
