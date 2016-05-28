from django.test import override_settings
from django.test.client import RequestFactory

from ecommerce.core.context_processors import core
from ecommerce.tests.testcases import TestCase

SUPPORT_URL = 'example.com'


class CoreContextProcessorTests(TestCase):
    @override_settings(SUPPORT_URL=SUPPORT_URL)
    def test_core(self):
        request = RequestFactory()
        request.site = self.site

        self.assertDictEqual(
            core(request),
            {
                'lms_base_url': request.site.siteconfiguration.build_lms_url(),
                'lms_dashboard_url': request.site.siteconfiguration.student_dashboard_url,
                'platform_name': request.site.name,
                'support_url': SUPPORT_URL
            }
        )
