"""
================================================================================
MODULE 07: QUẢN LÝ THÔNG BÁO & KHUYẾN MÃI (MOD-07) - TEMPLATE VIEWS
Thành viên phụ trách: MINH KHA
Mục đích:
  - Điều phối và render các giao diện HTML cho Module 7:
    1. Trang Ưu đãi 2 tab: Khuyến mãi Card Gradient & Ví Voucher (UC-7.2).
    2. Trang danh sách thông báo dạng Timeline bảng tin (UC-7.1).
    3. Màn hình Quản trị Thông báo & Khuyến mãi cho Admin (UC-7.3, UC-7.4).
    4. Màn hình Thông báo điều phối & ca trực cho Nhân viên (Staff).
  - Tích hợp chuẩn bộ nhận diện thương hiệu Cham Spa (Figma Moodboard 857:31).
  - Kế thừa chuẩn layouts/admin_layout.html, layouts/staff_layout.html, layouts/customer_layout.html.
================================================================================
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from django.contrib import messages

from core.models import Notification, Promotion, Voucher, User
from .utils import (
    classify_notification,
    classify_staff_notification,
    create_system_notification,
    ensure_sample_notifications_for_roles,
    filter_notifications_for_user,
)


def get_base_layout_for_user(user):
    """
    Hàm xác định layout chuẩn kế thừa dựa trên phân quyền người dùng:
      - Quản trị viên (Superuser) -> layouts/admin_layout.html
      - Kỹ thuật viên / CSKH (Staff) -> layouts/staff_layout.html
      - Khách hàng đã đăng nhập (Customer) -> layouts/customer_layout.html
      - Khách vãng lai (Chưa đăng nhập) -> layouts/public_layout.html
    """
    if user and user.is_authenticated:
        if user.is_superuser:
            return 'layouts/admin_layout.html'
        elif user.is_staff:
            return 'layouts/staff_layout.html'
        else:
            return 'layouts/customer_layout.html'
    return 'layouts/public_layout.html'


@ensure_csrf_cookie
def promotions_view(request):
    """
    [UC-7.2] TRANG ƯU ĐÃI & KHO VOUCHER (DÀNH CHO KHÁCH HÀNG & CỘNG ĐỒNG)
    Giao diện 2 Tab chuẩn Figma:
      - Tab 1: Chương trình Khuyến mãi (Thẻ Card CSS gradient hoàng gia Cham Spa).
      - Tab 2: Ví Voucher (Kho voucher với nút sao chép mã tiện lợi, hiển thị mức giảm, đơn tối thiểu, hạn dùng).
    """
    user = request.user
    base_layout = get_base_layout_for_user(user)

    # 1. Danh sách Chương trình khuyến mãi (Lọc đang hoạt động hoặc sắp diễn ra)
    promotions = list(
        Promotion.objects.filter(
            Q(status='Đang hoạt động') | Q(status='Sắp diễn ra')
        ).order_by('-created_at')
    )

    # 2. Danh sách Voucher
    now = timezone.now()
    if user.is_authenticated:
        # Lấy voucher khả dụng: gồm voucher toàn hệ thống (customer=None) hoặc gán cho chính user
        available_vouchers = list(
            Voucher.objects.filter(
                Q(customer__isnull=True) | Q(customer=user),
                status='Khả dụng',
                expiry_date__gte=now,
            ).select_related('promotion').order_by('expiry_date')
        )

        # Voucher đã sử dụng hoặc hết hạn của user
        history_vouchers = Voucher.objects.filter(
            Q(customer=user),
            Q(status__in=['Đã dùng', 'Hết hạn']) | Q(expiry_date__lt=now),
        ).select_related('promotion').order_by('-created_at')[:10]
    else:
        available_vouchers = list(
            Voucher.objects.filter(
                customer__isnull=True,
                status='Khả dụng',
                expiry_date__gte=now,
            ).select_related('promotion').order_by('expiry_date')
        )
        history_vouchers = []

    public_vouchers_by_promo = {}
    for v in available_vouchers:
        if v.promotion_id and v.customer_id is None:
            public_vouchers_by_promo.setdefault(v.promotion_id, []).append(v)
    for promo in promotions:
        promo.public_vouchers = public_vouchers_by_promo.get(promo.id, [])

    context = {
        'base_layout': base_layout,
        'promotions': promotions,
        'available_vouchers': available_vouchers,
        'history_vouchers': history_vouchers,
        'total_promotions': len(promotions),
        'total_vouchers': len(available_vouchers),
        'active_tab': request.GET.get('tab', 'promotions'),
    }
    return render(request, 'marketing/promotions.html', context)


@login_required
def notifications_view(request):
    """
    [UC-7.1] TRANG DANH SÁCH THÔNG BÁO DẠNG TIMELINE BẢNG TIN
    Hiển thị thông báo dạng dòng thời gian phân bổ theo các danh mục:
      - Nhắc lịch hẹn
      - Nhận mã voucher ưu đãi
      - Kết quả xử lý khiếu nại
      - Tích điểm & thăng hạng thẻ hội viên VIP
      - Thông báo hệ thống
    Tự động áp dụng layout tương ứng với quyền của tài khoản đang đăng nhập.
    """
    user = request.user
    base_layout = get_base_layout_for_user(user)

    # Tự động tạo dữ liệu mẫu nếu chưa có
    ensure_sample_notifications_for_roles()

    category = request.GET.get('category', 'all')
    if category not in ('all', 'appointment', 'voucher', 'complaint', 'membership', 'system'):
        category = 'all'
    search_kw = request.GET.get('q', '').strip()

    # Lọc đúng vai trò người dùng và phân loại duy nhất (mỗi thông báo chỉ thuộc 1 nhóm)
    base_qs = filter_notifications_for_user(
        Notification.objects.filter(user=user).select_related('promotion'),
        user,
    ).order_by('-created_at')

    stats = {
        'all': 0,
        'appointment': 0,
        'voucher': 0,
        'complaint': 0,
        'membership': 0,
        'system': 0,
    }
    url_cache = {}
    filtered_notifs = []
    search_l = search_kw.lower()

    for notif in base_qs:
        meta = classify_notification(notif)
        stat_cat = 'system' if meta['category'] == 'payment' else meta['category']
        notif.notif_category = stat_cat
        notif.notif_badge_label = meta['badge_label']
        notif.notif_badge_class = meta['badge_class']
        notif.notif_badge_style = meta['badge_style']

        url_name = meta['action_url_name']
        if url_name:
            cache_key = (url_name, meta['action_query'])
            if cache_key not in url_cache:
                url_cache[cache_key] = reverse(url_name) + meta['action_query']
            notif.notif_action_url = url_cache[cache_key]
            notif.notif_action_label = meta['action_label']
        else:
            notif.notif_action_url = ''
            notif.notif_action_label = ''

        stats['all'] += 1
        stats[stat_cat] += 1

        if search_l and search_l not in (notif.title or '').lower() and search_l not in (notif.content or '').lower():
            continue
        if category != 'all' and stat_cat != category:
            continue
        filtered_notifs.append(notif)

    paginator = Paginator(filtered_notifs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'base_layout': base_layout,
        'notifications': page_obj,
        'page_obj': page_obj,
        'current_category': category,
        'search_query': search_kw,
        'stats': stats,
    }
    return render(request, 'marketing/notifications.html', context)


def _parse_dt(val, end_of_day=True):
    """Chuyển đổi chuỗi ngày hoặc ngày giờ thành datetime có timezone."""
    if not val:
        return None
    if isinstance(val, datetime):
        dt = val
    else:
        s = str(val).strip()
        dt = parse_datetime(s)
        if not dt:
            d = parse_date(s)
            if d:
                if end_of_day:
                    dt = datetime(d.year, d.month, d.day, 23, 59, 59)
                else:
                    dt = datetime(d.year, d.month, d.day, 0, 0, 0)
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _fmt_decimal_input(val):
    """Định dạng Decimal gọn cho input number HTML."""
    if val is None:
        return ''
    if val == val.to_integral_value():
        return str(int(val))
    return format(val.normalize(), 'f')


def _fmt_vnd(val):
    """Định dạng số tiền VNĐ có dấu chấm phân cách hàng nghìn."""
    if val is None:
        return ''
    return f"{int(val):,}".replace(',', '.') + ' VNĐ'


def _voucher_discount_label(voucher):
    """Mô tả ngắn gọn mức giảm giá của Voucher."""
    if voucher.discount_type in ('PERCENT', 'Phần trăm'):
        base = f"Giảm { _fmt_decimal_input(voucher.discount_value) }%"
        if voucher.max_discount_amount:
            return f"{base} (tối đa {_fmt_vnd(voucher.max_discount_amount)})"
        return base
    return f"Giảm {_fmt_vnd(voucher.discount_value)}"


def _local_dt_str(dt, fmt="%d/%m/%Y %H:%M"):
    """Hiển thị DateTime theo múi giờ hiện tại."""
    if not dt:
        return ''
    return timezone.localtime(dt).strftime(fmt)


def _summarize_notification_group(group_notifs):
    """Tổng hợp thông tin đối tượng nhận và phạm vi của một đợt thông báo."""
    count = len(group_notifs)
    users = [n.user for n in group_notifs if n.user]
    if count <= 1 and users:
        u = users[0]
        role_tag = 'Quản trị' if u.is_superuser else ('Nhân viên' if u.is_staff else 'Khách hàng')
        name = u.name or u.username
        summary = f"{name} ({role_tag})"
        preview = summary
        scope = 'single'
    else:
        has_customer = any(not u.is_staff and not u.is_superuser for u in users)
        has_staff = any(u.is_staff and not u.is_superuser for u in users)
        has_admin = any(u.is_superuser for u in users)
        if has_customer and not has_staff and not has_admin:
            summary = f"Khách hàng ({count} người)"
        elif has_staff and not has_customer and not has_admin:
            summary = f"Nhân viên ({count} người)"
        else:
            summary = f"Nhiều đối tượng ({count} người)"
        names = [u.name or u.username for u in users[:8]]
        preview = ', '.join(names) + (f" ... (+{len(users) - 8} người)" if len(users) > 8 else '')
        scope = 'broadcast'
    return {
        'recipient_count': count,
        'target_summary': summary,
        'recipient_preview': preview,
        'scope': scope,
    }


def _serialize_admin_notification(notif, group_meta):
    """Chuyển bản ghi Notification thành dict an toàn cho modal Xem/Sửa."""
    return {
        'id': notif.id,
        'notification_code': notif.notification_code or '',
        'title': notif.title,
        'content': notif.content,
        'delivery_channels': notif.delivery_channels or 'In-App',
        'status': notif.status or 'Đã gửi',
        'promotion_id': str(notif.promotion_id) if notif.promotion_id else '',
        'promotion_title': notif.promotion.title if notif.promotion else 'Không đính kèm',
        'created_at_display': _local_dt_str(notif.created_at),
        'recipient_count': group_meta['recipient_count'],
        'target_summary': group_meta['target_summary'],
        'recipient_preview': group_meta['recipient_preview'],
        'scope': group_meta['scope'],
    }


def _handle_admin_notifications_post(request):
    """Xử lý form POST tạo/phát hành, cập nhật hoặc xóa thông báo từ trang Quản trị."""
    action = (request.POST.get('action') or '').strip()

    if action == 'create_notification':
        title = str(request.POST.get('title') or '').strip()
        content = str(request.POST.get('content') or '').strip()
        target_type = (request.POST.get('target_type') or 'all_customers').strip()
        channels = str(request.POST.get('delivery_channels') or 'In-App').strip() or 'In-App'
        promo_id = (request.POST.get('promotion_id') or '').strip()
        notif_status = (request.POST.get('status') or 'Đã gửi').strip()
        if notif_status not in ('Đã gửi', 'Chờ gửi'):
            notif_status = 'Đã gửi'

        if not title or not content:
            messages.error(request, "Vui lòng nhập đầy đủ tiêu đề và nội dung thông báo.")
            return redirect('marketing:admin_notifications')
        if target_type not in ('all_customers', 'all_staff', 'all_users', 'single_user'):
            messages.error(request, "Đối tượng nhận thông báo không hợp lệ.")
            return redirect('marketing:admin_notifications')

        promotion = None
        if promo_id:
            promotion = Promotion.objects.filter(id=int(promo_id)).first() if promo_id.isdigit() else None
            if not promotion:
                messages.error(request, "Chương trình khuyến mãi đính kèm không tồn tại.")
                return redirect('marketing:admin_notifications')

        if target_type == 'single_user':
            uid = (request.POST.get('user_id') or '').strip()
            target_user = User.objects.filter(id=int(uid)).first() if uid.isdigit() else None
            if not target_user:
                messages.error(request, "Không tìm thấy người dùng nhận thông báo.")
                return redirect('marketing:admin_notifications')
            create_system_notification(
                user=target_user, title=title, content=content,
                promotion=promotion, delivery_channels=channels, status=notif_status,
            )
            messages.success(request, f"Đã gửi thông báo đến {target_user.name or target_user.username}.")
            return redirect('marketing:admin_notifications')

        if target_type == 'all_customers':
            qs = User.objects.filter(is_staff=False, is_superuser=False)
            msg_empty = "Hệ thống hiện chưa có tài khoản khách hàng nào."
            msg_ok = f"Đã phát hành thông báo chung đến {qs.count()} khách hàng."
        elif target_type == 'all_staff':
            qs = User.objects.filter(is_staff=True, is_superuser=False)
            msg_empty = "Hệ thống hiện chưa có tài khoản nhân viên nào."
            msg_ok = f"Đã phát thông báo nội bộ đến {qs.count()} nhân viên."
        else:
            qs = User.objects.all()
            msg_empty = "Hệ thống chưa có người dùng nào."
            msg_ok = f"Đã gửi thông báo đến toàn bộ {qs.count()} người dùng."

        if not qs.exists():
            messages.error(request, msg_empty)
            return redirect('marketing:admin_notifications')

        create_system_notification(
            user=qs, title=title, content=content,
            promotion=promotion, delivery_channels=channels, status=notif_status,
        )
        messages.success(request, msg_ok)
        return redirect('marketing:admin_notifications')

    if action == 'update_notification':
        nid = (request.POST.get('notification_id') or '').strip()
        notif = Notification.objects.filter(id=int(nid)).first() if nid.isdigit() else None
        if not notif:
            messages.error(request, "Không tìm thấy thông báo cần chỉnh sửa.")
            return redirect('marketing:admin_notifications')

        title = str(request.POST.get('title') or '').strip()
        content = str(request.POST.get('content') or '').strip()
        channels = str(request.POST.get('delivery_channels') or 'In-App').strip() or 'In-App'
        notif_status = (request.POST.get('status') or notif.status or 'Đã gửi').strip()
        if notif_status not in ('Đã gửi', 'Chờ gửi'):
            messages.error(request, "Trạng thái thông báo không hợp lệ.")
            return redirect('marketing:admin_notifications')
        if not title or not content:
            messages.error(request, "Vui lòng nhập đầy đủ tiêu đề và nội dung thông báo.")
            return redirect('marketing:admin_notifications')

        promo_id = (request.POST.get('promotion_id') or '').strip()
        promotion = None
        if promo_id:
            promotion = Promotion.objects.filter(id=int(promo_id)).first() if promo_id.isdigit() else None
            if not promotion:
                messages.error(request, "Chương trình khuyến mãi đính kèm không tồn tại.")
                return redirect('marketing:admin_notifications')

        scope = (request.POST.get('scope') or 'broadcast').strip()
        with transaction.atomic():
            if scope == 'broadcast':
                updated_count = Notification.objects.filter(
                    title=notif.title,
                    content=notif.content,
                    notification_code__regex=r'^TB-\d+',
                ).update(
                    title=title,
                    content=content,
                    delivery_channels=channels,
                    promotion=promotion,
                    status=notif_status,
                )
                messages.success(request, f"Đã cập nhật thông báo thành công ({updated_count} bản ghi đồng bộ).")
            else:
                notif.title = title
                notif.content = content
                notif.delivery_channels = channels
                notif.promotion = promotion
                notif.status = notif_status
                notif.save()
                messages.success(request, "Đã cập nhật thông báo thành công.")
        return redirect('marketing:admin_notifications')

    if action == 'delete_notification':
        nid = (request.POST.get('notification_id') or '').strip()
        notif = Notification.objects.filter(id=int(nid)).first() if nid.isdigit() else None
        if not notif:
            messages.error(request, "Không tìm thấy thông báo cần xóa.")
            return redirect('marketing:admin_notifications')

        scope = (request.POST.get('scope') or 'broadcast').strip()
        if scope == 'broadcast':
            deleted_count, _ = Notification.objects.filter(
                title=notif.title,
                content=notif.content,
                notification_code__regex=r'^TB-\d+',
            ).delete()
            messages.success(request, f"Đã thu hồi và xóa đợt thông báo ({deleted_count} bản gửi).")
        else:
            notif.delete()
            messages.success(request, "Đã xóa thông báo thành công.")
        return redirect('marketing:admin_notifications')

    messages.error(request, "Thao tác không hợp lệ.")
    return redirect('marketing:admin_notifications')


@login_required
def admin_notifications_view(request):
    """
    [UC-7.3] MÀN HÌNH QUẢN TRỊ THÔNG BÁO (DÀNH CHO ADMIN)
    Layout: layouts/admin_layout.html (Nằm ở tab 'Quản lý Thông báo' trong Sidebar Admin)
    Chức năng:
      - Quản lý, xem chi tiết, chỉnh sửa và thu hồi/xóa các thông báo do Admin phát hành.
      - Soạn và phát thông báo mới cho khách hàng, nhân viên hoặc cá nhân cụ thể.
    """
    if not request.user.is_superuser:
        if request.method == 'POST':
            raise PermissionDenied("Bạn không có quyền quản trị thông báo.")
        messages.error(request, "Bạn không có quyền truy cập vào khu vực Quản trị Thông báo.")
        return redirect('marketing:notifications')

    if request.method == 'POST':
        return _handle_admin_notifications_post(request)

    ensure_sample_notifications_for_roles()

    search_kw = request.GET.get('q', '').strip()

    # Lấy các đợt thông báo do Admin/hệ thống phát hành (mã TB-<timestamp>-...)
    qs = (
        Notification.objects.filter(notification_code__regex=r'^TB-\d+')
        .select_related('promotion', 'user')
        .order_by('-created_at')
    )

    if search_kw:
        qs = qs.filter(
            Q(title__icontains=search_kw)
            | Q(content__icontains=search_kw)
            | Q(notification_code__icontains=search_kw)
        )

    # Gộp theo (tiêu đề, nội dung) để mỗi đợt gửi chung hiển thị thành 1 dòng lịch sử
    grouped = {}
    ordered_keys = []
    for notif in qs:
        key = (notif.title, notif.content)
        if key not in grouped:
            grouped[key] = []
            ordered_keys.append(key)
        grouped[key].append(notif)

    broadcast_items = []
    notif_map = {}
    for key in ordered_keys:
        group_notifs = grouped[key]
        rep = group_notifs[0]
        meta = _summarize_notification_group(group_notifs)
        rep.recipient_count = meta['recipient_count']
        rep.target_summary = meta['target_summary']
        rep.notif_scope = meta['scope']
        broadcast_items.append(rep)
        notif_map[str(rep.id)] = _serialize_admin_notification(rep, meta)

    notif_paginator = Paginator(broadcast_items, 15)
    notif_page = notif_paginator.get_page(request.GET.get('page', 1))

    promotions = Promotion.objects.all().order_by('-created_at')
    customers = User.objects.filter(is_staff=False, is_superuser=False).order_by('name')
    staffs = User.objects.filter(is_staff=True, is_superuser=False).order_by('name')

    context = {
        'base_layout': 'layouts/admin_layout.html',
        'notifications': notif_page,
        'total_broadcasts': len(broadcast_items),
        'promotions': promotions,
        'customers': customers,
        'staffs': staffs,
        'search_kw': search_kw,
        'notif_map': notif_map,
    }
    return render(request, 'marketing/admin_notifications.html', context)


def _parse_and_validate_promotion_payload(request, existing_promo=None):
    """Xác thực dữ liệu form Thêm/Sửa Chương trình Khuyến mãi và danh sách Voucher đính kèm."""
    title = str(request.POST.get('title') or '').strip()
    if not title:
        return None, "Vui lòng nhập tiêu đề chương trình khuyến mãi."

    raw_code = (request.POST.get('promotion_code') or '').strip().upper()
    if existing_promo is None:
        code = raw_code or f"KM-{int(timezone.now().timestamp())}"
    else:
        code = raw_code
        if not code:
            return None, "Vui lòng nhập mã chương trình khuyến mãi."

    dup_qs = Promotion.objects.filter(promotion_code=code)
    if existing_promo is not None:
        dup_qs = dup_qs.exclude(id=existing_promo.id)
    if dup_qs.exists():
        return None, f"Mã chương trình '{code}' đã tồn tại."

    status = (request.POST.get('status') or 'Đang hoạt động').strip()
    if status not in ('Đang hoạt động', 'Sắp diễn ra', 'Hết hạn'):
        status = 'Đang hoạt động'

    valid_from = _parse_dt(request.POST.get('valid_from'), end_of_day=False)
    valid_until = _parse_dt(request.POST.get('valid_until'), end_of_day=True)
    if valid_from and valid_until and valid_until < valid_from:
        return None, "Ngày kết thúc phải lớn hơn hoặc bằng ngày bắt đầu."

    raw_voucher_ids = [vid.strip() for vid in request.POST.getlist('voucher_ids') if str(vid).strip()]
    if any(not vid.isdigit() for vid in raw_voucher_ids):
        return None, "Danh sách mã Voucher được chọn không hợp lệ."
    voucher_ids = list(dict.fromkeys(int(vid) for vid in raw_voucher_ids))
    if voucher_ids and Voucher.objects.filter(id__in=voucher_ids).count() != len(voucher_ids):
        return None, "Có mã Voucher được chọn không tồn tại trong hệ thống."

    return {
        'promotion_code': code,
        'title': title,
        'conditions_desc': str(request.POST.get('conditions_desc') or '').strip(),
        'valid_from': valid_from,
        'valid_until': valid_until,
        'status': status,
        'voucher_ids': voucher_ids,
    }, None


def _parse_and_validate_voucher_payload(request, existing_voucher=None):
    """Xác thực dữ liệu form Thêm/Sửa Mã Voucher dùng chung cho Admin."""
    code = str(request.POST.get('voucher_code') or '').strip().upper()
    if not code:
        return None, "Vui lòng nhập mã Voucher."

    dup_qs = Voucher.objects.filter(voucher_code=code)
    if existing_voucher is not None:
        dup_qs = dup_qs.exclude(id=existing_voucher.id)
    if dup_qs.exists():
        return None, f"Mã Voucher '{code}' đã tồn tại trong hệ thống."

    disc_type = (request.POST.get('discount_type') or 'FIXED').strip()
    if disc_type not in ('PERCENT', 'FIXED', 'Phần trăm', 'Cố định'):
        return None, "Loại giảm giá không hợp lệ."

    try:
        disc_val = Decimal(str(request.POST.get('discount_value') or '0').strip())
    except (InvalidOperation, ValueError):
        return None, "Giá trị giảm giá không hợp lệ."
    if disc_val <= 0:
        return None, "Giá trị giảm giá phải lớn hơn 0."
    if disc_type in ('PERCENT', 'Phần trăm') and disc_val > Decimal(100):
        return None, "Giảm giá theo phần trăm (%) không được vượt quá 100%."

    max_disc = None
    raw_max = (request.POST.get('max_discount_amount') or '').strip()
    if disc_type in ('PERCENT', 'Phần trăm') and raw_max:
        try:
            max_disc = Decimal(raw_max)
            if max_disc <= 0:
                return None, "Mức giảm tối đa (khi giảm theo %) phải lớn hơn 0."
        except (InvalidOperation, ValueError):
            return None, "Mức giảm tối đa không hợp lệ."

    min_order = Decimal(0)
    raw_min = (request.POST.get('min_order_amount') or '').strip()
    if raw_min:
        try:
            min_order = Decimal(raw_min)
            if min_order < 0:
                return None, "Giá trị đơn hàng tối thiểu không thể âm."
        except (InvalidOperation, ValueError):
            return None, "Giá trị đơn hàng tối thiểu không hợp lệ."

    status = (request.POST.get('status') or (existing_voucher.status if existing_voucher else 'Khả dụng')).strip()
    if status not in ('Khả dụng', 'Đã dùng', 'Hết hạn'):
        return None, "Trạng thái Voucher không hợp lệ."

    expiry = _parse_dt(request.POST.get('expiry_date'), end_of_day=True)
    if not expiry:
        return None, "Vui lòng chọn ngày hết hạn hợp lệ."
    if status == 'Khả dụng' and expiry <= timezone.now():
        return None, "Ngày hết hạn của Voucher phải lớn hơn thời điểm hiện tại."

    promo_id = (request.POST.get('promotion_id') or '').strip()
    promotion = Promotion.objects.filter(id=int(promo_id)).first() if promo_id.isdigit() else None
    if promo_id and not promotion:
        return None, "Chương trình khuyến mãi không tồn tại."

    cust_id = (request.POST.get('customer_id') or '').strip()
    customer = User.objects.filter(id=int(cust_id)).first() if cust_id.isdigit() else None
    if cust_id and not customer:
        return None, "Khách hàng sở hữu riêng không tồn tại."

    return {
        'voucher_code': code,
        'discount_type': disc_type,
        'discount_value': disc_val,
        'max_discount_amount': max_disc if disc_type in ('PERCENT', 'Phần trăm') else None,
        'min_order_amount': min_order,
        'status': status,
        'expiry_date': expiry,
        'promotion': promotion,
        'customer': customer,
    }, None


def _serialize_admin_promotion(promo):
    """Chuyển bản ghi Promotion và danh sách Voucher đính kèm thành dict cho modal Xem/Sửa."""
    vouchers_list = list(promo.vouchers.all())
    return {
        'id': promo.id,
        'promotion_code': promo.promotion_code,
        'title': promo.title,
        'conditions_desc': promo.conditions_desc or '',
        'valid_from': _local_dt_str(promo.valid_from, '%Y-%m-%d'),
        'valid_from_display': _local_dt_str(promo.valid_from, '%d/%m/%Y') or '---',
        'valid_until': _local_dt_str(promo.valid_until, '%Y-%m-%d'),
        'valid_until_display': _local_dt_str(promo.valid_until, '%d/%m/%Y') or 'Vô thời hạn',
        'status': promo.status,
        'created_at_display': _local_dt_str(promo.created_at),
        'voucher_ids': [v.id for v in vouchers_list],
        'vouchers': [
            {
                'id': v.id,
                'voucher_code': v.voucher_code,
                'discount_label': _voucher_discount_label(v),
                'status': v.status,
                'target_label': (v.customer.name or v.customer.username) if v.customer else 'Toàn bộ khách hàng',
                'expiry_display': _local_dt_str(v.expiry_date),
            }
            for v in vouchers_list
        ],
    }


def _serialize_admin_voucher(v):
    """Chuyển bản ghi Voucher thành dict cho modal Xem/Sửa."""
    return {
        'id': v.id,
        'voucher_code': v.voucher_code,
        'promotion_id': str(v.promotion_id) if v.promotion_id else '',
        'promotion_title': f"{v.promotion.promotion_code} - {v.promotion.title}" if v.promotion else 'Voucher độc lập (Không thuộc chương trình)',
        'complaint_code': v.complaint.complaint_code if getattr(v, 'complaint', None) else '',
        'customer_id': str(v.customer_id) if v.customer_id else '',
        'customer_label': (
            f"{v.customer.name or v.customer.username} ({v.customer.phone or v.customer.email or ''})"
            if v.customer else 'Toàn bộ khách hàng'
        ),
        'discount_type': 'PERCENT' if v.discount_type in ('PERCENT', 'Phần trăm') else 'FIXED',
        'discount_type_label': 'Giảm theo %' if v.discount_type in ('PERCENT', 'Phần trăm') else 'Giảm tiền mặt (VNĐ)',
        'discount_value': _fmt_decimal_input(v.discount_value),
        'discount_display': _voucher_discount_label(v),
        'max_discount_amount': _fmt_decimal_input(v.max_discount_amount),
        'max_discount_display': _fmt_vnd(v.max_discount_amount) if v.max_discount_amount else 'Không giới hạn',
        'min_order_amount': _fmt_decimal_input(v.min_order_amount or Decimal(0)),
        'min_order_display': _fmt_vnd(v.min_order_amount or Decimal(0)),
        'status': v.status,
        'expiry_date': _local_dt_str(v.expiry_date, '%Y-%m-%dT%H:%M'),
        'expiry_display': _local_dt_str(v.expiry_date),
        'used_at_display': _local_dt_str(v.used_at) if v.used_at else 'Chưa sử dụng',
        'created_at_display': _local_dt_str(v.created_at),
    }


def _handle_admin_promotions_post(request):
    """Xử lý form POST Thêm/Sửa/Đổi trạng thái/Xóa Khuyến mãi và Voucher."""
    action = (request.POST.get('action') or '').strip()
    promo_redirect = f"{reverse('marketing:admin_promotions')}?subtab=promotions"
    voucher_redirect = f"{reverse('marketing:admin_promotions')}?subtab=vouchers"

    if action == 'create_promotion':
        data, err = _parse_and_validate_promotion_payload(request)
        if err:
            messages.error(request, err)
            return redirect(promo_redirect)
        voucher_ids = data.pop('voucher_ids')
        with transaction.atomic():
            promo = Promotion.objects.create(**data)
            if voucher_ids:
                Voucher.objects.filter(id__in=voucher_ids).update(promotion=promo)
        msg = f"Đã tạo chương trình khuyến mãi '{promo.title}' thành công."
        if voucher_ids:
            msg += f" (Đã gắn {len(voucher_ids)} voucher)."
        messages.success(request, msg)
        return redirect(promo_redirect)

    if action == 'update_promotion':
        pid = (request.POST.get('promotion_id') or '').strip()
        promo = Promotion.objects.filter(id=int(pid)).first() if pid.isdigit() else None
        if not promo:
            messages.error(request, "Không tìm thấy chương trình khuyến mãi cần chỉnh sửa.")
            return redirect(promo_redirect)
        data, err = _parse_and_validate_promotion_payload(request, existing_promo=promo)
        if err:
            messages.error(request, err)
            return redirect(promo_redirect)
        voucher_ids = data.pop('voucher_ids')
        with transaction.atomic():
            for field, val in data.items():
                setattr(promo, field, val)
            promo.save()
            Voucher.objects.filter(promotion=promo).exclude(id__in=voucher_ids).update(promotion=None)
            if voucher_ids:
                Voucher.objects.filter(id__in=voucher_ids).update(promotion=promo)
        messages.success(request, f"Đã cập nhật chương trình '{promo.title}' (đính kèm {len(voucher_ids)} voucher) thành công.")
        return redirect(promo_redirect)

    if action == 'toggle_promotion':
        pid = (request.POST.get('promotion_id') or '').strip()
        promo = Promotion.objects.filter(id=int(pid)).first() if pid.isdigit() else None
        if not promo:
            messages.error(request, "Không tìm thấy chương trình khuyến mãi.")
            return redirect(promo_redirect)
        promo.status = 'Hết hạn' if promo.status == 'Đang hoạt động' else 'Đang hoạt động'
        promo.save(update_fields=['status'])
        messages.success(request, f"Đã chuyển trạng thái '{promo.title}' sang '{promo.status}'.")
        return redirect(promo_redirect)

    if action == 'delete_promotion':
        pid = (request.POST.get('promotion_id') or '').strip()
        promo = Promotion.objects.filter(id=int(pid)).first() if pid.isdigit() else None
        if not promo:
            messages.error(request, "Không tìm thấy chương trình khuyến mãi cần xóa.")
            return redirect(promo_redirect)
        promo_title = promo.title
        promo.delete()
        messages.success(request, f"Đã xóa chiến dịch '{promo_title}' thành công.")
        return redirect(promo_redirect)

    if action == 'create_voucher':
        data, err = _parse_and_validate_voucher_payload(request)
        if err:
            messages.error(request, err)
            return redirect(voucher_redirect)
        with transaction.atomic():
            if data['status'] == 'Đã dùng':
                data['used_at'] = timezone.now()
            voucher = Voucher.objects.create(**data)
        messages.success(request, f"Phát hành mã Voucher {voucher.voucher_code} thành công.")
        return redirect(voucher_redirect)

    if action == 'update_voucher':
        vid = (request.POST.get('voucher_id') or '').strip()
        voucher = Voucher.objects.filter(id=int(vid)).first() if vid.isdigit() else None
        if not voucher:
            messages.error(request, "Không tìm thấy mã Voucher cần chỉnh sửa.")
            return redirect(voucher_redirect)
        data, err = _parse_and_validate_voucher_payload(request, existing_voucher=voucher)
        if err:
            messages.error(request, err)
            return redirect(voucher_redirect)
        with transaction.atomic():
            for field, val in data.items():
                setattr(voucher, field, val)
            if voucher.status == 'Đã dùng' and not voucher.used_at:
                voucher.used_at = timezone.now()
            elif voucher.status == 'Khả dụng':
                voucher.used_at = None
            voucher.save()
        messages.success(request, f"Đã cập nhật mã Voucher {voucher.voucher_code} thành công.")
        return redirect(voucher_redirect)

    if action == 'delete_voucher':
        vid = (request.POST.get('voucher_id') or '').strip()
        voucher = Voucher.objects.filter(id=int(vid)).first() if vid.isdigit() else None
        if not voucher:
            messages.error(request, "Không tìm thấy mã Voucher cần xóa.")
            return redirect(voucher_redirect)
        code = voucher.voucher_code
        voucher.delete()
        messages.success(request, f"Đã xóa mã Voucher {code} thành công.")
        return redirect(voucher_redirect)

    messages.error(request, "Thao tác không hợp lệ.")
    return redirect(promo_redirect)


@login_required
def admin_promotions_view(request):
    """
    [UC-7.4] MÀN HÌNH QUẢN TRỊ KHUYẾN MÃI & MÃ VOUCHER (DÀNH CHO ADMIN)
    Layout: layouts/admin_layout.html (Nằm ở tab 'Quản lý Khuyến mãi' trong Sidebar Admin)
    Bao gồm 2 Sub-tab nghiệp vụ:
      - Sub-tab 1: Chương trình Khuyến mãi (Thêm/Xem/Sửa/Xóa Promotion, chọn gắn Voucher hiện có).
      - Sub-tab 2: Quản lý Mã Voucher (Thêm/Xem/Sửa/Xóa Voucher linh hoạt % có trần hoặc cố định VNĐ).
    """
    if not request.user.is_superuser:
        if request.method == 'POST':
            raise PermissionDenied("Bạn không có quyền quản trị khuyến mãi.")
        messages.error(request, "Bạn không có quyền truy cập vào khu vực Quản trị Khuyến mãi.")
        return redirect('marketing:promotions')

    if request.method == 'POST':
        return _handle_admin_promotions_post(request)

    ensure_sample_notifications_for_roles()

    active_subtab = request.GET.get('subtab', 'promotions')
    if active_subtab not in ('promotions', 'vouchers'):
        active_subtab = 'promotions'

    # Dữ liệu cho Sub-tab 1: Chương trình Khuyến mãi
    promotions = list(
        Promotion.objects.all()
        .prefetch_related('vouchers', 'vouchers__customer')
        .annotate(total_vouchers=Count('vouchers'))
        .order_by('-created_at')
    )

    # Dữ liệu cho Sub-tab 2: Kho Mã Voucher (all_vouchers dùng cho selector ở modal Promotion)
    all_vouchers = list(
        Voucher.objects.all()
        .select_related('promotion', 'customer', 'complaint')
        .order_by('-created_at')
    )
    voucher_paginator = Paginator(all_vouchers, 15)
    voucher_page = voucher_paginator.get_page(request.GET.get('page', 1))

    # Gắn nhãn mô tả rút gọn cho selector chọn voucher ở Promotion modal
    for v in all_vouchers:
        v.discount_summary_label = _voucher_discount_label(v)

    # Danh sách khách hàng cho modal cấp/sửa voucher
    customers = User.objects.filter(is_staff=False, is_superuser=False).order_by('name')

    now = timezone.now()
    kpi = {
        'active_promotions': Promotion.objects.filter(status='Đang hoạt động').count(),
        'total_promotions': len(promotions),
        'available_vouchers': Voucher.objects.filter(status='Khả dụng', expiry_date__gte=now).count(),
        'used_vouchers': Voucher.objects.filter(status='Đã dùng').count(),
    }

    promo_map = {str(p.id): _serialize_admin_promotion(p) for p in promotions}
    voucher_map = {str(v.id): _serialize_admin_voucher(v) for v in all_vouchers}

    context = {
        'base_layout': 'layouts/admin_layout.html',
        'active_subtab': active_subtab,
        'promotions': promotions,
        'vouchers': voucher_page,
        'all_vouchers': all_vouchers,
        'customers': customers,
        'kpi': kpi,
        'promo_map': promo_map,
        'voucher_map': voucher_map,
    }
    return render(request, 'marketing/admin_promotions.html', context)


# Alias tương thích ngược
admin_marketing_view = admin_notifications_view


@login_required
def staff_notifications_view(request):
    """
    [UC-7.1, UC-7.5] MÀN HÌNH THÔNG BÁO DÀNH CHO NHÂN VIÊN (STAFF WORKSPACE)
    Layout: layouts/staff_layout.html
    Nhân viên (CSKH / Lễ tân) nhận các thông báo:
      - Admin phân công / giao xử lý khiếu nại khách hàng.
      - Yêu cầu tư vấn khách hàng trên Livechat Console.
      - Đánh giá dịch vụ & thông báo điều phối công việc nội bộ.
    """
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Khu vực này chỉ dành cho Nhân viên Cham Spa.")
        return redirect('marketing:notifications')

    ensure_sample_notifications_for_roles()

    tab = request.GET.get('tab', 'all')
    if tab == 'assigned':
        tab = 'complaints'
    if tab not in ('all', 'complaints', 'consultation', 'internal'):
        tab = 'all'
    search_kw = request.GET.get('q', '').strip()

    # Loại trừ các thông báo của Khách hàng (điểm thưởng, voucher...) và ca trực KTV khỏi luồng Staff
    base_qs = filter_notifications_for_user(
        Notification.objects.filter(user=request.user),
        request.user,
    ).order_by('-created_at')

    stats = {
        'all': 0,
        'complaints': 0,
        'consultation': 0,
        'internal': 0,
    }
    url_cache = {}
    filtered_notifs = []
    search_l = search_kw.lower()

    for notif in base_qs:
        meta = classify_staff_notification(notif)
        cat = meta['category']
        notif.staff_category = cat
        notif.staff_badge_label = meta['badge_label']
        notif.staff_badge_class = meta['badge_class']

        url_name = meta['action_url_name']
        if url_name:
            cache_key = (url_name, meta['action_query'])
            if cache_key not in url_cache:
                url_cache[cache_key] = reverse(url_name) + meta['action_query']
            notif.staff_action_url = url_cache[cache_key]
            notif.staff_action_label = meta['action_label']
        else:
            notif.staff_action_url = ''
            notif.staff_action_label = ''

        stats['all'] += 1
        stats[cat] += 1

        if search_l and search_l not in (notif.title or '').lower() and search_l not in (notif.content or '').lower():
            continue
        if tab != 'all' and cat != tab:
            continue
        filtered_notifs.append(notif)

    paginator = Paginator(filtered_notifs, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'base_layout': 'layouts/staff_layout.html',
        'notifications': page_obj,
        'page_obj': page_obj,
        'active_tab': tab,
        'search_query': search_kw,
        'stats': stats,
    }
    return render(request, 'marketing/staff_notifications.html', context)
