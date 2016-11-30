from django import template

from ecommerce.extensions.offer.utils import format_benefit_value

register = template.Library()


@register.filter(name='benefit_discount')
def benefit_discount(benefit):
    """
    Format benefit value.

    Arguments:
        benefit (Benefit): Voucher's Benefit.

    Returns:
        str: String value containing formatted benefit value and type.
    """
    return format_benefit_value(benefit)
