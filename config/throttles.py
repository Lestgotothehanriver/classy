from rest_framework.throttling import UserRateThrottle

class SafeMethodRateThrottle(UserRateThrottle):
    scope = 'safe_method'

    def allow_request(self, request, view):
        # Apply throttle only for safe HTTP methods (GET, HEAD, OPTIONS)
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return super().allow_request(request, view)
        return True

class UnsafeMethodRateThrottle(UserRateThrottle):
    scope = 'unsafe_method'

    def allow_request(self, request, view):
        # Apply throttle only for unsafe HTTP methods (POST, PUT, PATCH, DELETE)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            return super().allow_request(request, view)
        return True

class LoginRateThrottle(UserRateThrottle):
    scope = 'login'

    class Meta:
        pass

class SMSRateThrottle(UserRateThrottle):
    scope = 'sms'

class PurchaseRateThrottle(UserRateThrottle):
    scope = 'purchase'
