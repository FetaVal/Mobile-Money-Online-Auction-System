"""
Payment webhook handlers with signature verification, replay protection, and idempotency

Handles webhooks from:
- Flutterwave (MTN, Airtel Money)
- Stripe
- PayPal
"""

import hashlib
import hmac
import json
import time
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from decouple import config
from .models import Payment
from auctions.models import TransactionLog, Item
import logging

logger = logging.getLogger(__name__)


class WebhookVerificationError(Exception):
    """Raised when webhook signature verification fails"""
    pass


class ReplayAttackError(Exception):
    """Raised when webhook replay is detected"""
    pass


def verify_flutterwave_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Flutterwave webhook signature using HMAC-SHA256
    
    Args:
        payload: Raw request body bytes
        signature: verif-hash header from Flutterwave
    
    Returns:
        True if signature is valid
    """
    secret = config('FLUTTERWAVE_SECRET_HASH', default='')
    if not secret:
        logger.warning("FLUTTERWAVE_SECRET_HASH not configured - webhook verification disabled")
        return True  # Allow in dev mode
    
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


def verify_stripe_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Stripe webhook signature
    
    Args:
        payload: Raw request body bytes
        signature: Stripe-Signature header
    
    Returns:
        True if signature is valid
    """
    secret = config('STRIPE_WEBHOOK_SECRET', default='')
    if not secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured - webhook verification disabled")
        return True
    
    try:
        # Parse signature header
        sig_parts = dict(part.split('=') for part in signature.split(','))
        timestamp = sig_parts.get('t')
        signatures = [s for k, s in sig_parts.items() if k.startswith('v1')]
        
        if not timestamp or not signatures:
            return False
        
        # Check timestamp (reject if older than 5 minutes)
        current_time = int(time.time())
        if abs(current_time - int(timestamp)) > 300:
            logger.warning(f"Stripe webhook timestamp too old: {timestamp}")
            return False
        
        # Compute expected signature
        signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare with all provided signatures
        return any(hmac.compare_digest(expected_signature, sig) for sig in signatures)
    
    except Exception as e:
        logger.error(f"Stripe signature verification error: {e}")
        return False


def verify_paypal_signature(payload: bytes, headers: dict) -> bool:
    """
    Verify PayPal webhook signature
    
    Args:
        payload: Raw request body bytes
        headers: Request headers
    
    Returns:
        True if signature is valid
    """
    # PayPal uses a more complex verification with certificates
    # For demo purposes, we'll do basic verification
    # In production, use PayPal SDK's webhook verification
    
    webhook_id = config('PAYPAL_WEBHOOK_ID', default='')
    if not webhook_id:
        logger.warning("PAYPAL_WEBHOOK_ID not configured - webhook verification disabled")
        return True
    
    # In production, use PayPal SDK:
    # from paypalrestsdk import WebhookEvent
    # return WebhookEvent.verify(transmission_id, timestamp, webhook_id, event_body, ...)
    
    return True  # Simplified for demo


def check_replay_protection(event_id: str, provider: str, window_seconds: int = 300) -> bool:
    """
    Protect against replay attacks by tracking processed event IDs
    
    Args:
        event_id: Unique event identifier from payment provider
        provider: Payment provider name (flutterwave, stripe, paypal)
        window_seconds: Time window to track events (default 5 minutes)
    
    Returns:
        True if event is new, False if already processed
    
    Raises:
        ReplayAttackError: If replay attack detected
    """
    cache_key = f"webhook_event:{provider}:{event_id}"
    
    # Check if we've seen this event before
    if cache.get(cache_key):
        raise ReplayAttackError(f"Duplicate webhook event: {event_id}")
    
    # Mark event as processed
    cache.set(cache_key, True, window_seconds)
    return True


@csrf_exempt
@require_POST
def flutterwave_webhook(request):
    """
    Handle Flutterwave payment webhooks
    
    Verifies signature, prevents replay attacks, and updates payment status
    """
    try:
        # Get raw payload and signature
        payload = request.body
        signature = request.META.get('HTTP_VERIF_HASH', '')
        
        # Verify signature
        if not verify_flutterwave_signature(payload, signature):
            logger.error("Flutterwave webhook signature verification failed")
            return JsonResponse({'error': 'Invalid signature'}, status=401)
        
        # Parse payload
        data = json.loads(payload)
        event_type = data.get('event')
        event_data = data.get('data', {})
        
        # Get event ID for replay protection
        event_id = data.get('id') or event_data.get('id')
        if not event_id:
            return JsonResponse({'error': 'No event ID'}, status=400)
        
        # Check replay protection
        check_replay_protection(event_id, 'flutterwave')
        
        # Process event
        if event_type == 'charge.completed':
            return handle_flutterwave_charge_completed(event_data)
        
        logger.info(f"Unhandled Flutterwave event: {event_type}")
        return JsonResponse({'status': 'ignored'})
    
    except ReplayAttackError as e:
        logger.warning(f"Replay attack detected: {e}")
        return JsonResponse({'error': 'Duplicate event'}, status=409)
    
    except Exception as e:
        logger.error(f"Flutterwave webhook error: {e}")
        return JsonResponse({'error': 'Internal error'}, status=500)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Handle Stripe payment webhooks
    
    Verifies signature, prevents replay attacks, and updates payment status
    """
    try:
        # Get raw payload and signature
        payload = request.body
        signature = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        
        # Verify signature
        if not verify_stripe_signature(payload, signature):
            logger.error("Stripe webhook signature verification failed")
            return JsonResponse({'error': 'Invalid signature'}, status=401)
        
        # Parse payload
        data = json.loads(payload)
        event_type = data.get('type')
        event_data = data.get('data', {}).get('object', {})
        event_id = data.get('id')
        
        # Check replay protection
        check_replay_protection(event_id, 'stripe')
        
        # Process event
        if event_type == 'payment_intent.succeeded':
            return handle_stripe_payment_succeeded(event_data)
        elif event_type == 'payment_intent.payment_failed':
            return handle_stripe_payment_failed(event_data)
        
        logger.info(f"Unhandled Stripe event: {event_type}")
        return JsonResponse({'status': 'ignored'})
    
    except ReplayAttackError as e:
        logger.warning(f"Replay attack detected: {e}")
        return JsonResponse({'error': 'Duplicate event'}, status=409)
    
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return JsonResponse({'error': 'Internal error'}, status=500)


@csrf_exempt
@require_POST
def paypal_webhook(request):
    """
    Handle PayPal payment webhooks
    
    Verifies signature, prevents replay attacks, and updates payment status
    """
    try:
        # Get raw payload
        payload = request.body
        headers = dict(request.META)
        
        # Verify signature
        if not verify_paypal_signature(payload, headers):
            logger.error("PayPal webhook signature verification failed")
            return JsonResponse({'error': 'Invalid signature'}, status=401)
        
        # Parse payload
        data = json.loads(payload)
        event_type = data.get('event_type')
        event_id = data.get('id')
        
        # Check replay protection
        check_replay_protection(event_id, 'paypal')
        
        # Process event
        if event_type == 'PAYMENT.CAPTURE.COMPLETED':
            return handle_paypal_payment_completed(data.get('resource', {}))
        elif event_type == 'PAYMENT.CAPTURE.DENIED':
            return handle_paypal_payment_failed(data.get('resource', {}))
        
        logger.info(f"Unhandled PayPal event: {event_type}")
        return JsonResponse({'status': 'ignored'})
    
    except ReplayAttackError as e:
        logger.warning(f"Replay attack detected: {e}")
        return JsonResponse({'error': 'Duplicate event'}, status=409)
    
    except Exception as e:
        logger.error(f"PayPal webhook error: {e}")
        return JsonResponse({'error': 'Internal error'}, status=500)


@transaction.atomic
def handle_flutterwave_charge_completed(event_data: dict) -> JsonResponse:
    """
    Handle successful Flutterwave charge with idempotent DB writes
    """
    # Extract payment details
    tx_ref = event_data.get('tx_ref')  # Our payment_id
    status = event_data.get('status')
    amount = Decimal(str(event_data.get('amount', 0)))
    
    if not tx_ref:
        return JsonResponse({'error': 'Missing tx_ref'}, status=400)
    
    try:
        # Idempotent update: select_for_update prevents race conditions
        payment = Payment.objects.select_for_update().get(payment_id=tx_ref)
        
        # Only update if not already completed (idempotency)
        if payment.status == 'completed':
            logger.info(f"Payment {tx_ref} already completed - idempotent skip")
            return JsonResponse({'status': 'already_processed'})
        
        # Update payment status
        old_status = payment.status
        payment.status = 'completed' if status == 'successful' else 'failed'
        payment.provider_response = event_data
        payment.save()
        
        # Log to blockchain-style transaction log
        TransactionLog.objects.create(
            transaction_type='payment_webhook',
            user=payment.user,
            data={
                'payment_id': tx_ref,
                'provider': 'flutterwave',
                'old_status': old_status,
                'new_status': payment.status,
                'amount': str(amount),
                'event_data': event_data
            }
        )
        
        logger.info(f"Flutterwave payment {tx_ref} updated to {payment.status}")
        return JsonResponse({'status': 'success'})
    
    except Payment.DoesNotExist:
        logger.error(f"Payment not found: {tx_ref}")
        return JsonResponse({'error': 'Payment not found'}, status=404)


@transaction.atomic
def handle_stripe_payment_succeeded(event_data: dict) -> JsonResponse:
    """
    Handle successful Stripe payment with idempotent DB writes
    """
    payment_intent_id = event_data.get('id')
    amount = Decimal(str(event_data.get('amount', 0))) / 100  # Stripe uses cents
    
    try:
        payment = Payment.objects.select_for_update().get(payment_id=payment_intent_id)
        
        if payment.status == 'completed':
            return JsonResponse({'status': 'already_processed'})
        
        old_status = payment.status
        payment.status = 'completed'
        payment.provider_response = event_data
        payment.save()
        
        TransactionLog.objects.create(
            transaction_type='payment_webhook',
            user=payment.user,
            data={
                'payment_id': payment_intent_id,
                'provider': 'stripe',
                'old_status': old_status,
                'new_status': 'completed',
                'amount': str(amount)
            }
        )
        
        return JsonResponse({'status': 'success'})
    
    except Payment.DoesNotExist:
        logger.error(f"Stripe payment not found: {payment_intent_id}")
        return JsonResponse({'error': 'Payment not found'}, status=404)


@transaction.atomic
def handle_stripe_payment_failed(event_data: dict) -> JsonResponse:
    """Handle failed Stripe payment"""
    payment_intent_id = event_data.get('id')
    
    try:
        payment = Payment.objects.select_for_update().get(payment_id=payment_intent_id)
        
        if payment.status in ['completed', 'failed']:
            return JsonResponse({'status': 'already_processed'})
        
        payment.status = 'failed'
        payment.provider_response = event_data
        payment.save()
        
        return JsonResponse({'status': 'success'})
    
    except Payment.DoesNotExist:
        return JsonResponse({'error': 'Payment not found'}, status=404)


@transaction.atomic
def handle_paypal_payment_completed(event_data: dict) -> JsonResponse:
    """Handle successful PayPal payment"""
    # PayPal uses custom_id for our payment_id
    custom_id = event_data.get('custom_id')
    amount = Decimal(str(event_data.get('amount', {}).get('value', 0)))
    
    try:
        payment = Payment.objects.select_for_update().get(payment_id=custom_id)
        
        if payment.status == 'completed':
            return JsonResponse({'status': 'already_processed'})
        
        payment.status = 'completed'
        payment.provider_response = event_data
        payment.save()
        
        TransactionLog.objects.create(
            transaction_type='payment_webhook',
            user=payment.user,
            data={
                'payment_id': custom_id,
                'provider': 'paypal',
                'new_status': 'completed',
                'amount': str(amount)
            }
        )
        
        return JsonResponse({'status': 'success'})
    
    except Payment.DoesNotExist:
        return JsonResponse({'error': 'Payment not found'}, status=404)


@transaction.atomic
def handle_paypal_payment_failed(event_data: dict) -> JsonResponse:
    """Handle failed PayPal payment"""
    custom_id = event_data.get('custom_id')
    
    try:
        payment = Payment.objects.select_for_update().get(payment_id=custom_id)
        
        if payment.status in ['completed', 'failed']:
            return JsonResponse({'status': 'already_processed'})
        
        payment.status = 'failed'
        payment.provider_response = event_data
        payment.save()
        
        return JsonResponse({'status': 'success'})
    
    except Payment.DoesNotExist:
        return JsonResponse({'error': 'Payment not found'}, status=404)
