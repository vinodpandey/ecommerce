from oscar.test import factories

from ecommerce.extensions.fulfillment.status import ORDER, LINE


class FulfillmentTestMixin(object):
    def generate_open_order(self):
        """ Returns an open order, ready to be fulfilled. """
        return factories.create_order(status=ORDER.OPEN)

    def assert_order_fulfilled(self, order):
        """
        Verifies that an order has been fulfilled.

        An order is considered fulfilled if ALL of the following are true:
            * The order's status is COMPLETE.
            * The order's lines' statuses are COMPLETE.
        """
        self.assertEqual(order.status, ORDER.COMPLETE)
        self.assertSetEqual(set(order.lines.values_list('status', flat=True)), set([LINE.COMPLETE]))
