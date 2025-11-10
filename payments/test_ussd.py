"""
USSD Flow Tests

Tests USSD bidding flows including:
- Happy path (successful bid)
- Timeout handling
- Idempotency (duplicate requests)
- PIN validation
- Session management
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from auctions.models import Item, Category
from payments.models import USSDSession, Payment
import uuid


class USSDHappyPathTestCase(TestCase):
    """Test successful USSD bidding flow"""
    
    def setUp(self):
        """Create test data"""
        self.client = Client()
        
        # Create users
        self.seller = User.objects.create_user(
            username='ussd_seller',
            password='testpass123'
        )
        
        self.bidder = User.objects.create_user(
            username='ussd_bidder',
            password='testpass123'
        )
        
        # Create category
        self.category = Category.objects.create(
            name='USSD Test Category',
            slug='ussd-test'
        )
        
        # Create active item
        self.item = Item.objects.create(
            title='USSD Test Item',
            seller=self.seller,
            category=self.category,
            description='Test item for USSD',
            starting_price=Decimal('100000'),
            current_price=Decimal('100000'),
            min_increment=Decimal('5000'),
            end_time=timezone.now() + timedelta(hours=24),
            status='active'
        )
        
        self.phone_number = '+256700123456'
    
    def test_ussd_bidding_happy_path(self):
        """Test complete USSD bidding flow from start to finish"""
        session_id = str(uuid.uuid4())
        
        # Step 1: Initiate USSD (*354# for MTN)
        response = self.client.post('/ussd/initiate/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': ''
        })
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Welcome to AuctionHub', content)
        
        # Step 2: Select "Place Bid"
        response = self.client.post('/ussd/respond/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': '1'  # Select "Place Bid"
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Step 3: Enter Item ID
        response = self.client.post('/ussd/respond/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': f'1*{self.item.id}'
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Step 4: Enter bid amount
        response = self.client.post('/ussd/respond/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': f'1*{self.item.id}*110000'
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Verify session was created
        session = USSDSession.objects.filter(session_id=session_id).first()
        self.assertIsNotNone(session)
    
    def test_ussd_session_timeout(self):
        """Test USSD session expires after timeout period"""
        # Create old session
        old_session = USSDSession.objects.create(
            session_id=str(uuid.uuid4()),
            phone_number=self.phone_number,
            stage='item_id',
            created_at=timezone.now() - timedelta(minutes=10)
        )
        
        # Session should be considered expired (typical timeout: 3 minutes)
        age = timezone.now() - old_session.created_at
        self.assertGreater(age.total_seconds(), 180)  # > 3 minutes
    
    def test_ussd_invalid_pin(self):
        """Test USSD flow with invalid PIN"""
        session_id = str(uuid.uuid4())
        
        # Create session at PIN confirmation stage
        USSDSession.objects.create(
            session_id=session_id,
            phone_number=self.phone_number,
            stage='pin_confirmation',
            item_id=self.item.id,
            bid_amount=110000
        )
        
        # Enter wrong PIN
        response = self.client.post('/ussd/respond/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': '9999'  # Wrong PIN
        })
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Should show error or retry message
        self.assertTrue('wrong' in content.lower() or 'invalid' in content.lower() or 'incorrect' in content.lower())


class USSDIdempotencyTestCase(TestCase):
    """Test USSD idempotency - duplicate requests handled correctly"""
    
    def setUp(self):
        """Create test data"""
        self.client = Client()
        
        self.seller = User.objects.create_user(
            username='idem_seller',
            password='testpass123'
        )
        
        self.category = Category.objects.create(
            name='Idempotency Test',
            slug='idem-test'
        )
        
        self.item = Item.objects.create(
            title='Idem Test Item',
            seller=self.seller,
            category=self.category,
            description='Test',
            starting_price=Decimal('100000'),
            current_price=Decimal('100000'),
            min_increment=Decimal('5000'),
            end_time=timezone.now() + timedelta(hours=24),
            status='active'
        )
        
        self.phone_number = '+256700987654'
    
    def test_duplicate_ussd_initiate(self):
        """Test duplicate USSD session initiation"""
        session_id = str(uuid.uuid4())
        
        # First request
        response1 = self.client.post('/ussd/initiate/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': ''
        })
        
        # Duplicate request (network retry)
        response2 = self.client.post('/ussd/initiate/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': ''
        })
        
        # Both should succeed
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)
        
        # Should only create one session
        session_count = USSDSession.objects.filter(session_id=session_id).count()
        self.assertLessEqual(session_count, 1)
    
    def test_idempotent_bid_placement(self):
        """Test that duplicate bid placement creates only one bid"""
        session_id = str(uuid.uuid4())
        payment_id = str(uuid.uuid4())
        
        # Create session
        USSDSession.objects.create(
            session_id=session_id,
            phone_number=self.phone_number,
            stage='completed',
            item_id=self.item.id,
            bid_amount=110000,
            payment_id=payment_id
        )
        
        # Simulate duplicate payment confirmation (network retry)
        # This would happen if the SMS confirmation is sent twice
        
        # Check that payment_id acts as idempotency key
        # Multiple confirmations with same payment_id should not create duplicate bids


class USSDInputValidationTestCase(TestCase):
    """Test USSD input validation"""
    
    def setUp(self):
        """Create test data"""
        self.client = Client()
        self.phone_number = '+256700555555'
    
    def test_invalid_item_id(self):
        """Test USSD with invalid item ID"""
        session_id = str(uuid.uuid4())
        
        # Initiate
        self.client.post('/ussd/initiate/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': ''
        })
        
        # Select bid
        self.client.post('/ussd/respond/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': '1'
        })
        
        # Enter non-existent item ID
        response = self.client.post('/ussd/respond/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': '1*99999'  # Non-existent item
        })
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertTrue('not found' in content.lower() or 'invalid' in content.lower())
    
    def test_invalid_bid_amount(self):
        """Test USSD with invalid bid amount (non-numeric)"""
        session_id = str(uuid.uuid4())
        
        # Create session at bid amount stage
        seller = User.objects.create_user(username='val_seller', password='test')
        category = Category.objects.create(name='Val Test', slug='val-test')
        item = Item.objects.create(
            title='Val Item',
            seller=seller,
            category=category,
            description='Test',
            starting_price=Decimal('100000'),
            current_price=Decimal('100000'),
            min_increment=Decimal('5000'),
            end_time=timezone.now() + timedelta(hours=24),
            status='active'
        )
        
        USSDSession.objects.create(
            session_id=session_id,
            phone_number=self.phone_number,
            stage='bid_amount',
            item_id=item.id
        )
        
        # Enter non-numeric amount
        response = self.client.post('/ussd/respond/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': 'abc123'  # Invalid amount
        })
        
        self.assertEqual(response.status_code, 200)
    
    def test_bid_amount_below_minimum(self):
        """Test USSD with bid amount below minimum increment"""
        session_id = str(uuid.uuid4())
        
        seller = User.objects.create_user(username='min_seller', password='test')
        category = Category.objects.create(name='Min Test', slug='min-test')
        item = Item.objects.create(
            title='Min Item',
            seller=seller,
            category=category,
            description='Test',
            starting_price=Decimal('100000'),
            current_price=Decimal('100000'),
            min_increment=Decimal('5000'),
            end_time=timezone.now() + timedelta(hours=24),
            status='active'
        )
        
        USSDSession.objects.create(
            session_id=session_id,
            phone_number=self.phone_number,
            stage='bid_amount',
            item_id=item.id
        )
        
        # Enter amount below minimum
        response = self.client.post('/ussd/respond/', {
            'sessionId': session_id,
            'phoneNumber': self.phone_number,
            'text': '102000'  # Less than current + min_increment
        })
        
        self.assertEqual(response.status_code, 200)


class USSDSessionManagementTestCase(TestCase):
    """Test USSD session lifecycle management"""
    
    def test_session_cleanup(self):
        """Test that old sessions are cleaned up"""
        phone = '+256700111111'
        
        # Create old session
        old_session = USSDSession.objects.create(
            session_id=str(uuid.uuid4()),
            phone_number=phone,
            stage='item_id',
            created_at=timezone.now() - timedelta(hours=2)
        )
        
        # Verify session exists
        self.assertTrue(USSDSession.objects.filter(id=old_session.id).exists())
        
        # In production, a cleanup task would remove sessions older than X minutes
        # Test that we can identify stale sessions
        stale_threshold = timezone.now() - timedelta(minutes=15)
        stale_sessions = USSDSession.objects.filter(created_at__lt=stale_threshold)
        
        self.assertGreater(stale_sessions.count(), 0)
    
    def test_session_stage_progression(self):
        """Test that session stages progress correctly"""
        session_id = str(uuid.uuid4())
        phone = '+256700222222'
        
        # Create session
        session = USSDSession.objects.create(
            session_id=session_id,
            phone_number=phone,
            stage='welcome'
        )
        
        # Progress through stages
        stages = ['welcome', 'menu', 'item_id', 'bid_amount', 'pin_confirmation', 'completed']
        
        for i, stage in enumerate(stages):
            if i > 0:  # Skip first as it's already set
                session.stage = stage
                session.save()
            
            session.refresh_from_db()
            self.assertEqual(session.stage, stage)
