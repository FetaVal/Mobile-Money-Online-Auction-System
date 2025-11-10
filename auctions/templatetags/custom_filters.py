from django import template

register = template.Library()

@register.filter(name='intcomma')
def intcomma(value):
    """
    Converts an integer to a string containing commas every three digits.
    For example, 3000 becomes '3,000' and 45000 becomes '45,000'.
    """
    try:
        value = int(float(value))
        return "{:,}".format(value)
    except (ValueError, TypeError):
        return value

@register.filter(name='currency')
def currency(value):
    """
    Formats a number as currency with commas.
    For example, 4640600000 becomes '4,640,600,000'
    """
    try:
        value = float(value)
        if value >= 1000000000:
            return "{:,.0f}".format(value)
        elif value >= 1000000:
            return "{:,.2f}M".format(value / 1000000)
        elif value >= 1000:
            return "{:,.0f}".format(value)
        else:
            return "{:.2f}".format(value)
    except (ValueError, TypeError):
        return value
