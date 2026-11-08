"""
URL Configuration cho Phân hệ Quản lý Danh mục & Dịch vụ (MOD-03) - CHAMSPA CRM
Tác giả: Minh Khánh
Use Cases:
  - UC-3.1: Xem danh sách dịch vụ (/services/ & /services/api/)
  - UC-3.2: Xem chi tiết dịch vụ (/services/<slug>/ & /services/api/<slug>/)
  - UC-3.3: Quản trị danh mục & dịch vụ (/services/admin/ & /services/api/admin/...)
Tuân thủ quy định: Khai báo độc lập trong urls.py của module, không sửa config/urls.py tổng.
"""

from django.urls import path
from . import views, api

app_name = 'services'

urlpatterns = [
    # =========================================================================
    # 1. GIAO DIỆN WEB CỐ ĐỊNH (VIEWS)
    # =========================================================================
    # UC-3.1: Giao diện Danh sách dịch vụ phía Khách hàng (Figma Node 216-928)
    path('', views.service_list_view, name='service_list'),
    path('list/', views.service_list_view, name='service_list_alias'),

    # UC-3.3: Giao diện Quản trị Danh mục & Dịch vụ cho Quản lý (Figma Hình 23)
    path('admin/', views.service_admin_view, name='service_admin'),
    path('manage/', views.service_admin_view, name='service_manage'),

    # UC-3.2: Giao diện Chi tiết dịch vụ theo tiền tố cố định detail/
    path('detail/<slug:slug>/', views.service_detail_view, name='service_detail'),

    # =========================================================================
    # 2. RESTFUL API CHO FRONTEND (FETCH API / AJAX KHÔNG TẢI LẠI TRANG)
    # (ĐẶT TRƯỚC SLUG CATCH-ALL ĐỂ TRÁNH TRÙNG ROUTE)
    # =========================================================================
    # UC-3.1: Lấy danh sách dịch vụ phân trang, lọc theo danh mục, khoảng giá, sắp xếp
    path('api/', api.ServiceListAPI.as_view(), name='api_service_list'),
    path('api/services/', api.ServiceListAPI.as_view(), name='api_service_list_alias'),
    path('api/categories/', api.CategoryListAPI.as_view(), name='api_categories'),

    # UC-3.2: Lấy chi tiết dịch vụ theo slug (kèm gallery ảnh, 4 bước quy trình, feedback)
    path('api/detail/<slug:slug>/', api.ServiceDetailAPI.as_view(), name='api_service_detail'),
    path('api/services/<slug:slug>/', api.ServiceDetailAPI.as_view(), name='api_service_detail_alias'),

    # UC-3.3: API Quản trị Dịch vụ (CRUD, thống kê KPI, Toggle ẩn/hiện)
    path('api/admin/services/', api.AdminServiceListCreateAPI.as_view(), name='api_admin_services'),
    path('api/admin/services/<int:pk>/', api.AdminServiceDetailUpdateDeleteAPI.as_view(), name='api_admin_service_detail'),
    path('api/admin/services/<int:pk>/toggle-status/', api.AdminServiceToggleStatusAPI.as_view(), name='api_admin_service_toggle'),
    path('api/admin/categories/', api.AdminCategoryListCreateAPI.as_view(), name='api_admin_categories'),
    path('api/admin/categories/<int:pk>/', api.AdminCategoryDetailUpdateDeleteAPI.as_view(), name='api_admin_category_detail'),
    path('api/admin/stats/', api.AdminServiceStatsAPI.as_view(), name='api_admin_stats'),

    # =========================================================================
    # 3. GIAO DIỆN XEM CHI TIẾT DỊCH VỤ TRỰC TIẾP QUA SLUG
    # (ĐẶT CUỐI CÙNG ĐỂ KHÔNG CHẶN CÁC ROUTE CỐ ĐỊNH Ở TRÊN)
    # =========================================================================
    path('<slug:slug>/', views.service_detail_view, name='service_detail_slug'),
]
