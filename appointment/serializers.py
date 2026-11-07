from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone
from core.models import Appointment, AppointmentDetail, Service, Voucher


class ServiceSimpleSerializer(serializers.ModelSerializer):
    """Serializer tóm tắt cho Dịch vụ tại màn hình đặt lịch"""
    formatted_price = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = ['id', 'name', 'slug', 'description', 'price_vnd', 'formatted_price', 'duration_minutes', 'rating_avg']

    def get_formatted_price(self, obj):
        return f"{int(obj.price_vnd):,}".replace(',', '.') + " VNĐ"


class GuestDetailInputSerializer(serializers.Serializer):
    """Thông tin tùy chỉnh cho từng khách đi kèm"""
    guest_index = serializers.IntegerField(default=1)
    gender = serializers.ChoiceField(choices=['Nam', 'Nữ'], default='Nam')
    service_id = serializers.IntegerField()
    massage_pressure = serializers.ChoiceField(choices=['Nhẹ', 'Vừa', 'Mạnh', 'Nhẹ nhàng'], default='Vừa')


class AppointmentCreateSerializer(serializers.Serializer):
    """
    Serializer tiếp nhận yêu cầu đặt lịch hẹn trực tuyến (UC-1.1)
    Khớp 100% Figma Node 828:515 & Hợp đồng API Spec nhóm
    """
    branch_name = serializers.CharField(default='Cham Spa - 05 Lê Quang Hoà, Đà Nẵng')
    appointment_date = serializers.DateField()
    time_slot = serializers.CharField(max_length=10)
    total_guests = serializers.IntegerField(min_value=1, max_value=10, default=1)
    male_guests = serializers.IntegerField(min_value=0, default=0)
    female_guests = serializers.IntegerField(min_value=0, default=0)
    
    # Thông tin liên hệ
    customer_name = serializers.CharField(max_length=150)
    customer_phone = serializers.CharField(max_length=20)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    preferred_contact_channel = serializers.CharField(max_length=50, default='Zalo / Điện thoại')
    note = serializers.CharField(required=False, allow_blank=True)
    
    # Mã ưu đãi (Voucher)
    voucher_code = serializers.CharField(required=False, allow_blank=True)
    
    # Danh sách chi tiết từng khách
    guest_details = GuestDetailInputSerializer(many=True, required=False)

    def validate_appointment_date(self, value):
        today = timezone.localdate()
        if value < today:
            raise serializers.ValidationError("Không thể chọn ngày trong quá khứ.")
        return value

    def validate(self, attrs):
        total = attrs.get('total_guests', 1)
        male = attrs.get('male_guests', 0)
        female = attrs.get('female_guests', 0)
        
        # Nếu người dùng không nhập chi tiết nam/nữ, mặc định toàn bộ là tổng khách
        if male + female == 0:
            attrs['male_guests'] = total
        elif male + female != total:
            # Tự động cân đối số lượng
            attrs['total_guests'] = male + female

        return attrs


class AppointmentDetailOutputSerializer(serializers.ModelSerializer):
    """Chi tiết từng liệu trình của khách trong lịch hẹn"""
    service_name = serializers.CharField(source='service.name', read_only=True)
    service_price = serializers.DecimalField(source='service.price_vnd', max_digits=12, decimal_places=0, read_only=True)
    service_duration = serializers.IntegerField(source='service.duration_minutes', read_only=True)

    class Meta:
        model = AppointmentDetail
        fields = ['id', 'guest_index', 'gender', 'service', 'service_name', 'service_price', 'service_duration', 'massage_pressure']


class AppointmentFullSerializer(serializers.ModelSerializer):
    """
    Serializer đầy đủ cho Lịch hẹn (Dùng cho Digital Pass Node 154:4478 và Danh sách lịch cá nhân UC-1.2)
    """
    details = AppointmentDetailOutputSerializer(many=True, read_only=True)
    formatted_total_price = serializers.SerializerMethodField()
    voucher_code = serializers.CharField(source='voucher.voucher_code', read_only=True, default='')
    discount_amount = serializers.SerializerMethodField()
    date_display = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            'id', 'appointment_code', 'customer_name', 'customer_phone', 'customer_email',
            'preferred_contact_channel', 'appointment_date', 'date_display', 'time_slot',
            'total_guests', 'male_guests', 'female_guests', 'note', 'status',
            'total_price', 'formatted_total_price', 'voucher_code', 'discount_amount',
            'cancel_reason', 'refund_account_number', 'created_at', 'details'
        ]

    def get_formatted_total_price(self, obj):
        return f"{int(obj.total_price):,}".replace(',', '.') + " VNĐ"

    def get_discount_amount(self, obj):
        if not obj.voucher:
            return 0
        v = obj.voucher
        if v.discount_type == 'Phần trăm':
            # Tính tương đối
            raw = (obj.total_price * Decimal(v.discount_value)) / Decimal(100 - v.discount_value if v.discount_value < 100 else 1)
            return min(int(raw), int(v.max_discount_amount or 999999999))
        return int(v.discount_value)

    def get_date_display(self, obj):
        # Format: Thứ Sáu, 16 tháng 10, 2026
        d = obj.appointment_date
        weekday_map = {
            0: 'Thứ Hai', 1: 'Thứ Ba', 2: 'Thứ Tư', 3: 'Thứ Năm',
            4: 'Thứ Sáu', 5: 'Thứ Bảy', 6: 'Chủ Nhật'
        }
        weekday = weekday_map.get(d.weekday(), '')
        return f"{weekday}, ngày {d.day} tháng {d.month}, {d.year}"
