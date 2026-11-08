from django.urls import path
from . import views
from . import api

app_name = 'accounts'

urlpatterns = [
    # 1. Đăng nhập (Node 188:27886)
    path('login/', views.login_view, name='login'),

    # 2. Đăng ký tài khoản (Node 188:27928)
    path('register/', views.register_view, name='register'),

    # 3. Đăng xuất
    path('logout/', views.logout_view, name='logout'),

    # 4. Quên mật khẩu (Node 188:27987)
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('password-reset/', views.forgot_password_view, name='password_reset'),

    # 5. Đặt lại mật khẩu (Node 188:28011)
    path('reset-password/', views.reset_password_view, name='reset_password'),
    path('reset-password/<str:uidb64>/<str:token>/', views.reset_password_view, name='reset_password_confirm'),
    path('password-reset-confirm/<str:uidb64>/<str:token>/', views.reset_password_view, name='password_reset_confirm'),

    # 6. Hồ sơ cá nhân
    path('profile/', views.profile_view, name='profile'),

    # =========================================================================
    # 7. MODULE 5 - GIAO DIỆN QUẢN TRỊ VIÊN (ADMIN CUSTOMER MANAGEMENT)
    # =========================================================================
    path('admin/customers/', views.admin_customer_list_view, name='admin_customer_list'),
    path('admin/customers/<int:pk>/', views.admin_customer_detail_view, name='admin_customer_detail'),

    # =========================================================================
    # 8. HỆ THỐNG REST API CHO MODULE 5 (GIAO TIẾP ĐỒNG BỘ ĐA THIẾT BỊ / ĐA MÁY)
    # =========================================================================
    path('api/register/', api.RegisterAPI.as_view(), name='api_register'),
    path('api/login/', api.LoginAPI.as_view(), name='api_login'),
    path('api/me/', api.MeAPI.as_view(), name='api_me'),
    path('api/customers/', api.CustomerListAPI.as_view(), name='api_customers'),
    path('api/admin/customers/create/', api.AdminCustomerCreateAPI.as_view(), name='api_admin_customer_create'),
    path('api/stats/', api.AccountStatsAPI.as_view(), name='api_stats'),
]
