from django.urls import path
from . import views, api

app_name = 'services'

urlpatterns = [
    path('', views.service_list_view, name='service_list'),
    path('list/', views.service_list_view, name='service_list_alias'),
    path('admin/', views.service_admin_view, name='service_admin'),
    path('manage/', views.service_admin_view, name='service_manage'),
    path('detail/<slug:slug>/', views.service_detail_view, name='service_detail'),

    path('api/', api.service_list_api, name='api_service_list'),
    path('api/detail/<slug:slug>/', api.service_detail_api, name='api_service_detail'),

    path('<slug:slug>/', views.service_detail_view, name='service_detail_slug'),
]
