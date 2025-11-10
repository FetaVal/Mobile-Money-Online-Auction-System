# Online Auction System with Mobile Money Integration

## Overview
This project is a comprehensive Django-based online auction platform designed for efficient and secure bidding. It integrates mobile money payments (MTN, Airtel Money), USSD/SMS support for offline access, AI-powered fraud detection, and blockchain-inspired transaction logging. The system aims to address real-world challenges in Uganda's digital economy by promoting financial inclusion, bridging the digital divide, building trust through technology, and combining global e-commerce practices with local payment systems.

## User Preferences
No specific user preferences were provided in the original `replit.md` file.

## System Architecture

### UI/UX Decisions
The platform features a modern homepage with a hero section, professional search, and advanced filtering. Item detail pages include image galleries, live countdown timers, smart bid forms, and a professional AuctionHub Guarantee section displaying trust badges. Seller profile pages offer a showcase with statistics, active auctions, sold items, and reviews. The shopping cart and checkout system are professionally designed, and the payment system incorporates a modern country selector and dynamic payment tabs. A floating AI chatbot assistant appears on all pages. The design prioritizes responsiveness and professional styling, utilizing modern UI elements like animated gradients, subtle floating shapes, compact feature badges with glassmorphism, and elegant typography animations.

**Smart User Messaging (Nov 2025):**
- Personalized welcome messages that differentiate new users from returning users
- First-time login: "Welcome to AuctionHub, {username}! 🎉"
- Returning users: "Welcome back, {username}!"
- Logic checks `user.last_login` before login to determine first-time vs returning status
- Applied consistently across both regular login and 2FA verification flows

**Profile Sharing Feature (Nov 2025):**
- **Share Profile in Chat**: Users can share any profile (own or others) via chat messages with other users
- **Smart User Search**: Modal with real-time search functionality (300ms debounce, 2+ characters required)
- **Profile Button Positioning**: Edit Profile button repositioned closer to left with Share Profile button alongside
- **Universal Availability**: Share button appears on both own profile dashboard and other users' seller profiles
- **Proper URL Generation**: Uses Django's URL reversing to ensure correct username-based profile links
- **Search API**: New `/api/search-users/` endpoint for searching users by username (excludes self, returns up to 10 results)
- **Security**: CSRF protection, prevents self-messaging, validates all inputs

**Auto-Dismissing Notifications (Nov 2025):**
- All system notifications (success, info, warning, error) automatically dismiss after 5 seconds
- Uses Bootstrap 5 Alert API for smooth fade-out animation
- Manual close button remains functional for immediate dismissal
- Implemented via JavaScript DOMContentLoaded listener targeting `.auto-dismiss-alert` class
- Improves UX by reducing notification clutter without requiring user action

**New Account Bid Limits (Nov 2025):**
- Fraud prevention: New accounts must be at least 7 days old to place bids above 1,000,000 UGX
- Prevents spam and alt account abuse in high-value auctions
- Configurable via `MIN_ACCOUNT_AGE_FOR_HIGH_BIDS` (default: 7 days) and `HIGH_VALUE_BID_THRESHOLD` (default: 1,000,000 UGX)
- Clear error messages show account age, days remaining, and threshold when blocked
- Validation occurs before bid is saved, preventing database pollution

**Advanced Rapid Bidding Prevention (Nov 2025 - PRODUCTION-READY):**
- **Multi-tier enforcement system**: Soft challenges (CAPTCHA) → Hard cooldowns (60-120s) → Suspension (after 4th violation)
- **Per-auction detection**: Soft triggers at 5 bids/2min or 8 bids/5min; Hard triggers at 12 bids/5min or 3 bids/20s
- **Global velocity tracking**: Cross-auction monitoring (soft: 20 bids/3 auctions/10min; hard: 50 bids/5 auctions/30min)
- **Auction endgame exceptions**: Final 2 minutes automatically raise thresholds by 50% to allow legitimate last-minute bidding
- **Minimum increment detection**: Flags 3+ minimal increment bids within 30 seconds to prevent penny-increment attacks
- **BidCooldown model**: Tracks temporary restrictions per user/auction with database indexes for performance
- **CAPTCHA integration**: django-simple-captcha with auto-launching modal, timestamp validation (5 min expiry), and complete session cleanup
- **Bid revalidation**: verify_captcha view checks current auction state (price, status, end_time) before accepting CAPTCHA-protected bids
- **Fraud detection enforcement**: Both place_bid and verify_captcha paths run full fraud analysis; critical alerts delete bid and prevent cooldown resolution
- **40+ configurable settings**: All thresholds, windows, cooldown durations, and escalation rules customizable via settings.py
- **Admin Bypass Permissions System (Nov 2025)**: Admins can grant selective bypasses (account age, rapid bidding, fraud detection, or all restrictions) per user via clean modal interface in Users dashboard; tracks who granted bypass and when; superusers auto-exempt from ALL restrictions
- **Architect-verified**: Zero critical bugs, production-ready with comprehensive security safeguards

**Shipping & Checkout Enhancements (Nov 2025):**
- **Accurate shipping cost display**: Cart and checkout pages now show actual shipping fees from item.shipping_cost_base instead of hardcoded "FREE"
- **Shipping method badges**: Each item in cart/checkout displays visual badges (FREE SHIPPING, PICKUP, +UGX cost) based on seller settings
- **Enhanced pickup option**: Improved styling with green gradient background, FREE badge, checkbox properly aligned inside container, and clear description
- **Fixed double taxation bug**: USSD payments from web checkout no longer charge platform tax twice (tax calculated once during checkout, not again during USSD PIN confirmation)
- **Smart tax handling**: System detects checkout-context payments and uses pre-calculated tax amounts from metadata instead of recalculating
- **Improved USSD receipts**: Checkout payments via USSD now show detailed breakdown (Subtotal, Shipping, Platform Tax) in both PIN entry and confirmation messages
- **Cart clearing after purchase**: All payment methods (Card, PayPal, USSD/Mobile Money, Bank Transfer) now properly clear cart items after successful payment and settle amounts to sellers
- **Dynamic shipping calculation**: Real-time shipping cost updates when delivery city/area is selected; handles pickup option, free shipping items, and gracefully falls back to safe defaults on errors (prevents NaN corruption)
- **Cancel button styling**: Removed underline from "Cancel" links in sell item form for cleaner UI

### Technical Implementations
-   **Core Auction System:** Category management, multi-image support, advanced filtering, shopping cart, and "Buy Now" functionality with atomic updates and wallet integration.
-   **Payment Integration:** Country-based routing for payment methods, including local (MTN, Airtel Money via Flutterwave, M-Pesa) and international (Stripe, PayPal, Bank Transfer) options. Supports multi-currency, a demo mode, USSD simulator with SMS confirmations, and a 5% platform tax. Includes HMAC signature verification for webhooks, replay attack protection, idempotent updates, and daily reconciliation.
-   **Platform Revenue System:** Automated 5% tax collection on all transactions, transparent tax breakdown, and separate revenue tracking.
-   **Security & Trust Features:** Blockchain-inspired logging with SHA-256 hashing, **AI-powered fraud detection (15+ methods, FULLY FUNCTIONAL - Nov 2025)** with configurable thresholds for all detection methods (rapid bidding, bid sniping, shill detection, payment fraud, etc.), **advanced rapid bidding prevention system (PRODUCTION-READY - Nov 2025)** with multi-tier enforcement (CAPTCHA soft challenges, hard cooldowns, suspension escalation), per-auction and global velocity tracking, auction endgame exceptions, and comprehensive fraud detection integration, review and rating system, Django's built-in secure authentication, modern login/register UI with secure captcha, password strength indicator, comprehensive password recovery, advanced security features (PBKDF2 600k, login attempt limiting, email/TOTP 2FA, backup codes, security settings dashboard, security audit trail), **new account bid limits** (accounts must be 7+ days old to place bids above 1M UGX, configurable via settings to prevent spam and alt account abuse).
-   **Innovative Features:** AI Chatbot Assistant (GPT-4o-mini), transparent seller ratings, automated item status updates, and mobile money verification.

### Feature Specifications
-   **Privacy & Item Management:** Profile privacy controls, seller item status management (Active, Private, Off Sale, Sold) with dynamic display and AJAX.
-   **Core Functionality:** Comprehensive database models, robust authentication, modern homepage, "Sell an Item" flow, detailed item pages with bidding, online/offline status tracking, review and rating system, professional seller profiles with follow/unfollow, secure shopping cart, and a digital wallet system.
-   **USSD System:** Supports offline bidding and item listing via USSD (*354# MTN, *789# Airtel) with PIN confirmation, SMS receipts, and tax payment steps.
-   **Trust & Credibility:** AuctionHub Guarantee section with five trust badges (Secure Payment, Buyer Protection, Money-Back Guarantee, Quality Verified, 24/7 Support).
-   **Admin Dashboard:** Comprehensive analytics, platform revenue tracking, user management, item moderation, payment monitoring, and advanced fraud alert tracking with a dedicated security monitoring dashboard.
-   **Platform Tax System:** Consistent 5% platform fee on all transactions (web, USSD, wallet), transparent display of tax breakdown, and accurate revenue tracking.
-   **Professional Payment Forms (Demo Mode):** Realistic card payment forms, convincing PayPal login mimicry, context-aware processing, proper return URLs, and accurate tax display.
-   **Three-Tier User System:** Buyer accounts, admin-approved verified seller accounts (requiring KYC and business info), and admin accounts for full platform management.
-   **Access Control:** "Sell an Item" route protected, redirecting non-sellers to the application.

### System Design Choices
-   **Backend:** Django 5.2.8, SQLite (development) / MySQL (production), Django Channels with Daphne, Redis for caching, OpenAI API.
-   **Frontend:** Django Templates, Bootstrap 4 / Crispy Forms, WebSocket client, WCAG AA accessible design system.
-   **Security:** Django's PBKDF2, SHA-256 for transaction integrity, CSRF protection, secure session management, OWASP Top 10 threat coverage.
-   **Testing & CI/CD:** 66 comprehensive tests (WebSocket, USSD, webhooks), GitHub Actions CI/CD pipeline (lint, mypy, security scanning, tests), Docker Compose production stack.
-   **Database Schema:** Models for Category, Item, Bid, BidCooldown, Cart/CartItem, Review, TransactionLog, FraudAlert, Country, UserProfile, Follow, Payment, and USSDSession.
-   **Documentation:** THREAT_MODEL.md, OPERATIONS.md, RESULTS.md.

## External Dependencies
-   **Payment Gateways:**
    -   Flutterwave (MTN Mobile Money, Airtel Money)
    -   M-Pesa
    -   Stripe
    -   PayPal
-   **AI Services:**
    -   OpenAI API (for chatbot and fraud detection)
-   **Real-time Communication:**
    -   Redis (for Django Channels)
-   **Database:**
    -   MySQL (production)
    -   SQLite (development)