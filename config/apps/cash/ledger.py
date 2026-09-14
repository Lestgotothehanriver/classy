"""Cash-lot creation, debit, and external-refund application services."""

from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from .models import CashLot, CashLotUsage, PurchaseHistory


def create_paid_lot(purchase: PurchaseHistory) -> CashLot:
    """Create the one paid lot associated with a verified store purchase."""
    lot, _ = CashLot.objects.get_or_create(
        purchase_history=purchase,
        defaults={
            'user': purchase.user,
            'source': CashLot.Source.PAID,
            'original_cash': purchase.purchased_cash,
            'available_cash': purchase.purchased_cash,
        },
    )
    return lot


def create_coupon_lot(*, user, amount: int) -> CashLot:
    """Create a non-refundable lot after a coupon redemption."""
    return CashLot.objects.create(
        user=user,
        source=CashLot.Source.COUPON,
        original_cash=amount,
        available_cash=amount,
    )


def debit_lots_for_rental(*, user, rental, amount: int) -> None:
    """Debit non-refundable lots first, then paid lots FIFO, under row locks."""
    source_order = Case(
        When(source=CashLot.Source.LEGACY, then=Value(0)),
        When(source=CashLot.Source.COUPON, then=Value(1)),
        When(source=CashLot.Source.PROMOTION, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    lots = list(
        CashLot.objects.select_for_update()
        .filter(user=user, status=CashLot.Status.ACTIVE, available_cash__gt=0)
        .annotate(source_priority=source_order)
        .order_by('source_priority', 'created_at', 'pk')
    )
    remaining = amount
    for lot in lots:
        if remaining == 0:
            break
        used = min(lot.available_cash, remaining)
        lot.available_cash -= used
        lot.status = (
            CashLot.Status.USED if lot.available_cash == 0 else CashLot.Status.ACTIVE
        )
        lot.save(update_fields=['available_cash', 'status', 'updated_at'])
        CashLotUsage.objects.create(cash_lot=lot, rental=rental, used_cash=used)
        remaining -= used
    if remaining:
        raise ValueError('Cash lot balance is insufficient.')


def apply_external_refund(purchase: PurchaseHistory) -> str:
    """Recover an entirely unused paid lot without creating cash debt."""
    purchase = PurchaseHistory.objects.select_for_update().get(pk=purchase.pk)
    if purchase.is_refunded:
        return 'already_refunded'
    try:
        lot = CashLot.objects.select_for_update().get(purchase_history=purchase)
    except CashLot.DoesNotExist:
        purchase.refund_status = 'manual_review'
        purchase.refund_reason = 'legacy_purchase'
        purchase.save(update_fields=['refund_status', 'refund_reason'])
        return 'manual_review'

    if lot.available_cash != lot.original_cash:
        purchase.refund_status = 'manual_review'
        purchase.refund_reason = 'cash_already_used'
        purchase.save(update_fields=['refund_status', 'refund_reason'])
        return 'manual_review'

    user = type(purchase.user).objects.select_for_update().get(pk=purchase.user_id)
    user.cash -= lot.available_cash
    user.save(update_fields=['cash'])
    lot.available_cash = 0
    lot.status = CashLot.Status.REFUNDED
    lot.save(update_fields=['available_cash', 'status', 'updated_at'])
    purchase.is_refunded = True
    purchase.refunded_at = timezone.now()
    purchase.refund_percentage = 100000
    purchase.refunded_cash = purchase.purchased_cash
    purchase.refund_debt = 0
    purchase.refund_status = 'refunded'
    purchase.refund_reason = ''
    purchase.save(update_fields=[
        'is_refunded', 'refunded_at', 'refund_percentage', 'refunded_cash',
        'refund_debt', 'refund_status', 'refund_reason',
    ])
    return 'refunded'


def reverse_external_refund(purchase: PurchaseHistory) -> str:
    """Restore only a lot that this service had previously fully recovered."""
    purchase = PurchaseHistory.objects.select_for_update().get(pk=purchase.pk)
    try:
        lot = CashLot.objects.select_for_update().get(purchase_history=purchase)
    except CashLot.DoesNotExist:
        return 'purchase_not_found'
    if lot.status != CashLot.Status.REFUNDED:
        return 'refund_not_applied'
    user = type(purchase.user).objects.select_for_update().get(pk=purchase.user_id)
    user.cash += lot.original_cash
    user.save(update_fields=['cash'])
    lot.available_cash = lot.original_cash
    lot.status = CashLot.Status.ACTIVE
    lot.save(update_fields=['available_cash', 'status', 'updated_at'])
    purchase.is_refunded = False
    purchase.refunded_at = None
    purchase.refund_percentage = 0
    purchase.refunded_cash = 0
    purchase.refund_status = 'not_requested'
    purchase.refund_reason = ''
    purchase.save(update_fields=[
        'is_refunded', 'refunded_at', 'refund_percentage', 'refunded_cash',
        'refund_status', 'refund_reason',
    ])
    return 'refund_reversed'
