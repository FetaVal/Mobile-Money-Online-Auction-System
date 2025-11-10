from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import uuid

from .models import USSDSession, Payment
from .sms_service import SMSService
from .services import FlutterwaveService
from auctions.models import Item, Bid

@login_required
def ussd_simulator(request):
    """Main USSD simulator page"""
    return render(request, 'payments/ussd_simulator.html')

@login_required
def ussd_initiate(request):
    """Initiate a new USSD session"""
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number', '')
        network = request.POST.get('network', 'mtn')
        
        if not phone_number:
            return JsonResponse({'error': 'Phone number is required'}, status=400)
        
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        session_id = str(uuid.uuid4())
        
        session = USSDSession.objects.create(
            session_id=session_id,
            user=request.user,
            phone_number=phone_number,
            network=network,
            stage='main_menu',
            demo_mode=True
        )
        
        active_items = Item.objects.filter(status='active').order_by('-created_at')[:8]
        
        menu_text = f"{'MTN' if network == 'mtn' else 'Airtel'} AuctionHub\n\n"
        menu_text += "1. Bid on Items\n"
        menu_text += "2. List Item for Sale\n\n"
        menu_text += "0. Exit"
        
        session.last_message = menu_text
        session.session_data = {
            'items': [{'id': item.id, 'title': item.title, 'price': float(item.current_price)} for item in active_items],
            'main_menu': True
        }
        session.save()
        
        return JsonResponse({
            'session_id': session_id,
            'message': menu_text,
            'stage': 'main_menu'
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@login_required
def ussd_respond(request):
    """Handle USSD responses"""
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        session_id = request.POST.get('session_id')
        user_input = request.POST.get('input', '').strip()
        
        try:
            session = USSDSession.objects.get(session_id=session_id, is_active=True, user=request.user)
        except USSDSession.DoesNotExist:
            return JsonResponse({'error': 'Invalid or unauthorized session'}, status=400)
        
        if user_input == '0' and session.stage in ['main_menu', 'completed']:
            session.is_active = False
            session.stage = 'completed'
            session.save()
            return JsonResponse({
                'message': 'Thank you for using AuctionHub USSD!',
                'stage': 'completed',
                'end_session': True
            })
        
        if session.stage == 'main_menu':
            return handle_main_menu(session, user_input)
        elif session.stage == 'item_selection':
            return handle_item_selection(session, user_input)
        elif session.stage == 'action_selection':
            return handle_action_selection(session, user_input)
        elif session.stage == 'item_details':
            return handle_bid_entry(session, user_input)
        elif session.stage == 'bid_entry':
            return handle_pin_entry(session, user_input)
        elif session.stage == 'pin_entry':
            return handle_bid_confirmation(session, user_input)
        elif session.stage == 'buy_now_confirmation':
            return handle_buy_now_pin_entry(session, user_input)
        elif session.stage == 'buy_now_pin_entry':
            return handle_buy_now_confirmation(session, user_input)
        elif session.stage == 'listing_title':
            return handle_listing_title(session, user_input)
        elif session.stage == 'listing_description':
            return handle_listing_description(session, user_input)
        elif session.stage == 'listing_category':
            return handle_listing_category(session, user_input)
        elif session.stage == 'listing_price':
            return handle_listing_price(session, user_input)
        elif session.stage == 'listing_buy_now':
            return handle_listing_buy_now(session, user_input)
        elif session.stage == 'listing_shipping_cost':
            return handle_listing_shipping_cost(session, user_input)
        elif session.stage == 'listing_shipping_method':
            return handle_listing_shipping_method(session, user_input)
        elif session.stage == 'listing_duration':
            return handle_listing_duration(session, user_input)
        elif session.stage == 'listing_review':
            return handle_listing_review(session, user_input)
        elif session.stage == 'listing_tax_review':
            return handle_listing_tax_review(session, user_input)
        elif session.stage == 'listing_pin_entry':
            return handle_listing_pin_confirmation(session, user_input)
        
        return JsonResponse({'error': 'Invalid session stage'}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

def handle_main_menu(session, user_input):
    """Handle main menu selection (Bid or List)"""
    try:
        selection = int(user_input)
        
        if selection == 1:
            # Show items for bidding
            active_items = Item.objects.filter(status='active').order_by('-created_at')[:10]
            
            menu_text = "Select an item to bid:\n\n"
            for idx, item in enumerate(active_items, 1):
                menu_text += f"{idx}. {item.title[:30]}\n   UGX {item.current_price:,.0f}\n\n"
            menu_text += "0. Back to Main Menu"
            
            session.stage = 'item_selection'
            session.last_message = menu_text
            session.session_data['items'] = [{'id': item.id, 'title': item.title, 'price': float(item.current_price)} for item in active_items]
            session.save()
            
            return JsonResponse({
                'message': menu_text,
                'stage': 'item_selection'
            })
        
        elif selection == 2:
            # Start listing flow
            message = "List New Item\n\n"
            message += "Enter item title:\n(max 40 characters)\n\n"
            message += "0. Cancel"
            
            session.stage = 'listing_title'
            session.last_message = message
            session.session_data['listing_draft'] = {}
            session.save()
            
            return JsonResponse({
                'message': message,
                'stage': 'listing_title'
            })
        
        else:
            return JsonResponse({
                'message': 'Invalid selection. Please try again.\n\n' + session.last_message,
                'stage': 'main_menu'
            })
            
    except ValueError:
        return JsonResponse({
            'message': 'Invalid input. Please enter 1 or 2.\n\n' + session.last_message,
            'stage': 'main_menu'
        })

def handle_item_selection(session, user_input):
    """Handle item selection from main menu"""
    try:
        selection = int(user_input)
        items = session.session_data.get('items', [])
        
        if selection < 1 or selection > len(items):
            return JsonResponse({
                'message': 'Invalid selection. Please try again.\n\n' + session.last_message,
                'stage': 'main_menu'
            })
        
        selected_item_data = items[selection - 1]
        item = Item.objects.get(id=selected_item_data['id'])
        
        session.selected_item = item
        
        # Check if Buy Now is available (has buy_now_price and no bids)
        has_buy_now = item.buy_now_price and not item.bids.exists()
        
        if has_buy_now:
            # Show action selection menu
            session.stage = 'action_selection'
            
            message = f"Item: {item.title}\n\n"
            message += f"Current Bid: UGX {item.current_price:,.0f}\n"
            if item.buy_now_price:
                message += f"Buy Now: UGX {item.buy_now_price:,.0f}\n\n"
            message += "Select action:\n"
            message += "1. Place Bid\n"
            message += "2. Buy Now\n\n"
            message += "0. Back"
            
            session.last_message = message
            session.save()
            
            return JsonResponse({
                'message': message,
                'stage': 'action_selection'
            })
        else:
            # Go directly to bidding
            session.stage = 'item_details'
            
            message = f"Item: {item.title}\n\n"
            message += f"Current Bid: UGX {item.current_price:,.0f}\n"
            message += f"Minimum Bid: UGX {item.current_price + 1000:,.0f}\n\n"
            message += "Enter your bid amount:\n(or 0 to go back)"
            
            session.last_message = message
            session.save()
            
            return JsonResponse({
                'message': message,
                'stage': 'item_details'
            })
        
    except (ValueError, IndexError, Item.DoesNotExist):
        return JsonResponse({
            'message': 'Invalid selection. Please try again.\n\n' + session.last_message,
            'stage': 'main_menu'
        })

def handle_action_selection(session, user_input):
    """Handle action selection (Place Bid or Buy Now)"""
    try:
        selection = int(user_input)
        
        if selection == 0:
            session.stage = 'main_menu'
            session.selected_item = None
            session.save()
            return JsonResponse({
                'message': 'Returning to main menu...',
                'stage': 'main_menu'
            })
        elif selection == 1:
            # Place Bid
            session.stage = 'item_details'
            message = f"Item: {session.selected_item.title}\n\n"
            message += f"Current Bid: UGX {session.selected_item.current_price:,.0f}\n"
            message += f"Minimum Bid: UGX {session.selected_item.current_price + 1000:,.0f}\n\n"
            message += "Enter your bid amount:\n(or 0 to go back)"
            
            session.last_message = message
            session.save()
            
            return JsonResponse({
                'message': message,
                'stage': 'item_details'
            })
        elif selection == 2:
            # Buy Now
            if not session.selected_item.buy_now_price:
                return JsonResponse({
                    'message': 'Buy Now is not available for this item.\n\n' + session.last_message,
                    'stage': 'action_selection'
                })
            
            # Check wallet balance
            from users.models import Wallet
            try:
                wallet = session.user.wallet
                if wallet.balance < session.selected_item.buy_now_price:
                    message = f"❌ Insufficient Balance\n\n"
                    message += f"Buy Now Price: UGX {session.selected_item.buy_now_price:,.0f}\n"
                    message += f"Your Balance: UGX {wallet.balance:,.0f}\n\n"
                    message += f"Please deposit UGX {session.selected_item.buy_now_price - wallet.balance:,.0f} to your wallet.\n\n"
                    message += "0. Back"
                    return JsonResponse({
                        'message': message,
                        'stage': 'action_selection'
                    })
            except:
                return JsonResponse({
                    'message': '❌ Wallet Error\n\nPlease contact support.\n\n0. Back',
                    'stage': 'action_selection'
                })
            
            # Show Buy Now confirmation
            session.stage = 'buy_now_confirmation'
            TAX_RATE = Decimal('0.05')
            buy_now_price = session.selected_item.buy_now_price
            tax_amount = buy_now_price * TAX_RATE
            total_amount = buy_now_price
            seller_receives = total_amount - tax_amount
            
            session.session_data['buy_now_price'] = str(buy_now_price)
            session.session_data['tax_amount'] = str(tax_amount)
            session.session_data['total_amount'] = str(total_amount)
            session.session_data['seller_receives'] = str(seller_receives)
            
            network_name = 'MTN' if session.network == 'mtn' else 'Airtel'
            message = f"⚡ Buy Now Confirmation\n\n"
            message += f"Item: {session.selected_item.title[:30]}\n"
            message += f"Price: UGX {buy_now_price:,.0f}\n"
            message += f"Platform Tax (5%): UGX {tax_amount:,.0f}\n"
            message += f"Total: UGX {total_amount:,.0f}\n"
            message += f"Payment: Wallet\n\n"
            message += f"Enter your {network_name} PIN:\n(or 0 to cancel)"
            
            session.last_message = message
            session.save()
            
            return JsonResponse({
                'message': message,
                'stage': 'buy_now_confirmation'
            })
        else:
            return JsonResponse({
                'message': 'Invalid selection. Please try again.\n\n' + session.last_message,
                'stage': 'action_selection'
            })
    except ValueError:
        return JsonResponse({
            'message': 'Invalid input. Please enter 1 or 2.\n\n' + session.last_message,
            'stage': 'action_selection'
        })

def handle_buy_now_pin_entry(session, pin):
    """Handle PIN entry for Buy Now"""
    if pin == '0':
        session.stage = 'action_selection'
        session.save()
        return JsonResponse({
            'message': session.last_message if 'Select action' in session.last_message else 'Buy Now cancelled.',
            'stage': 'action_selection'
        })
    
    if len(pin) < 4:
        return JsonResponse({
            'message': 'Invalid PIN. Please enter your PIN:\n(or 0 to cancel)',
            'stage': 'buy_now_confirmation'
        })
    
    session.stage = 'buy_now_pin_entry'
    session.save()
    
    return handle_buy_now_confirmation(session, pin)

def handle_buy_now_confirmation(session, pin):
    """Process Buy Now purchase"""
    from django.db import transaction
    from auctions.models import Item
    from users.models import Wallet, WalletTransaction
    
    try:
        if not session.user:
            return JsonResponse({
                'message': '❌ Authentication Error\n\nPlease login and try again.',
                'stage': 'completed',
                'end_session': True,
                'error': 'No authenticated user'
            })
        
        item = session.selected_item
        
        # Pre-transaction checks
        if not item.buy_now_price or item.bids.exists():
            return JsonResponse({
                'message': '❌ Buy Now no longer available\n\nBidding has started on this item.',
                'stage': 'completed',
                'end_session': True
            })
        
        wallet = session.user.wallet
        buy_now_price = item.buy_now_price
        
        if wallet.balance < buy_now_price:
            return JsonResponse({
                'message': f'❌ Insufficient Balance\n\nYou need UGX {buy_now_price:,.0f}',
                'stage': 'completed',
                'end_session': True
            })
        
        # Calculate amounts
        TAX_RATE = Decimal('0.05')
        tax_amount = buy_now_price * TAX_RATE
        total_amount = buy_now_price
        seller_receives = total_amount - tax_amount
        
        # Atomic purchase transaction - works on all databases
        with transaction.atomic():
            # Attempt atomic conditional update - only succeeds if item hasn't been sold yet
            updated_count = Item.objects.filter(
                pk=item.pk,
                status='active',
                winner__isnull=True
            ).update(
                status='sold',
                winner=session.user
            )
            
            # If update didn't affect any rows, someone else bought it first
            if updated_count == 0:
                return JsonResponse({
                    'message': '❌ Someone else just purchased this item!',
                    'stage': 'completed',
                    'end_session': True
                })
            
            # Purchase successful - process wallet transactions
            wallet.balance -= total_amount
            wallet.save()
            
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='purchase',
                amount=-total_amount,
                description=f'Buy Now purchase (USSD): {item.title}',
                reference=f'USSD-BUYNOW-{item.pk}-{timezone.now().timestamp()}'
            )
            
            seller_wallet, _ = Wallet.objects.get_or_create(user=item.seller)
            seller_wallet.balance += seller_receives
            seller_wallet.save()
            
            WalletTransaction.objects.create(
                wallet=seller_wallet,
                transaction_type='sale',
                amount=seller_receives,
                description=f'Sale (USSD Buy Now): {item.title} (5% platform fee deducted)',
                reference=f'USSD-BUYNOW-SALE-{item.pk}-{timezone.now().timestamp()}'
            )
            
            WalletTransaction.objects.create(
                wallet=seller_wallet,
                transaction_type='platform_tax',
                amount=-tax_amount,
                description=f'Platform tax (5%) for {item.title}',
                reference=f'USSD-TAX-{item.pk}-{timezone.now().timestamp()}'
            )
        
        # Create transaction log
        from auctions.models import TransactionLog
        TransactionLog.objects.create(
            transaction_id=f'USSD-BUYNOW-{item.pk}-{session.user.pk}-{timezone.now().timestamp()}',
            transaction_type='buy_now_purchase',
            item=item,
            user=session.user,
            amount=total_amount,
            payment_method='ussd_wallet',
            payment_reference=f'USSD-BUYNOW-{item.pk}',
            data={
                'buyer': session.user.username,
                'seller': item.seller.username,
                'buy_now_price': str(total_amount),
                'platform_tax': str(tax_amount),
                'seller_receives': str(seller_receives),
                'network': session.network,
                'phone': session.phone_number,
                'timestamp': timezone.now().isoformat()
            }
        )
        
        # Send SMS confirmation
        sms = SMSService()
        sms.send_buy_now_confirmation(
            session.phone_number,
            item.title,
            total_amount,
            tax_amount,
            seller_receives
        )
        
        session.is_active = False
        session.stage = 'completed'
        session.save()
        
        message = f"✅ Purchase Successful!\n\n"
        message += f"Item: {item.title}\n"
        message += f"Amount: UGX {total_amount:,.0f}\n"
        message += f"Platform Tax: UGX {tax_amount:,.0f}\n\n"
        message += f"SMS receipt sent to {session.phone_number}\n\n"
        message += "Thank you for using AuctionHub!"
        
        return JsonResponse({
            'message': message,
            'stage': 'completed',
            'end_session': True
        })
        
    except Exception as e:
        import logging
        logging.error(f"Buy Now confirmation failed: {str(e)}")
        return JsonResponse({
            'message': f'❌ Purchase Failed\n\n{str(e)}',
            'stage': 'completed',
            'end_session': True
        })

def handle_bid_entry(session, user_input):
    """Handle bid amount entry"""
    if user_input == '0':
        session.stage = 'main_menu'
        session.selected_item = None
        session.save()
        return JsonResponse({
            'message': session.last_message if session.last_message and 'Select an item' in session.last_message else 'Returning to main menu...',
            'stage': 'main_menu'
        })
    
    try:
        bid_amount = Decimal(user_input)
        
        if bid_amount <= session.selected_item.current_price:
            message = f"Bid must be higher than UGX {session.selected_item.current_price:,.0f}\n\n"
            message += "Enter your bid amount:\n(or 0 to go back)"
            return JsonResponse({
                'message': message,
                'stage': 'item_details'
            })
        
        TAX_RATE = Decimal('0.05')
        tax_amount = bid_amount * TAX_RATE
        total_due = bid_amount + tax_amount
        
        session.bid_amount = bid_amount
        session.stage = 'bid_entry'
        session.session_data['subtotal'] = str(bid_amount)
        session.session_data['tax_amount'] = str(tax_amount)
        session.session_data['total_due'] = str(total_due)
        
        network_name = 'MTN' if session.network == 'mtn' else 'Airtel'
        message = f"Confirm Bid:\n\n"
        message += f"Item: {session.selected_item.title[:30]}\n"
        message += f"Amount: UGX {bid_amount:,.0f}\n"
        message += f"Platform Tax (5%): UGX {tax_amount:,.0f}\n"
        message += f"Total: UGX {total_due:,.0f}\n"
        message += f"Payment: {network_name} Mobile Money\n\n"
        message += f"Enter your {network_name} PIN:\n(or 0 to cancel)"
        
        session.last_message = message
        session.save()
        
        return JsonResponse({
            'message': message,
            'stage': 'bid_entry'
        })
        
    except (ValueError, InvalidOperation):
        message = "Invalid amount. Please enter a valid number:\n\n"
        message += f"Minimum: UGX {session.selected_item.current_price + 1000:,.0f}"
        return JsonResponse({
            'message': message,
            'stage': 'item_details'
        })

def handle_pin_entry(session, pin):
    """Handle PIN entry (not stored)"""
    if pin == '0':
        session.stage = 'main_menu'
        session.selected_item = None
        session.bid_amount = None
        session.save()
        return JsonResponse({
            'message': 'Bid cancelled. Returning to main menu.',
            'stage': 'main_menu'
        })
    
    if len(pin) < 4:
        return JsonResponse({
            'message': 'Invalid PIN. Please enter your PIN:\n(or 0 to cancel)',
            'stage': 'bid_entry'
        })
    
    session.stage = 'pin_entry'
    session.save()
    
    return handle_bid_confirmation(session, pin)

def handle_bid_confirmation(session, pin):
    """Process the bid and payment"""
    try:
        if not session.user:
            return JsonResponse({
                'message': '❌ Authentication Error\n\nPlease login and try again.',
                'stage': 'completed',
                'end_session': True,
                'error': 'No authenticated user'
            })
        
        tax_amount = Decimal(session.session_data.get('tax_amount', '0'))
        total_due = Decimal(session.session_data.get('total_due', str(session.bid_amount)))
        
        bid = Bid.objects.create(
            item=session.selected_item,
            bidder=session.user,
            amount=session.bid_amount
        )
        
        session.selected_item.current_price = session.bid_amount
        session.selected_item.save()
        
        payment = Payment.objects.create(
            user=session.user,
            item=session.selected_item,
            amount=total_due,
            platform_tax=tax_amount,
            payment_method=session.network,
            phone_number=session.phone_number,
            status='completed',
            description=f'USSD Bid Payment for {session.selected_item.title}',
            metadata={
                'network': session.network,
                'ussd_session': session.session_id,
                'demo_mode': True,
                'subtotal': str(session.bid_amount),
                'platform_tax': str(tax_amount),
                'total': str(total_due)
            }
        )
        
        SMSService.send_bid_confirmation(
            phone_number=session.phone_number,
            item_title=session.selected_item.title,
            bid_amount=float(session.bid_amount),
            tax_amount=float(tax_amount),
            total_amount=float(total_due),
            network=session.network.upper(),
            demo_mode=True
        )
        
        network_name = 'MTN' if session.network == 'mtn' else 'Airtel'
        message = f"✅ Bid Successful!\n\n"
        message += f"Item: {session.selected_item.title[:30]}\n"
        message += f"Bid: UGX {session.bid_amount:,.0f}\n"
        message += f"Tax (5%): UGX {tax_amount:,.0f}\n"
        message += f"Total Paid: UGX {total_due:,.0f}\n"
        message += f"Payment: {network_name} MoMo\n\n"
        message += f"SMS sent to {session.phone_number}\n\n"
        message += "Thank you for using AuctionHub!"
        
        session.stage = 'confirmation'
        session.is_active = False
        session.last_message = message
        session.save()
        
        return JsonResponse({
            'message': message,
            'stage': 'confirmation',
            'end_session': True,
            'bid_id': bid.id,
            'payment_id': str(payment.payment_id)
        })
        
    except Exception as e:
        message = f"❌ Bid Failed\n\n"
        message += f"Error: {str(e)}\n\n"
        message += "Please try again later."
        
        session.is_active = False
        session.save()
        
        return JsonResponse({
            'message': message,
            'stage': 'completed',
            'end_session': True,
            'error': str(e)
        })

def handle_listing_title(session, user_input):
    """Handle item title input"""
    if user_input == '0':
        session.stage = 'main_menu'
        session.save()
        return JsonResponse({
            'message': 'Listing cancelled. Returning to main menu.',
            'stage': 'main_menu'
        })
    
    if len(user_input) < 5 or len(user_input) > 40:
        return JsonResponse({
            'message': 'Title must be 5-40 characters.\n\nEnter item title:\n(or 0 to cancel)',
            'stage': 'listing_title'
        })
    
    session.session_data['listing_draft']['title'] = user_input
    session.stage = 'listing_description'
    session.save()
    
    message = "Enter item description:\n(max 160 characters)\n\n0. Cancel"
    
    return JsonResponse({
        'message': message,
        'stage': 'listing_description'
    })

def handle_listing_description(session, user_input):
    """Handle item description input"""
    if user_input == '0':
        session.stage = 'main_menu'
        session.save()
        return JsonResponse({
            'message': 'Listing cancelled.',
            'stage': 'main_menu'
        })
    
    if len(user_input) < 10 or len(user_input) > 160:
        return JsonResponse({
            'message': 'Description must be 10-160 characters.\n\nEnter description:\n(or 0 to cancel)',
            'stage': 'listing_description'
        })
    
    session.session_data['listing_draft']['description'] = user_input
    session.stage = 'listing_category'
    session.save()
    
    from auctions.models import Category
    categories = Category.objects.all()[:9]
    
    message = "Select category:\n\n"
    for idx, cat in enumerate(categories, 1):
        message += f"{idx}. {cat.name}\n"
    message += "\n0. Cancel"
    
    session.session_data['categories'] = [{'id': cat.id, 'name': cat.name} for cat in categories]
    session.save()
    
    return JsonResponse({
        'message': message,
        'stage': 'listing_category'
    })

def handle_listing_category(session, user_input):
    """Handle category selection"""
    if user_input == '0':
        session.stage = 'main_menu'
        session.save()
        return JsonResponse({
            'message': 'Listing cancelled.',
            'stage': 'main_menu'
        })
    
    try:
        selection = int(user_input)
        categories = session.session_data.get('categories', [])
        
        if selection < 1 or selection > len(categories):
            return JsonResponse({
                'message': 'Invalid selection. Try again:\n(or 0 to cancel)',
                'stage': 'listing_category'
            })
        
        selected_category = categories[selection - 1]
        session.session_data['listing_draft']['category_id'] = selected_category['id']
        session.session_data['listing_draft']['category_name'] = selected_category['name']
        session.stage = 'listing_price'
        session.save()
        
        message = "Enter starting price:\n(in UGX, min 10,000)\n\n0. Cancel"
        
        return JsonResponse({
            'message': message,
            'stage': 'listing_price'
        })
        
    except ValueError:
        return JsonResponse({
            'message': 'Invalid input. Enter category number:\n(or 0 to cancel)',
            'stage': 'listing_category'
        })

def handle_listing_price(session, user_input):
    """Handle starting price input"""
    if user_input == '0':
        session.stage = 'main_menu'
        session.save()
        return JsonResponse({
            'message': 'Listing cancelled.',
            'stage': 'main_menu'
        })
    
    try:
        price = Decimal(user_input)
        
        if price < 10000:
            return JsonResponse({
                'message': 'Price must be at least UGX 10,000.\n\nEnter price:\n(or 0 to cancel)',
                'stage': 'listing_price'
            })
        
        session.session_data['listing_draft']['starting_price'] = str(price)
        session.stage = 'listing_buy_now'
        session.save()
        
        message = "Enter Buy Now price:\n(in UGX, optional)\n\n"
        message += "Leave blank or enter 0 to skip Buy Now option.\n\n"
        message += "0. Skip"
        
        return JsonResponse({
            'message': message,
            'stage': 'listing_buy_now'
        })
        
    except (ValueError, InvalidOperation):
        return JsonResponse({
            'message': 'Invalid price. Enter valid amount:\n(or 0 to cancel)',
            'stage': 'listing_price'
        })

def handle_listing_buy_now(session, user_input):
    """Handle Buy Now price input"""
    if user_input == '0' or not user_input.strip():
        session.session_data['listing_draft']['buy_now_price'] = None
        session.stage = 'listing_shipping_cost'
        session.save()
        
        message = "Enter shipping cost:\n(in UGX)\n\n"
        message += "Enter 0 for free shipping.\n\n"
        message += "0. Free shipping"
        
        return JsonResponse({
            'message': message,
            'stage': 'listing_shipping_cost'
        })
    
    try:
        buy_now_price = Decimal(user_input)
        starting_price = Decimal(session.session_data['listing_draft']['starting_price'])
        
        if buy_now_price < starting_price:
            return JsonResponse({
                'message': f'Buy Now price must be ≥ starting price (UGX {starting_price:,.0f}).\n\nEnter Buy Now price:\n(or 0 to skip)',
                'stage': 'listing_buy_now'
            })
        
        session.session_data['listing_draft']['buy_now_price'] = str(buy_now_price)
        session.stage = 'listing_shipping_cost'
        session.save()
        
        message = "Enter shipping cost:\n(in UGX)\n\n"
        message += "Enter 0 for free shipping.\n\n"
        message += "0. Free shipping"
        
        return JsonResponse({
            'message': message,
            'stage': 'listing_shipping_cost'
        })
        
    except (ValueError, InvalidOperation):
        return JsonResponse({
            'message': 'Invalid price. Enter valid amount:\n(or 0 to skip Buy Now)',
            'stage': 'listing_buy_now'
        })

def handle_listing_shipping_cost(session, user_input):
    """Handle shipping cost input"""
    try:
        shipping_cost = Decimal(user_input) if user_input != '0' else Decimal('0')
        
        if shipping_cost < 0:
            return JsonResponse({
                'message': 'Shipping cost cannot be negative.\n\nEnter shipping cost:\n(or 0 for free)',
                'stage': 'listing_shipping_cost'
            })
        
        session.session_data['listing_draft']['shipping_cost'] = str(shipping_cost)
        session.stage = 'listing_shipping_method'
        session.save()
        
        message = "Select shipping method:\n\n"
        message += "1. Free Shipping\n"
        message += "2. Pick up from Store\n"
        message += "3. Both Options\n\n"
        message += "0. Cancel"
        
        return JsonResponse({
            'message': message,
            'stage': 'listing_shipping_method'
        })
        
    except (ValueError, InvalidOperation):
        return JsonResponse({
            'message': 'Invalid amount. Enter shipping cost:\n(or 0 for free)',
            'stage': 'listing_shipping_cost'
        })

def handle_listing_shipping_method(session, user_input):
    """Handle shipping method selection"""
    if user_input == '0':
        session.stage = 'main_menu'
        session.save()
        return JsonResponse({
            'message': 'Listing cancelled.',
            'stage': 'main_menu'
        })
    
    shipping_methods = {
        '1': 'free_shipping',
        '2': 'pickup',
        '3': 'both'
    }
    
    if user_input not in shipping_methods:
        return JsonResponse({
            'message': 'Invalid selection (1-3).\n\nSelect shipping method:\n(or 0 to cancel)',
            'stage': 'listing_shipping_method'
        })
    
    session.session_data['listing_draft']['shipping_method'] = shipping_methods[user_input]
    session.stage = 'listing_duration'
    session.save()
    
    message = "Select auction duration:\n\n"
    message += "1. 24 hours\n"
    message += "2. 48 hours (2 days)\n"
    message += "3. 72 hours (3 days)\n"
    message += "4. 7 days\n\n"
    message += "0. Cancel"
    
    return JsonResponse({
        'message': message,
        'stage': 'listing_duration'
    })

def handle_listing_duration(session, user_input):
    """Handle auction duration selection"""
    if user_input == '0':
        session.stage = 'main_menu'
        session.save()
        return JsonResponse({
            'message': 'Listing cancelled.',
            'stage': 'main_menu'
        })
    
    duration_map = {
        '1': ('24', '24 hours'),
        '2': ('48', '2 days'),
        '3': ('72', '3 days'),
        '4': ('168', '7 days')
    }
    
    if user_input not in duration_map:
        return JsonResponse({
            'message': 'Invalid selection (1-4).\n\nSelect duration:\n(or 0 to cancel)',
            'stage': 'listing_duration'
        })
    
    hours, label = duration_map[user_input]
    session.session_data['listing_draft']['duration_hours'] = hours
    session.session_data['listing_draft']['duration_label'] = label
    session.stage = 'listing_review'
    session.save()
    
    draft = session.session_data['listing_draft']
    message = "Review Your Listing:\n\n"
    message += f"Title: {draft['title']}\n"
    message += f"Description: {draft['description'][:30]}...\n"
    message += f"Category: {draft['category_name']}\n"
    message += f"Price: UGX {Decimal(draft['starting_price']):,.0f}\n"
    
    # Add Buy Now if available
    if draft.get('buy_now_price'):
        message += f"Buy Now: UGX {Decimal(draft['buy_now_price']):,.0f}\n"
    
    # Add shipping info
    if draft.get('shipping_cost'):
        shipping_cost = Decimal(draft['shipping_cost'])
        if shipping_cost > 0:
            message += f"Shipping: UGX {shipping_cost:,.0f}\n"
        else:
            message += "Shipping: Free\n"
    
    # Add shipping method
    method_labels = {
        'free_shipping': 'Free Shipping',
        'pickup': 'Store Pickup',
        'both': 'Shipping & Pickup'
    }
    if draft.get('shipping_method'):
        message += f"Delivery: {method_labels.get(draft['shipping_method'], 'N/A')}\n"
    
    message += f"Duration: {draft['duration_label']}\n\n"
    message += "1. Confirm & Publish\n"
    message += "0. Cancel"
    
    return JsonResponse({
        'message': message,
        'stage': 'listing_review'
    })

def handle_listing_review(session, user_input):
    """Handle listing review confirmation"""
    if user_input == '0':
        session.stage = 'main_menu'
        session.save()
        return JsonResponse({
            'message': 'Listing cancelled.',
            'stage': 'main_menu'
        })
    
    if user_input == '1':
        # Calculate listing tax before proceeding
        draft = session.session_data['listing_draft']
        starting_price = Decimal(draft['starting_price'])
        
        # Calculate 5% listing tax
        LISTING_TAX_RATE = Decimal('0.05')
        tax_amount = starting_price * LISTING_TAX_RATE
        total_due = tax_amount  # Only pay the tax, not the item price
        
        # Store in session
        session.session_data['listing_tax'] = str(tax_amount)
        session.session_data['listing_total'] = str(total_due)
        session.stage = 'listing_tax_review'
        session.save()
        
        # Show tax breakdown
        network_name = 'MTN' if session.network == 'mtn' else 'Airtel'
        message = f"Listing Fee Payment:\n\n"
        message += f"Item Price: UGX {starting_price:,.0f}\n"
        message += f"Listing Tax (5%): UGX {tax_amount:,.0f}\n"
        message += f"Total to Pay: UGX {total_due:,.0f}\n"
        message += f"Payment: {network_name} Mobile Money\n\n"
        message += f"Enter your {network_name} PIN to confirm:\n(or 0 to cancel)"
        
        return JsonResponse({
            'message': message,
            'stage': 'listing_tax_review'
        })
    
    return JsonResponse({
        'message': 'Invalid input. Enter 1 to confirm or 0 to cancel.',
        'stage': 'listing_review'
    })

def handle_listing_tax_review(session, pin):
    """Handle PIN entry for listing tax payment"""
    if pin == '0':
        session.stage = 'main_menu'
        session.session_data.pop('listing_draft', None)
        session.session_data.pop('listing_tax', None)
        session.session_data.pop('listing_total', None)
        session.save()
        return JsonResponse({
            'message': 'Listing cancelled. Returning to main menu.',
            'stage': 'main_menu'
        })
    
    if len(pin) < 4:
        network_name = 'MTN' if session.network == 'mtn' else 'Airtel'
        return JsonResponse({
            'message': f'Invalid PIN. Please enter your {network_name} PIN:\n(or 0 to cancel)',
            'stage': 'listing_tax_review'
        })
    
    # PIN is valid, move to confirmation
    session.stage = 'listing_pin_entry'
    session.save()
    
    return handle_listing_pin_confirmation(session, pin)

def handle_listing_pin_confirmation(session, pin):
    """Process listing tax payment and create item"""
    try:
        from datetime import timedelta
        from auctions.models import Category
        
        draft = session.session_data['listing_draft']
        tax_amount = Decimal(session.session_data.get('listing_tax', '0'))
        total_due = Decimal(session.session_data.get('listing_total', '0'))
        starting_price = Decimal(draft['starting_price'])
        
        # Get category
        category = Category.objects.get(id=draft['category_id'])
        
        # Calculate end time
        duration_hours = int(draft['duration_hours'])
        end_time = timezone.now() + timedelta(hours=duration_hours)
        
        # Determine shipping options from shipping_method
        shipping_method = draft.get('shipping_method', 'both')
        free_shipping = shipping_method in ['free_shipping', 'both']
        pickup_available = shipping_method in ['pickup', 'both']
        
        # Create item
        item = Item.objects.create(
            seller=session.user,
            category=category,
            title=draft['title'],
            description=draft['description'],
            starting_price=starting_price,
            current_price=starting_price,
            buy_now_price=Decimal(draft['buy_now_price']) if draft.get('buy_now_price') else None,
            shipping_cost_base=Decimal(draft.get('shipping_cost', '0')),
            free_shipping=free_shipping,
            pickup_available=pickup_available,
            end_time=end_time,
            status='active',
            created_via='ussd',
            requires_media_followup=True
        )
        
        # Create payment record for listing fee
        payment = Payment.objects.create(
            user=session.user,
            item=item,
            amount=total_due,
            platform_tax=tax_amount,
            payment_method=session.network,
            phone_number=session.phone_number,
            status='completed',
            description=f'USSD Listing Fee for {item.title}',
            metadata={
                'network': session.network,
                'ussd_session': session.session_id,
                'demo_mode': True,
                'listing_fee': str(tax_amount),
                'item_price': str(starting_price),
                'payment_type': 'listing_fee'
            }
        )
        
        # Send SMS confirmation
        SMSService.send_listing_confirmation(
            phone_number=session.phone_number,
            item_title=item.title,
            item_id=item.id,
            starting_price=float(starting_price),
            duration=draft['duration_label'],
            network=session.network.upper(),
            demo_mode=True
        )
        
        network_name = 'MTN' if session.network == 'mtn' else 'Airtel'
        message = f"✅ Payment Successful!\n✅ Item Listed!\n\n"
        message += f"Title: {item.title}\n"
        message += f"Price: UGX {starting_price:,.0f}\n"
        message += f"Listing Fee Paid: UGX {tax_amount:,.0f}\n"
        message += f"Duration: {draft['duration_label']}\n"
        message += f"Item ID: #{item.id}\n"
        message += f"Payment: {network_name} MoMo\n\n"
        message += f"SMS sent to {session.phone_number}\n\n"
        message += "Note: Upload images via web for better visibility.\n\n"
        message += "Thank you for using AuctionHub!"
        
        session.stage = 'completed'
        session.is_active = False
        session.save()
        
        return JsonResponse({
            'message': message,
            'stage': 'completed',
            'end_session': True,
            'item_id': item.id,
            'payment_id': str(payment.payment_id)
        })
        
    except Exception as e:
        message = f"❌ Listing Failed\n\n"
        message += f"Error: {str(e)}\n\n"
        message += "Please try again later."
        
        session.is_active = False
        session.save()
        
        return JsonResponse({
            'message': message,
            'stage': 'completed',
            'end_session': True,
            'error': str(e)
        })

@login_required
def ussd_wallet_deposit(request, payment_id):
    """USSD wallet deposit with PIN confirmation"""
    try:
        payment = Payment.objects.select_related('user').get(
            payment_id=payment_id, 
            user=request.user, 
            status='pending'
        )
    except Payment.DoesNotExist:
        messages.error(request, 'Payment not found or unauthorized.')
        return redirect('wallet_deposit')
    
    if payment.user != request.user:
        messages.error(request, 'Unauthorized access to payment.')
        return redirect('wallet_deposit')
    
    phone_number = payment.phone_number or ''
    
    context = {
        'payment': payment,
        'action': 'deposit',
        'network': payment.payment_method,
        'amount': payment.amount,
        'phone_number': phone_number,
    }
    
    return render(request, 'payments/ussd_wallet.html', context)

@login_required
def ussd_wallet_withdraw(request, payment_id):
    """USSD wallet withdrawal with PIN confirmation"""
    try:
        payment = Payment.objects.select_related('user').get(
            payment_id=payment_id, 
            user=request.user, 
            status='pending'
        )
    except Payment.DoesNotExist:
        messages.error(request, 'Payment not found or unauthorized.')
        return redirect('wallet_withdraw')
    
    if payment.user != request.user:
        messages.error(request, 'Unauthorized access to payment.')
        return redirect('wallet_withdraw')
    
    from users.models import Wallet
    try:
        wallet = Wallet.objects.get(user=request.user)
        if not wallet.can_withdraw(payment.amount):
            messages.error(request, 'Insufficient balance for withdrawal.')
            return redirect('wallet_withdraw')
    except Wallet.DoesNotExist:
        messages.error(request, 'Wallet not found.')
        return redirect('wallet_withdraw')
    
    phone_number = payment.phone_number or ''
    
    context = {
        'payment': payment,
        'action': 'withdraw',
        'network': payment.payment_method,
        'amount': payment.amount,
        'phone_number': phone_number,
    }
    
    return render(request, 'payments/ussd_wallet.html', context)

@login_required
def ussd_wallet_initiate(request):
    """Initiate USSD wallet transaction"""
    if request.method == 'POST':
        payment_id = request.POST.get('payment_id')
        phone_number = request.POST.get('phone_number', '')
        network = request.POST.get('network', 'mtn')
        action = request.POST.get('action', 'deposit')
        
        if not phone_number or not payment_id:
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        try:
            payment = Payment.objects.select_related('user').get(
                payment_id=payment_id, 
                user=request.user, 
                status='pending'
            )
        except Payment.DoesNotExist:
            return JsonResponse({'error': 'Payment not found or unauthorized'}, status=400)
        
        if payment.user != request.user:
            return JsonResponse({'error': 'Unauthorized access'}, status=403)
        
        is_checkout = 'cart_items' in payment.metadata
        
        if is_checkout:
            base_amount = Decimal(str(payment.metadata.get('subtotal', 0)))
            shipping_cost = Decimal(str(payment.metadata.get('shipping_cost', 0)))
            tax_amount = Decimal(str(payment.metadata.get('tax_amount', 0)))
            total_amount = base_amount + shipping_cost + tax_amount
        else:
            TAX_RATE = Decimal('0.05')
            base_amount = payment.amount
            shipping_cost = Decimal('0')
            tax_amount = base_amount * TAX_RATE
            total_amount = base_amount + tax_amount
        
        session_id = str(uuid.uuid4())
        
        session = USSDSession.objects.create(
            session_id=session_id,
            user=request.user,
            phone_number=phone_number,
            network=network,
            stage='wallet_pin_entry',
            demo_mode=True,
            session_data={
                'payment_id': str(payment_id),
                'action': action,
                'base_amount': str(base_amount),
                'shipping_cost': str(shipping_cost) if is_checkout else '0',
                'tax_amount': str(tax_amount),
                'total_amount': str(total_amount)
            }
        )
        
        network_name = 'MTN' if network == 'mtn' else 'Airtel'
        action_text = 'Deposit' if action == 'deposit' else 'Withdraw'
        
        menu_text = f"{network_name} Mobile Money\n\n"
        
        if is_checkout:
            menu_text += f"Checkout Payment\n"
            menu_text += f"Subtotal: UGX {base_amount:,.0f}\n"
            if shipping_cost > 0:
                menu_text += f"Shipping: UGX {shipping_cost:,.0f}\n"
            menu_text += f"Platform Tax (5%): UGX {tax_amount:,.0f}\n"
            menu_text += f"Total: UGX {total_amount:,.0f}\n\n"
        else:
            menu_text += f"Wallet {action_text}\n"
            menu_text += f"Amount: UGX {base_amount:,.0f}\n"
            menu_text += f"Platform Tax (5%): UGX {tax_amount:,.0f}\n"
            menu_text += f"Total: UGX {total_amount:,.0f}\n\n"
        
        menu_text += "Enter your PIN to confirm:"
        
        session.last_message = menu_text
        session.save()
        
        return JsonResponse({
            'session_id': session_id,
            'message': menu_text,
            'stage': 'wallet_pin_entry'
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@login_required
def ussd_wallet_respond(request):
    """Handle USSD wallet transaction responses"""
    if request.method == 'POST':
        session_id = request.POST.get('session_id')
        user_input = request.POST.get('input', '').strip()
        
        try:
            session = USSDSession.objects.get(session_id=session_id, is_active=True, user=request.user)
        except USSDSession.DoesNotExist:
            return JsonResponse({'error': 'Invalid session'}, status=400)
        
        if session.stage == 'wallet_pin_entry':
            return handle_wallet_pin_confirmation(session, user_input)
        
        return JsonResponse({'error': 'Invalid session stage'}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

def handle_wallet_pin_confirmation(session, pin):
    """Handle wallet transaction PIN confirmation"""
    from users.models import Wallet
    
    if len(pin) != 4 or not pin.isdigit():
        return JsonResponse({
            'message': 'Invalid PIN. Please enter a 4-digit PIN:',
            'stage': 'wallet_pin_entry'
        })
    
    try:
        payment_id = session.session_data.get('payment_id')
        action = session.session_data.get('action', 'deposit')
        base_amount = Decimal(str(session.session_data.get('base_amount', 0)))
        tax_amount = Decimal(str(session.session_data.get('tax_amount', 0)))
        total_amount = Decimal(str(session.session_data.get('total_amount', 0)))
        shipping_cost = Decimal(str(session.session_data.get('shipping_cost', 0)))
        
        payment = Payment.objects.get(payment_id=payment_id, user=session.user, status='pending')
        wallet, created = Wallet.objects.get_or_create(user=session.user)
        
        network_name = 'MTN' if session.network == 'mtn' else 'Airtel'
        
        if action == 'deposit':
            is_checkout = 'cart_items' in payment.metadata
            
            wallet.deposit(
                amount=base_amount,
                description=f'{network_name} Mobile Money deposit - {payment.transaction_reference}',
                transaction_type='deposit',
                payment_method=session.network
            )
            
            payment.amount = total_amount
            payment.platform_tax = tax_amount
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.metadata['base_amount'] = str(base_amount)
            payment.metadata['platform_tax'] = str(tax_amount)
            payment.metadata['total'] = str(total_amount)
            payment.save()
            
            SMSService.send_wallet_confirmation(
                phone_number=session.phone_number,
                amount=float(base_amount),
                tax_amount=float(tax_amount),
                total_amount=float(total_amount),
                balance=float(wallet.balance),
                action='deposit',
                network=network_name,
                demo_mode=True
            )
            
            if is_checkout:
                from auctions.models import Cart, CartItem
                from payments.services import settle_payment_to_sellers
                
                try:
                    cart = Cart.objects.get(user=session.user)
                    cart_items = list(cart.items.all())
                    
                    if cart_items:
                        settle_payment_to_sellers(payment, cart_items)
                        cart.items.all().delete()
                except Cart.DoesNotExist:
                    pass
                
                message = f"✅ Payment Successful!\n\n"
                message += f"Subtotal: UGX {base_amount:,.0f}\n"
                if shipping_cost > 0:
                    message += f"Shipping: UGX {shipping_cost:,.0f}\n"
                message += f"Platform Tax (5%): UGX {tax_amount:,.0f}\n"
                message += f"Total Paid: UGX {total_amount:,.0f}\n"
                message += f"Payment: {network_name} MoMo\n\n"
                message += f"Processing your order...\n"
                message += f"SMS sent to {session.phone_number}\n\n"
                message += "Thank you!"
            else:
                message = f"✅ Deposit Successful!\n\n"
                message += f"Amount: UGX {base_amount:,.0f}\n"
                message += f"Tax (5%): UGX {tax_amount:,.0f}\n"
                message += f"Total Paid: UGX {total_amount:,.0f}\n"
                message += f"New Balance: UGX {wallet.balance:,.0f}\n"
                message += f"Payment: {network_name} MoMo\n\n"
                message += f"SMS sent to {session.phone_number}\n\n"
                message += "Thank you!"
            
        elif action == 'withdraw':
            if not wallet.can_withdraw(base_amount):
                message = f"❌ Withdrawal Failed\n\n"
                message += f"Insufficient balance or wallet locked.\n\n"
                message += f"Available: UGX {wallet.balance:,.0f}"
                
                session.is_active = False
                session.save()
                
                return JsonResponse({
                    'message': message,
                    'stage': 'completed',
                    'end_session': True,
                    'error': 'Insufficient balance'
                })
            
            wallet.withdraw(
                amount=base_amount,
                description=f'{network_name} Mobile Money withdrawal - {payment.transaction_reference}',
                payment_method=session.network
            )
            
            payment.amount = total_amount
            payment.platform_tax = tax_amount
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.metadata['base_amount'] = str(base_amount)
            payment.metadata['platform_tax'] = str(tax_amount)
            payment.metadata['total'] = str(total_amount)
            payment.save()
            
            SMSService.send_wallet_confirmation(
                phone_number=session.phone_number,
                amount=float(base_amount),
                tax_amount=float(tax_amount),
                total_amount=float(total_amount),
                balance=float(wallet.balance),
                action='withdraw',
                network=network_name,
                demo_mode=True
            )
            
            message = f"✅ Withdrawal Successful!\n\n"
            message += f"Amount: UGX {base_amount:,.0f}\n"
            message += f"Tax (5%): UGX {tax_amount:,.0f}\n"
            message += f"Total Cost: UGX {total_amount:,.0f}\n"
            message += f"Sent to: {session.phone_number}\n"
            message += f"New Balance: UGX {wallet.balance:,.0f}\n"
            message += f"Payment: {network_name} MoMo\n\n"
            message += f"SMS sent\n\n"
            message += "Thank you!"
        else:
            message = "Invalid action"
        
        session.stage = 'wallet_completed'
        session.is_active = False
        session.last_message = message
        session.save()
        
        return JsonResponse({
            'message': message,
            'stage': 'wallet_completed',
            'end_session': True,
            'payment_id': str(payment.payment_id)
        })
        
    except Exception as e:
        message = f"❌ Transaction Failed\n\n"
        message += f"Error: {str(e)}\n\n"
        message += "Please try again later."
        
        session.is_active = False
        session.save()
        
        return JsonResponse({
            'message': message,
            'stage': 'completed',
            'end_session': True,
            'error': str(e)
        })
