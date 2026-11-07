from django.urls import path
from . import views, api

app_name = 'appointment'

urlpatterns = [
    # 1. Giao diện Web (Views)
    path('', views.booking_view, name='booking'),
    path('booking/', views.booking_view, name='booking_direct'),
    path('success/<str:code>/', views.booking_success_view, name='booking_success'),
    path('my-appointments/', views.my_appointments_view, name='my_appointments'),

    # 2. Hợp đồng RESTful API (Khớp 100% Spec Sheet nhóm)
    path('api/create/', api.AppointmentCreateAPI.as_view(), name='api_create'),
    path('api/available-slots/', api.AvailableSlotsAPI.as_view(), name='api_available_slots'),
    path('api/apply-voucher/', api.ApplyVoucherAPI.as_view(), name='api_apply_voucher'),
    path('api/<int:pk>/confirm-payment/', api.ConfirmPaymentAPI.as_view(), name='api_confirm_payment'),
    path('api/detail/<str:identifier>/', api.AppointmentDetailAPI.as_view(), name='api_detail'),
    path('api/my-appointments/', api.MyAppointmentsAPI.as_view(), name='api_my_appointments'),
    path('api/<int:pk>/reschedule/', api.RescheduleAPI.as_view(), name='api_reschedule'),
    path('api/<int:pk>/cancel/', api.CancelAPI.as_view(), name='api_cancel'),
    path('api/admin/appointments/', api.AdminAppointmentListAPI.as_view(), name='api_admin_appointments'),
    path('api/admin/appointments/<int:pk>/', api.AdminAppointmentListAPI.as_view(), name='api_admin_appointment_update'),
]
