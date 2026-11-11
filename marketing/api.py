from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.ajax import parse_json_body
from core.models import Notification, Voucher
from .utils import (
    classify_notification,
    ensure_sample_notifications_for_roles,
    filter_notifications_for_user,
)


def _fmt_vnd(amount):
    return f'{int(amount):,}'.replace(',', '.') + ' VNĐ'


def _serialize_notification(n):
    now = timezone.now()
    seconds = (now - n.created_at).total_seconds() if n.created_at else 0
    if seconds < 60:
        time_ago = 'Vừa xong'
    elif seconds < 3600:
        time_ago = f'{int(seconds // 60)} phút trước'
    elif seconds < 86400:
        time_ago = f'{int(seconds // 3600)} giờ trước'
    elif seconds < 172800:
        time_ago = 'Hôm qua'
    elif seconds < 86400 * 30:
        time_ago = f'{int(seconds // 86400)} ngày trước'
    else:
        time_ago = n.created_at.strftime('%d/%m/%Y %H:%M')

    cat_info = classify_notification(n)

    return {
        'id': n.id,
        'notification_code': n.notification_code,
        'user': n.user_id,
        'user_name': n.user.name if n.user else '',
        'user_phone': n.user.phone if n.user else '',
        'title': n.title,
        'content': n.content,
        'promotion': n.promotion_id,
        'promotion_title': n.promotion.title if n.promotion else None,
        'delivery_channels': n.delivery_channels,
        'status': n.status,
        'created_at': n.created_at.isoformat() if n.created_at else None,
        'time_ago': time_ago,
        'category': cat_info['category'],
        'category_label': cat_info['label'],
        'category_icon': cat_info['icon'],
        'category_color': cat_info['color'],
    }


@require_GET
def notification_dropdown_api(request):
    """[UC-7.1] Dropdown thông báo tại quả chuông Topbar."""
    user = request.user
    if not user.is_authenticated:
        notifs = Notification.objects.filter(promotion__isnull=False, status='Đã gửi').order_by('-created_at')[:6]
        return JsonResponse({
            'status': 'success',
            'role': 'ANONYMOUS',
            'unread_count': notifs.count(),
            'notifications': [_serialize_notification(n) for n in notifs],
        })

    ensure_sample_notifications_for_roles()
    qs = filter_notifications_for_user(
        Notification.objects.filter(user=user, status='Đã gửi'),
        user,
    )
    qs = qs.order_by('-created_at')
    total_count = qs.count()
    user_role = 'ADMIN' if user.is_superuser else ('STAFF' if user.is_staff else 'CUSTOMER')

    return JsonResponse({
        'status': 'success',
        'role': user_role,
        'user_name': user.name or user.username,
        'total_count': total_count,
        'unread_count': min(total_count, 5),
        'notifications': [_serialize_notification(n) for n in qs[:8]],
    })


@require_POST
def voucher_validate_api(request):
    """Kiểm tra tính hợp lệ và tính mức giảm giá của Voucher."""
    data, err_resp = parse_json_body(request)
    if err_resp:
        return err_resp

    code = str(data.get('voucher_code') or data.get('code') or '').strip().upper()
    if not code:
        return JsonResponse({'status': 'error', 'errors': {'voucher_code': 'Vui lòng nhập mã Voucher.'}}, status=400)

    raw_amt = data.get('order_amount', data.get('order_total', 0))
    try:
        order_amount = Decimal(str(raw_amt or 0))
    except (InvalidOperation, ValueError):
        return JsonResponse({'status': 'error', 'errors': {'order_amount': 'Giá trị đơn hàng không hợp lệ.'}}, status=400)

    voucher = Voucher.objects.filter(voucher_code=code).first()
    if not voucher:
        return JsonResponse({'valid': False, 'message': 'Mã Voucher không tồn tại trên hệ thống Cham Spa.'}, status=400)

    if voucher.status != 'Khả dụng':
        return JsonResponse({'valid': False, 'message': f"Mã Voucher hiện ở trạng thái '{voucher.status}', không thể sử dụng."}, status=400)

    if voucher.expiry_date and voucher.expiry_date < timezone.now():
        return JsonResponse({'valid': False, 'message': 'Mã Voucher đã hết hạn sử dụng.'}, status=400)

    if voucher.customer and (not request.user.is_authenticated or voucher.customer_id != request.user.id):
        return JsonResponse({'valid': False, 'message': 'Mã Voucher này được cấp riêng cho một khách hàng khác.'}, status=403)

    if voucher.min_order_amount and order_amount < voucher.min_order_amount:
        min_fmt = f'{int(voucher.min_order_amount):,}'.replace(',', '.')
        return JsonResponse({'valid': False, 'message': f'Đơn hàng chưa đạt giá trị tối thiểu {min_fmt} VNĐ để áp dụng mã này.'}, status=400)

    if voucher.discount_type in ('PERCENT', 'Phần trăm'):
        discount_amount = (order_amount * Decimal(voucher.discount_value)) / Decimal(100)
        if voucher.max_discount_amount and discount_amount > voucher.max_discount_amount:
            discount_amount = Decimal(voucher.max_discount_amount)
    else:
        discount_amount = Decimal(voucher.discount_value)

    discount_amount = min(discount_amount, order_amount)
    final_amount = max(Decimal(0), order_amount - discount_amount)

    return JsonResponse({
        'valid': True,
        'voucher_code': voucher.voucher_code,
        'discount_type': voucher.discount_type,
        'discount_value': float(voucher.discount_value),
        'discount_amount': float(discount_amount),
        'formatted_discount': f'-{int(discount_amount):,}'.replace(',', '.') + ' VNĐ',
        'final_amount': float(final_amount),
        'formatted_final_amount': _fmt_vnd(final_amount),
        'message': 'Áp dụng mã Voucher thành công!',
    })
