from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from core.models import Appointment, AppointmentDetail, Service, Voucher


def booking_view(request):
    """
    Màn hình Đặt lịch trải nghiệm (UC-1.1)
    Khớp 100% Figma Node 828:515 (Form đặt lịch) & Node 818:2 (Modal VietQR)
    QUY TẮC: Chỉ tài khoản Khách hàng đã đăng nhập mới được phép đặt lịch.
    """
    services = Service.objects.filter(status='Hoạt động').order_by('id')
    today = timezone.localdate()

    is_customer = False
    auth_warning = None

    if not request.user.is_authenticated:
        is_customer = False
        auth_warning = 'NOT_LOGGED_IN'
    elif request.user.is_staff or request.user.is_superuser:
        is_customer = False
        auth_warning = 'NOT_CUSTOMER'
    else:
        is_customer = True

    # Tự động điền thông tin nếu khách hàng đã đăng nhập
    initial_user = {
        'name': '',
        'phone': '',
        'email': ''
    }
    if request.user.is_authenticated:
        initial_user['name'] = request.user.name or request.user.get_full_name() or request.user.username
        initial_user['phone'] = request.user.phone or (request.user.username if request.user.username.isdigit() else '')
        initial_user['email'] = request.user.email or ''

    # Danh sách khung giờ mẫu
    time_slots = [
        {"slot": "09:00", "label": "09:00"},
        {"slot": "10:00", "label": "10:00"},
        {"slot": "14:00", "label": "14:00"},
        {"slot": "16:00", "label": "16:00"},
    ]

    selected_service_id = request.GET.get('service', '')

    context = {
        'services': services,
        'today': today,
        'today_str': today.strftime('%Y-%m-%d'),
        'initial_user': initial_user,
        'time_slots': time_slots,
        'selected_service_id': selected_service_id,
        'is_customer': is_customer,
        'auth_warning': auth_warning,
    }
    return render(request, 'appointment/booking.html', context)


def booking_success_view(request, code):
    """
    Màn hình Giữ chỗ & Nhận mã - Digital Pass Vé trải nghiệm chi tiết (UC-1.1)
    Khớp 100% Figma Node 154:4478
    """
    clean_code = code if code.startswith('#') else f"#{code}"
    appointment = get_object_or_404(Appointment, appointment_code=clean_code)

    # Chi tiết từng khách
    details = appointment.details.all().select_related('service')

    # Định dạng thứ trong tuần bằng tiếng Việt
    weekday_map = {
        0: 'Thứ Hai', 1: 'Thứ Ba', 2: 'Thứ Tư', 3: 'Thứ Năm',
        4: 'Thứ Sáu', 5: 'Thứ Bảy', 6: 'Chủ Nhật'
    }
    d = appointment.appointment_date
    date_display = f"{weekday_map.get(d.weekday(), '')}, ngày {d.day} tháng {d.month}, {d.year}"

    # Tính giảm giá nếu có voucher
    discount_amount = 0
    if appointment.voucher:
        v = appointment.voucher
        if v.discount_type == 'Phần trăm':
            discount_amount = int((appointment.total_price * v.discount_value) / 100)
        else:
            discount_amount = int(v.discount_value)

    context = {
        'appointment': appointment,
        'details': details,
        'date_display': date_display,
        'discount_amount': discount_amount,
    }
    return render(request, 'appointment/booking_success.html', context)


@login_required
def my_appointments_view(request):
    """
    Màn hình Quản lý lịch hẹn cá nhân cho Khách hàng (UC-1.2)
    """
    appointments = Appointment.objects.filter(user=request.user).order_by('-appointment_date', '-time_slot')
    return render(request, 'appointment/my_appointments.html', {'appointments': appointments})
