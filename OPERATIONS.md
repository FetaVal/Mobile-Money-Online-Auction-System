# AuctionHub - Operational Runbook

## Overview

This runbook provides step-by-step procedures for common operational tasks and incident response.

---

## Table of Contents

1. [System Health Monitoring](#system-health-monitoring)
2. [Common Operational Tasks](#common-operational-tasks)
3. [Incident Response](#incident-response)
4. [Recovery Procedures](#recovery-procedures)
5. [Maintenance Windows](#maintenance-windows)

---

## System Health Monitoring

### Key Metrics to Monitor

| Metric | Normal Range | Alert Threshold | Tool |
|--------|--------------|-----------------|------|
| Response Time | <500ms | >2s | Application logs |
| Error Rate | <0.1% | >1% | Error tracking |
| WebSocket Connections | 0-1000 | >5000 | Redis monitor |
| Redis Memory | <80% | >90% | Redis INFO |
| Database Connections | <50 | >80 | DB monitoring |
| Fraud Alert Rate | 1-5% | >10% | Admin dashboard |

### Health Check Endpoints

```bash
# Django health
curl http://localhost:5000/

# Redis health
redis-cli ping
# Expected: PONG

# Database health
python manage.py dbshell
# Should connect successfully
```

---

## Common Operational Tasks

### 1. Redis Down - What to Do

**Symptoms**:
- WebSocket connections failing
- Cache errors in logs
- "Redis unavailable, using LocMemCache fallback" message

**Impact**:
- Real-time bidding disabled (WebSockets down)
- Rate limiting falls back to in-memory (not distributed)
- Cache falls back to LocMemCache

**Resolution**:

```bash
# Check Redis status
systemctl status redis

# Restart Redis
sudo systemctl restart redis

# Verify Redis is running
redis-cli ping

# Check Django logs for reconnection
tail -f /var/log/django/app.log

# Restart Django/Daphne to reconnect
python manage.py runserver  # or
daphne auction_system.asgi:application
```

**Prevention**:
- Set up Redis monitoring and alerting
- Configure Redis persistence (AOF)
- Set up Redis replication for HA

---

### 2. Payment Webhook Callback Backlog

**Symptoms**:
- Payments stuck in "pending" status
- Users reporting completed payments not reflected
- TransactionLog shows missing webhook events

**Diagnosis**:

```bash
# Check pending payments older than 1 hour
python manage.py shell
>>> from payments.models import Payment
>>> from django.utils import timezone
>>> from datetime import timedelta
>>> cutoff = timezone.now() - timedelta(hours=1)
>>> stale = Payment.objects.filter(status='pending', created_at__lt=cutoff)
>>> print(f"Stale payments: {stale.count()}")
```

**Manual Resolution**:

```bash
# Run reconciliation management command manually
python manage.py reconcile_payments

# This will:
# 1. Find all pending payments older than 1 hour
# 2. Mark them as failed
# 3. Log reconciliation to TransactionLog
# 4. Report statistics (total checked, marked failed, already settled)
```

**Query Payment Provider**:

```python
# Flutterwave
import requests
tx_ref = "payment_id_here"
url = f"https://api.flutterwave.com/v3/transactions/verify_by_reference?tx_ref={tx_ref}"
headers = {"Authorization": f"Bearer {FLUTTERWAVE_SECRET_KEY}"}
response = requests.get(url, headers=headers)
print(response.json())

# Update payment manually if needed
payment = Payment.objects.get(payment_id=tx_ref)
payment.status = 'completed'
payment.save()
```

---

### 3. Transaction Chain Verification

**Purpose**: Verify blockchain-style transaction log integrity

**Procedure**:

```python
python manage.py shell

from auctions.models import TransactionLog
import hashlib

def verify_transaction_chain():
    """Verify all transaction hashes match"""
    transactions = TransactionLog.objects.all().order_by('id')
    
    errors = []
    for i, tx in enumerate(transactions):
        # Recalculate hash
        data = f"{tx.previous_hash}{tx.transaction_type}{tx.timestamp}{tx.data}"
        expected_hash = hashlib.sha256(data.encode()).hexdigest()
        
        if tx.transaction_hash != expected_hash:
            errors.append({
                'id': tx.id,
                'expected': expected_hash,
                'actual': tx.transaction_hash,
                'type': tx.transaction_type
            })
    
    if errors:
        print(f"⚠️  Found {len(errors)} hash mismatches:")
        for err in errors:
            print(f"  TX #{err['id']}: {err['type']}")
            print(f"    Expected: {err['expected'][:16]}...")
            print(f"    Actual:   {err['actual'][:16]}...")
    else:
        print(f"✓ All {transactions.count()} transaction hashes verified")
    
    return len(errors) == 0

# Run verification
verify_transaction_chain()
```

**If Tampering Detected**:
1. Identify affected transactions
2. Check database audit logs
3. Review admin access logs
4. Report to security team
5. Restore from backup if necessary

---

### 4. High Fraud Alert Volume

**Symptoms**:
- Fraud alert dashboard showing >10% fraud rate
- Many users flagged simultaneously
- Unusual bidding patterns

**Immediate Actions**:

```python
# Check recent alerts
python manage.py shell

from auctions.models import FraudAlert
from django.utils import timezone
from datetime import timedelta

recent = timezone.now() - timedelta(hours=1)
alerts = FraudAlert.objects.filter(created_at__gte=recent)

# Group by type
from django.db.models import Count
alert_summary = alerts.values('alert_type').annotate(count=Count('id'))
for item in alert_summary:
    print(f"{item['alert_type']}: {item['count']}")

# Check if specific attack pattern
rapid_bidding = alerts.filter(alert_type='rapid_bidding').count()
if rapid_bidding > 50:
    print("⚠️  Possible bot attack detected")
```

**Mitigation**:

```bash
# Temporarily tighten rate limits
# Edit users/rate_limiting.py
# Change: ('/place_bid/', 10, 60)
# To:     ('/place_bid/', 5, 60)

# Restart server
systemctl restart django

# Or enable stricter fraud detection
python manage.py shell
>>> from django.conf import settings
>>> # Adjust fraud detection thresholds in code
```

---

### 5. Database Migration Issues

**Before Migration**:

```bash
# Always backup before migrations
pg_dump auctionhub > backup_$(date +%Y%m%d_%H%M%S).sql

# Or with Django
python manage.py dumpdata > backup_$(date +%Y%m%d_%H%M%S).json
```

**Safe Migration**:

```bash
# Check for issues first
python manage.py makemigrations --dry-run
python manage.py migrate --plan

# Apply migrations
python manage.py migrate

# If error occurs, rollback
python manage.py migrate auctions <previous_migration_number>
```

**Recovery from Failed Migration**:

```bash
# Restore database
psql auctionhub < backup_20251108_120000.sql

# Or Django fixtures
python manage.py loaddata backup_20251108_120000.json

# Mark migrations as applied without running
python manage.py migrate --fake auctions <migration_number>
```

---

### 6. Session Management

**Clear expired sessions**:

```bash
# Django command
python manage.py clearsessions

# Or via cron (weekly)
0 3 * * 0 /path/to/venv/bin/python /path/to/manage.py clearsessions

# Payment reconciliation (daily at 2 AM)
0 2 * * * /path/to/venv/bin/python /path/to/manage.py reconcile_payments
```

**Force logout all users** (security incident):

```python
from django.contrib.sessions.models import Session
Session.objects.all().delete()
```

---

### 7. Static Files Not Loading

**Symptoms**:
- CSS/JS missing (404 errors)
- Images not displaying
- No styling on website

**Fix**:

```bash
# Collect static files
python manage.py collectstatic --noinput

# Check static file configuration
python manage.py findstatic bootstrap.css

# Verify settings
python manage.py shell
>>> from django.conf import settings
>>> print(settings.STATIC_URL)
>>> print(settings.STATIC_ROOT)
>>> print(settings.STATICFILES_DIRS)

# In production with Nginx
# Check nginx.conf for static file mapping
location /static/ {
    alias /path/to/staticfiles/;
}
```

---

## Incident Response

### Severity Levels

| Level | Definition | Response Time | Example |
|-------|------------|---------------|---------|
| P1 (Critical) | Service down | 15 minutes | Database crashed |
| P2 (High) | Major feature broken | 1 hour | Payments failing |
| P3 (Medium) | Minor feature issue | 4 hours | Email not sending |
| P4 (Low) | Cosmetic issue | 24 hours | Button misalignment |

### P1: Service Down

**Checklist**:
1. ☐ Alert team immediately
2. ☐ Check server status: `systemctl status django`
3. ☐ Check logs: `tail -f /var/log/django/error.log`
4. ☐ Check dependencies: Redis, Database
5. ☐ Restart services if needed
6. ☐ Monitor recovery
7. ☐ Document incident

**Common Causes**:
- Out of memory
- Database connection pool exhausted
- Redis connection timeout
- Disk full
- Python exceptions

---

### P2: Payment System Failure

**Symptoms**:
- All payment methods returning errors
- Webhook verification failing
- Payment status not updating

**Procedure**:

```bash
# 1. Check payment provider status pages
# - Flutterwave: status.flutterwave.com
# - Stripe: status.stripe.com
# - PayPal: status.paypal.com

# 2. Test webhook endpoints
curl -X POST http://localhost:5000/payments/webhook/stripe/ \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'

# 3. Check webhook secrets
python manage.py shell
>>> from decouple import config
>>> print("FLUTTERWAVE_SECRET_HASH:", config('FLUTTERWAVE_SECRET_HASH', default='NOT_SET'))
>>> print("STRIPE_WEBHOOK_SECRET:", config('STRIPE_WEBHOOK_SECRET', default='NOT_SET'))

# 4. Verify webhook URLs registered with providers
# Flutterwave: Dashboard > Settings > Webhooks
# Stripe: Dashboard > Developers > Webhooks
# PayPal: Developer Dashboard > Apps > Webhooks
```

---

### P3: Fraud Detection Not Working

**Symptoms**:
- No fraud alerts being generated
- Known fraudulent activity not flagged

**Diagnosis**:

```python
from auctions.fraud_detection import FraudDetectionService

# Test fraud detection
service = FraudDetectionService()

# Create test bid (rapid bidding)
from auctions.models import Bid, Item
from django.contrib.auth.models import User

item = Item.objects.first()
user = User.objects.first()

test_bid = Bid(item=item, bidder=user, amount=item.current_price + 10000)
alerts = service.analyze_bid(test_bid)

if not alerts:
    print("⚠️  Fraud detection not generating alerts")
else:
    print(f"✓ Fraud detection working: {len(alerts)} alerts")
```

---

## Recovery Procedures

### Database Backup & Restore

**Automated Backups** (setup):

```bash
# Cron job for daily backups
0 2 * * * pg_dump auctionhub > /backups/auctionhub_$(date +\%Y\%m\%d).sql

# Keep only last 7 days
0 3 * * * find /backups -name "auctionhub_*.sql" -mtime +7 -delete
```

**Manual Backup**:

```bash
# PostgreSQL
pg_dump auctionhub > backup.sql

# MySQL
mysqldump -u root -p auctionhub > backup.sql

# SQLite
cp db.sqlite3 db_backup_$(date +%Y%m%d).sqlite3
```

**Restore**:

```bash
# PostgreSQL
psql auctionhub < backup.sql

# MySQL
mysql -u root -p auctionhub < backup.sql

# SQLite
cp db_backup_20251108.sqlite3 db.sqlite3
```

---

### Redis Data Recovery

**Backup Redis**:

```bash
# Trigger save
redis-cli BGSAVE

# Copy RDB file
cp /var/lib/redis/dump.rdb /backups/redis_$(date +%Y%m%d).rdb
```

**Restore Redis**:

```bash
# Stop Redis
systemctl stop redis

# Replace RDB file
cp /backups/redis_20251108.rdb /var/lib/redis/dump.rdb

# Start Redis
systemctl start redis
```

---

## Maintenance Windows

### Recommended Maintenance Schedule

| Task | Frequency | Duration | Best Time |
|------|-----------|----------|-----------|
| Security updates | Weekly | 30 min | Sunday 2am |
| Database optimization | Monthly | 1 hour | 1st Sunday 2am |
| Log rotation | Daily | 5 min | Automated |
| Fraud model tuning | Quarterly | 2 hours | Planned |
| Dependency updates | Monthly | 1 hour | Planned |

### Pre-Maintenance Checklist

```bash
# 1. Notify users (if user-facing)
# 2. Backup database
pg_dump auctionhub > pre_maintenance_backup.sql

# 3. Document current state
python manage.py shell
>>> from auctions.models import Item
>>> print(f"Active auctions: {Item.objects.filter(status='active').count()}")

# 4. Put site in maintenance mode (optional)
# Create static maintenance.html and serve via Nginx

# 5. Stop services
systemctl stop django
systemctl stop daphne
```

### Post-Maintenance Checklist

```bash
# 1. Start services
systemctl start redis
systemctl start django
systemctl start daphne

# 2. Verify health
curl http://localhost:5000/
redis-cli ping

# 3. Check logs
tail -n 50 /var/log/django/app.log

# 4. Test critical paths
# - Login
# - Place bid
# - Make payment

# 5. Monitor for 30 minutes
# - Check error rates
# - Verify WebSocket connections
# - Monitor fraud alerts
```

---

## Monitoring & Alerts

### Log Locations

```
/var/log/django/app.log         - Application logs
/var/log/django/error.log       - Error logs
/var/log/django/fraud.log       - Fraud detection logs
/var/log/nginx/access.log       - Nginx access
/var/log/redis/redis-server.log - Redis logs
```

### Useful Log Commands

```bash
# Real-time error monitoring
tail -f /var/log/django/error.log

# Count errors in last hour
grep -c "ERROR" /var/log/django/error.log | tail -100

# Find payment failures
grep "payment.*failed" /var/log/django/app.log

# Monitor fraud alerts
grep "fraud" /var/log/django/app.log | tail -20

# WebSocket connection issues
grep "WebSocket" /var/log/django/app.log | grep -i "error"
```

---

## Emergency Contacts

**On-Call Rotation**: [Define your on-call schedule]

**Escalation Path**:
1. On-call engineer
2. Technical lead
3. CTO / Engineering manager

**External Contacts**:
- Flutterwave Support: support@flutterwave.com
- Stripe Support: support@stripe.com
- PayPal Support: [Merchant support portal]
- Hosting Provider: [Your hosting support]

---

## Quick Reference

### Django Management Commands

```bash
# Create superuser
python manage.py createsuperuser

# Payment reconciliation
python manage.py reconcile_payments

# Check for issues
python manage.py check

# Database shell
python manage.py dbshell

# Python shell
python manage.py shell

# Clear cache
python manage.py shell
>>> from django.core.cache import cache
>>> cache.clear()
```

---

**Last Updated**: November 8, 2025  
**Maintained By**: AuctionHub Operations Team  
**Review Frequency**: Quarterly
