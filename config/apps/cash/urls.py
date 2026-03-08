from django.urls import path
from .views import PurchaseCashView

app_name = 'cash'

urlpatterns = [
    path('purchase/', PurchaseCashView.as_view(), name='purchase'),
]
