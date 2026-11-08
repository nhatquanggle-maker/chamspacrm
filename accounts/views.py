from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib import messages
from django.urls import reverse
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from .forms import LoginForm, RegisterForm, ProfileForm, ForgotPasswordForm, ResetPasswordForm
from core.models import User, UserProfile, Membership
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


