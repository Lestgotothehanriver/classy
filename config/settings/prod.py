from .base import *

DEBUG = False 
ALLOWED_HOSTS = ["*"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "DEBUG", "propagate": True},
        "rest_framework": {"handlers": ["console"], "level": "DEBUG", "propagate": True},
    },
}