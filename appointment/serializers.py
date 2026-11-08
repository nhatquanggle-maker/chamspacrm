"""
Serializers cho Phân hệ Quản lý Lịch hẹn (MOD-01) - CHAMSPA CRM
Tác giả: Nhật Quang (Leader)
Khớp 100% Bảng Đặc tả Chốt & Thiết kế Figma:
  - Form đặt lịch: Node 828:515
  - Thanh toán VietQR: Node 818:2
  - Phiếu xác nhận đặt lịch hoàn tất (Digital Pass): Node 154:4478
"""

from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from core.models import Appointment, AppointmentDetail, Service, Voucher


class ServiceSimpleSerializer(serializers.ModelSerializer):
    """
    Serializer tóm tắt cho Dịch vụ Spa tại màn hình đặt lịch
    """
    formatted_price = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = ['id', 'name', 'slug', 'description', 'price_vnd', 'formatted_price', 'duration_minutes', 'rating_avg']

    def get_formatted_price(self, obj):
        return f"{int(obj.price_vnd):,}".replace(',', '.') + " VNĐ"


class GuestDetailInputSerializer(serializers.Serializer):
    """
    Thông tin yêu cầu trải nghiệm cho từng khách trong đoàn (Figma Node 828:515)
    Bao gồm: Thứ tự khách, Giới tính, Dịch vụ riêng và Lực massage mong muốn (Nhẹ, Vừa, Mạnh)
    """
    guest_index = serializers.IntegerField(default=1)
    gender = serializers.ChoiceField(choices=['Nam', 'Nữ'], default='Nam')
    service_id = serializers.IntegerField(required=False, allow_null=True)
    massage_pressure = serializers.CharField(max_length=50, default='Vừa')


class AppointmentCreateSerializer(serializers.Serializer):
    """
    Serializer tiếp nhận yêu cầu đặt lịch hẹn trực tuyến (UC-1.1)
    Hỗ trợ cả Hợp đồng API Spec (POST /api/appointments/create/) và Web Form Figma
    """
    branch_name = serializers.CharField(required=False, default='Cham Spa - 05 Lê Quang Hoà, Đà Nẵng')
    appointment_date = serializers.DateField()
    time_slot = serializers.CharField(max_length=20)
    total_guests = serializers.IntegerField(min_value=1, max_value=10, default=1)
    male_guests = serializers.IntegerField(min_value=0, default=0, required=False)
    female_guests = serializers.IntegerField(min_value=0, default=0, required=False)

    # Thông tin liên hệ khách hàng (Tự động điền từ tài khoản đăng nhập)
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    customer_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    preferred_contact_channel = serializers.CharField(max_length=50, required=False, default='Điện thoại')
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Ưu đãi Voucher & Dịch vụ mặc định
    voucher_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    service_id = serializers.IntegerField(required=False, allow_null=True)

    # Chi tiết từng khách (chấp nhận cả 'guests' và 'guest_details')
    guests = GuestDetailInputSerializer(many=True, required=False)
    guest_details = GuestDetailInputSerializer(many=True, required=False)

    def validate_appointment_date(self, value):
        """Kiểm tra ngày hẹn hợp lệ trong hệ thống"""
        if value.year < 2026:
            raise serializers.ValidationError("Không thể đặt lịch vào năm trong quá khứ.")
        return value

    def validate_customer_phone(self, value):
        """Kiểm tra định dạng cơ bản của số điện thoại nếu được cung cấp"""
        if not value:
            return value
        clean_phone = value.strip().replace(' ', '').replace('.', '').replace('-', '')
        if len(clean_phone) < 9 or len(clean_phone) > 15:
            raise serializers.ValidationError("Số điện thoại không đúng định dạng.")
        return clean_phone

    def validate(self, attrs):
        total = attrs.get('total_guests', 1)
        male = attrs.get('male_guests', 0)
        female = attrs.get('female_guests', 0)

        # Cân đối số lượng nam/nữ
        if male + female == 0:
            attrs['male_guests'] = total
            attrs['female_guests'] = 0
        elif male + female != total:
            attrs['total_guests'] = male + female

        # Chuẩn hóa danh sách khách từ 'guests' sang 'guest_details' nếu có
        if not attrs.get('guest_details') and attrs.get('guests'):
            attrs['guest_details'] = attrs.get('guests')

        return attrs


class AppointmentDetailOutputSerializer(serializers.ModelSerializer):
    """
    Serializer dữ liệu chi tiết từng khách trong lịch hẹn
    """
    service_id = serializers.IntegerField(source='service.id', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    service_price = serializers.DecimalField(source='service.price_vnd', max_digits=15, decimal_places=0, read_only=True)
    service_duration = serializers.IntegerField(source='service.duration_minutes', read_only=True)

    class Meta:
        model = AppointmentDetail
        fields = [
            'id', 'guest_index', 'gender', 'service_id', 'service_name',
            'service_price', 'service_duration', 'massage_pressure'
        ]


class AppointmentFullSerializer(serializers.ModelSerializer):
    """
    Serializer đầy đủ cho Lịch hẹn (Dùng cho Hợp đồng API & Digital Pass Node 154:4478)
    """
    details = AppointmentDetailOutputSerializer(many=True, read_only=True)
    service_name = serializers.SerializerMethodField()
    formatted_total_price = serializers.SerializerMethodField()
    voucher_code = serializers.CharField(source='voucher.voucher_code', read_only=True, default='')
    discount_amount = serializers.SerializerMethodField()
    formatted_discount = serializers.SerializerMethodField()
    date_display = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            'id', 'appointment_code', 'customer_name', 'customer_phone', 'customer_email',
            'preferred_contact_channel', 'appointment_date', 'date_display', 'time_slot',
            'total_guests', 'male_guests', 'female_guests', 'note', 'status', 'status_label',
            'total_price', 'formatted_total_price', 'voucher_id', 'voucher_code',
            'discount_amount', 'formatted_discount', 'service_name',
            'cancel_reason', 'refund_account_number', 'created_at', 'details'
        ]

    def get_service_name(self, obj):
        details = obj.details.all().select_related('service')
        if details.exists():
            names = [d.service.name for d in details if d.service]
            if len(names) == 1:
                return names[0]
            elif len(names) > 1:
                return f"{names[0]} (+{len(names) - 1} dịch vụ khác)"
        return "Dịch vụ Massage & Trị liệu Cham Spa"

    def get_formatted_total_price(self, obj):
        return f"{int(obj.total_price):,}".replace(',', '.') + " VNĐ"

    def get_discount_amount(self, obj):
        if not obj.voucher:
            return 0
        v = obj.voucher
        if v.discount_type in ['PERCENT', 'Phần trăm']:
            if v.discount_value < 100:
                raw = (obj.total_price * Decimal(v.discount_value)) / Decimal(100 - v.discount_value)
            else:
                raw = obj.total_price
            if v.max_discount_amount:
                raw = min(raw, v.max_discount_amount)
            return int(raw)
        return int(v.discount_value)

    def get_formatted_discount(self, obj):
        val = self.get_discount_amount(obj)
        if val > 0:
            return f"-{val:,}".replace(',', '.') + " VNĐ"
        return "0 VNĐ"

    def get_date_display(self, obj):
        d = obj.appointment_date
        weekday_map = {
            0: 'Thứ Hai', 1: 'Thứ Ba', 2: 'Thứ Tư', 3: 'Thứ Năm',
            4: 'Thứ Sáu', 5: 'Thứ Bảy', 6: 'Chủ Nhật'
        }
        weekday = weekday_map.get(d.weekday(), '')
        return f"{weekday}, ngày {d.day:02d} tháng {d.month:02d}, {d.year}"

    def get_status_label(self, obj):
        status_map = {
            'Hold': 'Chờ thanh toán QR',
            'Pending': 'Đang chờ xác nhận',
            'Confirmed': 'Đã xác nhận',
            'In_Progress': 'Đang làm dịch vụ',
            'Completed': 'Đã hoàn thành',
            'Cancelled': 'Đã hủy',
        }
        return status_map.get(obj.status, obj.status)
