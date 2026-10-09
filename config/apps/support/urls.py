from django.urls import path

from .views import PaybackPayoutDetailView, TicketAttachmentView, TicketContextView, TicketDetailView, TicketListCreateView, TicketMessageView, TicketReadView

urlpatterns = [
    path("tickets/", TicketListCreateView.as_view(), name="support-ticket-list-create"),
    path("ticket-context/", TicketContextView.as_view(), name="support-ticket-context"),
    path("payback-payouts/<int:registration_id>/", PaybackPayoutDetailView.as_view(), name="support-payback-payout-detail"),
    path("tickets/<int:pk>/", TicketDetailView.as_view(), name="support-ticket-detail"),
    path("tickets/<int:pk>/messages/", TicketMessageView.as_view(), name="support-ticket-message"),
    path("tickets/<int:pk>/read/", TicketReadView.as_view(), name="support-ticket-read"),
    path("tickets/<int:pk>/attachments/<int:attachment_id>/", TicketAttachmentView.as_view(), name="support-ticket-attachment"),
]
