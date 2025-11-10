import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class SMSService:
    
    @staticmethod
    def send_sms(phone_number, message, demo_mode=True):
        """
        Send SMS using Africa's Talking or demo mode
        
        Args:
            phone_number: Recipient phone number
            message: SMS message content
            demo_mode: If True, just log the SMS instead of sending
            
        Returns:
            dict: Status of SMS sending
        """
        if demo_mode:
            logger.info(f"📱 [DEMO MODE] SMS to {phone_number}: {message}")
            return {
                'success': True,
                'message_id': f'demo-{phone_number[-4:]}',
                'status': 'sent',
                'demo': True
            }
        
        try:
            if hasattr(settings, 'AFRICAS_TALKING_USERNAME') and hasattr(settings, 'AFRICAS_TALKING_API_KEY'):
                return SMSService._send_africas_talking(phone_number, message)
            elif hasattr(settings, 'TWILIO_ACCOUNT_SID') and hasattr(settings, 'TWILIO_AUTH_TOKEN'):
                return SMSService._send_twilio(phone_number, message)
            else:
                logger.warning("No SMS credentials configured. Using demo mode.")
                return SMSService.send_sms(phone_number, message, demo_mode=True)
        except Exception as e:
            logger.error(f"SMS sending failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'status': 'failed'
            }
    
    @staticmethod
    def _send_africas_talking(phone_number, message):
        """Send SMS via Africa's Talking"""
        import africastalking
        
        username = settings.AFRICAS_TALKING_USERNAME
        api_key = settings.AFRICAS_TALKING_API_KEY
        
        africastalking.initialize(username, api_key)
        sms = africastalking.SMS
        
        response = sms.send(message, [phone_number])
        
        return {
            'success': True,
            'response': response,
            'status': 'sent',
            'provider': 'africastalking'
        }
    
    @staticmethod
    def _send_twilio(phone_number, message):
        """Send SMS via Twilio"""
        from twilio.rest import Client
        
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        from_number = settings.TWILIO_PHONE_NUMBER
        
        client = Client(account_sid, auth_token)
        
        message = client.messages.create(
            body=message,
            from_=from_number,
            to=phone_number
        )
        
        return {
            'success': True,
            'message_id': message.sid,
            'status': 'sent',
            'provider': 'twilio'
        }
    
    @staticmethod
    def send_bid_confirmation(phone_number, item_title, bid_amount, tax_amount=0, total_amount=None, network='MTN', demo_mode=True):
        """Send bid confirmation SMS"""
        if total_amount is None:
            total_amount = bid_amount
            
        message = (
            f"✅ Bid Confirmed!\n"
            f"Item: {item_title[:30]}\n"
            f"Bid: UGX {bid_amount:,.0f}\n"
        )
        
        if tax_amount > 0:
            message += f"Tax (5%): UGX {tax_amount:,.0f}\n"
            message += f"Total: UGX {total_amount:,.0f}\n"
            
        message += (
            f"Payment: {network} Mobile Money\n"
            f"Thank you for bidding on AuctionHub!"
        )
        return SMSService.send_sms(phone_number, message, demo_mode)
    
    @staticmethod
    def send_payment_confirmation(phone_number, item_title, amount, payment_method, demo_mode=True):
        """Send payment confirmation SMS"""
        message = (
            f"💳 Payment Received!\n"
            f"Item: {item_title}\n"
            f"Amount: UGX {amount:,.0f}\n"
            f"Method: {payment_method}\n"
            f"Your item will be delivered soon. Thank you!"
        )
        return SMSService.send_sms(phone_number, message, demo_mode)
    
    @staticmethod
    def send_wallet_confirmation(phone_number, amount, balance, tax_amount=0, total_amount=None, action='deposit', network='MTN', demo_mode=True):
        """Send wallet transaction confirmation SMS"""
        action_text = 'Deposited' if action == 'deposit' else 'Withdrawn'
        action_emoji = '➕' if action == 'deposit' else '➖'
        
        if total_amount is None:
            total_amount = amount
        
        message = f"{action_emoji} Wallet {action_text}!\n"
        message += f"Amount: UGX {amount:,.0f}\n"
        
        if tax_amount > 0:
            message += f"Tax (5%): UGX {tax_amount:,.0f}\n"
            message += f"Total: UGX {total_amount:,.0f}\n"
        
        message += (
            f"New Balance: UGX {balance:,.0f}\n"
            f"Payment: {network} Mobile Money\n"
            f"Thank you for using AuctionHub!"
        )
        return SMSService.send_sms(phone_number, message, demo_mode)
    
    @staticmethod
    def send_listing_confirmation(phone_number, item_title, item_id, starting_price, duration, network='MTN', demo_mode=True):
        """Send item listing confirmation SMS"""
        message = (
            f"✅ Item Listed!\n"
            f"Title: {item_title[:30]}\n"
            f"Price: UGX {starting_price:,.0f}\n"
            f"Duration: {duration}\n"
            f"Item ID: #{item_id}\n"
            f"Note: Upload images via web for better visibility.\n"
            f"Thank you for using AuctionHub USSD!"
        )
        return SMSService.send_sms(phone_number, message, demo_mode)
    
    @staticmethod
    def send_buy_now_confirmation(phone_number, item_title, total_amount, tax_amount, seller_receives, demo_mode=True):
        """Send Buy Now purchase confirmation SMS"""
        message = (
            f"⚡ Purchase Successful!\n"
            f"Item: {item_title[:30]}\n"
            f"Amount: UGX {total_amount:,.0f}\n"
            f"Platform Tax (5%): UGX {tax_amount:,.0f}\n"
            f"Seller Receives: UGX {seller_receives:,.0f}\n"
            f"Payment: Wallet\n"
            f"Thank you for using AuctionHub Buy Now!"
        )
        return SMSService.send_sms(phone_number, message, demo_mode)
