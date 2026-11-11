from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from core import views

urlpatterns = [
    # 1. Trang quản trị Django mặc định
    path('admin/', admin.site.urls),

    # 2. Trang chủ Cham Spa (Landing Page)
    path('', views.home, name='home'),

    # =========================================================================
    # 3. CÁC MODULES NGHIỆP VỤ HỆ THỐNG CHAM SPA CRM
    # =========================================================================
    path('accounts/', include('accounts.urls')),          # Đăng nhập, đăng ký, hồ sơ & phân quyền
    path('services/', include('services.urls')),          # Quản lý danh mục & các gói liệu trình Spa
    path('appointment/', include('appointment.urls')),    # Đặt lịch hẹn, ca trực & buồng/phòng
    path('dashboard/', include('dashboard.urls')),        # Thống kê KPI, doanh thu Admin & Staff
    path('membership/', include('membership.urls')),      # Thẻ hội viên Serenity & tích điểm
    path('health/', include('health.urls')),              # Hồ sơ sức khỏe & tiền sử bệnh khách hàng
    path('feedbacks/', include('feedbacks.urls')),        # Đánh giá 5 sao & xử lý khiếu nại
    path('chatbox/', include('chatbox.urls')),            # Chatbot tư vấn trực tuyến
    path('marketing/', include('marketing.urls')),        # Chiến dịch khuyến mãi & thông báo
]

# Phục vụ file Media người dùng tải lên trong môi trường phát triển (DEBUG=True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# 4. Bắt mọi đường dẫn không tồn tại hoặc nhập sai bất kỳ -> Hiển thị trang 404 Cham Spa
urlpatterns += [
    re_path(r'^.*$', views.custom_404_view, name='catch_all_404'),
]

