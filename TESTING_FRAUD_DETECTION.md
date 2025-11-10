# Fraud Detection & Security Testing Guide

This guide shows you how to test all 15+ fraud detection methods, view alerts in the admin dashboard, and verify transaction logging security.

---

## 🎯 Quick Start

### 1. Access Admin Fraud Dashboard
- Login as admin: `http://your-replit-url/admin/login/`
- Navigate to: **Admin Dashboard** → **Fraud Alerts** tab
- Or direct URL: `http://your-replit-url/admin/fraud-alerts/`

### 2. View Fraud Alerts
The admin dashboard shows:
- **Total Alerts** - All fraud alerts detected
- **Critical Alerts** - Highest severity (red badges)
- **High Alerts** - High severity (orange badges)
- **Unresolved Alerts** - Alerts waiting for admin review
- **Charts** - Last 7 days fraud activity, alert types distribution

---

## 🧪 Testing Fraud Detection Methods

### Method 1: Rapid Bidding Detection (Bot Activity)
**What it detects:** Users placing >10 bids within 5 minutes

**How to test:**
```python
# Run in Django shell: python manage.py shell
from auctions.models import Item, Bid, User
from decimal import Decimal
from django.utils import timezone

# Get or create test user
user = User.objects.get(username='testuser')  # Create one if needed
item = Item.objects.filter(status='active').first()

# Place 11 bids rapidly
for i in range(11):
    Bid.objects.create(
        item=item,
        bidder=user,
        amount=item.current_price + Decimal('5000') * (i+1),
        bid_time=timezone.now()
    )

# Check fraud alerts
from auctions.models import FraudAlert
FraudAlert.objects.filter(alert_type='rapid_bidding').latest('created_at')
```

**Expected Result:**
- ✅ Alert Type: `rapid_bidding`
- ✅ Severity: `HIGH`
- ✅ Description: "User placed 11 bids in 5 minutes. Possible bot activity."
- ✅ Visible in admin dashboard with orange badge

---

### Method 2: Self-Bidding Detection
**What it detects:** Sellers bidding on their own items (CRITICAL)

**How to test:**
```python
# Run in Django shell
from auctions.models import Item, Bid, User
from decimal import Decimal

# Get a seller's item
seller = User.objects.get(username='seller_username')
item = Item.objects.filter(seller=seller, status='active').first()

# Seller bids on their own item
Bid.objects.create(
    item=item,
    bidder=seller,  # Same as seller!
    amount=item.current_price + Decimal('10000')
)

# Check alert
FraudAlert.objects.filter(alert_type='self_bidding').latest('created_at')
```

**Expected Result:**
- ✅ Alert Type: `self_bidding`
- ✅ Severity: `CRITICAL`
- ✅ Description: "Seller is bidding on their own item"
- ✅ Red badge in admin dashboard
- ✅ Should prevent the bid

---

### Method 3: New Account High-Value Bids
**What it detects:** Accounts <7 days old placing bids >1,000,000 UGX

**How to test:**
```python
# Create brand new user
from django.contrib.auth.models import User
from auctions.models import Bid, Item
from decimal import Decimal
from django.utils import timezone

new_user = User.objects.create_user(
    username=f'newuser_{timezone.now().timestamp()}',
    password='testpass123'
)

item = Item.objects.filter(status='active').first()

# Place high-value bid (>1M UGX)
Bid.objects.create(
    item=item,
    bidder=new_user,
    amount=Decimal('1500000')  # 1.5M UGX
)

# Check alert
from auctions.models import FraudAlert
FraudAlert.objects.filter(alert_type='new_account_high_value').latest('created_at')
```

**Expected Result:**
- ✅ Alert Type: `new_account_high_value`
- ✅ Severity: `HIGH`
- ✅ Description: "New account (<7 days) placing high-value bid"

---

### Method 4: Bid Sniping Pattern
**What it detects:** Users consistently bidding in last 60 seconds

**How to test:**
```python
from auctions.models import Item, Bid, User
from datetime import timedelta
from django.utils import timezone
from decimal import Decimal

user = User.objects.get(username='testuser')

# Find or create items ending soon
for i in range(6):
    item = Item.objects.create(
        seller=User.objects.exclude(pk=user.pk).first(),
        title=f'Test Snipe Item {i}',
        description='Testing bid sniping',
        starting_price=Decimal('50000'),
        current_price=Decimal('50000'),
        min_increment=Decimal('5000'),
        end_time=timezone.now() + timedelta(seconds=30),  # Ends in 30 sec
        status='active'
    )
    
    # Bid in last 30 seconds
    Bid.objects.create(
        item=item,
        bidder=user,
        amount=Decimal('55000')
    )

# Check alert
FraudAlert.objects.filter(alert_type='bid_sniping').latest('created_at')
```

**Expected Result:**
- ✅ Alert Type: `bid_sniping`
- ✅ Severity: `MEDIUM`
- ✅ Description indicates sniping pattern

---

### Method 5: Shill Bidding Detection
**What it detects:** Users bidding repeatedly on same seller's items (>70% affinity)

**How to test:**
```python
from auctions.models import Bid, Item, User
from decimal import Decimal

shill = User.objects.get(username='shill_user')
seller = User.objects.get(username='target_seller')

# Create 10 items from seller
items = []
for i in range(10):
    item = Item.objects.create(
        seller=seller,
        title=f'Seller Item {i}',
        description='Test',
        starting_price=Decimal('50000'),
        current_price=Decimal('50000'),
        min_increment=Decimal('5000'),
        end_time=timezone.now() + timedelta(days=1),
        status='active'
    )
    items.append(item)

# Shill bids on 8 of 10 items (80% affinity)
for item in items[:8]:
    Bid.objects.create(
        item=item,
        bidder=shill,
        amount=item.current_price + Decimal('5000')
    )

# Trigger detection on next bid
Bid.objects.create(
    item=items[8],
    bidder=shill,
    amount=items[8].current_price + Decimal('5000')
)

# Check alert
FraudAlert.objects.filter(alert_type='shill_bidding').latest('created_at')
```

**Expected Result:**
- ✅ Alert Type: `shill_bidding` or `seller_affinity`
- ✅ Severity: `HIGH`
- ✅ Data shows high percentage of bids on one seller

---

### Method 6: Low Win Ratio Detection
**What it detects:** Users who bid frequently but never win (<5% win rate)

**How to test:**
```python
from auctions.models import Bid, Item, User
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

shill = User.objects.get_or_create(username='low_win_user')[0]

# Create 30 completed auctions where user bid but lost
for i in range(30):
    item = Item.objects.create(
        seller=User.objects.exclude(pk=shill.pk).first(),
        title=f'Completed Item {i}',
        description='Test',
        starting_price=Decimal('50000'),
        current_price=Decimal('100000'),
        min_increment=Decimal('5000'),
        end_time=timezone.now() - timedelta(days=1),  # Already ended
        status='completed',
        winner=User.objects.exclude(pk=shill.pk).last()  # Different winner
    )
    
    # Shill bid but didn't win
    Bid.objects.create(
        item=item,
        bidder=shill,
        amount=Decimal('55000')  # Lower than winning bid
    )

# Trigger detection on new bid
new_item = Item.objects.filter(status='active').first()
Bid.objects.create(
    item=new_item,
    bidder=shill,
    amount=new_item.current_price + Decimal('5000')
)

# Check alert
FraudAlert.objects.filter(alert_type='low_win_ratio').latest('created_at')
```

**Expected Result:**
- ✅ Alert Type: `low_win_ratio`
- ✅ Severity: `MEDIUM`
- ✅ Shows win percentage <5%

---

### Method 7: Unusual Bid Amount
**What it detects:** Bids 5x+ higher than current price

**How to test:**
```python
from auctions.models import Bid, Item, User
from decimal import Decimal

user = User.objects.get(username='testuser')
item = Item.objects.filter(status='active').first()

# Bid 6x the current price
unusual_amount = item.current_price * 6

Bid.objects.create(
    item=item,
    bidder=user,
    amount=unusual_amount
)

# Check alert
FraudAlert.objects.filter(alert_type='unusual_bid_amount').latest('created_at')
```

**Expected Result:**
- ✅ Alert Type: `unusual_bid_amount`
- ✅ Severity: `MEDIUM`
- ✅ Shows multiplier data

---

### Method 8: AI Fraud Assessment (GPT-4o-mini)
**What it detects:** Complex patterns analyzed by AI

**Prerequisites:**
- OpenAI API key must be set in environment (`OPENAI_API_KEY`)
- At least one heuristic alert must be triggered first

**How to test:**
```python
# Trigger multiple fraud patterns (e.g., rapid bidding + shill bidding)
# AI assessment will automatically run if OpenAI is enabled

# Check for AI assessment
FraudAlert.objects.filter(alert_type='ai_fraud_assessment').latest('created_at')
```

**Expected Result:**
- ✅ Alert Type: `ai_fraud_assessment`
- ✅ Severity: Based on AI analysis
- ✅ Description contains AI reasoning
- ✅ Data includes risk_level, confidence_score, recommended_action

---

## 📊 Viewing Alerts in Admin Dashboard

### Step-by-Step:

1. **Login as Admin**
   - URL: `/admin/login/`
   - Use your superuser credentials

2. **Navigate to Fraud Alerts**
   - Click "Admin Dashboard" in navigation
   - Click "Fraud Alerts" tab
   - Or go directly to `/admin/fraud-alerts/`

3. **Dashboard Features:**
   - **Summary Cards** (top):
     - Total Alerts
     - Critical Alerts (red)
     - High Alerts (orange)
     - Resolved vs Unresolved

   - **Filters**:
     - Search by username, alert type, description
     - Filter by severity (all, low, medium, high, critical)
     - Filter by status (all, resolved, unresolved)
     - Filter by alert type
     - Filter by date range (7, 30, 90 days, all)

   - **Alert List**:
     - Color-coded severity badges
     - User information
     - Item link (if applicable)
     - Alert type and description
     - Timestamp
     - Actions: View Details, Resolve

   - **Charts**:
     - Last 7 Days Activity (line chart)
     - Alert Types Distribution (bar chart)
     - Severity breakdown

4. **Resolve Alerts:**
   - Click "View Details" on any alert
   - Review the full description and data
   - Click "Mark as Resolved"
   - Alert moves to "Resolved" section

---

## 🔗 Testing Transaction Logging (Blockchain-Inspired)

### What it does:
- Every transaction creates a SHA-256 hash
- Each transaction links to previous hash (blockchain chain)
- Tampering breaks the chain

### Test Hash Generation:

```python
# Run in Django shell
from auctions.models import TransactionLog, Item, User
from decimal import Decimal

user = User.objects.first()
item = Item.objects.first()

# Create transaction
log = TransactionLog.objects.create(
    transaction_id='TEST-001',
    transaction_type='purchase',
    item=item,
    user=user,
    amount=Decimal('100000'),
    payment_method='mtn',
    payment_reference='MTN-REF-123',
    data={
        'seller': item.seller.username,
        'payment_id': 'PAY-001',
        'phone_number': '+256700000000'
    }
)

# Verify hash exists
print(f"Hash: {log.current_hash}")
print(f"Previous Hash: {log.previous_hash}")
print(f"Hash Length: {len(log.current_hash)} (should be 64)")
```

### Test Chain Integrity:

```python
# Create multiple transactions
for i in range(5):
    TransactionLog.objects.create(
        transaction_id=f'TEST-{i+2:03d}',
        transaction_type='bid',
        item=item,
        user=user,
        amount=Decimal('50000') * (i+1),
        payment_method='web'
    )

# Verify chain
logs = TransactionLog.objects.all().order_by('id')
for i in range(1, len(logs)):
    current = logs[i]
    previous = logs[i-1]
    
    # Current's previous_hash should match previous' current_hash
    if current.previous_hash == previous.current_hash:
        print(f"✅ Transaction {i}: Chain intact")
    else:
        print(f"❌ Transaction {i}: Chain broken!")
```

### Test Tamper Detection:

```python
# Get a transaction
log = TransactionLog.objects.first()
original_hash = log.current_hash
original_amount = log.amount

# Manually tamper with amount (bypassing save to avoid recalculation)
TransactionLog.objects.filter(pk=log.pk).update(amount=Decimal('999999'))

# Refresh
log.refresh_from_db()

# Hash is still original, but data changed
print(f"Hash unchanged: {log.current_hash == original_hash}")  # True
print(f"Amount changed: {log.amount != original_amount}")  # True

# Recalculate hash
recalculated_hash = log.calculate_hash()
print(f"Hash mismatch: {recalculated_hash != log.current_hash}")  # True - Tamper detected!
```

---

## 🧪 Quick Test Script (All Methods)

Save this as `test_fraud.py` and run `python manage.py shell < test_fraud.py`:

```python
from auctions.models import User, Item, Bid, FraudAlert, TransactionLog
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

print("🧪 Testing Fraud Detection System\n")

# Setup
try:
    user = User.objects.get(username='fraudtest')
except User.DoesNotExist:
    user = User.objects.create_user(username='fraudtest', password='test123')

try:
    seller = User.objects.get(username='seller_test')
except User.DoesNotExist:
    seller = User.objects.create_user(username='seller_test', password='test123')

item = Item.objects.filter(status='active').first()

if not item:
    from auctions.models import Category
    category = Category.objects.first()
    item = Item.objects.create(
        seller=seller,
        category=category,
        title='Fraud Test Item',
        description='Testing fraud detection',
        starting_price=Decimal('100000'),
        current_price=Decimal('100000'),
        min_increment=Decimal('5000'),
        end_time=timezone.now() + timedelta(days=1),
        status='active'
    )

initial_count = FraudAlert.objects.count()

# Test 1: Rapid Bidding
print("Test 1: Rapid Bidding...")
for i in range(11):
    Bid.objects.create(
        item=item,
        bidder=user,
        amount=item.current_price + Decimal('5000') * (i+1)
    )
alerts = FraudAlert.objects.filter(alert_type='rapid_bidding', user=user)
print(f"  ✅ Created {alerts.count()} rapid bidding alert(s)")

# Test 2: Unusual Bid Amount
print("\nTest 2: Unusual Bid Amount...")
Bid.objects.create(
    item=item,
    bidder=user,
    amount=item.current_price * 6  # 6x price
)
alerts = FraudAlert.objects.filter(alert_type='unusual_bid_amount', user=user)
print(f"  ✅ Created {alerts.count()} unusual bid alert(s)")

# Summary
total_alerts = FraudAlert.objects.count() - initial_count
print(f"\n📊 Total New Alerts: {total_alerts}")
print(f"🌐 View in admin dashboard: /admin/fraud-alerts/")
```

---

## 📝 Summary Checklist

- ✅ Rapid Bidding (>10 bids/5min)
- ✅ Self-Bidding (seller on own item)
- ✅ New Account High-Value (new user, >1M bid)
- ✅ Bid Sniping (last 60 seconds pattern)
- ✅ Shill Bidding (>70% affinity to seller)
- ✅ Low Win Ratio (<5% win rate)
- ✅ Unusual Bid Amount (5x+ current price)
- ✅ Bid Pattern Anomaly (statistical deviation)
- ✅ Seller Affinity (disproportionate bidding)
- ✅ Bid Timing Pattern (early bid, avoid final)
- ✅ Collusive Bidding (coordinated accounts)
- ✅ Payment Fraud Detection
- ✅ AI Assessment (GPT-4o-mini)
- ✅ Admin Dashboard Viewing
- ✅ Transaction Log Hashing (SHA-256)
- ✅ Chain Integrity Verification

---

## 🎓 Performance Metrics

According to test results (see `RESULTS.md`):
- **Precision**: 90.24%
- **Recall**: 92.50%
- **F1-Score**: 91.35%
- **Individual Method Accuracy**: 80-100%

---

## 🔧 Troubleshooting

**Q: No alerts appearing?**
- Check if FraudDetectionService is called in `auctions/views.py` `place_bid` view
- Verify thresholds (e.g., need >10 bids for rapid bidding)
- Check Django logs for errors

**Q: AI assessment not working?**
- Verify `OPENAI_API_KEY` is set: `echo $OPENAI_API_KEY`
- Ensure at least one heuristic alert triggered first
- Check OpenAI API quota

**Q: Can't access admin dashboard?**
- Ensure you're logged in as superuser
- Create superuser: `python manage.py createsuperuser`
- Check URL: `/admin/fraud-alerts/`

---

Happy Testing! 🚀
