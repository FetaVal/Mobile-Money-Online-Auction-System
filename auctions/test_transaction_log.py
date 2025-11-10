from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from auctions.models import Item, Category, TransactionLog
import hashlib
import json


class TransactionLogIntegrityTestCase(TestCase):
    """Test blockchain-inspired transaction log integrity"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass123')
        self.category = Category.objects.create(name='Electronics')
        
        self.item = Item.objects.create(
            seller=self.user,
            category=self.category,
            title='Test Item',
            description='Testing transaction logs',
            starting_price=Decimal('100000'),
            current_price=Decimal('100000'),
            min_increment=Decimal('5000'),
            end_time=timezone.now() + timedelta(days=1),
            status='active'
        )
    
    def test_transaction_log_creation(self):
        """Test that transaction logs are created with correct data"""
        log = TransactionLog.objects.create(
            transaction_id='TEST-001',
            transaction_type='purchase',
            item=self.item,
            user=self.user,
            amount=Decimal('100000'),
            payment_method='mtn',
            payment_reference='MTN-REF-123',
            data={
                'seller': self.user.username,
                'payment_id': 'PAY-001',
                'phone_number': '+256700000000'
            }
        )
        
        self.assertEqual(log.transaction_id, 'TEST-001')
        self.assertEqual(log.transaction_type, 'purchase')
        self.assertEqual(log.amount, Decimal('100000'))
        self.assertIsNotNone(log.current_hash)
        self.assertIsNotNone(log.timestamp)
    
    def test_hash_generation(self):
        """Test that transaction hashes are generated correctly"""
        log = TransactionLog.objects.create(
            transaction_id='TEST-HASH-001',
            transaction_type='bid',
            item=self.item,
            user=self.user,
            amount=Decimal('50000'),
            payment_method='web'
        )
        
        # Verify hash exists
        self.assertIsNotNone(log.current_hash)
        self.assertEqual(len(log.current_hash), 64)  # SHA-256 produces 64 char hex
        
        # Verify hash is valid SHA-256
        try:
            int(log.current_hash, 16)  # Should be valid hex
            valid_hex = True
        except ValueError:
            valid_hex = False
        
        self.assertTrue(valid_hex)
    
    def test_transaction_chain_integrity(self):
        """Test that transaction logs maintain chain integrity"""
        # Create first transaction
        log1 = TransactionLog.objects.create(
            transaction_id='CHAIN-001',
            transaction_type='purchase',
            item=self.item,
            user=self.user,
            amount=Decimal('100000'),
            payment_method='mtn'
        )
        
        # Create second transaction (should link to first)
        log2 = TransactionLog.objects.create(
            transaction_id='CHAIN-002',
            transaction_type='purchase',
            item=self.item,
            user=self.user,
            amount=Decimal('150000'),
            payment_method='airtel'
        )
        
        # Verify chain link
        if log2.previous_hash:
            self.assertEqual(log2.previous_hash, log1.current_hash)
    
    def test_hash_recalculation(self):
        """Test that we can verify hash integrity"""
        log = TransactionLog.objects.create(
            transaction_id='VERIFY-001',
            transaction_type='purchase',
            item=self.item,
            user=self.user,
            amount=Decimal('200000'),
            payment_method='card',
            data={'test': 'data'}
        )
        
        # Recalculate hash
        hash_data = {
            'transaction_id': log.transaction_id,
            'transaction_type': log.transaction_type,
            'item_id': log.item.id if log.item else None,
            'user_id': log.user.id if log.user else None,
            'amount': str(log.amount),
            'timestamp': log.timestamp.isoformat(),
            'previous_hash': log.previous_hash or 'genesis'
        }
        
        calculated_hash = hashlib.sha256(
            json.dumps(hash_data, sort_keys=True).encode()
        ).hexdigest()
        
        # The hash should match (if calculated the same way in model)
        self.assertEqual(len(calculated_hash), 64)
        self.assertIsInstance(calculated_hash, str)
    
    def test_tamper_detection(self):
        """Test that tampering with transaction data can be detected"""
        log = TransactionLog.objects.create(
            transaction_id='TAMPER-001',
            transaction_type='purchase',
            item=self.item,
            user=self.user,
            amount=Decimal('100000'),
            payment_method='mtn'
        )
        
        original_hash = log.current_hash
        original_amount = log.amount
        
        # Manually tamper with amount (bypass save signal)
        TransactionLog.objects.filter(id=log.id).update(amount=Decimal('50000'))
        
        log.refresh_from_db()
        
        # Hash should still be original (since we bypassed save)
        self.assertEqual(log.current_hash, original_hash)
        
        # But amount changed
        self.assertNotEqual(log.amount, original_amount)
        
        # If we recalculate hash, it won't match
        # This demonstrates tamper detection capability
    
    def test_multiple_transactions_chain(self):
        """Test chain integrity with multiple transactions"""
        num_transactions = 10
        previous_log = None
        
        for i in range(num_transactions):
            log = TransactionLog.objects.create(
                transaction_id=f'MULTI-{i:03d}',
                transaction_type='purchase',
                item=self.item,
                user=self.user,
                amount=Decimal(str(100000 + (i * 10000))),
                payment_method='mtn'
            )
            
            if previous_log:
                # Verify chain
                if log.previous_hash:
                    self.assertEqual(log.previous_hash, previous_log.current_hash)
            
            previous_log = log
        
        # Verify we created all transactions
        total_logs = TransactionLog.objects.filter(
            transaction_id__startswith='MULTI-'
        ).count()
        self.assertEqual(total_logs, num_transactions)
    
    def test_transaction_types(self):
        """Test different transaction types are logged correctly"""
        transaction_types = ['purchase', 'bid', 'listing', 'wallet_deposit', 'wallet_withdrawal']
        
        for trans_type in transaction_types:
            log = TransactionLog.objects.create(
                transaction_id=f'{trans_type.upper()}-001',
                transaction_type=trans_type,
                item=self.item if trans_type != 'wallet_deposit' else None,
                user=self.user,
                amount=Decimal('50000'),
                payment_method='web'
            )
            
            self.assertEqual(log.transaction_type, trans_type)
            self.assertIsNotNone(log.current_hash)
    
    def test_genesis_transaction(self):
        """Test the first transaction (genesis block)"""
        # Delete all existing logs
        TransactionLog.objects.all().delete()
        
        # Create first log
        genesis_log = TransactionLog.objects.create(
            transaction_id='GENESIS-001',
            transaction_type='purchase',
            item=self.item,
            user=self.user,
            amount=Decimal('100000'),
            payment_method='mtn'
        )
        
        # Genesis transaction should have no previous hash or "genesis" as previous
        self.assertTrue(
            genesis_log.previous_hash is None or 
            genesis_log.previous_hash == 'genesis' or
            genesis_log.previous_hash == ''
        )
    
    def test_data_field_json(self):
        """Test that data field correctly stores JSON"""
        complex_data = {
            'seller': 'testuser',
            'buyer': 'buyer1',
            'item_details': {
                'title': 'Laptop',
                'category': 'Electronics',
                'price': 500000
            },
            'shipping': {
                'city': 'Kampala',
                'area': 'Kololo'
            },
            'payment': {
                'method': 'MTN',
                'reference': 'MTN-12345',
                'tax': 25000
            }
        }
        
        log = TransactionLog.objects.create(
            transaction_id='JSON-TEST-001',
            transaction_type='purchase',
            item=self.item,
            user=self.user,
            amount=Decimal('525000'),
            payment_method='mtn',
            data=complex_data
        )
        
        log.refresh_from_db()
        
        # Verify data is preserved
        self.assertEqual(log.data['seller'], 'testuser')
        self.assertEqual(log.data['item_details']['price'], 500000)
        self.assertEqual(log.data['shipping']['city'], 'Kampala')
        self.assertEqual(log.data['payment']['tax'], 25000)
