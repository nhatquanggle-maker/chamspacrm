from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from core.models import User, UserProfile


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
            'placeholder': 'name@example.com',
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
        phone = self.cleaned_data.get('phone', '').strip().replace(' ', '').replace('.', '')
        if User.objects.filter(phone=phone).exists():
            raise ValidationError("Số điện thoại này đã được đăng ký tài khoản tại Cham Spa.")
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email=email).exists():
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
            'placeholder': 'user@example.com',
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

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip().replace(' ', '').replace('.', '')
        if User.objects.exclude(pk=self.instance.pk).filter(phone=phone).exists():
            raise ValidationError("Số điện thoại này đã được sử dụng bởi tài khoản khác.")
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise ValidationError("Địa chỉ email này đã được sử dụng bởi tài khoản khác.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if user.phone:
            user.username = user.phone
        if commit:
            user.save()
        return user
