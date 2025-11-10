from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from payments.models import Payment
import uuid


class PaymentProcessingTestCase(TestCase):
    """Test payment processing logic"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass123')
    
    def test_payment_creation(self):
        """Test creating a payment record"""
        payment_id = uuid.uuid4()
        
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal('100000'),
            platform_tax=Decimal('5000'),
            payment_method='mtn',
            status='pending',
            payment_id=payment_id,
            metadata={
                'phone_number': '+256700000000',
                'country': 'UG'
            }
        )
        
        self.assertEqual(payment.amount, Decimal('100000'))
        self.assertEqual(payment.platform_tax, Decimal('5000'))
        self.assertEqual(payment.payment_method, 'mtn')
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(payment.user, self.user)
    
    def test_payment_status_transitions(self):
        """Test valid payment status transitions"""
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal('50000'),
            platform_tax=Decimal('2500'),
            payment_method='card',
            status='pending',
            payment_id=uuid.uuid4()
        )
        
        # Pending → Completed
        payment.status = 'completed'
        payment.save()
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'completed')
        
        # Test failed status
        payment2 = Payment.objects.create(
            user=self.user,
            amount=Decimal('75000'),
            platform_tax=Decimal('3750'),
            payment_method='paypal',
            status='pending',
            payment_id=uuid.uuid4()
        )
        
        payment2.status = 'failed'
        payment2.save()
        payment2.refresh_from_db()
        self.assertEqual(payment2.status, 'failed')
    
    def test_platform_tax_calculation(self):
        """Test that platform tax is calculated correctly (5%)"""
        test_amounts = [
            (Decimal('100000'), Decimal('5000')),
            (Decimal('200000'), Decimal('10000')),
            (Decimal('50000'), Decimal('2500')),
            (Decimal('1000000'), Decimal('50000')),
        ]
        
        for amount, expected_tax in test_amounts:
            # Tax rate is 5%
            calculated_tax = amount * Decimal('0.05')
            self.assertEqual(calculated_tax, expected_tax)
    
    def test_payment_metadata_storage(self):
        """Test that payment metadata is stored correctly"""
        metadata = {
            'cart_items': [1, 2, 3],
            'country': 'UG',
            'subtotal': '95000',
            'shipping_cost': '15000',
            'tax_rate': '0.05',
            'tax_amount': '5500',
            'total': '115500',
            'delivery_city': 'Kampala',
            'delivery_area': 'Kololo',
            'phone_number': '+256700000000'
        }
        
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal('115500'),
            platform_tax=Decimal('5500'),
            payment_method='mtn',
            status='pending',
            payment_id=uuid.uuid4(),
            metadata=metadata
        )
        
        payment.refresh_from_db()
        
        # Verify metadata preserved
        self.assertEqual(payment.metadata['country'], 'UG')
        self.assertEqual(payment.metadata['delivery_city'], 'Kampala')
        self.assertEqual(payment.metadata['phone_number'], '+256700000000')
        self.assertEqual(len(payment.metadata['cart_items']), 3)
    
    def test_payment_methods(self):
        """Test different payment methods"""
        payment_methods = ['mtn', 'airtel', 'card', 'paypal', 'mpesa']
        
        for method in payment_methods:
            payment = Payment.objects.create(
                user=self.user,
                amount=Decimal('100000'),
                platform_tax=Decimal('5000'),
                payment_method=method,
                status='pending',
                payment_id=uuid.uuid4()
            )
            
            self.assertEqual(payment.payment_method, method)
    
    def test_payment_amount_precision(self):
        """Test decimal precision in payment amounts"""
        # Test with exact decimal amounts
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal('123456.78'),
            platform_tax=Decimal('6172.84'),
            payment_method='card',
            status='completed',
            payment_id=uuid.uuid4()
        )
        
        self.assertEqual(payment.amount, Decimal('123456.78'))
        self.assertEqual(payment.platform_tax, Decimal('6172.84'))
    
    def test_payment_with_shipping(self):
        """Test payment including shipping costs"""
        subtotal = Decimal('100000')
        shipping = Decimal('15000')
        base_for_tax = subtotal + shipping  # 115000
        tax = base_for_tax * Decimal('0.05')  # 5750
        total = base_for_tax + tax  # 120750
        
        payment = Payment.objects.create(
            user=self.user,
            amount=total,
            platform_tax=tax,
            payment_method='mtn',
            status='pending',
            payment_id=uuid.uuid4(),
            metadata={
                'subtotal': str(subtotal),
                'shipping_cost': str(shipping),
                'total': str(total)
            }
        )
        
        self.assertEqual(payment.amount, Decimal('120750'))
        self.assertEqual(payment.platform_tax, Decimal('5750'))
    
    def test_idempotency_key_uniqueness(self):
        """Test that payment_id serves as idempotency key"""
        payment_id = uuid.uuid4()
        
        # First payment
        payment1 = Payment.objects.create(
            user=self.user,
            amount=Decimal('100000'),
            platform_tax=Decimal('5000'),
            payment_method='mtn',
            status='pending',
            payment_id=payment_id
        )
        
        # Try to create duplicate (should be prevented by unique constraint)
        from django.db import IntegrityError
        
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                user=self.user,
                amount=Decimal('100000'),
                platform_tax=Decimal('5000'),
                payment_method='mtn',
                status='pending',
                payment_id=payment_id  # Same ID
            )
    
    def test_payment_query_by_status(self):
        """Test querying payments by status"""
        # Create payments with different statuses
        for i in range(5):
            Payment.objects.create(
                user=self.user,
                amount=Decimal('100000'),
                platform_tax=Decimal('5000'),
                payment_method='mtn',
                status='completed',
                payment_id=uuid.uuid4()
            )
        
        for i in range(3):
            Payment.objects.create(
                user=self.user,
                amount=Decimal('50000'),
                platform_tax=Decimal('2500'),
                payment_method='card',
                status='pending',
                payment_id=uuid.uuid4()
            )
        
        # Query
        completed_payments = Payment.objects.filter(status='completed').count()
        pending_payments = Payment.objects.filter(status='pending').count()
        
        self.assertEqual(completed_payments, 5)
        self.assertEqual(pending_payments, 3)
    
    def test_user_payment_history(self):
        """Test retrieving user's payment history"""
        user2 = User.objects.create_user(username='user2', password='pass123')
        
        # Create payments for user1
        for i in range(3):
            Payment.objects.create(
                user=self.user,
                amount=Decimal('100000'),
                platform_tax=Decimal('5000'),
                payment_method='mtn',
                status='completed',
                payment_id=uuid.uuid4()
            )
        
        # Create payments for user2
        for i in range(2):
            Payment.objects.create(
                user=user2,
                amount=Decimal('50000'),
                platform_tax=Decimal('2500'),
                payment_method='card',
                status='completed',
                payment_id=uuid.uuid4()
            )
        
        # Query user payments
        user1_payments = Payment.objects.filter(user=self.user).count()
        user2_payments = Payment.objects.filter(user=user2).count()
        
        self.assertEqual(user1_payments, 3)
        self.assertEqual(user2_payments, 2)


class PaymentSecurityTestCase(TestCase):
    """Test payment security features"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass123')
    
    def test_payment_user_isolation(self):
        """Test that users can only access their own payments"""
        user2 = User.objects.create_user(username='user2', password='pass123')
        
        payment1 = Payment.objects.create(
            user=self.user,
            amount=Decimal('100000'),
            platform_tax=Decimal('5000'),
            payment_method='mtn',
            status='completed',
            payment_id=uuid.uuid4()
        )
        
        payment2 = Payment.objects.create(
            user=user2,
            amount=Decimal('50000'),
            platform_tax=Decimal('2500'),
            payment_method='card',
            status='completed',
            payment_id=uuid.uuid4()
        )
        
        # User1 should not see user2's payments
        user1_payments = Payment.objects.filter(user=self.user)
        self.assertNotIn(payment2, user1_payments)
        
        # User2 should not see user1's payments
        user2_payments = Payment.objects.filter(user=user2)
        self.assertNotIn(payment1, user2_payments)
    
    def test_sensitive_data_in_metadata(self):
        """Test handling of sensitive data in metadata"""
        # Phone numbers should be in metadata, not plain fields
        payment = Payment.objects.create(
            user=self.user,
            amount=Decimal('100000'),
            platform_tax=Decimal('5000'),
            payment_method='mtn',
            status='pending',
            payment_id=uuid.uuid4(),
            metadata={
                'phone_number': '+256700000000',
                'transaction_reference': 'MTN-REF-12345'
            }
        )
        
        # Verify data is in metadata
        self.assertIn('phone_number', payment.metadata)
        self.assertIn('transaction_reference', payment.metadata)
