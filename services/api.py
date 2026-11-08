"""
RESTful API Endpoints cho Phân hệ Quản lý Danh mục & Dịch vụ (MOD-03) - CHAMSPA CRM
Tác giả: Minh Khánh
Use Cases:
  - UC-3.1: Xem danh sách dịch vụ (lọc theo danh mục, thời lượng, khoảng giá, sắp xếp, phân trang)
  - UC-3.2: Xem chi tiết dịch vụ theo slug (thông tin liệu trình, ảnh gallery, đánh giá khách hàng)
  - UC-3.3: Quản lý danh mục & dịch vụ (CRUD, cập nhật giá/ảnh, bật/tắt trạng thái hiển thị)
Khớp 100% Hợp đồng API (Sheet 5) và Thiết kế Figma (Node 216-928, Node 216-929).
"""

from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from core.models import Category, Service, ServiceImage
from .serializers import (
    CategorySerializer,
    ServiceListSerializer,
    ServiceDetailSerializer,
    AdminServiceWriteSerializer,
    AdminCategoryWriteSerializer
)


class ServiceListAPI(APIView):
    """
    API Lấy danh sách dịch vụ phân trang & lọc (UC-3.1)
    Khớp 100% Hợp đồng API Sheet 5:
      - Method: GET
      - Endpoint: /services/api/ hoặc /services/api/services/
      - Params hỗ trợ:
          + category_slug: Lọc theo danh mục (vd: massage-body, cham-soc-da)
          + search: Tìm kiếm theo tên hoặc mô tả dịch vụ
          + min_price, max_price: Lọc theo khoảng giá
          + duration: Lọc theo thời lượng (30, 60, 90, 120 phút)
          + sort: 'price_asc' (giá tăng), 'price_desc' (giá giảm), 'rating' (sao cao nhất), 'popular' (được ưa chuộng nhất)
          + page: Trang hiện tại (mặc định: 1)
          + page_size: Số dịch vụ/trang (mặc định: 9)
      - Quyền truy cập: Public (Không yêu cầu đăng nhập)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # 1. Chỉ lấy các dịch vụ đang ở trạng thái 'Hoạt động' cho khách hàng
        queryset = Service.objects.filter(status='Hoạt động').select_related('category').prefetch_related('images')

        # 2. Bộ lọc theo danh mục (Category Slug)
        category_slug = request.GET.get('category_slug', '').strip()
        if category_slug and category_slug.lower() not in ['all', 'tat-ca']:
            queryset = queryset.filter(category__slug=category_slug)

        # 3. Tìm kiếm từ khóa (Search)
        search_query = request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # 4. Bộ lọc khoảng giá (Price Range)
        min_price = request.GET.get('min_price', '').strip()
        max_price = request.GET.get('max_price', '').strip()
        if min_price:
            try:
                queryset = queryset.filter(price_vnd__gte=Decimal(min_price))
            except Exception:
                pass
        if max_price:
            try:
                queryset = queryset.filter(price_vnd__lte=Decimal(max_price))
            except Exception:
                pass

        # 5. Bộ lọc thời lượng (Duration in minutes: 30, 60, 90, 120)
        duration = request.GET.get('duration', '').strip()
        if duration and duration.isdigit():
            queryset = queryset.filter(duration_minutes=int(duration))

        # 6. Sắp xếp kết quả (Sorting)
        sort_by = request.GET.get('sort', 'default').strip().lower()
        if sort_by == 'price_asc':
            queryset = queryset.order_by('price_vnd')
        elif sort_by == 'price_desc':
            queryset = queryset.order_by('-price_vnd')
        elif sort_by == 'rating':
            queryset = queryset.order_by('-rating_avg', '-review_count')
        elif sort_by == 'popular':
            queryset = queryset.order_by('-review_count', '-rating_avg')
        else:
            # Mặc định sắp xếp theo ID tăng dần
            queryset = queryset.order_by('id')

        # 7. Phân trang thủ công linh hoạt (Pagination)
        total_count = queryset.count()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 9))
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 9

        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        services_page = queryset[start_index:end_index]

        import math
        total_pages = max(1, math.ceil(total_count / page_size))

        serializer = ServiceListSerializer(services_page, many=True)

        return Response({
            "count": len(serializer.data),
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "results": serializer.data
        }, status=status.HTTP_200_OK)


class ServiceDetailAPI(APIView):
    """
    API Lấy chi tiết dịch vụ chuyên sâu theo slug (UC-3.2)
    Khớp 100% Hợp đồng API Sheet 5:
      - Method: GET
      - Endpoint: /services/api/<slug>/ hoặc /services/api/detail/<slug>/
      - Trả về: Thông tin chi tiết, mảng ảnh gallery, 4 bước quy trình và các đánh giá khách hàng
      - BỎ HOÀN TOÀN việc đếm và tăng lượt xem (views_count) theo đúng chốt duyệt đề cương.
      - Quyền truy cập: Public (Không yêu cầu đăng nhập)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        service = get_object_or_404(
            Service.objects.select_related('category').prefetch_related('images'),
            slug=slug
        )

        serializer = ServiceDetailSerializer(service)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CategoryListAPI(APIView):
    """
    API Lấy danh sách danh mục dịch vụ đang hoạt động
    Dùng để đổ dữ liệu thanh tab ngang và sidebar bộ lọc trên Frontend.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        categories = Category.objects.filter(status='Active').order_by('id')
        serializer = CategorySerializer(categories, many=True)
        return Response({
            "status": "success",
            "categories": serializer.data
        }, status=status.HTTP_200_OK)


# ==============================================================================
# CÁC API DÀNH RIÊNG CHO PHÂN HỆ QUẢN TRỊ VIÊN (UC-3.3 - QUẢN LÝ DỊCH VỤ)
# Chỉ áp dụng cho tài khoản có quyền Quản lý / Ban Giám đốc (IsSuperuser / IsStaff)
# ==============================================================================

class AdminServiceListCreateAPI(APIView):
    """
    API Xem toàn bộ danh sách dịch vụ & Thêm mới dịch vụ từ Admin (UC-3.3)
    Giao diện Quản trị khớp Figma Hình 23 (Node quản lý dịch vụ).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Lấy danh sách tất cả dịch vụ (kể cả Ngừng hoạt động) phục vụ Quản lý"""
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền quản trị.'}, status=status.HTTP_403_FORBIDDEN)

        queryset = Service.objects.all().select_related('category').prefetch_related('images').order_by('id')

        # Lọc theo danh mục
        category_id = request.GET.get('category_id')
        if category_id and category_id.isdigit():
            queryset = queryset.filter(category_id=int(category_id))

        # Lọc theo trạng thái ('Hoạt động', 'Ngừng hoạt động')
        status_filter = request.GET.get('status', '').strip()
        if status_filter and status_filter.lower() != 'all':
            queryset = queryset.filter(status=status_filter)

        # Tìm kiếm nhanh
        q = request.GET.get('search', '').strip()
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(slug__icontains=q))

        serializer = ServiceListSerializer(queryset, many=True)
        return Response({
            "total": queryset.count(),
            "results": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Thêm mới 1 dịch vụ Spa vào CSDL trong 1 Database Transaction an toàn"""
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền thêm mới dịch vụ.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AdminServiceWriteSerializer(data=request.data)
        if not serializer.is_valid():
            is_dup = 'name' in serializer.errors and any('đã tồn tại' in str(e) for e in serializer.errors['name'])
            err_msg = serializer.errors.get('name', ["Dữ liệu nhập không hợp lệ, vui lòng kiểm tra lại."])[0] if is_dup else "Dữ liệu nhập không hợp lệ, vui lòng kiểm tra lại."
            return Response({
                "status": "error",
                "code": "DUPLICATE_SERVICE_NAME" if is_dup else "VALIDATION_ERROR",
                "message": err_msg,
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        gallery_urls = serializer.validated_data.pop('gallery_urls', [])

        try:
            with transaction.atomic():
                service = serializer.save()

                # Lưu các ảnh gallery bổ sung vào bảng ServiceImage
                for url in gallery_urls:
                    if url and url.strip():
                        ServiceImage.objects.create(service=service, image_url=url.strip())

            return Response({
                "status": "success",
                "message": f"Dịch vụ '{service.name}' đã được tạo thành công!",
                "service": ServiceDetailSerializer(service).data
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                "status": "error",
                "message": f"Lỗi trong quá trình lưu cơ sở dữ liệu: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminServiceDetailUpdateDeleteAPI(APIView):
    """
    API Lấy chi tiết, Cập nhật hoặc Xóa một dịch vụ cụ thể (UC-3.3)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """Lấy thông tin chi tiết một dịch vụ để đưa vào Form chỉnh sửa"""
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền truy cập.'}, status=status.HTTP_403_FORBIDDEN)

        service = get_object_or_404(Service.objects.select_related('category').prefetch_related('images'), pk=pk)
        return Response(ServiceDetailSerializer(service).data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        """Cập nhật thông tin dịch vụ (đổi giá, đổi ảnh, sửa mô tả)"""
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền sửa dịch vụ.'}, status=status.HTTP_403_FORBIDDEN)

        service = get_object_or_404(Service, pk=pk)
        serializer = AdminServiceWriteSerializer(service, data=request.data, partial=True)

        if not serializer.is_valid():
            is_dup = 'name' in serializer.errors and any('đã tồn tại' in str(e) for e in serializer.errors['name'])
            err_msg = serializer.errors.get('name', ["Dữ liệu cập nhật không hợp lệ."])[0] if is_dup else "Dữ liệu cập nhật không hợp lệ."
            return Response({
                "status": "error",
                "code": "DUPLICATE_SERVICE_NAME" if is_dup else "VALIDATION_ERROR",
                "message": err_msg,
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        gallery_urls = serializer.validated_data.pop('gallery_urls', None)

        try:
            with transaction.atomic():
                updated_service = serializer.save()

                # Nếu có truyền danh sách ảnh mới, làm mới gallery
                if gallery_urls is not None:
                    ServiceImage.objects.filter(service=updated_service).delete()
                    for url in gallery_urls:
                        if url and url.strip():
                            ServiceImage.objects.create(service=updated_service, image_url=url.strip())

            return Response({
                "status": "success",
                "message": f"Cập nhật dịch vụ '{updated_service.name}' thành công!",
                "service": ServiceDetailSerializer(updated_service).data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": "error",
                "message": f"Lỗi cập nhật CSDL: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """
        Ẩn hoặc Xóa dịch vụ khỏi hệ thống
        Ưu tiên chuyển status sang 'Ngừng hoạt động' (Soft Delete) để đảm bảo toàn vẹn liên kết lịch hẹn.
        """
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền xóa dịch vụ.'}, status=status.HTTP_403_FORBIDDEN)

        service = get_object_or_404(Service, pk=pk)

        # Kiểm tra xem dịch vụ đã có lịch hẹn chưa
        if service.appointment_details.exists():
            # Chuyển trạng thái sang Ngừng hoạt động để bảo vệ lịch sử hóa đơn/lịch hẹn
            service.status = 'Ngừng hoạt động'
            service.save()
            return Response({
                "status": "success",
                "message": f"Dịch vụ '{service.name}' đã từng phát sinh lịch hẹn nên hệ thống đã chuyển sang 'Ngừng hoạt động' thay vì xóa vĩnh viễn.",
                "action": "deactivated"
            }, status=status.HTTP_200_OK)
        else:
            name = service.name
            service.delete()
            return Response({
                "status": "success",
                "message": f"Đã xóa vĩnh viễn dịch vụ '{name}' khỏi hệ thống.",
                "action": "deleted"
            }, status=status.HTTP_200_OK)


class AdminServiceToggleStatusAPI(APIView):
    """
    API Đổi nhanh trạng thái dịch vụ (Hoạt động <-> Ngừng hoạt động)
    Dùng cho công tắc Toggle Switch trên bảng dữ liệu Admin Figma mà không cần tải lại trang.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền thực hiện thao tác này.'}, status=status.HTTP_403_FORBIDDEN)

        service = get_object_or_404(Service, pk=pk)
        if service.status == 'Hoạt động':
            service.status = 'Ngừng hoạt động'
        else:
            service.status = 'Hoạt động'

        service.save()

        return Response({
            "status": "success",
            "service_id": service.id,
            "new_status": service.status,
            "is_active": service.status == 'Hoạt động',
            "message": f"Dịch vụ '{service.name}' hiện đang ở trạng thái: '{service.status}'."
        }, status=status.HTTP_200_OK)


class AdminCategoryListCreateAPI(APIView):
    """
    API Quản lý danh mục (Category) - Xem danh sách và tạo mới (UC-3.3)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền truy cập.'}, status=status.HTTP_403_FORBIDDEN)

        categories = Category.objects.all().annotate(
            total_services=Count('services')
        ).order_by('id')

        serializer = CategorySerializer(categories, many=True)
        return Response({
            "total": categories.count(),
            "results": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền tạo danh mục.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AdminCategoryWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Dữ liệu danh mục không hợp lệ.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        category = serializer.save()
        return Response({
            "status": "success",
            "message": f"Danh mục '{category.name}' đã được tạo thành công!",
            "category": CategorySerializer(category).data
        }, status=status.HTTP_201_CREATED)


class AdminCategoryDetailUpdateDeleteAPI(APIView):
    """
    API Sửa hoặc Xóa danh mục dịch vụ (UC-3.3)
    """
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền sửa danh mục.'}, status=status.HTTP_403_FORBIDDEN)

        category = get_object_or_404(Category, pk=pk)
        serializer = AdminCategoryWriteSerializer(category, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        updated_cat = serializer.save()
        return Response({
            "status": "success",
            "message": f"Đã cập nhật danh mục '{updated_cat.name}'.",
            "category": CategorySerializer(updated_cat).data
        }, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Bạn không có quyền xóa danh mục.'}, status=status.HTTP_403_FORBIDDEN)

        category = get_object_or_404(Category, pk=pk)
        if category.services.exists():
            return Response({
                "status": "error",
                "message": f"Không thể xóa danh mục '{category.name}' vì vẫn còn {category.services.count()} dịch vụ thuộc danh mục này."
            }, status=status.HTTP_400_BAD_REQUEST)

        name = category.name
        category.delete()
        return Response({
            "status": "success",
            "message": f"Đã xóa danh mục '{name}' thành công!"
        }, status=status.HTTP_200_OK)


class AdminServiceStatsAPI(APIView):
    """
    API Thống kê 4 thẻ KPI đầu trang Quản trị Dịch vụ (UC-3.3)
    Khớp 100% Figma Hình 23:
      - Tổng số Dịch vụ (Tổng cộng trong hệ thống)
      - Số dịch vụ Đang hoạt động
      - Số dịch vụ Đang ẩn / Khóa (Ngừng hoạt động)
      - Số lượng Danh mục
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Không có quyền truy cập.'}, status=status.HTTP_403_FORBIDDEN)

        total_services = Service.objects.count()
        active_services = Service.objects.filter(status='Hoạt động').count()
        inactive_services = Service.objects.filter(status='Ngừng hoạt động').count()
        total_categories = Category.objects.count()

        return Response({
            "total_services": total_services,
            "active_services": active_services,
            "inactive_services": inactive_services,
            "total_categories": total_categories
        }, status=status.HTTP_200_OK)
