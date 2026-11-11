from django.urls import path
from . import views, api

app_name = 'membership'

urlpatterns = [
    path('', views.customer_membership_view, name='my_card'),
    path('my-card/', views.customer_membership_view, name='my_card_direct'),
    path('card/', views.customer_membership_view, name='card_view'),

    path('lookup/', views.staff_membership_lookup_view, name='staff_lookup'),
    path('manage/', views.staff_membership_lookup_view, name='manage'),
    path('staff/', views.staff_membership_lookup_view, name='staff_manage'),
    path('admin/', views.staff_membership_lookup_view, name='admin_manage'),

    path('api/lookup/', api.lookup_api, name='api_lookup'),
]
