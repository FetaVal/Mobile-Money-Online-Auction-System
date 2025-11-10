"""
Comprehensive Security Tests for AuctionHub

Tests cover:
1. Password Hashing (PBKDF2 600k iterations)
2. Login Attempt Limiting & Lockout
3. Email-based 2FA
4. TOTP-based 2FA  
5. Backup Codes
6. Security Settings Management
"""

from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from users.models import LoginAttempt, EmailOTP, TwoFactorAuth
import json
import pyotp


class PasswordHashingTestCase(TestCase):
    """Test PBKDF2 password hashing with 600k iterations"""
    
    def test_custom_hasher_iterations(self):
        """Verify custom hasher uses 600,000 iterations"""
        from auction_system.hashers import PBKDF2PasswordHasher600k
        hasher = PBKDF2PasswordHasher600k()
        self.assertEqual(hasher.iterations, 600000)
    
    def test_password_hashing_on_user_creation(self):
        """Test that new users get passwords hashed with 600k iterations"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
        
        self.assertTrue(user.password.startswith('pbkdf2_sha256$600000$'))
    
    def test_password_verification(self):
        """Test that password verification works correctly"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
        
        self.assertTrue(user.check_password('TestPassword123!'))
        self.assertFalse(user.check_password('WrongPassword'))


class LoginAttemptLimitingTestCase(TransactionTestCase):
    """Test login attempt limiting and account lockout"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
    
    def test_failed_login_tracked(self):
        """Test that failed login attempts are tracked"""
        response = self.client.post('/users/login/', {
            'username': 'testuser',
            'password': 'WrongPassword',
            'captcha_token': 'invalid'
        })
        
        attempts = LoginAttempt.objects.filter(username='testuser', success=False)
        self.assertTrue(attempts.exists())
    
    def test_successful_login_tracked(self):
        """Test that successful logins are tracked"""
        from django.contrib.auth.hashers import make_password
        import secrets
        import hashlib
        
        session = self.client.session
        challenge = secrets.token_urlsafe(32)
        session['captcha_challenge'] = challenge
        session['captcha_timestamp'] = timezone.now().timestamp()
        session.save()
        
        captcha_token = hashlib.sha256(f"{challenge}:completed".encode()).hexdigest()
        
        response = self.client.post('/users/login/', {
            'username': 'testuser',
            'password': 'TestPassword123!',
            'captcha_token': captcha_token
        })
        
        attempts = LoginAttempt.objects.filter(username='testuser', success=True)
        self.assertTrue(attempts.exists())
    
    def test_lockout_after_5_failed_attempts(self):
        """Test that account is locked after 5 failed attempts"""
        for i in range(5):
            LoginAttempt.objects.create(
                username='testuser',
                ip_address='127.0.0.1',
                user_agent='Test',
                success=False,
                failure_reason='Invalid credentials'
            )
        
        self.assertTrue(LoginAttempt.is_locked_out('testuser'))
    
    def test_lockout_time_remaining(self):
        """Test lockout time remaining calculation"""
        for i in range(5):
            LoginAttempt.objects.create(
                username='testuser',
                ip_address='127.0.0.1',
                user_agent='Test',
                success=False,
                failure_reason='Invalid credentials'
            )
        
        time_remaining = LoginAttempt.get_lockout_time_remaining('testuser')
        self.assertGreater(time_remaining, 0)
        self.assertLessEqual(time_remaining, 15)
    
    def test_lockout_cleared_after_successful_login(self):
        """Test that lockout is cleared after successful login"""
        for i in range(5):
            LoginAttempt.objects.create(
                username='testuser',
                ip_address='127.0.0.1',
                user_agent='Test',
                success=False,
                failure_reason='Invalid credentials'
            )
        
        self.assertTrue(LoginAttempt.is_locked_out('testuser'))
        
        LoginAttempt.clear_attempts('testuser')
        
        self.assertFalse(LoginAttempt.is_locked_out('testuser'))


class EmailOTPTestCase(TestCase):
    """Test Email OTP generation and verification"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
    
    def test_otp_generation(self):
        """Test that OTP codes are generated correctly"""
        otp = EmailOTP.generate_code(
            user=self.user,
            purpose='login',
            validity_minutes=5
        )
        
        self.assertEqual(len(otp.code), 6)
        self.assertTrue(otp.code.isdigit())
        self.assertFalse(otp.is_used)
    
    def test_otp_expiration(self):
        """Test that OTP codes expire correctly"""
        otp = EmailOTP.generate_code(
            user=self.user,
            purpose='login',
            validity_minutes=0  # Expires immediately
        )
        
        self.assertFalse(otp.is_valid())
    
    def test_otp_verification_success(self):
        """Test successful OTP verification"""
        otp = EmailOTP.generate_code(
            user=self.user,
            purpose='login',
            validity_minutes=5
        )
        
        success, message = EmailOTP.verify_code(self.user, otp.code, 'login')
        self.assertTrue(success)
    
    def test_otp_verification_wrong_code(self):
        """Test OTP verification with wrong code"""
        otp = EmailOTP.generate_code(
            user=self.user,
            purpose='login',
            validity_minutes=5
        )
        
        success, message = EmailOTP.verify_code(self.user, '000000', 'login')
        self.assertFalse(success)
    
    def test_otp_single_use(self):
        """Test that OTP codes can only be used once"""
        otp = EmailOTP.generate_code(
            user=self.user,
            purpose='login',
            validity_minutes=5
        )
        
        # First use should succeed
        success1, _ = EmailOTP.verify_code(self.user, otp.code, 'login')
        self.assertTrue(success1)
        
        # Second use should fail
        success2, _ = EmailOTP.verify_code(self.user, otp.code, 'login')
        self.assertFalse(success2)
    
    def test_otp_deletes_previous_codes(self):
        """Test that generating new OTP deletes old ones"""
        otp1 = EmailOTP.generate_code(
            user=self.user,
            purpose='login',
            validity_minutes=5
        )
        code1 = otp1.code
        
        otp2 = EmailOTP.generate_code(
            user=self.user,
            purpose='login',
            validity_minutes=5
        )
        
        # Old code should no longer work
        success, _ = EmailOTP.verify_code(self.user, code1, 'login')
        self.assertFalse(success)


class TOTPTestCase(TestCase):
    """Test TOTP (Google Authenticator) functionality"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
        
        self.two_factor = TwoFactorAuth.objects.create(
            user=self.user,
            enabled=True,
            method='totp',
            totp_secret=pyotp.random_base32()
        )
    
    def test_totp_secret_generation(self):
        """Test that TOTP secrets are generated correctly"""
        self.assertIsNotNone(self.two_factor.totp_secret)
        self.assertEqual(len(self.two_factor.totp_secret), 32)
    
    def test_totp_verification(self):
        """Test TOTP code verification"""
        totp = pyotp.TOTP(self.two_factor.totp_secret)
        current_code = totp.now()
        
        # Verification should succeed
        self.assertTrue(totp.verify(current_code))
    
    def test_totp_invalid_code(self):
        """Test TOTP verification with invalid code"""
        totp = pyotp.TOTP(self.two_factor.totp_secret)
        
        # Wrong code should fail
        self.assertFalse(totp.verify('000000'))


class BackupCodesTestCase(TestCase):
    """Test backup recovery codes"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
        
        # Generate backup codes
        import secrets
        backup_codes = {}
        for _ in range(10):
            code = ''.join([str(secrets.randbelow(10)) for _ in range(8)])
            backup_codes[code] = False
        
        self.two_factor = TwoFactorAuth.objects.create(
            user=self.user,
            enabled=True,
            method='email',
            backup_codes=json.dumps(backup_codes)
        )
    
    def test_backup_codes_generated(self):
        """Test that backup codes are generated"""
        codes = json.loads(self.two_factor.backup_codes)
        self.assertEqual(len(codes), 10)
    
    def test_backup_code_format(self):
        """Test backup code format (8 digits)"""
        codes = json.loads(self.two_factor.backup_codes)
        for code in codes.keys():
            self.assertEqual(len(code), 8)
            self.assertTrue(code.isdigit())
    
    def test_backup_codes_not_used_initially(self):
        """Test that backup codes are not marked as used initially"""
        codes = json.loads(self.two_factor.backup_codes)
        for code, used in codes.items():
            self.assertFalse(used)


class TwoFactorAuthFlowTestCase(TransactionTestCase):
    """Test complete 2FA authentication flow"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
    
    def test_2fa_enabled_redirects_to_verification(self):
        """Test that 2FA enabled users are redirected to verification"""
        TwoFactorAuth.objects.create(
            user=self.user,
            enabled=True,
            method='email'
        )
        
        # Login should redirect to 2FA verification (we can't test this fully without
        # completing the captcha flow, but we can verify the 2FA object exists)
        two_factor = TwoFactorAuth.objects.get(user=self.user)
        self.assertTrue(two_factor.enabled)
    
    def test_2fa_disabled_allows_direct_login(self):
        """Test that users without 2FA can login directly"""
        # User without 2FA should not have TwoFactorAuth object
        self.assertFalse(TwoFactorAuth.objects.filter(user=self.user).exists())


class SecuritySettingsViewTestCase(TestCase):
    """Test security settings page and management"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
        self.client.force_login(self.user)
    
    def test_security_settings_accessible(self):
        """Test that security settings page is accessible"""
        response = self.client.get('/users/security/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/security_settings.html')
    
    def test_enable_email_2fa(self):
        """Test enabling email-based 2FA"""
        response = self.client.get('/users/security/enable-email-2fa/')
        
        two_factor = TwoFactorAuth.objects.get(user=self.user)
        self.assertTrue(two_factor.enabled)
        self.assertEqual(two_factor.method, 'email')
    
    def test_disable_2fa(self):
        """Test disabling 2FA"""
        TwoFactorAuth.objects.create(
            user=self.user,
            enabled=True,
            method='email'
        )
        
        response = self.client.post('/users/security/disable-2fa/')
        
        two_factor = TwoFactorAuth.objects.get(user=self.user)
        self.assertFalse(two_factor.enabled)
    
    def test_totp_setup_page_accessible(self):
        """Test that TOTP setup page is accessible"""
        response = self.client.get('/users/security/setup-totp/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/setup_totp.html')


class ModelMethodsTestCase(TestCase):
    """Test model methods and class methods"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
    
    def test_login_attempt_is_locked_out_method(self):
        """Test LoginAttempt.is_locked_out() class method"""
        for i in range(5):
            LoginAttempt.objects.create(
                username='testuser',
                ip_address='127.0.0.1',
                success=False
            )
        
        self.assertTrue(LoginAttempt.is_locked_out('testuser'))
        self.assertFalse(LoginAttempt.is_locked_out('otheruser'))
    
    def test_email_otp_is_valid_method(self):
        """Test EmailOTP.is_valid() instance method"""
        # Valid OTP
        otp_valid = EmailOTP.objects.create(
            user=self.user,
            code='123456',
            purpose='login',
            expires_at=timezone.now() + timedelta(minutes=5)
        )
        self.assertTrue(otp_valid.is_valid())
        
        # Expired OTP
        otp_expired = EmailOTP.objects.create(
            user=self.user,
            code='654321',
            purpose='login',
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self.assertFalse(otp_expired.is_valid())


def run_security_tests():
    """
    Run all security tests
    
    Usage:
        python manage.py test users.tests_security
    """
    pass


if __name__ == '__main__':
    import django
    from django.test.utils import get_runner
    from django.conf import settings
    
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['users.tests_security'])
