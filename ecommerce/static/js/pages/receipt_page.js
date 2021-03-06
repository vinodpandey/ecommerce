/**
 * Basket page scripts.
 **/

define([
        'jquery'
    ],
    function ($) {
        'use strict';

        function trackPurchase(order_id, total_amount, currency) {
            window.analytics.track('Order Completed', {
                orderId: order_id,
                total: total_amount,
                currency: currency
            });
        }

        function onReady() {
            var el = $('#receipt-container'),
                order_id = el.data('order-id'),
                total_amount = el.data('total-amount'),
                currency = el.data('currency');
            if (order_id) {
                trackPurchase(order_id, total_amount, currency);
            }
        }

        $(document).ready(onReady);

        return {
            onReady: onReady
        };
    }
);
