from django.contrib import admin
from django import forms
from django.shortcuts import redirect
from django.urls import path
from django.contrib import messages

from config.apps.chat_app.notifications import push_to_all


class AnnouncementForm(forms.Form):
    title = forms.CharField(label="제목", max_length=100)
    body = forms.CharField(label="내용", widget=forms.Textarea)


class NotificationAdmin(admin.AdminSite):
    pass


# Django Admin 커스텀 뷰로 공지 발송 폼 추가
class AnnouncementAdminView(admin.ModelAdmin):
    pass


# Admin 사이트에 공지 발송 페이지를 추가하는 방법:
# admin/notification/announce/ 에서 POST 하면 push_to_all 호출
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views import View
from django.shortcuts import render


@method_decorator(staff_member_required, name="dispatch")
class AdminAnnouncementView(View):
    template_name = "admin/notification/announce.html"

    def get(self, request):
        form = AnnouncementForm()
        return render(request, self.template_name, {"form": form, "title": "공지 푸시 발송"})

    def post(self, request):
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            result = push_to_all(
                title=form.cleaned_data["title"],
                body=form.cleaned_data["body"],
                data={"type": "announcement"},
            )
            messages.success(
                request,
                f"발송 완료 — 성공: {result['success']}, 실패: {result['failure']}"
            )
            return redirect("admin:announce")
        return render(request, self.template_name, {"form": form, "title": "공지 푸시 발송"})
