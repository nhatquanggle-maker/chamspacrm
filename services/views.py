"""
Django Views cho Phân hệ Quản lý Danh mục & Dịch vụ (MOD-03) - CHAMSPA CRM
Tác giả: Minh Khánh
Use Cases:
  - UC-3.1: Xem danh sách dịch vụ (service_list_view)
  - UC-3.2: Xem chi tiết dịch vụ (service_detail_view)
  - UC-3.3: Quản trị danh mục & dịch vụ cho Quản lý (service_admin_view)
Giao diện tuân thủ chuẩn kế thừa Django Template ({% extends %}), tích hợp Vanilla JS (Fetch API).
"""

import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Min, Max, Count

from core.models import Category, Service, ServiceImage, Feedback
from .serializers import ServiceListSerializer, ServiceDetailSerializer


def service_list_view(request):
    """
    Màn hình Xem danh sách Dịch vụ phía Khách hàng & Khách vãng lai (UC-3.1)
    Khớp 100% Giao diện Figma Node 216-928:
      - Thanh phân loại danh mục (All, Massage Body, Foot, Gội đầu, Facial, Trị liệu...)
      - Khung bộ lọc sidebar (Danh mục, Khoảng giá slider, Thời lượng chips, Đặt lại bộ lọc)
      - Lưới thẻ dịch vụ responsive (Ảnh thumbnail, Tên, Giá VNĐ, Thời lượng, Đánh giá sao, Nút Đặt ngay & Xem chi tiết)
      - Tích hợp Modal Popup Chi tiết dịch vụ (Figma Node 216-929) xem ngay không cần chuyển trang.
    """
    # 1. Lấy danh sách danh mục đang hoạt động
    categories = Category.objects.filter(status='Active').order_by('id')

    # 2. Lấy toàn bộ dịch vụ đang hoạt động
    services_qs = Service.objects.filter(status='Hoạt động').select_related('category').prefetch_related('images').order_by('id')

    # 3. Cấu hình khoảng giá thanh trượt Slider chuẩn Figma (200.000 VNĐ - 2.000.000 VNĐ)
    min_price = 200000
    max_price = 2000000

    # 4. Chuẩn bị danh sách thời lượng tiêu biểu
    durations = [30, 45, 60, 75, 90, 120]

    # 5. Format dữ liệu ban đầu để đưa vào template (SSR kết hợp nạp nhanh)
    services_list = []
    for s in services_qs:
        formatted_price = f"{int(s.price_vnd):,}".replace(',', '.') + " VNĐ"
        s.formatted_price = formatted_price
        services_list.append({
            'id': s.id,
            'code': f"#DVO{s.id:02d}",
            'name': s.name,
            'slug': s.slug,
            'category_id': s.category_id,
            'category_name': s.category.name,
            'category_slug': s.category.slug,
            'thumbnail_url': s.thumbnail_url or '/static/images/treatment_1.png',
            'price_vnd': float(s.price_vnd),
            'formatted_price': formatted_price,
            'duration_minutes': s.duration_minutes,
            'rating_avg': float(s.rating_avg),
            'review_count': s.review_count,
            'description': s.description or ''
        })

    context = {
        'categories': categories,
        'services': services_qs,
        'services_data': services_list,
        'services_json': json.dumps(services_list, ensure_ascii=False),
        'total_services': services_qs.count(),
        'min_price': min_price,
        'max_price': max_price,
        'durations': durations,
    }
    return render(request, 'services/service_list.html', context)


def service_detail_view(request, slug):
    """
    Trang Xem chi tiết Dịch vụ độc lập (UC-3.2)
    Hỗ trợ truy cập trực tiếp qua đường dẫn thân thiện /services/<slug>/
    Khớp 100% Giao diện Figma Node 216-929:
      - Gallery ảnh đa góc chụp (ảnh lớn + 3 thumbnail)
      - Huy hiệu bảo chứng chất lượng & an toàn thảo mộc
      - Bảng giá niêm yết, thời lượng, đánh giá trung bình
      - Khối Accordion 4 bước quy trình trải nghiệm Champa
      - Nhận xét và đánh giá thực tế của khách hàng từ bảng Feedback
      - 2 Nút Call-To-Action: Đặt lịch ngay & Tư vấn qua Chatbot
    """
    service = get_object_or_404(
        Service.objects.select_related('category').prefetch_related('images'),
        slug=slug
    )

    # Bộ sưu tập ảnh gallery
    gallery_images = list(service.images.values_list('image_url', flat=True))
    if not gallery_images and service.thumbnail_url:
        gallery_images = [service.thumbnail_url]

    # Danh sách đánh giá thực tế từ bảng Feedback
    feedbacks = Feedback.objects.filter(
        appointment__details__service=service
    ).exclude(status='Đã ẩn').select_related('customer').order_by('-created_at')[:6]

    # Dịch vụ liên quan trong cùng danh mục
    related_services = Service.objects.filter(
        category=service.category,
        status='Hoạt động'
    ).exclude(id=service.id)[:3]
    for r in related_services:
        r.formatted_price = f"{int(r.price_vnd):,}".replace(',', '.') + " VNĐ"

    # Định dạng giá tiền
    formatted_price = f"{int(service.price_vnd):,}".replace(',', '.') + " VNĐ"

    context = {
        'service': service,
        'formatted_price': formatted_price,
        'service_code': f"#DVO{service.id:02d}",
        'gallery_images': gallery_images,
        'feedbacks': feedbacks,
        'related_services': related_services,
    }
    return render(request, 'services/service_detail.html', context)


@login_required
def service_admin_view(request):
    """
    Màn hình Quản trị Dịch vụ & Danh mục dành cho Quản lý / Ban Giám đốc (UC-3.3)
    Khớp 100% Giao diện Figma Hình 23 (Node quản lý danh mục dịch vụ):
      - 4 Thẻ KPI thống kê: Tổng dịch vụ, Đang hoạt động, Đang ẩn/Khóa, Số danh mục
      - Thanh công cụ lọc nhanh, chọn danh mục, chọn trạng thái, nút Xuất Excel (SheetJS)
      - Nút '+ Thêm dịch vụ mới' mở Modal nhập liệu
      - Bảng dữ liệu Data Table (Mã DV, Ảnh, Tên dịch vụ, Danh mục, Thời lượng, Giá, Trạng thái, Thao tác)
      - Nút Toggle Switch đổi trạng thái trực tiếp bằng Fetch API không tải lại trang
      - Tab Quản lý Danh mục (Category)
    """
    # Chỉ tài khoản Quản lý (is_superuser=True hoặc is_staff=True) mới có quyền truy cập
    if not (request.user.is_superuser or request.user.is_staff):
        raise PermissionDenied("Chỉ Quản lý hoặc Nhân viên có thẩm quyền mới được truy cập trang này.")

    services = Service.objects.all().select_related('category').prefetch_related('images').order_by('id')
    categories = Category.objects.all().annotate(total_svc=Count('services')).order_by('id')

    # Thống kê KPI khớp Figma
    total_services = services.count()
    active_services = services.filter(status='Hoạt động').count()
    inactive_services = services.filter(status='Ngừng hoạt động').count()
    total_categories = categories.count()

    # Dữ liệu JSON cho client-side table & export Excel
    services_admin_data = [
        {
            'id': s.id,
            'code': f"#DVO{s.id:02d}",
            'name': s.name,
            'slug': s.slug,
            'category_id': s.category_id,
            'category_name': s.category.name,
            'thumbnail_url': s.thumbnail_url or '/static/images/treatment_1.png',
            'price_vnd': float(s.price_vnd),
            'formatted_price': f"{int(s.price_vnd):,}".replace(',', '.') + " VNĐ",
            'duration_minutes': s.duration_minutes,
            'status': s.status,
            'is_active': s.status == 'Hoạt động',
            'rating_avg': float(s.rating_avg),
            'review_count': s.review_count,
            'updated_at': s.updated_at.strftime('%d/%m/%Y') if s.updated_at else ''
        }
        for s in services
    ]

    categories_data = [
        {
            'id': c.id,
            'name': c.name,
            'slug': c.slug,
            'status': c.status,
            'is_active': c.status == 'Active',
            'total_services': c.total_svc
        }
        for c in categories
    ]

    context = {
        'services': services,
        'categories': categories,
        'services_admin_data': services_admin_data,
        'categories_data': categories_data,
        'services_admin_json': json.dumps(services_admin_data, ensure_ascii=False),
        'categories_json': json.dumps(categories_data, ensure_ascii=False),
        'total_services': total_services,
        'active_services': active_services,
        'inactive_services': inactive_services,
        'total_categories': total_categories,
    }
    return render(request, 'services/service_admin.html', context)
