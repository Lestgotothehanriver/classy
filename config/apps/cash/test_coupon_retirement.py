from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from .models import Coupon, CashLot


class CouponRetirementTests(APITestCase):
    def test_old_clients_cannot_credit_a_valid_coupon(self):
        user = get_user_model().objects.create_user(username='coupon-test', email='coupon@example.com', user_name='coupon-test', cash=500)
        coupon = Coupon.objects.create(code='VALIDCOUPON', cash_amount=10000)
        self.client.force_authenticate(user)
        response = self.client.post('/cash/coupons/redeem/', {'code': coupon.code})
        self.assertEqual(response.status_code, 410)
        user.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(user.cash, 500)
        self.assertIsNone(coupon.redeemed_by_id)
        self.assertFalse(CashLot.objects.filter(user=user).exists())
