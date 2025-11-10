from django import template
from auctions.models import Message

register = template.Library()

@register.simple_tag
def get_unread_messages_count(user):
    """Safely get the number of unread messages for a user."""
    if not user.is_authenticated:
        return 0
    try:
        return Message.objects.filter(
            recipient=user,
            is_read=False
        ).count()
    except:
        return 0
