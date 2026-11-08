from rest_framework import serializers
from django.contrib.auth import authenticate
from core.models import User, UserProfile, Membership


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['avatar', 'birthday', 'gender', 'created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    role = serializers.SerializerMethodField()
    membership_tier = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'name',
            'email',
            'phone',
            'role',
            'is_staff',
            'is_superuser',
            'is_active',
            'date_joined',
            'profile',
            'membership_tier',
        ]
        read_only_fields = ['id', 'is_staff', 'is_superuser', 'date_joined']

    def get_role(self, obj):
        if obj.is_superuser:
            return 'ADMIN'
        elif obj.is_staff:
            return 'STAFF'
        return 'CUSTOMER'

    def get_membership_tier(self, obj):
        try:
            membership = Membership.objects.filter(user=obj).select_related('tier').first()
            if membership and membership.tier:
                return membership.tier.name
        except Exception:
            pass
        return 'Member Gold'


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=True)
    phone = serializers.CharField(max_length=20, required=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate_phone(self, value):
        val = value.strip().replace(' ', '').replace('.', '')
        if User.objects.filter(username=val).exists() or User.objects.filter(phone=val).exists():
            raise serializers.ValidationError("Số điện thoại này đã được đăng ký tài khoản tại Cham Spa.")
        return val

    def validate_email(self, value):
        val = value.strip().lower()
        if User.objects.filter(email=val).exists():
            raise serializers.ValidationError("Địa chỉ email này đã tồn tại trong hệ thống.")
        return val

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Mật khẩu xác nhận không trùng khớp."})
        return data

    def create(self, validated_data):
        phone = validated_data['phone']
        user = User.objects.create_user(
            username=phone,
            name=validated_data['name'].strip(),
            phone=phone,
            email=validated_data['email'].strip().lower(),
            password=validated_data['password']
        )
        UserProfile.objects.get_or_create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True, help_text="Nhập Username, Số điện thoại hoặc Email")
    password = serializers.CharField(write_only=True, required=True)
    remember_me = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        identifier = data.get('username', '').strip()
        password = data.get('password', '')

        # Tìm user bằng Username, SĐT hoặc Email
        user = (
            User.objects.filter(username=identifier).first() or
            User.objects.filter(phone=identifier).first() or
            User.objects.filter(email__iexact=identifier).first()
        )

        if not user:
            raise serializers.ValidationError({"username": "Tài khoản hoặc thông tin đăng nhập không tồn tại."})

        authenticated_user = authenticate(username=user.username, password=password)
        if not authenticated_user:
            raise serializers.ValidationError({"password": "Mật khẩu không chính xác."})

        if not authenticated_user.is_active:
            raise serializers.ValidationError({"non_field_errors": "Tài khoản này hiện đang bị tạm khóa."})

        data['user'] = authenticated_user
        return data


class ProfileUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=20, required=False)
    email = serializers.EmailField(required=False)
    gender = serializers.ChoiceField(choices=['Nữ', 'Nam', 'Khác'], required=False, allow_null=True)
    birthday = serializers.DateField(required=False, allow_null=True)

    def update(self, instance, validated_data):
        if 'name' in validated_data:
            instance.name = validated_data['name'].strip()
        if 'phone' in validated_data:
            new_phone = validated_data['phone'].strip().replace(' ', '')
            if User.objects.exclude(pk=instance.pk).filter(phone=new_phone).exists():
                raise serializers.ValidationError({"phone": "Số điện thoại đã thuộc về người khác."})
            instance.phone = new_phone
        if 'email' in validated_data:
            new_email = validated_data['email'].strip().lower()
            if User.objects.exclude(pk=instance.pk).filter(email=new_email).exists():
                raise serializers.ValidationError({"email": "Email đã được sử dụng bởi tài khoản khác."})
            instance.email = new_email
        instance.save()

        profile, _ = UserProfile.objects.get_or_create(user=instance)
        if 'gender' in validated_data:
            profile.gender = validated_data['gender']
        if 'birthday' in validated_data:
            profile.birthday = validated_data['birthday']
        profile.save()

        return instance


class StaffCreateSerializer(serializers.Serializer):
    """UC-5.11: Tạo tài khoản nhân viên mới (is_staff=True)"""
    name = serializers.CharField(max_length=150, required=True)
    phone = serializers.CharField(max_length=20, required=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_phone(self, value):
        val = value.strip().replace(' ', '').replace('.', '')
        if User.objects.filter(username=val).exists() or User.objects.filter(phone=val).exists():
            raise serializers.ValidationError("Số điện thoại này đã được sử dụng.")
        return val

    def validate_email(self, value):
        val = value.strip().lower()
        if User.objects.filter(email=val).exists():
            raise serializers.ValidationError("Email này đã tồn tại trong hệ thống.")
        return val

    def create(self, validated_data):
        phone = validated_data['phone']
        user = User.objects.create_user(
            username=phone,
            name=validated_data['name'].strip(),
            phone=phone,
            email=validated_data['email'].strip().lower(),
            password=validated_data['password'],
            is_staff=True,
            is_superuser=False,
            is_active=True
        )
        UserProfile.objects.get_or_create(user=user)
        return user


class StaffUpdateSerializer(serializers.Serializer):
    """UC-5.13: Cập nhật thông tin nhân viên"""
    name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=20, required=False)
    password = serializers.CharField(write_only=True, min_length=8, required=False)

    def update(self, instance, validated_data):
        if 'name' in validated_data:
            instance.name = validated_data['name'].strip()
        if 'phone' in validated_data:
            new_phone = validated_data['phone'].strip().replace(' ', '')
            if User.objects.exclude(pk=instance.pk).filter(phone=new_phone).exists():
                raise serializers.ValidationError({"phone": "Số điện thoại đã bị trùng với tài khoản khác."})
            instance.phone = new_phone
        if 'password' in validated_data and validated_data['password']:
            instance.set_password(validated_data['password'])
        instance.save()
        return instance


class CustomerCreateAdminSerializer(serializers.Serializer):
    """UC-5.6: Quản lý tạo tài khoản khách hàng mới"""
    name = serializers.CharField(max_length=150, required=True)
    phone = serializers.CharField(max_length=20, required=True)
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    password = serializers.CharField(write_only=True, required=False, min_length=6, default='customer123456')
    gender = serializers.ChoiceField(choices=['Nữ', 'Nam', 'Khác'], required=False, default='Nữ')
    birthday = serializers.DateField(required=False, allow_null=True)
    tier_name = serializers.CharField(required=False, default='Thành viên')
    care_note = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_phone(self, value):
        val = value.strip().replace(' ', '').replace('.', '')
        if User.objects.filter(username=val).exists() or User.objects.filter(phone=val).exists():
            raise serializers.ValidationError("Số điện thoại này đã được sử dụng.")
        return val

    def validate_email(self, value):
        val = value.strip().lower()
        if val and User.objects.filter(email=val).exists():
            raise serializers.ValidationError("Email này đã tồn tại trong hệ thống.")
        return val

    def create(self, validated_data):
        from core.models import Tier, UserHealthProfile
        phone = validated_data['phone']
        pwd = validated_data.get('password') or 'customer123456'
        user = User.objects.create_user(
            username=phone,
            name=validated_data['name'].strip(),
            phone=phone,
            email=validated_data.get('email', '').strip().lower(),
            password=pwd,
            is_staff=False,
            is_superuser=False,
            is_active=True
        )
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'gender': validated_data.get('gender', 'Nữ'),
                'birthday': validated_data.get('birthday')
            }
        )
        tier_obj = Tier.objects.filter(name=validated_data.get('tier_name')).first() or Tier.objects.first()
        Membership.objects.get_or_create(
            user=user,
            defaults={
                'tier': tier_obj,
                'current_points': tier_obj.min_points if tier_obj else 0
            }
        )
        care_note = validated_data.get('care_note', '').strip()
        if care_note:
            UserHealthProfile.objects.update_or_create(
                user=user,
                defaults={
                    'health_code': f"HS-{user.id:04d}",
                    'special_requests': care_note
                }
            )
        return user


class CustomerUpdateAdminSerializer(serializers.Serializer):
    """UC-5.9: Quản lý / Nhân viên cập nhật thông tin khách hàng"""
    name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=20, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=['Nữ', 'Nam', 'Khác'], required=False, allow_null=True)
    birthday = serializers.DateField(required=False, allow_null=True)
    tier_name = serializers.CharField(required=False, allow_blank=True)
    care_note = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def update(self, instance, validated_data):
        from core.models import Tier, UserHealthProfile
        if 'name' in validated_data and validated_data['name']:
            instance.name = validated_data['name'].strip()
        if 'phone' in validated_data and validated_data['phone']:
            new_phone = validated_data['phone'].strip().replace(' ', '')
            if User.objects.exclude(pk=instance.pk).filter(phone=new_phone).exists():
                raise serializers.ValidationError({"phone": "Số điện thoại này đã được tài khoản khác sử dụng."})
            instance.phone = new_phone
        if 'email' in validated_data:
            new_email = validated_data['email'].strip().lower()
            if new_email and User.objects.exclude(pk=instance.pk).filter(email=new_email).exists():
                raise serializers.ValidationError({"email": "Email này đã được tài khoản khác sử dụng."})
            instance.email = new_email
        if 'is_active' in validated_data:
            instance.is_active = validated_data['is_active']
        instance.save()

        profile, _ = UserProfile.objects.get_or_create(user=instance)
        if 'gender' in validated_data:
            profile.gender = validated_data['gender']
        if 'birthday' in validated_data:
            profile.birthday = validated_data['birthday']
        profile.save()

        if 'tier_name' in validated_data and validated_data['tier_name']:
            tier_obj = Tier.objects.filter(name=validated_data['tier_name']).first()
            if tier_obj:
                membership, _ = Membership.objects.get_or_create(user=instance)
                membership.tier = tier_obj
                membership.save()

        if 'care_note' in validated_data:
            health_prof, _ = UserHealthProfile.objects.get_or_create(
                user=instance,
                defaults={'health_code': f"HS-{instance.id:04d}"}
            )
            health_prof.special_requests = validated_data['care_note']
            health_prof.save()

        return instance


