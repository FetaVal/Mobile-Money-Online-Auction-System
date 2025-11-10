from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.db import transaction as db_transaction
from django.urls import reverse
from decimal import Decimal
from .models import Payment
from auctions.models import Item, Cart, CartItem
from users.models import Wallet
import uuid


@login_required
def card_payment_page(request, payment_id):
    """Display card payment form"""
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user, status='pending')
    
    # Determine payment context and return URL
    payment_context = request.GET.get('context', 'checkout')
    
    if payment_context == 'wallet_deposit':
        return_url = 'wallet_dashboard'
        cancel_url_name = 'wallet_deposit'
        payment_type = 'Wallet Deposit'
    elif payment_context == 'wallet_withdraw':
        return_url = 'wallet_dashboard'
        cancel_url_name = 'wallet_withdraw'
        payment_type = 'Wallet Withdrawal'
    else:
        return_url = 'home'
        cancel_url_name = 'checkout'
        payment_type = 'Purchase'
    
    # Extract tax info from metadata
    base_amount = payment.metadata.get('base_amount', str(payment.amount - payment.platform_tax))
    tax_amount = payment.platform_tax
    total_amount = payment.amount
    
    context = {
        'payment': payment,
        'payment_id': payment.payment_id,
        'payment_context': payment_context,
        'payment_type': payment_type,
        'base_amount': Decimal(base_amount) if isinstance(base_amount, str) else base_amount,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
        'return_url': return_url,
        'cancel_url': reverse(cancel_url_name),
    }
    
    return render(request, 'payments/card_payment.html', context)


@login_required
@require_POST
def process_card_payment(request):
    """Process card payment (demo mode)"""
    payment_id = request.POST.get('payment_id')
    payment_context = request.POST.get('payment_context', 'checkout')
    cardholder_name = request.POST.get('cardholder_name')
    card_number = request.POST.get('card_number', '').replace(' ', '')
    expiry_date = request.POST.get('expiry_date')
    cvv = request.POST.get('cvv')
    billing_zip = request.POST.get('billing_zip')
    
    # Validate inputs
    if not all([payment_id, cardholder_name, card_number, expiry_date, cvv, billing_zip]):
        messages.error(request, 'All fields are required.')
        return redirect('card_payment_page', payment_id=payment_id)
    
    try:
        payment = Payment.objects.get(payment_id=payment_id, user=request.user, status='pending')
    except Payment.DoesNotExist:
        messages.error(request, 'Payment not found or already processed.')
        return redirect('home')
    
    # Extract amounts from metadata
    base_amount = Decimal(payment.metadata.get('base_amount', str(payment.amount - payment.platform_tax)))
    
    try:
        with db_transaction.atomic():
            if payment_context == 'wallet_deposit':
                # Wallet deposit
                wallet, created = Wallet.objects.get_or_create(user=request.user)
                wallet.deposit(
                    amount=base_amount,
                    description=f'Card deposit - {payment.transaction_reference}',
                    transaction_type='deposit',
                    payment_method='card'
                )
                
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.metadata['card_last4'] = card_number[-4:]
                payment.metadata['cardholder_name'] = cardholder_name
                payment.save()
                
                messages.success(request, f'Successfully deposited UGX {base_amount:,} to your wallet!')
                messages.info(request, f'Transaction: Amount UGX {base_amount:,} + Tax (5%) UGX {payment.platform_tax:,} = Total UGX {payment.amount:,}')
                return redirect('wallet_dashboard')
                
            elif payment_context == 'wallet_withdraw':
                # Wallet withdrawal - deduct base amount + tax (total payment amount)
                wallet = Wallet.objects.get(user=request.user)
                wallet.withdraw(
                    amount=payment.amount,
                    description=f'Card withdrawal - {payment.transaction_reference}',
                    payment_method='card'
                )
                
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.metadata['card_last4'] = card_number[-4:]
                payment.metadata['cardholder_name'] = cardholder_name
                payment.save()
                
                messages.success(request, f'Successfully withdrew UGX {payment.amount:,} from your wallet!')
                messages.info(request, f'Breakdown: Amount UGX {base_amount:,} + Tax (5%) UGX {payment.platform_tax:,} = Total UGX {payment.amount:,}')
                return redirect('wallet_dashboard')
                
            else:
                # Checkout payment
                cart = Cart.objects.get(user=request.user)
                cart_items = CartItem.objects.filter(cart=cart)
                
                for cart_item in cart_items:
                    item = cart_item.item
                    item.status = 'sold'
                    item.winning_bidder = request.user
                    item.save()
                
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.metadata['card_last4'] = card_number[-4:]
                payment.metadata['cardholder_name'] = cardholder_name
                payment.save()
                
                cart_items.delete()
                
                messages.success(request, f'Payment successful! Your order has been confirmed.')
                messages.info(request, f'Total paid: UGX {payment.amount:,} (including 5% platform tax)')
                return redirect('home')
                
    except Exception as e:
        payment.status = 'failed'
        payment.save()
        messages.error(request, f'Payment failed: {str(e)}')
        return redirect('checkout')


@login_required
def paypal_login_page(request, payment_id):
    """Display PayPal login page"""
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user, status='pending')
    
    # Determine payment context and return URL
    payment_context = request.GET.get('context', 'checkout')
    
    if payment_context == 'wallet_deposit':
        return_url = 'wallet_dashboard'
        cancel_url_name = 'wallet_deposit'
        payment_type = 'Wallet Deposit'
    elif payment_context == 'wallet_withdraw':
        return_url = 'wallet_dashboard'
        cancel_url_name = 'wallet_withdraw'
        payment_type = 'Wallet Withdrawal'
    else:
        return_url = 'home'
        cancel_url_name = 'checkout'
        payment_type = 'Purchase'
    
    # Extract tax info from metadata
    base_amount = payment.metadata.get('base_amount', str(payment.amount - payment.platform_tax))
    tax_amount = payment.platform_tax
    total_amount = payment.amount
    
    context = {
        'payment': payment,
        'payment_id': payment.payment_id,
        'payment_context': payment_context,
        'payment_type': payment_type,
        'base_amount': Decimal(base_amount) if isinstance(base_amount, str) else base_amount,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
        'return_url': return_url,
        'cancel_url': reverse(cancel_url_name),
    }
    
    return render(request, 'payments/paypal_login.html', context)


@login_required
@require_POST
def process_paypal_payment(request):
    """Process PayPal payment (demo mode)"""
    payment_id = request.POST.get('payment_id')
    payment_context = request.POST.get('payment_context', 'checkout')
    email = request.POST.get('email')
    password = request.POST.get('password')
    
    # Validate inputs
    if not all([payment_id, email, password]):
        messages.error(request, 'Email and password are required.')
        return redirect('paypal_login_page', payment_id=payment_id)
    
    try:
        payment = Payment.objects.get(payment_id=payment_id, user=request.user, status='pending')
    except Payment.DoesNotExist:
        messages.error(request, 'Payment not found or already processed.')
        return redirect('home')
    
    # Extract amounts from metadata
    base_amount = Decimal(payment.metadata.get('base_amount', str(payment.amount - payment.platform_tax)))
    
    try:
        with db_transaction.atomic():
            if payment_context == 'wallet_deposit':
                # Wallet deposit
                wallet, created = Wallet.objects.get_or_create(user=request.user)
                wallet.deposit(
                    amount=base_amount,
                    description=f'PayPal deposit - {payment.transaction_reference}',
                    transaction_type='deposit',
                    payment_method='paypal'
                )
                
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.metadata['paypal_email'] = email
                payment.save()
                
                messages.success(request, f'Successfully deposited UGX {base_amount:,} to your wallet!')
                messages.info(request, f'Transaction: Amount UGX {base_amount:,} + Tax (5%) UGX {payment.platform_tax:,} = Total UGX {payment.amount:,}')
                return redirect('wallet_dashboard')
                
            elif payment_context == 'wallet_withdraw':
                # Wallet withdrawal - deduct base amount + tax (total payment amount)
                wallet = Wallet.objects.get(user=request.user)
                wallet.withdraw(
                    amount=payment.amount,
                    description=f'PayPal withdrawal - {payment.transaction_reference}',
                    payment_method='paypal'
                )
                
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.metadata['paypal_email'] = email
                payment.save()
                
                messages.success(request, f'Successfully withdrew UGX {payment.amount:,} from your wallet!')
                messages.info(request, f'Breakdown: Amount UGX {base_amount:,} + Tax (5%) UGX {payment.platform_tax:,} = Total UGX {payment.amount:,}')
                return redirect('wallet_dashboard')
                
            else:
                # Checkout payment
                cart = Cart.objects.get(user=request.user)
                cart_items = CartItem.objects.filter(cart=cart)
                
                for cart_item in cart_items:
                    item = cart_item.item
                    item.status = 'sold'
                    item.winning_bidder = request.user
                    item.save()
                
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.metadata['paypal_email'] = email
                payment.save()
                
                cart_items.delete()
                
                messages.success(request, f'Payment successful! Your order has been confirmed.')
                messages.info(request, f'Total paid: UGX {payment.amount:,} (including 5% platform tax)')
                return redirect('home')
                
    except Exception as e:
        payment.status = 'failed'
        payment.save()
        messages.error(request, f'Payment failed: {str(e)}')
        return redirect('checkout')
