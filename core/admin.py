from django.contrib import admin
from .models import (
    User, UserProfile, UserHealthProfile,
    Category, Service, ServiceImage,
    Tier, Membership, MembershipPoint,
    Appointment, AppointmentDetail,
    Invoice, Feedback, Complaint,
    FAQ, Conversation, ConversationMessage,
    Promotion, Voucher, Notification
)

# MOD-05: Quản lý Tài khoản
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'email', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('name', 'phone', 'email')
    list_filter = ('is_active', 'is_staff', 'is_superuser')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'gender', 'birthday')

# MOD-08: Hồ sơ sức khỏe
@admin.register(UserHealthProfile)
class UserHealthProfileAdmin(admin.ModelAdmin):
    list_display = ('health_code', 'user', 'blood_pressure', 'pain_level', 'created_at')
    search_fields = ('health_code', 'user__name', 'user__phone')

# MOD-03: Dịch vụ & Danh mục
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'status', 'created_at')
    prepopulated_fields = {'slug': ('name',)}

class ServiceImageInline(admin.TabularInline):
    model = ServiceImage
    extra = 1

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category', 'price_vnd', 'duration_minutes', 'status', 'rating_avg')
    list_filter = ('category', 'status')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ServiceImageInline]

# MOD-06: Hội viên & Tích điểm
@admin.register(Tier)
class TierAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'min_points', 'discount_percent')

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'tier', 'current_points', 'total_spent')
    search_fields = ('user__name', 'user__phone')

@admin.register(MembershipPoint)
class MembershipPointAdmin(admin.ModelAdmin):
    list_display = ('id', 'membership', 'points_amount', 'reason_description', 'created_at')

# MOD-07: Khuyến mãi, Voucher & Thông báo
@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('promotion_code', 'title', 'valid_from', 'valid_until', 'status')

@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ('voucher_code', 'discount_type', 'discount_value', 'min_order_amount', 'status', 'expiry_date')
    list_filter = ('discount_type', 'status')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'status', 'created_at')

# MOD-01: Đặt lịch & Quản lý lịch hẹn
class AppointmentDetailInline(admin.TabularInline):
    model = AppointmentDetail
    extra = 0

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('appointment_code', 'customer_name', 'customer_phone', 'appointment_date', 'time_slot', 'total_price', 'status')
    list_filter = ('status', 'appointment_date')
    search_fields = ('appointment_code', 'customer_name', 'customer_phone')
    inlines = [AppointmentDetailInline]

# MOD-09: Hóa đơn & Thanh toán
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'appointment', 'amount', 'discount_applied', 'status', 'paid_at')
    list_filter = ('status',)

# MOD-04: Đánh giá & Khiếu nại
@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('feedback_code', 'appointment', 'customer', 'rating', 'status', 'created_at')
    list_filter = ('rating', 'status')

@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('complaint_code', 'appointment', 'customer', 'assigned_staff', 'status', 'created_at')
    list_filter = ('status',)

# MOD-02: Boxchat & FAQ
@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('faq_code', 'category', 'question', 'status')
    list_filter = ('category', 'status')
    search_fields = ('question', 'keywords')

class ConversationMessageInline(admin.TabularInline):
    model = ConversationMessage
    extra = 0

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'staff', 'status', 'created_at')
    list_filter = ('status',)
    inlines = [ConversationMessageInline]