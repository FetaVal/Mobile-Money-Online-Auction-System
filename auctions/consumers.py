import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from decimal import Decimal
from .models import Item, Bid
from django.utils import timezone
from django.core.cache import cache
import time


class AuctionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.item_id = self.scope['url_route']['kwargs']['item_id']
        self.room_group_name = f'auction_{self.item_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        
        item_data = await self.get_item_data()
        if item_data:
            await self.send(text_data=json.dumps({
                'type': 'auction_state',
                **item_data
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            # Rate limiting for WebSocket messages
            if not await self.check_websocket_rate_limit():
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Rate limit exceeded. Please slow down.'
                }))
                return

            if message_type == 'place_bid':
                await self.handle_place_bid(data)
            elif message_type == 'request_update':
                await self.send_auction_update()
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))

    async def handle_place_bid(self, data):
        user = self.scope.get('user')
        
        if not user or not user.is_authenticated:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You must be logged in to place a bid'
            }))
            return

        bid_amount = data.get('amount')
        if not bid_amount:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Bid amount is required'
            }))
            return

        try:
            bid_amount = Decimal(str(bid_amount))
        except (ValueError, TypeError):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid bid amount'
            }))
            return

        result = await self.create_bid(user, bid_amount)
        
        if result['success']:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'bid_placed',
                    'bid': result['bid_data']
                }
            )
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': result.get('error', 'Failed to place bid')
            }))

    async def bid_placed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_bid',
            'bid': event['bid']
        }))

    async def send_auction_update(self):
        item_data = await self.get_item_data()
        if item_data:
            await self.send(text_data=json.dumps({
                'type': 'auction_update',
                **item_data
            }))

    @database_sync_to_async
    def get_item_data(self):
        try:
            item = Item.objects.get(id=self.item_id, status='active')
            latest_bids = item.bids.order_by('-bid_time')[:5]
            
            return {
                'item_id': item.id,
                'title': item.title,
                'current_price': str(item.current_price),
                'bid_count': item.bid_count,
                'time_remaining': self.get_time_remaining(item),
                'status': item.status,
                'latest_bids': [
                    {
                        'bidder': bid.bidder.username,
                        'amount': str(bid.amount),
                        'time': bid.bid_time.isoformat()
                    }
                    for bid in latest_bids
                ]
            }
        except Item.DoesNotExist:
            return None

    @database_sync_to_async
    def create_bid(self, user, bid_amount):
        try:
            item = Item.objects.select_for_update().get(id=self.item_id)
            
            if item.status != 'active':
                return {'success': False, 'error': 'Auction is not active'}
            
            if item.end_time <= timezone.now():
                item.status = 'expired'
                item.save()
                return {'success': False, 'error': 'Auction has ended'}
            
            if item.seller == user:
                return {'success': False, 'error': 'You cannot bid on your own item'}
            
            min_bid = item.current_price + item.min_increment
            if bid_amount < min_bid:
                return {
                    'success': False,
                    'error': f'Bid must be at least UGX {min_bid:,.0f}'
                }
            
            item.bids.filter(is_winning=True).update(is_winning=False)
            
            bid = Bid.objects.create(
                item=item,
                bidder=user,
                amount=bid_amount,
                is_winning=True,
                payment_method='websocket'
            )
            
            item.current_price = bid_amount
            item.bid_count += 1
            item.save()
            
            return {
                'success': True,
                'bid_data': {
                    'bidder': user.username,
                    'amount': str(bid_amount),
                    'time': bid.bid_time.isoformat(),
                    'bid_count': item.bid_count,
                    'current_price': str(item.current_price)
                }
            }
        except Item.DoesNotExist:
            return {'success': False, 'error': 'Item not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_time_remaining(self, item):
        if item.end_time <= timezone.now():
            return 'Ended'
        
        delta = item.end_time - timezone.now()
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f'{days}d {hours}h'
        elif hours > 0:
            return f'{hours}h {minutes}m'
        elif minutes > 0:
            return f'{minutes}m {seconds}s'
        else:
            return f'{seconds}s'
    
    async def check_websocket_rate_limit(self):
        """
        Rate limit WebSocket messages to prevent abuse
        Allows 10 messages per minute per user
        """
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            return True  # Allow anonymous connections
        
        cache_key = f"ws_ratelimit:auction:{user.id}"
        max_messages = 10
        window = 60  # seconds
        
        try:
            data = cache.get(cache_key, {'count': 0, 'reset_time': time.time() + window})
            
            current_time = time.time()
            
            if current_time >= data['reset_time']:
                data = {'count': 1, 'reset_time': current_time + window}
                cache.set(cache_key, data, window)
                return True
            
            data['count'] += 1
            
            if data['count'] > max_messages:
                cache.set(cache_key, data, window)
                return False
            
            cache.set(cache_key, data, window)
            return True
        except Exception:
            # If cache fails, allow the message (fail open)
            return True
