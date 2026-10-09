from django.urls import path

from .views import TicketAttachmentView, TicketDetailView, TicketListCreateView, TicketMessageView

urlpatterns = [
    path("tickets/", TicketListCreateView.as_view(), name="support-ticket-list-create"),
    path("tickets/<int:pk>/", TicketDetailView.as_view(), name="support-ticket-detail"),
    path("tickets/<int:pk>/messages/", TicketMessageView.as_view(), name="support-ticket-message"),
    path("tickets/<int:pk>/attachments/<int:attachment_id>/", TicketAttachmentView.as_view(), name="support-ticket-attachment"),
]
