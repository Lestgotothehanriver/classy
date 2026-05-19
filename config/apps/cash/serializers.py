from rest_framework import serializers


class CashPurchaseSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=['apple', 'google'])
    receipt_data = serializers.CharField(required=False, help_text="Apple receipt data")
    purchase_token = serializers.CharField(required=False, help_text="Google purchase token")
    product_id = serializers.CharField(help_text="Product ID (e.g., cash_1000)")

    def validate(self, data):
        platform = data.get('platform')
        if platform == 'apple' and not data.get('receipt_data'):
            raise serializers.ValidationError(
                "receipt_data is required for Apple purchases."
            )
        if platform == 'google' and not data.get('purchase_token'):
            raise serializers.ValidationError(
                "purchase_token is required for Google purchases."
            )
        return data


class LectureRentalSerializer(serializers.Serializer):
    lecture_id = serializers.IntegerField(help_text="Lecture ID to rent")


class RedeemCouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50, trim_whitespace=True)
