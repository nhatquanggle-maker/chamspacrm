"""
================================================================================
URL CONFIGURATION CHO PHÂN HỆ QUẢN LÝ HỒ SƠ SỨC KHỎE (MOD-08) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc (Meo)
Định tuyến toàn bộ Giao diện (Views) và RESTful API (DRF) cho Module 8.
Khớp 100% Thiết kế Figma:
  - Giao diện hồ sơ sức khỏe: Node 273:2545
  - Giao diện cập nhật hồ sơ sức khỏe: Node 273:2839
  - Màn hình dành cho Staff Workspace tra cứu & bảo đảm an toàn y tế
================================================================================
"""

from django.urls import path
from . import views, api

app_name = 'health'

urlpatterns = [
    # =========================================================================
    # 1. GIAO DIỆN WEB (VIEWS) - FIGMA NODE 273:2545 & NODE 273:2839
    # =========================================================================
    # UC-8.2: Xem hồ sơ sức khỏe cá nhân (Figma Node 273:2545)
    path('', views.my_health_profile_view, name='profile'),
    path('my-profile/', views.my_health_profile_view, name='my_profile'),

    # UC-8.1: Khảo sát / Cập nhật hồ sơ sức khỏe Body Map 1-1 (Figma Node 273:2839)
    path('update/', views.health_profile_update_view, name='update'),
    path('survey/', views.health_profile_update_view, name='survey'),

    # Màn hình dành cho Staff Workspace: Tra cứu & Quản lý hồ sơ sức khỏe khách hàng
    path('staff/', views.staff_health_lookup_view, name='staff_lookup'),
    path('staff/<int:user_id>/', views.staff_customer_health_detail_view, name='staff_detail'),
    path('customer/<int:user_id>/', views.staff_customer_health_detail_view, name='customer_detail'),

    # =========================================================================
    # 2. RESTFUL API THEO HỢP ĐỒNG GIAO TIẾP (SPEC SHEET CHỐT)
    # =========================================================================
    # UC-8.2: Lấy thông tin hồ sơ sức khỏe (GET)
    # Hỗ trợ cả GET /health/api/ và alias /health/api/my-profile/
    path('api/', api.HealthProfileDetailAPI.as_view(), name='api_profile'),
    path('api/my-profile/', api.HealthProfileDetailAPI.as_view(), name='api_my_profile'),

    # UC-8.1: Cập nhật / Lưu hồ sơ sức khỏe 1-1 (POST, PUT)
    path('api/update/', api.HealthProfileUpdateAPI.as_view(), name='api_update'),
    path('api/save/', api.HealthProfileUpdateAPI.as_view(), name='api_save_alias'),

    # UC-8.2: Chi tiết hồ sơ sức khỏe khách hàng cho Nhân viên / KTV (GET)
    path('api/customer/<int:user_id>/', api.StaffCustomerHealthAPI.as_view(), name='api_customer_health'),

    # Tiện ích tra cứu nhanh hồ sơ theo Số điện thoại / Tên / Mã hồ sơ (GET)
    path('api/lookup/', api.HealthLookupAPI.as_view(), name='api_lookup'),

    # Tiện ích đồng bộ lực massage sang form Đặt lịch hẹn Module 1 (GET)
    path('api/sync-pressure/', api.SyncPressureToBookingAPI.as_view(), name='api_sync_pressure'),
]
