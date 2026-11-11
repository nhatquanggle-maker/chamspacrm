from django.urls import path
from . import views

app_name = 'health'

urlpatterns = [
    path('', views.my_health_profile_view, name='profile'),
    path('my-profile/', views.my_health_profile_view, name='my_profile'),
    path('update/', views.health_profile_update_view, name='update'),
    path('survey/', views.health_profile_update_view, name='survey'),
    path('staff/', views.staff_health_lookup_view, name='staff_lookup'),
    path('staff/<int:user_id>/', views.staff_customer_health_detail_view, name='staff_detail'),
    path('customer/<int:user_id>/', views.staff_customer_health_detail_view, name='customer_detail'),
]
