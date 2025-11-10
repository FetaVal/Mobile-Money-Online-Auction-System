import os
import stripe
import paypalrestsdk
import requests
import uuid
from decimal import Decimal
from django.conf import settings

stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', os.getenv('STRIPE_SECRET_KEY'))

class PaymentService:
    @staticmethod
    def get_service(payment_method, country_code=None):
        if payment_method in ['mtn', 'airtel']:
            return FlutterwaveService()
        elif payment_method == 'card':
            return StripeService()
        elif payment_method == 'paypal':
            return PayPalService()
        else:
            return BankTransferService()
    
    def process_payment(self, amount, currency, payment_data):
        raise NotImplementedError("Subclasses must implement process_payment")

class FlutterwaveService(PaymentService):
    def __init__(self):
        self.base_url = "https://api.flutterwave.com/v3"
        self.secret_key = os.getenv('FLUTTERWAVE_SECRET_KEY', '')
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
    
    def process_payment(self, amount, currency, payment_data):
        phone_number = payment_data.get('phone_number', '')
        network = payment_data.get('network', 'MTN').upper()
        email = payment_data.get('email', '')
        fullname = payment_data.get('fullname', 'Customer')
        
        if not phone_number or not email:
            return {
                'success': False,
                'message': 'Phone number and email are required'
            }
        
        if not self.secret_key:
            transaction_id = f"DEMO-{network}-{uuid.uuid4().hex[:8].upper()}"
            return {
                'success': True,
                'transaction_id': transaction_id,
                'message': f'✅ {network} Mobile Money payment simulated successfully! Check your phone at {phone_number}',
                'data': {
                    'id': transaction_id,
                    'status': 'successful',
                    'amount': amount,
                    'currency': currency,
                    'network': network,
                    'demo_mode': True
                }
            }
        
        phone_clean = phone_number.replace('0', '256', 1) if phone_number.startswith('0') else phone_number
        phone_clean = phone_clean.replace('+', '')
        
        try:
            response = requests.post(
                f"{self.base_url}/charges?type=mobile_money_uganda",
                json={
                    "tx_ref": f"TXN-{uuid.uuid4()}",
                    "amount": str(amount),
                    "currency": currency,
                    "network": network,
                    "email": email,
                    "phone_number": phone_clean,
                    "fullname": fullname,
                    "redirect_url": payment_data.get('redirect_url', '')
                },
                headers=self.headers
            )
            
            result = response.json()
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'transaction_id': result.get('data', {}).get('id'),
                    'message': 'Please check your phone for payment prompt',
                    'data': result.get('data')
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Payment failed'),
                    'data': result
                }
        except Exception as e:
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

class StripeService(PaymentService):
    def process_payment(self, amount, currency, payment_data):
        if not stripe.api_key:
            transaction_id = f"DEMO-STRIPE-{uuid.uuid4().hex[:8].upper()}"
            return {
                'success': True,
                'session_id': transaction_id,
                'message': f'✅ Card payment of {currency} {amount} processed successfully via Stripe (Demo Mode)',
                'data': {
                    'transaction_id': transaction_id,
                    'status': 'paid',
                    'amount': amount,
                    'currency': currency,
                    'demo_mode': True
                }
            }
        
        try:
            amount_cents = int(float(amount) * 100)
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': currency.lower(),
                        'unit_amount': amount_cents,
                        'product_data': {
                            'name': payment_data.get('description', 'Auction Purchase'),
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=payment_data.get('success_url', ''),
                cancel_url=payment_data.get('cancel_url', ''),
                client_reference_id=payment_data.get('user_id'),
                metadata=payment_data.get('metadata', {})
            )
            
            return {
                'success': True,
                'session_id': session.id,
                'session_url': session.url,
                'message': 'Redirecting to Stripe checkout...'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Stripe error: {str(e)}'
            }

class PayPalService(PaymentService):
    def __init__(self):
        client_id = os.getenv('PAYPAL_CLIENT_ID', '')
        client_secret = os.getenv('PAYPAL_SECRET_ID', '')
        
        if client_id and client_secret:
            paypalrestsdk.configure({
                "mode": os.getenv('PAYPAL_MODE', 'sandbox'),
                "client_id": client_id,
                "client_secret": client_secret
            })
        self.has_credentials = bool(client_id and client_secret)
    
    def process_payment(self, amount, currency, payment_data):
        if not self.has_credentials:
            transaction_id = f"DEMO-PAYPAL-{uuid.uuid4().hex[:8].upper()}"
            return {
                'success': True,
                'payment_id': transaction_id,
                'message': f'✅ PayPal payment of {currency} {amount} processed successfully (Demo Mode)',
                'data': {
                    'transaction_id': transaction_id,
                    'status': 'completed',
                    'amount': amount,
                    'currency': currency,
                    'demo_mode': True
                }
            }
        
        try:
            payment = paypalrestsdk.Payment({
                "intent": "sale",
                "payer": {
                    "payment_method": "paypal"
                },
                "redirect_urls": {
                    "return_url": payment_data.get('success_url', ''),
                    "cancel_url": payment_data.get('cancel_url', '')
                },
                "transactions": [{
                    "amount": {
                        "total": str(amount),
                        "currency": currency
                    },
                    "description": payment_data.get('description', 'Auction Purchase')
                }]
            })
            
            if payment.create():
                for link in payment.links:
                    if link.rel == "approval_url":
                        return {
                            'success': True,
                            'payment_id': payment.id,
                            'approval_url': link.href,
                            'message': 'Redirecting to PayPal...'
                        }
            else:
                return {
                    'success': False,
                    'message': payment.error
                }
        except Exception as e:
            return {
                'success': False,
                'message': f'PayPal error: {str(e)}'
            }

class BankTransferService(PaymentService):
    def process_payment(self, amount, currency, payment_data):
        bank_details = {
            'bank_name': 'Stanbic Bank Uganda',
            'account_number': '9030007345678',
            'account_name': 'AuctionHub Limited',
            'swift_code': 'SBICUGKX',
            'branch': 'Kampala Main Branch'
        }
        
        return {
            'success': True,
            'message': 'Bank transfer initiated',
            'bank_details': bank_details,
            'reference': f"BANK-{uuid.uuid4()}",
            'note': 'Please use the reference number when making your transfer'
        }

def settle_payment_to_sellers(payment, cart_items):
    """
    Credit seller wallets for completed payments.
    This function MUST be called within a transaction.atomic() block.
    
    Args:
        payment: Payment object that was completed
        cart_items: QuerySet or list of CartItem objects being purchased
        
    Returns:
        dict with settlement results
    """
    from users.models import Wallet
    from django.utils import timezone
    
    results = {
        'success': True,
        'sellers_credited': [],
        'errors': []
    }
    
    for cart_item in cart_items:
        item = cart_item.item
        seller = item.seller
        amount = item.current_price
        
        try:
            wallet, created = Wallet.objects.get_or_create(user=seller)
            
            wallet.deposit(
                amount=amount,
                description=f'Sale of "{item.title}" to {payment.user.username}',
                transaction_type='sale',
                payment_method=payment.payment_method
            )
            
            item.winner = payment.user
            item.status = 'sold'
            item.save(update_fields=['winner', 'status'])
            
            results['sellers_credited'].append({
                'seller': seller.username,
                'amount': float(amount),
                'item': item.title
            })
            
        except Exception as e:
            results['success'] = False
            results['errors'].append({
                'seller': seller.username,
                'item': item.title,
                'error': str(e)
            })
    
    payment.completed_at = timezone.now()
    payment.save(update_fields=['completed_at'])
    
    return results
