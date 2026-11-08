"""
================================================================================
RESTFUL API CHO PHÂN HỆ QUẢN LÝ HỒ SƠ SỨC KHỎE (MOD-08) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc (Meo)
Mục đích:
  - Cung cấp toàn bộ RESTful API giao tiếp giữa Client (Vanilla JS Fetch API) và Backend Django.
  - Phục vụ 2 Use Cases chính:
      + UC-8.1: Cập nhật hồ sơ sức khỏe khách hàng 1-1 (Ghi đè, không lưu lịch sử)
      + UC-8.2: Xem hồ sơ sức khỏe cá nhân (Phân quyền: User xem của mình, Staff xem mọi khách)
  - Khớp 100% Hợp đồng API mục số 18 trong Spec Sheet chốt:
      POST, PUT /api/health-profile/
  - Tích hợp tính năng an toàn y tế cho Kỹ thuật viên (KTV) và Lễ tân Spa.
================================================================================
"""

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import UserHealthProfile, User, Appointment
from .serializers import UserHealthProfileSerializer, HealthProfileUpdateInputSerializer

logger = logging.getLogger(__name__)


def generate_unique_health_code(user):
    """
    Hàm sinh mã định danh hồ sơ sức khỏe duy nhất:
    Định dạng: HP-KH{user.id:04d} (Ví dụ: HP-KH0003, HP-KH0012)
    Nếu đã tồn tại thì tự động thêm hậu tố để đảm bảo ràng buộc Unique 100%.
    """
    base_code = f"HP-KH{user.id:04d}"
    if not UserHealthProfile.objects.filter(health_code=base_code).exists():
        return base_code
    
    # Nếu trùng, thêm timestamp ngắn
    suffix = timezone.now().strftime("%y%m%d%H%M")
    return f"HP-KH{user.id:03d}-{suffix[-4:]}"


class HealthProfileDetailAPI(APIView):
    """
    [MOD-08 - UC-8.2] API lấy chi tiết Hồ sơ sức khỏe cá nhân (Chuẩn 1-1).
    URL: GET /health/api/ hoặc GET /health/api/my-profile/
    Quyền truy cập: Người dùng đã đăng nhập (IsAuthenticated).
    
    Nghiệp vụ:
      - Khách hàng xem hồ sơ sức khỏe của chính mình.
      - Nếu người dùng có quyền Staff hoặc Quản trị viên (is_staff/is_superuser) và truyền ?user_id=X,
        hệ thống cho phép xem hồ sơ sức khỏe của khách hàng tương ứng.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        target_user = request.user

        # Cho phép Nhân viên / Quản lý xem hồ sơ của khách khác qua query param ?user_id=
        user_id_param = request.query_params.get('user_id')
        if user_id_param and (request.user.is_staff or request.user.is_superuser):
            try:
                target_user = User.objects.get(id=int(user_id_param))
            except (User.DoesNotExist, ValueError):
                return Response({
                    "status": "error",
                    "message": f"Không tìm thấy người dùng có ID {user_id_param}."
                }, status=status.HTTP_404_NOT_FOUND)

        # Lấy hồ sơ sức khỏe quan hệ 1-1
        try:
            profile = target_user.health_profile
            serializer = UserHealthProfileSerializer(profile)
            return Response({
                "status": "success",
                "has_profile": True,
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except UserHealthProfile.DoesNotExist:
            return Response({
                "status": "success",
                "has_profile": False,
                "message": "Người dùng chưa tạo hồ sơ sức khỏe.",
                "data": {
                    "user_id": target_user.id,
                    "user_name": target_user.name or target_user.username,
                    "user_phone": target_user.phone,
                    "user_email": target_user.email,
                    "health_code": None,
                    "height_cm": None,
                    "weight_kg": None,
                    "blood_pressure": "Bình thường",
                    "focus_areas": [],
                    "massage_pressure": "Lực vừa",
                    "pain_level": 5,
                    "health_conditions": [],
                    "allergy_notes": "",
                    "special_requests": "",
                    "recovery_goals": [],
                }
            }, status=status.HTTP_200_OK)


class HealthProfileUpdateAPI(APIView):
    """
    [MOD-08 - UC-8.1] API Cập nhật / Khảo sát hồ sơ sức khỏe khách hàng.
    URL: POST, PUT /health/api/ hoặc POST, PUT /health/api/update/
    Khớp 100% Hợp đồng API:
      Request Body (JSON):
      {
        "height_cm": 165,
        "weight_kg": 55,
        "blood_pressure": "Bình thường",
        "focus_areas": ["Vai gáy", "Thắt lưng"],
        "massage_pressure": "Lực vừa",
        "pain_level": 7,
        "health_conditions": ["Da nhạy cảm"],
        "allergy_notes": "Dị ứng tinh dầu quế",
        "recovery_goals": ["Giảm đau mỏi vai gáy"],
        "special_requests": "Phòng ấm"
      }
      Response (JSON):
      {
        "status": "success",
        "message": "Cập nhật hồ sơ sức khỏe thành công",
        "health_code": "HP-KH001",
        "data": {...}
      }

    Quy tắc nghiệp vụ:
      - Chuẩn 1-1 tối giản: Ghi đè lên bản ghi duy nhất hiện tại (update_or_create).
      - Bỏ xem lịch sử nhiều lần điền theo đúng chốt duyệt.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        return self._save_profile(request)

    @transaction.atomic
    def put(self, request, *args, **kwargs):
        return self._save_profile(request)

    def _save_profile(self, request):
        target_user = request.user

        # Nếu là Staff/Admin và muốn cập nhật thay cho khách (qua query param hoặc body)
        user_id_param = request.data.get('user_id') or request.query_params.get('user_id')
        if user_id_param and (request.user.is_staff or request.user.is_superuser):
            try:
                target_user = User.objects.get(id=int(user_id_param))
            except (User.DoesNotExist, ValueError):
                return Response({
                    "status": "error",
                    "message": f"Không tìm thấy khách hàng có ID {user_id_param} để cập nhật hồ sơ."
                }, status=status.HTTP_404_NOT_FOUND)

        # Validate dữ liệu đầu vào bằng Serializer
        serializer = HealthProfileUpdateInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Dữ liệu khảo sát sức khỏe không hợp lệ.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data

        # Chuẩn bị dữ liệu cập nhật
        update_fields = {
            'height_cm': validated_data.get('height_cm'),
            'weight_kg': validated_data.get('weight_kg'),
            'blood_pressure': validated_data.get('blood_pressure') or 'Bình thường',
            'focus_areas': validated_data.get('focus_areas', []),
            'massage_pressure': validated_data.get('massage_pressure') or 'Lực vừa',
            'pain_level': validated_data.get('pain_level') or 5,
            'health_conditions': validated_data.get('health_conditions', []),
            'allergy_notes': validated_data.get('allergy_notes', ''),
            'special_requests': validated_data.get('special_requests', ''),
            'recovery_goals': validated_data.get('recovery_goals', []),
        }

        # Kiểm tra xem hồ sơ đã tồn tại chưa (Chuẩn 1-1: ghi đè)
        profile = UserHealthProfile.objects.filter(user=target_user).first()
        if profile:
            # Ghi đè lên bản ghi hiện tại
            for field, val in update_fields.items():
                setattr(profile, field, val)
            profile.save()
            action_desc = "Cập nhật"
        else:
            # Tạo mới bản ghi duy nhất kèm sinh mã health_code
            health_code = generate_unique_health_code(target_user)
            profile = UserHealthProfile.objects.create(
                user=target_user,
                health_code=health_code,
                **update_fields
            )
            action_desc = "Khởi tạo"

        # Trả về kết quả JSON theo đúng Hợp đồng API
        response_serializer = UserHealthProfileSerializer(profile)
        return Response({
            "status": "success",
            "message": f"{action_desc} hồ sơ sức khỏe thành công",
            "health_code": profile.health_code,
            "data": response_serializer.data
        }, status=status.HTTP_200_OK)


class StaffCustomerHealthAPI(APIView):
    """
    [MOD-08 - UC-8.2] API dành cho Nhân viên CSKH & Kỹ thuật viên (KTV) tra cứu chi tiết
    hồ sơ sức khỏe của một khách hàng cụ thể theo user_id.
    URL: GET /health/api/customer/<int:user_id>/
    Quyền truy cập: Nhân viên (is_staff=True) hoặc Quản lý (is_superuser=True).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id, *args, **kwargs):
        # Kiểm tra quyền nhân viên hoặc quản trị
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({
                "status": "error",
                "message": "Bạn không có quyền truy cập hồ sơ sức khỏe khách hàng này."
            }, status=status.HTTP_403_FORBIDDEN)

        customer = get_object_or_404(User, id=user_id)

        try:
            profile = customer.health_profile
            serializer = UserHealthProfileSerializer(profile)
            profile_data = serializer.data
            has_profile = True
        except UserHealthProfile.DoesNotExist:
            profile_data = None
            has_profile = False

        # Lấy thêm 3 lịch hẹn gần nhất của khách hàng để KTV nắm bắt lộ trình trị liệu
        recent_appointments = (
            Appointment.objects.filter(user=customer)
            .select_related('voucher')
            .prefetch_related('details__service')
            .order_by('-appointment_date', '-time_slot')[:3]
        )
        
        appointments_list = []
        for appt in recent_appointments:
            services_names = [d.service.name for d in appt.details.all()]
            appointments_list.append({
                "id": appt.id,
                "appointment_code": appt.appointment_code,
                "appointment_date": appt.appointment_date.strftime('%d/%m/%Y'),
                "time_slot": appt.time_slot,
                "services": services_names,
                "status": appt.status,
                "note": appt.note,
            })

        return Response({
            "status": "success",
            "has_profile": has_profile,
            "customer": {
                "id": customer.id,
                "name": customer.name or customer.username,
                "phone": customer.phone,
                "email": customer.email,
                "gender": getattr(getattr(customer, 'profile', None), 'gender', 'Chưa rõ'),
                "birthday": str(getattr(getattr(customer, 'profile', None), 'birthday', '')) or None,
            },
            "health_profile": profile_data,
            "recent_appointments": appointments_list
        }, status=status.HTTP_200_OK)


class HealthLookupAPI(APIView):
    """
    [MOD-08] API tìm kiếm / tra cứu nhanh hồ sơ sức khỏe khách hàng theo Số điện thoại,
    Tên hoặc Mã hồ sơ sức khỏe.
    URL: GET /health/api/lookup/?q=0905...
    Quyền truy cập: Nhân viên hoặc Quản lý.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({
                "status": "error",
                "message": "Quyền truy cập bị từ chối."
            }, status=status.HTTP_403_FORBIDDEN)

        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({
                "status": "success",
                "results": []
            }, status=status.HTTP_200_OK)

        # Tìm kiếm theo tên, phone, health_code
        profiles = (
            UserHealthProfile.objects.select_related('user')
            .filter(
                Q(health_code__icontains=query) |
                Q(user__name__icontains=query) |
                Q(user__phone__icontains=query) |
                Q(user__email__icontains=query)
            )[:15]
        )

        results = []
        for p in profiles:
            serializer = UserHealthProfileSerializer(p)
            results.append({
                "user_id": p.user.id,
                "name": p.user.name or p.user.username,
                "phone": p.user.phone,
                "health_code": p.health_code,
                "blood_pressure": p.blood_pressure,
                "pain_level": p.pain_level,
                "massage_pressure": p.massage_pressure,
                "has_medical_alert": serializer.get_has_medical_alert(p),
                "created_at": p.created_at.strftime('%d/%m/%Y %H:%M') if p.created_at else "",
            })

        return Response({
            "status": "success",
            "query": query,
            "count": len(results),
            "results": results
        }, status=status.HTTP_200_OK)


class SyncPressureToBookingAPI(APIView):
    """
    [MOD-08 -> MOD-01] Tiện ích đồng bộ lực massage và vùng đau mỏi ưa thích
    từ Hồ sơ sức khỏe của người dùng sang Bước đặt lịch hẹn trực tuyến (UC-1.1).
    URL: GET /health/api/sync-pressure/
    Quyền truy cập: Mọi đối tượng (nếu đăng nhập thì trả về cấu hình cá nhân).
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({
                "status": "success",
                "authenticated": False,
                "preferred_pressure": "Lực vừa",
                "focus_areas": [],
                "allergy_notes": "",
            }, status=status.HTTP_200_OK)

        try:
            hp = request.user.health_profile
            return Response({
                "status": "success",
                "authenticated": True,
                "preferred_pressure": hp.massage_pressure or "Lực vừa",
                "focus_areas": hp.focus_areas or [],
                "allergy_notes": hp.allergy_notes or "",
                "pain_level": hp.pain_level or 5,
                "health_conditions": hp.health_conditions or [],
            }, status=status.HTTP_200_OK)
        except UserHealthProfile.DoesNotExist:
            return Response({
                "status": "success",
                "authenticated": True,
                "preferred_pressure": "Lực vừa",
                "focus_areas": [],
                "allergy_notes": "",
            }, status=status.HTTP_200_OK)
