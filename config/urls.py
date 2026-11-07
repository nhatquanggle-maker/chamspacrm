from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from core import views
from accounts import api as accounts_api

urlpatterns = [
    # 1. Trang quản trị Django mặc định
    path('admin/', admin.site.urls),

    # 2. Trang chủ Cham Spa (Landing Page)
    path('', views.home, name='home'),

    # =========================================================================
    # 3. 10 MODULES NGHIỆP VỤ HỆ THỐNG CHAM SPA CRM
    # =========================================================================
    path('accounts/', include('accounts.urls')),          # Đăng nhập, đăng ký, hồ sơ & phân quyền
    path('services/', include('services.urls')),          # Quản lý danh mục & các gói liệu trình Spa
    path('appointment/', include('appointment.urls')),    # Đặt lịch hẹn, ca trực & buồng/phòng
    path('dashboard/', include('dashboard.urls')),        # Thống kê KPI, doanh thu Admin & Staff
    path('membership/', include('membership.urls')),      # Thẻ hội viên Serenity & tích điểm
    path('health/', include('health.urls')),              # Hồ sơ sức khỏe & tiền sử bệnh khách hàng
    path('feedbacks/', include('feedbacks.urls')),        # Đánh giá 5 sao & xử lý khiếu nại
    path('payments/', include('payments.urls')),          # Hóa đơn thanh toán & áp mã voucher
    path('chatbox/', include('chatbox.urls')),            # Chatbot tư vấn trực tuyến
    path('marketing/', include('marketing.urls')),        # Chiến dịch khuyến mãi & thông báo

    # =========================================================================
    # 4. HỢP ĐỒNG API TOÀN HỆ THỐNG (KHỚP 100% SPEC SHEET NHÓM) - MODULE 5
    # =========================================================================
    path('api/auth/register/', accounts_api.RegisterAPI.as_view(), name='api_auth_register'),
    path('api/auth/login/', accounts_api.LoginAPI.as_view(), name='api_auth_login'),
    path('api/auth/logout/', accounts_api.LogoutAPI.as_view(), name='api_auth_logout'),
    path('api/user/profile/', accounts_api.MeAPI.as_view(), name='api_user_profile'),
    path('api/admin/users/', accounts_api.AdminUserListAPI.as_view(), name='api_admin_users'),
    path('api/admin/users/<int:pk>/toggle-status/', accounts_api.AdminUserToggleStatusAPI.as_view(), name='api_admin_user_toggle'),
    path('api/admin/customers/', accounts_api.CustomerListAPI.as_view(), name='api_admin_customers'),
    path('api/admin/customers/<int:pk>/', accounts_api.AdminCustomerDetailAPI.as_view(), name='api_admin_customer_detail'),
    path('api/admin/customers/<int:pk>/update/', accounts_api.AdminCustomerUpdateAPI.as_view(), name='api_admin_customer_update'),
    path('api/admin/customers/<int:pk>/deactivate/', accounts_api.AdminCustomerDeactivateAPI.as_view(), name='api_admin_customer_deactivate'),
    path('api/admin/staff/', accounts_api.AdminStaffListAPI.as_view(), name='api_admin_staff'),
    path('api/admin/staff/create/', accounts_api.AdminStaffCreateAPI.as_view(), name='api_admin_staff_create'),
    path('api/admin/staff/<int:pk>/update/', accounts_api.AdminStaffUpdateAPI.as_view(), name='api_admin_staff_update'),
    path('api/admin/staff/<int:pk>/deactivate/', accounts_api.AdminStaffDeactivateAPI.as_view(), name='api_admin_staff_deactivate'),
]

# Phục vụ file Media người dùng tải lên trong môi trường phát triển (DEBUG=True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# 4. Bắt mọi đường dẫn không tồn tại hoặc nhập sai bất kỳ -> Hiển thị trang 404 Cham Spa
urlpatterns += [
    re_path(r'^.*$', views.custom_404_view, name='catch_all_404'),
]

