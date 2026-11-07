from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


# ==============================================================================
# MODULE 05: QUẢN LÝ TÀI KHOẢN & PHÂN QUYỀN (MOD-05)
# Thành viên phụ trách: NHẬT QUANG (Leader)
# Use Cases: UC-5.1 đến UC-5.14 (Đăng ký, Đăng nhập, Hồ sơ, Quản lý User, Khóa TK)
# Bảng CSDL: User, UserProfile
# Ghi chú kỹ thuật: Đặt User ở đầu file vì là Custom User Model kế thừa AbstractUser,
#                   làm gốc xác thực và liên kết cho toàn bộ hệ thống.
# ==============================================================================

class User(AbstractUser):
    """
    [MOD-05] Bảng User trung tâm kế thừa AbstractUser của Django.
    Phân quyền 3 cấp độ:
      1. Khách hàng: is_staff=False, is_superuser=False
      2. Nhân viên:   is_staff=True,  is_superuser=False
      3. Quản trị:    is_superuser=True
    [SỬA #6]: phone là Unique, Not Null để phục vụ đăng nhập và tra cứu hội viên.
    [SỬA #10]: is_active dùng để Khóa/Mở khóa tài khoản (Soft Deactivation), tuyệt đối không xóa cứng.
    """
    name = models.CharField(max_length=255, verbose_name="Họ và tên")
    email = models.EmailField(max_length=255, unique=True, verbose_name="Địa chỉ Email")
    phone = models.CharField(max_length=20, unique=True, verbose_name="Số điện thoại (Unique)")

    is_active = models.BooleanField(default=True, verbose_name="Trạng thái tài khoản (True=Hoạt động, False=Đã khóa)")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật gần nhất")

    def save(self, *args, **kwargs):
        # Tự động gán username bằng phone hoặc email để tương thích toàn diện với Django Auth
        if not self.username:
            self.username = self.phone or self.email
        super().save(*args, **kwargs)

    class Meta:
        db_table = "chamspa_user"
        verbose_name = "Người dùng"
        verbose_name_plural = "MOD-05: 1. Người dùng (Users)"

    def __str__(self):
        role = "Quản lý" if self.is_superuser else ("Nhân viên" if self.is_staff else "Khách hàng")
        return f"{self.name} ({self.phone}) - [{role}]"


class UserProfile(models.Model):
    """
    [MOD-05] Bảng hồ sơ nhân khẩu học cá nhân (Quan hệ 1-1 với User).
    Phục vụ UC-5.4: Quản lý hồ sơ cá nhân và avatar.
    """
    GENDER_CHOICES = [
        ('Nam', 'Nam'),
        ('Nữ', 'Nữ'),
        ('Khác', 'Khác'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name="Tài khoản User")
    avatar = models.CharField(max_length=500, null=True, blank=True, verbose_name="Đường dẫn Avatar")
    birthday = models.DateField(null=True, blank=True, verbose_name="Ngày sinh")
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, null=True, blank=True, verbose_name="Giới tính")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo hồ sơ")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật hồ sơ")

    class Meta:
        db_table = "chamspa_user_profile"
        verbose_name = "Hồ sơ cá nhân"
        verbose_name_plural = "MOD-05: 2. Hồ sơ cá nhân (User Profiles)"

    def __str__(self):
        return f"Hồ sơ của: {self.user.name}"


# ==============================================================================
# MODULE 08: QUẢN LÝ HỒ SƠ SỨC KHỎE (MOD-08)
# Thành viên phụ trách: THẢO NGỌC
# Use Cases: UC-8.1 (Cập nhật hồ sơ sức khỏe 1-1), UC-8.2 (Xem hồ sơ sức khỏe)
# Bảng CSDL: UserHealthProfile
# Ghi chú nghiệp vụ: Chuẩn 1-1 tối giản: mỗi khách chỉ có 1 bản ghi duy nhất,
#                   khi khách khảo sát lại sẽ ghi đè lên bản ghi cũ.
# ==============================================================================

class UserHealthProfile(models.Model):
    """
    [MOD-08] Hồ sơ thể trạng sức khỏe khách hàng (Quan hệ 1-1 với User).
    Lưu trữ Body map vùng đau, mức độ đau, huyết áp để cảnh báo KTV khi làm dịch vụ.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='health_profile',
                                verbose_name="Khách hàng")
    health_code = models.CharField(max_length=50, unique=True, verbose_name="Mã hồ sơ sức khỏe (VD: HP-KH001)")
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                    verbose_name="Chiều cao (cm)")
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Cân nặng (kg)")
    blood_pressure = models.CharField(max_length=50, null=True, blank=True,
                                      verbose_name="Huyết áp (Bình thường/Thấp/Cao)")

    # Mảng JSON các vùng đau: ['Vai gáy', 'Thắt lưng']
    focus_areas = models.JSONField(default=list, blank=True, verbose_name="Vùng đau mỏi cần tập trung (JSON)")
    massage_pressure = models.CharField(max_length=50, null=True, blank=True, verbose_name="Lực massage mong muốn")
    pain_level = models.IntegerField(null=True, blank=True, verbose_name="Mức độ đau (1 đến 10)")

    # Mảng JSON bệnh lý cảnh báo an toàn: ['Đang mang thai', 'Da nhạy cảm']
    health_conditions = models.JSONField(default=list, blank=True, verbose_name="Bệnh lý / Lưu ý đặc biệt (JSON)")
    allergy_notes = models.TextField(null=True, blank=True, verbose_name="Ghi chú dị ứng tinh dầu/mỹ phẩm")
    special_requests = models.TextField(null=True, blank=True, verbose_name="Yêu cầu đặc biệt khác")

    # Mảng JSON mục tiêu trị liệu: ['Giảm stress', 'Trị liệu cổ vai gáy']
    recovery_goals = models.JSONField(default=list, blank=True, verbose_name="Mục tiêu trị liệu (JSON)")
    created_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật hồ sơ gần nhất")

    class Meta:
        db_table = "chamspa_user_health_profile"
        verbose_name = "Hồ sơ sức khỏe"
        verbose_name_plural = "MOD-08: 3. Hồ sơ sức khỏe (Health Profiles)"

    def __str__(self):
        return f"{self.health_code} - {self.user.name}"


# ==============================================================================
# MODULE 03: QUẢN LÝ DANH MỤC DỊCH VỤ (MOD-03)
# Thành viên phụ trách: MINH KHÁNH
# Use Cases: UC-3.1 (Danh sách dịch vụ), UC-3.2 (Chi tiết dịch vụ), UC-3.3 (CRUD Dịch vụ & Danh mục)
# Bảng CSDL: Category, Service, ServiceImage
# Ghi chú nghiệp vụ:
#   - ĐÃ BỎ trường views_count theo đúng chốt duyệt.
#   - Gói Combo được quản lý như một dịch vụ thông thường với giá trọn gói.
# ==============================================================================

class Category(models.Model):
    """
    [MOD-03] Danh mục phân loại dịch vụ của Spa (Massage Body, Massage Foot, Chăm sóc da, Combo...).
    [SỬA #5]: Đã bổ sung trường updated_at.
    """
    STATUS_CHOICES = [
        ('Active', 'Hoạt động'),
        ('Inactive', 'Ẩn'),
    ]

    name = models.CharField(max_length=255, verbose_name="Tên danh mục")
    slug = models.SlugField(max_length=255, unique=True, verbose_name="Đường dẫn thân thiện (Slug)")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Active', verbose_name="Trạng thái")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo danh mục")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật gần nhất")

    class Meta:
        db_table = "chamspa_category"
        verbose_name = "Danh mục dịch vụ"
        verbose_name_plural = "MOD-03: 4. Danh mục dịch vụ (Categories)"

    def __str__(self):
        return self.name


class Service(models.Model):
    """
    [MOD-03] Chi tiết gói dịch vụ chăm sóc và trị liệu (Bao gồm cả Combo trọn gói).
    """
    STATUS_CHOICES = [
        ('Hoạt động', 'Hoạt động'),
        ('Ngừng hoạt động', 'Ngừng hoạt động'),
    ]

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='services',
                                 verbose_name="Danh mục phân loại")
    name = models.CharField(max_length=255, verbose_name="Tên dịch vụ")
    slug = models.SlugField(max_length=255, unique=True, verbose_name="Đường dẫn thân thiện (Slug)")
    thumbnail_url = models.CharField(max_length=500, null=True, blank=True, verbose_name="Đường dẫn ảnh đại diện chính")
    description = models.TextField(null=True, blank=True, verbose_name="Mô tả chi tiết liệu trình & công dụng")
    price_vnd = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Giá niêm yết (VNĐ)")
    duration_minutes = models.IntegerField(verbose_name="Thời lượng thực hiện (phút)")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Hoạt động',
                              verbose_name="Trạng thái hiển thị")
    rating_avg = models.DecimalField(max_digits=2, decimal_places=1, default=0.0,
                                     verbose_name="Điểm đánh giá sao TB (1.0 - 5.0)")
    review_count = models.IntegerField(default=0, verbose_name="Tổng số lượt đánh giá")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo dịch vụ")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật gần nhất")

    class Meta:
        db_table = "chamspa_service"
        verbose_name = "Dịch vụ Spa"
        verbose_name_plural = "MOD-03: 5. Dịch vụ Spa (Services)"

    def __str__(self):
        return f"{self.name} ({self.duration_minutes}p - {int(self.price_vnd):,}đ)"


class ServiceImage(models.Model):
    """
    [MOD-03] Bộ sưu tập hình ảnh chi tiết (Gallery) minh họa không gian và quy trình dịch vụ.
    """
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='images', verbose_name="Dịch vụ")
    image_url = models.CharField(max_length=500, verbose_name="Đường dẫn URL ảnh")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tải ảnh lên")

    class Meta:
        db_table = "chamspa_service_image"
        verbose_name = "Hình ảnh dịch vụ"
        verbose_name_plural = "MOD-03: 6. Hình ảnh dịch vụ (Service Images)"

    def __str__(self):
        return f"Ảnh gallery của {self.service.name}"


# ==============================================================================
# MODULE 06: QUẢN LÝ HỘI VIÊN & TÍCH ĐIỂM (MOD-06)
# Thành viên phụ trách: MINH KHÁNH
# Use Cases: UC-6.1 (Thẻ hội viên & tiến trình thăng hạng), UC-6.2 (Tra cứu hội viên), UC-6.3 (Tự động tích điểm)
# Bảng CSDL: Tier, Membership, MembershipPoint
# Ghi chú nghiệp vụ:
#   - Điểm tự động tích khi Invoice chuyển sang 'Đã thanh toán' (10.000 VNĐ = 1 điểm).
#   - [SỬA #5]: Bảng MembershipPoint đã được nối đúng với Membership.
#   - ĐÃ BỎ trừ điểm hủy đơn và BỎ cronjob quét sinh nhật theo đúng chốt duyệt.
# ==============================================================================

class Tier(models.Model):
    """
    [MOD-06] Định nghĩa các hạng thành viên (Thành viên, Hạng Bạc, Hạng Vàng, Kim Cương) và mức chiết khấu.
    """
    name = models.CharField(max_length=100, verbose_name="Tên hạng thẻ")
    min_points = models.IntegerField(default=0, verbose_name="Điểm tối thiểu để đạt hạng")
    discount_percent = models.IntegerField(default=0, verbose_name="% Giảm giá đặc quyền")
    description = models.TextField(null=True, blank=True, verbose_name="Mô tả quyền lợi và quà tặng")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo hạng thẻ")

    class Meta:
        db_table = "chamspa_tier"
        verbose_name = "Hạng thẻ thành viên"
        verbose_name_plural = "MOD-06: 7. Hạng thẻ thành viên (Tiers)"

    def __str__(self):
        return f"{self.name} (Chiết khấu {self.discount_percent}%)"


class Membership(models.Model):
    """
    [MOD-06] Thẻ hội viên điện tử của khách hàng (Quan hệ 1-1 với User).
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='membership', verbose_name="Khách hàng")
    tier = models.ForeignKey(Tier, on_delete=models.SET_NULL, null=True, blank=True, related_name='members',
                             verbose_name="Hạng thẻ hiện tại")
    current_points = models.IntegerField(default=0, verbose_name="Điểm thưởng khả dụng hiện tại")
    total_points_used = models.IntegerField(default=0, verbose_name="Tổng điểm đã sử dụng")
    total_spent = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                      verbose_name="Tổng chi tiêu tích lũy (VNĐ)")
    tier_expiration_date = models.DateField(null=True, blank=True, verbose_name="Hạn duy trì hạng thẻ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm cấp thẻ")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật điểm/hạng")

    class Meta:
        db_table = "chamspa_membership"
        verbose_name = "Thẻ hội viên"
        verbose_name_plural = "MOD-06: 8. Thẻ hội viên (Memberships)"

    def __str__(self):
        tier_name = self.tier.name if self.tier else "Chưa xếp hạng"
        return f"VIP: {self.user.name} - [{tier_name}] ({self.current_points} điểm)"


class MembershipPoint(models.Model):
    """
    [MOD-06] Lịch sử biến động điểm thưởng (cộng điểm khi hóa đơn chuyển thành 'Đã thanh toán').
    """
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='point_history',
                                   verbose_name="Thẻ hội viên")
    appointment_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="Mã lịch hẹn phát sinh điểm")
    points_amount = models.IntegerField(verbose_name="Số điểm biến động (+/-)")
    reason_description = models.TextField(verbose_name="Diễn giải lý do tích điểm")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm phát sinh biến động")

    class Meta:
        db_table = "chamspa_membership_point"
        ordering = ['-created_at']
        verbose_name = "Lịch sử tích điểm"
        verbose_name_plural = "MOD-06: 9. Lịch sử tích điểm (Membership Points)"

    def __str__(self):
        return f"{self.membership.user.name}: {self.points_amount:+} điểm ({self.reason_description})"


# ==============================================================================
# MODULE 07: QUẢN LÝ THÔNG BÁO & KHUYẾN MÃI (MOD-07)
# Thành viên phụ trách: MINH KHA
# Use Cases: UC-7.1 (Xem thông báo), UC-7.2 (Kho Voucher), UC-7.3 (Quản lý thông báo),
#            UC-7.4 (Quản lý KM & Voucher), UC-7.5 (Tự động gửi thông báo)
# Bảng CSDL: Promotion, Voucher, Notification
# Ghi chú nghiệp vụ:
#   - [SỬA #7]: Bảng Voucher đã bổ sung 3 trường: discount_type ('PERCENT'/'FIXED'), max_discount_amount, min_order_amount.
#   - [SỬA #9]: Bảng Notification đã bỏ trường is_read, hoạt động như bảng tin chung.
# ==============================================================================

class Promotion(models.Model):
    """
    [MOD-07] Chương trình khuyến mãi chung của toàn Spa (Hiển thị thẻ Card CSS màu gradient).
    """
    STATUS_CHOICES = [
        ('Sắp diễn ra', 'Sắp diễn ra'),
        ('Đang hoạt động', 'Đang hoạt động'),
        ('Hết hạn', 'Hết hạn'),
    ]

    promotion_code = models.CharField(max_length=50, unique=True, verbose_name="Mã chương trình (Duy nhất)")
    title = models.CharField(max_length=255, verbose_name="Tiêu đề chương trình ưu đãi")
    conditions_desc = models.TextField(null=True, blank=True, verbose_name="Điều kiện áp dụng ưu đãi")
    valid_from = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm bắt đầu áp dụng")
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm kết thúc áp dụng")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Sắp diễn ra',
                              verbose_name="Trạng thái chương trình")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo chương trình")

    class Meta:
        db_table = "chamspa_promotion"
        verbose_name = "Chương trình khuyến mãi"
        verbose_name_plural = "MOD-07: 10. Chương trình khuyến mãi (Promotions)"

    def __str__(self):
        return f"{self.promotion_code} - {self.title}"


class Voucher(models.Model):
    """
    [MOD-07] Mã giảm giá chiết khấu (Linh hoạt giảm % có trần hoặc giảm tiền mặt cố định).
    Có thể phát hành từ Chương trình khuyến mãi hoặc từ Phiếu giải quyết khiếu nại (đền bù).
    """
    DISCOUNT_TYPE_CHOICES = [
        ('PERCENT', 'Giảm theo phần trăm (%)'),
        ('FIXED', 'Giảm theo số tiền mặt cố định (VNĐ)'),
    ]
    STATUS_CHOICES = [
        ('Khả dụng', 'Khả dụng'),
        ('Đã dùng', 'Đã dùng'),
        ('Hết hạn', 'Hết hạn'),
    ]

    voucher_code = models.CharField(max_length=50, unique=True, verbose_name="Mã nhập Voucher")
    promotion = models.ForeignKey(Promotion, on_delete=models.SET_NULL, null=True, blank=True, related_name='vouchers',
                                  verbose_name="Chương trình KM gốc")
    complaint = models.OneToOneField('Complaint', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='compensated_voucher', verbose_name="Phiếu khiếu nại đền bù")
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='vouchers',
                                 verbose_name="Khách hàng sở hữu riêng")

    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='FIXED',
                                     verbose_name="Hình thức giảm giá")
    discount_value = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Giá trị giảm (% hoặc VNĐ)")
    max_discount_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True,
                                              verbose_name="Số tiền giảm tối đa (khi giảm %)")
    min_order_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                           verbose_name="Giá trị đơn hàng tối thiểu để áp mã (VNĐ)")

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Khả dụng', verbose_name="Trạng thái mã")
    expiry_date = models.DateTimeField(verbose_name="Ngày hết hạn sử dụng")
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm áp dụng thanh toán")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm phát hành voucher")

    class Meta:
        db_table = "chamspa_voucher"
        verbose_name = "Mã Voucher"
        verbose_name_plural = "MOD-07: 11. Mã Voucher (Vouchers)"

    def __str__(self):
        val_str = f"{int(self.discount_value)}%" if self.discount_type == 'PERCENT' else f"{int(self.discount_value):,}đ"
        return f"{self.voucher_code} - Giảm {val_str} ({self.status})"


class Notification(models.Model):
    """
    [MOD-07] Bảng tin thông báo hệ thống gửi đến người dùng (nhắc lịch hẹn, kết quả khiếu nại, voucher mới).
    """
    STATUS_CHOICES = [
        ('Chờ gửi', 'Chờ gửi'),
        ('Đã gửi', 'Đã gửi'),
    ]

    notification_code = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name="Mã thông báo")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications',
                             verbose_name="Người nhận thông báo")
    title = models.CharField(max_length=255, verbose_name="Tiêu đề thông báo")
    content = models.TextField(verbose_name="Nội dung thông báo")
    promotion = models.ForeignKey(Promotion, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='notifications', verbose_name="Khuyến mãi đính kèm")
    delivery_channels = models.CharField(max_length=100, default='Web', verbose_name="Kênh phát (Web/Email/SMS)")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Chờ gửi', verbose_name="Trạng thái gửi")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm gửi thông báo")

    class Meta:
        db_table = "chamspa_notification"
        ordering = ['-created_at']
        verbose_name = "Thông báo hệ thống"
        verbose_name_plural = "MOD-07: 12. Thông báo hệ thống (Notifications)"

    def __str__(self):
        return f"{self.title} -> {self.user.name}"


# ==============================================================================
# MODULE 01: ĐẶT LỊCH & QUẢN LÝ LỊCH HẸN (MOD-01)
# Thành viên phụ trách: NHẬT QUANG (Leader)
# Use Cases: UC-1.1 (Đặt lịch trực tuyến), UC-1.2 (Lịch cá nhân), UC-1.3 (Dời lịch),
#            UC-1.4 (Hủy lịch kèm STK hoàn tiền), UC-1.5 (Quản lý danh sách lịch hẹn)
# Bảng CSDL: Appointment, AppointmentDetail
# Ghi chú nghiệp vụ:
#   - BỎ CHỌN & PHÂN CÔNG KTV TRÊN WEB. Spa tự điều phối KTV nội bộ.
#   - Trạng thái sau khi đặt: Hold (Chờ thanh toán QR) hoặc Pending.
#   - [SỬA #1]: Đã thêm cancel_reason và refund_account_number vào Appointment.
#   - [SỬA #3]: Đã thêm voucher_id liên kết Voucher.
#   - [SỬA #4]: Đã thêm total_price (tổng tiền thanh toán sau giảm).
# ==============================================================================

class Appointment(models.Model):
    """
    [MOD-01] Bảng trung tâm quản lý lịch hẹn dịch vụ của Spa.
    """
    STATUS_CHOICES = [
        ('Hold', 'Hold (Chờ thanh toán QR)'),
        ('Pending', 'Pending (Chờ xác nhận)'),
        ('Confirmed', 'Confirmed (Đã xác nhận)'),
        ('In_Progress', 'In_Progress (Đang làm dịch vụ)'),
        ('Completed', 'Completed (Đã hoàn thành)'),
        ('Cancelled', 'Cancelled (Đã hủy)'),
    ]

    appointment_code = models.CharField(max_length=50, unique=True, verbose_name="Mã đặt lịch (VD: AP-20261016-01)")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='appointments',
                             verbose_name="Tài khoản khách đặt (NULL nếu vãng lai)")
    voucher = models.ForeignKey(Voucher, on_delete=models.SET_NULL, null=True, blank=True, related_name='appointments',
                                verbose_name="Mã Voucher áp dụng")

    appointment_date = models.DateField(verbose_name="Ngày hẹn trải nghiệm")
    time_slot = models.CharField(max_length=50, verbose_name="Khung giờ hẹn (VD: 14:00)")

    total_guests = models.IntegerField(default=1, verbose_name="Tổng số lượng khách")
    male_guests = models.IntegerField(default=0, verbose_name="Số khách nam")
    female_guests = models.IntegerField(default=0, verbose_name="Số khách nữ")

    customer_name = models.CharField(max_length=255, verbose_name="Họ tên người liên hệ")
    customer_phone = models.CharField(max_length=20, verbose_name="Số điện thoại liên hệ")
    customer_email = models.CharField(max_length=255, null=True, blank=True, verbose_name="Email nhận biên nhận")
    preferred_contact_channel = models.CharField(max_length=50, null=True, blank=True,
                                                 verbose_name="Kênh liên hệ ưu tiên (Gọi điện/Zalo/SMS)")
    note = models.TextField(null=True, blank=True, verbose_name="Ghi chú của khách cho Spa")

    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                      verbose_name="Tổng tiền thanh toán sau trừ voucher (VNĐ)")

    # Trường phục vụ hủy lịch và hoàn tiền của kế toán
    cancel_reason = models.TextField(null=True, blank=True, verbose_name="Lý do khách hàng hủy lịch")
    refund_account_number = models.CharField(max_length=50, null=True, blank=True,
                                             verbose_name="Số tài khoản ngân hàng nhận tiền hoàn")

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Hold', verbose_name="Trạng thái lịch hẹn")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo lịch hẹn")

    class Meta:
        db_table = "chamspa_appointment"
        ordering = ['-appointment_date', 'time_slot']
        verbose_name = "Lịch hẹn Spa"
        verbose_name_plural = "MOD-01: 13. Lịch hẹn Spa (Appointments)"

    def __str__(self):
        return f"{self.appointment_code} - {self.customer_name} ({self.appointment_date} {self.time_slot}) [{self.status}]"


class AppointmentDetail(models.Model):
    """
    [MOD-01] Chi tiết từng khách và yêu cầu lực massage trong mỗi lịch hẹn.
    """
    GENDER_CHOICES = [
        ('Nam', 'Nam'),
        ('Nữ', 'Nữ'),
    ]

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='details',
                                    verbose_name="Lịch hẹn cha")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='appointment_details',
                                verbose_name="Dịch vụ trải nghiệm")
    guest_index = models.IntegerField(default=1, verbose_name="Thứ tự khách trong đoàn (Khách 1, 2...)")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, verbose_name="Giới tính khách")
    massage_pressure = models.CharField(max_length=50, verbose_name="Lực massage mong muốn (Nhẹ nhàng/Lực vừa/Mạnh)")

    class Meta:
        db_table = "chamspa_appointment_detail"
        verbose_name = "Chi tiết khách đặt lịch"
        verbose_name_plural = "MOD-01: 14. Chi tiết khách đặt lịch (Appointment Details)"

    def __str__(self):
        return f"{self.appointment.appointment_code} - Khách {self.guest_index} ({self.service.name})"


# ==============================================================================
# MODULE 09: QUẢN LÝ THANH TOÁN & HÓA ĐƠN (MOD-09)
# Thành viên phụ trách: THANH THẢO
# Use Cases: UC-9.1 (Thanh toán trực tuyến VietQR), UC-9.2 (Đối soát hóa đơn tại quầy),
#            UC-9.3 (Theo dõi & Tra cứu danh sách hóa đơn)
# Bảng CSDL: Invoice
# Ghi chú nghiệp vụ:
#   - Hỗ trợ VietQR động.
#   - Khi Invoice chuyển thành 'Đã thanh toán', tự động kích hoạt Signal cộng điểm sang MOD-06.
#   - ĐÃ BỎ đếm ngược 10 phút và cronjob hủy đơn theo đúng chốt duyệt.
# ==============================================================================

class Invoice(models.Model):
    """
    [MOD-09] Quản lý hóa đơn thanh toán cho từng lịch hẹn (Quan hệ 1-1 với Appointment).
    """
    STATUS_CHOICES = [
        ('Chờ xác nhận', 'Chờ xác nhận'),
        ('Đã thanh toán', 'Đã thanh toán'),
        ('Không hợp lệ', 'Không hợp lệ'),
    ]

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='invoice',
                                       verbose_name="Lịch hẹn gắn với hóa đơn")
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Tổng số tiền thực thu (VNĐ)")
    discount_applied = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                           verbose_name="Số tiền đã giảm giá từ Voucher/Hạng thẻ (VNĐ)")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Chờ xác nhận',
                              verbose_name="Trạng thái hóa đơn")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm thanh toán thành công")
    reason_refuse = models.TextField(null=True, blank=True, verbose_name="Lý do từ chối giao dịch (nếu không hợp lệ)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm xuất hóa đơn")

    class Meta:
        db_table = "chamspa_invoice"
        ordering = ['-created_at']
        verbose_name = "Hóa đơn thanh toán"
        verbose_name_plural = "MOD-09: 15. Hóa đơn thanh toán (Invoices)"

    def __str__(self):
        return f"HĐ-{self.appointment.appointment_code} - {int(self.amount):,}đ [{self.status}]"


# ==============================================================================
# MODULE 04: QUẢN LÝ PHẢN HỒI & KHIẾU NẠI (MOD-04)
# Thành viên phụ trách: THANH THẢO
# Use Cases: UC-4.1 (Gửi đánh giá/khiếu nại), UC-4.2 (Duyệt/Ẩn đánh giá), UC-4.3 (Phản hồi đánh giá),
#            UC-4.4 (Xử lý khiếu nại & Cấp voucher đền bù), UC-4.5 (Theo dõi tiến độ khiếu nại)
# Bảng CSDL: Feedback, Complaint
# Ghi chú nghiệp vụ:
#   - Feedback gắn 1-1 với Appointment đã hoàn thành (Completed).
#   - [SỬA #4]: Bảng Feedback đã bổ sung replied_by và replied_at để hiển thị tên nhân viên trả lời.
#   - [SỬA #2]: Bảng Complaint đổi quan hệ 1-N với Appointment. Bỏ bộ mẫu và nhật ký cuộc gọi.
# ==============================================================================

class Feedback(models.Model):
    """
    [MOD-04] Đánh giá số sao và nhận xét của khách hàng sau khi hoàn tất lịch hẹn (Quan hệ 1-1 với Appointment).
    """
    STATUS_CHOICES = [
        ('Chờ phản hồi', 'Chờ phản hồi'),
        ('Đã phản hồi', 'Đã phản hồi'),
        ('Đã ẩn', 'Đã ẩn'),
    ]

    feedback_code = models.CharField(max_length=50, unique=True, verbose_name="Mã phiếu đánh giá (VD: FB-20261016-01)")
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='feedback',
                                       verbose_name="Lịch hẹn được đánh giá")
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedbacks',
                                 verbose_name="Khách hàng gửi đánh giá")
    rating = models.IntegerField(verbose_name="Số sao đánh giá (1 đến 5 sao)")
    tags = models.JSONField(default=list, blank=True, null=True, verbose_name="Thẻ cảm nhận nhanh (JSON)")
    comment = models.TextField(null=True, blank=True, verbose_name="Nội dung nhận xét chi tiết")
    attached_media = models.JSONField(default=list, blank=True, null=True,
                                      verbose_name="Ảnh/Video trải nghiệm thực tế (JSON)")

    # Phản hồi công khai từ đại diện Spa
    reply = models.TextField(null=True, blank=True, verbose_name="Câu trả lời của đại diện Spa")
    replied_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='replied_feedbacks', verbose_name="Nhân viên đã phản hồi")
    replied_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm nhân viên gửi phản hồi")

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Chờ phản hồi',
                              verbose_name="Trạng thái hiển thị")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm gửi đánh giá")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật gần nhất")

    class Meta:
        db_table = "chamspa_feedback"
        ordering = ['-created_at']
        verbose_name = "Đánh giá dịch vụ"
        verbose_name_plural = "MOD-04: 16. Đánh giá dịch vụ (Feedbacks)"

    def __str__(self):
        return f"{self.feedback_code} - {self.rating} sao - {self.customer.name}"


class Complaint(models.Model):
    """
    [MOD-04] Phiếu khiếu nại sự cố chất lượng dịch vụ (Quan hệ 1-N với Appointment Completed).
    Có thể giải quyết bằng cách cấp Voucher đền bù (gắn complaint_id sang Voucher).
    """
    STATUS_CHOICES = [
        ('Chờ phân công', 'Chờ phân công'),
        ('Đang xử lý', 'Đang xử lý'),
        ('Đã xử lý', 'Đã xử lý'),
        ('Đã từ chối', 'Đã từ chối'),
        ('Chờ liên hệ lại', 'Chờ liên hệ lại'),
    ]

    complaint_code = models.CharField(max_length=50, unique=True,
                                      verbose_name="Mã phiếu khiếu nại (VD: COMP-20261016-01)")
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='complaints',
                                    verbose_name="Lịch hẹn phát sinh khiếu nại")
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='complaints',
                                 verbose_name="Khách hàng gửi khiếu nại")
    description = models.TextField(verbose_name="Mô tả chi tiết nội dung sự cố gặp phải")
    attached_proofs = models.JSONField(default=list, blank=True, null=True, verbose_name="Ảnh/Video bằng chứng (JSON)")
    desired_resolution = models.CharField(max_length=100, null=True, blank=True,
                                          verbose_name="Yêu cầu mong muốn của khách")

    assigned_staff = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='assigned_complaints', verbose_name="Nhân viên CSKH phụ trách")
    resolution_note = models.TextField(null=True, blank=True,
                                       verbose_name="Ghi chú tóm tắt kết quả xử lý của nhân viên")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Chờ phân công',
                              verbose_name="Trạng thái giải quyết khiếu nại")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm gửi khiếu nại")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật trạng thái")

    class Meta:
        db_table = "chamspa_complaint"
        ordering = ['-created_at']
        verbose_name = "Khiếu nại dịch vụ"
        verbose_name_plural = "MOD-04: 17. Khiếu nại dịch vụ (Complaints)"

    def __str__(self):
        return f"{self.complaint_code} - {self.customer.name} [{self.status}]"


# ==============================================================================
# MODULE 02: QUẢN LÝ BOXCHAT TƯ VẤN (MOD-02)
# Thành viên phụ trách: THẢO NGỌC
# Use Cases: UC-2.1 (Chatbot tự động FAQ), UC-2.2 (Trò chuyện trực tiếp với nhân viên), UC-2.3 (Quản lý FAQ)
# Bảng CSDL: FAQ, Conversation, ConversationMessage
# Ghi chú nghiệp vụ:
#   - Khách vãng lai chỉ chạy session in-memory, KHÔNG ghi Conversation vào CSDL.
#   - Chỉ lưu vào Conversation và ConversationMessage khi khách hàng đã đăng nhập.
#   - Câu trả lời của FAQ thuần túy là văn bản (TEXT), không kèm ảnh/nút bấm phức tạp.
# ==============================================================================

class FAQ(models.Model):
    """
    [MOD-02] Danh sách câu hỏi thường gặp phục vụ Chatbot tự động trả lời khách hàng (Thuần TEXT).
    """
    STATUS_CHOICES = [
        ('Active', 'Đang sử dụng'),
        ('Hidden', 'Ẩn tạm thời'),
    ]

    faq_code = models.CharField(max_length=50, unique=True, verbose_name="Mã câu hỏi FAQ")
    category = models.CharField(max_length=100, verbose_name="Nhóm danh mục (Bảng giá/Giờ mở cửa/Chính sách)")
    question = models.CharField(max_length=255, verbose_name="Nội dung câu hỏi")
    keywords = models.TextField(null=True, blank=True, verbose_name="Từ khóa nhận diện phục vụ tìm kiếm của Bot")
    answer = models.TextField(verbose_name="Nội dung câu trả lời tự động (TEXT)")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Active',
                              verbose_name="Trạng thái hoạt động")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo câu hỏi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật gần nhất")

    class Meta:
        db_table = "chamspa_faq"
        verbose_name = "Câu hỏi thường gặp FAQ"
        verbose_name_plural = "MOD-02: 18. Câu hỏi thường gặp FAQ (FAQs)"

    def __str__(self):
        return f"{self.faq_code} - {self.question}"


class Conversation(models.Model):
    """
    [MOD-02] Quản lý phiên hội thoại trực tuyến giữa Khách hàng và Chatbot hoặc Nhân viên tư vấn.
    """
    STATUS_CHOICES = [
        ('Bot xử lý', 'Bot xử lý'),
        ('Đang chờ', 'Đang chờ (Chờ nhân viên tiếp nhận)'),
        ('Đang xử lý', 'Đang xử lý (Nhân viên đã nhận chat)'),
        ('Kết thúc', 'Kết thúc phiên chat'),
    ]

    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='customer_conversations', verbose_name="Khách hàng đang chat")
    staff = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='staff_conversations', verbose_name="Nhân viên CSKH tiếp nhận")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Bot xử lý',
                              verbose_name="Trạng thái phiên hội thoại")
    customer_tag = models.CharField(max_length=100, null=True, blank=True,
                                    verbose_name="Thẻ phân loại khách (VD: Khách VIP, Khách Body)")
    bot_collected_data = models.TextField(null=True, blank=True, verbose_name="Dữ liệu nhu cầu bot thu thập (JSON)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm mở phiên chat")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm kết thúc phiên chat")

    class Meta:
        db_table = "chamspa_conversation"
        ordering = ['-created_at']
        verbose_name = "Phiên hội thoại chat"
        verbose_name_plural = "MOD-02: 19. Phiên hội thoại chat (Conversations)"

    def __str__(self):
        cust_name = self.customer.name if self.customer else "Khách vãng lai"
        return f"Hội thoại #{self.id} - {cust_name} [{self.status}]"


class ConversationMessage(models.Model):
    """
    [MOD-02] Chi tiết từng tin nhắn trao đổi trong phiên hội thoại.
    """
    SENDER_TYPE_CHOICES = [
        ('Customer', 'Khách hàng'),
        ('Bot', 'Chatbot tự động'),
        ('Staff', 'Nhân viên tư vấn'),
    ]
    MESSAGE_TYPE_CHOICES = [
        ('TEXT', 'Văn bản (TEXT)'),
        ('IMAGE', 'Hình ảnh (IMAGE)'),
        ('FILE', 'Tệp đính kèm (FILE)'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages',
                                     verbose_name="Phiên hội thoại chứa tin nhắn")
    sender_type = models.CharField(max_length=50, choices=SENDER_TYPE_CHOICES, verbose_name="Loại người gửi")
    message_type = models.CharField(max_length=50, choices=MESSAGE_TYPE_CHOICES, default='TEXT',
                                    verbose_name="Loại tin nhắn")
    content = models.TextField(null=True, blank=True, verbose_name="Nội dung văn bản tin nhắn")
    attachment_url = models.CharField(max_length=255, null=True, blank=True, verbose_name="Đường dẫn file/ảnh đính kèm")
    attachment_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Tên file đính kèm hiển thị")
    attachment_size = models.CharField(max_length=50, null=True, blank=True, verbose_name="Dung lượng file")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm gửi tin nhắn")

    class Meta:
        db_table = "chamspa_conversation_message"
        ordering = ['created_at']
        verbose_name = "Tin nhắn hội thoại"
        verbose_name_plural = "MOD-02: 20. Tin nhắn hội thoại (Conversation Messages)"

    def __str__(self):
        return f"[{self.sender_type}] {self.content[:30] if self.content else '[Đính kèm]'}"

# ==============================================================================
# MODULE 10: QUẢN LÝ DASHBOARD & BÁO CÁO (MOD-10)
# Thành viên phụ trách: MINH KHA
# Use Cases: UC-10.1 (Xem Dashboard thống kê tổng quan), UC-10.2 (Xuất báo cáo tại trình duyệt)
# Ghi chú kỹ thuật:
#   - Phân hệ này KHÔNG CẦN BẢNG CSDL RIÊNG.
#   - [SỬA #8]: Đã xóa bảng Report_export khỏi CSDL theo đúng thỏa thuận chốt lỗi.
#   - Logic báo cáo được tính toán trực tiếp từ:
#       + Invoice (doanh thu thực tế của các đơn 'Đã thanh toán')
#       + Appointment (số lượt lịch hẹn completed, top dịch vụ đặt nhiều nhất)
#       + Membership (cơ cấu hội viên Bạc, Vàng, Kim Cương)
#   - Tính năng xuất Excel/PDF được thực hiện ở Client-side bằng JavaScript (SheetJS & html2pdf).
# ==============================================================================