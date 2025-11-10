from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.models import User
from .models import Item, Category, Bid, Review, Cart, CartItem, TransactionLog
from .forms import PlaceBidForm, ReviewForm

def home(request):
    from django.db.models import Q
    
    items = Item.objects.filter(status='active').select_related('category', 'seller')
    
    search_query = request.GET.get('q', '')
    category_filter = request.GET.get('category', 'all')
    min_price = request.GET.get('min_price', '0')
    max_price = request.GET.get('max_price', '10000000')
    
    if search_query:
        items = items.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
    
    if category_filter and category_filter != 'all':
        try:
            category = Category.objects.get(name__iexact=category_filter)
            items = items.filter(category=category)
        except Category.DoesNotExist:
            pass
    
    try:
        min_price_val = float(min_price) if min_price else 0
        max_price_val = float(max_price) if max_price else 10000000
        items = items.filter(current_price__gte=min_price_val, current_price__lte=max_price_val)
    except ValueError:
        pass
    
    items = items.order_by('-created_at')
    
    categories = Category.objects.all()
    
    context = {
        'items': items,
        'all_categories': categories,
        'search_query': search_query,
        'selected_category': category_filter,
        'min_price': min_price,
        'max_price': max_price,
        'item_count': items.count(),
    }
    return render(request, 'home.html', context)

def item_list(request):
    items = Item.objects.filter(status='active').order_by('-created_at')
    
    category_filter = request.GET.get('category')
    if category_filter:
        items = items.filter(category__name=category_filter)
    
    sort_by = request.GET.get('sort', '-created_at')
    if sort_by == 'price_low':
        items = items.order_by('current_price')
    elif sort_by == 'price_high':
        items = items.order_by('-current_price')
    elif sort_by == 'ending_soon':
        items = items.filter(end_time__gt=timezone.now()).order_by('end_time')
    
    categories = Category.objects.all()
    
    context = {
        'items': items,
        'categories': categories,
        'selected_category': category_filter,
    }
    return render(request, 'auctions/item_list.html', context)

def item_detail(request, pk):
    item = get_object_or_404(Item, pk=pk)
    
    # Privacy enforcement: private and off_sale items only visible to seller
    if item.status in ['private', 'off_sale']:
        if not request.user.is_authenticated or request.user != item.seller:
            messages.error(request, "This item is not available for public viewing.")
            return redirect('home')
    
    item.view_count += 1
    item.save(update_fields=['view_count'])
    
    bids = item.bids.select_related('bidder').order_by('-amount')[:10]
    reviews = item.reviews.select_related('reviewer').all()[:5]
    
    highest_bid = item.bids.order_by('-amount').first()
    is_highest_bidder = False
    if request.user.is_authenticated and highest_bid:
        is_highest_bidder = highest_bid.bidder == request.user
    
    seller_rating = 0
    seller_review_count = 0
    if hasattr(item.seller, 'profile'):
        seller_rating = item.seller.profile.average_rating()
        seller_review_count = item.seller.profile.rating_count
    
    all_images = []
    if item.main_image:
        all_images.append(item.main_image)
    for img_field in ['image1', 'image2', 'image3', 'image4']:
        img = getattr(item, img_field)
        if img:
            all_images.append(img)
    
    bid_form = PlaceBidForm(item=item)
    review_form = ReviewForm()
    
    user_has_bid = False
    user_has_reviewed = False
    if request.user.is_authenticated:
        user_has_bid = Bid.objects.filter(item=item, bidder=request.user).exists()
        user_has_reviewed = Review.objects.filter(item=item, reviewer=request.user).exists()
    
    # Check if Buy Now should be shown
    # Show Buy Now until the first valid bid (hide after first bid)
    show_buy_now = False
    if item.buy_now_price and item.status == 'active':
        # Hide Buy Now if there are any bids
        has_bids = item.bids.exists()
        show_buy_now = not has_bids
    
    # Check if CAPTCHA should be shown for this auction
    show_captcha_for_item = request.session.get(f'show_captcha_{item.id}', False)
    
    context = {
        'item': item,
        'bids': bids,
        'reviews': reviews,
        'highest_bid': highest_bid,
        'is_highest_bidder': is_highest_bidder,
        'seller_rating': seller_rating,
        'seller_review_count': seller_review_count,
        'all_images': all_images,
        'bid_form': bid_form,
        'form': review_form,
        'min_bid': item.current_price + item.min_increment,
        'user_has_bid': user_has_bid,
        'user_has_reviewed': user_has_reviewed,
        'show_buy_now': show_buy_now,
        'show_captcha': show_captcha_for_item,
    }
    return render(request, 'auctions/item_detail.html', context)

@login_required
def place_bid(request, pk):
    item = get_object_or_404(Item, pk=pk)
    
    if request.method == 'POST':
        if item.seller == request.user:
            messages.error(request, "You cannot bid on your own item!")
            return redirect('item_detail', pk=pk)
        
        if item.status != 'active':
            messages.error(request, "This auction is no longer active.")
            return redirect('item_detail', pk=pk)
        
        if item.end_time <= timezone.now():
            messages.error(request, "This auction has ended.")
            return redirect('item_detail', pk=pk)
        
        form = PlaceBidForm(request.POST, item=item)
        if form.is_valid():
            bid = form.save(commit=False)
            bid.item = item
            bid.bidder = request.user
            bid_amount = bid.amount
            
            # RUN ALL CHECKS IN PARALLEL - collect results but don't return early
            from django.conf import settings
            from .rapid_bidding import RapidBiddingDetector
            
            should_reject_bid = False
            rejection_reasons = []
            
            # Get user bypass permissions (superusers are auto-exempt from ALL restrictions)
            is_superuser = request.user.is_superuser
            user_profile = request.user.profile
            bypass_all = is_superuser or user_profile.bypass_all_restrictions
            bypass_rapid_bidding = is_superuser or user_profile.bypass_rapid_bidding_check or bypass_all
            bypass_account_age = is_superuser or user_profile.bypass_account_age_check or bypass_all
            bypass_fraud = is_superuser or user_profile.bypass_fraud_detection or bypass_all
            
            # 1. Check rapid bidding (soft/hard thresholds) - unless user has bypass
            if not bypass_rapid_bidding:
                is_allowed, action_type, rapid_message, cooldown = RapidBiddingDetector.check_rapid_bidding(
                    request.user, item, bid_amount
                )
                
                if not is_allowed:
                    should_reject_bid = True
                    if action_type == 'soft_challenge':
                        # Store pending bid for CAPTCHA
                        session_key = f'pending_bid_{item.id}'
                        request.session[session_key] = {
                            'amount': str(bid_amount),
                            'item_id': item.id,
                            'timestamp': timezone.now().isoformat(),
                        }
                        request.session[f'show_captcha_{item.id}'] = True
                        rejection_reasons.append(('warning', rapid_message))
                    else:
                        rejection_reasons.append(('error', rapid_message))
            
            # 2. Check account age (but don't return - let fraud detection run) - unless user has bypass
            if not bypass_account_age:
                account_age_days = (timezone.now() - request.user.date_joined).days
                account_age_blocked = False
                
                if bid_amount > settings.HIGH_VALUE_BID_THRESHOLD:
                    if account_age_days < settings.MIN_ACCOUNT_AGE_FOR_HIGH_BIDS:
                        account_age_blocked = True
                        should_reject_bid = True
                        days_remaining = settings.MIN_ACCOUNT_AGE_FOR_HIGH_BIDS - account_age_days
                        rejection_reasons.append((
                            'error',
                            f"New accounts must be at least {settings.MIN_ACCOUNT_AGE_FOR_HIGH_BIDS} days old to place bids above UGX {settings.HIGH_VALUE_BID_THRESHOLD:,}. "
                            f"Your account is {account_age_days} day(s) old. Please wait {days_remaining} more day(s) or bid a lower amount."
                        ))
            
            # 3. ALWAYS save bid temporarily to run fraud detection (even if will be deleted)
            bid.save()
            
            # 4. Run fraud detection REGARDLESS of other failures
            fraud_alerts = []
            fraud_blocked = False
            try:
                from .fraud_detection import FraudDetectionService
                fraud_service = FraudDetectionService()
                fraud_alerts = fraud_service.analyze_bid(bid)
                
                if fraud_alerts:
                    # Fraud alerts are SAVED to database regardless of bid outcome
                    critical_alerts = [alert for alert in fraud_alerts if alert.severity == 'critical']
                    
                    # Build detailed fraud message for user
                    fraud_types = set(alert.alert_type for alert in fraud_alerts)
                    fraud_details = []
                    if 'rapid_bidding' in fraud_types:
                        fraud_details.append("rapid bidding pattern")
                    if 'unusual_bid_amount' in fraud_types:
                        fraud_details.append("unusual bid amount (3x+ average)")
                    if 'bid_sniping' in fraud_types:
                        fraud_details.append("suspicious bid timing")
                    if 'shill_bidding' in fraud_types:
                        fraud_details.append("possible shill bidding")
                    if 'new_account_high_value' in fraud_types:
                        fraud_details.append("new account high-value bid")
                    
                    fraud_msg = f"⚠️ FRAUD ALERT: Detected {', '.join(fraud_details)}. "
                    
                    # Check if user has fraud detection bypass
                    if not bypass_fraud:
                        if critical_alerts:
                            fraud_blocked = True
                            should_reject_bid = True
                            rejection_reasons.append(('error', fraud_msg + "Your bid has been blocked. Contact support if you believe this is an error."))
                        else:
                            # Non-critical alerts - warn but allow bid
                            rejection_reasons.append(('warning', fraud_msg + "Your bid is under review. Our security team will verify this activity."))
                    else:
                        # User has bypass - just warn but don't block
                        rejection_reasons.append(('warning', fraud_msg + "Logged for review (you have fraud detection bypass)."))
            except Exception as e:
                import logging
                logging.error(f"Fraud detection failed: {str(e)}")
            
            # 5. If ANY check failed, delete bid and show ALL messages
            if should_reject_bid:
                bid.delete()
                for msg_type, msg_text in rejection_reasons:
                    if msg_type == 'error':
                        messages.error(request, msg_text)
                    else:
                        messages.warning(request, msg_text)
                return redirect('item_detail', pk=pk)
            
            # 6. Bid is valid - update auction state
            Bid.objects.filter(item=item).update(is_winning=False)
            
            highest_bid = item.bids.order_by('-amount').first()
            if highest_bid:
                highest_bid.is_winning = True
                highest_bid.save(update_fields=['is_winning'])
                item.current_price = highest_bid.amount
            
            item.bid_count += 1
            item.save(update_fields=['current_price', 'bid_count'])
            
            # Show success and any warnings
            messages.success(request, f'Your bid of UGX {bid.amount:,.0f} has been placed successfully!')
            for msg_type, msg_text in rejection_reasons:
                if msg_type == 'warning':
                    messages.warning(request, msg_text)
        else:
            for error in form.errors.values():
                messages.error(request, error[0])
    
    return redirect('item_detail', pk=pk)

@login_required
def verify_captcha(request, pk):
    """Verify CAPTCHA and allow pending bid to proceed"""
    from captcha.models import CaptchaStore
    from captcha.helpers import captcha_image_url
    from datetime import datetime, timedelta
    from decimal import Decimal, InvalidOperation
    from .rapid_bidding import RapidBiddingDetector
    
    item = get_object_or_404(Item, pk=pk)
    
    if request.method == 'POST':
        # Verify CAPTCHA answer
        captcha_key = request.POST.get('captcha_0')
        captcha_value = request.POST.get('captcha_1')
        
        if captcha_key and captcha_value:
            try:
                captcha = CaptchaStore.objects.get(hashkey=captcha_key)
                if captcha.response == captcha_value.lower():
                    # CAPTCHA passed - retrieve pending bid from session
                    session_key = f'pending_bid_{item.id}'
                    pending_bid = request.session.get(session_key)
                    
                    if pending_bid:
                        # Validate timestamp (max 5 minutes old)
                        bid_timestamp = datetime.fromisoformat(pending_bid['timestamp'])
                        now = timezone.now()
                        age = (now - bid_timestamp).total_seconds()
                        
                        if age > 300:  # 5 minutes
                            messages.error(request, "Verification expired. Please try bidding again.")
                            # Clean up session
                            del request.session[session_key]
                            del request.session[f'show_captcha_{item.id}']
                            return redirect('item_detail', pk=pk)
                        
                        try:
                            bid_amount = Decimal(str(pending_bid['amount']))
                            
                            # Revalidate bid against current auction state
                            min_bid_required = item.current_price + item.min_increment
                            if bid_amount < min_bid_required:
                                messages.error(
                                    request,
                                    f"Another bidder raised the price while you were verifying. "
                                    f"Minimum bid is now UGX {min_bid_required:,.0f}. Please bid again."
                                )
                                # Clean up session
                                del request.session[session_key]
                                del request.session[f'show_captcha_{item.id}']
                                # Delete the used CAPTCHA
                                captcha.delete()
                                return redirect('item_detail', pk=pk)
                            
                            # Check auction is still active
                            if item.status != 'active':
                                messages.error(request, "This auction is no longer active.")
                                # Clean up
                                del request.session[session_key]
                                del request.session[f'show_captcha_{item.id}']
                                captcha.delete()
                                return redirect('item_detail', pk=pk)
                            
                            if item.end_time <= timezone.now():
                                messages.error(request, "This auction has ended.")
                                # Clean up
                                del request.session[session_key]
                                del request.session[f'show_captcha_{item.id}']
                                captcha.delete()
                                return redirect('item_detail', pk=pk)
                            
                            # Create the bid (but don't mark CAPTCHA passed yet - fraud detection must pass first)
                            bid = Bid(
                                item=item,
                                bidder=request.user,
                                amount=bid_amount
                            )
                            bid.save()
                            
                            # Delete the used CAPTCHA to prevent reuse
                            captcha.delete()
                            
                            # Run fraud detection (mirror place_bid logic)
                            fraud_passed = True
                            try:
                                from .fraud_detection import FraudDetectionService
                                fraud_service = FraudDetectionService()
                                fraud_alerts = fraud_service.analyze_bid(bid)
                                
                                if fraud_alerts:
                                    critical_alerts = [alert for alert in fraud_alerts if alert.severity == 'critical']
                                    if critical_alerts:
                                        bid.delete()
                                        fraud_passed = False
                                        # Clean up session
                                        del request.session[session_key]
                                        del request.session[f'show_captcha_{item.id}']
                                        messages.error(request, "Your bid has been flagged by our fraud detection system. Please contact support if you believe this is an error.")
                                        return redirect('item_detail', pk=pk)
                                    else:
                                        messages.warning(request, "Your bid has been placed but flagged for review. Our team will verify the activity.")
                            except Exception as e:
                                import logging
                                logging.error(f"Fraud detection failed in verify_captcha: {str(e)}")
                                pass
                            
                            # Only mark CAPTCHA as passed if bid wasn't deleted by fraud detection
                            if fraud_passed:
                                RapidBiddingDetector.pass_captcha_challenge(request.user, item)
                            
                            # Update auction state
                            Bid.objects.filter(item=item).update(is_winning=False)
                            highest_bid = item.bids.order_by('-amount').first()
                            if highest_bid:
                                highest_bid.is_winning = True
                                highest_bid.save(update_fields=['is_winning'])
                                item.current_price = highest_bid.amount
                            
                            item.bid_count += 1
                            item.save(update_fields=['current_price', 'bid_count'])
                            
                            # Clean up session
                            del request.session[session_key]
                            del request.session[f'show_captcha_{item.id}']
                            
                            messages.success(request, f'Verification successful! Your bid of UGX {bid_amount:,.0f} has been placed.')
                            return redirect('item_detail', pk=pk)
                            
                        except (InvalidOperation, ValueError):
                            messages.error(request, "Invalid bid amount.")
                            # Clean up
                            if session_key in request.session:
                                del request.session[session_key]
                            if f'show_captcha_{item.id}' in request.session:
                                del request.session[f'show_captcha_{item.id}']
                            captcha.delete()
                    else:
                        messages.error(request, "No pending bid found. Please try bidding again.")
                        # Clean up session flag
                        if f'show_captcha_{item.id}' in request.session:
                            del request.session[f'show_captcha_{item.id}']
                else:
                    # CAPTCHA failed
                    RapidBiddingDetector.fail_captcha_challenge(request.user, item)
                    captcha.delete()  # Clean up failed attempt
                    messages.error(request, "Incorrect answer. Please try again.")
                    return redirect('item_detail', pk=pk)
            except CaptchaStore.DoesNotExist:
                messages.error(request, "Invalid or expired verification code.")
                # Clean up session if CAPTCHA is invalid
                session_key = f'pending_bid_{item.id}'
                if session_key in request.session:
                    del request.session[session_key]
                if f'show_captcha_{item.id}' in request.session:
                    del request.session[f'show_captcha_{item.id}']
        else:
            messages.error(request, "Please complete the verification.")
    
    return redirect('item_detail', pk=pk)

@login_required
def buy_now(request, pk):
    """Handle immediate purchase via Buy Now"""
    from django.db import transaction, connection
    from decimal import Decimal
    from users.models import Wallet, WalletTransaction
    from django.http import Http404
    
    # First, validate the item exists and basic checks
    try:
        item = Item.objects.get(pk=pk)
    except Item.DoesNotExist:
        raise Http404("Item not found")
    
    # Check basic prerequisites before transaction
    if item.status != 'active':
        messages.error(request, "This auction is no longer active.")
        return redirect('item_detail', pk=pk)
    
    if item.end_time <= timezone.now():
        messages.error(request, "This auction has ended.")
        return redirect('item_detail', pk=pk)
    
    if not item.buy_now_price:
        messages.error(request, "This item doesn't have a Buy Now price.")
        return redirect('item_detail', pk=pk)
    
    if item.seller == request.user:
        messages.error(request, "You cannot buy your own item!")
        return redirect('item_detail', pk=pk)
    
    if item.bids.exists():
        messages.error(request, "Buy Now is no longer available. Bidding has started.")
        return redirect('item_detail', pk=pk)
    
    # Check wallet balance
    try:
        wallet = request.user.wallet
        if wallet.balance < item.buy_now_price:
            messages.error(request, f'Insufficient wallet balance. You need UGX {item.buy_now_price:,.0f} but have UGX {wallet.balance:,.0f}. Please deposit funds.')
            return redirect('wallet_dashboard')
    except:
        messages.error(request, 'You need to have a wallet to use Buy Now. Please contact support.')
        return redirect('item_detail', pk=pk)
    
    # Calculate amounts
    platform_tax_rate = Decimal('0.05')
    platform_tax = item.buy_now_price * platform_tax_rate
    total_amount = item.buy_now_price
    seller_receives = total_amount - platform_tax
    
    # Atomic purchase transaction - works on all databases
    with transaction.atomic():
        # Attempt atomic conditional update - only succeeds if item hasn't been sold yet
        updated_count = Item.objects.filter(
            pk=pk,
            status='active',
            winner__isnull=True
        ).update(
            status='sold',
            winner=request.user
        )
        
        # If update didn't affect any rows, someone else bought it first
        if updated_count == 0:
            messages.error(request, "Someone else just purchased this item!")
            return redirect('item_detail', pk=pk)
        
        # Purchase successful - process wallet transactions
        wallet.balance -= total_amount
        wallet.save()
        
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='purchase',
            amount=-total_amount,
            description=f'Buy Now purchase: {item.title}',
            reference=f'BUYNOW-{pk}-{timezone.now().timestamp()}'
        )
        
        seller_wallet, _ = Wallet.objects.get_or_create(user=item.seller)
        seller_wallet.balance += seller_receives
        seller_wallet.save()
        
        WalletTransaction.objects.create(
            wallet=seller_wallet,
            transaction_type='sale',
            amount=seller_receives,
            description=f'Sale: {item.title} (Buy Now, 5% platform fee deducted)',
            reference=f'BUYNOW-SALE-{pk}-{timezone.now().timestamp()}'
        )
        
        WalletTransaction.objects.create(
            wallet=seller_wallet,
            transaction_type='platform_tax',
            amount=-platform_tax,
            description=f'Platform tax (5%) for {item.title}',
            reference=f'TAX-{pk}-{timezone.now().timestamp()}'
        )
        
        # Create transaction log
        TransactionLog.objects.create(
            transaction_id=f'BUYNOW-{item.pk}-{request.user.pk}-{timezone.now().timestamp()}',
            transaction_type='buy_now_purchase',
            item=item,
            user=request.user,
            amount=total_amount,
            payment_method='wallet',
            payment_reference=f'BUYNOW-{item.pk}',
            data={
                'buyer': request.user.username,
                'seller': item.seller.username,
                'buy_now_price': str(total_amount),
                'platform_tax': str(platform_tax),
                'seller_receives': str(seller_receives),
                'timestamp': timezone.now().isoformat()
            }
        )
        
        messages.success(request, f'Congratulations! You successfully purchased "{item.title}" for UGX {total_amount:,.0f} using Buy Now!')
        messages.info(request, f'Platform fee (5%): UGX {platform_tax:,.0f}. Seller receives: UGX {seller_receives:,.0f}')
        
    return redirect('item_detail', pk=pk)

@login_required
def sell_item(request):
    from .forms import SellItemForm
    from django.contrib import messages
    from datetime import timedelta
    
    profile = request.user.profile
    if not profile.is_seller or profile.seller_status != 'approved':
        if profile.seller_status == 'pending':
            messages.warning(request, 'Your seller application is under review. Please wait for approval.')
            return redirect('seller_application_status')
        elif profile.seller_status == 'rejected':
            messages.error(request, f'Your seller application was rejected. Reason: {profile.rejection_reason}')
            return redirect('seller_application')
        else:
            messages.info(request, 'You need to become a verified seller before you can list items.')
            return redirect('seller_application')
    
    if request.method == 'POST':
        form = SellItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.seller = request.user
            item.current_price = item.starting_price
            
            duration_minutes = form.cleaned_data.get('duration_minutes', 600)
            item.end_time = timezone.now() + timedelta(minutes=duration_minutes)
            
            item.status = 'active'
            item.save()
            
            messages.success(request, f'Your item "{item.title}" is now live!')
            return redirect('home')
    else:
        form = SellItemForm()
    
    context = {
        'form': form,
    }
    return render(request, 'auctions/sell_item.html', context)

@login_required
def submit_review(request, pk):
    item = get_object_or_404(Item, pk=pk)
    
    if item.seller == request.user:
        messages.error(request, "You cannot review your own item!")
        return redirect('item_detail', pk=pk)
    
    has_bid = Bid.objects.filter(item=item, bidder=request.user).exists()
    if not has_bid:
        messages.error(request, "Only buyers who have placed bids can leave reviews.")
        return redirect('item_detail', pk=pk)
    
    if Review.objects.filter(item=item, reviewer=request.user).exists():
        messages.error(request, "You have already reviewed this seller for this item.")
        return redirect('item_detail', pk=pk)
    
    if request.method == 'POST':
        form = ReviewForm(request.POST, request.FILES)
        if form.is_valid():
            review = form.save(commit=False)
            review.item = item
            review.reviewer = request.user
            review.seller = item.seller
            review.save()
            
            if hasattr(item.seller, 'profile'):
                profile = item.seller.profile
                profile.rating_sum += int(review.rating)
                profile.rating_count += 1
                profile.save(update_fields=['rating_sum', 'rating_count'])
            
            messages.success(request, 'Thank you for your review!')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    
    return redirect('item_detail', pk=pk)

def seller_profile(request, username):
    from users.models import Follow
    
    seller = get_object_or_404(User, username=username)
    
    # Privacy enforcement: only show public items unless viewing own profile
    if request.user.is_authenticated and request.user == seller:
        # Owner can see all their items
        items = Item.objects.filter(seller=seller).order_by('-created_at')
        active_items = items.exclude(status='sold')
    else:
        # Public view: only show active items
        items = Item.objects.filter(seller=seller, status__in=['active', 'sold']).order_by('-created_at')
        active_items = items.filter(status='active')
    
    sold_items = items.filter(status='sold')
    
    reviews = Review.objects.filter(seller=seller).select_related('reviewer', 'item').order_by('-created_at')[:10]
    
    seller_rating = 0
    seller_review_count = 0
    if hasattr(seller, 'profile'):
        seller_rating = seller.profile.average_rating()
        seller_review_count = seller.profile.rating_count
    
    followers_count = seller.followers.count()
    following_count = seller.following.count()
    
    is_following = False
    if request.user.is_authenticated:
        is_following = Follow.objects.filter(follower=request.user, following=seller).exists()
    
    context = {
        'seller': seller,
        'active_items': active_items,
        'sold_items': sold_items,
        'reviews': reviews,
        'seller_rating': seller_rating,
        'seller_review_count': seller_review_count,
        'total_items': items.count(),
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
    }
    return render(request, 'auctions/seller_profile.html', context)

@login_required
def view_cart(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related('item__seller').all()
    total = cart.total()
    
    context = {
        'cart': cart,
        'cart_items': cart_items,
        'total': total,
    }
    return render(request, 'auctions/cart.html', context)

@login_required
def add_to_cart(request, pk):
    item = get_object_or_404(Item, pk=pk)
    
    if item.winner != request.user:
        messages.error(request, "You can only add items you have won to your cart.")
        return redirect('item_detail', pk=pk)
    
    if item.status != 'sold':
        messages.error(request, "This item is not available for purchase yet.")
        return redirect('item_detail', pk=pk)
    
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    cart_item, item_created = CartItem.objects.get_or_create(cart=cart, item=item)
    
    if item_created:
        messages.success(request, f'"{item.title}" has been added to your cart!')
    else:
        messages.info(request, f'"{item.title}" is already in your cart.')
    
    return redirect('view_cart')

@login_required
def remove_from_cart(request, pk):
    cart_item = get_object_or_404(CartItem, pk=pk, cart__user=request.user)
    item_title = cart_item.item.title
    cart_item.delete()
    messages.success(request, f'"{item_title}" has been removed from your cart.')
    return redirect('view_cart')

@login_required
def checkout(request):
    from .models import Country, ShippingLocation, ShippingCost
    from payments.services import PaymentService, settle_payment_to_sellers
    from django.db import transaction as db_transaction
    from decimal import Decimal
    
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related('item__seller').all()
    
    if not cart_items:
        messages.warning(request, "Your cart is empty.")
        return redirect('view_cart')
    
    subtotal = cart.total()
    TAX_RATE = Decimal('0.05')
    
    shipping_cost = Decimal('0')
    
    cities = ShippingLocation.objects.values_list('city', flat=True).distinct().order_by('city')
    countries = Country.objects.filter(is_active=True)
    
    if request.method == 'POST':
        country_code = request.POST.get('country')
        payment_method = request.POST.get('payment_method')
        phone_number = request.POST.get('phone_number', '')
        delivery_city = request.POST.get('delivery_city', '')
        delivery_area = request.POST.get('delivery_area', '')
        pickup_option = request.POST.get('pickup_option', '') == '1'
        
        if not pickup_option:
            if not delivery_city or not delivery_area:
                messages.error(request, "Please select your delivery city and area, or choose pickup option.")
                return redirect('checkout')
            
            for cart_item in cart_items:
                item = cart_item.item
                if item.free_shipping:
                    continue
                elif item.seller_city and delivery_city:
                    item_shipping = item.calculate_shipping_cost(delivery_city, delivery_area)
                    shipping_cost += Decimal(str(item_shipping))
        
        tax_amount = (subtotal + shipping_cost) * TAX_RATE
        total = subtotal + shipping_cost + tax_amount
        
        try:
            country = Country.objects.get(code=country_code)
        except Country.DoesNotExist:
            messages.error(request, "Invalid country selected.")
            return redirect('checkout')
        
        if payment_method in ['mtn', 'airtel'] and not phone_number:
            messages.error(request, "Please provide your mobile money number.")
            return redirect('checkout')
        
        from payments.models import Payment
        import uuid
        
        payment_id = str(uuid.uuid4())
        
        payment_service = PaymentService.get_service(payment_method, country_code)
        payment_data = {
            'phone_number': phone_number,
            'network': payment_method.upper(),
            'email': request.user.email,
            'fullname': request.user.get_full_name() or request.user.username,
            'description': f'Auction purchase - {len(cart_items)} items',
            'user_id': str(request.user.id),
            'metadata': {'cart_items': [item.item.id for item in cart_items]},
            'success_url': request.build_absolute_uri('/'),
            'cancel_url': request.build_absolute_uri('/cart/'),
            'redirect_url': request.build_absolute_uri('/')
        }
        
        result = payment_service.process_payment(float(total), country.currency, payment_data)
        
        payment = Payment.objects.create(
            user=request.user,
            amount=total,
            platform_tax=tax_amount,
            payment_method=payment_method,
            phone_number=phone_number,
            status='pending' if result.get('success') else 'failed',
            payment_id=payment_id,
            metadata={
                'cart_items': [item.item.id for item in cart_items],
                'country': country_code,
                'subtotal': float(subtotal),
                'tax_rate': float(TAX_RATE),
                'tax_amount': float(tax_amount),
                'payment_result': {
                    'success': result.get('success'),
                    'message': result.get('message'),
                    'transaction_id': result.get('transaction_id') or result.get('payment_id') or result.get('session_id')
                }
            }
        )
        
        if result.get('success'):
            for cart_item in cart_items:
                item = cart_item.item
                TransactionLog.objects.create(
                    transaction_id=f"ORDER-{payment.payment_id}-{item.id}",
                    transaction_type='purchase',
                    item=item,
                    user=request.user,
                    amount=item.current_price,
                    payment_method=payment_method,
                    payment_reference=payment.payment_id,
                    data={
                        'seller': item.seller.username,
                        'payment_id': payment.payment_id,
                        'phone_number': phone_number,
                        'country': country_code,
                        'currency': country.currency
                    }
                )
            
            if payment_method in ['mtn', 'airtel']:
                payment.metadata['base_amount'] = str(subtotal)
                payment.metadata['shipping_cost'] = str(shipping_cost)
                payment.metadata['platform_tax'] = str(tax_amount)
                payment.metadata['total'] = str(total)
                payment.metadata['phone_number'] = phone_number
                payment.metadata['delivery_city'] = delivery_city
                payment.metadata['delivery_area'] = delivery_area
                payment.metadata['pickup_option'] = pickup_option
                payment.save()
                return redirect(f'/ussd/wallet/deposit/{payment.payment_id}/')
            elif payment_method == 'card':
                payment.metadata['base_amount'] = str(subtotal)
                payment.metadata['shipping_cost'] = str(shipping_cost)
                payment.metadata['platform_tax'] = str(tax_amount)
                payment.metadata['total'] = str(total)
                payment.metadata['delivery_city'] = delivery_city
                payment.metadata['delivery_area'] = delivery_area
                payment.metadata['pickup_option'] = pickup_option
                payment.save()
                return redirect(f'/payment/card/{payment.payment_id}/?context=checkout')
            elif payment_method == 'paypal':
                payment.metadata['base_amount'] = str(subtotal)
                payment.metadata['shipping_cost'] = str(shipping_cost)
                payment.metadata['platform_tax'] = str(tax_amount)
                payment.metadata['total'] = str(total)
                payment.metadata['delivery_city'] = delivery_city
                payment.metadata['delivery_area'] = delivery_area
                payment.metadata['pickup_option'] = pickup_option
                payment.save()
                return redirect(f'/payment/paypal/{payment.payment_id}/?context=checkout')
            else:
                with db_transaction.atomic():
                    payment.status = 'completed'
                    payment.save()
                    settle_payment_to_sellers(payment, list(cart_items))
                    cart.items.all().delete()
                messages.success(request, f'Order placed! {result.get("message", "")}')
                return redirect('home')
        else:
            messages.error(request, f'Payment failed: {result.get("message", "Unknown error")}')
            return redirect('checkout')
    
    tax_amount = (subtotal + shipping_cost) * TAX_RATE
    total = subtotal + shipping_cost + tax_amount
    
    context = {
        'cart': cart,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'shipping_cost': shipping_cost,
        'tax_amount': tax_amount,
        'tax_rate': float(TAX_RATE * 100),
        'total': total,
        'countries': countries,
        'cities': cities,
    }
    return render(request, 'auctions/checkout.html', context)

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import json

def get_chatbot_response(user_message):
    """Rule-based chatbot - no API costs!"""
    import re
    
    msg = user_message.lower().strip()
    
    # Casual greetings
    if re.search(r'\b(yo|yoo)\b', msg):
        return "Hey! What's good? How can I help you with AuctionHub today?"
    
    if re.search(r'\b(what\'?s up|sup|wassup|whats up)\b', msg):
        return "Not much, just here to help! What brings you to AuctionHub today?"
    
    if re.search(r'\b(how (are )?you doin|how are you|how you doing)\b', msg):
        return "I'm doing great, thanks for asking! How can I assist you today?"
    
    if re.search(r'^(hey|hi|hello|hola|good morning|good afternoon|good evening)\b', msg):
        return "Hi there! 👋 I'm here to help with bidding, payments, or selling. What can I do for you?"
    
    # Thanks/appreciation - request rating
    if re.search(r'\b(thanks|thank you|thx|appreciate|helpful|helped)\b', msg):
        return "You're welcome! 😊 If you found this helpful, I'd love your feedback! Could you rate this interaction? ⭐⭐⭐⭐⭐ (1-5 stars). Your feedback helps me improve!\n\nIs there anything else I can help you with today?"
    
    # Rating responses
    if re.search(r'\b[1-5]\s*(stars?|\/5)?\b', msg):
        return "Thank you so much for the rating! Your feedback helps me serve you better. 😊 Have a great day!"
    
    # Platform features - bidding
    if re.search(r'\b(how|place|make|bid|bidding)\b', msg) and re.search(r'\b(bid|bidding|auction)\b', msg):
        return "To place a bid:\n1. Find an item you like\n2. Click the 'Bid' button\n3. Enter your amount (must be higher than current bid)\n4. Confirm!\n\nYou'll get real-time updates if someone outbids you. Is there anything else you'd like to know?"
    
    # Payment methods
    if re.search(r'\b(payment|pay|accepted|methods?)\b', msg):
        return "We accept:\n• MTN Mobile Money\n• Airtel Money\n• Visa/Mastercard (via Stripe)\n• PayPal\n\nAll payments use bank-grade encryption and fraud detection. A 5% platform fee applies. Need help with a specific payment method?"
    
    # Mobile money
    if re.search(r'\b(mobile money|mtn|airtel|momo)\b', msg):
        return "Mobile money is easy! Select MTN or Airtel, enter your phone number, and approve the USSD prompt on your phone. Payment is instant and secure! 💰\n\nNeed help with something else?"
    
    # USSD/offline bidding
    if re.search(r'\b(ussd|offline|no internet|without internet|\*354|\*789)\b', msg):
        return "Yes! You can bid without internet:\n• MTN: Dial *354#\n• Airtel: Dial *789#\n\nFollow the prompts to browse items and place bids. Perfect for areas with poor internet! ⚡"
    
    # Wallet
    if re.search(r'\b(wallet|deposit|withdraw|balance)\b', msg):
        return "Our digital wallet lets you:\n• Deposit via mobile money, card, or PayPal\n• Withdraw to mobile money (1-5 min processing)\n• Minimum withdrawal: UGX 1,000\n\nManage your funds easily! Need specific wallet help?"
    
    # Seller trust/safety
    if re.search(r'\b(trust|safe|seller|scam|fraud|reliable)\b', msg):
        return "Safety is our priority! ✅\n• Check seller ratings & reviews\n• AI fraud detection (91% accuracy)\n• Verified sellers approved by admins\n• Blockchain-inspired transaction logs\n\nWe've got your back!"
    
    # Selling items
    if re.search(r'\b(sell|selling|list item|become seller)\b', msg):
        return "To sell items:\n1. Click 'Sell an Item' (verified sellers only)\n2. Upload photos\n3. Set starting price & auction duration\n4. Items go live instantly!\n\nNeed to become a verified seller? Apply through your profile!"
    
    # Security/payment security
    if re.search(r'\b(secure|security|safe|encrypted)\b', msg):
        return "Your security is guaranteed! 🔒\n• Bank-grade encryption\n• HMAC signature verification\n• AI fraud detection (91% accuracy)\n• Daily payment reconciliation\n• WCAG AA accessibility\n\nYour financial data is protected!"
    
    # What's new/updates
    if re.search(r'\b(new|update|2025|recent|latest|improved)\b', msg):
        return "2025 Platform Upgrades:\n✅ Payment webhook security (HMAC)\n✅ Enhanced fraud detection (91% F1-score)\n✅ Automated reconciliation\n✅ Full CI/CD pipeline\n✅ Accessibility improvements\n\nWe're constantly improving!"
    
    # Winning auction
    if re.search(r'\b(win|won|winner|winning)\b', msg):
        return "When you win an auction:\n1. You'll get a notification\n2. Proceed to checkout\n3. Complete payment\n4. Receive seller contact info for delivery\n\nCongratulations on your win! 🎉"
    
    # Account/refund/dispute - escalate
    if re.search(r'\b(account|refund|dispute|problem|issue|error|bug|broken)\b', msg):
        return "I've reached the limit of what I can help with. For account-specific issues, refunds, or technical problems, please contact our support team:\n\n📧 support@auctionhub.com\n📞 +256-XXX-XXXXXX\n\nThey'll help you right away!"
    
    # Legal/policy - escalate
    if re.search(r'\b(legal|policy|terms|conditions|privacy)\b', msg):
        return "For legal matters and policies, please reach out to our management team at:\n\n📧 info@auctionhub.com\n\nThey'll provide you with the official information you need."
    
    # Default - general help
    return "I'm here to help with AuctionHub! I can answer questions about:\n\n• Placing bids & winning auctions\n• Payment methods (mobile money, cards, PayPal)\n• USSD bidding (*354# MTN, *789# Airtel)\n• Digital wallet deposits/withdrawals\n• Seller trust & safety\n• Platform security features\n\nWhat would you like to know? 😊"

@csrf_exempt
@require_POST
def chatbot(request):
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '')
        
        if not user_message:
            return JsonResponse({'error': 'No message provided'}, status=400)
        
        bot_reply = get_chatbot_response(user_message)
        
        return JsonResponse({
            'reply': bot_reply,
            'success': True
        })
        
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'reply': "I'm having trouble right now. Please try again in a moment! 😊",
            'success': False
        }, status=500)

@login_required
def inbox(request):
    """Show all conversations for the logged-in user"""
    from .models import Message
    conversations = Message.get_conversations_for_user(request.user)
    
    # Get unread count
    unread_total = Message.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()
    
    context = {
        'conversations': conversations,
        'unread_total': unread_total,
    }
    return render(request, 'auctions/inbox.html', context)

@login_required
def conversation(request, user_id):
    """View conversation with a specific user"""
    from .models import Message
    
    try:
        other_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('inbox')
    
    # Get all messages between these two users
    conversation_messages = Message.get_conversation(request.user, other_user)
    
    # Mark messages from other user as read
    Message.objects.filter(
        sender=other_user,
        recipient=request.user,
        is_read=False
    ).update(is_read=True)
    
    # Get item context if there is one
    item = None
    if conversation_messages.exists():
        first_msg_with_item = conversation_messages.filter(item__isnull=False).first()
        if first_msg_with_item:
            item = first_msg_with_item.item
    
    # Get purchase history with this seller (for sidebar)
    active_orders = Item.objects.filter(
        seller=other_user,
        status='active'
    ).filter(
        bids__bidder=request.user
    ).distinct().order_by('-created_at')[:5]
    
    completed_orders = Item.objects.filter(
        seller=other_user,
        status='sold',
        winner=request.user
    ).order_by('-updated_at')[:10]
    
    total_spent = sum(order.current_price for order in completed_orders)
    
    context = {
        'other_user': other_user,
        'chat_messages': conversation_messages,
        'item': item,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'total_spent': total_spent,
        'order_count': completed_orders.count(),
    }
    return render(request, 'auctions/conversation.html', context)

@login_required
@require_POST
def send_message(request):
    """AJAX endpoint to send a message"""
    from .models import Message
    
    try:
        recipient_id = request.POST.get('recipient_id')
        content = request.POST.get('content', '').strip()
        item_id = request.POST.get('item_id')
        image = request.FILES.get('image')
        
        if not recipient_id:
            return JsonResponse({'success': False, 'error': 'Recipient not specified'})
        
        if not content and not image:
            return JsonResponse({'success': False, 'error': 'Message cannot be empty'})
        
        try:
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Recipient not found'})
        
        if recipient == request.user:
            return JsonResponse({'success': False, 'error': 'Cannot send message to yourself'})
        
        # Get item if specified
        item = None
        if item_id:
            try:
                item = Item.objects.get(id=item_id)
            except Item.DoesNotExist:
                pass
        
        # Create message
        message = Message.objects.create(
            sender=request.user,
            recipient=recipient,
            content=content or '',
            item=item,
            image=image
        )
        
        return JsonResponse({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'image_url': message.image.url if message.image else None,
                'created_at': message.created_at.strftime('%b %d, %Y %I:%M %p'),
                'sender': request.user.username
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def start_conversation(request, user_id):
    """Start or continue a conversation with a user"""
    try:
        other_user = User.objects.get(id=user_id)
        if other_user == request.user:
            messages.error(request, "You cannot message yourself.")
            return redirect('home')
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('home')
    
    return redirect('conversation', user_id=user_id)

@login_required
def change_item_status(request, item_id):
    """Change the status of an item (private, off_sale, sold, active)"""
    from django.http import JsonResponse
    from django.views.decorators.http import require_POST
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)
    
    try:
        item = Item.objects.get(id=item_id, seller=request.user)
        new_status = request.POST.get('status')
        
        valid_statuses = ['active', 'private', 'off_sale', 'sold']
        if new_status not in valid_statuses:
            return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
        
        item.status = new_status
        item.save(update_fields=['status'])
        
        return JsonResponse({
            'success': True,
            'message': f'Item status changed to {new_status}',
            'new_status': new_status
        })
        
    except Item.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found or you do not have permission'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# Admin Dashboard Views
from functools import wraps
from django.http import HttpResponseForbidden
from django.db.models import Sum, Count, Avg
from datetime import timedelta
from payments.models import Payment

def admin_required(view_func):
    """Decorator to restrict view access to superusers only"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please login to access the admin dashboard.")
            return redirect('login')
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to access the admin dashboard.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper

@admin_required
def admin_dashboard(request):
    """Admin dashboard overview with key analytics"""
    from .models import FraudAlert
    from users.models import UserProfile
    
    # Date range for analytics (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # User statistics
    total_users = User.objects.count()
    new_users_30d = User.objects.filter(date_joined__gte=thirty_days_ago).count()
    active_users = User.objects.filter(profile__last_seen__gte=timezone.now() - timedelta(minutes=5)).count()
    
    # Seller application statistics
    pending_sellers = UserProfile.objects.filter(seller_status='pending').count()
    
    # Item statistics
    total_items = Item.objects.count()
    active_items = Item.objects.filter(status='active').count()
    sold_items = Item.objects.filter(status='sold').count()
    new_items_30d = Item.objects.filter(created_at__gte=thirty_days_ago).count()
    
    # Payment statistics
    total_payments = Payment.objects.filter(status='completed').count()
    total_spent = Payment.objects.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
    platform_revenue = Payment.objects.filter(status='completed').aggregate(total=Sum('platform_tax'))['total'] or 0
    spent_30d = Payment.objects.filter(
        status='completed',
        completed_at__gte=thirty_days_ago
    ).aggregate(total=Sum('amount'))['total'] or 0
    revenue_30d = Payment.objects.filter(
        status='completed',
        completed_at__gte=thirty_days_ago
    ).aggregate(total=Sum('platform_tax'))['total'] or 0
    
    # Bid statistics
    total_bids = Bid.objects.count()
    avg_bid_amount = Bid.objects.aggregate(avg=Avg('amount'))['avg'] or 0
    
    # Fraud alerts
    unresolved_fraud_alerts = FraudAlert.objects.filter(is_resolved=False).count()
    high_severity_alerts = FraudAlert.objects.filter(severity='high', is_resolved=False).count()
    
    # Recent activity
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_items = Item.objects.order_by('-created_at')[:5]
    recent_payments = Payment.objects.filter(status='completed').order_by('-completed_at')[:5]
    
    context = {
        'total_users': total_users,
        'new_users_30d': new_users_30d,
        'active_users': active_users,
        'pending_sellers': pending_sellers,
        'total_items': total_items,
        'active_items': active_items,
        'sold_items': sold_items,
        'new_items_30d': new_items_30d,
        'total_payments': total_payments,
        'total_spent': total_spent,
        'spent_30d': spent_30d,
        'platform_revenue': platform_revenue,
        'revenue_30d': revenue_30d,
        'total_bids': total_bids,
        'avg_bid_amount': avg_bid_amount,
        'unresolved_fraud_alerts': unresolved_fraud_alerts,
        'high_severity_alerts': high_severity_alerts,
        'recent_users': recent_users,
        'recent_items': recent_items,
        'recent_payments': recent_payments,
    }
    return render(request, 'admin/dashboard.html', context)

@admin_required
def admin_users(request):
    """Admin user management"""
    from users.models import UserProfile
    from django.db.models import Q
    
    search_query = request.GET.get('q', '')
    users = User.objects.select_related('profile').all()
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(profile__phone_number__icontains=search_query)
        )
    
    users = users.order_by('-date_joined')
    
    context = {
        'users': users,
        'search_query': search_query,
        'total_count': users.count(),
    }
    return render(request, 'admin/users.html', context)

@admin_required
def admin_items(request):
    """Admin item management"""
    from django.db.models import Q
    
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', 'all')
    
    items = Item.objects.select_related('seller', 'category').all()
    
    if search_query:
        items = items.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query) |
            Q(seller__username__icontains=search_query)
        )
    
    if status_filter != 'all':
        items = items.filter(status=status_filter)
    
    items = items.order_by('-created_at')
    
    context = {
        'items': items,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_count': items.count(),
    }
    return render(request, 'admin/items.html', context)

@admin_required
def admin_payments(request):
    """Admin payment monitoring"""
    from django.db.models import Q
    
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', 'all')
    
    payments = Payment.objects.select_related('user', 'item').all()
    
    if search_query:
        payments = payments.filter(
            Q(payment_id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(transaction_reference__icontains=search_query)
        )
    
    if status_filter != 'all':
        payments = payments.filter(status=status_filter)
    
    payments = payments.order_by('-created_at')
    
    context = {
        'payments': payments,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_count': payments.count(),
    }
    return render(request, 'admin/payments.html', context)

@admin_required
def admin_fraud_alerts(request):
    """Admin fraud alert monitoring with analytics"""
    from .models import FraudAlert
    from django.db.models import Q, Count
    from django.utils import timezone
    from datetime import timedelta
    import json
    
    search_query = request.GET.get('q', '')
    severity_filter = request.GET.get('severity', 'all')
    resolved_filter = request.GET.get('resolved', 'unresolved')
    alert_type_filter = request.GET.get('alert_type', 'all')
    date_filter = request.GET.get('date_filter', '30')
    
    alerts = FraudAlert.objects.select_related('user', 'item', 'resolved_by').all()
    
    if search_query:
        alerts = alerts.filter(
            Q(user__username__icontains=search_query) |
            Q(alert_type__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if severity_filter != 'all':
        alerts = alerts.filter(severity=severity_filter)
    
    if resolved_filter == 'resolved':
        alerts = alerts.filter(is_resolved=True)
    elif resolved_filter == 'unresolved':
        alerts = alerts.filter(is_resolved=False)
    
    if alert_type_filter != 'all':
        alerts = alerts.filter(alert_type=alert_type_filter)
    
    if date_filter != 'all':
        days = int(date_filter)
        date_from = timezone.now() - timedelta(days=days)
        alerts = alerts.filter(created_at__gte=date_from)
    
    alerts = alerts.order_by('-created_at')
    
    total_alerts = FraudAlert.objects.count()
    critical_alerts = FraudAlert.objects.filter(severity='critical', is_resolved=False).count()
    high_alerts = FraudAlert.objects.filter(severity='high', is_resolved=False).count()
    resolved_alerts = FraudAlert.objects.filter(is_resolved=True).count()
    unresolved_alerts = FraudAlert.objects.filter(is_resolved=False).count()
    
    severity_stats = FraudAlert.objects.filter(is_resolved=False).values('severity').annotate(count=Count('id'))
    alert_type_stats = FraudAlert.objects.values('alert_type').annotate(count=Count('id')).order_by('-count')[:10]
    
    alert_types = FraudAlert.objects.values_list('alert_type', flat=True).distinct()
    
    today = timezone.now().date()
    last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily_alerts = []
    for day in last_7_days:
        count = FraudAlert.objects.filter(created_at__date=day).count()
        daily_alerts.append({'date': day.strftime('%b %d'), 'count': count})
    
    context = {
        'alerts': alerts,
        'search_query': search_query,
        'severity_filter': severity_filter,
        'resolved_filter': resolved_filter,
        'alert_type_filter': alert_type_filter,
        'date_filter': date_filter,
        'total_count': alerts.count(),
        'total_alerts': total_alerts,
        'critical_alerts': critical_alerts,
        'high_alerts': high_alerts,
        'resolved_alerts': resolved_alerts,
        'unresolved_alerts': unresolved_alerts,
        'severity_stats': list(severity_stats),
        'alert_type_stats': list(alert_type_stats),
        'alert_types': list(alert_types),
        'daily_alerts_json': json.dumps(daily_alerts),
    }
    return render(request, 'admin/fraud_alerts.html', context)

@admin_required
@require_POST
def admin_toggle_user_status(request, user_id):
    """Toggle user active status"""
    from django.http import JsonResponse
    try:
        target_user = User.objects.get(id=user_id)
        if target_user.is_superuser:
            return JsonResponse({'success': False, 'error': 'Cannot deactivate superusers'}, status=403)
        
        target_user.is_active = not target_user.is_active
        target_user.save()
        
        return JsonResponse({
            'success': True,
            'is_active': target_user.is_active,
            'message': f'User {target_user.username} is now {"active" if target_user.is_active else "inactive"}'
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@admin_required
@require_POST
def admin_update_bypass_permissions(request, user_id):
    """Update user bypass permissions"""
    from django.http import JsonResponse
    import json
    
    try:
        target_user = User.objects.get(id=user_id)
        if target_user.is_superuser:
            return JsonResponse({'success': False, 'error': 'Superusers already have auto-bypass'}, status=403)
        
        data = json.loads(request.body)
        profile = target_user.profile
        
        # Update bypass permissions
        profile.bypass_all_restrictions = data.get('bypass_all', False)
        profile.bypass_account_age_check = data.get('bypass_age', False)
        profile.bypass_rapid_bidding_check = data.get('bypass_rapid', False)
        profile.bypass_fraud_detection = data.get('bypass_fraud', False)
        profile.bypass_notes = data.get('bypass_notes', '')
        
        # Track who granted these permissions
        profile.bypass_granted_by = request.user
        profile.bypass_granted_at = timezone.now()
        
        profile.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Bypass permissions updated for {target_user.username}'
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@admin_required
@require_POST
def admin_change_item_status(request, item_id):
    """Change item status from admin panel"""
    from django.http import JsonResponse
    try:
        item = Item.objects.get(id=item_id)
        new_status = request.POST.get('status')
        
        valid_statuses = ['active', 'private', 'off_sale', 'sold', 'expired', 'cancelled']
        if new_status not in valid_statuses:
            return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
        
        item.status = new_status
        item.save(update_fields=['status'])
        
        return JsonResponse({
            'success': True,
            'message': f'Item status changed to {new_status}',
            'new_status': new_status
        })
    except Item.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@admin_required
def admin_export_payments(request):
    """Export payments to CSV"""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payments_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Payment ID', 'User', 'Amount', 'Method', 'Status', 'Created', 'Completed'])
    
    payments = Payment.objects.select_related('user').all().order_by('-created_at')
    for payment in payments:
        writer.writerow([
            str(payment.payment_id),
            payment.user.username,
            float(payment.amount),
            payment.payment_method,
            payment.status,
            payment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            payment.completed_at.strftime('%Y-%m-%d %H:%M:%S') if payment.completed_at else 'N/A'
        ])
    
    return response

@admin_required
def admin_export_fraud_alerts(request):
    """Export fraud alerts to CSV"""
    import csv
    from django.http import HttpResponse
    from .models import FraudAlert
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="fraud_alerts_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['User', 'Alert Type', 'Severity', 'Details', 'Resolved', 'Created', 'Resolved By', 'Resolved At'])
    
    alerts = FraudAlert.objects.select_related('user', 'resolved_by').all().order_by('-created_at')
    for alert in alerts:
        writer.writerow([
            alert.user.username,
            alert.alert_type,
            alert.severity,
            alert.description,
            'Yes' if alert.is_resolved else 'No',
            alert.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            alert.resolved_by.username if alert.resolved_by else 'N/A',
            alert.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if alert.resolved_at else 'N/A'
        ])
    
    return response

@admin_required
@require_POST
def admin_resolve_fraud_alert(request, alert_id):
    """Resolve a fraud alert"""
    from django.http import JsonResponse
    from .models import FraudAlert
    from django.utils import timezone
    
    try:
        alert = FraudAlert.objects.get(id=alert_id)
        
        if alert.is_resolved:
            return JsonResponse({'success': False, 'error': 'Alert is already resolved'}, status=400)
        
        alert.is_resolved = True
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Fraud alert #{alert_id} has been resolved',
            'resolved_by': request.user.username,
            'resolved_at': alert.resolved_at.strftime('%b %d, %Y %H:%M')
        })
    except FraudAlert.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Alert not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@admin_required
@require_POST
def admin_dismiss_fraud_alert(request, alert_id):
    """Dismiss (delete) a fraud alert"""
    from django.http import JsonResponse
    from .models import FraudAlert
    
    try:
        alert = FraudAlert.objects.get(id=alert_id)
        alert.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Fraud alert #{alert_id} has been dismissed'
        })
    except FraudAlert.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Alert not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@admin_required
@require_POST
def admin_bulk_resolve_alerts(request):
    """Bulk resolve fraud alerts"""
    from django.http import JsonResponse
    from .models import FraudAlert
    from django.utils import timezone
    import json
    
    try:
        data = json.loads(request.body)
        alert_ids = data.get('alert_ids', [])
        
        if not alert_ids:
            return JsonResponse({'success': False, 'error': 'No alert IDs provided'}, status=400)
        
        updated = FraudAlert.objects.filter(id__in=alert_ids, is_resolved=False).update(
            is_resolved=True,
            resolved_by=request.user,
            resolved_at=timezone.now()
        )
        
        return JsonResponse({
            'success': True,
            'message': f'{updated} alerts resolved successfully',
            'count': updated
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@admin_required
def admin_seller_applications(request):
    """Admin seller application management"""
    from users.models import UserProfile
    from django.db.models import Q
    
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '')
    
    applications = UserProfile.objects.select_related('user').exclude(seller_status='none')
    
    if status_filter != 'all':
        applications = applications.filter(seller_status=status_filter)
    
    if search_query:
        applications = applications.filter(
            Q(business_name__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )
    
    applications = applications.order_by('-seller_application_date')
    
    pending_count = UserProfile.objects.filter(seller_status='pending').count()
    approved_count = UserProfile.objects.filter(seller_status='approved').count()
    rejected_count = UserProfile.objects.filter(seller_status='rejected').count()
    
    context = {
        'applications': applications,
        'status_filter': status_filter,
        'search_query': search_query,
        'total_count': applications.count(),
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
    }
    return render(request, 'admin/seller_applications.html', context)

@admin_required
def admin_approve_seller(request, user_id):
    """Approve a seller application"""
    from users.models import UserProfile
    from django.utils import timezone
    
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        profile = user.profile
        
        profile.seller_status = 'approved'
        profile.is_seller = True
        profile.seller_approval_date = timezone.now()
        profile.rejection_reason = ''
        profile.save(update_fields=['seller_status', 'is_seller', 'seller_approval_date', 'rejection_reason'])
        
        messages.success(request, f'Seller application for {user.username} ({profile.business_name}) has been approved!')
        
    return redirect('admin_seller_applications')

@admin_required
def admin_reject_seller(request, user_id):
    """Reject a seller application"""
    from users.models import UserProfile
    
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        profile = user.profile
        
        rejection_reason = request.POST.get('rejection_reason', 'Application does not meet our requirements.')
        
        profile.seller_status = 'rejected'
        profile.is_seller = False
        profile.rejection_reason = rejection_reason
        profile.save(update_fields=['seller_status', 'is_seller', 'rejection_reason'])
        
        messages.success(request, f'Seller application for {user.username} has been rejected.')
        
    return redirect('admin_seller_applications')


def get_cities(request, country_code):
    """API endpoint to get cities for a selected country"""
    from .models import ShippingLocation
    
    cities = ShippingLocation.objects.filter(
        country=country_code.upper(), 
        is_active=True
    ).values_list('city', flat=True).distinct().order_by('city')
    
    return JsonResponse({'cities': list(cities)})

def get_areas(request, city):
    """API endpoint to get areas for a selected city"""
    from .models import ShippingLocation
    
    country_code = request.GET.get('country', 'UG')
    
    areas = ShippingLocation.objects.filter(
        country=country_code.upper(),
        city=city, 
        is_active=True
    ).values_list('area', flat=True).order_by('area')
    
    return JsonResponse({'areas': list(areas)})
