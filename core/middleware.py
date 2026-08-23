from django.conf import settings


class SecurityHeadersMiddleware:
    """CSP básica para toda resposta (server-rendered, sem CDNs externas)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resposta = self.get_response(request)
        if getattr(settings, "CONTENT_SECURITY_POLICY", ""):
            resposta.headers.setdefault(
                "Content-Security-Policy", settings.CONTENT_SECURITY_POLICY
            )
        return resposta
