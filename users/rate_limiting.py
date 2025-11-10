"""
Rate limiting middleware for AuctionHub

Protects against brute-force attacks and abuse on:
- Login endpoints
- Bidding operations
- USSD/SMS requests
- Payment processing
"""

from django.core.cache import cache
from django.http import JsonResponse, HttpResponse
from django.conf import settings
import time
import hashlib


class RateLimitMiddleware:
    """
    Rate limiting middleware using Redis cache
    
    Rate limits (per IP address):
    - Login: 5 attempts per minute
    - Bidding: 10 bids per minute
    - USSD: 20 requests per minute
    - General API: 100 requests per minute
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, 'RATELIMIT_ENABLE', True)
        
        # Rate limit rules: (path_contains, max_requests, window_seconds)
        self.rules = [
            ('/login/', 5, 60),           # 5 login attempts per minute
            ('/place_bid/', 10, 60),      # 10 bids per minute
            ('/ussd/', 20, 60),           # 20 USSD requests per minute
            ('/api/', 100, 60),           # 100 API calls per minute
            ('/checkout/', 10, 60),       # 10 checkout attempts per minute
        ]
    
    def __call__(self, request):
        if not self.enabled:
            return self.get_response(request)
        
        # Get client identifier (IP address + user agent hash)
        client_id = self._get_client_id(request)
        path = request.path
        
        # Check rate limits
        for path_pattern, max_requests, window in self.rules:
            if path_pattern in path:
                if not self._check_rate_limit(client_id, path_pattern, max_requests, window):
                    return self._rate_limit_exceeded_response(request)
        
        response = self.get_response(request)
        return response
    
    def _get_client_id(self, request):
        """Generate unique client identifier"""
        # Use IP address
        ip = self._get_client_ip(request)
        
        # Add user agent hash for additional uniqueness
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        ua_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]
        
        return f"{ip}:{ua_hash}"
    
    def _get_client_ip(self, request):
        """Extract client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip
    
    def _check_rate_limit(self, client_id, endpoint, max_requests, window):
        """
        Check if request is within rate limit
        
        Uses sliding window counter algorithm
        """
        cache_key = f"ratelimit:{endpoint}:{client_id}"
        
        # Get current request count and timestamp
        data = cache.get(cache_key, {'count': 0, 'reset_time': time.time() + window})
        
        current_time = time.time()
        
        # Reset counter if window expired
        if current_time >= data['reset_time']:
            data = {'count': 1, 'reset_time': current_time + window}
            cache.set(cache_key, data, window)
            return True
        
        # Increment counter
        data['count'] += 1
        
        # Check if limit exceeded
        if data['count'] > max_requests:
            cache.set(cache_key, data, window)
            return False
        
        # Update cache
        cache.set(cache_key, data, window)
        return True
    
    def _rate_limit_exceeded_response(self, request):
        """Return 429 Too Many Requests response"""
        if request.META.get('HTTP_ACCEPT', '').startswith('application/json'):
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'message': 'Too many requests. Please try again later.',
                'status': 429
            }, status=429)
        else:
            return HttpResponse(
                '<h1>429 Too Many Requests</h1>'
                '<p>You have made too many requests. Please wait a moment and try again.</p>',
                status=429
            )


def rate_limit_decorator(max_requests=10, window=60):
    """
    Decorator for view-level rate limiting
    
    Usage:
        @rate_limit_decorator(max_requests=5, window=60)
        def my_view(request):
            ...
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if not getattr(settings, 'RATELIMIT_ENABLE', True):
                return view_func(request, *args, **kwargs)
            
            # Get client ID
            ip = request.META.get('REMOTE_ADDR', '')
            cache_key = f"ratelimit:{view_func.__name__}:{ip}"
            
            # Check rate limit
            data = cache.get(cache_key, {'count': 0, 'reset_time': time.time() + window})
            
            current_time = time.time()
            
            if current_time >= data['reset_time']:
                data = {'count': 1, 'reset_time': current_time + window}
                cache.set(cache_key, data, window)
            else:
                data['count'] += 1
                
                if data['count'] > max_requests:
                    cache.set(cache_key, data, window)
                    
                    if request.META.get('HTTP_ACCEPT', '').startswith('application/json'):
                        return JsonResponse({
                            'error': 'Rate limit exceeded',
                            'message': f'Maximum {max_requests} requests per {window} seconds'
                        }, status=429)
                    else:
                        return HttpResponse('Rate limit exceeded', status=429)
                
                cache.set(cache_key, data, window)
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


# User-specific rate limiting
def user_rate_limit(user, action, max_requests=10, window=60):
    """
    Check rate limit for specific user action
    
    Returns: (allowed: bool, remaining: int, reset_time: float)
    """
    if not user or not user.is_authenticated:
        return True, max_requests, 0
    
    cache_key = f"user_ratelimit:{action}:{user.id}"
    
    data = cache.get(cache_key, {'count': 0, 'reset_time': time.time() + window})
    
    current_time = time.time()
    
    if current_time >= data['reset_time']:
        data = {'count': 1, 'reset_time': current_time + window}
        cache.set(cache_key, data, window)
        return True, max_requests - 1, data['reset_time']
    
    data['count'] += 1
    
    if data['count'] > max_requests:
        cache.set(cache_key, data, window)
        return False, 0, data['reset_time']
    
    cache.set(cache_key, data, window)
    return True, max_requests - data['count'], data['reset_time']
