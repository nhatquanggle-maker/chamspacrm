from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # 1. Đăng nhập
    path('login/', views.login_view, name='login'),

    # 2. Đăng ký tài khoản
    path('register/', views.register_view, name='register'),

    # 3. Đăng xuất
    path('logout/', views.logout_view, name='logout'),

    # 4. Quên mật khẩu
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('password-reset/', views.forgot_password_view, name='password_reset'),

    # 5. Đặt lại mật khẩu
    path('reset-password/', views.reset_password_view, name='reset_password'),
    path('reset-password/<str:uidb64>/<str:token>/', views.reset_password_view, name='reset_password_confirm'),
    path('password-reset-confirm/<str:uidb64>/<str:token>/', views.reset_password_view, name='password_reset_confirm'),

    # 6. Hồ sơ cá nhân
    path('profile/', views.profile_view, name='profile'),

    # 7. Quản trị khách hàng & nhân viên
    path('admin/customers/', views.admin_customer_list_view, name='admin_customer_list'),
    path('admin/customers/<int:pk>/', views.admin_customer_detail_view, name='admin_customer_detail'),
    path('admin/staff/', views.admin_staff_list_view, name='admin_staff_list'),
    path('admin/staff/<int:pk>/', views.admin_staff_detail_view, name='admin_staff_detail'),
]
