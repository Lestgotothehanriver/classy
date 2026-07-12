from django.urls import path
from .views import (
    InstructorAccountView,
    PurchaseCashView,
    RedeemCouponView,
    RentLectureView,
    CancelLectureRentalView,
    RefundPurchaseView,
    GooglePlayWebhookView,
    PurchaseHistoryListView,
    RentalHistoryListView,
    TossVirtualAccountWebhookView,
)

app_name = 'cash'

urlpatterns = [
    path('webhook/toss/', TossVirtualAccountWebhookView.as_view(), name='toss-webhook'),
    path('account/', InstructorAccountView.as_view(), name='instructor-account'),
    path('purchase/', PurchaseCashView.as_view(), name='purchase'),
    path('coupons/redeem/', RedeemCouponView.as_view(), name='coupon-redeem'),
    path('webhook/apple/', RefundPurchaseView.as_view(), name='apple-webhook'),
    path('webhook/google/', GooglePlayWebhookView.as_view(), name='google-webhook'),
    path('rentals/', RentLectureView.as_view(), name='lecture-rent'),
    path('rentals/<int:pk>/cancel/', CancelLectureRentalView.as_view(), name='lecture-rent-cancel'),
    path('purchase-history/', PurchaseHistoryListView.as_view(), name='purchase-history'),
    path('rental-history/', RentalHistoryListView.as_view(), name='rental-history'),
]
