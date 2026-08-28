from rest_framework import serializers


class CashPurchaseSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=['apple'])
    signed_transaction_info = serializers.CharField(
        max_length=20000,
        help_text="StoreKit 2 signed transaction JWS",
    )
    product_id = serializers.CharField(help_text="Product ID (e.g., cash_1000)")

    def to_internal_value(self, data):
        # Keep one release of compatibility with the existing Flutter payload:
        # `store` was sent instead of `platform`, and StoreKit 2 JWS was named
        # `receipt_data`. Legacy app receipts still fail cryptographic JWS
        # verification; this only aliases field names.
        if isinstance(data, dict):
            data = data.copy()
            data.setdefault('platform', data.get('store'))
            data.setdefault('signed_transaction_info', data.get('receipt_data'))
        return super().to_internal_value(data)


class LectureRentalSerializer(serializers.Serializer):
    lecture_id = serializers.IntegerField(help_text="Lecture ID to rent")


class RedeemCouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50, trim_whitespace=True)
