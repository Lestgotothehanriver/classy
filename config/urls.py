"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.conf import settings
from django.views.static import serve
from config.apps.notification.views import DeviceTokenAPIView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("config.apps.accounts.urls")),
    path("pending/", include("config.apps.pending.urls")),
    path("tutoring/", include("config.apps.tutoring.urls")),
    path("cash/", include("config.apps.cash.urls")),
    path("lectures/", include("config.apps.lecture.urls")),
    path("report/", include("config.apps.report.urls")),
    path("main/", include("config.apps.main.urls")),
    path("mypage/", include("config.apps.mypage.urls")),
    # FCM device token endpoints must resolve to notification.DeviceToken,
    # not the legacy chat_app token model.
    path("device-token/", DeviceTokenAPIView.as_view()),
    path("", include("config.apps.chat_app.urls")),
    path("notification/", include("config.apps.notification.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # DEBUG=False 환경(테스트 등)에서도 로컬 미디어를 제공하기 위한 fallback
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
