from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth import login as auth_login, logout as auth_logout
from decimal import Decimal
from django.db import models
from django.db.models import Q, Avg, Sum
from django.utils import timezone
from core.models import User, UserProfile
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
)


class RegisterAPI(APIView):
    """
    API Đăng ký tài khoản Khách hàng
    POST /accounts/api/register/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            auth_login(request, user)  # Thiết lập phiên đăng nhập
            user_data = UserSerializer(user).data
            return Response({
                "status": "success",
                "message": f"Chúc mừng quý khách {user.name} đã đăng ký tài khoản thành công!",
                "user": user_data,
            }, status=status.HTTP_201_CREATED)
        return Response({
            "status": "error",
            "message": "Dữ liệu đăng ký không hợp lệ.",
            "errors": serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)


class LoginAPI(APIView):
    """
    API Đăng nhập tài khoản & Nhận diện vai trò
    POST /accounts/api/login/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            auth_login(request, user)
            if not serializer.validated_data.get('remember_me'):
                request.session.set_expiry(0)

            user_data = UserSerializer(user).data
            # Xác định URL chuyển hướng theo vai trò
            if user.is_superuser:
                redirect_url = "/dashboard/admin/"
            elif user.is_staff:
                redirect_url = "/dashboard/staff/"
            else:
                redirect_url = "/accounts/profile/"

            return Response({
                "status": "success",
                "message": f"Chào mừng {user.name or user.username} đã đăng nhập thành công!",
                "role": user_data['role'],
                "redirect_url": redirect_url,
                "user": user_data,
            }, status=status.HTTP_200_OK)
        return Response({
            "status": "error",
            "message": "Thông tin đăng nhập không chính xác.",
            "errors": serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)


class MeAPI(APIView):
    """
    API Xem & Cập nhật Hồ sơ cá nhân của người dùng hiện tại
    GET /accounts/api/me/
    PUT /accounts/api/me/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response({
            "status": "success",
            "user": serializer.data,
        }, status=status.HTTP_200_OK)

    def put(self, request):
        return self.patch(request)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.update(request.user, serializer.validated_data)
            return Response({
                "status": "success",
                "message": "Cập nhật hồ sơ cá nhân thành công!",
                "user": UserSerializer(user).data,
            }, status=status.HTTP_200_OK)
        return Response({
            "status": "error",
            "errors": serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)


class CustomerListAPI(APIView):
    """
    API Quản lý Khách hàng dành cho Admin & Staff ở máy khác:
    GET /accounts/api/customers/
    Query params:
      - search: tìm theo Tên, Số điện thoại hoặc Email
      - today: nếu = 1 hoặc true, lọc khách hàng mới đăng ký trong ngày hôm nay
    """
    permission_classes = [permissions.AllowAny]  # Cho phép xem danh sách phục vụ demo đa thiết bị

    def get(self, request):
        # Chỉ lấy khách hàng thông thường (không phải staff hoặc superuser)
        customers = User.objects.filter(is_staff=False, is_superuser=False)

        # 1. Tìm kiếm theo từ khóa
        search_query = request.GET.get('search', '').strip()
        if search_query:
            customers = customers.filter(
                Q(name__icontains=search_query) |
                Q(phone__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(username__icontains=search_query)
            )

        # 2. Lọc khách mới tạo hôm nay
        today_filter = request.GET.get('today', '').strip().lower()
        if today_filter in ('1', 'true'):
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            customers = customers.filter(date_joined__gte=today_start)

        # 3. Sắp xếp khách mới nhất lên đầu
        customers = customers.select_related('profile').order_by('-date_joined')

        serializer = UserSerializer(customers, many=True)
        return Response({
            "status": "success",
            "total_count": customers.count(),
            "customers": serializer.data,
            "timestamp": timezone.now().isoformat(),
        }, status=status.HTTP_200_OK)


class AccountStatsAPI(APIView):
    """
    API Thống kê Tổng quan Người dùng (Dành cho Dashboard Admin / Staff)
    GET /accounts/api/stats/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        total_customers = User.objects.filter(is_staff=False, is_superuser=False).count()
        new_today = User.objects.filter(is_staff=False, is_superuser=False, date_joined__gte=today_start).count()
        total_staff = User.objects.filter(is_staff=True, is_superuser=False).count()
        total_admins = User.objects.filter(is_superuser=True).count()

        return Response({
            "status": "success",
            "stats": {
                "total_customers": total_customers,
                "new_customers_today": new_today,
                "total_staff": total_staff,
                "total_admins": total_admins,
            },
            "timestamp": timezone.now().isoformat(),
        }, status=status.HTTP_200_OK)


class LogoutAPI(APIView):
    """
    UC-5.5: Đăng xuất tài khoản qua API
    POST /api/auth/logout/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        auth_logout(request)
        return Response({
            "status": "success",
            "message": "Đăng xuất tài khoản thành công.",
        }, status=status.HTTP_200_OK)


class AdminUserListAPI(APIView):
    """
    UC-5.6: Quản lý danh sách toàn bộ User (Khách hàng, Nhân viên, Quản trị viên)
    GET /api/admin/users/
    """
    permission_classes = [permissions.AllowAny]  # Hỗ trợ demo đa thiết bị

    def get(self, request):
        users = User.objects.all().select_related('profile').order_by('-date_joined')

        role_filter = request.GET.get('role', '').strip().upper()
        if role_filter == 'ADMIN':
            users = users.filter(is_superuser=True)
        elif role_filter == 'STAFF':
            users = users.filter(is_staff=True, is_superuser=False)
        elif role_filter == 'CUSTOMER':
            users = users.filter(is_staff=False, is_superuser=False)

        status_filter = request.GET.get('status', '').strip()
        if status_filter in ('active', 'true', '1'):
            users = users.filter(is_active=True)
        elif status_filter in ('inactive', 'false', '0'):
            users = users.filter(is_active=False)

        q = request.GET.get('search', '').strip()
        if q:
            users = users.filter(
                Q(name__icontains=q) |
                Q(phone__icontains=q) |
                Q(email__icontains=q) |
                Q(username__icontains=q)
            )

        serializer = UserSerializer(users, many=True)
        return Response({
            "status": "success",
            "total_count": users.count(),
            "users": serializer.data,
        }, status=status.HTTP_200_OK)


class AdminUserToggleStatusAPI(APIView):
    """
    UC-5.7: Mở / Khóa tài khoản người dùng (is_active)
    PUT /api/admin/users/{id}/toggle-status/
    """
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        try:
            target_user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"status": "error", "message": "Tài khoản không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.is_authenticated and request.user.pk == target_user.pk:
            return Response({"status": "error", "message": "Không thể tự khóa tài khoản quản trị đang đăng nhập."}, status=status.HTTP_400_BAD_REQUEST)

        # Chuyển đổi trạng thái is_active
        target_user.is_active = not target_user.is_active
        target_user.save()

        action = "Mở khóa" if target_user.is_active else "Khóa"
        return Response({
            "status": "success",
            "is_active": target_user.is_active,
            "message": f"Đã {action} tài khoản thành công.",
            "user_id": target_user.id,
        }, status=status.HTTP_200_OK)


class AdminCustomerCreateAPI(APIView):
    """
    UC-5.6: Admin tạo tài khoản khách hàng mới
    POST /api/admin/customers/create/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from .serializers import CustomerCreateAdminSerializer
        serializer = CustomerCreateAdminSerializer(data=request.data)
        if serializer.is_valid():
            customer = serializer.save()
            return Response({
                "status": "success",
                "message": f"Tạo mới tài khoản khách hàng {customer.name} thành công!",
                "customer": UserSerializer(customer).data,
            }, status=status.HTTP_201_CREATED)
        return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class AdminCustomerDetailAPI(APIView):
    """
    UC-5.8: Xem thông tin khách hàng (Dashboard 360)
    GET /api/admin/customers/{id}/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        try:
            customer = User.objects.select_related('profile', 'membership__tier', 'health_profile').get(pk=pk, is_staff=False, is_superuser=False)
        except User.DoesNotExist:
            return Response({"status": "error", "message": "Khách hàng không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserSerializer(customer)
        # Thống kê lịch hẹn & lịch sử
        appts = customer.appointments.all() if hasattr(customer, 'appointments') else []
        appointment_count = appts.count() if hasattr(appts, 'count') else len(appts)
        completed_count = appts.filter(status='Completed').count() if hasattr(appts, 'filter') else 0
        cancelled_count = appts.filter(status='Cancelled').count() if hasattr(appts, 'filter') else 0
        total_spent = sum((a.total_price for a in (appts.filter(status__in=['Completed', 'Confirmed']) if hasattr(appts, 'filter') else [])), Decimal(0))
        
        feedbacks = customer.feedbacks.all() if hasattr(customer, 'feedbacks') else []
        feedback_count = feedbacks.count() if hasattr(feedbacks, 'count') else len(feedbacks)
        avg_rating = feedbacks.aggregate(avg=models.Avg('rating'))['avg'] or 5.0 if hasattr(feedbacks, 'aggregate') else 5.0

        membership = getattr(customer, 'membership', None)
        health_profile = getattr(customer, 'health_profile', None)

        return Response({
            "status": "success",
            "customer": serializer.data,
            "overview_360": {
                "total_appointments": appointment_count,
                "completed_appointments": completed_count,
                "cancelled_appointments": cancelled_count,
                "total_spent": float(total_spent),
                "formatted_total_spent": f"{int(total_spent):,}".replace(',', '.') + "đ",
                "total_feedbacks": feedback_count,
                "avg_rating": round(float(avg_rating), 1),
            },
            "membership": {
                "tier_name": membership.tier.name if membership and membership.tier else "Thành viên",
                "current_points": membership.current_points if membership else 0,
                "total_spent": float(membership.total_spent) if membership else 0.0,
            } if membership else None,
            "health_profile": {
                "health_code": health_profile.health_code if health_profile else None,
                "height_cm": float(health_profile.height_cm) if health_profile and health_profile.height_cm else None,
                "weight_kg": float(health_profile.weight_kg) if health_profile and health_profile.weight_kg else None,
                "blood_pressure": health_profile.blood_pressure if health_profile else None,
                "focus_areas": health_profile.focus_areas if health_profile else [],
                "massage_pressure": health_profile.massage_pressure if health_profile else "Lực vừa",
                "pain_level": health_profile.pain_level if health_profile else 0,
                "allergy_notes": health_profile.allergy_notes if health_profile else "",
                "special_requests": health_profile.special_requests if health_profile else "",
            } if health_profile else None
        }, status=status.HTTP_200_OK)


class AdminCustomerUpdateAPI(APIView):
    """
    UC-5.9: Cập nhật thông tin khách hàng
    PUT /api/admin/customers/{id}/update/
    """
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        try:
            customer = User.objects.get(pk=pk, is_staff=False, is_superuser=False)
        except User.DoesNotExist:
            return Response({"status": "error", "message": "Khách hàng không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        from .serializers import CustomerUpdateAdminSerializer
        serializer = CustomerUpdateAdminSerializer(data=request.data)
        if serializer.is_valid():
            serializer.update(customer, serializer.validated_data)
            return Response({
                "status": "success",
                "message": "Cập nhật thông tin khách hàng thành công!",
                "customer": UserSerializer(customer).data,
            }, status=status.HTTP_200_OK)
        return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class AdminCustomerDeactivateAPI(APIView):
    """
    UC-5.10: Khóa tài khoản khách hàng (is_active = False)
    PUT /api/admin/customers/{id}/deactivate/
    """
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        try:
            customer = User.objects.get(pk=pk, is_staff=False, is_superuser=False)
        except User.DoesNotExist:
            return Response({"status": "error", "message": "Khách hàng không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        customer.is_active = False
        customer.save()
        return Response({
            "status": "success",
            "is_active": False,
            "message": f"Tài khoản khách hàng {customer.name} đã được khóa an toàn (bảo toàn toàn vẹn dữ liệu).",
        }, status=status.HTTP_200_OK)


class AdminStaffCreateAPI(APIView):
    """
    UC-5.11: Tạo tài khoản nhân viên mới
    POST /api/admin/staff/create/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from .serializers import StaffCreateSerializer
        serializer = StaffCreateSerializer(data=request.data)
        if serializer.is_valid():
            staff = serializer.save()
            return Response({
                "status": "success",
                "message": f"Tạo tài khoản nhân viên {staff.name} thành công!",
                "staff": UserSerializer(staff).data,
            }, status=status.HTTP_201_CREATED)
        return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class AdminStaffListAPI(APIView):
    """
    UC-5.12: Xem danh sách nhân viên
    GET /api/admin/staff/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        staff_members = User.objects.filter(is_staff=True).select_related('profile').order_by('-date_joined')
        q = request.GET.get('search', '').strip()
        if q:
            staff_members = staff_members.filter(
                Q(name__icontains=q) |
                Q(phone__icontains=q) |
                Q(email__icontains=q)
            )

        serializer = UserSerializer(staff_members, many=True)
        return Response({
            "status": "success",
            "total_count": staff_members.count(),
            "staff": serializer.data,
        }, status=status.HTTP_200_OK)


class AdminStaffUpdateAPI(APIView):
    """
    UC-5.13: Cập nhật thông tin nhân viên
    PUT /api/admin/staff/{id}/update/
    """
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        try:
            staff = User.objects.get(pk=pk, is_staff=True)
        except User.DoesNotExist:
            return Response({"status": "error", "message": "Nhân viên không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        from .serializers import StaffUpdateSerializer
        serializer = StaffUpdateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.update(staff, serializer.validated_data)
            return Response({
                "status": "success",
                "message": "Cập nhật thông tin nhân viên thành công!",
                "staff": UserSerializer(staff).data,
            }, status=status.HTTP_200_OK)
        return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class AdminStaffDeactivateAPI(APIView):
    """
    UC-5.14: Khóa tài khoản nhân viên (is_active = False)
    PUT /api/admin/staff/{id}/deactivate/
    """
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        try:
            staff = User.objects.get(pk=pk, is_staff=True)
        except User.DoesNotExist:
            return Response({"status": "error", "message": "Nhân viên không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.is_authenticated and request.user.pk == staff.pk:
            return Response({"status": "error", "message": "Không thể tự khóa tài khoản của chính mình."}, status=status.HTTP_400_BAD_REQUEST)

        staff.is_active = False
        staff.save()
        return Response({
            "status": "success",
            "is_active": False,
            "message": f"Tài khoản nhân viên {staff.name} đã được khóa thành công.",
        }, status=status.HTTP_200_OK)


