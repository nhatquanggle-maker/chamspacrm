from django.shortcuts import render


def home(request):
    """Trang chủ Cham Spa (10 Section Landing Page)"""
    return render(request, 'home.html')


def custom_404_view(request, *args, **kwargs):
    """Bắt mọi đường dẫn nhập sai hoặc không tồn tại và hiển thị giao diện 404 Cham Spa"""
    return render(request, '404.html', status=404)

