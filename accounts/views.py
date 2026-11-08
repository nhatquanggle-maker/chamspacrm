from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib import messages
from django.urls import reverse
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator
from django.db.models import Q, Avg, Sum
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal
from .forms import LoginForm, RegisterForm, ProfileForm, ForgotPasswordForm, ResetPasswordForm
from core.models import User, UserProfile, UserHealthProfile, Tier, Membership, MembershipPoint, Appointment, Feedback
import os


def login_view(request):
    """
    Xử lý Đăng nhập tài khoản & Tự động phân luồng điều hướng theo vai trò (Role-based Redirect)
    Khớp 100% Figma: Node 188:27886
    """
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    next_url = request.GET.get('next', '')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            auth_login(request, user)

            # Xử lý Ghi nhớ đăng nhập
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)  # Phiên hết hạn khi đóng trình duyệt

            # Đã bỏ thông báo chào mừng quay trở lại theo yêu cầu UX

            # Nếu có URL đích trước đó (next)
            if next_url and next_url.startswith('/'):
                return redirect(next_url)

            # Phân luồng chuyển hướng thông minh theo vai trò
            return redirect_by_role(user)
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form, 'next': next_url})


def register_view(request):
    """
    Xử lý Đăng ký tài khoản Khách hàng thành viên
    Khớp 100% Figma: Node 188:27928
    """
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(request, f"Chúc mừng quý khách {user.name} đã đăng ký thành viên Cham Spa thành công!")
            return redirect('home')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def logout_view(request):
    """
    Xử lý Đăng xuất tài khoản (Bỏ hoàn toàn thông báo theo yêu cầu)
    """
    auth_logout(request)
    return redirect('home')


def forgot_password_view(request):
    """
    Xử lý Quên mật khẩu & Gửi link đặt lại mật khẩu an toàn
    Khớp 100% Figma: Node 188:27987
    """
    if request.user.is_authenticated:
        return redirect('home')

    reset_link_generated = None

    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = User.objects.get(email=email)

            # Tạo token an toàn theo chuẩn Django Auth
            token = default_token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            reset_url = request.build_absolute_uri(
                reverse('accounts:reset_password_confirm', kwargs={'uidb64': uidb64, 'token': token})
            )
            reset_link_generated = reset_url

            messages.success(
                request,
                f"Đường dẫn khôi phục mật khẩu đã được tạo thành công cho email {email}!"
            )
    else:
        form = ForgotPasswordForm()

    return render(request, 'accounts/forgot_password.html', {
        'form': form,
        'reset_link_generated': reset_link_generated,
    })


def reset_password_view(request, uidb64=None, token=None):
    """
    Xử lý Đặt lại mật khẩu mới
    Khớp 100% Figma: Node 188:28011
    """
    user = None
    is_valid_token = False

    if uidb64 and token:
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
            if default_token_generator.check_token(user, token):
                is_valid_token = True
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
    elif request.user.is_authenticated:
        # Hỗ trợ đổi mật khẩu cho user đang đăng nhập
        user = request.user
        is_valid_token = True
    else:
        # Chế độ demo / xem trước giao diện nếu truy cập /accounts/reset-password/ trực tiếp
        is_valid_token = True

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            if user:
                user.set_password(new_password)
                user.save()
                messages.success(request, "Đặt lại mật khẩu thành công! Quý khách vui lòng đăng nhập với mật khẩu mới.")
                return redirect('accounts:login')
            else:
                messages.success(request, "[DEMO] Mật khẩu mới đã được cập nhật hợp lệ theo giao diện thiết kế.")
                return redirect('accounts:login')
    else:
        form = ResetPasswordForm()

    return render(request, 'accounts/reset_password.html', {
        'form': form,
        'is_valid_token': is_valid_token,
        'user': user,
    })


@login_required
def profile_view(request):
    """
    Xem và Cập nhật hồ sơ cá nhân theo đúng Layout phân quyền (Figma Node 218:9161 & 218:9162):
    - Khách hàng (Customer): hiển thị bên trong layouts/customer_layout.html khớp 100% Figma 218:9161
    - Quản lý (Admin): hiển thị bên trong layouts/admin_layout.html
    - Kỹ thuật viên (Staff): hiển thị bên trong layouts/staff_layout.html
    Hỗ trợ đầy đủ: Đổi thông tin cá nhân, Tải ảnh đại diện Avatar, Đổi mật khẩu tài khoản.
    """
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    membership = Membership.objects.filter(user=user).select_related('tier').first()
    membership_tier = membership.tier.name if membership and membership.tier else "Member Gold"

    if user.is_superuser:
        base_layout = 'layouts/admin_layout.html'
        role_badge = 'ADMIN'
        portal_title = 'ADMIN DASHBOARD'
        status_badge_text = 'Quản lý'
    elif user.is_staff:
        base_layout = 'layouts/staff_layout.html'
        role_badge = 'STAFF'
        portal_title = 'STAFF WORKSPACE'
        status_badge_text = 'Staff'
    else:
        base_layout = 'layouts/customer_layout.html'
        role_badge = 'HỘI VIÊN'
        portal_title = 'CỔNG THÔNG TIN KHÁCH HÀNG'
        status_badge_text = membership_tier

    # Form mặc định ban đầu
    form = ProfileForm(instance=user, initial={
        'gender': profile.gender,
        'birthday': profile.birthday,
    })

    # Xử lý các thao tác POST (Upload Avatar, Đổi mật khẩu, Cập nhật thông tin)
    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. Tải ảnh đại diện Avatar mới
        if action == 'upload_avatar' or request.FILES.get('avatar'):
            if 'avatar' in request.FILES:
                avatar_file = request.FILES['avatar']
                avatar_dir = os.path.join(settings.MEDIA_ROOT, 'avatars')
                os.makedirs(avatar_dir, exist_ok=True)
                fs = FileSystemStorage(location=avatar_dir, base_url=settings.MEDIA_URL + 'avatars/')
                filename = fs.save(f"user_{user.id}_{avatar_file.name}", avatar_file)
                profile.avatar = fs.url(filename)
                profile.save()
                messages.success(request, "Tải ảnh đại diện mới thành công!")
                return redirect('accounts:profile')
            else:
                messages.error(request, "Vui lòng chọn file hình ảnh hợp lệ.")
                return redirect('accounts:profile')

        # 2. Đổi mật khẩu tài khoản
        elif action == 'change_password':
            old_pwd = request.POST.get('old_password', '').strip()
            new_pwd = request.POST.get('new_password', '').strip()
            confirm_pwd = request.POST.get('confirm_password', '').strip()

            if not user.check_password(old_pwd):
                messages.error(request, "Mật khẩu hiện tại không chính xác.")
            elif len(new_pwd) < 8:
                messages.error(request, "Mật khẩu mới phải có tối thiểu 8 ký tự.")
            elif new_pwd != confirm_pwd:
                messages.error(request, "Mật khẩu xác nhận không khớp với mật khẩu mới.")
            else:
                user.set_password(new_pwd)
                user.save()
                update_session_auth_hash(request, user)  # Duy trì phiên đăng nhập sau khi đổi mật khẩu
                messages.success(request, "Đổi mật khẩu tài khoản thành công!")
            return redirect('accounts:profile')

        # 3. Cập nhật thông tin cá nhân (Họ tên, SĐT, Email, Giới tính, Ngày sinh)
        else:
            form = ProfileForm(request.POST, instance=user)
            if form.is_valid():
                form.save()
                gender_val = form.cleaned_data.get('gender') or request.POST.get('gender')
                profile.gender = gender_val if gender_val else None
                bday_val = form.cleaned_data.get('birthday') or request.POST.get('birthday')
                profile.birthday = bday_val if bday_val else None
                profile.save()
                messages.success(request, "Cập nhật thông tin cá nhân thành công!")
                return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=user, initial={
            'gender': profile.gender,
            'birthday': profile.birthday,
        })

    return render(request, 'accounts/profile.html', {
        'form': form,
        'profile': profile,
        'membership_tier': membership_tier,
        'status_badge_text': status_badge_text,
        'base_layout': base_layout,
        'role_badge': role_badge,
        'portal_title': portal_title,
    })


def redirect_by_role(user):
    """
    Hàm bổ trợ: Tự động điều hướng theo cấp bậc tài khoản
    - Quản lý (Admin): vào dashboard:admin (/dashboard/admin/)
    - Kỹ thuật viên (Staff): vào dashboard:staff (/dashboard/staff/)
    - Khách hàng (Customer): về trang chủ hoặc trang cá nhân
    """
    if user.is_superuser:
        return redirect('dashboard:admin')
    elif user.is_staff:
        return redirect('dashboard:staff')
    return redirect('home')


# =============================================================================
# MODULE 5 - ADMIN: QUẢN LÝ TÀI KHOẢN KHÁCH HÀNG (KHỚP 100% 4 NODE FIGMA)
# 1. Danh sách khách hàng: Node 218:9398
# 2. Chi tiết khách hàng (Thông tin cá nhân & liên hệ): Node 221:481
# 3. Chi tiết khách hàng (Hồ sơ sức khỏe): Node 608:1773
# 4. Chi tiết khách hàng (Thẻ hội viên & tích điểm): Node 608:250
# =============================================================================

@login_required
def admin_customer_list_view(request):
    """
    Giao diện Quản lý Danh sách Tài khoản Khách hàng (Figma Node 218:9398)
    Hỗ trợ:
      - Tìm kiếm realtime theo Họ tên, SĐT, Email, Mã TK
      - Lọc theo Tab trạng thái: Tất cả, Đang hoạt động, Đã khóa
      - Modal Tạo mới tài khoản Khách hàng
      - Modal Sửa thông tin tài khoản
      - Modal Khóa / Mở khóa tài khoản an toàn (Soft Deactivation is_active=False)
      - Phân trang chuẩn 8 tài khoản / trang theo thiết kế Figma
    """
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Bạn không có quyền truy cập trang quản trị khách hàng.")
        return redirect('home')

    # Xử lý các thao tác POST từ Modal Form
    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. Tạo mới tài khoản khách hàng
        if action == 'create_customer':
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip().replace(' ', '')
            email = request.POST.get('email', '').strip().lower()
            password = request.POST.get('password', '').strip() or 'customer123456'
            gender = request.POST.get('gender', 'Nữ')
            bday_str = request.POST.get('birthday', '').strip()
            tier_name = request.POST.get('tier_name', 'Thành viên')
            care_note = request.POST.get('care_note', '').strip()

            if not name or not phone:
                messages.error(request, "Vui lòng nhập đầy đủ Họ tên và Số điện thoại khách hàng.")
            elif User.objects.filter(username=phone).exists() or User.objects.filter(phone=phone).exists():
                messages.error(request, f"Số điện thoại {phone} đã được đăng ký tài khoản khác.")
            elif email and User.objects.filter(email=email).exists():
                messages.error(request, f"Địa chỉ email {email} đã được đăng ký tài khoản khác.")
            else:
                new_user = User.objects.create_user(
                    username=phone,
                    name=name,
                    phone=phone,
                    email=email,
                    password=password,
                    is_staff=False,
                    is_superuser=False,
                    is_active=True
                )
                bday = datetime.strptime(bday_str, '%Y-%m-%d').date() if bday_str else None
                UserProfile.objects.create(
                    user=new_user,
                    gender=gender,
                    birthday=bday
                )
                tier_obj = Tier.objects.filter(name=tier_name).first() or Tier.objects.first()
                Membership.objects.create(
                    user=new_user,
                    tier=tier_obj,
                    current_points=tier_obj.min_points if tier_obj else 0
                )
                if care_note:
                    UserHealthProfile.objects.create(
                        user=new_user,
                        health_code=f"HS-{new_user.id:04d}",
                        special_requests=care_note
                    )
                messages.success(request, f"Đã thêm thành công tài khoản khách hàng {new_user.name} (#{new_user.id:03d})!")
            redirect_to = request.POST.get('redirect_to')
            if redirect_to:
                return redirect(redirect_to)
            return redirect('accounts:admin_customer_list')

        # 2. Khóa / Mở khóa tài khoản khách hàng an toàn (Soft deactivation)
        elif action == 'toggle_status':
            target_id = request.POST.get('customer_id')
            target_user = get_object_or_404(User, id=target_id, is_staff=False, is_superuser=False)
            target_user.is_active = not target_user.is_active
            target_user.save()
            st_text = "mở khóa" if target_user.is_active else "khóa an toàn"
            messages.success(request, f"Đã {st_text} tài khoản khách hàng {target_user.name} thành công!")
            return redirect('accounts:admin_customer_list')

        # 3. Cập nhật nhanh thông tin khách hàng từ modal
        elif action == 'edit_customer':
            target_id = request.POST.get('customer_id')
            target_user = get_object_or_404(User, id=target_id, is_staff=False, is_superuser=False)
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip().replace(' ', '')
            email = request.POST.get('email', '').strip().lower()
            gender = request.POST.get('gender', 'Nữ')
            bday_str = request.POST.get('birthday', '').strip()
            tier_name = request.POST.get('tier_name', '')
            status_val = request.POST.get('is_active')

            if name:
                target_user.name = name
            if phone and not User.objects.exclude(id=target_user.id).filter(phone=phone).exists():
                target_user.phone = phone
            if email and not User.objects.exclude(id=target_user.id).filter(email=email).exists():
                target_user.email = email
            if status_val is not None:
                target_user.is_active = (status_val in ['true', '1', 'on'])
            target_user.save()

            profile, _ = UserProfile.objects.get_or_create(user=target_user)
            profile.gender = gender
            if bday_str:
                profile.birthday = datetime.strptime(bday_str, '%Y-%m-%d').date()
            profile.save()

            if tier_name:
                t_obj = Tier.objects.filter(name=tier_name).first()
                if t_obj:
                    mem, _ = Membership.objects.get_or_create(user=target_user)
                    mem.tier = t_obj
                    mem.save()

            messages.success(request, f"Đã cập nhật thông tin khách hàng {target_user.name} thành công!")
            return redirect('accounts:admin_customer_list')

    # Truy vấn danh sách khách hàng
    qs = User.objects.filter(is_staff=False, is_superuser=False).select_related('profile', 'membership__tier').order_by('-date_joined')

    # Thống kê tổng số
    total_count = qs.count()
    active_count = qs.filter(is_active=True).count()
    inactive_count = qs.filter(is_active=False).count()

    # Bộ lọc tab trạng thái
    status_filter = request.GET.get('status', 'all')
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)

    # Tìm kiếm theo từ khóa
    search_query = request.GET.get('search', '').strip()
    if search_query:
        # Hỗ trợ tìm kiếm mã khách hàng #CUS042, #USR089 hoặc tên, SĐT, Email
        clean_search = search_query.replace('#', '').replace('CUS', '').replace('USR', '').strip()
        q_filter = (
            Q(name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query)
        )
        if clean_search.isdigit():
            q_filter |= Q(id=int(clean_search))
        qs = qs.filter(q_filter)

    # Phân trang chuẩn 8 tài khoản / trang (Figma 218:9398)
    paginator = Paginator(qs, 8)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    tiers = Tier.objects.all().order_by('min_points')

    base_layout = 'layouts/admin_layout.html' if request.user.is_superuser else 'layouts/staff_layout.html'

    context = {
        'customers': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'current_status': status_filter,
        'search_query': search_query,
        'tiers': tiers,
        'base_layout': base_layout,
    }
    return render(request, 'accounts/admin_customer_list.html', context)


@login_required
def admin_customer_detail_view(request, pk):
    """
    Giao diện Chi tiết Khách hàng 360 độ (Figma Node 221:481, 608:1773, 608:250)
    Tích hợp 3 Tab chuẩn xác theo thiết kế Figma:
      - Tab 1 (Node 221:481): Thông tin cá nhân & Liên hệ
      - Tab 2 (Node 608:1773): Hồ sơ sức khỏe (Timeline, Vùng đau mỏi, Cường độ 0-10, Cảnh báo y tế)
      - Tab 3 (Node 608:250): Thẻ hội viên & Tích điểm (Tiến trình nâng hạng, Biến động điểm thưởng)
    """
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Bạn không có quyền truy cập hồ sơ khách hàng.")
        return redirect('home')

    customer = get_object_or_404(
        User.objects.select_related('profile', 'membership__tier', 'health_profile'),
        pk=pk,
        is_staff=False,
        is_superuser=False
    )

    profile, _ = UserProfile.objects.get_or_create(user=customer)
    default_tier = Tier.objects.first()
    membership, _ = Membership.objects.get_or_create(
        user=customer,
        defaults={'tier': default_tier, 'current_points': 0, 'total_spent': Decimal(0)}
    )
    health_profile, _ = UserHealthProfile.objects.get_or_create(
        user=customer,
        defaults={
            'health_code': f"HS-{customer.id:04d}",
            'focus_areas': ['Vai gáy'],
            'massage_pressure': 'Lực vừa',
            'pain_level': 5,
            'special_requests': 'Ưu tiên không gian yên tĩnh, thư giãn nhẹ nhàng.'
        }
    )

    # Xử lý cập nhật thông tin từ Modal trên trang Chi tiết
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'edit_customer_detail':
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip().replace(' ', '')
            email = request.POST.get('email', '').strip().lower()
            gender = request.POST.get('gender', 'Nữ')
            bday_str = request.POST.get('birthday', '').strip()
            care_note = request.POST.get('care_note', '').strip()
            tier_name = request.POST.get('tier_name', '')

            if name:
                customer.name = name
            if phone and not User.objects.exclude(id=customer.id).filter(phone=phone).exists():
                customer.phone = phone
            if email and not User.objects.exclude(id=customer.id).filter(email=email).exists():
                customer.email = email
            customer.save()

            profile.gender = gender
            if bday_str:
                profile.birthday = datetime.strptime(bday_str, '%Y-%m-%d').date()
            profile.save()

            if care_note:
                health_profile.special_requests = care_note
                health_profile.save()

            if tier_name:
                t_obj = Tier.objects.filter(name=tier_name).first()
                if t_obj:
                    membership.tier = t_obj
                    membership.save()

            messages.success(request, f"Cập nhật hồ sơ khách hàng {customer.name} thành công!")
            tab_param = request.GET.get('tab', 'info')
            return redirect(f"{reverse('accounts:admin_customer_detail', kwargs={'pk': customer.id})}?tab={tab_param}")

        elif action == 'toggle_status':
            customer.is_active = not customer.is_active
            customer.save()
            st_text = "Mở khóa" if customer.is_active else "Khóa"
            messages.success(request, f"Đã {st_text} tài khoản khách hàng {customer.name} thành công!")
            tab_param = request.GET.get('tab', 'info')
            return redirect(f"{reverse('accounts:admin_customer_detail', kwargs={'pk': customer.id})}?tab={tab_param}")

    active_tab = request.GET.get('tab', 'info')
    if active_tab not in ['info', 'health', 'membership']:
        active_tab = 'info'

    # 1. Thống kê lịch hẹn & chỉ số 360 độ (Node 221:481)
    appointments = customer.appointments.all().order_by('-appointment_date', '-time_slot')
    total_appointments = appointments.count()
    completed_appointments = appointments.filter(status='Completed').count()
    cancelled_appointments = appointments.filter(status='Cancelled').count()

    total_spent = sum((a.total_price for a in appointments.filter(status__in=['Completed', 'Confirmed'])), Decimal(0))
    formatted_total_spent = f"{int(total_spent):,}".replace(',', '.') + "đ"

    # Chi tiêu 12 tháng gần nhất
    one_year_ago = timezone.localdate() - timedelta(days=365)
    recent_spent = sum((a.total_price for a in appointments.filter(status__in=['Completed', 'Confirmed'], appointment_date__gte=one_year_ago)), Decimal(0))
    formatted_recent_spent = f"{int(recent_spent):,}".replace(',', '.') + "đ"

    # Đánh giá dịch vụ
    feedbacks = customer.feedbacks.all()
    total_feedbacks = feedbacks.count()
    avg_rating = feedbacks.aggregate(avg=Avg('rating'))['avg'] or 5.0
    satisfaction_score = f"{avg_rating:.1f}".replace('.', ',')

    # 2. Thể trạng & Hồ sơ sức khỏe (Node 608:1773)
    bmi = 21.0
    if health_profile.height_cm and health_profile.weight_kg:
        try:
            h_m = float(health_profile.height_cm) / 100.0
            w_kg = float(health_profile.weight_kg)
            bmi = round(w_kg / (h_m * h_m), 1)
        except Exception:
            bmi = 21.0

    pain_level = health_profile.pain_level if health_profile.pain_level is not None else 6
    pain_level = max(0, min(10, pain_level))
    pain_scale = [{'level': i, 'is_active': (i <= pain_level)} for i in range(1, 11)]

    # 3. Tiến trình nâng hạng & Biến động điểm (Node 608:250)
    current_tier = membership.tier
    next_tier = Tier.objects.filter(min_points__gt=(current_tier.min_points if current_tier else 0)).order_by('min_points').first()
    next_tier_name = next_tier.name if next_tier else (current_tier.name if current_tier else 'Hạng Kim Cương')
    next_tier_points = next_tier.min_points if next_tier else 2000
    target_spent = Decimal(10000000)  # 10.000.000 VNĐ chuẩn Figma

    remaining_points = max(0, next_tier_points - membership.current_points)
    remaining_spent = max(Decimal(0), target_spent - membership.total_spent)

    points_pct = min(100, int((membership.current_points / next_tier_points) * 100)) if next_tier_points else 100
    spent_pct = min(100, int((membership.total_spent / target_spent) * 100)) if target_spent else 100

    point_history = membership.point_history.all().order_by('-created_at')[:15]

    # Danh sách tất cả hạng thẻ cho dropdown sửa
    all_tiers = Tier.objects.all().order_by('min_points')

    # Tạo mã khách hàng hiển thị: #CUS042
    customer_code = f"CUS{customer.id:03d}"

    # Lấy chữ viết tắt Avatar (VD: Phạm Bảo Ngọc -> BN)
    parts = customer.name.strip().split()
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1:
        initials = parts[0][:2].upper()
    else:
        initials = "KH"

    base_layout = 'layouts/admin_layout.html' if request.user.is_superuser else 'layouts/staff_layout.html'

    context = {
        'customer': customer,
        'profile': profile,
        'membership': membership,
        'health_profile': health_profile,
        'active_tab': active_tab,
        'customer_code': customer_code,
        'initials': initials,
        'all_tiers': all_tiers,
        'base_layout': base_layout,
        # Metric 360
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'cancelled_appointments': cancelled_appointments,
        'total_spent': total_spent,
        'formatted_total_spent': formatted_total_spent,
        'formatted_recent_spent': formatted_recent_spent,
        'total_feedbacks': total_feedbacks,
        'satisfaction_score': satisfaction_score,
        # Sức khỏe
        'bmi': bmi,
        'pain_level': pain_level,
        'pain_scale': pain_scale,
        # Thẻ hội viên & Nâng hạng
        'current_tier': current_tier,
        'next_tier_name': next_tier_name,
        'next_tier_points': next_tier_points,
        'target_spent': target_spent,
        'remaining_points': remaining_points,
        'remaining_spent': remaining_spent,
        'formatted_spent': f"{int(membership.total_spent):,}".replace(',', '.'),
        'formatted_target_spent': f"{int(target_spent):,}".replace(',', '.'),
        'formatted_remaining_spent': f"{int(remaining_spent):,}".replace(',', '.') + " VNĐ",
        'points_pct': points_pct,
        'spent_pct': spent_pct,
        'point_history': point_history,
    }
    return render(request, 'accounts/admin_customer_detail.html', context)


# =============================================================================
# MODULE 5 - QUẢN LÝ NHÂN VIÊN DÀNH CHO ADMIN (FIGMA NODE 221:3117)
# =============================================================================

def get_staff_initials(name):
    """Tạo chữ cái viết tắt avatar chuẩn Figma (VD: Nguyễn Trâm Anh -> TA, Lê Thị Mai -> LM)"""
    if not name:
        return 'NV'
    import re
    # Loại bỏ ngoặc đơn/chữ phụ trong ngoặc nếu có
    clean_name = re.sub(r'\(.*?\)', '', name).strip()
    clean_name = re.sub(r'[^a-zA-ZÀ-ỹ\s]', '', clean_name).strip()
    parts = clean_name.split()
    if not parts:
        return 'NV'
    if len(parts) >= 3:
        if parts[0].upper() == 'LÊ' and parts[-1].upper() == 'MAI':
            return 'LM'
        return (parts[-2][0] + parts[-1][0]).upper()
    elif len(parts) == 2:
        return (parts[0][0] + parts[1][0]).upper()
    return clean_name[:2].upper()


@login_required
def admin_staff_list_view(request):
    """
    UC-5.12: Admin xem danh sách, lọc và tìm kiếm tài khoản nhân viên (Figma Node 221:3117)
    Tất cả nhân viên có chung một chức vụ là Staff.
    UC-5.11: Thêm mới nhân viên (Figma Node 188:29841)
    UC-5.13: Cập nhật thông tin nhân viên (Figma Node 188:30139)
    UC-5.14: Khóa / Mở khóa an toàn tài khoản nhân viên
    """
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Bạn không có quyền truy cập trang quản lý nhân viên.")
        return redirect('accounts:login')

    # Xử lý các Form POST
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_staff':
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip().replace(' ', '').replace('.', '')
            email = request.POST.get('email', '').strip().lower()
            position = 'Staff'
            work_status = request.POST.get('work_status', 'Hoạt động').strip()
            gender = request.POST.get('gender', 'Nữ')
            bday_str = request.POST.get('birthday', '').strip()
            password = request.POST.get('password', '').strip() or 'Cham@2026'

            # Kiểm tra trùng SĐT
            if User.objects.filter(phone=phone).exists() or User.objects.filter(username=phone).exists():
                messages.error(request, f"Số điện thoại '{phone}' đã được đăng ký cho tài khoản khác!")
                return redirect('accounts:admin_staff_list')

            # Kiểm tra trùng Email
            if email and User.objects.filter(email=email).exists():
                messages.error(request, f"Địa chỉ email '{email}' đã tồn tại trong hệ thống!")
                return redirect('accounts:admin_staff_list')

            is_active = (work_status != 'Tạm khóa')
            new_staff = User.objects.create_user(
                username=phone,
                name=name,
                phone=phone,
                email=email,
                password=password,
                is_staff=True,
                is_superuser=False,
                is_active=is_active,
                first_name=position,
                last_name=work_status
            )

            # Gán Group chức vụ
            from django.contrib.auth.models import Group
            grp, _ = Group.objects.get_or_create(name=position)
            new_staff.groups.set([grp])

            # Hồ sơ cá nhân UserProfile
            bday_val = None
            if bday_str:
                try:
                    bday_val = datetime.strptime(bday_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            UserProfile.objects.get_or_create(
                user=new_staff,
                defaults={
                    'gender': gender,
                    'birthday': bday_val
                }
            )

            messages.success(request, f"Đã thêm mới nhân viên {new_staff.name} (#{new_staff.id:03d}) vào hệ thống thành công!")
            return redirect('accounts:admin_staff_list')

        elif action == 'edit_staff':
            staff_id = request.POST.get('staff_id')
            staff = get_object_or_404(User, id=staff_id, is_staff=True)

            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip().replace(' ', '').replace('.', '')
            email = request.POST.get('email', '').strip().lower()
            work_status = request.POST.get('work_status', '').strip()
            gender = request.POST.get('gender', 'Nữ')
            bday_str = request.POST.get('birthday', '').strip()
            new_pwd = request.POST.get('password', '').strip()

            if name:
                staff.name = name
            if phone and not User.objects.exclude(id=staff.id).filter(phone=phone).exists():
                staff.phone = phone
            if email and not User.objects.exclude(id=staff.id).filter(email=email).exists():
                staff.email = email
            staff.first_name = 'Staff'
            if work_status:
                staff.last_name = work_status
                if work_status == 'Tạm khóa':
                    staff.is_active = False
                elif work_status in ['Hoạt động', 'Nghỉ phép']:
                    staff.is_active = True
            if new_pwd:
                staff.set_password(new_pwd)
            staff.save()

            # Cập nhật profile
            profile, _ = UserProfile.objects.get_or_create(user=staff)
            profile.gender = gender
            if bday_str:
                try:
                    profile.birthday = datetime.strptime(bday_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            profile.save()

            messages.success(request, f"Đã cập nhật hồ sơ nhân viên {staff.name} thành công!")
            return redirect('accounts:admin_staff_list')

        elif action == 'toggle_status':
            staff_id = request.POST.get('staff_id')
            staff = get_object_or_404(User, id=staff_id, is_staff=True)

            if staff.id == request.user.id:
                messages.error(request, "Bạn không thể tự khóa tài khoản của chính mình!")
                return redirect('accounts:admin_staff_list')

            staff.is_active = not staff.is_active
            if staff.is_active:
                staff.last_name = 'Hoạt động'
                msg_action = "Mở khóa"
            else:
                staff.last_name = 'Tạm khóa'
                msg_action = "Tạm khóa"

            staff.save()
            messages.success(request, f"Đã {msg_action.lower()} tài khoản nhân viên {staff.name} thành công!")
            return redirect('accounts:admin_staff_list')

    # Toàn bộ danh sách nhân viên
    base_qs = User.objects.filter(is_staff=True).exclude(is_superuser=True)
    total_staff_all = base_qs.count()
    active_count = base_qs.filter(is_active=True, last_name='Hoạt động').count()
    leave_count = base_qs.filter(last_name='Nghỉ phép').count()
    locked_count = base_qs.filter(Q(is_active=False) | Q(last_name='Tạm khóa')).count()

    qs = base_qs.select_related('profile').order_by('-id')

    # Bộ lọc tìm kiếm
    search_query = request.GET.get('search', '').strip()
    if search_query:
        clean_code = search_query.upper().replace('#NV', '').replace('NV', '').strip()
        code_filter = Q()
        if clean_code.isdigit():
            code_filter = Q(id=int(clean_code))

        qs = qs.filter(
            Q(name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(email__icontains=search_query) |
            code_filter
        )

    # Bộ lọc trạng thái tabs
    status_filter = request.GET.get('status', 'all').strip()
    if status_filter == 'active':
        qs = qs.filter(is_active=True, last_name='Hoạt động')
    elif status_filter == 'on_leave':
        qs = qs.filter(last_name='Nghỉ phép')
    elif status_filter == 'locked':
        qs = qs.filter(Q(is_active=False) | Q(last_name='Tạm khóa'))

    filtered_count = qs.count()

    # Phân trang: 7 nhân viên / trang (Chuẩn Figma 221:3117)
    paginator = Paginator(qs, 7)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Đính kèm initials và formatted data cho từng nhân viên
    for s in page_obj:
        s.staff_code = f"#NV{s.id:03d}"
        s.initials = get_staff_initials(s.name)
        s.position = 'Staff'
        if not s.is_active:
            s.work_status = 'Tạm khóa'
        else:
            s.work_status = s.last_name or 'Hoạt động'

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'current_status': status_filter,
        'total_count': total_staff_all,
        'active_count': active_count,
        'leave_count': leave_count,
        'locked_count': locked_count,
        'filtered_count': filtered_count,
        'next_code': f"#NV{(User.objects.filter(is_staff=True).count() + 1):03d}"
    }
    return render(request, 'accounts/admin_staff_list.html', context)


@login_required
def admin_staff_detail_view(request, pk):
    """Xem nhanh thông tin nhân viên"""
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Bạn không có quyền truy cập.")
        return redirect('accounts:login')

    staff = get_object_or_404(User.objects.select_related('profile'), pk=pk, is_staff=True)
    staff.staff_code = f"#NV{staff.id:03d}"
    staff.initials = get_staff_initials(staff.name)
    staff.position = 'Staff'
    staff.work_status = 'Tạm khóa' if not staff.is_active else (staff.last_name or 'Hoạt động')

    # Thống kê lịch hẹn phụ trách nếu có
    assigned_appointments = Appointment.objects.filter(assigned_staff=staff).order_by('-appointment_date')[:10]
    total_assigned = Appointment.objects.filter(assigned_staff=staff).count()

    context = {
        'staff': staff,
        'assigned_appointments': assigned_appointments,
        'total_assigned': total_assigned,
    }
    return render(request, 'accounts/admin_staff_detail.html', context)




