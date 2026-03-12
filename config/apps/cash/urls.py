from django.urls import path
from .views import (
    PurchaseCashView,
    RentLectureView,
    CancelLectureRentalView,
    RefundPurchaseView,
    GooglePlayWebhookView
)

app_name = 'cash'

urlpatterns = [
    path('purchase/', PurchaseCashView.as_view(), name='purchase'),
    path('webhook/apple/', RefundPurchaseView.as_view(), name='apple-webhook'),
    path('webhook/google/', GooglePlayWebhookView.as_view(), name='google-webhook'),
    path('rentals/', RentLectureView.as_view(), name='lecture-rent'),
    path('rentals/<int:pk>/cancel/', CancelLectureRentalView.as_view(), name='lecture-rent-cancel'),
]
