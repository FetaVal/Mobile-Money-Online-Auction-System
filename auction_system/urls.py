"""
URL configuration for auction_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from auctions.views import home, sell_item, item_detail, place_bid, verify_captcha, buy_now, submit_review, seller_profile, view_cart, add_to_cart, remove_from_cart, checkout, chatbot, inbox, conversation, send_message, start_conversation, search_users, change_item_status, admin_dashboard, admin_users, admin_items, admin_payments, admin_fraud_alerts, admin_toggle_user_status, admin_update_bypass_permissions, admin_change_item_status, admin_export_payments, admin_export_fraud_alerts, admin_resolve_fraud_alert, admin_dismiss_fraud_alert, admin_bulk_resolve_alerts, admin_seller_applications, admin_approve_seller, admin_reject_seller, get_cities, get_areas, calculate_shipping
from payments.ussd_views import ussd_simulator, ussd_initiate, ussd_respond, ussd_wallet_deposit, ussd_wallet_withdraw, ussd_wallet_initiate, ussd_wallet_respond
from payments.views import card_payment_page, process_card_payment, paypal_login_page, process_paypal_payment

urlpatterns = [
    path('admin/', admin.site.urls),
    path('captcha/', include('captcha.urls')),
    path('payments/', include('payments.urls_webhooks')),  # Payment webhooks
    path('', home, name='home'),
    path('sell/', sell_item, name='sell_item'),
    path('item/<int:pk>/', item_detail, name='item_detail'),
    path('item/<int:pk>/bid/', place_bid, name='place_bid'),
    path('item/<int:pk>/verify-captcha/', verify_captcha, name='verify_captcha'),
    path('item/<int:pk>/buy-now/', buy_now, name='buy_now'),
    path('item/<int:pk>/review/', submit_review, name='submit_review'),
    path('items/<int:item_id>/change-status/', change_item_status, name='change_item_status'),
    path('cart/', view_cart, name='view_cart'),
    path('cart/add/<int:pk>/', add_to_cart, name='cart_add'),
    path('cart/remove/<int:pk>/', remove_from_cart, name='cart_remove'),
    path('checkout/', checkout, name='checkout'),
    path('get-cities/<str:country_code>/', get_cities, name='get_cities'),
    path('get-areas/<str:city>/', get_areas, name='get_areas'),
    path('calculate-shipping/', calculate_shipping, name='calculate_shipping'),
    path('chatbot/', chatbot, name='chatbot'),
    path('messages/', inbox, name='inbox'),
    path('messages/<int:user_id>/', conversation, name='conversation'),
    path('messages/send/', send_message, name='send_message'),
    path('messages/start/<int:user_id>/', start_conversation, name='start_conversation'),
    path('api/search-users/', search_users, name='search_users'),
    path('ussd/', ussd_simulator, name='ussd_simulator'),
    path('ussd/initiate/', ussd_initiate, name='ussd_initiate'),
    path('ussd/respond/', ussd_respond, name='ussd_respond'),
    path('ussd/wallet/deposit/<uuid:payment_id>/', ussd_wallet_deposit, name='ussd_wallet_deposit'),
    path('ussd/wallet/withdraw/<uuid:payment_id>/', ussd_wallet_withdraw, name='ussd_wallet_withdraw'),
    path('ussd/wallet/initiate/', ussd_wallet_initiate, name='ussd_wallet_initiate'),
    path('ussd/wallet/respond/', ussd_wallet_respond, name='ussd_wallet_respond'),
    path('payment/card/<uuid:payment_id>/', card_payment_page, name='card_payment_page'),
    path('payment/card/process/', process_card_payment, name='process_card_payment'),
    path('payment/paypal/<uuid:payment_id>/', paypal_login_page, name='paypal_login_page'),
    path('payment/paypal/process/', process_paypal_payment, name='process_paypal_payment'),
    path('dashboard/', admin_dashboard, name='admin_dashboard'),
    path('dashboard/users/', admin_users, name='admin_users'),
    path('dashboard/users/<int:user_id>/toggle-status/', admin_toggle_user_status, name='admin_toggle_user_status'),
    path('dashboard/users/<int:user_id>/update-bypass/', admin_update_bypass_permissions, name='admin_update_bypass_permissions'),
    path('dashboard/items/', admin_items, name='admin_items'),
    path('dashboard/items/<int:item_id>/change-status/', admin_change_item_status, name='admin_change_item_status'),
    path('dashboard/payments/', admin_payments, name='admin_payments'),
    path('dashboard/payments/export/', admin_export_payments, name='admin_export_payments'),
    path('dashboard/fraud-alerts/', admin_fraud_alerts, name='admin_fraud_alerts'),
    path('dashboard/fraud-alerts/export/', admin_export_fraud_alerts, name='admin_export_fraud_alerts'),
    path('dashboard/fraud-alerts/<int:alert_id>/resolve/', admin_resolve_fraud_alert, name='admin_resolve_fraud_alert'),
    path('dashboard/fraud-alerts/<int:alert_id>/dismiss/', admin_dismiss_fraud_alert, name='admin_dismiss_fraud_alert'),
    path('dashboard/fraud-alerts/bulk-resolve/', admin_bulk_resolve_alerts, name='admin_bulk_resolve_alerts'),
    path('dashboard/sellers/', admin_seller_applications, name='admin_seller_applications'),
    path('dashboard/sellers/<int:user_id>/approve/', admin_approve_seller, name='admin_approve_seller'),
    path('dashboard/sellers/<int:user_id>/reject/', admin_reject_seller, name='admin_reject_seller'),
    path('', include('users.urls')),
    path('seller/<str:username>/', seller_profile, name='seller_profile'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
