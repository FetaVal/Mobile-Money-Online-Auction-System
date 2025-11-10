"""
Webhook URL patterns for payment providers
"""

from django.urls import path
from . import webhooks

urlpatterns = [
    path('webhook/flutterwave/', webhooks.flutterwave_webhook, name='flutterwave_webhook'),
    path('webhook/stripe/', webhooks.stripe_webhook, name='stripe_webhook'),
    path('webhook/paypal/', webhooks.paypal_webhook, name='paypal_webhook'),
]
