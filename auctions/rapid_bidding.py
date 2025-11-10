from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from decimal import Decimal
import math
from .models import Bid, BidCooldown, Item
from django.contrib.auth.models import User


class RapidBiddingDetector:
    
    @staticmethod
    def check_rapid_bidding(user, item, bid_amount):
        """
        Comprehensive rapid bidding check with soft/hard thresholds and endgame exceptions.
        Returns: (is_allowed, action_type, message, cooldown_duration)
        - is_allowed: True if bid can proceed, False if blocked
        - action_type: 'allow', 'soft_challenge', 'hard_cooldown', or 'suspended'
        - message: User-friendly message
        - cooldown_duration: Seconds for cooldown (if applicable)
        """
        now = timezone.now()
        
        existing_cooldown = BidCooldown.get_active_cooldown(user, item)
        if existing_cooldown:
            if existing_cooldown.cooldown_type == 'soft_challenge' and not existing_cooldown.captcha_passed:
                return (
                    False,
                    'soft_challenge',
                    f"Please complete the security challenge to continue bidding.",
                    None
                )
            elif existing_cooldown.cooldown_type in ['hard_cooldown', 'suspended']:
                time_remaining = int((existing_cooldown.expires_at - now).total_seconds())
                mins = time_remaining // 60
                secs = time_remaining % 60
                return (
                    False,
                    existing_cooldown.cooldown_type,
                    f"You're bidding too quickly. Please wait {mins}m {secs}s before bidding again.",
                    time_remaining
                )
        
        is_endgame = RapidBiddingDetector._is_auction_endgame(item)
        multiplier = settings.AUCTION_ENDGAME_MULTIPLIER if is_endgame else 1.0
        
        user_bids = Bid.objects.filter(bidder=user, item=item).order_by('-bid_time')
        
        soft_2min_threshold = math.ceil(settings.RAPID_BID_SOFT_THRESHOLD_2MIN * multiplier)
        soft_2min_check, soft_2min_count = RapidBiddingDetector._check_window(
            user_bids,
            minutes=settings.RAPID_BID_SOFT_WINDOW_2MIN,
            threshold=soft_2min_threshold
        )
        
        soft_5min_threshold = math.ceil(settings.RAPID_BID_SOFT_THRESHOLD_5MIN * multiplier)
        soft_5min_check, soft_5min_count = RapidBiddingDetector._check_window(
            user_bids,
            minutes=settings.RAPID_BID_SOFT_WINDOW_5MIN,
            threshold=soft_5min_threshold
        )
        
        if soft_2min_check or soft_5min_check:
            window_desc = f"{soft_2min_count} bids in 2 minutes" if soft_2min_check else f"{soft_5min_count} bids in 5 minutes"
            escalated = RapidBiddingDetector._create_soft_challenge(user, item, f"Rapid bidding: {window_desc}")
            if escalated:
                return (
                    False,
                    'hard_cooldown',
                    "Too many verification attempts. You've been temporarily blocked from bidding.",
                    settings.RAPID_BID_COOLDOWN_DURATION * 2
                )
            return (
                False,
                'soft_challenge',
                f"Unusual activity detected ({window_desc}). Please complete the security challenge to continue bidding.",
                None
            )
        
        hard_5min_threshold = math.ceil(settings.RAPID_BID_HARD_THRESHOLD_5MIN * multiplier)
        hard_5min_check, hard_5min_count = RapidBiddingDetector._check_window(
            user_bids,
            minutes=settings.RAPID_BID_HARD_WINDOW_5MIN,
            threshold=hard_5min_threshold
        )
        
        hard_20sec_threshold = math.ceil(settings.RAPID_BID_HARD_THRESHOLD_20SEC * multiplier)
        hard_20sec_check, hard_20sec_count = RapidBiddingDetector._check_window(
            user_bids,
            seconds=settings.RAPID_BID_HARD_WINDOW_20SEC,
            threshold=hard_20sec_threshold
        )
        
        if hard_5min_check or hard_20sec_check:
            cooldown_duration = settings.RAPID_BID_COOLDOWN_DURATION
            window_desc = f"{hard_5min_count} bids in 5 minutes" if hard_5min_check else f"{hard_20sec_count} bids in 20 seconds"
            RapidBiddingDetector._create_hard_cooldown(
                user, item, cooldown_duration,
                f"Excessive bidding: {window_desc}"
            )
            mins = cooldown_duration // 60
            return (
                False,
                'hard_cooldown',
                f"Too many bids too quickly ({window_desc}). Please wait {mins} minutes before bidding again.",
                cooldown_duration
            )
        
        global_soft_check = RapidBiddingDetector._check_global_velocity_soft(user)
        if global_soft_check:
            RapidBiddingDetector._create_soft_challenge(user, None, "High velocity across multiple auctions")
            return (
                False,
                'soft_challenge',
                "Unusual bidding activity detected. Please complete the security challenge.",
                None
            )
        
        global_hard_check = RapidBiddingDetector._check_global_velocity_hard(user)
        if global_hard_check:
            cooldown_duration = settings.RAPID_BID_COOLDOWN_DURATION * 2
            RapidBiddingDetector._create_hard_cooldown(
                user, None, cooldown_duration,
                "Excessive bidding across multiple auctions"
            )
            mins = cooldown_duration // 60
            return (
                False,
                'hard_cooldown',
                f"Suspicious cross-auction bidding. Cooling down for {mins} minutes.",
                cooldown_duration
            )
        
        min_increment_check = RapidBiddingDetector._check_minimum_increment_pattern(user, item, bid_amount)
        if min_increment_check:
            RapidBiddingDetector._create_soft_challenge(user, item, "Suspicious minimal increment pattern")
            return (
                False,
                'soft_challenge',
                "Unusual bid pattern detected. Please complete the verification.",
                None
            )
        
        return (True, 'allow', 'Bid allowed', None)
    
    @staticmethod
    def _is_auction_endgame(item):
        """Check if auction is in the last N minutes (endgame period)"""
        if item.status != 'active':
            return False
        
        now = timezone.now()
        time_remaining = (item.end_time - now).total_seconds()
        endgame_seconds = settings.AUCTION_ENDGAME_WINDOW_MINUTES * 60
        
        return 0 < time_remaining <= endgame_seconds
    
    @staticmethod
    def _check_window(bids_queryset, minutes=None, seconds=None, threshold=1):
        """
        Check if number of bids in time window exceeds threshold.
        Includes the current pending bid (+1) in the count.
        Returns (exceeded, count_of_existing_bids)
        """
        now = timezone.now()
        
        if minutes:
            window_start = now - timedelta(minutes=minutes)
        elif seconds:
            window_start = now - timedelta(seconds=seconds)
        else:
            return (False, 0)
        
        count = bids_queryset.filter(bid_time__gte=window_start).count()
        # Include the current pending bid in the count
        return (count + 1 >= threshold, count + 1)
    
    @staticmethod
    def _check_global_velocity_soft(user):
        """Check global cross-auction velocity (soft threshold). Includes pending bid."""
        now = timezone.now()
        window_start = now - timedelta(minutes=settings.GLOBAL_VELOCITY_SOFT_WINDOW_MINUTES)
        
        recent_bids = Bid.objects.filter(
            bidder=user,
            bid_time__gte=window_start
        )
        
        bid_count = recent_bids.count() + 1  # Include pending bid
        auction_count = recent_bids.values('item').distinct().count()
        
        return (
            bid_count >= settings.GLOBAL_VELOCITY_SOFT_THRESHOLD_BIDS and
            auction_count >= settings.GLOBAL_VELOCITY_SOFT_THRESHOLD_AUCTIONS
        )
    
    @staticmethod
    def _check_global_velocity_hard(user):
        """Check global cross-auction velocity (hard threshold). Includes pending bid."""
        now = timezone.now()
        window_start = now - timedelta(minutes=settings.GLOBAL_VELOCITY_HARD_WINDOW_MINUTES)
        
        recent_bids = Bid.objects.filter(
            bidder=user,
            bid_time__gte=window_start
        )
        
        bid_count = recent_bids.count() + 1  # Include pending bid
        auction_count = recent_bids.values('item').distinct().count()
        
        return (
            bid_count >= settings.GLOBAL_VELOCITY_HARD_THRESHOLD_BIDS and
            auction_count >= settings.GLOBAL_VELOCITY_HARD_THRESHOLD_AUCTIONS
        )
    
    @staticmethod
    def _check_minimum_increment_pattern(user, item, current_bid_amount):
        """Detect if user is consistently bidding minimal increments"""
        now = timezone.now()
        window_start = now - timedelta(seconds=settings.MIN_INCREMENT_WINDOW_SECONDS)
        
        recent_bids = Bid.objects.filter(
            bidder=user,
            item=item,
            bid_time__gte=window_start
        ).order_by('bid_time')
        
        if recent_bids.count() < settings.MIN_INCREMENT_THRESHOLD_BIDS - 1:
            return False
        
        minimal_increments = 0
        tolerance = Decimal('1.1')
        
        for i in range(len(recent_bids) - 1):
            current = recent_bids[i].amount
            next_bid = recent_bids[i + 1].amount
            increment = next_bid - current
            
            if increment <= item.min_increment * tolerance:
                minimal_increments += 1
        
        if current_bid_amount and recent_bids.exists():
            last_bid = recent_bids.last().amount
            increment = Decimal(str(current_bid_amount)) - last_bid
            if increment <= item.min_increment * tolerance:
                minimal_increments += 1
        
        return minimal_increments >= settings.MIN_INCREMENT_THRESHOLD_BIDS
    
    @staticmethod
    def _create_soft_challenge(user, item, reason):
        """
        Create a soft challenge cooldown requiring CAPTCHA.
        Returns True if escalated to hard cooldown (after too many soft challenges).
        """
        expires_at = timezone.now() + timedelta(minutes=10)
        
        # Check for recent soft challenges (last hour) to escalate repeat offenders
        recent_soft_challenges = BidCooldown.objects.filter(
            user=user,
            item=item,
            cooldown_type='soft_challenge',
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()
        
        # After 2 existing soft challenges, the 3rd triggers escalation to hard cooldown
        if recent_soft_challenges >= 2:
            RapidBiddingDetector._create_hard_cooldown(
                user, item,
                settings.RAPID_BID_COOLDOWN_DURATION * 2,
                "Repeated soft challenge violations"
            )
            return True
        
        existing = BidCooldown.objects.filter(
            user=user,
            item=item,
            cooldown_type='soft_challenge',
            is_active=True
        ).first()
        
        if not existing:
            BidCooldown.objects.create(
                user=user,
                item=item,
                cooldown_type='soft_challenge',
                reason=reason,
                expires_at=expires_at,
                captcha_required=True
            )
        
        return False
    
    @staticmethod
    def _create_hard_cooldown(user, item, duration_seconds, reason):
        """Create a hard cooldown preventing bidding"""
        expires_at = timezone.now() + timedelta(seconds=duration_seconds)
        
        BidCooldown.objects.create(
            user=user,
            item=item,
            cooldown_type='hard_cooldown',
            reason=reason,
            expires_at=expires_at
        )
    
    @staticmethod
    def pass_captcha_challenge(user, item):
        """Mark captcha as passed for user's soft challenge"""
        cooldown = BidCooldown.objects.filter(
            user=user,
            item=item,
            cooldown_type='soft_challenge',
            is_active=True,
            captcha_required=True
        ).first()
        
        if cooldown:
            cooldown.captcha_passed = True
            cooldown.is_active = False
            cooldown.save(update_fields=['captcha_passed', 'is_active'])
            return True
        return False
    
    @staticmethod
    def fail_captcha_challenge(user, item):
        """Record failed CAPTCHA attempt"""
        cooldown = BidCooldown.objects.filter(
            user=user,
            item=item,
            cooldown_type='soft_challenge',
            is_active=True
        ).first()
        
        if cooldown:
            cooldown.failed_attempts += 1
            
            if cooldown.failed_attempts >= 3:
                cooldown.is_active = False
                cooldown.save(update_fields=['failed_attempts', 'is_active'])
                
                RapidBiddingDetector._create_hard_cooldown(
                    user, item,
                    settings.RAPID_BID_COOLDOWN_DURATION * 3,
                    "Failed CAPTCHA challenge 3 times"
                )
            else:
                cooldown.save(update_fields=['failed_attempts'])
