"""
URL Configuration cho Phân hệ Quản lý Lịch hẹn - CHAMSPA CRM
"""

from django.urls import path
from . import views, api

app_name = 'appointment'

urlpatterns = [
    # 1. Giao diện Web
    path('', views.booking_view, name='booking'),
    path('booking/', views.booking_view, name='booking_direct'),
    path('success/<str:code>/', views.booking_success_view, name='booking_success'),
    path('my-appointments/', views.my_appointments_view, name='my_appointments'),
    path('staff/', views.staff_appointments_view, name='staff_appointments'),
    path('staff/appointments/', views.staff_appointments_view, name='staff_appointments_direct'),
    path('admin/', views.admin_appointments_view, name='admin_appointments'),
    path('admin/appointments/', views.admin_appointments_view, name='admin_appointments_direct'),
    path('admin/export/', views.admin_export_appointments_view, name='admin_export_appointments'),

    # 2. AJAX Endpoints cho đặt lịch hẹn & thanh toán VietQR
    path('api/create/', api.appointment_create_api, name='api_create'),
    path('api/available-slots/', api.available_slots_api, name='api_available_slots'),
    path('api/apply-voucher/', api.apply_voucher_api, name='api_apply_voucher'),
    path('api/<int:pk>/confirm-payment/', api.confirm_payment_api, name='api_confirm_payment'),
    path('api/<int:pk>/update-payment/', api.update_payment_api, name='api_update_payment'),
    path('api/detail/<str:identifier>/', api.appointment_detail_api, name='api_detail'),
    path('api/<int:pk>/reschedule/', api.reschedule_api, name='api_reschedule'),
    path('api/<int:pk>/cancel/', api.cancel_api, name='api_cancel'),
    path('api/admin/appointments/', api.admin_appointments_api, name='api_admin_appointments'),
    path('api/admin/appointments/<int:pk>/', api.admin_appointments_api, name='api_admin_appointment_detail'),
    path('api/admin/appointments/<int:pk>/status/', api.admin_appointments_api, name='api_admin_appointment_status'),
    path('api/staff/quick-create/', api.staff_quick_create_api, name='api_staff_quick_create'),
]
