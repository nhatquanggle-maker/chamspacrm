from django.urls import path
from . import views

app_name = 'feedbacks'

urlpatterns = [
    path('', views.customer_feedback_tracking, name='my_feedbacks'),
    path('tracking/', views.customer_feedback_tracking, name='customer_tracking'),
    path('manage/', views.admin_feedback_management, name='admin_management'),
    path('admin/', views.admin_feedback_management, name='admin_feedback_list'),
    path('staff/', views.admin_feedback_management, name='staff_feedback_list'),
]
