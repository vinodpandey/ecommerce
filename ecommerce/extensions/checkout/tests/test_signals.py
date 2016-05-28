import httpretty
from django.conf import settings
from django.core import mail
from oscar.test.newfactories import BasketFactory

from ecommerce.core.tests import toggle_switch
from ecommerce.courses.models import Course
from ecommerce.extensions.catalogue.tests.mixins import CourseCatalogTestMixin
from ecommerce.extensions.checkout.signals import send_course_purchase_email
from ecommerce.extensions.test.factories import create_order
from ecommerce.tests.testcases import TestCase


class SignalTests(CourseCatalogTestMixin, TestCase):
    def setUp(self):
        super(SignalTests, self).setUp()
        self.user = self.create_user()

    @httpretty.activate
    def test_post_checkout_callback(self):
        """
        When the post_checkout signal is emitted, the receiver should attempt
        to fulfill the newly-placed order and send receipt email.
        """
        httpretty.register_uri(
            httpretty.GET, self.site.siteconfiguration.build_lms_url('api/credit/v1/providers/ASU'),
            body='{"display_name": "Hogwarts"}',
            content_type="application/json"
        )
        toggle_switch('ENABLE_NOTIFICATIONS', True)
        course = Course.objects.create(id='edX/DemoX/Demo_Course', name='Demo Course')
        seat = course.create_or_update_seat('credit', False, 50, self.partner, 'ASU', None, 2)

        basket = BasketFactory(site=self.site)
        basket.add_product(seat, 1)
        order = create_order(number=1, basket=basket, user=self.user)
        send_course_purchase_email(None, order=order)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.site.siteconfiguration.from_email)
        self.assertEqual(mail.outbox[0].subject, 'Order Receipt')

        path = '{}?orderNum={}'.format(settings.RECEIPT_PAGE_PATH, order.number)
        receipt_url = self.site.siteconfiguration.build_lms_url(path)
        self.assertEqual(
            mail.outbox[0].body,
            '\nPayment confirmation for: {course_title}'
            '\n\nDear {full_name},'
            '\n\nThank you for purchasing {credit_hours} credit hours from {credit_provider} for {course_title}. '
            'A charge will appear on your credit or debit card statement with a company name of "{platform_name}".'
            '\n\nTo receive your course credit, you must also request credit at the {credit_provider} website. '
            'For a link to request credit from {credit_provider}, or to see the status of your credit request, '
            'go to your {platform_name} dashboard.'
            '\n\nTo explore other credit-eligible courses, visit the {platform_name} website. '
            'We add new courses frequently!'
            '\n\nTo view your payment information, visit the following website.'
            '\n{receipt_url}'
            '\n\nThank you. We hope you enjoyed your course!'
            '\nThe {platform_name} team'
            '\n\nYou received this message because you purchased credit hours for {course_title}, '
            'an {platform_name} course.\n'.format(
                course_title=order.lines.first().product.title,
                full_name=self.user.get_full_name(),
                credit_hours=2,
                credit_provider='Hogwarts',
                platform_name=order.site.name,
                receipt_url=receipt_url
            )
        )
