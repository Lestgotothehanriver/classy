from django.db import migrations


def import_legacy_inquiries(apps, schema_editor):
    Inquiry = apps.get_model("report", "Inquiry")
    Ticket = apps.get_model("support", "SupportTicket")
    Message = apps.get_model("support", "SupportMessage")
    Event = apps.get_model("support", "SupportEvent")
    for inquiry in Inquiry.objects.all().iterator():
        if Ticket.objects.filter(ticket_type="LEGACY", title=inquiry.title, requester_id=inquiry.user_id, created_at=inquiry.created_at).exists():
            continue
        ticket = Ticket.objects.create(
            requester_id=inquiry.user_id,
            ticket_type="LEGACY",
            status="CLOSED" if inquiry.is_resolved else "RECEIVED",
            title=inquiry.title,
            requester_name="기존 문의 사용자",
            created_at=inquiry.created_at,
            updated_at=inquiry.created_at,
            closed_at=inquiry.created_at if inquiry.is_resolved else None,
            last_user_message_at=inquiry.created_at,
        )
        Message.objects.create(ticket=ticket, sender_id=inquiry.user_id, sender_kind="USER", content=inquiry.content, created_at=inquiry.created_at)
        Event.objects.create(ticket=ticket, event_type="ticket.legacy_imported", payload={"legacy_inquiry_id": inquiry.pk}, created_at=inquiry.created_at)


class Migration(migrations.Migration):
    dependencies = [("support", "0001_initial"), ("report", "0003_report_content_type_report_description_and_more")]
    operations = [migrations.RunPython(import_legacy_inquiries, migrations.RunPython.noop)]
