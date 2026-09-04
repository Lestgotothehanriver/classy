from rest_framework import serializers


class CashPurchaseSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=['apple', 'google'])
    signed_transaction_info = serializers.CharField(
        max_length=20000,
        required=False,
        help_text="StoreKit 2 signed transaction JWS",
    )
    purchase_token = serializers.CharField(
        max_length=10000,
        required=False,
        trim_whitespace=False,
        help_text="Google Play purchase token",
    )
    product_id = serializers.CharField(help_text="Product ID (e.g., cash_1000)")

    def to_internal_value(self, data):
        # Keep one release of compatibility with the existing Flutter payload:
        # `store` was sent instead of `platform`, and StoreKit 2 JWS was named
        # `receipt_data`. Legacy app receipts still fail cryptographic JWS
        # verification; this only aliases field names.
        if isinstance(data, dict):
            data = data.copy()
            if 'platform' not in data and data.get('store') is not None:
                data['platform'] = data.get('store')
            if (
                'signed_transaction_info' not in data
                and data.get('receipt_data') is not None
            ):
                data['signed_transaction_info'] = data.get('receipt_data')
        values = super().to_internal_value(data)
        platform = values['platform']
        if platform == 'apple' and not values.get('signed_transaction_info'):
            raise serializers.ValidationError({
                'signed_transaction_info': 'This field is required for Apple purchases.',
            })
        if platform == 'google' and not values.get('purchase_token'):
            raise serializers.ValidationError({
                'purchase_token': 'This field is required for Google purchases.',
            })
        return values


class LectureRentalSerializer(serializers.Serializer):
    lecture_id = serializers.IntegerField(help_text="Lecture ID to rent")


class RedeemCouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50, trim_whitespace=True)
