"""
================================================================================
DJANGO ADMIN CHO PHÂN HỆ QUẢN LÝ HỒ SƠ SỨC KHỎE (MOD-08) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc (Meo)
================================================================================
"""

from django.contrib import admin
from core.models import UserHealthProfile


try:
    admin.site.unregister(UserHealthProfile)
except admin.sites.NotRegistered:
    pass

@admin.register(UserHealthProfile)
class UserHealthProfileAdmin(admin.ModelAdmin):
    """
    Cấu hình quản trị Hồ sơ sức khỏe khách hàng trong Django Admin Panel
    """
    list_display = (
        'health_code',
        'get_customer_name',
        'get_customer_phone',
        'height_cm',
        'weight_kg',
        'blood_pressure',
        'massage_pressure',
        'pain_level',
        'created_at',
    )
    list_filter = (
        'blood_pressure',
        'massage_pressure',
        'pain_level',
        'created_at',
    )
    search_fields = (
        'health_code',
        'user__name',
        'user__phone',
        'user__email',
    )
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def get_customer_name(self, obj):
        return obj.user.name or obj.user.username
    get_customer_name.short_description = "Khách hàng"

    def get_customer_phone(self, obj):
        return obj.user.phone
    get_customer_phone.short_description = "Số điện thoại"
