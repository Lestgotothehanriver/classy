from rest_framework import serializers

from config.apps.accounts.models import Subject

from .models import TutoringSubmission


class PaybackAccountInputSerializer(serializers.Serializer):
    bankCode = serializers.CharField(source="bank_code", max_length=20)
    accountNumber = serializers.CharField(
        source="account_number", max_length=50, trim_whitespace=True
    )
    accountHolder = serializers.CharField(source="account_holder", max_length=30)

    def validate(self, attrs):
        value = attrs["account_number"]
        compact = value.replace("-", "").replace(" ", "")
        if not compact.isdigit():
            raise serializers.ValidationError(
                {"accountNumber": "계좌번호는 숫자만 입력해주세요."}
            )
        attrs["account_number"] = compact
        return attrs


class MyRegistrationInputSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=100)
    subjectIds = serializers.ListField(
        source="subject_ids",
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=3,
    )
    startDate = serializers.DateField(source="start_date")
    classType = serializers.ChoiceField(
        source="class_type", choices=TutoringSubmission.ClassType.choices
    )
    firstMonthFee = serializers.IntegerField(source="first_month_fee", min_value=1)
    paybackAccount = PaybackAccountInputSerializer(
        source="payback_account", required=False
    )

    def validate(self, attrs):
        subject_ids = list(dict.fromkeys(attrs["subject_ids"]))
        if Subject.objects.filter(number__in=subject_ids).count() != len(subject_ids):
            raise serializers.ValidationError(
                {"subjectIds": "존재하지 않는 과목이 포함되어 있습니다."}
            )
        attrs["subject_ids"] = subject_ids

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
