"""
Views giao diện cho Phân hệ Quản lý Lịch hẹn (MOD-01) - CHAMSPA CRM
Tác giả: Nhật Quang (Leader)
Khớp 100% Thiết kế Figma:
  - Form đặt lịch hẹn trực tuyến: Node 828:515
  - Modal thanh toán VietQR: Node 818:2
  - Phiếu xác nhận đặt lịch hoàn tất (Digital Pass): Node 154:4478
"""

from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from core.models import Appointment, AppointmentDetail, Service, Voucher


def booking_view(request):
    """
    Màn hình Đặt lịch trải nghiệm (UC-1.1)
    Khớp 100% Figma Node 828:515 (Form đặt lịch) & Node 818:2 (Modal VietQR)
    
    YÊU CẦU PHÂN QUYỀN NGHIÊM NGẶT:
      - CHỈ DUY NHẤT khách hàng ĐÃ ĐĂNG NHẬP (is_authenticated và KHÔNG phải staff/superuser) mới có thể bấm đặt lịch.
      - Khách hàng chưa đăng nhập, Staff, Admin: KHÔNG THỂ NÀO BẤM ĐẶT LỊCH ĐƯỢC (Nút bị khóa, hiển thị nhãn và banner cảnh báo rõ ràng).
      - Tự động điền sẵn thông tin khách hàng từ tài khoản chính chủ đã đăng nhập, tránh nhập lại thủ công.
    """
    user = request.user

    # 1. Xác định vai trò người dùng trong hệ thống
    if not user.is_authenticated:
        user_role = 'anonymous'
    elif user.is_superuser:
        user_role = 'admin'
    elif user.is_staff:
        user_role = 'staff'
    else:
        user_role = 'customer'

    can_book = (user_role == 'customer')

    services = Service.objects.filter(status='Hoạt động').order_by('id')
    today = timezone.localdate()

    # 2. Khởi tạo thông tin người dùng
    initial_user = {
        'name': '',
        'phone': '',
        'display_phone': '',
        'email': '',
    }

    if user.is_authenticated:
        user_name = (user.name or '').strip() or user.get_full_name().strip() or user.username
        raw_phone = (user.phone or '').strip() or (user.username if user.username.isdigit() else '')

        clean_phone = raw_phone
        if clean_phone.startswith('+84'):
            clean_phone = clean_phone[3:].strip()
        elif clean_phone.startswith('84') and len(clean_phone) in (10, 11):
            clean_phone = clean_phone[2:].strip()
        elif clean_phone.startswith('0'):
            clean_phone = clean_phone[1:].strip()

        initial_user = {
            'name': user_name,
            'phone': clean_phone,
            'display_phone': raw_phone or ('0' + clean_phone if clean_phone else ''),
            'email': (user.email or '').strip(),
        }

    # 4 Khung giờ chính chuẩn Figma (09:00, 10:00, 14:00, 16:00)
    time_slots = [
        {"slot": "09:00", "label": "09:00"},
        {"slot": "10:00", "label": "10:00"},
        {"slot": "14:00", "label": "14:00"},
        {"slot": "16:00", "label": "16:00"},
    ]

    selected_service_id = request.GET.get('service', '')

    services_data = [
        {
            'id': s.id,
            'name': s.name,
            'price_vnd': float(s.price_vnd),
            'formatted_price': f"{int(s.price_vnd):,}".replace(',', '.') + " VNĐ",
            'duration_minutes': s.duration_minutes,
            'description': s.description or ''
        }
        for s in services
    ]

    context = {
        'services': services,
        'services_data': services_data,
        'today': today,
        'today_str': today.strftime('%Y-%m-%d'),
        'initial_user': initial_user,
        'time_slots': time_slots,
        'selected_service_id': selected_service_id,
        'user_role': user_role,
        'can_book': can_book,
        'is_customer': can_book,
    }
    return render(request, 'appointment/booking.html', context)


def booking_success_view(request, code):
    """
    Màn hình Giữ chỗ & Nhận mã - Phiếu xác nhận đặt lịch hoàn tất (Digital Pass) (UC-1.1)
    Khớp 100% Figma Node 154:4478
    """
    clean_code = code if code.startswith('#') else f"#{code}"
    appointment = get_object_or_404(
        Appointment.objects.select_related('voucher', 'user').prefetch_related('details__service'),
        appointment_code=clean_code
    )

    details = appointment.details.all().select_related('service')

    weekday_map = {
        0: 'Thứ Hai', 1: 'Thứ Ba', 2: 'Thứ Tư', 3: 'Thứ Năm',
        4: 'Thứ Sáu', 5: 'Thứ Bảy', 6: 'Chủ Nhật'
    }
    d = appointment.appointment_date
    date_display = f"{weekday_map.get(d.weekday(), '')}, ngày {d.day:02d} tháng {d.month:02d}, {d.year}"

    discount_amount = 0
    if appointment.voucher:
        v = appointment.voucher
        if v.discount_type in ['PERCENT', 'Phần trăm']:
            discount_amount = int((appointment.total_price * v.discount_value) / 100)
            if v.max_discount_amount:
                discount_amount = min(discount_amount, int(v.max_discount_amount))
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
    Màn hình Quản lý lịch hẹn cá nhân cho Khách hàng (UC-1.2, UC-1.3, UC-1.4)
    Khớp 100% Figma Node 166:563 (Quản lý lịch cá nhân)
    Tích hợp Modal Dời lịch (Node 172:3086) và Modal Hủy lịch (Node 172:3088)
    """
    appointments = Appointment.objects.filter(user=request.user)\
        .select_related('voucher')\
        .prefetch_related('details__service')\
        .order_by('-appointment_date', '-time_slot')

    weekday_map = {
        0: 'Thứ Hai', 1: 'Thứ Ba', 2: 'Thứ Tư', 3: 'Thứ Năm',
        4: 'Thứ Sáu', 5: 'Thứ Bảy', 6: 'Chủ Nhật'
    }

    # Format hiển thị từng lịch hẹn khớp chuẩn Figma
    for appt in appointments:
        w_name = weekday_map.get(appt.appointment_date.weekday(), '')
        appt.date_vn_formatted = f"{appt.time_slot}, {w_name} - {appt.appointment_date.strftime('%d/%m/%Y')}"
        appt.booking_date_formatted = appt.created_at.strftime('%d/%m/%Y') if appt.created_at else appt.appointment_date.strftime('%d/%m/%Y')
        appt.formatted_price = f"{int(appt.total_price):,}".replace(',', '.') + " VNĐ"
        appt.is_upcoming = appt.status in ['Hold', 'Pending', 'Confirmed']
        appt.is_completed = appt.status == 'Completed'
        appt.is_cancelled = appt.status == 'Cancelled'

    counts = {
        'all': appointments.count(),
        'upcoming': sum(1 for a in appointments if a.is_upcoming),
        'completed': sum(1 for a in appointments if a.is_completed),
        'cancelled': sum(1 for a in appointments if a.is_cancelled),
    }

    context = {
        'appointments': appointments,
        'counts': counts,
    }
    return render(request, 'appointment/my_appointments.html', context)


@login_required
def staff_appointments_view(request):
    """
    Màn hình Quản lý Lịch hẹn cho Nhân viên Lễ tân / CSKH (UC-1.5)
    Khớp 100% Figma Node 110:4969 (Staff Dashboard / Lịch hẹn hôm nay)
    
    Phân quyền:
      - Chỉ Nhân viên (is_staff) hoặc Quản lý (is_superuser) mới được quyền truy cập.
      - Khách hàng không có thẩm quyền sẽ được chuyển hướng an toàn về trang cá nhân.
    
    Tính năng:
      - Bộ lọc: Tên khách/SĐT/Mã đơn, Ngày đặt lịch, Khung giờ, Trạng thái.
      - Cập nhật trạng thái trực tiếp: Tiếp nhận, Hoàn thành, Hủy nhanh qua Fetch API.
      - Modal Đặt lịch nhanh tại quầy (Quick-create) cho khách vãng lai.
      - Modal Xem chi tiết lịch hẹn.
    """
    from django.db.models import Q

    # 1. Kiểm tra phân quyền truy cập
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập khu vực Quản lý Lịch hẹn của Nhân viên.')
        return redirect('appointment:booking')

    today = timezone.localdate()

    # 2. Xử lý tham số bộ lọc từ query string
    date_param = request.GET.get('date', '').strip()
    slot_param = request.GET.get('time_slot', '').strip()
    status_param = request.GET.get('status', '').strip()
    search_param = request.GET.get('search', '').strip() or request.GET.get('q', '').strip()

    selected_date = None
    if date_param:
        if date_param.lower() != 'all':
            try:
                selected_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                selected_date = today
    else:
        # Mặc định lấy ngày hôm nay
        selected_date = today

    # 3. Lọc danh sách lịch hẹn
    qs = Appointment.objects.select_related('voucher', 'user').prefetch_related('details__service')

    if selected_date:
        qs = qs.filter(appointment_date=selected_date)

    if slot_param and slot_param != 'all' and slot_param != 'Tất cả khung giờ':
        qs = qs.filter(time_slot=slot_param)

    if status_param and status_param != 'all' and status_param != 'Tất cả trạng thái':
        if status_param in ['Hold', 'Pending', 'Confirmed', 'In_Progress', 'Completed', 'Cancelled']:
            qs = qs.filter(status=status_param)

    if search_param:
        qs = qs.filter(
            Q(appointment_code__icontains=search_param) |
            Q(customer_name__icontains=search_param) |
            Q(customer_phone__icontains=search_param)
        )

    appointments = list(qs.order_by('time_slot', '-created_at'))

    # 4. Thống kê theo ngày đã chọn
    all_day_qs = Appointment.objects.filter(appointment_date=selected_date) if selected_date else Appointment.objects.all()
    counts = {
        'total_day': all_day_qs.count(),
        'in_progress': all_day_qs.filter(status='In_Progress').count(),
        'confirmed': all_day_qs.filter(status='Confirmed').count(),
        'pending': all_day_qs.filter(status__in=['Hold', 'Pending']).count(),
        'completed': all_day_qs.filter(status='Completed').count(),
        'cancelled': all_day_qs.filter(status='Cancelled').count(),
        'visible': len(appointments)
    }

    # 5. Cấu hình bảng màu nhãn trạng thái chuẩn Figma
    status_config = {
        'Confirmed': {
            'label': 'Đã xác nhận',
            'badge_bg': '#EAF5EF',
            'badge_color': '#167455',
            'dot_color': '#167455',
            'class': 'status-confirmed'
        },
        'In_Progress': {
            'label': 'Đang phục vụ',
            'badge_bg': '#E8F4FD',
            'badge_color': '#026AA2',
            'dot_color': '#026AA2',
            'class': 'status-in-progress'
        },
        'Hold': {
            'label': 'Chờ xác nhận',
            'badge_bg': '#FEF6E7',
            'badge_color': '#B25E09',
            'dot_color': '#B25E09',
            'class': 'status-pending'
        },
        'Pending': {
            'label': 'Chờ xác nhận',
            'badge_bg': '#FEF6E7',
            'badge_color': '#B25E09',
            'dot_color': '#B25E09',
            'class': 'status-pending'
        },
        'Completed': {
            'label': 'Đã hoàn thành',
            'badge_bg': '#F3EFFB',
            'badge_color': '#5925DC',
            'dot_color': '#5925DC',
            'class': 'status-completed'
        },
        'Cancelled': {
            'label': 'Đã hủy',
            'badge_bg': '#FEE4E2',
            'badge_color': '#B42318',
            'dot_color': '#B42318',
            'class': 'status-cancelled'
        }
    }

    # 6. Format dữ liệu từng hàng khớp giao diện Figma
    for appt in appointments:
        first_detail = appt.details.first()
        if first_detail and first_detail.service:
            svc_name = first_detail.service.name
            duration = first_detail.service.duration_minutes
            extra_count = appt.details.count() - 1
            if extra_count > 0:
                appt.service_summary = f"{svc_name} · {duration} phút (+{extra_count})"
            else:
                appt.service_summary = f"{svc_name} · {duration} phút"
        else:
            appt.service_summary = f"{appt.total_guests} khách"

        if appt.user:
            tier = getattr(appt.user, 'membership_tier', '') or 'Gold'
            appt.customer_cue = f"{tier} · Có hồ sơ sức khỏe"
            appt.has_profile = True
        else:
            appt.customer_cue = "Khách vãng lai"
            appt.has_profile = False

        cfg = status_config.get(appt.status, status_config['Hold'])
        appt.status_display = cfg['label']
        appt.status_bg = cfg['badge_bg']
        appt.status_color = cfg['badge_color']
        appt.status_dot = cfg['dot_color']
        appt.status_class = cfg['class']
        appt.price_vnd_formatted = f"{int(appt.total_price):,}".replace(',', '.') + " VNĐ"

    services = Service.objects.filter(status='Hoạt động').order_by('id')
    time_slots = ['09:00', '10:00', '10:30', '11:30', '13:00', '14:00', '15:30', '16:00', '16:30', '17:00', '17:30', '19:00', '20:00']

    context = {
        'appointments': appointments,
        'counts': counts,
        'selected_date': selected_date.strftime('%Y-%m-%d') if selected_date else '',
        'selected_date_display': selected_date.strftime('%d/%m/%Y') if selected_date else 'Tất cả các ngày',
        'selected_slot': slot_param,
        'selected_status': status_param,
        'search_query': search_param,
        'services': services,
        'time_slots': time_slots,
        'today_str': today.strftime('%Y-%m-%d'),
    }
    return render(request, 'appointment/staff_appointments.html', context)
