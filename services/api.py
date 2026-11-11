import math
from decimal import Decimal

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from core.models import Feedback, Service


def _fmt_price(price_vnd):
    try:
        return f"{int(price_vnd):,}".replace(',', '.') + ' VNĐ'
    except (ValueError, TypeError):
        return '0 VNĐ'


def _serialize_category(cat):
    if not cat:
        return None
    return {
        'id': cat.id,
        'name': cat.name,
        'slug': cat.slug,
        'status': cat.status,
        'services_count': cat.services.filter(status='Hoạt động').count(),
        'created_at': cat.created_at.isoformat() if cat.created_at else None,
        'updated_at': cat.updated_at.isoformat() if cat.updated_at else None,
    }


def _serialize_service_list(service):
    updated_date = ''
    if service.updated_at:
        updated_date = service.updated_at.strftime('%d/%m/%Y')
    elif service.created_at:
        updated_date = service.created_at.strftime('%d/%m/%Y')
    return {
        'id': service.id,
        'code': f'#DVO{service.id:02d}',
        'name': service.name,
        'slug': service.slug,
        'category': _serialize_category(service.category),
        'category_name': service.category.name if service.category else '',
        'thumbnail_url': service.thumbnail_url,
        'description': service.description,
        'price_vnd': float(service.price_vnd),
        'formatted_price': _fmt_price(service.price_vnd),
        'duration_minutes': service.duration_minutes,
        'status': service.status,
        'rating_avg': float(service.rating_avg or 0),
        'review_count': int(service.review_count or 0),
        'updated_date_formatted': updated_date,
        'created_at': service.created_at.isoformat() if service.created_at else None,
        'updated_at': service.updated_at.isoformat() if service.updated_at else None,
    }


def _serialize_service_feedback(fb):
    avatar_url = '/static/images/chamspa-logo.png'
    if fb.customer and hasattr(fb.customer, 'profile') and fb.customer.profile.avatar:
        av = fb.customer.profile.avatar
        avatar_url = av.url if hasattr(av, 'url') else str(av)
    return {
        'id': fb.id,
        'feedback_code': fb.feedback_code,
        'customer_name': fb.customer.name if fb.customer else 'Khách hàng',
        'customer_avatar': avatar_url,
        'rating': fb.rating,
        'tags': fb.tags or [],
        'comment': fb.comment,
        'attached_media': fb.attached_media or [],
        'reply': fb.reply,
        'replied_by': fb.replied_by,
        'replied_at': fb.replied_at.isoformat() if fb.replied_at else None,
        'date_formatted': fb.created_at.strftime('%d/%m/%Y') if fb.created_at else '',
        'created_at': fb.created_at.isoformat() if fb.created_at else None,
    }


def _serialize_service_detail(service):
    urls = list(service.images.values_list('image_url', flat=True))
    if not urls and service.thumbnail_url:
        urls = [service.thumbnail_url]

    feedbacks = (
        Feedback.objects.filter(appointment__details__service=service)
        .exclude(status='Đã ẩn')
        .select_related('customer', 'customer__profile')
        .order_by('-created_at')[:10]
    )

    data = _serialize_service_list(service)
    data.update({
        'images': urls,
        'feedbacks': [_serialize_service_feedback(fb) for fb in feedbacks],
        'process_steps': [
            {
                'step': 1,
                'title': 'Thăm vấn',
                'icon': 'bi-chat-heart',
                'description': 'Chuyên viên lắng nghe tình trạng cơ thể, xác định điểm căng cơ và mức áp lực phù hợp theo thể trạng riêng của quý khách.',
            },
            {
                'step': 2,
                'title': 'Khởi động',
                'icon': 'bi-flower1',
                'description': 'Thưởng thức trà thảo mộc ấm, ngâm chân muối khoáng thảo dược cổ truyền người Dao Đỏ và làm ấm cơ thể trong không gian thư thái.',
            },
            {
                'step': 3,
                'title': 'Ấn huyệt trị liệu',
                'icon': 'bi-hand-index-thumb',
                'description': f'Áp dụng kỹ thuật bấm huyệt Đông y Champa chuyên sâu cho gói {service.name}, giải phóng ứ trệ và đả thông kinh lạc toàn thân.',
            },
            {
                'step': 4,
                'title': 'Đá nóng Champa',
                'icon': 'bi-gem',
                'description': 'Sử dụng đá bazan núi lửa tự nhiên hấp nóng kết hợp tinh dầu trầm hương Cham Spa giúp thẩm thấu dưỡng chất và đưa cơ thể vào trạng thái thư giãn sâu.',
            },
        ],
    })
    return data


@require_GET
def service_list_api(request):
    """[UC-3.1] Lấy danh sách dịch vụ hoạt động kèm lọc & phân trang."""
    queryset = Service.objects.filter(status='Hoạt động').select_related('category').prefetch_related('images')

    category_slug = request.GET.get('category_slug', '').strip()
    if category_slug and category_slug.lower() not in ('all', 'tat-ca'):
        queryset = queryset.filter(category__slug=category_slug)

    search_query = request.GET.get('search', '').strip()
    if search_query:
        queryset = queryset.filter(Q(name__icontains=search_query) | Q(description__icontains=search_query))

    for param, lookup in (('min_price', 'price_vnd__gte'), ('max_price', 'price_vnd__lte')):
        val = request.GET.get(param, '').strip()
        if val:
            try:
                queryset = queryset.filter(**{lookup: Decimal(val)})
            except Exception:
                pass

    duration = request.GET.get('duration', '').strip()
    if duration.isdigit():
        queryset = queryset.filter(duration_minutes=int(duration))

    sort_by = request.GET.get('sort', 'default').strip().lower()
    order_map = {
        'price_asc': ('price_vnd',),
        'price_desc': ('-price_vnd',),
        'rating': ('-rating_avg', '-review_count'),
        'popular': ('-review_count', '-rating_avg'),
    }
    queryset = queryset.order_by(*order_map.get(sort_by, ('id',)))

    total_count = queryset.count()
    try:
        page = max(1, int(request.GET.get('page', 1)))
    except ValueError:
        page = 1
    try:
        page_size = max(1, int(request.GET.get('page_size', 9)))
    except ValueError:
        page_size = 9

    start = (page - 1) * page_size
    results = [_serialize_service_list(s) for s in queryset[start:start + page_size]]

    return JsonResponse({
        'count': len(results),
        'total': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, math.ceil(total_count / page_size)),
        'results': results,
    })


@require_GET
def service_detail_api(request, slug):
    """Lấy chi tiết dịch vụ theo slug."""
    service = get_object_or_404(
        Service.objects.select_related('category').prefetch_related('images'),
        slug=slug,
    )
    return JsonResponse(_serialize_service_detail(service))
