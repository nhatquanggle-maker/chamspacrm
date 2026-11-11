from decimal import Decimal
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.ajax import require_staff_json
from core.models import Appointment, Membership, Tier, User


def _serialize_point(pt):
    code = str(pt.appointment_id).strip() if pt.appointment_id else ''
    if not code:
        display_code = '#HD-CHAMSPA'
    elif code.isdigit():
        appt = Appointment.objects.filter(id=int(code)).first()
        raw_c = appt.appointment_code if (appt and appt.appointment_code) else code
        display_code = raw_c if raw_c.startswith('#') else f'#{raw_c}'
    else:
        display_code = code if code.startswith('#') else f'#{code}'

    formatted_created = timezone.localtime(pt.created_at).strftime('%d/%m/%Y %H:%M') if pt.created_at else ''
    return {
        'id': pt.id,
        'appointment_id': pt.appointment_id,
        'display_code': display_code,
        'points_amount': pt.points_amount,
        'reason_description': pt.reason_description,
        'created_at': pt.created_at.isoformat() if pt.created_at else None,
        'formatted_created_at': formatted_created,
        'is_positive': pt.points_amount > 0,
    }


def _serialize_lookup(obj):
    profile = getattr(obj.user, 'profile', None)
    spent = int(obj.total_spent or 0)
    recent = obj.point_history.all().order_by('-created_at')[:5]
    return {
        'id': obj.id,
        'customer_id': obj.user_id,
        'customer_name': obj.user.name if obj.user else '',
        'customer_phone': obj.user.phone if obj.user else '',
        'customer_email': obj.user.email if obj.user else '',
        'customer_code': f'CUS{obj.user_id:03d}',
        'avatar': profile.avatar if (profile and profile.avatar) else '',
        'tier_name': obj.tier.name if obj.tier else 'Hạng Đồng',
        'discount_percent': obj.tier.discount_percent if obj.tier else 0,
        'tier_description': obj.tier.description if obj.tier else 'Chưa có mô tả quyền lợi',
        'current_points': obj.current_points,
        'formatted_current_points': f'{obj.current_points:,}'.replace(',', '.'),
        'total_points_used': obj.total_points_used,
        'total_spent': float(obj.total_spent or 0),
        'formatted_total_spent': f'{spent:,}'.replace(',', '.') + ' VNĐ',
        'tier_expiration_date': obj.tier_expiration_date.isoformat() if obj.tier_expiration_date else None,
        'created_at': obj.created_at.isoformat() if obj.created_at else None,
        'recent_history': [_serialize_point(pt) for pt in recent],
    }


@require_GET
@require_staff_json
def lookup_api(request):
    """[UC-6.2] Tra cứu thông tin hội viên tại quầy (chỉ Staff/Admin)."""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({
            'status': 'error',
            'error': 'Vui lòng cung cấp số điện thoại hoặc từ khóa tìm kiếm (?q=...)',
        }, status=400)

    clean_phone = query.replace(' ', '').replace('.', '').replace('-', '')
    q_filter = (
        Q(user__phone__icontains=clean_phone) |
        Q(user__name__icontains=query) |
        Q(user__email__icontains=query)
    )
    if query.upper().startswith('CUS') and query[3:].isdigit():
        q_filter |= Q(user__id=int(query[3:]))
    elif query.isdigit():
        q_filter |= Q(user__id=int(query))

    memberships = (
        Membership.objects.filter(q_filter)
        .select_related('user', 'tier', 'user__profile')
        .prefetch_related('point_history')[:10]
    )

    if not memberships.exists():
        unlinked_users = (
            User.objects.filter(
                Q(phone__icontains=clean_phone) | Q(name__icontains=query) | Q(email__icontains=query)
            )
            .filter(membership__isnull=True)[:5]
        )
        default_tier = Tier.objects.filter(min_points=0).order_by('min_points').first()
        for u in unlinked_users:
            Membership.objects.create(
                user=u, tier=default_tier, current_points=0, total_points_used=0, total_spent=Decimal(0),
            )
        memberships = (
            Membership.objects.filter(q_filter)
            .select_related('user', 'tier', 'user__profile')
            .prefetch_related('point_history')[:10]
        )

    results = [_serialize_lookup(m) for m in memberships]
    return JsonResponse({'status': 'success', 'count': len(results), 'results': results})
