import re
from datetime import datetime
from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.validators import validate_email as django_validate_email
from core.models import User, UserProfile


def normalize_phone(raw_phone):
    """Chuẩn hóa số điện thoại bằng cách bỏ khoảng trắng và ký tự phân tách."""
    return re.sub(r'[\s.\-()]+', '', (raw_phone or '').strip())


def has_phone_conflict(clean_phone, exclude_user_id=None):
    """Kiểm tra trùng số điện thoại hoặc username số điện thoại trên tất cả tài khoản khác."""
    if not clean_phone:
        return False
    qs = User.objects.all()
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    for phone_val, username_val in qs.values_list('phone', 'username'):
        if normalize_phone(phone_val) == clean_phone:
            return True
        clean_username = normalize_phone(username_val)
        if username_val and (
            username_val.strip().lower() == clean_phone.lower()
            or (clean_username.isdigit() and clean_username == clean_phone)
        ):
            return True
    return False


def has_email_conflict(clean_email, exclude_user_id=None):
    """Kiểm tra trùng địa chỉ email (không phân biệt hoa thường)."""
    if not clean_email:
        return False
    qs = User.objects.all()
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    return qs.filter(email__iexact=clean_email).exists()


def validate_email_domain_for_role(email, is_staff_or_admin=False):
    """
    Ràng buộc tên miền email theo vai trò:
      - Khách hàng: @gmail.com
      - Nhân viên / Quản trị viên: @chamspa.vn
    Trả về chuỗi lỗi tiếng Việt nếu không hợp lệ, None nếu hợp lệ.
    """
    clean_email = (email or '').strip().lower()
    if not clean_email:
        return "Vui lòng nhập địa chỉ email."
    try:
        django_validate_email(clean_email)
    except ValidationError:
        return "Địa chỉ email không đúng định dạng hợp lệ."
    if is_staff_or_admin:
        if not clean_email.endswith('@chamspa.vn'):
            return "Email nhân viên / quản trị viên phải sử dụng đuôi @chamspa.vn (ví dụ: ten@chamspa.vn)."
    elif not clean_email.endswith('@gmail.com'):
        return "Email khách hàng phải sử dụng đuôi @gmail.com (ví dụ: ten@gmail.com)."
    return None


def parse_optional_date(date_str):
    """Phân tích ngày sinh định dạng YYYY-MM-DD (cho phép rỗng để xóa ngày sinh)."""
    cleaned = (date_str or '').strip()
    if not cleaned:
        return None, None
    try:
        return datetime.strptime(cleaned, '%Y-%m-%d').date(), None
    except ValueError:
        return None, "Ngày sinh không đúng định dạng hợp lệ (YYYY-MM-DD)."


def validate_account_payload(name, raw_phone, raw_email, is_staff_or_admin=False, exclude_user_id=None, require_email=True):
    """Kiểm tra tính hợp lệ và trùng lặp Họ tên, SĐT, Email theo vai trò tài khoản."""
    clean_name = (name or '').strip()
    clean_phone = normalize_phone(raw_phone)
    clean_email = (raw_email or '').strip().lower()

    if not clean_name or not clean_phone:
        return None, "Vui lòng nhập đầy đủ Họ tên và Số điện thoại."
    if has_phone_conflict(clean_phone, exclude_user_id=exclude_user_id):
        return None, f"Số điện thoại '{clean_phone}' đã được sử dụng bởi tài khoản khác."
    if require_email or clean_email:
        domain_err = validate_email_domain_for_role(clean_email, is_staff_or_admin=is_staff_or_admin)
        if domain_err:
            return None, domain_err
        if has_email_conflict(clean_email, exclude_user_id=exclude_user_id):
            return None, f"Địa chỉ email '{clean_email}' đã được sử dụng bởi tài khoản khác."

    return {
        'name': clean_name,
        'phone': clean_phone,
        'email': clean_email,
    }, None


def sync_user_phone_username(user, new_phone, old_phone=''):
    """Đồng bộ username theo SĐT khi tài khoản vốn dùng SĐT làm username (giữ nguyên username cố định)."""
    old_clean = normalize_phone(old_phone)
    if new_phone and (
        not user.username
        or (user.username not in ('admin', 'staff') and normalize_phone(user.username) == old_clean)
    ):
        if not User.objects.exclude(pk=user.pk).filter(username=new_phone).exists():
            user.username = new_phone


class LoginForm(forms.Form):
    """
    Form Đăng nhập linh hoạt (Số điện thoại, Email hoặc Tên tài khoản)
    Khớp 100% bản thiết kế Figma (Node 188:27886)
    """
    username = forms.CharField(
        label="Tài khoản / Email / SĐT *",
        widget=forms.TextInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': 'Nhập tài khoản, Email hoặc Số điện thoại',
            'autocomplete': 'username',
            'required': True,
        })
    )
    password = forms.CharField(
        label="Mật khẩu *",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': 'Nhập mật khẩu',
            'autocomplete': 'current-password',
            'required': True,
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        label="Ghi nhớ đăng nhập"
    )

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')

        if username and password:
            login_id = username.strip()
            # Tìm kiếm user trực tiếp theo Số điện thoại, Email hoặc Username
            user = User.objects.filter(
                Q(phone__iexact=login_id) |
                Q(email__iexact=login_id) |
                Q(username__iexact=login_id)
            ).first()

            if user is None or not user.check_password(password):
                raise ValidationError("Thông tin đăng nhập hoặc mật khẩu không chính xác. Vui lòng kiểm tra lại.")
            if not user.is_active:
                raise ValidationError("Tài khoản của bạn hiện đang bị tạm khóa. Vui lòng liên hệ lễ tân Cham Spa.")
            cleaned_data['user'] = user

        return cleaned_data


class RegisterForm(forms.Form):
    """
    Form Đăng ký tài khoản Khách hàng Cham Spa
    Khớp 100% bản thiết kế Figma (Node 188:27928)
    """
    name = forms.CharField(
        label="Họ và tên *",
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': 'Nhập họ và tên',
            'required': True,
        })
    )
    email = forms.EmailField(
        label="Email *",
        widget=forms.EmailInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': 'tenban@gmail.com',
            'required': True,
        })
    )
    phone = forms.CharField(
        label="Số điện thoại *",
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': '09xx xxx xxx',
            'required': True,
        })
    )
    password = forms.CharField(
        label="Mật khẩu *",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': 'Tối thiểu 8 ký tự',
            'required': True,
        })
    )
    password_confirm = forms.CharField(
        label="Nhập lại Mật khẩu *",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': 'Nhập lại mật khẩu',
            'required': True,
        })
    )

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get('phone', ''))
        if not phone:
            raise ValidationError("Vui lòng nhập số điện thoại.")
        if has_phone_conflict(phone):
            raise ValidationError("Số điện thoại này đã được đăng ký tài khoản tại Cham Spa.")
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        domain_err = validate_email_domain_for_role(email, is_staff_or_admin=False)
        if domain_err:
            raise ValidationError(domain_err)
        if has_email_conflict(email):
            raise ValidationError("Địa chỉ email này đã được sử dụng. Vui lòng dùng email khác.")
        return email

    def clean_password(self):
        pwd = self.cleaned_data.get('password')
        if pwd and len(pwd) < 8:
            raise ValidationError("Mật khẩu phải có tối thiểu 8 ký tự.")
        return pwd

    def clean(self):
        cleaned_data = super().clean()
        pwd = cleaned_data.get('password')
        pwd_confirm = cleaned_data.get('password_confirm')

        if pwd and pwd_confirm and pwd != pwd_confirm:
            self.add_error('password_confirm', "Mật khẩu xác nhận không khớp.")

        return cleaned_data

    def save(self):
        cd = self.cleaned_data
        user = User(
            username=cd['phone'],
            name=cd['name'],
            phone=cd['phone'],
            email=cd['email'],
            is_staff=False,
            is_superuser=False,
            is_active=True
        )
        user.set_password(cd['password'])
        user.save()

        # Tự động tạo kèm hồ sơ cá nhân UserProfile
        UserProfile.objects.get_or_create(user=user)
        return user


class ForgotPasswordForm(forms.Form):
    """
    Form Quên mật khẩu
    Khớp 100% bản thiết kế Figma (Node 188:27987)
    """
    email = forms.EmailField(
        label="Email đăng ký *",
        widget=forms.EmailInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': 'ten@gmail.com',
            'required': True,
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        user = User.objects.filter(email=email).first()
        if not user:
            raise ValidationError("Email này chưa được đăng ký trong hệ thống Cham Spa.")
        if not user.is_active:
            raise ValidationError("Tài khoản gắn với email này hiện đang bị khóa.")
        return email


class ResetPasswordForm(forms.Form):
    """
    Form Đặt lại mật khẩu mới
    Khớp 100% bản thiết kế Figma (Node 188:28011)
    """
    new_password = forms.CharField(
        label="Mật khẩu mới *",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': 'Nhập mật khẩu mới',
            'required': True,
        })
    )
    confirm_password = forms.CharField(
        label="Xác nhận Mật khẩu mới *",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control cham-auth-input',
            'placeholder': 'Nhập lại mật khẩu mới',
            'required': True,
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', "Mật khẩu xác nhận không khớp.")
        return cleaned_data


class ProfileForm(forms.ModelForm):
    """
    Form Cập nhật hồ sơ cá nhân (Dùng cho cả Khách hàng, Nhân viên, Quản trị viên)
    Tất cả các trường đều có thể chỉnh sửa tự do theo yêu cầu.
    """
    gender = forms.ChoiceField(
        label="Giới tính",
        choices=UserProfile.GENDER_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select cham-input'})
    )
    birthday = forms.DateField(
        label="Ngày sinh",
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control cham-input', 'type': 'date'})
    )

    class Meta:
        model = User
        fields = ['name', 'phone', 'email']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control cham-input', 'placeholder': 'Nhập họ và tên...'}),
            'phone': forms.TextInput(attrs={'class': 'form-control cham-input', 'placeholder': 'Nhập số điện thoại...'}),
            'email': forms.EmailInput(attrs={'class': 'form-control cham-input', 'placeholder': 'Nhập địa chỉ email...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_phone = normalize_phone(self.instance.phone) if self.instance and self.instance.pk else ''

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError("Vui lòng nhập họ và tên.")
        return name

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get('phone', ''))
        if not phone:
            raise ValidationError("Vui lòng nhập số điện thoại.")
        if has_phone_conflict(phone, exclude_user_id=self.instance.pk):
            raise ValidationError("Số điện thoại này đã được sử dụng bởi tài khoản khác.")
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        is_staff_or_admin = bool(self.instance and (self.instance.is_superuser or self.instance.is_staff))
        domain_err = validate_email_domain_for_role(email, is_staff_or_admin=is_staff_or_admin)
        if domain_err:
            raise ValidationError(domain_err)
        if has_email_conflict(email, exclude_user_id=self.instance.pk):
            raise ValidationError("Địa chỉ email này đã được sử dụng bởi tài khoản khác.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # Chỉ đồng bộ username theo SĐT cho tài khoản dùng SĐT làm username (giữ nguyên username cố định như 'admin', 'staff')
        sync_user_phone_username(user, user.phone, self._original_phone)
        if commit:
            user.save()
        return user
