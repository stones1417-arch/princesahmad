from django.test import SimpleTestCase


class NotificationTestDiscoveryTests(SimpleTestCase):
    """
    اختبار بسيط للتأكد من أن Django يكتشف اختبارات التطبيق.
    """

    def test_notifications_tests_are_discovered(self):
        self.assertTrue(True)