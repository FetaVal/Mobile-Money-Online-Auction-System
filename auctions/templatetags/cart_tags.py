from django import template
from auctions.models import Cart

register = template.Library()

@register.simple_tag
def get_cart_count(user):
    """Safely get the number of items in a user's cart."""
    if not user.is_authenticated:
        return 0
    try:
        cart = Cart.objects.get(user=user)
        return cart.items.count()
    except Cart.DoesNotExist:
        return 0
