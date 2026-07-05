def apply_patches():
    from django.core.files.storage import FileSystemStorage
    from django.conf import settings
    from rest_framework.fields import FileField
    from rest_framework.settings import api_settings

    # 1. Patch FileSystemStorage.url
    original_storage_url = FileSystemStorage.url

    def absolute_storage_url(self, name):
        relative_url = original_storage_url(self, name)
        if not relative_url:
            return relative_url

        if relative_url.startswith('http://') or relative_url.startswith('https://'):
            return relative_url

        from config.apps.common.middleware import get_current_request
        request = get_current_request()
        if request is not None:
            return request.build_absolute_uri(relative_url)

        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        if not relative_url.startswith('/'):
            relative_url = '/' + relative_url
        return f"{site_url.rstrip('/')}{relative_url}"

    FileSystemStorage.url = absolute_storage_url

    # 2. Patch DRF FileField.to_representation
    original_drf_to_representation = FileField.to_representation

    def absolute_drf_to_representation(self, value):
        if not value:
            return None

        use_url = getattr(self, 'use_url', api_settings.UPLOADED_FILES_USE_URL)
        if use_url:
            try:
                url = value.url
            except AttributeError:
                return None
            
            if url.startswith('http://') or url.startswith('https://'):
                return url

            request = self.context.get('request', None)
            if request is None:
                from config.apps.common.middleware import get_current_request
                request = get_current_request()

            if request is not None:
                return request.build_absolute_uri(url)

            site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
            if not url.startswith('/'):
                url = '/' + url
            return f"{site_url.rstrip('/')}{url}"

        return value.name

    FileField.to_representation = absolute_drf_to_representation
