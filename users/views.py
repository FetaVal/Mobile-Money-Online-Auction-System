from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from .forms import UserRegisterForm, UserLoginForm, ProfileUpdateForm
from .models import Follow

def register_view(request):
    import secrets
    import hashlib
    from django.utils import timezone
    
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        captcha_token = request.POST.get('captcha_token', '')
        session_token = request.session.get('captcha_challenge', '')
        token_timestamp = request.session.get('captcha_timestamp', 0)
        
        is_valid_captcha = False
        if session_token and captcha_token:
            expected_response = hashlib.sha256(f"{session_token}:completed".encode()).hexdigest()
            time_diff = timezone.now().timestamp() - token_timestamp
            
            if captcha_token == expected_response and time_diff < 300:
                is_valid_captcha = True
        
        if not is_valid_captcha:
            messages.error(request, 'Please complete the verification slider correctly.')
            form = UserRegisterForm()
            context = {'form': form, 'captcha_challenge': secrets.token_urlsafe(32)}
            request.session['captcha_challenge'] = context['captcha_challenge']
            request.session['captcha_timestamp'] = timezone.now().timestamp()
            return render(request, 'users/register.html', context)
        
        del request.session['captcha_challenge']
        del request.session['captcha_timestamp']
        
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            if not hasattr(user, 'profile'):
                from .models import UserProfile
                UserProfile.objects.create(user=user)
            
            if form.cleaned_data.get('phone_number'):
                user.profile.phone_number = form.cleaned_data['phone_number']
            if form.cleaned_data.get('mobile_money_provider'):
                user.profile.mobile_money_provider = form.cleaned_data['mobile_money_provider']
            user.profile.save()
            
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created successfully for {username}! You can now log in.')
            return redirect('login')
        else:
            context = {'form': form, 'captcha_challenge': secrets.token_urlsafe(32)}
            request.session['captcha_challenge'] = context['captcha_challenge']
            request.session['captcha_timestamp'] = timezone.now().timestamp()
            return render(request, 'users/register.html', context)
    else:
        form = UserRegisterForm()
        captcha_challenge = secrets.token_urlsafe(32)
        request.session['captcha_challenge'] = captcha_challenge
        request.session['captcha_timestamp'] = timezone.now().timestamp()
        return render(request, 'users/register.html', {'form': form, 'captcha_challenge': captcha_challenge})

def login_view(request):
    import secrets
    import hashlib
    from django.utils import timezone
    from datetime import timedelta
    from .models import LoginAttempt, EmailOTP, TwoFactorAuth
    
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if LoginAttempt.is_locked_out(username):
            time_remaining = LoginAttempt.get_lockout_time_remaining(username)
            messages.error(request, f'Account temporarily locked due to too many failed login attempts. Please try again in {time_remaining} minutes.')
            context = {'captcha_challenge': secrets.token_urlsafe(32), 'locked_out': True, 'time_remaining': time_remaining}
            request.session['captcha_challenge'] = context['captcha_challenge']
            request.session['captcha_timestamp'] = timezone.now().timestamp()
            return render(request, 'users/login.html', context)
        
        captcha_token = request.POST.get('captcha_token', '')
        session_token = request.session.get('captcha_challenge', '')
        token_timestamp = request.session.get('captcha_timestamp', 0)
        
        is_valid_captcha = False
        if session_token and captcha_token:
            expected_response = hashlib.sha256(f"{session_token}:completed".encode()).hexdigest()
            time_diff = timezone.now().timestamp() - token_timestamp
            
            if captcha_token == expected_response and time_diff < 300:
                is_valid_captcha = True
        
        if not is_valid_captcha:
            messages.error(request, 'Please complete the verification slider correctly.')
            context = {'captcha_challenge': secrets.token_urlsafe(32)}
            request.session['captcha_challenge'] = context['captcha_challenge']
            request.session['captcha_timestamp'] = timezone.now().timestamp()
            return render(request, 'users/login.html', context)
        
        del request.session['captcha_challenge']
        del request.session['captcha_timestamp']
        
        def get_client_ip(request):
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            return ip
        
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        user = authenticate(username=username, password=password)
        
        if user is not None:
            LoginAttempt.objects.create(
                username=username,
                ip_address=ip_address,
                user_agent=user_agent,
                success=True
            )
            
            LoginAttempt.clear_attempts(username)
            
            try:
                two_factor = TwoFactorAuth.objects.get(user=user)
                if two_factor.enabled:
                    if two_factor.method == 'email':
                        otp = EmailOTP.generate_code(
                            user=user,
                            purpose='login',
                            validity_minutes=5,
                            ip_address=ip_address,
                            user_agent=user_agent
                        )
                        request.session['pending_2fa_otp_id'] = otp.id
                        messages.info(request, f'A verification code has been sent to {user.email}')
                    elif two_factor.method == 'totp':
                        messages.info(request, 'Please enter the code from your authenticator app')
                    
                    request.session['pending_2fa_user_id'] = user.id
                    request.session['2fa_expires'] = (timezone.now() + timedelta(minutes=5)).timestamp()
                    return redirect('verify_2fa')
            except TwoFactorAuth.DoesNotExist:
                pass
            
            # Check if this is first login
            is_first_login = user.last_login is None
            
            login(request, user)
            
            # Different message for first-time vs returning users
            if is_first_login:
                messages.success(request, f'Welcome to AuctionHub, {username}! 🎉')
            else:
                messages.success(request, f'Welcome back, {username}!')
            
            next_url = request.GET.get('next', 'home')
            return redirect(next_url)
        else:
            LoginAttempt.objects.create(
                username=username,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                failure_reason='Invalid credentials'
            )
            
            remaining_attempts = 5 - LoginAttempt.objects.filter(
                username=username,
                success=False,
                timestamp__gte=timezone.now() - timedelta(minutes=15)
            ).count()
            
            if remaining_attempts > 0:
                messages.error(request, f'Invalid username or password. {remaining_attempts} attempts remaining.')
            else:
                messages.error(request, 'Too many failed attempts. Account locked for 15 minutes.')
            
            context = {'captcha_challenge': secrets.token_urlsafe(32)}
            request.session['captcha_challenge'] = context['captcha_challenge']
            request.session['captcha_timestamp'] = timezone.now().timestamp()
            return render(request, 'users/login.html', context)
    else:
        captcha_challenge = secrets.token_urlsafe(32)
        request.session['captcha_challenge'] = captcha_challenge
        request.session['captcha_timestamp'] = timezone.now().timestamp()
        return render(request, 'users/login.html', {'captcha_challenge': captcha_challenge})

@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('home')

@login_required
def profile_view(request):
    from auctions.models import Item, Bid, Cart
    from payments.models import Payment
    from django.db.models import Count, Sum
    
    user = request.user
    
    items_won = Item.objects.filter(winner=user, status='sold').order_by('-end_time')
    items_selling = Item.objects.filter(seller=user).exclude(status='sold').order_by('-created_at')
    items_sold = Item.objects.filter(seller=user, status='sold').order_by('-end_time')
    
    try:
        cart = Cart.objects.get(user=user)
        cart_items = cart.items.all()
        cart_total = cart.total()
    except Cart.DoesNotExist:
        cart = None
        cart_items = []
        cart_total = 0
    
    total_bids = Bid.objects.filter(bidder=user).count()
    total_spent = Payment.objects.filter(user=user, status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    total_won = items_won.count()
    
    active_bids = Bid.objects.filter(
        bidder=user, 
        item__status='active'
    ).select_related('item').order_by('-bid_time')[:5]
    
    followers_count = user.followers.count()
    following_count = user.following.count()
    
    followers_list = Follow.objects.filter(following=user).select_related('follower')[:10]
    following_list = Follow.objects.filter(follower=user).select_related('following')[:10]
    
    context = {
        'items_won': items_won,
        'items_selling': items_selling,
        'items_sold': items_sold,
        'cart': cart,
        'cart_items': cart_items,
        'cart_total': cart_total,
        'total_bids': total_bids,
        'total_spent': total_spent,
        'total_won': total_won,
        'active_bids': active_bids,
        'followers_count': followers_count,
        'following_count': following_count,
        'followers_list': followers_list,
        'following_list': following_list,
    }
    
    return render(request, 'users/profile_dashboard.html', context)

@login_required
def profile_edit_view(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated!')
            return redirect('profile')
    else:
        form = ProfileUpdateForm(instance=request.user.profile)
    
    return render(request, 'users/profile.html', {'form': form})

@login_required
@require_POST
def follow_user(request, username):
    user_to_follow = get_object_or_404(User, username=username)
    
    if request.user == user_to_follow:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'You cannot follow yourself'}, status=400)
        messages.error(request, 'You cannot follow yourself.')
        return redirect('seller_profile', username=username)
    
    follow, created = Follow.objects.get_or_create(
        follower=request.user,
        following=user_to_follow
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'following': True,
            'followers_count': user_to_follow.followers.count()
        })
    
    messages.success(request, f'You are now following {username}.')
    return redirect('seller_profile', username=username)

@login_required
@require_POST
def unfollow_user(request, username):
    user_to_unfollow = get_object_or_404(User, username=username)
    
    Follow.objects.filter(
        follower=request.user,
        following=user_to_unfollow
    ).delete()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'following': False,
            'followers_count': user_to_unfollow.followers.count()
        })
    
    messages.success(request, f'You have unfollowed {username}.')
    return redirect('seller_profile', username=username)

@login_required
def wallet_dashboard(request):
    from .models import Wallet, WalletTransaction
    from auctions.models import Country
    
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    
    transactions = WalletTransaction.objects.filter(wallet=wallet)[:20]
    
    countries = Country.objects.all().order_by('name')
    
    context = {
        'wallet': wallet,
        'transactions': transactions,
        'countries': countries,
    }
    
    return render(request, 'users/wallet_dashboard.html', context)

@login_required
def wallet_deposit(request):
    from auctions.models import Country
    from .models import Wallet
    
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    countries = Country.objects.all().order_by('name')
    
    context = {
        'wallet': wallet,
        'countries': countries,
    }
    
    return render(request, 'users/wallet_deposit.html', context)

@login_required
@require_POST
def process_deposit(request):
    from .models import Wallet, WalletTransaction
    from payments.models import Payment
    from decimal import Decimal
    from django.db import transaction as db_transaction
    from django.utils import timezone
    import uuid
    
    amount = request.POST.get('amount')
    payment_method = request.POST.get('payment_method')
    phone_number = request.POST.get('phone_number', '')
    
    if not amount or not payment_method:
        messages.error(request, 'Please provide all required fields.')
        return redirect('wallet_deposit')
    
    if payment_method in ['mtn', 'airtel'] and not phone_number:
        messages.error(request, 'Phone number is required for mobile money payments.')
        return redirect('wallet_deposit')
    
    try:
        amount = Decimal(amount)
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
            return redirect('wallet_deposit')
        if amount > 100000000:
            messages.error(request, 'Amount exceeds maximum limit.')
            return redirect('wallet_deposit')
    except:
        messages.error(request, 'Invalid amount.')
        return redirect('wallet_deposit')
    
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    
    if wallet.user != request.user:
        messages.error(request, 'Unauthorized wallet access.')
        return redirect('wallet_deposit')
    
    TAX_RATE = Decimal('0.05')
    base_amount = amount
    tax_amount = base_amount * TAX_RATE
    total_amount = base_amount + tax_amount
    
    payment = Payment.objects.create(
        user=request.user,
        amount=total_amount,
        platform_tax=tax_amount,
        payment_method=payment_method,
        phone_number=phone_number,
        status='pending',
        description=f'Wallet deposit - UGX {base_amount}',
        transaction_reference=f'DEP-{uuid.uuid4().hex[:12].upper()}',
        metadata={
            'base_amount': str(base_amount),
            'platform_tax': str(tax_amount),
            'total': str(total_amount)
        }
    )
    
    if payment_method in ['mtn', 'airtel']:
        return redirect('ussd_wallet_deposit', payment_id=payment.payment_id)
    elif payment_method == 'card':
        return redirect(f'/payment/card/{payment.payment_id}/?context=wallet_deposit')
    elif payment_method == 'paypal':
        return redirect(f'/payment/paypal/{payment.payment_id}/?context=wallet_deposit')
    else:
        payment.status = 'failed'
        payment.save(update_fields=['status'])
        messages.error(request, 'Invalid payment method.')
        return redirect('wallet_deposit')

@login_required
def wallet_withdraw(request):
    from .models import Wallet
    
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    
    context = {
        'wallet': wallet,
    }
    
    return render(request, 'users/wallet_withdraw.html', context)

@login_required
@require_POST
def process_withdrawal(request):
    from .models import Wallet
    from payments.models import Payment
    from decimal import Decimal
    import uuid
    
    amount = request.POST.get('amount')
    payment_method = request.POST.get('payment_method')
    phone_number = request.POST.get('phone_number', '')
    
    if not amount or not payment_method:
        messages.error(request, 'Please provide all required fields.')
        return redirect('wallet_withdraw')
    
    if payment_method in ['mtn', 'airtel'] and not phone_number:
        messages.error(request, 'Phone number is required for mobile money withdrawals.')
        return redirect('wallet_withdraw')
    
    try:
        amount = Decimal(amount)
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
            return redirect('wallet_withdraw')
        if amount < 1000:
            messages.error(request, 'Minimum withdrawal is UGX 1,000.')
            return redirect('wallet_withdraw')
    except:
        messages.error(request, 'Invalid amount.')
        return redirect('wallet_withdraw')
    
    try:
        wallet = Wallet.objects.get(user=request.user)
    except Wallet.DoesNotExist:
        messages.error(request, 'Wallet not found.')
        return redirect('wallet_withdraw')
    
    if wallet.user != request.user:
        messages.error(request, 'Unauthorized wallet access.')
        return redirect('wallet_withdraw')
    
    if not wallet.can_withdraw(amount):
        messages.error(request, 'Insufficient balance or wallet is locked.')
        return redirect('wallet_withdraw')
    
    TAX_RATE = Decimal('0.05')
    base_amount = amount
    tax_amount = base_amount * TAX_RATE
    total_amount = base_amount + tax_amount
    
    payment = Payment.objects.create(
        user=request.user,
        amount=total_amount,
        platform_tax=tax_amount,
        payment_method=payment_method,
        phone_number=phone_number,
        status='pending',
        description=f'Wallet withdrawal - UGX {base_amount}',
        transaction_reference=f'WTH-{uuid.uuid4().hex[:12].upper()}',
        metadata={
            'base_amount': str(base_amount),
            'platform_tax': str(tax_amount),
            'total': str(total_amount)
        }
    )
    
    if payment_method in ['mtn', 'airtel']:
        return redirect('ussd_wallet_withdraw', payment_id=payment.payment_id)
    elif payment_method == 'card':
        return redirect(f'/payment/card/{payment.payment_id}/?context=wallet_withdraw')
    elif payment_method == 'paypal':
        return redirect(f'/payment/paypal/{payment.payment_id}/?context=wallet_withdraw')
    else:
        payment.status = 'failed'
        payment.save(update_fields=['status'])
        messages.error(request, 'Invalid payment method.')
        return redirect('wallet_withdraw')

@login_required
def seller_application_view(request):
    from .forms import SellerApplicationForm
    from django.utils import timezone
    
    profile = request.user.profile
    
    if profile.seller_status == 'approved':
        messages.info(request, 'You are already an approved seller!')
        return redirect('seller_dashboard')
    
    if profile.seller_status == 'pending':
        messages.info(request, 'Your seller application is pending review.')
        return redirect('seller_application_status')
    
    if request.method == 'POST':
        form = SellerApplicationForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.seller_status = 'pending'
            profile.seller_application_date = timezone.now()
            profile.save()
            
            messages.success(request, 'Your seller application has been submitted successfully! We will review it within 24-48 hours.')
            return redirect('seller_application_status')
    else:
        form = SellerApplicationForm(instance=profile)
    
    return render(request, 'users/seller_application.html', {'form': form})

@login_required
def seller_application_status_view(request):
    profile = request.user.profile
    
    if profile.seller_status == 'none':
        messages.info(request, 'You have not applied to become a seller yet.')
        return redirect('seller_application')
    
    return render(request, 'users/seller_application_status.html', {'profile': profile})

@login_required
def seller_dashboard_view(request):
    from auctions.models import Item, Bid, Review
    from payments.models import Payment
    from django.db.models import Sum, Count, Avg, Q
    from django.utils import timezone
    from datetime import timedelta
    
    profile = request.user.profile
    
    if not profile.is_seller or profile.seller_status != 'approved':
        messages.error(request, 'You need to be an approved seller to access this page.')
        return redirect('seller_application')
    
    my_items = Item.objects.filter(seller=request.user)
    active_items = my_items.filter(status='active')
    sold_items = my_items.filter(status='sold')
    
    total_sales = sold_items.count()
    total_revenue = Payment.objects.filter(
        item__seller=request.user,
        status='completed'
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    platform_tax_paid = Payment.objects.filter(
        item__seller=request.user,
        status='completed'
    ).aggregate(Sum('platform_tax'))['platform_tax__sum'] or 0
    
    net_revenue = total_revenue - platform_tax_paid
    
    total_items_listed = my_items.count()
    active_listings = active_items.count()
    
    total_views = my_items.aggregate(Sum('views'))['views__sum'] or 0
    
    avg_rating = Review.objects.filter(
        item__seller=request.user
    ).aggregate(Avg('rating'))['rating__avg'] or 0
    
    total_reviews = Review.objects.filter(item__seller=request.user).count()
    
    top_performing_items = sold_items.annotate(
        final_price=Count('bids')
    ).order_by('-current_price')[:5]
    
    recent_sales = sold_items.order_by('-end_time')[:10]
    
    recent_reviews = Review.objects.filter(
        item__seller=request.user
    ).select_related('reviewer', 'item').order_by('-created_at')[:5]
    
    last_30_days = timezone.now() - timedelta(days=30)
    monthly_sales = sold_items.filter(end_time__gte=last_30_days).count()
    monthly_revenue = Payment.objects.filter(
        item__seller=request.user,
        status='completed',
        created_at__gte=last_30_days
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    last_7_days = timezone.now() - timedelta(days=7)
    weekly_sales = sold_items.filter(end_time__gte=last_7_days).count()
    
    conversion_rate = 0
    if total_items_listed > 0:
        conversion_rate = (total_sales / total_items_listed) * 100
    
    avg_sale_price = 0
    if total_sales > 0:
        avg_sale_price = total_revenue / total_sales
    
    items_by_category = my_items.values('category__name').annotate(
        count=Count('id'),
        revenue=Sum('current_price')
    ).order_by('-revenue')[:5]
    
    context = {
        'profile': profile,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'platform_tax_paid': platform_tax_paid,
        'net_revenue': net_revenue,
        'total_items_listed': total_items_listed,
        'active_listings': active_listings,
        'total_views': total_views,
        'avg_rating': round(avg_rating, 1) if avg_rating else 0,
        'total_reviews': total_reviews,
        'top_performing_items': top_performing_items,
        'recent_sales': recent_sales,
        'recent_reviews': recent_reviews,
        'monthly_sales': monthly_sales,
        'monthly_revenue': monthly_revenue,
        'weekly_sales': weekly_sales,
        'conversion_rate': round(conversion_rate, 1),
        'avg_sale_price': avg_sale_price,
        'items_by_category': items_by_category,
        'active_items': active_items[:5],
    }
    
    return render(request, 'users/seller_dashboard.html', context)

# Password Reset Views
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.forms import SetPasswordForm
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

def password_reset_request(request):
    """Request password reset"""
    if request.method == 'POST':
        email = request.POST.get('email')
        
        try:
            user = User.objects.get(email=email)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            reset_link = request.build_absolute_uri(f'/users/password-reset-confirm/{uid}/{token}/')
            
            try:
                send_mail(
                    subject='Password Reset Request - AuctionHub',
                    message=f'Click the link below to reset your password:\n\n{reset_link}\n\nIf you did not request this, please ignore this email.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                messages.success(request, 'Password reset link has been sent to your email!')
            except Exception as e:
                messages.warning(request, f'Password reset link: {reset_link}')
                messages.info(request, 'Email service not configured. Please copy the link above.')
            
            return redirect('login')
        except User.DoesNotExist:
            messages.success(request, 'If that email exists, a reset link has been sent.')
            return redirect('login')
    
    return render(request, 'users/password_reset.html')

def password_reset_confirm(request, uidb64, token):
    """Confirm password reset"""
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            
            if password1 != password2:
                messages.error(request, 'Passwords do not match!')
                return render(request, 'users/password_reset_confirm.html', {'valid_link': True})
            
            if len(password1) < 8:
                messages.error(request, 'Password must be at least 8 characters long!')
                return render(request, 'users/password_reset_confirm.html', {'valid_link': True})
            
            user.set_password(password1)
            user.save()
            
            messages.success(request, 'Your password has been reset successfully! You can now log in.')
            return redirect('login')
        
        return render(request, 'users/password_reset_confirm.html', {'valid_link': True})
    else:
        messages.error(request, 'Password reset link is invalid or has expired.')
        return redirect('password_reset')

def verify_2fa(request):
    """Verify 2FA code - supports both Email OTP and TOTP"""
    from django.utils import timezone
    from .models import EmailOTP, TwoFactorAuth
    import pyotp
    
    pending_user_id = request.session.get('pending_2fa_user_id')
    expires_timestamp = request.session.get('2fa_expires')
    
    if not pending_user_id or not expires_timestamp:
        messages.error(request, 'Session expired. Please login again.')
        return redirect('login')
    
    if timezone.now().timestamp() > expires_timestamp:
        if 'pending_2fa_user_id' in request.session:
            del request.session['pending_2fa_user_id']
        if 'pending_2fa_otp_id' in request.session:
            del request.session['pending_2fa_otp_id']
        if '2fa_expires' in request.session:
            del request.session['2fa_expires']
        messages.error(request, 'Verification code expired. Please login again.')
        return redirect('login')
    
    try:
        user = User.objects.get(id=pending_user_id)
        two_factor = TwoFactorAuth.objects.get(user=user)
    except (User.DoesNotExist, TwoFactorAuth.DoesNotExist):
        messages.error(request, 'Invalid session. Please login again.')
        return redirect('login')
    
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        use_backup = request.POST.get('use_backup', '') == 'true'
        
        # Check if this is a backup code (8 hex characters)
        if use_backup or (len(code) == 8 and all(c in '0123456789ABCDEFabcdef' for c in code)):
            if two_factor.use_backup_code(code):
                verified = True
                messages.success(request, 'Backup code verified! You have successfully logged in.')
                messages.warning(request, f'You have {len(two_factor.backup_codes)} backup codes remaining.')
            else:
                messages.error(request, 'Invalid backup code.')
                time_remaining = int(expires_timestamp - timezone.now().timestamp())
                return render(request, 'users/verify_2fa.html', {
                    'user': user,
                    'two_factor': two_factor,
                    'time_remaining': max(0, time_remaining)
                })
        else:
            # Regular 2FA code verification
            if len(code) != 6 or not code.isdigit():
                messages.error(request, 'Please enter a valid 6-digit code.')
                time_remaining = int(expires_timestamp - timezone.now().timestamp())
                return render(request, 'users/verify_2fa.html', {
                    'user': user,
                    'two_factor': two_factor,
                    'time_remaining': max(0, time_remaining)
                })
            
            verified = False
            
            if two_factor.method == 'email':
                pending_otp_id = request.session.get('pending_2fa_otp_id')
                if pending_otp_id:
                    try:
                        otp = EmailOTP.objects.get(id=pending_otp_id, user=user, purpose='login')
                        if otp.is_valid() and otp.code == code and not otp.is_used:
                            otp.mark_as_used()
                            verified = True
                        elif otp.is_used:
                            messages.error(request, 'This verification code has already been used.')
                        elif not otp.is_valid():
                            messages.error(request, 'Verification code has expired.')
                        else:
                            messages.error(request, 'Invalid verification code.')
                    except EmailOTP.DoesNotExist:
                        messages.error(request, 'Invalid verification code.')
            
            elif two_factor.method == 'totp' and two_factor.totp_secret:
                totp = pyotp.TOTP(two_factor.totp_secret)
                if totp.verify(code, valid_window=1):
                    verified = True
                else:
                    messages.error(request, 'Invalid verification code.')
        
        if verified:
            if 'pending_2fa_user_id' in request.session:
                del request.session['pending_2fa_user_id']
            if 'pending_2fa_otp_id' in request.session:
                del request.session['pending_2fa_otp_id']
            if '2fa_expires' in request.session:
                del request.session['2fa_expires']
            
            two_factor.last_used = timezone.now()
            two_factor.save()
            
            # Check if this is first login
            is_first_login = user.last_login is None
            
            login(request, user)
            
            # Different message for first-time vs returning users
            if is_first_login:
                messages.success(request, f'Welcome to AuctionHub, {user.username}! 🎉')
            else:
                messages.success(request, f'Welcome back, {user.username}!')
            
            return redirect('home')
        
        if not verified and not messages.get_messages(request):
            time_remaining = int(expires_timestamp - timezone.now().timestamp())
            return render(request, 'users/verify_2fa.html', {
                'user': user,
                'two_factor': two_factor,
                'time_remaining': max(0, time_remaining)
            })
    
    time_remaining = int(expires_timestamp - timezone.now().timestamp())
    return render(request, 'users/verify_2fa.html', {
        'user': user,
        'two_factor': two_factor,
        'time_remaining': max(0, time_remaining)
    })

@login_required
def security_settings(request):
    """Security settings page for 2FA management"""
    from .models import TwoFactorAuth, LoginAttempt
    import json
    
    try:
        two_factor = TwoFactorAuth.objects.get(user=request.user)
    except TwoFactorAuth.DoesNotExist:
        two_factor = None
    
    backup_codes = []
    if two_factor and two_factor.backup_codes:
        try:
            all_codes = json.loads(two_factor.backup_codes)
            backup_codes = [code for code, used in all_codes.items() if not used]
        except:
            pass
    
    login_attempts = LoginAttempt.objects.filter(
        username=request.user.username
    ).order_by('-timestamp')[:10]
    
    context = {
        'two_factor': two_factor,
        'backup_codes': backup_codes,
        'login_attempts': login_attempts,
    }
    
    return render(request, 'users/security_settings.html', context)

@login_required
def enable_2fa_email(request):
    """Enable email-based 2FA"""
    from .models import TwoFactorAuth
    import json
    import secrets
    
    two_factor, created = TwoFactorAuth.objects.get_or_create(
        user=request.user,
        defaults={'enabled': True, 'method': 'email'}
    )
    
    if not created:
        two_factor.enabled = True
        two_factor.method = 'email'
        two_factor.save()
    
    backup_codes = {}
    for _ in range(10):
        code = ''.join([str(secrets.randbelow(10)) for _ in range(8)])
        backup_codes[code] = False
    
    two_factor.backup_codes = json.dumps(backup_codes)
    two_factor.save()
    
    messages.success(request, 'Two-factor authentication has been enabled! Backup codes have been generated.')
    return redirect('security_settings')

@login_required
def disable_2fa(request):
    """Disable 2FA"""
    from .models import TwoFactorAuth
    
    if request.method == 'POST':
        try:
            two_factor = TwoFactorAuth.objects.get(user=request.user)
            two_factor.enabled = False
            two_factor.save(update_fields=['enabled'])
            messages.success(request, 'Two-factor authentication has been disabled.')
        except TwoFactorAuth.DoesNotExist:
            messages.info(request, '2FA was not enabled.')
    
    return redirect('security_settings')

@login_required
def change_password(request):
    """Change user password with old password verification"""
    from django.contrib.auth import update_session_auth_hash
    
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        # Verify old password
        if not request.user.check_password(old_password):
            messages.error(request, 'Current password is incorrect.')
            return render(request, 'users/change_password.html')
        
        # Check if new passwords match
        if new_password1 != new_password2:
            messages.error(request, 'New passwords do not match.')
            return render(request, 'users/change_password.html')
        
        # Check password length
        if len(new_password1) < 8:
            messages.error(request, 'New password must be at least 8 characters long.')
            return render(request, 'users/change_password.html')
        
        # Check if new password is same as old
        if old_password == new_password1:
            messages.error(request, 'New password must be different from your current password.')
            return render(request, 'users/change_password.html')
        
        # Change password
        request.user.set_password(new_password1)
        request.user.save()
        
        # Keep user logged in after password change
        update_session_auth_hash(request, request.user)
        
        messages.success(request, 'Your password has been changed successfully!')
        return redirect('security_settings')
    
    return render(request, 'users/change_password.html')

@login_required
def setup_totp(request):
    """Setup TOTP (Google Authenticator)"""
    import pyotp
    import qrcode
    import io
    import base64
    from .models import TwoFactorAuth
    
    two_factor, created = TwoFactorAuth.objects.get_or_create(user=request.user)
    
    if not two_factor.totp_secret:
        two_factor.totp_secret = pyotp.random_base32()
        two_factor.save()
    
    totp_uri = pyotp.totp.TOTP(two_factor.totp_secret).provisioning_uri(
        name=request.user.email,
        issuer_name='AuctionHub'
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    qr_code_data = base64.b64encode(buffer.getvalue()).decode()
    
    if request.method == 'POST':
        verification_code = request.POST.get('code', '').strip()
        totp = pyotp.TOTP(two_factor.totp_secret)
        
        if totp.verify(verification_code, valid_window=1):
            two_factor.enabled = True
            two_factor.method = 'totp'
            
            import json
            import secrets
            backup_codes = {}
            for _ in range(10):
                code = ''.join([str(secrets.randbelow(10)) for _ in range(8)])
                backup_codes[code] = False
            two_factor.backup_codes = json.dumps(backup_codes)
            two_factor.save()
            
            messages.success(request, 'TOTP authentication has been enabled successfully!')
            return redirect('security_settings')
        else:
            messages.error(request, 'Invalid verification code. Please try again.')
    
    context = {
        'qr_code_data': qr_code_data,
        'totp_secret': two_factor.totp_secret,
        'two_factor': two_factor,
    }
    
    return render(request, 'users/setup_totp.html', context)

@login_required
def generate_backup_codes(request):
    """Generate new backup codes"""
    from .models import TwoFactorAuth
    import json
    import secrets
    
    if request.method == 'POST':
        try:
            two_factor = TwoFactorAuth.objects.get(user=request.user)
            
            backup_codes = {}
            for _ in range(10):
                code = ''.join([str(secrets.randbelow(10)) for _ in range(8)])
                backup_codes[code] = False
            
            two_factor.backup_codes = json.dumps(backup_codes)
            two_factor.save()
            
            messages.success(request, 'New backup codes have been generated!')
        except TwoFactorAuth.DoesNotExist:
            messages.error(request, 'Please enable 2FA first.')
    
    return redirect('security_settings')
