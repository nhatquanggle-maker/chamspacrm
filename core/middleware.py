from django.shortcuts import render


class ChamSpaErrorFallbackMiddleware:
    """
    Middleware bắt mọi mã lỗi (404, 500) hoặc ngoại lệ phát sinh trong hệ thống
    và tự động hiển thị giao diện trang lỗi 404 Cham Spa theo đúng yêu cầu.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Bỏ qua các file tĩnh để không làm gián đoạn tài nguyên
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return response

        if response.status_code in (404, 500):
            return render(request, '404.html', status=404)
        return response

    def process_exception(self, request, exception):
        # Bắt mọi ngoại lệ runtime (lỗi code / 500) và hiển thị trang 404 Cham Spa
        return render(request, '404.html', status=404)

