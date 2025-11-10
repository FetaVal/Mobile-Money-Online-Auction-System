from django.core.management.base import BaseCommand
from django.db import transaction
from payments.models import Payment
from auctions.models import Item, CartItem
from users.models import Wallet, WalletTransaction
from decimal import Decimal

class Command(BaseCommand):
    help = 'Credit seller wallets for all completed sales that haven\'t been credited yet'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be credited without actually crediting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        completed_payments = Payment.objects.filter(status='completed').select_related('user')
        
        total_payments = 0
        total_sellers_credited = 0
        total_amount = Decimal('0.00')
        errors = []
        
        for payment in completed_payments:
            total_payments += 1
            cart_item_ids = payment.metadata.get('cart_items', [])
            
            if not cart_item_ids:
                self.stdout.write(self.style.WARNING(
                    f'Payment {payment.payment_id} has no cart items in metadata'
                ))
                continue
            
            items = Item.objects.filter(id__in=cart_item_ids).select_related('seller')
            
            for item in items:
                seller = item.seller
                amount = item.current_price
                
                from django.db.models import Q
                existing_sale = WalletTransaction.objects.filter(
                    wallet__user=seller,
                    transaction_type='sale',
                    description__icontains=item.title
                ).filter(description__icontains=payment.user.username).exists()
                
                if existing_sale:
                    self.stdout.write(
                        f'  ✓ Seller {seller.username} already credited for "{item.title}"'
                    )
                    continue
                
                if dry_run:
                    self.stdout.write(self.style.SUCCESS(
                        f'  [DRY RUN] Would credit {seller.username}: UGX {amount} for "{item.title}"'
                    ))
                    total_sellers_credited += 1
                    total_amount += amount
                else:
                    try:
                        with transaction.atomic():
                            wallet, created = Wallet.objects.get_or_create(user=seller)
                            
                            wallet.deposit(
                                amount=amount,
                                description=f'Sale of "{item.title}" to {payment.user.username} (Retroactive)',
                                transaction_type='sale',
                                payment_method=payment.payment_method
                            )
                            
                            if item.status != 'sold':
                                item.winner = payment.user
                                item.status = 'sold'
                                item.save(update_fields=['winner', 'status'])
                            
                            total_sellers_credited += 1
                            total_amount += amount
                            
                            self.stdout.write(self.style.SUCCESS(
                                f'  ✓ Credited {seller.username}: UGX {amount} for "{item.title}"'
                            ))
                    except Exception as e:
                        error_msg = f'Error crediting {seller.username} for "{item.title}": {str(e)}'
                        errors.append(error_msg)
                        self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
        
        self.stdout.write(self.style.SUCCESS(f'\n{"=" * 60}'))
        self.stdout.write(self.style.SUCCESS(f'SUMMARY'))
        self.stdout.write(self.style.SUCCESS(f'{"=" * 60}'))
        self.stdout.write(f'Total payments processed: {total_payments}')
        self.stdout.write(f'Sellers credited: {total_sellers_credited}')
        self.stdout.write(f'Total amount credited: UGX {total_amount:,.2f}')
        
        if errors:
            self.stdout.write(self.style.ERROR(f'\nErrors: {len(errors)}'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nThis was a DRY RUN. Run without --dry-run to actually credit sellers.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Successfully credited {total_sellers_credited} sales!'))
