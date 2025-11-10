from django.urls import re_path
from auctions import consumers

websocket_urlpatterns = [
    re_path(r'ws/auction/(?P<item_id>\d+)/$', consumers.AuctionConsumer.as_asgi()),
]
