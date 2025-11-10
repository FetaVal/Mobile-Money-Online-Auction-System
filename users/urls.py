from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    path('follow/<str:username>/', views.follow_user, name='follow_user'),
    path('unfollow/<str:username>/', views.unfollow_user, name='unfollow_user'),
    path('wallet/', views.wallet_dashboard, name='wallet_dashboard'),
    path('wallet/deposit/', views.wallet_deposit, name='wallet_deposit'),
    path('wallet/deposit/process/', views.process_deposit, name='process_deposit'),
    path('wallet/withdraw/', views.wallet_withdraw, name='wallet_withdraw'),
    path('wallet/withdraw/process/', views.process_withdrawal, name='process_withdrawal'),
    path('seller/apply/', views.seller_application_view, name='seller_application'),
    path('seller/status/', views.seller_application_status_view, name='seller_application_status'),
    path('seller/dashboard/', views.seller_dashboard_view, name='seller_dashboard'),
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset-confirm/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    path('verify-2fa/', views.verify_2fa, name='verify_2fa'),
    path('security/', views.security_settings, name='security_settings'),
    path('security/enable-email-2fa/', views.enable_2fa_email, name='enable_2fa_email'),
    path('security/disable-2fa/', views.disable_2fa, name='disable_2fa'),
    path('security/setup-totp/', views.setup_totp, name='setup_totp'),
    path('security/generate-backup-codes/', views.generate_backup_codes, name='generate_backup_codes'),
    path('security/change-password/', views.change_password, name='change_password'),
]
