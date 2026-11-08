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
        if status_param in ['Hold', 'Pending']:
            qs = qs.filter(status__in=['Hold', 'Pending'])
        elif status_param in ['Confirmed', 'In_Progress']:
            qs = qs.filter(status__in=['Confirmed', 'In_Progress'])
        elif status_param == 'Completed':
            qs = qs.filter(status='Completed')
        elif status_param == 'Cancelled':
            qs = qs.filter(status='Cancelled')

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
        'confirmed': all_day_qs.filter(status__in=['Confirmed', 'In_Progress']).count(),
        'pending': all_day_qs.filter(status__in=['Hold', 'Pending']).count(),
        'completed': all_day_qs.filter(status='Completed').count(),
        'cancelled': all_day_qs.filter(status='Cancelled').count(),
        'visible': len(appointments)
    }

    # 5. Cấu hình bảng màu nhãn trạng thái chuẩn Figma (3 trạng thái cốt lõi: Chờ xác nhận, Đã xác nhận, Đã hoàn thành, Đã hủy)
    status_config = {
        'Confirmed': {
            'label': 'Đã xác nhận',
            'badge_bg': '#EAF5EF',
            'badge_color': '#167455',
            'dot_color': '#167455',
            'class': 'status-confirmed'
        },
        'In_Progress': {
            'label': 'Đã xác nhận',
            'badge_bg': '#EAF5EF',
            'badge_color': '#167455',
            'dot_color': '#167455',
            'class': 'status-confirmed'
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

    from core.models import Tier
    tiers = Tier.objects.all().order_by('min_points')

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
        'tiers': tiers,
    }
    return render(request, 'appointment/staff_appointments.html', context)


@login_required
def admin_appointments_view(request):
    """
    Màn hình Quản lý Lịch hẹn toàn hệ thống dành cho Admin / Ban Quản lý (UC-1.5)
    Đồng bộ và thống nhất cấu trúc vận hành với phân hệ Staff, tích hợp 3 thẻ chỉ số KPI
    và tự động tích lũy điểm thưởng thành viên khi hoàn thành lịch hẹn.
    """
    from datetime import timedelta
    from django.db.models import Q

    # 1. Phân quyền Admin
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, 'Bạn không có quyền truy cập khu vực Quản trị Lịch hẹn của Admin.')
        return redirect('appointment:booking')

    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    # 2. Xử lý các tham số lọc từ GET request
    search_param = (request.GET.get('search') or request.GET.get('q') or '').strip()
    date_param = request.GET.get('date')
    slot_param = (request.GET.get('time_slot') or '').strip()
    status_param = (request.GET.get('status') or '').strip()

    # Xử lý ngày chọn (Mặc định hôm nay nếu không chỉ định)
    if date_param:
        try:
            selected_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    elif date_param == '':
        selected_date = None
    else:
        selected_date = today

    # 3. Lọc danh sách lịch hẹn
    qs = Appointment.objects.select_related('voucher', 'user__membership__tier').prefetch_related('details__service')

    if selected_date:
        qs = qs.filter(appointment_date=selected_date)

    if slot_param and slot_param != 'all' and slot_param != 'Tất cả khung giờ':
        qs = qs.filter(time_slot=slot_param)

    if status_param and status_param != 'all' and status_param != 'Tất cả trạng thái':
        if status_param in ['Hold', 'Pending']:
            qs = qs.filter(status__in=['Hold', 'Pending'])
        elif status_param in ['Confirmed', 'In_Progress']:
            qs = qs.filter(status__in=['Confirmed', 'In_Progress'])
        elif status_param == 'Completed':
            qs = qs.filter(status='Completed')
        elif status_param == 'Cancelled':
            qs = qs.filter(status='Cancelled')
        elif status_param in ['waiting', 'Đang chờ']:
            qs = qs.filter(status__in=['Hold', 'Pending', 'Confirmed', 'In_Progress'])

    if search_param:
        qs = qs.filter(
            Q(appointment_code__icontains=search_param) |
            Q(customer_name__icontains=search_param) |
            Q(customer_phone__icontains=search_param)
        )

    appointments = list(qs.order_by('time_slot', '-created_at'))

    # 4. Tính toán 3 thẻ chỉ số Operational Metrics (Admin KPIs)
    today_count = Appointment.objects.filter(appointment_date=today).count()
    yesterday_count = Appointment.objects.filter(appointment_date=yesterday).count()
    diff_count = today_count - yesterday_count
    if diff_count > 0:
        diff_str = f"+{diff_count} so với hôm qua"
    elif diff_count < 0:
        diff_str = f"{diff_count} so với hôm qua"
    else:
        diff_str = "+0 so với hôm qua"

    waiting_count = Appointment.objects.filter(status__in=['Hold', 'Pending', 'Confirmed', 'In_Progress']).count()
    waiting_today_count = Appointment.objects.filter(
        appointment_date=today,
        status__in=['Hold', 'Pending', 'Confirmed', 'In_Progress']
    ).count()

    completed_count = Appointment.objects.filter(status='Completed').count()

    metrics = {
        'today': {
            'value': today_count,
            'note': diff_str
        },
        'waiting': {
            'value': waiting_count,
            'note': f'{waiting_today_count} lịch hôm nay'
        },
        'completed': {
            'value': completed_count,
            'note': 'Đã cộng điểm thưởng'
        }
    }

    # 5. Thống kê theo ngày đã chọn
    all_day_qs = Appointment.objects.filter(appointment_date=selected_date) if selected_date else Appointment.objects.all()
    counts = {
        'total_day': all_day_qs.count(),
        'confirmed': all_day_qs.filter(status__in=['Confirmed', 'In_Progress']).count(),
        'pending': all_day_qs.filter(status__in=['Hold', 'Pending']).count(),
        'completed': all_day_qs.filter(status='Completed').count(),
        'cancelled': all_day_qs.filter(status='Cancelled').count(),
        'visible': len(appointments)
    }

    # 6. Cấu hình bảng màu nhãn trạng thái chuẩn Figma (3 trạng thái cốt lõi: Chờ xác nhận, Đã xác nhận, Đã hoàn thành, Đã hủy)
    status_config = {
        'Confirmed': {
            'label': 'Đã xác nhận',
            'badge_bg': '#EAF5EF',
            'badge_color': '#167455',
            'dot_color': '#167455',
            'class': 'status-confirmed'
        },
        'In_Progress': {
            'label': 'Đã xác nhận',
            'badge_bg': '#EAF5EF',
            'badge_color': '#167455',
            'dot_color': '#167455',
            'class': 'status-confirmed'
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

    # 7. Format dữ liệu từng hàng khớp 100% giao diện Figma
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

        if appt.user and hasattr(appt.user, 'membership') and appt.user.membership:
            mem = appt.user.membership
            tier_name = mem.tier.name if mem.tier else 'Member'
            pts_formatted = f"{mem.current_points:,}".replace(',', '.')
            appt.customer_cue = f"{tier_name} · {pts_formatted} điểm"
            appt.has_profile = True
        elif appt.user:
            tier_name = getattr(appt.user, 'membership_tier', '') or 'Member'
            appt.customer_cue = f"{tier_name} · Có hồ sơ sức khỏe"
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
        'metrics': metrics,
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
    return render(request, 'appointment/admin_appointments.html', context)


@login_required
def admin_export_appointments_view(request):
    """
    Xuất danh sách lịch hẹn ra file CSV chuẩn UTF-8 BOM cho Excel
    """
    import csv
    from django.http import HttpResponse
    from django.db.models import Q

    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponse('Bạn không có quyền truy cập.', status=403)

    search_query = (request.GET.get('search') or request.GET.get('q') or '').strip()
    date_str = request.GET.get('date', '').strip()
    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()
    slot_param = request.GET.get('time_slot', '').strip()
    status_filter = request.GET.get('status', '').strip()

    qs = Appointment.objects.select_related('voucher', 'user__membership__tier').prefetch_related('details__service')

    if search_query:
        qs = qs.filter(
            Q(appointment_code__icontains=search_query) |
            Q(customer_name__icontains=search_query) |
            Q(customer_phone__icontains=search_query)
        )

    if date_str and date_str != 'all':
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d').date()
            qs = qs.filter(appointment_date=d)
        except ValueError:
            pass
    else:
        if date_from_str:
            try:
                df = datetime.strptime(date_from_str, '%Y-%m-%d').date()
                qs = qs.filter(appointment_date__gte=df)
            except ValueError:
                pass
        if date_to_str:
            try:
                dt = datetime.strptime(date_to_str, '%Y-%m-%d').date()
                qs = qs.filter(appointment_date__lte=dt)
            except ValueError:
                pass

    if slot_param and slot_param != 'all' and slot_param != 'Tất cả khung giờ':
        qs = qs.filter(time_slot=slot_param)

    if status_filter and status_filter != 'all' and status_filter != 'Tất cả trạng thái':
        if status_filter in ['Hold', 'Pending', 'Confirmed', 'In_Progress', 'Completed', 'Cancelled']:
            qs = qs.filter(status=status_filter)
        elif status_filter in ['waiting', 'Đang chờ']:
            qs = qs.filter(status__in=['Hold', 'Pending', 'Confirmed', 'In_Progress'])

    appointments = qs.order_by('-appointment_date', 'time_slot')

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="Danh_sach_lich_hen_ChamSpa_{timezone.localdate().strftime("%d_%m_%Y")}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Mã lịch hẹn', 'Khách hàng', 'Hạng thành viên', 'Số điện thoại', 'Email',
        'Ngày hẹn', 'Khung giờ', 'Dịch vụ', 'Số khách', 'Tổng tiền (VNĐ)', 'Trạng thái', 'Ghi chú'
    ])

    for a in appointments:
        mem_info = 'Khách vãng lai'
        if a.user and hasattr(a.user, 'membership') and a.user.membership:
            t = a.user.membership.tier.name if a.user.membership.tier else 'Member'
            mem_info = f"{t} ({a.user.membership.current_points} điểm)"

        svc_names = ", ".join([d.service.name for d in a.details.all() if d.service])
        writer.writerow([
            a.appointment_code,
            a.customer_name,
            mem_info,
            a.customer_phone,
            a.customer_email,
            a.appointment_date.strftime('%d/%m/%Y'),
            a.time_slot,
            svc_names,
            a.total_guests,
            int(a.total_price),
            a.status,
            a.note
        ])

    return response
