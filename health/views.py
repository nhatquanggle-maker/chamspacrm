"""
================================================================================
VIEWS GIAO DIỆN CHO PHÂN HỆ QUẢN LÝ HỒ SƠ SỨC KHỎE (MOD-08) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc (Meo)
Triển khai giao diện chuẩn Figma:
  - Node 273:2545: Giao diện xem hồ sơ sức khỏe cá nhân & Cảnh báo an toàn y tế
  - Node 273:2839: Giao diện cập nhật / khảo sát thể trạng sức khỏe Body Map
  - Màn hình Tra cứu & Xem Hồ sơ sức khỏe Khách hàng dành cho Staff Workspace
================================================================================
"""

import json
from datetime import datetime
from urllib.parse import quote, urlencode
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator

from core.models import UserHealthProfile, User, Appointment, Tier, Membership, UserProfile
from accounts.forms import validate_account_payload, parse_optional_date
from .helpers import generate_unique_health_code, serialize_health_profile, validate_health_payload


def is_staff_or_superuser(user):
    """Kiểm tra quyền Nhân viên hoặc Quản trị viên"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def format_metric_value(val):
    """Định dạng số đo Chiều cao / Cân nặng đẹp mắt, loại bỏ .00 hoặc ,00 thừa"""
    if val is None:
        return ""
    try:
        f = float(val)
        return str(int(f)) if f.is_integer() else f"{f:.1f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return str(val)


@login_required
def my_health_profile_view(request):
    """
    [MOD-08 - UC-8.2 & Figma Node 273:2575]
    Màn hình Xem Hồ sơ sức khỏe cá nhân dành cho Khách hàng (và Nhân viên).
    Hiển thị thông tin sinh trắc học, chỉ số BMI, mức độ đau mỏi,
    lực massage ưa chuộng và các mục tiêu trị liệu.
    """
    user = request.user

    # Xác định Master Layout phù hợp với vai trò của tài khoản
    if user.is_superuser:
        base_layout = 'layouts/admin_layout.html'
    elif user.is_staff:
        base_layout = 'layouts/staff_layout.html'
    else:
        base_layout = 'layouts/customer_layout.html'

    # Lấy hồ sơ sức khỏe quan hệ 1-1
    profile = UserHealthProfile.objects.filter(user=user).first()

    profile_data = None
    height_display = ""
    weight_display = ""
    if profile:
        profile_data = serialize_health_profile(profile)
        height_display = format_metric_value(profile.height_cm)
        weight_display = format_metric_value(profile.weight_kg)

    context = {
        'page_title': 'Hồ sơ sức khỏe cá nhân',
        'base_layout': base_layout,
        'profile': profile,
        'profile_data': profile_data,
        'has_profile': bool(profile),
        'height_display': height_display,
        'weight_display': weight_display,
        'now': timezone.now(),
    }

    return render(request, 'health/profile_view.html', context)


@login_required
def health_profile_update_view(request):
    """
    [MOD-08 - UC-8.1 & Figma Node 273:2839]
    Màn hình Khảo sát / Cập nhật Hồ sơ sức khỏe cá nhân (Chuẩn 1-1 tối giản).
    Tự động điền sẵn 100% dữ liệu cũ để khách hàng có thể chỉnh sửa lại dễ dàng.
    """
    user = request.user

    if user.is_superuser:
        base_layout = 'layouts/admin_layout.html'
    elif user.is_staff:
        base_layout = 'layouts/staff_layout.html'
    else:
        base_layout = 'layouts/customer_layout.html'

    # Lấy hồ sơ hiện tại để nạp sẵn dữ liệu lên form (nếu có)
    profile = UserHealthProfile.objects.filter(user=user).first()

    # Xử lý khi người dùng submit qua Form POST truyền thống
    if request.method == 'POST':
        target_user = user
        target_uid = request.POST.get('user_id')
        if target_uid and is_staff_or_superuser(user):
            target_user = get_object_or_404(User, id=target_uid)
            profile = UserHealthProfile.objects.filter(user=target_user).first()

        payload = {
            'height_cm': request.POST.get('height_cm'),
            'weight_kg': request.POST.get('weight_kg'),
            'blood_pressure': request.POST.get('blood_pressure', 'Bình thường'),
            'massage_pressure': request.POST.get('massage_pressure', 'Lực vừa'),
            'pain_level': request.POST.get('pain_level', '5'),
            'allergy_notes': '',
            'special_requests': request.POST.get('special_requests', ''),
            'focus_areas': request.POST.getlist('focus_areas'),
            'health_conditions': [],
            'recovery_goals': request.POST.getlist('recovery_goals'),
        }
        cleaned, errors = validate_health_payload(payload)
        if errors:
            messages.error(request, next(iter(errors.values())))
            return redirect('health:update')

        try:
            with transaction.atomic():
                if profile:
                    for field, val in cleaned.items():
                        setattr(profile, field, val)
                    profile.save()
                    messages.success(request, "Cập nhật hồ sơ sức khỏe thành công! Dữ liệu đã được lưu an toàn.")
                else:
                    profile = UserHealthProfile.objects.create(
                        user=target_user,
                        health_code=generate_unique_health_code(target_user),
                        **cleaned,
                    )
                    messages.success(request, "Tạo mới hồ sơ sức khỏe thành công!")
                return redirect('health:profile')
        except Exception as e:
            messages.error(request, f"Lỗi khi lưu hồ sơ sức khỏe: {str(e)}")
            return redirect('health:update')

    profile_data = None
    height_display = ""
    weight_display = ""
    if profile:
        profile_data = serialize_health_profile(profile)
        height_display = format_metric_value(profile.height_cm)
        weight_display = format_metric_value(profile.weight_kg)

    # Danh sách mục tiêu trị liệu tiêu chuẩn, gộp cùng mục tiêu hiện có của khách
    standard_recovery_goals = [
        "Giảm đau vai gáy",
        "Thư giãn ngủ ngon",
        "Giải tỏa căng thẳng",
        "Cải thiện tuần hoàn",
        "Phục hồi cơ bắp & Thải độc",
    ]
    user_goals = list(profile.recovery_goals or []) if profile else []
    all_goals = list(standard_recovery_goals)
    for g in user_goals:
        if g and g not in all_goals:
            all_goals.append(g)

    # Chuẩn hóa lực massage
    raw_pressure = profile.massage_pressure if profile else "Lực vừa"
    if not raw_pressure:
        current_pressure = "Lực vừa"
    elif "nhẹ" in raw_pressure.lower():
        current_pressure = "Nhẹ nhàng"
    elif "mạnh" in raw_pressure.lower():
        current_pressure = "Lực mạnh"
    else:
        current_pressure = "Lực vừa"

    current_bp = profile.blood_pressure if (profile and profile.blood_pressure) else "Bình thường"
    current_pain = profile.pain_level if (profile and profile.pain_level is not None) else 5

    context = {
        'page_title': 'Khảo sát thể trạng & Cập nhật hồ sơ sức khỏe',
        'base_layout': base_layout,
        'profile': profile,
        'profile_data': profile_data,
        'has_profile': bool(profile),
        'height_display': height_display,
        'weight_display': weight_display,
        'standard_recovery_goals': all_goals,
        'current_pressure': current_pressure,
        'current_bp': current_bp,
        'current_pain': current_pain,
    }

    return render(request, 'health/profile_form.html', context)


@login_required
def staff_health_lookup_view(request):
    """
    [MOD-08 - Mở rộng cho Staff Workspace & Figma Node 273:2545]
    Màn hình Quản lý & Tra cứu Hồ sơ sức khỏe Khách hàng dành cho Nhân viên Lễ tân,
    Tư vấn viên CSKH và Kỹ thuật viên (KTV).
    Cho phép:
      - Tìm kiếm theo SĐT, Tên khách hàng, Mã hồ sơ sức khỏe.
      - Phân loại nhanh các hồ sơ theo tình trạng Huyết áp (Bình thường, Thấp, Cao).
      - Xem nhanh thể trạng khách trước ca trực để bảo đảm an toàn trị liệu.
    """
    if not is_staff_or_superuser(request.user):
        messages.error(request, "Bạn không có quyền truy cập vào màn hình Quản lý sức khỏe của nhân viên.")
        return redirect('home')

    base_layout = 'layouts/admin_layout.html' if request.user.is_superuser else 'layouts/staff_layout.html'

    # Xử lý Staff thêm mới tài khoản khách hàng
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_customer':
            password = request.POST.get('password', '').strip() or 'customer123456'
            gender = request.POST.get('gender', 'Nữ')
            tier_name = request.POST.get('tier_name', 'Thành viên')
            care_note = request.POST.get('care_note', '').strip()

            validated, err = validate_account_payload(
                request.POST.get('name'),
                request.POST.get('phone'),
                request.POST.get('email'),
                is_staff_or_admin=False,
                require_email=True,
            )
            bday, date_err = parse_optional_date(request.POST.get('birthday'))

            if err or date_err:
                messages.error(request, err or date_err)
            else:
                new_user = User.objects.create_user(
                    username=validated['phone'],
                    name=validated['name'],
                    phone=validated['phone'],
                    email=validated['email'],
                    password=password,
                    is_staff=False,
                    is_superuser=False,
                    is_active=True
                )
                profile, _ = UserProfile.objects.get_or_create(user=new_user)
                profile.gender = gender
                profile.birthday = bday
                profile.save()
                tier_obj = Tier.objects.filter(name=tier_name).first() or Tier.objects.first()
                mem, _ = Membership.objects.get_or_create(user=new_user)
                mem.tier = tier_obj
                mem.current_points = tier_obj.min_points if tier_obj else 0
                mem.save()

                hp, _ = UserHealthProfile.objects.get_or_create(
                    user=new_user,
                    defaults={'health_code': f"HS-{new_user.id:04d}"}
                )
                if care_note:
                    hp.special_requests = care_note
                    hp.save()
                messages.success(request, f"Đã thêm thành công tài khoản khách hàng {new_user.name} (#{new_user.id:03d})!")
            return redirect('health:staff_lookup')

    # Tìm kiếm
    query = request.GET.get('q', '').strip()
    filter_bp = request.GET.get('bp', '').strip()

    profiles_qs = UserHealthProfile.objects.select_related('user').order_by('-created_at')

    if query:
        profiles_qs = profiles_qs.filter(
            Q(health_code__icontains=query) |
            Q(user__name__icontains=query) |
            Q(user__phone__icontains=query) |
            Q(user__email__icontains=query)
        )

    # Thống kê nhanh
    total_profiles = UserHealthProfile.objects.count()
    all_profiles_list = []

    for p in profiles_qs:
        p_data = serialize_health_profile(p)
        normalized_bp = p.blood_pressure if p.blood_pressure in ('Cao', 'Thấp') else 'Bình thường'

        if filter_bp in ('Bình thường', 'Thấp', 'Cao') and normalized_bp != filter_bp:
            continue

        all_profiles_list.append({
            'obj': p,
            'data': p_data,
        })

    # Phân trang chuẩn 7 hồ sơ mỗi trang
    paginator = Paginator(all_profiles_list, 7)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    page_range = list(paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1))

    params = {}
    if query:
        params['q'] = query
    if filter_bp:
        params['bp'] = filter_bp
    pagination_prefix = f"?{urlencode(params, quote_via=quote)}&" if params else "?"

    tiers = Tier.objects.all().order_by('min_points')

    context = {
        'page_title': 'Quản lý & Tra cứu Hồ sơ sức khỏe khách hàng (Staff Workspace)',
        'base_layout': base_layout,
        'query': query,
        'filter_bp': filter_bp,
        'total_profiles': total_profiles,
        'profiles_list': page_obj,
        'page_obj': page_obj,
        'page_range': page_range,
        'ellipsis_label': paginator.ELLIPSIS,
        'pagination_prefix': pagination_prefix,
        'tiers': tiers,
    }

    return render(request, 'health/staff_lookup.html', context)


@login_required
def staff_customer_health_detail_view(request, user_id):
    """
    [MOD-08 & MOD-05] Chi tiết hồ sơ khách hàng 360 độ đầy đủ 3 Tab cho Nhân viên & Admin:
      - Tab 1 (Figma Node 221:481): Thông tin cá nhân & Liên hệ
      - Tab 2 (Figma Node 608:1773): Hồ sơ sức khỏe
      - Tab 3 (Figma Node 608:250): Thẻ hội viên & Tích điểm
    Đồng thời hỗ trợ hiển thị giao diện chuyên biệt cho KTV in phiếu khi có tham số ?view=ktv hoặc ?standalone=1.
    """
    if not is_staff_or_superuser(request.user):
        messages.error(request, "Bạn không có quyền truy cập hồ sơ sức khỏe khách hàng này.")
        return redirect('home')

    # Nếu KTV yêu cầu xem bản in phiếu hồ sơ y tế chuyên sâu (Figma Node 279:1633)
    if request.GET.get('view') in ['ktv', 'standalone', 'print']:
        base_layout = 'layouts/admin_layout.html' if request.user.is_superuser else 'layouts/staff_layout.html'
        customer = get_object_or_404(User, id=user_id)
        profile = UserHealthProfile.objects.filter(user=customer).first()

        profile_data = None
        height_display = ""
        weight_display = ""
        if profile:
            profile_data = serialize_health_profile(profile)
            height_display = format_metric_value(profile.height_cm)
            weight_display = format_metric_value(profile.weight_kg)

        recent_appointments = (
            Appointment.objects.filter(user=customer)
            .prefetch_related('details__service')
            .order_by('-appointment_date', '-time_slot')[:5]
        )

        context = {
            'page_title': f'Hồ sơ sức khỏe: {customer.name or customer.username}',
            'base_layout': base_layout,
            'customer': customer,
            'profile': profile,
            'profile_data': profile_data,
            'has_profile': bool(profile),
            'height_display': height_display,
            'weight_display': weight_display,
            'recent_appointments': recent_appointments,
        }
        return render(request, 'health/staff_detail.html', context)

    active_tab = request.GET.get('tab', 'health')
    return redirect(f"{reverse('accounts:admin_customer_detail', kwargs={'pk': user_id})}?tab={active_tab}")
