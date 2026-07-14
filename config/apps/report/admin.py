from django.contrib import admin

from .models import Report, ReportChoice, Inquiry


class ReportChoiceInline(admin.TabularInline):
    model = ReportChoice
    extra = 0
    readonly_fields = ("content",)

@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "is_resolved", "created_at")
    list_filter = ("is_resolved", "created_at")
    search_fields = ("user__email", "title", "content")
    readonly_fields = ("created_at",)
    list_editable = ("is_resolved",)

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "reporter", "reported_user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("reporter__username", "reported_user__username")
    readonly_fields = ("created_at",)
    inlines = [ReportChoiceInline]


@admin.register(ReportChoice)
class ReportChoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "report", "content")
    list_filter = ("content",)
