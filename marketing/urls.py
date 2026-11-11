from django.urls import path
from . import views, api

app_name = 'marketing'

urlpatterns = [
    path('', views.promotions_view, name='promotions'),
    path('offers/', views.promotions_view, name='offers'),
    path('notifications/', views.notifications_view, name='notifications'),
    path('manage/', views.admin_notifications_view, name='admin_management'),
    path('admin/', views.admin_notifications_view, name='admin_marketing'),
    path('admin/notifications/', views.admin_notifications_view, name='admin_notifications'),
    path('admin/promotions/', views.admin_promotions_view, name='admin_promotions'),
    path('staff/', views.staff_notifications_view, name='staff_notifications'),

    path('api/notifications/dropdown/', api.notification_dropdown_api, name='api_notification_dropdown'),
    path('api/vouchers/validate/', api.voucher_validate_api, name='api_voucher_validate'),
]
