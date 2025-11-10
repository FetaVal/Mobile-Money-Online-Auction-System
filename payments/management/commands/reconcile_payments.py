"""
Django management command for payment reconciliation

Run via cron: 0 2 * * * python manage.py reconcile_payments
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from decimal import Decimal
from payments.models import Payment
from auctions.models import TransactionLog
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Reconcile unsettled payments with payment providers'

    def handle(self, *args, **options):
        self.stdout.write("Starting payment reconciliation...")
        
        stats = {
            'total_checked': 0,
            'marked_failed': 0,
            'already_settled': 0
        }
        
        # Find pending payments older than 1 hour
        cutoff_time = timezone.now() - timedelta(hours=1)
        stale_payments = Payment.objects.filter(
            status='pending',
            created_at__lt=cutoff_time
        ).select_related('user')
        
        stats['total_checked'] = stale_payments.count()
        
        for payment in stale_payments:
            try:
                with transaction.atomic():
                    # Lock payment row
                    payment = Payment.objects.select_for_update().get(id=payment.id)
                    
                    if payment.status != 'pending':
                        stats['already_settled'] += 1
                        continue
                    
                    # Mark as failed
                    age = timezone.now() - payment.created_at
                    payment.status = 'failed'
                    payment.save()
                    
                    stats['marked_failed'] += 1
                    
                    # Log to TransactionLog
                    TransactionLog.objects.create(
                        transaction_type='payment_reconciliation',
                        user=payment.user,
                        data={
                            'payment_id': str(payment.payment_id),
                            'old_status': 'pending',
                            'new_status': 'failed',
                            'reason': 'stale_pending_payment',
                            'age_hours': age.total_seconds() / 3600
                        }
                    )
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error reconciling payment {payment.payment_id}: {e}"))
        
        self.stdout.write(self.style.SUCCESS(
            f"Reconciliation complete: {stats['total_checked']} checked, "
            f"{stats['marked_failed']} marked failed, "
            f"{stats['already_settled']} already settled"
        ))
