from rest_framework import serializers

from .models import TutoringSubmission


class PaybackAccountInputSerializer(serializers.Serializer):
    bankCode = serializers.CharField(source="bank_code", max_length=20)
    accountNumber = serializers.CharField(
        source="account_number", max_length=50, trim_whitespace=True
    )
    accountHolder = serializers.CharField(source="account_holder", max_length=30)

    def validate_account_number(self, value):
        compact = value.replace("-", "").replace(" ", "")
        if not compact.isdigit():
            raise serializers.ValidationError("계좌번호는 숫자만 입력해주세요.")
        return compact


class MyRegistrationInputSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=100)
    startDate = serializers.DateField(source="start_date")
    classType = serializers.ChoiceField(
        source="class_type", choices=TutoringSubmission.ClassType.choices
    )
    firstMonthFee = serializers.IntegerField(source="first_month_fee", min_value=1)
    paybackAccount = PaybackAccountInputSerializer(
        source="payback_account", required=False
    )

    def validate(self, attrs):
        if self.context.get("role") == TutoringSubmission.Role.STUDENT:
            if "payback_account" not in attrs:
                raise serializers.ValidationError(
                    {"paybackAccount": "학생은 페이백 계좌 정보를 입력해야 합니다."}
                )
        elif "payback_account" in attrs:
            raise serializers.ValidationError(
                {"paybackAccount": "강사 등록에는 페이백 계좌 정보를 입력할 수 없습니다."}
            )
        return attrs
