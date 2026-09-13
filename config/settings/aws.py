"""AWS production: private RDS, S3 uploads, and a shared Redis cache."""
from .prod import *

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['api.classystudy.com', 'localhost', '127.0.0.1'])
BASE_URL = env('BASE_URL', default='https://api.classystudy.com')
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    'https://classystudy.com', 'https://www.classystudy.com',
    'https://classy-admin-web-qsog.onrender.com',
])
CSRF_TRUSTED_ORIGINS = [BASE_URL, *CORS_ALLOWED_ORIGINS]
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

DATABASES['default']['OPTIONS'] = {
    'sslmode': 'verify-full',
    'sslrootcert': env('RDS_CA_BUNDLE'),
    'connect_timeout': 10,
}
DATABASES['default']['CONN_MAX_AGE'] = 0  # ASGI requests must not retain connections.

AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = env('AWS_DEFAULT_REGION', default='ap-northeast-2')
STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'bucket_name': AWS_STORAGE_BUCKET_NAME,
            'region_name': AWS_S3_REGION_NAME,
            'default_acl': None,
            'file_overwrite': False,
            'querystring_auth': True,
            'querystring_expire': 14400,
            'signature_version': 's3v4',
            'max_memory_size': 5 * 1024 * 1024,
            'object_parameters': {'ServerSideEncryption': 'AES256'},
        },
    },
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
REDIS_URL = env('REDIS_URL')
CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels_redis.core.RedisChannelLayer', 'CONFIG': {'hosts': [REDIS_URL]}},
}
CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': REDIS_URL},
}
FILE_UPLOAD_HANDLERS = ['django.core.files.uploadhandler.TemporaryFileUploadHandler']
FILE_UPLOAD_MAX_MEMORY_SIZE = 0
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
