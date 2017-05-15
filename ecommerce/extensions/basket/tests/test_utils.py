import datetime
import json

import ddt
import mock
import pytz
from django.db import transaction
from django.test import RequestFactory, TransactionTestCase
from oscar.core.loading import get_model
from oscar.test.factories import BasketFactory, ProductFactory, RangeFactory, VoucherFactory

from ecommerce.core.constants import ENROLLMENT_CODE_PRODUCT_CLASS_NAME, ENROLLMENT_CODE_SWITCH
from ecommerce.core.tests import toggle_switch
from ecommerce.courses.tests.factories import CourseFactory
from ecommerce.extensions.basket.utils import attribute_cookie_data, prepare_basket
from ecommerce.extensions.catalogue.tests.mixins import CourseCatalogTestMixin
from ecommerce.extensions.order.exceptions import AlreadyPlacedOrderException
from ecommerce.extensions.order.utils import UserAlreadyPlacedOrder
from ecommerce.extensions.partner.models import StockRecord
from ecommerce.extensions.test.factories import prepare_voucher
from ecommerce.referrals.models import Referral
from ecommerce.tests.factories import SiteConfigurationFactory
from ecommerce.tests.mixins import UserMixin
from ecommerce.tests.testcases import TestCase

Benefit = get_model('offer', 'Benefit')
Basket = get_model('basket', 'Basket')
Product = get_model('catalogue', 'Product')


@ddt.ddt
class BasketUtilsTests(CourseCatalogTestMixin, TestCase):
    """ Tests for basket utility functions. """

    def setUp(self):
        super(BasketUtilsTests, self).setUp()
        self.request = RequestFactory()
        self.request.COOKIES = {}
        self.request.user = self.create_user()
        site_configuration = SiteConfigurationFactory(partner__name='Tester')
        site_configuration.utm_cookie_name = 'test.edx.utm'
        self.request.site = site_configuration.site

    def test_prepare_basket_with_voucher(self):
        """ Verify a basket is returned and contains a voucher and the voucher is applied. """
        # Prepare a product with price of 100 and a voucher with 10% discount for that product.
        product = ProductFactory(stockrecords__price_excl_tax=100)
        new_range = RangeFactory(products=[product, ])
        voucher, product = prepare_voucher(_range=new_range, benefit_value=10)

        stock_record = StockRecord.objects.get(product=product)
        self.assertEqual(stock_record.price_excl_tax, 100.00)

        basket = prepare_basket(self.request, [product], voucher)
        self.assertIsNotNone(basket)
        self.assertEqual(basket.status, Basket.OPEN)
        self.assertEqual(basket.lines.count(), 1)
        self.assertEqual(basket.lines.first().product, product)
        self.assertEqual(basket.vouchers.count(), 1)
        self.assertIsNotNone(basket.applied_offers())
        self.assertEqual(basket.total_discount, 10.00)
        self.assertEqual(basket.total_excl_tax, 90.00)

    def test_prepare_basket_enrollment_with_voucher(self):
        """Verify the basket does not contain a voucher if enrollment code is added to it."""
        course = CourseFactory()
        toggle_switch(ENROLLMENT_CODE_SWITCH, True)
        course.create_or_update_seat('verified', False, 10, self.partner, create_enrollment_code=True)
        enrollment_code = Product.objects.get(product_class__name=ENROLLMENT_CODE_PRODUCT_CLASS_NAME)
        voucher, product = prepare_voucher()

        basket = prepare_basket(self.request, [product], voucher)
        self.assertIsNotNone(basket)
        self.assertEqual(basket.all_lines()[0].product, product)
        self.assertTrue(basket.contains_a_voucher)

        basket = prepare_basket(self.request, [enrollment_code], voucher)
        self.assertIsNotNone(basket)
        self.assertEqual(basket.all_lines()[0].product, enrollment_code)
        self.assertFalse(basket.contains_a_voucher)

    def test_multiple_vouchers(self):
        """ Verify only the last entered voucher is contained in the basket. """
        product = ProductFactory()
        voucher1 = VoucherFactory(code='FIRST')
        basket = prepare_basket(self.request, [product], voucher1)
        self.assertEqual(basket.vouchers.count(), 1)
        self.assertEqual(basket.vouchers.first(), voucher1)

        voucher2 = VoucherFactory(code='SECOND')
        new_basket = prepare_basket(self.request, [product], voucher2)
        self.assertEqual(basket, new_basket)
        self.assertEqual(new_basket.vouchers.count(), 1)
        self.assertEqual(new_basket.vouchers.first(), voucher2)

    def test_prepare_basket_without_voucher(self):
        """ Verify a basket is returned and does not contain a voucher. """
        product = ProductFactory()
        basket = prepare_basket(self.request, [product])
        self.assertIsNotNone(basket)
        self.assertEqual(basket.status, Basket.OPEN)
        self.assertEqual(basket.lines.count(), 1)
        self.assertEqual(basket.lines.first().product, product)
        self.assertFalse(basket.vouchers.all())
        self.assertFalse(basket.applied_offers())

    def test_prepare_basket_with_multiple_products(self):
        """ Verify a basket is returned and only contains a single product. """
        product1 = ProductFactory(stockrecords__partner__short_code='test1')
        product2 = ProductFactory(stockrecords__partner__short_code='test2')
        basket = prepare_basket(self.request, [product1])
        basket = prepare_basket(self.request, [product2])
        self.assertIsNotNone(basket)
        self.assertEqual(basket.status, Basket.OPEN)
        self.assertEqual(basket.lines.count(), 1)
        self.assertEqual(basket.lines.first().product, product2)
        self.assertEqual(basket.product_quantity(product2), 1)

    def test_prepare_basket_calls_attribution_method(self):
        """ Verify a basket is returned and referral method called. """
        with mock.patch('ecommerce.extensions.basket.utils.attribute_cookie_data') as mock_attr_method:
            product = ProductFactory()
            basket = prepare_basket(self.request, [product])
            mock_attr_method.assert_called_with(basket, self.request)

    def test_attribute_cookie_data_affiliate_cookie_lifecycle(self):
        """ Verify a basket is returned and referral captured if there is cookie info """

        # If there is no cookie info, verify no referral is created.
        basket = BasketFactory(owner=self.request.user, site=self.request.site)
        attribute_cookie_data(basket, self.request)
        with self.assertRaises(Referral.DoesNotExist):
            Referral.objects.get(basket=basket)

        # If there is cookie info, verify a referral is captured
        affiliate_id = 'test_affiliate'
        self.request.COOKIES['affiliate_id'] = affiliate_id
        attribute_cookie_data(basket, self.request)
        # test affiliate id from cookie saved in referral
        referral = Referral.objects.get(basket_id=basket.id)
        self.assertEqual(referral.affiliate_id, affiliate_id)

        # update cookie
        new_affiliate_id = 'new_affiliate'
        self.request.COOKIES['affiliate_id'] = new_affiliate_id
        attribute_cookie_data(basket, self.request)

        # test new affiliate id saved
        referral = Referral.objects.get(basket_id=basket.id)
        self.assertEqual(referral.affiliate_id, new_affiliate_id)

        # expire cookie
        del self.request.COOKIES['affiliate_id']
        attribute_cookie_data(basket, self.request)

        # test referral record is deleted when no cookie set
        with self.assertRaises(Referral.DoesNotExist):
            Referral.objects.get(basket_id=basket.id)

    def test_attribute_cookie_data_utm_cookie_lifecycle(self):
        """ Verify a basket is returned and referral captured. """
        utm_source = 'test-source'
        utm_medium = 'test-medium'
        utm_campaign = 'test-campaign'
        utm_term = 'test-term'
        utm_content = 'test-content'
        utm_created_at = 1475590280823
        expected_created_at = datetime.datetime.fromtimestamp(int(utm_created_at) / float(1000), tz=pytz.UTC)

        utm_cookie = {
            'utm_source': utm_source,
            'utm_medium': utm_medium,
            'utm_campaign': utm_campaign,
            'utm_term': utm_term,
            'utm_content': utm_content,
            'created_at': utm_created_at,
        }

        self.request.COOKIES['test.edx.utm'] = json.dumps(utm_cookie)
        basket = BasketFactory(owner=self.request.user, site=self.request.site)
        attribute_cookie_data(basket, self.request)

        # test utm data from cookie saved in referral
        referral = Referral.objects.get(basket_id=basket.id)
        self.assertEqual(referral.utm_source, utm_source)
        self.assertEqual(referral.utm_medium, utm_medium)
        self.assertEqual(referral.utm_campaign, utm_campaign)
        self.assertEqual(referral.utm_term, utm_term)
        self.assertEqual(referral.utm_content, utm_content)
        self.assertEqual(referral.utm_created_at, expected_created_at)

        # update cookie
        utm_source = 'test-source-new'
        utm_medium = 'test-medium-new'
        utm_campaign = 'test-campaign-new'
        utm_term = 'test-term-new'
        utm_content = 'test-content-new'
        utm_created_at = 1470590000000
        expected_created_at = datetime.datetime.fromtimestamp(int(utm_created_at) / float(1000), tz=pytz.UTC)

        new_utm_cookie = {
            'utm_source': utm_source,
            'utm_medium': utm_medium,
            'utm_campaign': utm_campaign,
            'utm_term': utm_term,
            'utm_content': utm_content,
            'created_at': utm_created_at,
        }
        self.request.COOKIES['test.edx.utm'] = json.dumps(new_utm_cookie)
        attribute_cookie_data(basket, self.request)

        # test new utm data saved
        referral = Referral.objects.get(basket_id=basket.id)
        self.assertEqual(referral.utm_source, utm_source)
        self.assertEqual(referral.utm_medium, utm_medium)
        self.assertEqual(referral.utm_campaign, utm_campaign)
        self.assertEqual(referral.utm_term, utm_term)
        self.assertEqual(referral.utm_content, utm_content)
        self.assertEqual(referral.utm_created_at, expected_created_at)

        # expire cookie
        del self.request.COOKIES['test.edx.utm']
        attribute_cookie_data(basket, self.request)

        # test referral record is deleted when no cookie set
        with self.assertRaises(Referral.DoesNotExist):
            Referral.objects.get(basket_id=basket.id)

    def test_attribute_cookie_data_multiple_cookies(self):
        """ Verify a basket is returned and referral captured. """
        utm_source = 'test-source'
        utm_medium = 'test-medium'
        utm_campaign = 'test-campaign'
        utm_term = 'test-term'
        utm_content = 'test-content'
        utm_created_at = 1475590280823

        utm_cookie = {
            'utm_source': utm_source,
            'utm_medium': utm_medium,
            'utm_campaign': utm_campaign,
            'utm_term': utm_term,
            'utm_content': utm_content,
            'created_at': utm_created_at,
        }

        affiliate_id = 'affiliate'

        self.request.COOKIES['test.edx.utm'] = json.dumps(utm_cookie)
        self.request.COOKIES['affiliate_id'] = affiliate_id
        basket = BasketFactory(owner=self.request.user, site=self.request.site)
        attribute_cookie_data(basket, self.request)

        # test affiliate id & UTM data from cookie saved in referral
        referral = Referral.objects.get(basket_id=basket.id)
        expected_created_at = datetime.datetime.fromtimestamp(int(utm_created_at) / float(1000), tz=pytz.UTC)
        self.assertEqual(referral.utm_source, utm_source)
        self.assertEqual(referral.utm_medium, utm_medium)
        self.assertEqual(referral.utm_campaign, utm_campaign)
        self.assertEqual(referral.utm_term, utm_term)
        self.assertEqual(referral.utm_content, utm_content)
        self.assertEqual(referral.utm_created_at, expected_created_at)
        self.assertEqual(referral.affiliate_id, affiliate_id)

        # expire 1 cookie
        del self.request.COOKIES['test.edx.utm']
        attribute_cookie_data(basket, self.request)

        # test affiliate id still saved in referral but utm data removed
        referral = Referral.objects.get(basket_id=basket.id)
        self.assertEqual(referral.utm_source, '')
        self.assertEqual(referral.utm_medium, '')
        self.assertEqual(referral.utm_campaign, '')
        self.assertEqual(referral.utm_term, '')
        self.assertEqual(referral.utm_content, '')
        self.assertIsNone(referral.utm_created_at)
        self.assertEqual(referral.affiliate_id, affiliate_id)

        # expire other cookie
        del self.request.COOKIES['affiliate_id']
        attribute_cookie_data(basket, self.request)

        # test referral record is deleted when no cookies are set
        with self.assertRaises(Referral.DoesNotExist):
            Referral.objects.get(basket_id=basket.id)

    def test_prepare_basket_raises_exception_for_purchased_product(self):
        """
        Test prepare_basket raises AlreadyPlacedOrderException if the product is already purchased by user
        """
        product = ProductFactory()
        with mock.patch.object(UserAlreadyPlacedOrder, 'user_already_placed_order', return_value=True):
            with self.assertRaises(AlreadyPlacedOrderException):
                prepare_basket(self.request, [product])

    def test_prepare_basket_for_purchased_enrollment_code(self):
        """
        Test prepare_basket returns basket with product even if its already been purchased by user
        """
        course = CourseFactory()
        toggle_switch(ENROLLMENT_CODE_SWITCH, True)
        course.create_or_update_seat('verified', False, 10, self.partner, create_enrollment_code=True)
        enrollment_code = Product.objects.get(product_class__name=ENROLLMENT_CODE_PRODUCT_CLASS_NAME)
        with mock.patch.object(UserAlreadyPlacedOrder, 'user_already_placed_order', return_value=True):
            basket = prepare_basket(self.request, [enrollment_code])
            self.assertIsNotNone(basket)


class BasketUtilsTransactionTests(UserMixin, TransactionTestCase):
    def setUp(self):
        super(BasketUtilsTransactionTests, self).setUp()
        self.request = RequestFactory()
        self.request.COOKIES = {}
        self.request.user = self.create_user()
        site_configuration = SiteConfigurationFactory(partner__name='Tester')
        site_configuration.utm_cookie_name = 'test.edx.utm'
        self.request.site = site_configuration.site

    def _setup_request_cookie(self):
        utm_campaign = 'test-campaign'
        utm_content = 'test-content'
        utm_created_at = 1475590280823

        utm_cookie = {
            'utm_campaign': utm_campaign,
            'utm_content': utm_content,
            'created_at': utm_created_at,
        }

        affiliate_id = 'affiliate'

        self.request.COOKIES['test.edx.utm'] = json.dumps(utm_cookie)
        self.request.COOKIES['affiliate_id'] = affiliate_id

    def test_attribution_atomic_transaction(self):
        """
        Verify that an IntegrityError raised while creating a referral
        does not prevent a basket from being created.
        """
        self._setup_request_cookie()
        product = ProductFactory()
        existing_basket = Basket.get_basket(self.request.user, self.request.site)
        existing_referral = Referral(basket=existing_basket, site=self.request.site)
        # Let's save an existing referral object to force the duplication happen in database
        existing_referral.save()

        with transaction.atomic():
            with mock.patch('ecommerce.extensions.basket.utils._referral_from_basket_site') as mock_get_referral:
                # Mock to return a duplicated referral object, so when saved, a DB integrity error is raised
                # Mocking with side_effect to raise IntegrityError will not roll back the DB transaction
                # We actually would handle the exception in the attribute_cookie_data method.
                # Only causing the true database conflict like what we are doing here, would cause the roll back
                mock_get_referral.return_value = Referral(basket=existing_basket, site=self.request.site)
                basket = prepare_basket(self.request, [product])
                referral = Referral.objects.filter(basket=basket)

        self.assertEqual(len(referral), 1)
        self.assertIsNotNone(basket)
        self.assertTrue(basket.id > 0)
        self.assertEqual(basket.status, Basket.OPEN)
        self.assertEqual(basket.lines.count(), 1)
        self.assertEqual(basket.lines.first().product, product)
