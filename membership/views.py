"""
================================================================================
MODULE 06: QUẢN LÝ HỘI VIÊN & TÍCH ĐIỂM (MOD-06) - TEMPLATE VIEWS
Thành viên phụ trách: MINH KHÁNH
Mục đích:
  - Điều phối và render các giao diện HTML cho Module 6:
    1. Giao diện Thẻ Hội viên điện tử & Tiến trình thăng hạng của Khách hàng (UC-6.1)
       Kế thừa layouts/customer_layout.html khớp thiết kế Figma Node 1323 & 608:250.
    2. Giao diện Tra cứu Hội viên tại Quầy Lễ Tân & Quản lý Thẻ VIP toàn Spa (UC-6.2)
       Kế thừa layouts/admin_layout.html hoặc layouts/staff_layout.html.
================================================================================
"""

from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.contrib import messages
from django.utils import timezone

# Tuyệt đối chỉ import model từ core.models (Không tạo model mới)
from core.models import Tier, Membership, MembershipPoint, Notification, User, Appointment, Voucher


@login_required
def customer_membership_view(request):
    """
    [UC-6.1 - Figma Node 1323 & 608:250] Màn hình Thẻ Hội viên điện tử & Tiến trình thăng hạng:
    - Thẻ hội viên VIP sang trọng mang thương hiệu Cham Spa (Serenity Card).
    - Thanh Progress Bar hiển thị tiến độ thăng hạng (Hạng Đồng -> Hạng Bạc -> Hạng Vàng -> Hạng Kim Cương).
    - 4 Widget thống kê: Điểm khả dụng, Tổng chi tiêu, Chiết khấu VIP, Hạng thẻ hiện tại.
    - Bảng Lịch sử tích điểm thưởng (MembershipPoint) có tìm kiếm và phân trang.
    - Bảng đối chiếu đặc quyền các hạng thẻ VIP (4 hạng chuẩn: Đồng, Bạc, Vàng, Kim Cương).
    - Tab Ví Voucher: Tra cứu, kiểm tra & sao chép các mã ưu đãi khả dụng từ Cham Spa.
    """
    user = request.user

    # 1. Lấy hoặc tự động tạo Thẻ hội viên cho tài khoản
    default_tier = Tier.objects.filter(min_points=0).order_by('min_points').first() or Tier.objects.order_by('min_points').first()
    membership, created = Membership.objects.get_or_create(
        user=user,
        defaults={
            'tier': default_tier,
            'current_points': 0,
            'total_points_used': 0,
            'total_spent': Decimal(0),
        }
    )

    if membership.tier is None and default_tier:
        membership.tier = default_tier
        membership.save(update_fields=['tier'])

    current_tier = membership.tier

    # 2. Tính toán Hạng thẻ kế tiếp và Tiến trình thăng hạng (Tier Upgrade Roadmap)
    curr_min = current_tier.min_points if current_tier else 0
    next_tier = Tier.objects.filter(min_points__gt=curr_min).order_by('min_points').first()

    next_tier_name = next_tier.name if next_tier else (current_tier.name if current_tier else "Hạng Kim Cương")
    next_tier_points = next_tier.min_points if next_tier else (current_tier.min_points if current_tier else 3000)
    is_max_tier = next_tier is None

    # Tiến độ điểm
    remaining_points = max(0, next_tier_points - membership.current_points) if not is_max_tier else 0
    if next_tier_points > 0:
        points_pct = min(100, int((membership.current_points / next_tier_points) * 100))
    else:
        points_pct = 100

    # Tiến độ chi tiêu (Mốc chuẩn 10.000.000 VNĐ theo Figma)
    target_spent = Decimal(10000000)
    remaining_spent = max(Decimal(0), target_spent - (membership.total_spent or Decimal(0))) if not is_max_tier else Decimal(0)
    if target_spent > 0:
        spent_pct = min(100, int((float(membership.total_spent or 0) / float(target_spent)) * 100))
    else:
        spent_pct = 100

    # 3. Lịch sử tích điểm thưởng (chỉ ghi nhận điểm cộng từ thanh toán > 0)
    point_history_qs = membership.point_history.filter(points_amount__gt=0).order_by('-created_at')

    # Tìm kiếm theo mã lịch hẹn hoặc lý do
    search_q = request.GET.get('q', '').strip()
    if search_q:
        point_history_qs = point_history_qs.filter(
            Q(appointment_id__icontains=search_q) |
            Q(reason_description__icontains=search_q)
        )

    # Phân trang lịch sử điểm (10 bản ghi / trang)
    paginator = Paginator(point_history_qs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Đồng bộ mã hiển thị giao dịch chuẩn (#LH... hoặc #HD...)
    appt_ids = [p.appointment_id for p in page_obj if p.appointment_id and str(p.appointment_id).isdigit()]
    appt_map = {}
    if appt_ids:
        appt_map = dict(Appointment.objects.filter(id__in=[int(x) for x in appt_ids]).values_list('id', 'appointment_code'))

    for p in page_obj:
        raw = str(p.appointment_id or '').strip()
        if raw.isdigit() and int(raw) in appt_map:
            c = appt_map[int(raw)]
            p.display_code = c if c.startswith('#') else f"#{c}"
        elif raw:
            p.display_code = raw if raw.startswith('#') else f"#{raw}"
        else:
            p.display_code = "#HD-CHAMSPA"

    # 4. Thống kê tổng quan cá nhân
    total_earned = membership.point_history.filter(points_amount__gt=0).aggregate(
        total=Sum('points_amount')
    )['total'] or 0

    # Danh sách tất cả 4 Hạng thẻ để hiển thị Bảng so sánh quyền lợi
    all_tiers = Tier.objects.all().order_by('min_points')

    # 5. Ví Voucher cá nhân & ưu đãi chung khả dụng cho khách hàng (MOD-07 sync)
    now = timezone.now()
    available_vouchers = list(Voucher.objects.filter(
        Q(customer__isnull=True) | Q(customer=user),
        status='Khả dụng',
        expiry_date__gte=now
    ).select_related('promotion').order_by('expiry_date'))

    history_vouchers = list(Voucher.objects.filter(
        customer=user
    ).filter(
        Q(status__in=['Đã dùng', 'Hết hạn']) | Q(expiry_date__lt=now)
    ).select_related('promotion').order_by('-created_at')[:10])

    for v in available_vouchers + history_vouchers:
        val = int(v.discount_value or 0)
        if v.discount_type in ('PERCENT', 'Phần trăm'):
            v.display_discount = f"-{val}%"
        else:
            v.display_discount = f"-{val:,}".replace(',', '.') + "đ"
        min_amt = int(v.min_order_amount or 0)
        v.display_min_order = f"{min_amt:,}".replace(',', '.') + "đ" if min_amt > 0 else ""
        max_amt = int(v.max_discount_amount or 0) if v.max_discount_amount else 0
        v.display_max_discount = f"{max_amt:,}".replace(',', '.') + "đ" if max_amt > 0 else ""

    active_tab = request.GET.get('tab', 'card')
    if active_tab not in ('card', 'vouchers'):
        active_tab = 'card'

    # Mã khách hàng hiển thị và Mã thẻ số
    customer_code = f"CUS{user.id:03d}"
    card_number = f"CS-{timezone.now().year}-{user.id:04d}"

    # Định dạng tiền tệ hiển thị đẹp mắt
    formatted_total_spent = f"{int(membership.total_spent or 0):,}".replace(',', '.') + " VNĐ"
    formatted_remaining_spent = f"{int(remaining_spent):,}".replace(',', '.') + " VNĐ"
    formatted_target_spent = f"{int(target_spent):,}".replace(',', '.') + " VNĐ"

    context = {
        'membership': membership,
        'current_tier': current_tier,
        'next_tier': next_tier,
        'next_tier_name': next_tier_name,
        'next_tier_points': next_tier_points,
        'is_max_tier': is_max_tier,
        'remaining_points': remaining_points,
        'points_pct': points_pct,
        'target_spent': target_spent,
        'remaining_spent': remaining_spent,
        'spent_pct': spent_pct,
        'formatted_total_spent': formatted_total_spent,
        'formatted_remaining_spent': formatted_remaining_spent,
        'formatted_target_spent': formatted_target_spent,
        'point_history': page_obj,
        'total_earned': total_earned,
        'all_tiers': all_tiers,
        'available_vouchers': available_vouchers,
        'history_vouchers': history_vouchers,
        'total_vouchers': len(available_vouchers),
        'active_tab': active_tab,
        'customer_code': customer_code,
        'card_number': card_number,
        'search_q': search_q,
    }
    return render(request, 'membership/customer_membership.html', context)


def _handle_adjust_points_post(request):
    """Xử lý form POST điều chỉnh (cộng/trừ) điểm thưởng thủ công tại quầy."""
    mid_raw = (request.POST.get('membership_id') or '').strip()
    membership = Membership.objects.select_related('user', 'tier').filter(id=int(mid_raw)).first() if mid_raw.isdigit() else None
    if not membership:
        messages.error(request, "Không tìm thấy thẻ hội viên hợp lệ.")
        return redirect('membership:staff_lookup')

    action = (request.POST.get('adjust_action') or request.POST.get('action') or 'ADD').strip().upper()
    if action not in ('ADD', 'DEDUCT'):
        messages.error(request, "Loại thao tác điều chỉnh điểm không hợp lệ.")
        return redirect('membership:staff_lookup')

    try:
        points_amount = int((request.POST.get('points_amount') or '').strip())
    except (TypeError, ValueError):
        messages.error(request, "Số điểm phải là số nguyên dương.")
        return redirect('membership:staff_lookup')
    if points_amount < 1:
        messages.error(request, "Số điểm phải lớn hơn 0.")
        return redirect('membership:staff_lookup')

    reason_desc = str(request.POST.get('reason_description') or '').strip()
    if len(reason_desc) < 5 or len(reason_desc) > 500:
        messages.error(request, "Lý do điều chỉnh phải từ 5 đến 500 ký tự.")
        return redirect('membership:staff_lookup')

    if action == 'DEDUCT' and membership.current_points < points_amount:
        messages.error(
            request,
            f"Số dư điểm hiện tại ({membership.current_points} điểm) không đủ để trừ {points_amount} điểm."
        )
        return redirect('membership:staff_lookup')

    operator_name = request.user.name or request.user.username

    with transaction.atomic():
        if action == 'ADD':
            points_delta = points_amount
            membership.current_points += points_amount
            full_reason = f"[Cộng điểm bởi {operator_name}] {reason_desc}"
            action_text = f"Cộng +{points_amount} điểm thưởng"
        else:
            points_delta = -points_amount
            membership.current_points -= points_amount
            membership.total_points_used += points_amount
            full_reason = f"[Trừ điểm bởi {operator_name}] {reason_desc}"
            action_text = f"Trừ -{points_amount} điểm thưởng"

        MembershipPoint.objects.create(
            membership=membership,
            appointment_id=f"ADJ-{int(timezone.now().timestamp())}",
            points_amount=points_delta,
            reason_description=full_reason,
        )

        if action == 'ADD':
            accumulated_points = max(
                membership.current_points,
                membership.current_points + membership.total_points_used,
            )
            eligible_tier = Tier.objects.filter(min_points__lte=accumulated_points).order_by('-min_points').first()
            if eligible_tier and membership.tier and eligible_tier.min_points > membership.tier.min_points:
                membership.tier = eligible_tier
                try:
                    from marketing.utils import create_unique_notification
                    create_unique_notification(
                        user=membership.user,
                        title=f"Chúc mừng bạn đã thăng hạng {eligible_tier.name}!",
                        content=f"Quý khách {membership.user.name} đã được nâng lên {eligible_tier.name} với chiết khấu {eligible_tier.discount_percent}%.",
                        prefix="TB-TIER",
                        delivery_channels='Web',
                        status='Đã gửi',
                        dedup_title_only=True,
                    )
                except Exception:
                    pass

        membership.save()

        try:
            from marketing.utils import create_unique_notification
            sign_char = '+' if points_delta > 0 else ''
            create_unique_notification(
                user=membership.user,
                title=f"Biến động điểm thưởng: {sign_char}{points_delta} điểm",
                content=f"Tài khoản của bạn vừa có giao dịch {action_text}. Lý do: {reason_desc}. Số dư mới: {membership.current_points} điểm.",
                prefix="TB-ADJ",
                delivery_channels='Web',
                status='Đã gửi',
            )
        except Exception:
            pass

    messages.success(request, f"Đã thực hiện {action_text} thành công cho khách hàng {membership.user.name}.")
    return redirect('membership:staff_lookup')


def _handle_update_tier_post(request):
    """Xử lý form POST cập nhật hạng thẻ VIP thủ công."""
    mid_raw = (request.POST.get('membership_id') or '').strip()
    tid_raw = (request.POST.get('tier_id') or '').strip()

    membership = Membership.objects.select_related('user', 'tier').filter(id=int(mid_raw)).first() if mid_raw.isdigit() else None
    if not membership:
        messages.error(request, "Không tìm thấy thẻ hội viên.")
        return redirect('membership:staff_lookup')

    tier = Tier.objects.filter(id=int(tid_raw)).first() if tid_raw.isdigit() else None
    if not tier:
        messages.error(request, "Không tìm thấy hạng thẻ hợp lệ.")
        return redirect('membership:staff_lookup')

    reason = str(request.POST.get('reason_description') or '').strip()
    membership.tier = tier
    membership.save(update_fields=['tier'])

    try:
        from marketing.utils import create_unique_notification
        create_unique_notification(
            user=membership.user,
            title=f"Hạng thẻ VIP của bạn đã được cập nhật thành {tier.name}!",
            content=(
                f"Quý khách {membership.user.name} đã được đại diện Spa cập nhật lên hạng {tier.name}. "
                f"Đặc quyền giảm {tier.discount_percent}% cho các dịch vụ tại Cham Spa."
                + (f" Ghi chú: {reason}" if reason else "")
            ),
            prefix="TB-TIER-MANUAL",
            delivery_channels='Web',
            status='Đã gửi',
        )
    except Exception:
        pass

    messages.success(
        request,
        f"Đã cập nhật hạng thẻ của {membership.user.name} sang {tier.name} (Chiết khấu {tier.discount_percent}%)."
    )
    return redirect('membership:staff_lookup')


@login_required
def staff_membership_lookup_view(request):
    """
    Giao diện Tra cứu Hội viên tại Quầy Lễ Tân & Quản lý Thẻ VIP toàn Spa:
    - Ô tra cứu nhanh theo Số điện thoại / Tên / Email với Live search.
    - Thẻ tóm tắt thông tin hội viên & % chiết khấu đặc quyền áp dụng ngay khi thanh toán.
    - 4 Widget KPI: Tổng số hội viên, Hội viên Bạc, Hội viên Vàng, Hội viên Kim Cương.
    - Bảng danh sách hội viên phân trang, lọc theo hạng thẻ.
    - Modal Cộng điểm thưởng thủ công & Thay đổi hạng thẻ VIP (Form POST).
    """
    user = request.user

    # Kiểm tra phân quyền: Chỉ Nhân viên (Staff) hoặc Quản lý (Admin) mới được truy cập
    if not (user.is_staff or user.is_superuser):
        if request.method == 'POST':
            raise PermissionDenied("Bạn không có quyền điều chỉnh điểm hoặc hạng thẻ hội viên.")
        messages.warning(request, "Bạn không có quyền truy cập trang quản lý hội viên nội bộ.")
        return redirect('membership:my_card')

    if request.method == 'POST':
        form_action = (request.POST.get('form_action') or '').strip()
        if form_action == 'adjust_points':
            return _handle_adjust_points_post(request)
        if form_action == 'update_tier':
            return _handle_update_tier_post(request)
        messages.error(request, "Thao tác không hợp lệ.")
        return redirect('membership:staff_lookup')

    base_layout = 'layouts/admin_layout.html' if user.is_superuser else 'layouts/staff_layout.html'

    # 1. Thống kê KPI toàn hệ thống
    total_members = Membership.objects.count()
    silver_count = Membership.objects.filter(tier__name__icontains='Bạc').count()
    gold_count = Membership.objects.filter(tier__name__icontains='Vàng').count()
    diamond_count = Membership.objects.filter(tier__name__icontains='Kim Cương').count()

    total_points_issued = Membership.objects.aggregate(total=Sum('current_points'))['total'] or 0
    total_revenue_members = Membership.objects.aggregate(total=Sum('total_spent'))['total'] or Decimal(0)
    formatted_total_revenue = f"{int(total_revenue_members):,}".replace(',', '.') + " VNĐ"

    # 2. Truy vấn danh sách Hội viên
    members_qs = Membership.objects.select_related(
        'user', 'tier', 'user__profile'
    ).prefetch_related('point_history').order_by('-current_points')

    # Bộ lọc theo Hạng thẻ
    tier_filter = request.GET.get('tier', 'all')
    if tier_filter != 'all' and tier_filter.isdigit():
        members_qs = members_qs.filter(tier_id=int(tier_filter))

    # Tìm kiếm theo SĐT, Tên, Email hoặc Mã
    search_query = request.GET.get('q', '').strip()
    if search_query:
        clean_p = search_query.replace(' ', '').replace('.', '').replace('-', '')
        q_obj = (
            Q(user__phone__icontains=clean_p) |
            Q(user__name__icontains=search_query) |
            Q(user__email__icontains=search_query)
        )
        if search_query.upper().startswith('CUS') and search_query[3:].isdigit():
            q_obj |= Q(user__id=int(search_query[3:]))
        members_qs = members_qs.filter(q_obj)

    # Phân trang (10 hội viên / trang)
    paginator = Paginator(members_qs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Danh sách tất cả các hạng thẻ cho Dropdown lọc và Modal
    all_tiers = Tier.objects.all().order_by('min_points')

    context = {
        'base_layout': base_layout,
        'total_members': total_members,
        'silver_count': silver_count,
        'gold_count': gold_count,
        'diamond_count': diamond_count,
        'total_points_issued': f"{total_points_issued:,}".replace(',', '.'),
        'formatted_total_revenue': formatted_total_revenue,
        'members': page_obj,
        'all_tiers': all_tiers,
        'tier_filter': tier_filter,
        'search_query': search_query,
    }
    return render(request, 'membership/staff_lookup.html', context)
