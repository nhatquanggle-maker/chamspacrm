"""
API Endpoints (Pure Django JsonResponse) cho Phân hệ Quản lý Lịch hẹn - CHAMSPA CRM
"""

import random
import uuid
from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.ajax import (
    is_staff_or_admin,
    json_error,
    parse_json_body,
    require_auth_json,
    require_staff_json,
)
from core.models import (
    Appointment,
    AppointmentDetail,
    Invoice,
    Notification,
    Service,
    User,
    Voucher,
)
from marketing.utils import create_unique_notification


STANDARD_TIME_SLOTS = [
    "09:00", "09:30", "10:00", "10:30", "14:00", "14:30",
    "15:00", "15:30", "16:00", "17:00", "17:30", "19:00",
]

WEEKDAY_NAMES = {
    0: 'Thứ Hai', 1: 'Thứ Ba', 2: 'Thứ Tư', 3: 'Thứ Năm',
    4: 'Thứ Sáu', 5: 'Thứ Bảy', 6: 'Chủ Nhật',
}

STATUS_LABELS = {
    'Hold': 'Chờ thanh toán QR',
    'Pending': 'Đang chờ xác nhận',
    'Confirmed': 'Đã xác nhận',
    'In_Progress': 'Đang làm dịch vụ',
    'Completed': 'Đã hoàn thành',
    'Cancelled': 'Đã hủy',
}


def generate_notification_code(prefix="TB"):
    """Sinh mã định danh thông báo duy nhất."""
    return f"{prefix}-{int(timezone.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"


def _generate_appointment_code():
    """Sinh mã lịch hẹn độc nhất dạng #LHxxxxx."""
    for _ in range(15):
        cand = f"#LH{random.randint(10000, 99999)}"
        if not Appointment.objects.filter(appointment_code=cand).exists():
            return cand
    return f"#LH{int(timezone.now().timestamp()) % 100000:05d}"


def parse_slot_time(time_slot):
    """Chuyển chuỗi khung giờ 'HH:MM' thành đối tượng datetime.time."""
    try:
        return datetime.strptime(str(time_slot).strip(), '%H:%M').time()
    except ValueError:
        return None


def is_slot_in_past(target_date, time_slot, now_local=None):
    """Kiểm tra ngày và khung giờ đã qua so với thời gian thực chưa."""
    now_local = now_local or timezone.localtime()
    today_local = now_local.date()
    if target_date < today_local:
        return True
    if target_date > today_local:
        return False
    slot_t = parse_slot_time(time_slot)
    if slot_t is None:
        return False
    return slot_t <= now_local.time()


def _parse_int(value, default=None):
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ('true', '1'):
            return True
        if low in ('false', '0'):
            return False
    return None


def _can_access_appointment(request, appointment):
    """Chỉ cho phép Staff/Admin, chủ sở hữu lịch hẹn hoặc phiên vừa đặt lịch."""
    if is_staff_or_admin(request.user):
        return True
    if request.user.is_authenticated and appointment.user_id == request.user.id:
        return True
    recent_ids = request.session.get('recent_booking_ids', [])
    return appointment.id in recent_ids


def _remember_booking_in_session(request, appointment_id):
    recent = list(request.session.get('recent_booking_ids', []))
    if appointment_id not in recent:
        recent.append(appointment_id)
    request.session['recent_booking_ids'] = recent[-20:]
    request.session.modified = True


def _compute_voucher_discount(voucher, total_amount):
    """Tính toán số tiền được giảm từ voucher, chặn không vượt quá tổng đơn."""
    if voucher.discount_type in ['PERCENT', 'Phần trăm']:
        discount = (total_amount * Decimal(voucher.discount_value)) / Decimal(100)
        if voucher.max_discount_amount and discount > voucher.max_discount_amount:
            discount = Decimal(voucher.max_discount_amount)
    else:
        discount = Decimal(voucher.discount_value)
    return min(discount, total_amount)


def _format_vnd(amount):
    return f"{int(amount):,}".replace(',', '.') + " VNĐ"


def _serialize_appointment_user(obj):
    user = obj.user
    if not user and obj.customer_phone:
        clean_phone = obj.customer_phone.replace(' ', '').replace('.', '').replace('-', '').strip()
        user = User.objects.filter(phone=clean_phone).first() or User.objects.filter(username=clean_phone).first()
    if not user:
        return None

    membership = getattr(user, 'membership', None)
    tier_name = membership.tier.name if (membership and membership.tier) else "Thành viên"
    points = membership.current_points if membership else 0

    health_profile = getattr(user, 'health_profile', None) or getattr(user, 'userhealthprofile', None)
    has_health = health_profile is not None

    return {
        'id': user.id,
        'name': user.name or user.get_full_name() or user.username,
        'phone': user.phone or '',
        'email': user.email or '',
        'membership_tier': tier_name,
        'membership_points': points,
        'has_health_profile': has_health,
        'health_code': health_profile.health_code if has_health else None,
        'blood_pressure': health_profile.blood_pressure if has_health else None,
        'focus_areas': health_profile.focus_areas if has_health else [],
        'special_requests': health_profile.special_requests if has_health else '',
        'massage_pressure': health_profile.massage_pressure if has_health else '',
    }


def _get_payment_info(obj):
    invoice = getattr(obj, 'invoice', None)
    method = 'transfer'
    is_paid = False
    paid_at = None

    if invoice:
        paid_at = invoice.paid_at.strftime('%H:%M %d/%m/%Y') if invoice.paid_at else None
        is_paid = (invoice.status == 'Đã thanh toán')
        reason = (invoice.reason_refuse or '').lower()
        if 'quầy' in reason or 'tiền mặt' in reason or 'pos' in reason:
            method = 'counter'
    else:
        note_lower = (obj.note or '').lower()
        channel_lower = (obj.preferred_contact_channel or '').lower()
        if 'quầy' in note_lower or 'quầy' in channel_lower or 'tiền mặt' in note_lower:
            method = 'counter'
        elif obj.status in ['Confirmed', 'Completed']:
            is_paid = True
        if obj.status == 'Completed':
            is_paid = True

    if method == 'transfer':
        method_label = 'Chuyển khoản (VietQR)'
        if is_paid:
            status_label = 'Đã chuyển khoản'
            badge_bg = '#EAF5EF'
            badge_color = '#167455'
            icon = 'bi-qr-code-scan'
            desc = 'Đã quét mã VietQR và chuyển khoản thành công'
        else:
            status_label = 'Chờ chuyển khoản'
            badge_bg = '#EFF8FF'
            badge_color = '#175CD3'
            icon = 'bi-qr-code'
            desc = 'Chưa nhận được chuyển khoản ngân hàng'
    else:
        method_label = 'Tới quầy trả tiền'
        if is_paid:
            status_label = 'Đã thanh toán tại quầy'
            badge_bg = '#EAF5EF'
            badge_color = '#167455'
            icon = 'bi-cash-coin'
            desc = 'Đã thanh toán tiền mặt / thẻ POS tại quầy lễ tân'
        else:
            status_label = 'Tới quầy trả tiền'
            badge_bg = '#FEF6E7'
            badge_color = '#B25E09'
            icon = 'bi-cash-coin'
            desc = 'Khách sẽ thanh toán trực tiếp khi tới quầy'

    return {
        'method': method,
        'method_label': method_label,
        'is_paid': is_paid,
        'status_label': status_label,
        'badge_bg': badge_bg,
        'badge_color': badge_color,
        'icon': icon,
        'description': desc,
        'paid_at': paid_at,
    }


def _get_appointment_discount(obj):
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


def serialize_appointment_full(obj):
    """Chuyển đổi Appointment thành dict JSON đầy đủ cho giao diện & nhân sự."""
    details_qs = obj.details.all().select_related('service')
    details = []
    names = []
    for d in details_qs:
        svc = d.service
        if svc:
            names.append(svc.name)
        details.append({
            'id': d.id,
            'guest_index': d.guest_index,
            'gender': d.gender,
            'service_id': svc.id if svc else None,
            'service_name': svc.name if svc else '',
            'service_price': f"{Decimal(svc.price_vnd):.0f}" if svc else "0",
            'service_duration': svc.duration_minutes if svc else 0,
            'massage_pressure': d.massage_pressure,
        })

    if len(names) == 1:
        service_name = names[0]
    elif len(names) > 1:
        service_name = f"{names[0]} (+{len(names) - 1} dịch vụ khác)"
    else:
        service_name = "Dịch vụ Massage & Trị liệu Cham Spa"

    discount_val = _get_appointment_discount(obj)
    d = obj.appointment_date
    weekday = WEEKDAY_NAMES.get(d.weekday(), '') if hasattr(d, 'weekday') else ''
    date_display = f"{weekday}, ngày {d.day:02d} tháng {d.month:02d}, {d.year}" if hasattr(d, 'day') else str(d)

    return {
        'id': obj.id,
        'appointment_code': obj.appointment_code,
        'customer_name': obj.customer_name,
        'customer_phone': obj.customer_phone,
        'customer_email': obj.customer_email,
        'preferred_contact_channel': obj.preferred_contact_channel,
        'appointment_date': d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d),
        'date_display': date_display,
        'time_slot': obj.time_slot,
        'total_guests': obj.total_guests,
        'male_guests': obj.male_guests,
        'female_guests': obj.female_guests,
        'note': obj.note,
        'status': obj.status,
        'status_label': STATUS_LABELS.get(obj.status, obj.status),
        'total_price': f"{Decimal(obj.total_price):.2f}",
        'formatted_total_price': _format_vnd(obj.total_price),
        'voucher_id': obj.voucher_id,
        'voucher_code': obj.voucher.voucher_code if obj.voucher else '',
        'discount_amount': discount_val,
        'formatted_discount': f"-{discount_val:,}".replace(',', '.') + " VNĐ" if discount_val > 0 else "0 VNĐ",
        'service_name': service_name,
        'cancel_reason': obj.cancel_reason,
        'refund_account_number': obj.refund_account_number,
        'created_at': timezone.localtime(obj.created_at).isoformat() if obj.created_at else None,
        'details': details,
        'payment': _get_payment_info(obj),
        'user': _serialize_appointment_user(obj),
    }


def _validate_date_and_slot(date_raw, time_slot_raw):
    """Kiểm tra ngày hẹn và khung giờ hợp lệ, không nằm trong quá khứ."""
    errors = {}
    appt_date = None
    if not date_raw:
        errors['appointment_date'] = "Vui lòng chọn ngày hẹn."
    else:
        try:
            appt_date = datetime.strptime(str(date_raw).strip(), '%Y-%m-%d').date()
            if appt_date < timezone.localdate():
                errors['appointment_date'] = "Không thể đặt lịch hẹn cho ngày trong quá khứ."
        except ValueError:
            errors['appointment_date'] = "Định dạng ngày hẹn không hợp lệ (YYYY-MM-DD)."

    time_slot = str(time_slot_raw or '').strip()
    if not time_slot:
        errors['time_slot'] = "Vui lòng chọn khung giờ."
    elif len(time_slot) > 20:
        errors['time_slot'] = "Khung giờ không hợp lệ."
    elif appt_date and not errors.get('appointment_date') and is_slot_in_past(appt_date, time_slot):
        errors['time_slot'] = (
            f"Khung giờ {time_slot} hôm nay đã qua so với thời gian thực. "
            "Vui lòng chọn khung giờ sau hoặc ngày khác."
        )

    return appt_date, time_slot, errors


def _validate_booking_payload(data):
    appt_date, time_slot, errors = _validate_date_and_slot(
        data.get('appointment_date'),
        data.get('time_slot'),
    )

    total_guests = _parse_int(data.get('total_guests'), default=1)
    male_guests = _parse_int(data.get('male_guests'), default=0)
    female_guests = _parse_int(data.get('female_guests'), default=0)

    if total_guests is None or total_guests < 1 or total_guests > 10:
        errors['total_guests'] = "Tổng số khách phải từ 1 đến 10 người."
    if male_guests is None or male_guests < 0:
        errors['male_guests'] = "Số khách nam không hợp lệ."
    if female_guests is None or female_guests < 0:
        errors['female_guests'] = "Số khách nữ không hợp lệ."

    if not errors:
        if male_guests + female_guests == 0:
            male_guests = total_guests
            female_guests = 0
        elif male_guests + female_guests != total_guests:
            total_guests = male_guests + female_guests
            if total_guests > 10:
                errors['total_guests'] = "Tổng số khách tối đa 10 người mỗi lượt."

    clean_phone = (data.get('customer_phone') or '').strip().replace(' ', '').replace('.', '').replace('-', '')
    if clean_phone and (len(clean_phone) < 9 or len(clean_phone) > 15):
        errors['customer_phone'] = "Số điện thoại không đúng định dạng."

    customer_email = (data.get('customer_email') or '').strip()
    if customer_email:
        try:
            validate_email(customer_email)
        except DjangoValidationError:
            errors['customer_email'] = "Email không đúng định dạng."

    raw_guests = data.get('guest_details') or data.get('guests') or []
    guest_details = []
    if isinstance(raw_guests, list):
        for idx, g in enumerate(raw_guests, start=1):
            if not isinstance(g, dict):
                errors['guest_details'] = "Thông tin chi tiết từng khách không hợp lệ."
                break
            g_idx = _parse_int(g.get('guest_index'), default=idx)
            gender = g.get('gender') or 'Nam'
            if gender not in ('Nam', 'Nữ'):
                gender = 'Nam'
            svc_id = _parse_int(g.get('service_id'), default=None)
            pressure = str(g.get('massage_pressure') or 'Vừa').strip()[:50]
            guest_details.append({
                'guest_index': g_idx or idx,
                'gender': gender,
                'service_id': svc_id,
                'massage_pressure': pressure or 'Vừa',
            })

    if errors:
        return None, errors

    return {
        'appointment_date': appt_date,
        'time_slot': time_slot,
        'total_guests': total_guests,
        'male_guests': male_guests,
        'female_guests': female_guests,
        'customer_name': (data.get('customer_name') or '').strip()[:255],
        'customer_phone': clean_phone,
        'customer_email': customer_email,
        'preferred_contact_channel': (data.get('preferred_contact_channel') or 'Điện thoại')[:50],
        'note': (data.get('note') or '').strip(),
        'voucher_code': (data.get('voucher_code') or '').strip().upper(),
        'service_id': _parse_int(data.get('service_id'), default=None),
        'guest_details': guest_details,
    }, None


def _validate_quick_create_payload(data):
    appt_date, time_slot, errors = _validate_date_and_slot(
        data.get('appointment_date'),
        data.get('time_slot'),
    )
    customer_name = (data.get('customer_name') or '').strip()
    customer_phone = (data.get('customer_phone') or '').strip()
    customer_email = (data.get('customer_email') or '').strip()
    service_id = _parse_int(data.get('service_id'), default=None)
    total_guests = _parse_int(data.get('total_guests'), default=1)
    male_guests = _parse_int(data.get('male_guests'), default=0)
    female_guests = _parse_int(data.get('female_guests'), default=1)
    appt_status = (data.get('status') or 'Confirmed').strip()

    if not customer_name:
        errors['customer_name'] = "Vui lòng nhập tên khách hàng."
    if not customer_phone:
        errors['customer_phone'] = "Vui lòng nhập số điện thoại khách hàng."
    if customer_email:
        try:
            validate_email(customer_email)
        except DjangoValidationError:
            errors['customer_email'] = "Email không đúng định dạng."
    if not service_id:
        errors['service_id'] = "Vui lòng chọn dịch vụ."
    if total_guests is None or total_guests < 1 or total_guests > 10:
        errors['total_guests'] = "Tổng số khách phải từ 1 đến 10."
    if male_guests is None or male_guests < 0:
        errors['male_guests'] = "Số khách nam không hợp lệ."
    if female_guests is None or female_guests < 0:
        errors['female_guests'] = "Số khách nữ không hợp lệ."
    if appt_status not in ('Confirmed', 'Hold', 'In_Progress'):
        errors['status'] = "Trạng thái khởi tạo không hợp lệ."

    if errors:
        return None, errors

    return {
        'customer_name': customer_name[:255],
        'customer_phone': customer_phone[:50],
        'customer_email': customer_email,
        'appointment_date': appt_date,
        'time_slot': time_slot,
        'service_id': service_id,
        'total_guests': total_guests,
        'male_guests': male_guests,
        'female_guests': female_guests,
        'note': (data.get('note') or 'Đặt trực tiếp tại quầy').strip(),
        'status': appt_status,
    }, None


@require_GET
def available_slots_api(request):
    """Kiểm tra danh sách khung giờ và số chỗ còn trống."""
    date_str = request.GET.get('date')
    if not date_str:
        target_date = timezone.localdate()
    else:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return json_error('Định dạng ngày không hợp lệ (YYYY-MM-DD)', status=400)

    bookings = Appointment.objects.filter(
        appointment_date=target_date
    ).exclude(status='Cancelled').values('time_slot').annotate(booked_guests=Sum('total_guests'))

    booked_map = {b['time_slot']: (b['booked_guests'] or 0) for b in bookings}
    now_local = timezone.localtime()

    result = []
    for slot in STANDARD_TIME_SLOTS:
        booked = booked_map.get(slot, 0)
        remaining = max(0, 10 - booked)
        is_past = is_slot_in_past(target_date, slot, now_local=now_local)
        if is_past:
            is_available = False
            status_label = 'Đã qua'
        elif remaining > 0:
            is_available = True
            status_label = 'Còn chỗ'
        else:
            is_available = False
            status_label = 'Kín lịch'
        result.append({
            'slot': slot,
            'booked': booked,
            'remaining': remaining,
            'is_available': is_available,
            'is_past': is_past,
            'status_label': status_label,
        })

    return JsonResponse({
        'status': 'success',
        'date': target_date.strftime('%Y-%m-%d'),
        'server_now': now_local.strftime('%Y-%m-%d %H:%M'),
        'slots': result,
    }, status=200)


@require_POST
def apply_voucher_api(request):
    """Kiểm tra và tính toán giảm giá của Voucher."""
    data, err = parse_json_body(request)
    if err:
        return err

    code = (data.get('code') or '').strip().upper()
    try:
        order_total = Decimal(str(data.get('order_total', 0)))
    except Exception:
        order_total = Decimal(0)

    if not code:
        return json_error('Vui lòng nhập mã Voucher', status=400)

    voucher = Voucher.objects.filter(voucher_code=code, status='Khả dụng').first()
    if not voucher:
        return json_error('Mã Voucher không tồn tại hoặc đã hết lượt sử dụng.', status=400)

    if voucher.expiry_date and voucher.expiry_date < timezone.now():
        return json_error('Mã Voucher đã hết hạn sử dụng.', status=400)

    if voucher.customer and (not request.user.is_authenticated or voucher.customer_id != request.user.id):
        return json_error('Mã Voucher này được cấp riêng cho một khách hàng khác.', status=403)

    if voucher.min_order_amount and order_total < voucher.min_order_amount:
        min_fmt = f"{int(voucher.min_order_amount):,}".replace(',', '.')
        return json_error(f'Voucher chỉ áp dụng cho đơn hàng từ {min_fmt} VNĐ trở lên.', status=400)

    discount_amount = _compute_voucher_discount(voucher, order_total)
    final_total = max(Decimal(0), order_total - discount_amount)

    return JsonResponse({
        'status': 'success',
        'success': True,
        'voucher_code': voucher.voucher_code,
        'discount_type': voucher.discount_type,
        'discount_value': float(voucher.discount_value),
        'discount_amount': float(discount_amount),
        'formatted_discount': f"-{_format_vnd(discount_amount)}",
        'final_total': float(final_total),
        'formatted_final_total': _format_vnd(final_total),
    }, status=200)


@require_POST
def appointment_create_api(request):
    """Tạo lịch hẹn trực tuyến (chỉ dành cho tài khoản Khách hàng)."""
    if not request.user.is_authenticated:
        return json_error(
            'Vui lòng đăng nhập tài khoản Khách hàng để thực hiện đặt lịch trải nghiệm.',
            status=401,
            status_code_label='error',
        )

    if is_staff_or_admin(request.user):
        return json_error(
            'Tài khoản Quản trị viên hoặc Nhân viên không có quyền đặt lịch trải nghiệm. Chức năng này chỉ dành riêng cho Khách hàng.',
            status=403,
        )

    raw_data, err = parse_json_body(request)
    if err:
        return err

    data, errors = _validate_booking_payload(raw_data)
    if errors:
        return JsonResponse({'status': 'error', 'error': errors}, status=400)

    appointment_date = data['appointment_date']
    time_slot = data['time_slot']
    total_guests = data['total_guests']

    booked = Appointment.objects.filter(
        appointment_date=appointment_date,
        time_slot=time_slot,
    ).exclude(status='Cancelled').aggregate(total=Sum('total_guests'))['total'] or 0

    if booked + total_guests > 10:
        remaining = max(0, 10 - booked)
        return JsonResponse({
            'status': 'error',
            'error': f'Khung giờ {time_slot} ngày {appointment_date} chỉ còn {remaining} chỗ trống. Quý khách vui lòng chọn khung giờ khác.',
        }, status=400)

    default_service = None
    if data['service_id']:
        default_service = Service.objects.filter(id=data['service_id'], status='Hoạt động').first()
    if not default_service:
        default_service = Service.objects.filter(status='Hoạt động').first()
    if not default_service:
        return JsonResponse({
            'status': 'error',
            'error': 'Hiện chưa có dịch vụ nào đang hoạt động trong hệ thống Spa.',
        }, status=400)

    calculated_total = Decimal(0)
    details_to_create = []
    guest_details = data['guest_details']

    if not guest_details:
        for idx in range(1, total_guests + 1):
            gender = 'Nam' if idx <= data['male_guests'] else 'Nữ'
            details_to_create.append({
                'guest_index': idx,
                'gender': gender,
                'service': default_service,
                'massage_pressure': 'Vừa',
            })
            calculated_total += default_service.price_vnd
    else:
        for idx, g in enumerate(guest_details, start=1):
            svc_id = g.get('service_id')
            svc = Service.objects.filter(id=svc_id, status='Hoạt động').first() if svc_id else default_service
            svc = svc or default_service
            details_to_create.append({
                'guest_index': g.get('guest_index', idx),
                'gender': g.get('gender', 'Nam'),
                'service': svc,
                'massage_pressure': g.get('massage_pressure', 'Vừa'),
            })
            calculated_total += svc.price_vnd

    auth_user = request.user
    applied_voucher = None
    discount_amount = Decimal(0)
    voucher_code = data['voucher_code']

    if voucher_code:
        voucher = Voucher.objects.filter(voucher_code=voucher_code, status='Khả dụng').first()
        if voucher and (not voucher.expiry_date or voucher.expiry_date >= timezone.now()):
            if voucher.customer and voucher.customer_id != auth_user.id:
                pass
            elif not voucher.min_order_amount or calculated_total >= voucher.min_order_amount:
                applied_voucher = voucher
                discount_amount = _compute_voucher_discount(voucher, calculated_total)

    discount_amount = min(discount_amount, calculated_total)
    final_total = max(Decimal(0), calculated_total - discount_amount)

    code = _generate_appointment_code()
    cust_name = data['customer_name'] or (auth_user.name or '').strip() or auth_user.get_full_name().strip() or auth_user.username
    cust_phone = data['customer_phone'] or (auth_user.phone or '').strip() or (auth_user.username if auth_user.username.isdigit() else '')
    cust_email = data['customer_email'] or (auth_user.email or '').strip()

    with transaction.atomic():
        appointment = Appointment.objects.create(
            appointment_code=code,
            user=auth_user,
            voucher=applied_voucher,
            appointment_date=appointment_date,
            time_slot=time_slot,
            total_guests=total_guests,
            male_guests=data['male_guests'],
            female_guests=data['female_guests'],
            customer_name=cust_name,
            customer_phone=cust_phone,
            customer_email=cust_email,
            preferred_contact_channel='Điện thoại',
            note=data['note'],
            total_price=final_total,
            status='Hold',
        )

        for item in details_to_create:
            AppointmentDetail.objects.create(
                appointment=appointment,
                service=item['service'],
                guest_index=item['guest_index'],
                gender=item['gender'],
                massage_pressure=item['massage_pressure'],
            )

        Invoice.objects.create(
            appointment=appointment,
            amount=final_total,
            discount_applied=discount_amount,
            status='Chờ xác nhận',
            paid_at=None,
            reason_refuse='Chuyển khoản VietQR',
        )

    _remember_booking_in_session(request, appointment.id)

    clean_code_num = appointment.appointment_code.replace('#', '')
    qr_memo = f"CHAMSPA {clean_code_num}"
    vietqr_url = (
        f"https://img.vietqr.io/image/MB-0946020526-compact2.png"
        f"?amount={int(final_total)}&addInfo={qr_memo}&accountName=CHAM%20SPA%20MASSAGE"
    )
    d = appointment.appointment_date
    date_display = f"{WEEKDAY_NAMES.get(d.weekday(), '')}, ngày {d.day:02d}/{d.month:02d}/{d.year}"

    return JsonResponse({
        'status': 'success',
        'success': True,
        'message': 'Đặt lịch thành công',
        'id': appointment.id,
        'appointment_id': appointment.id,
        'appointment_code': appointment.appointment_code,
        'total_price': float(appointment.total_price),
        'formatted_total_price': _format_vnd(final_total),
        'discount_applied': float(discount_amount),
        'discount_amount': float(discount_amount),
        'status_label': 'Hold',
        'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
        'date_display': date_display,
        'time_slot': appointment.time_slot,
        'customer_name': appointment.customer_name,
        'customer_phone': appointment.customer_phone,
        'total_guests': appointment.total_guests,
        'vietqr_url': vietqr_url,
        'bank_info': {
            'bank_name': 'MB BANK',
            'account_number': '0946 020 526',
            'account_name': 'CHAM SPA MASSAGE',
            'amount': int(final_total),
            'memo': qr_memo,
        },
    }, status=201)


@require_POST
def confirm_payment_api(request, pk=None):
    """Xác nhận đã quét QR thanh toán thành công (chủ lịch hẹn hoặc nhân sự)."""
    data, err = parse_json_body(request)
    if err:
        return err

    target_id = pk or data.get('appointment_id')
    code = (data.get('appointment_code') or '').strip()

    appointment = None
    if target_id:
        appointment = Appointment.objects.filter(id=target_id).first()
    if not appointment and code:
        clean_code = code if code.startswith('#') else f"#{code}"
        appointment = Appointment.objects.filter(appointment_code=clean_code).first()

    if not appointment:
        return JsonResponse({'status': 'error', 'error': 'Không tìm thấy thông tin lịch hẹn.'}, status=404)

    if not _can_access_appointment(request, appointment):
        return JsonResponse({'status': 'error', 'error': 'Bạn không có quyền xác nhận thanh toán cho lịch hẹn này.'}, status=403)

    appointment.status = 'Confirmed'
    appointment.save()

    invoice, _ = Invoice.objects.get_or_create(
        appointment=appointment,
        defaults={
            'amount': appointment.total_price,
            'discount_applied': 0,
            'status': 'Đã thanh toán',
            'paid_at': timezone.now(),
            'reason_refuse': 'Chuyển khoản VietQR',
        },
    )
    invoice.status = 'Đã thanh toán'
    invoice.paid_at = timezone.now()
    invoice.reason_refuse = 'Chuyển khoản VietQR'
    invoice.amount = appointment.total_price
    invoice.save()

    if appointment.voucher and appointment.voucher.customer:
        appointment.voucher.status = 'Đã dùng'
        appointment.voucher.used_at = timezone.now()
        appointment.voucher.save()

    if appointment.user:
        try:
            create_unique_notification(
                user=appointment.user,
                title="Lịch hẹn đã được xác nhận!",
                content=(
                    f"Lịch hẹn {appointment.appointment_code} lúc {appointment.time_slot} "
                    f"ngày {appointment.appointment_date} đã được thanh toán và xác nhận thành công."
                ),
                prefix="TB-CONFIRM",
                delivery_channels="Web",
                status="Đã gửi",
            )
        except Exception:
            pass

    clean_code_redirect = appointment.appointment_code.replace('#', '')
    return JsonResponse({
        'status': 'success',
        'success': True,
        'message': 'Thanh toán thành công! Lịch hẹn của bạn đã được xác nhận.',
        'appointment_code': appointment.appointment_code,
        'appointment_status': 'Confirmed',
        'redirect_url': f"/appointment/success/{clean_code_redirect}/",
    }, status=200)


@require_POST
def update_payment_api(request, pk):
    """Cập nhật phương thức thanh toán hoặc trạng thái thu tiền (nhân sự)."""
    appointment = Appointment.objects.filter(pk=pk).first()
    if not appointment:
        return JsonResponse({'status': 'error', 'error': 'Không tìm thấy lịch hẹn.'}, status=404)

    if not _can_access_appointment(request, appointment):
        return JsonResponse({'status': 'error', 'error': 'Bạn không có quyền cập nhật thông tin thanh toán này.'}, status=403)

    data, err = parse_json_body(request)
    if err:
        return err

    method = data.get('payment_method')
    is_paid = _parse_bool(data.get('is_paid'))

    if is_paid is not None and not is_staff_or_admin(request.user):
        return JsonResponse({
            'status': 'error',
            'error': 'Chỉ nhân viên hoặc quản trị viên mới có quyền cập nhật trạng thái thu tiền.',
        }, status=403)

    invoice, _ = Invoice.objects.get_or_create(
        appointment=appointment,
        defaults={
            'amount': appointment.total_price,
            'discount_applied': 0,
            'status': 'Chờ xác nhận',
        },
    )

    if method == 'counter':
        invoice.reason_refuse = 'Tại quầy (Tiền mặt/POS)'
    elif method == 'transfer':
        invoice.reason_refuse = 'Chuyển khoản VietQR'

    if is_paid is True:
        invoice.status = 'Đã thanh toán'
        if not invoice.paid_at:
            invoice.paid_at = timezone.now()
    elif is_paid is False:
        invoice.status = 'Chờ xác nhận'
        invoice.paid_at = None

    invoice.amount = appointment.total_price
    invoice.save()

    return JsonResponse({
        'status': 'success',
        'message': 'Đã cập nhật thông tin thanh toán thành công!',
        'appointment': serialize_appointment_full(appointment),
    }, status=200)


@require_GET
def appointment_detail_api(request, identifier):
    """Lấy thông tin chi tiết một lịch hẹn (chỉ chủ lịch hẹn hoặc nhân sự)."""
    appointment = None
    if str(identifier).isdigit():
        appointment = Appointment.objects.filter(id=int(identifier)).select_related('voucher', 'user').prefetch_related('details__service').first()
    if not appointment:
        code = identifier if str(identifier).startswith('#') else f"#{identifier}"
        appointment = Appointment.objects.filter(appointment_code=code).select_related('voucher', 'user').prefetch_related('details__service').first()

    if not appointment:
        return JsonResponse({'status': 'error', 'error': 'Không tìm thấy lịch hẹn.'}, status=404)

    if not _can_access_appointment(request, appointment):
        return JsonResponse({'status': 'error', 'error': 'Bạn không có quyền xem thông tin lịch hẹn này.'}, status=403)

    return JsonResponse(serialize_appointment_full(appointment), status=200)


@require_auth_json
@require_POST
def reschedule_api(request, pk):
    """Dời lịch hẹn sang ngày giờ mới của chính khách hàng."""
    appointment = Appointment.objects.filter(id=pk, user=request.user).first()
    if not appointment:
        return JsonResponse({'status': 'error', 'error': 'Không tìm thấy lịch hẹn hoặc bạn không có quyền thao tác.'}, status=404)

    if appointment.status not in ('Hold', 'Pending', 'Confirmed'):
        return JsonResponse({'status': 'error', 'error': f'Lịch hẹn ở trạng thái {appointment.status} không được phép dời lịch.'}, status=400)

    data, err = parse_json_body(request)
    if err:
        return err

    new_date_str = data.get('new_date') or data.get('appointment_date')
    new_slot = data.get('new_time_slot') or data.get('time_slot')

    if not new_date_str or not new_slot:
        return JsonResponse({'status': 'error', 'error': 'Vui lòng chọn ngày và khung giờ mới.'}, status=400)

    try:
        new_date = datetime.strptime(str(new_date_str).strip(), '%Y-%m-%d').date()
    except Exception:
        return JsonResponse({'status': 'error', 'error': 'Ngày mới không đúng định dạng (YYYY-MM-DD).'}, status=400)

    if new_date < timezone.localdate():
        return JsonResponse({'status': 'error', 'error': 'Không thể dời lịch hẹn về ngày trong quá khứ.'}, status=400)
    if is_slot_in_past(new_date, new_slot):
        return JsonResponse({
            'status': 'error',
            'error': f'Khung giờ {new_slot} hôm nay đã qua so với thời gian thực. Vui lòng chọn khung giờ sau.',
        }, status=400)

    booked_new = Appointment.objects.filter(
        appointment_date=new_date,
        time_slot=new_slot,
    ).exclude(id=appointment.id).exclude(status='Cancelled').aggregate(t=Sum('total_guests'))['t'] or 0

    if booked_new + appointment.total_guests > 10:
        remaining = max(0, 10 - booked_new)
        return JsonResponse({
            'status': 'error',
            'error': f'Khung giờ {new_slot} ngày {new_date_str} chỉ còn {remaining} chỗ, không đủ cho {appointment.total_guests} khách.',
        }, status=400)

    old_date = appointment.appointment_date
    old_slot = appointment.time_slot

    appointment.appointment_date = new_date
    appointment.time_slot = new_slot
    appointment.save()

    if appointment.user:
        try:
            create_unique_notification(
                user=appointment.user,
                title="Dời lịch hẹn thành công!",
                content=f"Lịch hẹn {appointment.appointment_code} đã được dời từ ({old_slot} ngày {old_date}) sang ({new_slot} ngày {new_date}).",
                prefix="TB-RESCHED",
                delivery_channels="Web",
                status="Đã gửi",
            )
        except Exception:
            pass

    w_name = WEEKDAY_NAMES.get(new_date.weekday(), '')
    date_display = f"{new_slot}, {w_name} - {new_date.strftime('%d/%m/%Y')}"

    return JsonResponse({
        'status': 'success',
        'success': True,
        'message': f'Dời lịch hẹn {appointment.appointment_code} sang {date_display} thành công!',
        'appointment_code': appointment.appointment_code,
        'new_date': str(new_date),
        'new_time_slot': new_slot,
        'date_display': date_display,
    }, status=200)


@require_auth_json
@require_POST
def cancel_api(request, pk):
    """Hủy lịch hẹn kèm STK hoàn tiền của chính khách hàng."""
    appointment = Appointment.objects.filter(id=pk, user=request.user).first()
    if not appointment:
        return JsonResponse({'status': 'error', 'error': 'Không tìm thấy lịch hẹn hoặc bạn không có quyền thao tác.'}, status=404)

    if appointment.status in ('Completed', 'Cancelled'):
        return JsonResponse({'status': 'error', 'error': f'Lịch hẹn đã {appointment.status}, không thể thực hiện thao tác hủy.'}, status=400)

    data, err = parse_json_body(request)
    if err:
        return err

    cancel_reason = (data.get('cancel_reason') or '').strip()
    refund_account_number = (data.get('refund_account_number') or '').strip()
    bank_name = (data.get('bank_name') or '').strip()
    account_holder = (data.get('account_holder') or '').strip()

    if not cancel_reason:
        return JsonResponse({'status': 'error', 'error': 'Vui lòng chọn hoặc nhập lý do hủy lịch.'}, status=400)
    if not refund_account_number:
        return JsonResponse({'status': 'error', 'error': 'Vui lòng cung cấp số tài khoản ngân hàng để nhận hoàn tiền cọc.'}, status=400)

    refund_info_parts = []
    if bank_name:
        refund_info_parts.append(bank_name)
    refund_info_parts.append(refund_account_number)
    if account_holder:
        refund_info_parts.append(f"({account_holder})")

    full_refund_account = " - ".join(refund_info_parts)

    appointment.status = 'Cancelled'
    appointment.cancel_reason = cancel_reason
    appointment.refund_account_number = full_refund_account
    appointment.save()

    invoice = Invoice.objects.filter(appointment=appointment).first()
    if invoice:
        invoice.status = 'Không hợp lệ'
        invoice.save()

    if appointment.voucher and appointment.voucher.status == 'Đã dùng':
        appointment.voucher.status = 'Khả dụng'
        appointment.voucher.used_at = None
        appointment.voucher.save()

    if appointment.user:
        try:
            create_unique_notification(
                user=appointment.user,
                title="Xác nhận yêu cầu hủy lịch hẹn",
                content=(
                    f"Yêu cầu hủy lịch hẹn {appointment.appointment_code} đã được tiếp nhận. "
                    f"Bộ phận Kế toán sẽ hoàn tất đối soát hoàn cọc về tài khoản {full_refund_account} trong 24h làm việc."
                ),
                prefix="TB-CANCEL",
                delivery_channels="Web",
                status="Đã gửi",
            )
        except Exception:
            pass

    return JsonResponse({
        'status': 'success',
        'success': True,
        'message': f'Lịch hẹn {appointment.appointment_code} đã được hủy thành công. Kế toán sẽ đối soát và hoàn tiền cọc trong vòng 24 giờ.',
        'appointment_code': appointment.appointment_code,
        'cancel_reason': cancel_reason,
        'refund_account': full_refund_account,
    }, status=200)


def _update_appointment_status(request, pk=None):
    data, err = parse_json_body(request)
    if err:
        return err

    target_id = pk or data.get('id') or data.get('appointment_id')
    appointment = Appointment.objects.filter(id=target_id).first()
    if not appointment:
        return JsonResponse({'status': 'error', 'error': 'Không tìm thấy lịch hẹn.'}, status=404)

    new_status = data.get('status')
    valid_statuses = ('Hold', 'Pending', 'Confirmed', 'In_Progress', 'Completed', 'Cancelled')
    if new_status not in valid_statuses:
        return JsonResponse({'status': 'error', 'error': f"Trạng thái '{new_status}' không hợp lệ."}, status=400)

    old_status = appointment.status
    appointment.status = new_status
    appointment.save()

    invoice, _ = Invoice.objects.get_or_create(
        appointment=appointment,
        defaults={
            'amount': appointment.total_price,
            'discount_applied': 0,
            'status': 'Chờ xác nhận',
        },
    )

    earned_points = int(appointment.total_price) // 10000

    if new_status in ('Confirmed', 'Completed'):
        invoice.status = 'Đã thanh toán'
        if not invoice.paid_at:
            invoice.paid_at = timezone.now()
        if new_status == 'Confirmed':
            invoice.reason_refuse = 'Chuyển khoản VietQR'
        invoice.amount = appointment.total_price
        invoice.save()

        if appointment.voucher and appointment.voucher.customer:
            appointment.voucher.status = 'Đã dùng'
            if not appointment.voucher.used_at:
                appointment.voucher.used_at = timezone.now()
            appointment.voucher.save()

    elif new_status == 'Cancelled':
        invoice.status = 'Không hợp lệ'
        invoice.save()

        if appointment.voucher and appointment.voucher.status == 'Đã dùng':
            appointment.voucher.status = 'Khả dụng'
            appointment.voucher.used_at = None
            appointment.voucher.save()

    if appointment.user and old_status != new_status:
        status_labels = {
            'Confirmed': 'đã được xác nhận',
            'In_Progress': 'đang được phục vụ',
            'Completed': 'đã hoàn thành' + (f' (+{earned_points} điểm thưởng)' if earned_points > 0 else ''),
            'Cancelled': 'đã bị hủy',
        }
        label_txt = status_labels.get(new_status, new_status)
        try:
            create_unique_notification(
                user=appointment.user,
                title=f"Lịch hẹn {appointment.appointment_code} {label_txt}",
                content=f"Lịch hẹn {appointment.appointment_code} ({appointment.time_slot} ngày {appointment.appointment_date}) {label_txt}.",
                prefix="TB-STATUS",
                delivery_channels="Web",
                status="Đã gửi",
            )
        except Exception:
            pass

    if new_status == 'Confirmed':
        resp_msg = f"Đã xác nhận lịch hẹn {appointment.appointment_code} và cập nhật hình thức thanh toán thành 'Đã chuyển khoản'."
    else:
        resp_msg = f"Đã cập nhật trạng thái lịch hẹn {appointment.appointment_code} thành '{new_status}'."
        if new_status == 'Completed' and earned_points > 0 and appointment.user:
            resp_msg += f" Đã tự động tích lũy +{earned_points} điểm thưởng cho thành viên!"

    appointment.refresh_from_db()
    payment_data = serialize_appointment_full(appointment).get('payment')

    return JsonResponse({
        'status': 'success',
        'success': True,
        'appointment_id': appointment.id,
        'appointment_code': appointment.appointment_code,
        'old_status': old_status,
        'updated_status': new_status,
        'earned_points': earned_points,
        'payment': payment_data,
        'message': resp_msg,
    }, status=200)


@require_staff_json
@require_http_methods(['GET', 'POST', 'PUT'])
def admin_appointments_api(request, pk=None):
    """Quản lý danh sách và cập nhật trạng thái lịch hẹn cho Nhân viên & Quản trị viên."""
    if request.method in ('POST', 'PUT'):
        return _update_appointment_status(request, pk)

    if pk:
        appointment = Appointment.objects.filter(id=pk).select_related('voucher', 'user').prefetch_related('details__service').first()
        if not appointment:
            return JsonResponse({'status': 'error', 'error': 'Không tìm thấy lịch hẹn.'}, status=404)
        return JsonResponse(serialize_appointment_full(appointment), status=200)

    qs = Appointment.objects.all().select_related('voucher', 'user').prefetch_related('details__service')

    date_filter = request.GET.get('date')
    date_from = request.GET.get('date_from') or request.GET.get('start_date')
    date_to = request.GET.get('date_to') or request.GET.get('end_date')

    if date_filter and date_filter != 'all':
        try:
            d = datetime.strptime(date_filter, '%Y-%m-%d').date()
            qs = qs.filter(appointment_date=d)
        except ValueError:
            pass
    else:
        if date_from:
            try:
                df = datetime.strptime(date_from, '%Y-%m-%d').date()
                qs = qs.filter(appointment_date__gte=df)
            except ValueError:
                pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                qs = qs.filter(appointment_date__lte=dt_to)
            except ValueError:
                pass

    time_slot = request.GET.get('time_slot')
    if time_slot and time_slot not in ('all', 'Tất cả khung giờ'):
        qs = qs.filter(time_slot=time_slot)

    status_filter = request.GET.get('status')
    if status_filter and status_filter not in ('all', 'Tất cả trạng thái'):
        if status_filter in ('Hold', 'Pending', 'Confirmed', 'In_Progress', 'Completed', 'Cancelled'):
            qs = qs.filter(status=status_filter)
        elif status_filter in ('waiting', 'upcoming', 'pending_all', 'Đang chờ'):
            qs = qs.filter(status__in=['Hold', 'Pending', 'Confirmed'])

    search_query = request.GET.get('search') or request.GET.get('q')
    if search_query:
        search_query = search_query.strip()
        qs = qs.filter(
            Q(appointment_code__icontains=search_query) |
            Q(customer_name__icontains=search_query) |
            Q(customer_phone__icontains=search_query)
        )

    today_date = timezone.localdate()
    today_qs = Appointment.objects.filter(appointment_date=today_date)
    counts = {
        'total_today': today_qs.count(),
        'in_progress': today_qs.filter(status='In_Progress').count(),
        'confirmed': today_qs.filter(status='Confirmed').count(),
        'pending': today_qs.filter(status__in=['Hold', 'Pending']).count(),
        'completed': today_qs.filter(status='Completed').count(),
        'cancelled': today_qs.filter(status='Cancelled').count(),
    }

    qs = qs.order_by('time_slot', '-created_at')
    items = [serialize_appointment_full(a) for a in qs]
    return JsonResponse({
        'status': 'success',
        'counts': counts,
        'total_count': len(items),
        'appointments': items,
    }, status=200)


@require_staff_json
@require_POST
def staff_quick_create_api(request):
    """Tạo nhanh lịch hẹn tại quầy dành cho Nhân viên Lễ tân / CSKH."""
    raw_data, err = parse_json_body(request)
    if err:
        return err

    data, errors = _validate_quick_create_payload(raw_data)
    if errors:
        return JsonResponse({'status': 'error', 'error': errors}, status=400)

    service = Service.objects.filter(id=data['service_id'], status='Hoạt động').first()
    if not service:
        return JsonResponse({'status': 'error', 'error': 'Dịch vụ được chọn không khả dụng.'}, status=400)

    total_guests = data['total_guests']
    total_price = service.price_vnd * total_guests
    code = _generate_appointment_code()

    clean_phone = data['customer_phone'].replace(' ', '').replace('.', '').replace('-', '').strip()
    matched_user = User.objects.filter(
        Q(phone=clean_phone) | Q(username=clean_phone)
    ).filter(is_staff=False, is_superuser=False).first()

    with transaction.atomic():
        appointment = Appointment.objects.create(
            appointment_code=code,
            user=matched_user,
            customer_name=data['customer_name'],
            customer_phone=data['customer_phone'],
            customer_email=data['customer_email'],
            appointment_date=data['appointment_date'],
            time_slot=data['time_slot'],
            total_guests=total_guests,
            male_guests=data['male_guests'],
            female_guests=data['female_guests'],
            preferred_contact_channel='Quầy lễ tân',
            note=data['note'],
            total_price=total_price,
            status=data['status'],
        )

        is_paid = (data['status'] == 'Completed')
        Invoice.objects.get_or_create(
            appointment=appointment,
            defaults={
                'amount': total_price,
                'discount_applied': 0,
                'status': 'Đã thanh toán' if is_paid else 'Chờ xác nhận',
                'paid_at': timezone.now() if is_paid else None,
                'reason_refuse': 'Tại quầy (Tiền mặt/POS)',
            },
        )

        for idx in range(1, total_guests + 1):
            gender = 'Nam' if idx <= data['male_guests'] else 'Nữ'
            AppointmentDetail.objects.create(
                appointment=appointment,
                guest_index=idx,
                gender=gender,
                service=service,
                massage_pressure='Vừa',
            )

    return JsonResponse({
        'status': 'success',
        'success': True,
        'message': f'Tiếp nhận lịch hẹn {appointment.appointment_code} tại quầy thành công!',
        'appointment': serialize_appointment_full(appointment),
    }, status=201)
