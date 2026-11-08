"""
URL Configuration cho Phân hệ Quản lý Lịch hẹn (MOD-01) - CHAMSPA CRM
Tác giả: Nhật Quang (Leader)
Khớp 100% Thiết kế Figma:
  - Form đặt lịch hẹn trực tuyến: Node 828:515
  - Modal thanh toán VietQR: Node 818:2
  - Phiếu xác nhận đặt lịch hoàn tất (Digital Pass): Node 154:4478
"""

from django.urls import path
from . import views, api

app_name = 'appointment'

urlpatterns = [
    # 1. GIAO DIỆN WEB (VIEWS)
    path('', views.booking_view, name='booking'),
    path('booking/', views.booking_view, name='booking_direct'),
    path('success/<str:code>/', views.booking_success_view, name='booking_success'),
    path('my-appointments/', views.my_appointments_view, name='my_appointments'),
    path('staff/', views.staff_appointments_view, name='staff_appointments'),
    path('staff/appointments/', views.staff_appointments_view, name='staff_appointments_direct'),

    # 2. RESTful API CHO ĐẶT LỊCH HẸN & THANH TOÁN VIETQR
    path('api/create/', api.AppointmentCreateAPI.as_view(), name='api_create'),
    path('api/available-slots/', api.AvailableSlotsAPI.as_view(), name='api_available_slots'),
    path('api/slots/', api.AvailableSlotsAPI.as_view(), name='api_slots_alias'),
    path('api/apply-voucher/', api.ApplyVoucherAPI.as_view(), name='api_apply_voucher'),
    path('api/voucher/apply/', api.ApplyVoucherAPI.as_view(), name='api_voucher_apply_alias'),
    path('api/<int:pk>/confirm-payment/', api.ConfirmPaymentAPI.as_view(), name='api_confirm_payment'),
    path('api/confirm-payment/', api.ConfirmPaymentAPI.as_view(), name='api_confirm_payment_direct'),
    path('api/detail/<str:identifier>/', api.AppointmentDetailAPI.as_view(), name='api_detail'),

    # API hỗ trợ bổ sung
    path('api/my-appointments/', api.MyAppointmentsAPI.as_view(), name='api_my_appointments'),
    path('api/<int:pk>/reschedule/', api.RescheduleAPI.as_view(), name='api_reschedule'),
    path('api/<int:pk>/cancel/', api.CancelAPI.as_view(), name='api_cancel'),
    path('api/admin/appointments/', api.AdminAppointmentListAPI.as_view(), name='api_admin_appointments'),
    path('api/admin/appointments/<int:pk>/', api.AdminAppointmentListAPI.as_view(), name='api_admin_appointment_detail'),
    path('api/admin/appointments/<int:pk>/status/', api.AdminAppointmentListAPI.as_view(), name='api_admin_appointment_status'),
    path('api/staff/quick-create/', api.StaffQuickCreateAppointmentAPI.as_view(), name='api_staff_quick_create'),
]
