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
    promotions = Promotion.objects.filter(
        Q(status='Đang hoạt động') | Q(status='Sắp diễn ra')
    ).order_by('-created_at')

    # 2. Danh sách Voucher
    if user.is_authenticated:
        # Lấy voucher khả dụng: gồm voucher toàn hệ thống (customer=None) hoặc gán cho chính user
        available_vouchers = Voucher.objects.filter(
            Q(customer__isnull=True) | Q(customer=user),
            status='Khả dụng',
            expiry_date__gte=timezone.now()
        ).select_related('promotion').order_by('expiry_date')

        # Voucher đã sử dụng hoặc hết hạn của user
        history_vouchers = Voucher.objects.filter(
            Q(customer=user),
            Q(status__in=['Đã dùng', 'Hết hạn']) | Q(expiry_date__lt=timezone.now())
        ).select_related('promotion').order_by('-created_at')[:10]
    else:
        available_vouchers = Voucher.objects.filter(
            customer__isnull=True,
            status='Khả dụng',
            expiry_date__gte=timezone.now()
        ).select_related('promotion').order_by('expiry_date')
        history_vouchers = []

    context = {
        'base_layout': base_layout,
        'promotions': promotions,
        'available_vouchers': available_vouchers,
        'history_vouchers': history_vouchers,
        'total_promotions': promotions.count(),
        'total_vouchers': available_vouchers.count(),
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


def _parse_dt(val):
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
                dt = datetime(d.year, d.month, d.day, 23, 59, 59)
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _handle_admin_notifications_post(request):
    """Xử lý form POST tạo/phát hành hoặc xóa thông báo từ trang Quản trị."""
    action = (request.POST.get('action') or '').strip()

    if action == 'create_notification':
        title = str(request.POST.get('title') or '').strip()
        content = str(request.POST.get('content') or '').strip()
        target_type = (request.POST.get('target_type') or 'all_customers').strip()
        channels = str(request.POST.get('delivery_channels') or 'In-App').strip()
        promo_id = (request.POST.get('promotion_id') or '').strip()

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
                promotion=promotion, delivery_channels=channels, status='Đã gửi',
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
            promotion=promotion, delivery_channels=channels, status='Đã gửi',
        )
        messages.success(request, msg_ok)
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
                user__is_staff=False,
                user__is_superuser=False,
                title=notif.title,
                content=notif.content,
                notification_code__regex=r'^TB-\d+',
            ).delete()
            messages.success(request, f"Đã thu hồi và xóa đợt thông báo chung ({deleted_count} bản gửi).")
        else:
            notif.delete()
            messages.success(request, "Đã xóa thông báo thành công.")
        return redirect('marketing:admin_notifications')

    messages.error(request, "Thao tác không hợp lệ.")
    return redirect('marketing:admin_notifications')


@login_required
def admin_notifications_view(request):
    """
    [UC-7.3] MÀN HÌNH QUẢN TRỊ THÔNG BÁO CHUNG GỬI KHÁCH HÀNG (DÀNH CHO ADMIN)
    Layout: layouts/admin_layout.html (Nằm ở tab 'Quản lý Thông báo' trong Sidebar Admin)
    Chức năng:
      - Quản lý và theo dõi lịch sử các đợt phát thông báo chung tới toàn bộ khách hàng.
      - Soạn và phát thông báo chung mới đến toàn bộ khách hàng (Form POST + bulk_create).
      - Thu hồi/xóa đợt thông báo đã gửi.
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

    # Chỉ lấy các đợt thông báo chung phát hành cho toàn bộ khách hàng (mã TB-<timestamp>-...)
    qs = (
        Notification.objects.filter(
            user__is_staff=False,
            user__is_superuser=False,
            notification_code__regex=r'^TB-\d+',
        )
        .select_related('promotion')
        .order_by('-created_at')
    )

    if search_kw:
        qs = qs.filter(Q(title__icontains=search_kw) | Q(content__icontains=search_kw))

    # Gộp theo (tiêu đề, nội dung) để mỗi đợt gửi chung hiển thị thành 1 dòng lịch sử
    seen_broadcasts = set()
    broadcast_items = []
    for notif in qs:
        key = (notif.title, notif.content)
        if key not in seen_broadcasts:
            seen_broadcasts.add(key)
            broadcast_items.append(notif)

    notif_paginator = Paginator(broadcast_items, 15)
    notif_page = notif_paginator.get_page(request.GET.get('page', 1))

    promotions = Promotion.objects.filter(status='Đang hoạt động').order_by('-created_at')

    context = {
        'base_layout': 'layouts/admin_layout.html',
        'notifications': notif_page,
        'total_broadcasts': len(broadcast_items),
        'promotions': promotions,
        'search_kw': search_kw,
    }
    return render(request, 'marketing/admin_notifications.html', context)


def _handle_admin_promotions_post(request):
    """Xử lý form POST tạo/đổi trạng thái/xóa Khuyến mãi và tạo/xóa Voucher."""
    action = (request.POST.get('action') or '').strip()
    promo_redirect = f"{reverse('marketing:admin_promotions')}?subtab=promotions"
    voucher_redirect = f"{reverse('marketing:admin_promotions')}?subtab=vouchers"

    if action == 'create_promotion':
        title = str(request.POST.get('title') or '').strip()
        if not title:
            messages.error(request, "Vui lòng nhập tiêu đề chương trình khuyến mãi.")
            return redirect(promo_redirect)
        code = (request.POST.get('promotion_code') or '').strip().upper() or f"KM-{int(timezone.now().timestamp())}"
        if Promotion.objects.filter(promotion_code=code).exists():
            messages.error(request, f"Mã chương trình '{code}' đã tồn tại.")
            return redirect(promo_redirect)
        status = (request.POST.get('status') or 'Đang hoạt động').strip()
        if status not in ('Đang hoạt động', 'Sắp diễn ra', 'Hết hạn'):
            status = 'Đang hoạt động'

        Promotion.objects.create(
            promotion_code=code,
            title=title,
            conditions_desc=str(request.POST.get('conditions_desc') or '').strip(),
            valid_from=_parse_dt(request.POST.get('valid_from')),
            valid_until=_parse_dt(request.POST.get('valid_until')),
            status=status,
        )
        messages.success(request, f"Đã tạo chương trình khuyến mãi '{title}' thành công.")
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
        code = str(request.POST.get('voucher_code') or '').strip().upper()
        if not code:
            messages.error(request, "Vui lòng nhập mã Voucher.")
            return redirect(voucher_redirect)
        if Voucher.objects.filter(voucher_code=code).exists():
            messages.error(request, f"Mã Voucher '{code}' đã tồn tại trong hệ thống.")
            return redirect(voucher_redirect)

        disc_type = (request.POST.get('discount_type') or 'FIXED').strip()
        if disc_type not in ('PERCENT', 'FIXED', 'Phần trăm', 'Cố định'):
            messages.error(request, "Loại giảm giá không hợp lệ.")
            return redirect(voucher_redirect)

        try:
            disc_val = Decimal(str(request.POST.get('discount_value') or '0').strip())
        except (InvalidOperation, ValueError):
            messages.error(request, "Giá trị giảm giá không hợp lệ.")
            return redirect(voucher_redirect)
        if disc_val <= 0:
            messages.error(request, "Giá trị giảm giá phải lớn hơn 0.")
            return redirect(voucher_redirect)
        if disc_type in ('PERCENT', 'Phần trăm') and disc_val > Decimal(100):
            messages.error(request, "Giảm giá theo phần trăm (%) không được vượt quá 100%.")
            return redirect(voucher_redirect)

        max_disc = None
        raw_max = (request.POST.get('max_discount_amount') or '').strip()
        if disc_type in ('PERCENT', 'Phần trăm') and raw_max:
            try:
                max_disc = Decimal(raw_max)
                if max_disc <= 0:
                    messages.error(request, "Mức giảm tối đa (khi giảm theo %) phải lớn hơn 0.")
                    return redirect(voucher_redirect)
            except (InvalidOperation, ValueError):
                messages.error(request, "Mức giảm tối đa không hợp lệ.")
                return redirect(voucher_redirect)

        min_order = Decimal(0)
        raw_min = (request.POST.get('min_order_amount') or '').strip()
        if raw_min:
            try:
                min_order = Decimal(raw_min)
                if min_order < 0:
                    messages.error(request, "Giá trị đơn hàng tối thiểu không thể âm.")
                    return redirect(voucher_redirect)
            except (InvalidOperation, ValueError):
                messages.error(request, "Giá trị đơn hàng tối thiểu không hợp lệ.")
                return redirect(voucher_redirect)

        expiry = _parse_dt(request.POST.get('expiry_date'))
        if not expiry:
            messages.error(request, "Vui lòng chọn ngày hết hạn hợp lệ.")
            return redirect(voucher_redirect)
        if expiry <= timezone.now():
            messages.error(request, "Ngày hết hạn của Voucher phải lớn hơn thời điểm hiện tại.")
            return redirect(voucher_redirect)

        promo_id = (request.POST.get('promotion_id') or '').strip()
        promotion = Promotion.objects.filter(id=int(promo_id)).first() if promo_id.isdigit() else None
        if promo_id and not promotion:
            messages.error(request, "Chương trình khuyến mãi không tồn tại.")
            return redirect(voucher_redirect)

        cust_id = (request.POST.get('customer_id') or '').strip()
        customer = User.objects.filter(id=int(cust_id)).first() if cust_id.isdigit() else None
        if cust_id and not customer:
            messages.error(request, "Khách hàng sở hữu riêng không tồn tại.")
            return redirect(voucher_redirect)

        with transaction.atomic():
            voucher = Voucher.objects.create(
                voucher_code=code,
                discount_type=disc_type,
                discount_value=disc_val,
                max_discount_amount=max_disc if disc_type in ('PERCENT', 'Phần trăm') else None,
                min_order_amount=min_order,
                expiry_date=expiry,
                promotion=promotion,
                customer=customer,
            )
        messages.success(request, f"Phát hành mã Voucher {voucher.voucher_code} thành công.")
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
      - Sub-tab 1: Chương trình Khuyến mãi (CRUD Promotion, toggle status nhanh qua Form POST).
      - Sub-tab 2: Quản lý Mã Voucher (Phát hành Voucher linh hoạt % có trần hoặc cố định VNĐ).
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

    # Dữ liệu cho Sub-tab 1: Chương trình Khuyến mãi
    promotions = Promotion.objects.all().annotate(total_vouchers=Count('vouchers')).order_by('-created_at')

    # Dữ liệu cho Sub-tab 2: Kho Mã Voucher
    vouchers_qs = Voucher.objects.all().select_related('promotion', 'customer').order_by('-created_at')
    voucher_paginator = Paginator(vouchers_qs, 15)
    voucher_page = voucher_paginator.get_page(request.GET.get('page', 1))

    # Danh sách khách hàng và chương trình cho modal cấp voucher
    customers = User.objects.filter(is_staff=False, is_superuser=False).order_by('name')

    now = timezone.now()
    kpi = {
        'active_promotions': Promotion.objects.filter(status='Đang hoạt động').count(),
        'total_promotions': Promotion.objects.count(),
        'available_vouchers': Voucher.objects.filter(status='Khả dụng', expiry_date__gte=now).count(),
        'used_vouchers': Voucher.objects.filter(status='Đã dùng').count(),
    }

    context = {
        'base_layout': 'layouts/admin_layout.html',
        'active_subtab': active_subtab,
        'promotions': promotions,
        'vouchers': voucher_page,
        'customers': customers,
        'kpi': kpi,
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
