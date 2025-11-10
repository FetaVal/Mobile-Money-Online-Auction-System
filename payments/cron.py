"""
Django-CRON jobs for payment reconciliation and monitoring

Runs daily to:
1. Reconcile unsettled payments with payment providers
2. Mark stale pending payments
3. Log discrepancies to TransactionLog
"""

from django_cron import CronJobBase, Schedule
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from decimal import Decimal
from .models import Payment
from auctions.models import TransactionLog
import logging

logger = logging.getLogger(__name__)


class ReconcilePaymentsCronJob(CronJobBase):
    """
    Daily payment reconciliation job
    
    Runs every 24 hours to:
    - Find pending payments older than 1 hour
    - Mark them as failed if not confirmed
    - Log discrepancies to TransactionLog for audit trail
    """
    
    RUN_EVERY_MINS = 60 * 24  # Run once daily
    
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'payments.reconcile_payments'  # Unique code
    
    def do(self):
        """Execute the reconciliation logic"""
        logger.info("Starting payment reconciliation job")
        
        reconciliation_stats = {
            'total_checked': 0,
            'marked_failed': 0,
            'already_settled': 0,
            'discrepancies': []
        }
        
        try:
            # Find pending payments older than 1 hour
            cutoff_time = timezone.now() - timedelta(hours=1)
            stale_payments = Payment.objects.filter(
                status='pending',
                created_at__lt=cutoff_time
            ).select_related('user')
            
            reconciliation_stats['total_checked'] = stale_payments.count()
            
            for payment in stale_payments:
                try:
                    self._reconcile_payment(payment, reconciliation_stats)
                except Exception as e:
                    logger.error(f"Error reconciling payment {payment.payment_id}: {e}")
                    reconciliation_stats['discrepancies'].append({
                        'payment_id': str(payment.payment_id),
                        'error': str(e)
                    })
            
            # Log reconciliation summary to TransactionLog
            self._log_reconciliation_summary(reconciliation_stats)
            
            logger.info(f"Payment reconciliation completed: {reconciliation_stats}")
            
        except Exception as e:
            logger.error(f"Payment reconciliation job failed: {e}")
            raise
    
    @transaction.atomic
    def _reconcile_payment(self, payment, stats):
        """
        Reconcile a single payment
        
        In production, this would query the payment provider's API
        to check actual payment status.
        """
        # Lock the payment row
        payment = Payment.objects.select_for_update().get(id=payment.id)
        
        # Check if payment was already settled
        if payment.status != 'pending':
            stats['already_settled'] += 1
            return
        
        # Calculate how long payment has been pending
        age = timezone.now() - payment.created_at
        
        # Mark as failed if pending for more than 1 hour
        # In production, query provider API first
        if age > timedelta(hours=1):
            old_status = payment.status
            payment.status = 'failed'
            payment.save()
            
            stats['marked_failed'] += 1
            
            # Log to TransactionLog for audit trail
            TransactionLog.objects.create(
                transaction_type='payment_reconciliation',
                user=payment.user,
                data={
                    'payment_id': str(payment.payment_id),
                    'old_status': old_status,
                    'new_status': 'failed',
                    'reason': 'stale_pending_payment',
                    'age_hours': age.total_seconds() / 3600,
                    'amount': str(payment.amount),
                    'method': payment.method
                }
            )
            
            logger.warning(f"Marked payment {payment.payment_id} as failed (age: {age})")
    
    def _log_reconciliation_summary(self, stats):
        """Log reconciliation summary to TransactionLog"""
        TransactionLog.objects.create(
            transaction_type='reconciliation_summary',
            user=None,  # System-level transaction
            data={
                'timestamp': timezone.now().isoformat(),
                'total_checked': stats['total_checked'],
                'marked_failed': stats['marked_failed'],
                'already_settled': stats['already_settled'],
                'discrepancies_count': len(stats['discrepancies']),
                'discrepancies': stats['discrepancies']
            }
        )


class MonitorUnconfirmedPaymentsCronJob(CronJobBase):
    """
    Hourly job to monitor and alert on unconfirmed payments
    
    Runs every hour to catch payment issues faster
    """
    
    RUN_EVERY_MINS = 60  # Run hourly
    
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'payments.monitor_unconfirmed'
    
    def do(self):
        """Check for unconfirmed payments and alert"""
        logger.info("Starting payment monitoring job")
        
        try:
            # Find payments pending for more than 10 minutes
            cutoff_time = timezone.now() - timedelta(minutes=10)
            unconfirmed = Payment.objects.filter(
                status='pending',
                created_at__lt=cutoff_time
            ).count()
            
            if unconfirmed > 0:
                logger.warning(f"Found {unconfirmed} unconfirmed payments older than 10 minutes")
                
                # Log to TransactionLog
                TransactionLog.objects.create(
                    transaction_type='payment_alert',
                    user=None,
                    data={
                        'alert_type': 'unconfirmed_payments',
                        'count': unconfirmed,
                        'threshold_minutes': 10,
                        'timestamp': timezone.now().isoformat()
                    }
                )
            
            logger.info(f"Payment monitoring completed: {unconfirmed} unconfirmed payments")
            
        except Exception as e:
            logger.error(f"Payment monitoring job failed: {e}")
            raise


class CleanupExpiredWebhookEventsCronJob(CronJobBase):
    """
    Daily job to clean up old webhook event IDs from cache
    
    Prevents memory bloat from replay protection tracking
    """
    
    RUN_EVERY_MINS = 60 * 24  # Run daily
    
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'payments.cleanup_webhook_events'
    
    def do(self):
        """
        Clean up expired webhook event IDs
        
        Note: Redis TTL handles this automatically, but this job
        logs the cleanup for audit purposes.
        """
        logger.info("Webhook event cleanup job executed")
        
        # Log to TransactionLog
        TransactionLog.objects.create(
            transaction_type='webhook_cleanup',
            user=None,
            data={
                'timestamp': timezone.now().isoformat(),
                'note': 'Webhook event IDs expire automatically via Redis TTL'
            }
        )
