import os
import dj_database_url
import environ
from .base import *

env = environ.Env(
    DEBUG=(bool, False)
)

# SECRET_KEY and DEBUG
SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')

# Render sets RENDER_EXTERNAL_HOSTNAME automatically
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')

# ALLOWED_HOSTS
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[
    'classystudy.com',
    'www.classystudy.com',
])
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Security settings
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[
    'https://classystudy.com',
    'https://www.classystudy.com',
])
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_EXTERNAL_HOSTNAME}')

# WhiteNoise Middleware for static files
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

# Database configuration
# Render will automatically inject DATABASE_URL into the environment.
# dj_database_url will automatically use DATABASE_URL.
DATABASES = {
    'default': dj_database_url.config(
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Static files
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Channel Layers (Redis for production)
REDIS_URL = env('REDIS_URL', default=None)
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer"
        }
    }

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

INSTRUCTIONS = """
주요 반영 사항
ALLOWED_HOSTS 및 인증 도메인: 요청하신 도메인인 classystudy.com과 www.classystudy.com을 기본적으로 허용했습니다. 추가적으로 Render에서 앱이 구동될 때 자동으로 할당되는 호스트네임(RENDER_EXTERNAL_HOSTNAME)을 감지하여 도메인 목록에 추가하도록 했습니다.
CSRF_TRUSTED_ORIGINS: 보안 정책(CSRF) 충돌을 방지하기 위해, 허용된 도메인(classystudy.com, www.classystudy.com 및 Render 도메인)의 https:// 주소를 CSRF 신뢰 출처(Trusted Origins)로 등록했습니다.
데이터베이스 설정 (PostgreSQL): Render는 프로비저닝된 PostgreSQL의 연결 URL을 DATABASE_URL이라는 환경 변수로 컨테이너에 자동 주입해 줍니다. 파일 내에서 사용 중인 dj_database_url.config() 클래스는 기본적으로 DATABASE_URL 환경 변수를 알아서 읽어오므로 기존 구성을 변경 없이 잘 활용하도록 남겨 두었습니다.
종속성 확인: 

requirements.txt
를 확인한 결과, Postgres DB 호환에 필요한 psycopg2-binary 및 dj-database-url, 그리고 정적 파일 처리에 쓰이는 whitenoise가 이미 정상적으로 포함되어 있는 것을 검증했습니다.
Render 배포 시 환경 변수(Environment Variables) 추가 팁
Render 대시보드의 Environment 탭에 다음 변수들을 등록해 주시면 됩니다.

DJANGO_SETTINGS_MODULE: config.settings.prod (필수)
SECRET_KEY: 사용하실 장고 시크릿 키 (필수)
DEBUG: False (기본값으로 처리되지만 명시적으로 넣어두면 좋습니다)
DATABASE_URL: Render에 구성하신 PostgreSQL을 연결하면 자동으로 등록됩니다.
REDIS_URL: WebSocket 서버(Channels)를 위한 Redis를 연결하실 경우 입력하세요.

"""