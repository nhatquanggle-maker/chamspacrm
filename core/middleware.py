from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render


class ChamSpaErrorFallbackMiddleware:
    """
    Middleware hiển thị giao diện 404 Cham Spa cho lỗi 404,
    và chỉ fallback 500 sang trang lỗi thân thiện khi DEBUG=False.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return response

        if response.status_code == 404 and not request.path.startswith(('/api/', '/dashboard/api/', '/appointment/api/', '/services/api/', '/membership/api/', '/health/api/', '/feedbacks/api/', '/chatbox/api/', '/marketing/api/')):
            return render(request, '404.html', status=404)
        if response.status_code == 500 and not settings.DEBUG:
            return render(request, '404.html', status=500)
        return response

    def process_exception(self, request, exception):
        if settings.DEBUG or isinstance(exception, (PermissionDenied, Http404)):
            return None
        return render(request, '404.html', status=500)

