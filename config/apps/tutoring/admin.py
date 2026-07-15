from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from config.apps.tutoring.models import (
    Region,
    TutoringPost,
    TutoringProposal,
    InstructorInfo,
    InstructorReview,
    StudentReview,
    TutoringResource,
    TutoringResourceFile,
    CommissionInvoice,
    StudentPaybackAccount,
    TutoringRegistration,
    TutoringSubmission,
)


# ── Region ────────────────────────────────────────────────────────────────────
@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("id", "number", "__str__")
    ordering     = ("number",)


# ── TutoringPost ──────────────────────────────────────────────────────────────
@admin.register(TutoringPost)
class TutoringPostAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_student", "method", "sex", "field", "cost", "view_count", "is_active")
    list_filter   = ("is_active", "method", "sex", "field")
    search_fields = ("title", "student__user__username", "student__user__email", "region")
    ordering      = ("-id",)

    def get_student(self, obj):
        return obj.student.user.username
    get_student.short_description = "학생"


# ── TutoringProposal ──────────────────────────────────────────────────────────
@admin.register(TutoringProposal)
class TutoringProposalAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_instructor", "get_post_title", "get_student")
    search_fields = (
        "instructor__user__username",
        "tutoring_post__title",
        "tutoring_post__student__user__username",
    )
    ordering = ("-id",)

    def get_instructor(self, obj):
        return obj.instructor.user.username
    get_instructor.short_description = "강사"

    def get_post_title(self, obj):
        return obj.tutoring_post.title
    get_post_title.short_description = "공고 제목"

    def get_student(self, obj):
        return obj.tutoring_post.student.user.username
    get_student.short_description = "학생"


# ── InstructorInfo ────────────────────────────────────────────────────────────
@admin.register(InstructorInfo)
class InstructorInfoAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_instructor", "method", "cost", "location")
    list_filter   = ("method",)
    search_fields = ("instructor__user__username", "instructor__user__email", "location")
    ordering      = ("-id",)

    def get_instructor(self, obj):
        return obj.instructor.user.username
    get_instructor.short_description = "강사"


# ── InstructorReview ──────────────────────────────────────────────────────────
@admin.register(InstructorReview)
class InstructorReviewAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_instructor", "get_student", "professionalism", "teaching_skill", "punctuality")
    list_filter   = ("professionalism", "teaching_skill", "punctuality")
    search_fields = (
        "instructor__user__username",
        "student__user__username",
        "comment",
    )
    ordering      = ("-id",)

    def get_instructor(self, obj):
        return obj.instructor.user.username
    get_instructor.short_description = "강사"

    def get_student(self, obj):
        return obj.student.user.username
    get_student.short_description = "학생"


# ── StudentReview ─────────────────────────────────────────────────────────────
@admin.register(StudentReview)
class StudentReviewAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_student", "get_instructor", "rating")
    list_filter   = ("rating",)
    search_fields = (
        "student__user__username",
        "instructor__user__username",
        "comment",
    )
    ordering      = ("-id",)

    def get_student(self, obj):
        return obj.student.user.username
    get_student.short_description = "학생"

    def get_instructor(self, obj):
        return obj.instructor.user.username
    get_instructor.short_description = "강사"


# ── TutoringResource ──────────────────────────────────────────────────────────

@admin.action(description='수수료 납부 확인 (PAID 처리 + 강사 알림)')
def confirm_fee_payment(modeladmin, request, queryset):
    from config.apps.notification.helpers import notify_fee_payment_confirmed
    from config.apps.tutoring.registration_services import refresh_contract_status

    updated = 0
    for resource in queryset.filter(fee_payment_status='AWAITING_CONFIRMATION'):
        resource.fee_payment_status = 'PAID'
        resource.save(update_fields=['fee_payment_status'])
        registration = getattr(resource, 'registration', None)
        if registration:
            invoice = registration.commission_invoices.filter(
                invoice_type=CommissionInvoice.InvoiceType.INITIAL
            ).first()
            if invoice:
                invoice.status = CommissionInvoice.Status.PAID
                invoice.paid_at = timezone.now()
                invoice.save(update_fields=['status', 'paid_at', 'updated_at'])
            contract_status = refresh_contract_status(registration)
            if contract_status == TutoringRegistration.ContractStatus.ACTIVE:
                notify_fee_payment_confirmed(resource)
        else:
            notify_fee_payment_confirmed(resource)
        updated += 1
    modeladmin.message_user(
        request,
        f'{updated}건 입금 확인 완료. 양측 정보가 일치한 계약만 성사 완료 처리했습니다.',
    )


@admin.action(description='수수료 납부 실패 처리 (FAILED)')
def reject_fee_payment(modeladmin, request, queryset):
    resources = queryset.filter(
        fee_payment_status__in=['PENDING', 'AWAITING_CONFIRMATION']
    )
    updated = resources.update(fee_payment_status='FAILED')
    CommissionInvoice.objects.filter(
        registration__resource__in=resources,
        status__in=[
            CommissionInvoice.Status.READY,
            CommissionInvoice.Status.PAYMENT_PENDING,
        ],
    ).update(status=CommissionInvoice.Status.FAILED)
    modeladmin.message_user(request, f'{updated}건 FAILED 처리 완료.')


@admin.register(TutoringResource)
class TutoringResourceAdmin(admin.ModelAdmin):
    list_display  = (
        'id', 'get_instructor', 'get_student',
        'class_type', 'first_month_fee', 'get_expected_commission_amount',
        'fee_payment_status', 'start_date',
    )
    list_filter   = ('fee_payment_status', 'class_type')
    search_fields = (
        'instructor__user__username', 'instructor__user__email',
        'student__user__username',
    )
    ordering      = ('-id',)
    actions       = [confirm_fee_payment, reject_fee_payment]
    readonly_fields = (
        'fee_payment_status', 'fee_confirmation_file',
        'get_expected_commission_amount',
    )

    class TutoringResourceFileInline(admin.TabularInline):
        model = TutoringResourceFile
        extra = 0
        can_delete = False
        readonly_fields = ('file', 'uploaded_at')

        def has_add_permission(self, request, obj=None):
            return False

    inlines = [TutoringResourceFileInline]

    def get_instructor(self, obj):
        return obj.instructor.user.username
    get_instructor.short_description = '강사'

    def get_student(self, obj):
        return obj.student.user.username
    get_student.short_description = '학생'

    @admin.display(description='납부 예정 금액')
    def get_expected_commission_amount(self, obj):
        return f'{obj.expected_commission_amount:,}원'


admin.site.register(TutoringRegistration)
admin.site.register(TutoringSubmission)
admin.site.register(CommissionInvoice)


@admin.register(StudentPaybackAccount)
class StudentPaybackAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'get_student',
        'bank_code',
        'get_masked_account_number',
        'account_holder',
        'verification_status',
    )
    list_filter = ('verification_status', 'bank_code')
    search_fields = (
        'registration__student__username',
        'registration__student__user_name',
        'account_holder',
    )
    readonly_fields = (
        'registration',
        'bank_code',
        'get_account_number',
        'account_holder',
        'verified_at',
        'created_at',
        'updated_at',
    )
    fields = (
        'registration',
        'bank_code',
        'get_account_number',
        'account_holder',
        'verification_status',
        'verified_at',
        'created_at',
        'updated_at',
    )

    @admin.display(description='학생')
    def get_student(self, obj):
        return obj.registration.student.user_name

    def _account_number(self, obj):
        from config.apps.tutoring.registration_services import (
            decrypt_account_number,
        )

        try:
            return decrypt_account_number(obj.encrypted_account_number)
        except Exception:
            return '복호화 실패'

    @admin.display(description='계좌번호')
    def get_account_number(self, obj):
        return self._account_number(obj)

    @admin.display(description='계좌번호')
    def get_masked_account_number(self, obj):
        account_number = self._account_number(obj)
        if account_number == '복호화 실패' or len(account_number) <= 4:
            return account_number
        return f'****{account_number[-4:]}'

    def save_model(self, request, obj, form, change):
        if obj.verification_status == StudentPaybackAccount.VerificationStatus.VERIFIED:
            obj.verified_at = obj.verified_at or timezone.now()
        else:
            obj.verified_at = None
        super().save_model(request, obj, form, change)
