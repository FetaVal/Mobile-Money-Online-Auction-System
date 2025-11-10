from django.urls import path
from . import views
from . import ussd_views

urlpatterns = [
    # Card payment
    path('card/<uuid:payment_id>/', views.card_payment_page, name='card_payment_page'),
    path('card/process/', views.process_card_payment, name='process_card_payment'),
    
    # PayPal payment
    path('paypal/<uuid:payment_id>/', views.paypal_login_page, name='paypal_login_page'),
    path('paypal/process/', views.process_paypal_payment, name='process_paypal_payment'),
    
    # USSD payments (existing routes)
    path('ussd/initiate/', ussd_views.ussd_initiate, name='ussd_initiate'),
    path('ussd/respond/', ussd_views.ussd_respond, name='ussd_respond'),
    path('ussd/wallet/deposit/<uuid:payment_id>/', ussd_views.ussd_wallet_deposit, name='ussd_wallet_deposit'),
    path('ussd/wallet/withdraw/<uuid:payment_id>/', ussd_views.ussd_wallet_withdraw, name='ussd_wallet_withdraw'),
    path('ussd/wallet/initiate/', ussd_views.ussd_wallet_initiate, name='ussd_wallet_initiate'),
    path('ussd/wallet/respond/', ussd_views.ussd_wallet_respond, name='ussd_wallet_respond'),
]
