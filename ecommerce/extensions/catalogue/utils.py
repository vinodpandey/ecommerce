from __future__ import unicode_literals

import logging
from hashlib import md5

from django.conf import settings
from django.db.utils import IntegrityError
from oscar.core.loading import get_model

from ecommerce.core.constants import COUPON_PRODUCT_CLASS_NAME
from ecommerce.extensions.voucher.models import CouponVouchers
from ecommerce.extensions.voucher.utils import create_vouchers

Catalog = get_model('catalogue', 'Catalog')
logger = logging.getLogger(__name__)
Product = get_model('catalogue', 'Product')
ProductCategory = get_model('catalogue', 'ProductCategory')
ProductClass = get_model('catalogue', 'ProductClass')
StockRecord = get_model('partner', 'StockRecord')


def create_coupon_product(
        benefit_type,
        benefit_value,
        catalog,
        catalog_query,
        category,
        code,
        course_seat_types,
        email_domains,
        end_datetime,
        enterprise_customer,
        max_uses,
        note,
        partner,
        price,
        quantity,
        start_datetime,
        title,
        voucher_type,
        course_catalog,
        program_uuid,
):
    """
    Creates a coupon product and a stock record for it.

    Arguments:
        benefit_type (str): Voucher Benefit type.
        benefit_value (int): Voucher Benefit value.
        catalog (Catalog): Catalog used to create a range of products.
        catalog_query (str): ElasticSearch query used by dynamic coupons.
        category (dict): Contains category ID and name.
        code (str): Voucher code.
        course_seat_types (str): Comma-separated list of course seat types.
        course_catalog (int): Course catalog id from Catalog Service
        email_domains (str): Comma-separated list of email domains.
        end_datetime (Datetime): Voucher end Datetime.
        enterprise_customer (str): UUID of an EnterpriseCustomer to attach to this voucher
        max_uses (int): Number of Voucher max uses.
        note (str): Coupon note.
        partner (User): Partner associated with coupon Stock Record.
        price (int): The price of the coupon.
        quantity (int): Number of vouchers to be created and associated with the coupon.
        start_datetime (Datetime): Voucher start Datetime.
        title (str): The name of the coupon.
        voucher_type (str): Voucher type
        program_uuid (str): Program UUID for the Coupon

    Returns:
        A coupon Product object.

    Raises:
        IntegrityError: An error occurred when create_vouchers method returns
                        an IntegrityError exception
    """
    product_class = ProductClass.objects.get(name=COUPON_PRODUCT_CLASS_NAME)
    coupon_product = Product.objects.create(title=title, product_class=product_class)

    ProductCategory.objects.get_or_create(product=coupon_product, category=category)

    # Vouchers are created during order and not fulfillment like usual
    # because we want vouchers to be part of the line in the order.

    try:
        vouchers = create_vouchers(
            benefit_type=benefit_type,
            benefit_value=benefit_value,
            catalog=catalog,
            catalog_query=catalog_query,
            code=code or None,
            coupon=coupon_product,
            course_catalog=course_catalog,
            course_seat_types=course_seat_types,
            email_domains=email_domains,
            end_datetime=end_datetime,
            enterprise_customer=enterprise_customer,
            max_uses=max_uses,
            name=title,
            quantity=int(quantity),
            start_datetime=start_datetime,
            voucher_type=voucher_type,
            program_uuid=program_uuid,
        )
    except IntegrityError:
        logger.exception('Failed to create vouchers for [%s] coupon.', coupon_product.title)
        raise

    coupon_vouchers, __ = CouponVouchers.objects.get_or_create(coupon=coupon_product)
    coupon_vouchers.vouchers.add(*vouchers)
    coupon_product.attr.coupon_vouchers = coupon_vouchers
    coupon_product.attr.note = note
    coupon_product.save()

    sku = generate_sku(product=coupon_product, partner=partner)
    StockRecord.objects.update_or_create(
        defaults={
            'price_currency': settings.OSCAR_DEFAULT_CURRENCY,
            'price_excl_tax': price
        },
        partner=partner,
        partner_sku=sku,
        product=coupon_product
    )

    return coupon_product


def generate_sku(product, partner):
    """
    Generates a SKU for the given partner and and product combination.

    Example: 76E4E71
    """
    if not product.get_product_class():
        raise AttributeError('Product has no product class')

    if product.is_coupon_product:
        _hash = ' '.join((
            unicode(product.id),
            str(partner.id)
        ))
    elif product.is_enrollment_code_product:
        _hash = ' '.join((
            getattr(product.attr, 'course_key', ''),
            getattr(product.attr, 'seat_type', ''),
            unicode(partner.id)
        ))
    elif product.is_seat_product:
        _hash = ' '.join((
            getattr(product.attr, 'certificate_type', ''),
            product.attr.course_key,
            unicode(product.attr.id_verification_required),
            getattr(product.attr, 'credit_provider', ''),
            str(partner.id)
        ))
    else:
        raise Exception('Unexpected product class')

    md5_hash = md5(_hash.lower())
    digest = md5_hash.hexdigest()[-7:]

    return digest.upper()


def get_or_create_catalog(name, partner, stock_record_ids):
    """
    Returns the catalog which has the same name, partner and stock records.
    If there isn't one with that data, creates and returns a new one.
    """
    catalogs = Catalog.objects.all()
    stock_records = [StockRecord.objects.get(id=id) for id in stock_record_ids]  # pylint: disable=redefined-builtin

    for catalog in catalogs:
        if catalog.name == name and catalog.partner == partner:
            if set(catalog.stock_records.all()) == set(stock_records):
                return catalog, False

    catalog = Catalog.objects.create(name=name, partner=partner)
    for stock_record in stock_records:
        catalog.stock_records.add(stock_record)
    return catalog, True
