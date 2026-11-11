from django.urls import path
from . import views, api

app_name = 'dashboard'

urlpatterns = [
    path('', views.admin_dashboard, name='index'),
    path('admin/', views.admin_dashboard, name='admin'),
    path('staff/', views.staff_dashboard, name='staff'),
    path('api/stats/', api.stats_api, name='api_stats'),
    path('api/export-data/', api.export_data_api, name='api_export_data'),
]
