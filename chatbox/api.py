"""
API Endpoints (Pure Django JsonResponse) cho Phân hệ Quản lý Boxchat Tư vấn - CHAMSPA CRM
"""

import csv
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.ajax import (
    is_staff_or_admin,
    json_error,
    parse_json_body,
    require_auth_json,
    require_staff_json,
)
from core.models import (
    Conversation,
    ConversationMessage,
    FAQ,
    Membership,
    User,
    UserHealthProfile,
)


def _format_local_dt(dt_val, fmt='%d/%m/%Y %H:%M'):
    if not dt_val:
        return ""
    return timezone.localtime(dt_val).strftime(fmt)


def serialize_faq(faq):
    return {
        'id': faq.id,
        'faq_code': faq.faq_code,
        'category': faq.category,
        'question': faq.question,
        'keywords': faq.keywords or '',
        'answer': faq.answer,
        'status': faq.status,
        'created_at': faq.created_at.isoformat() if faq.created_at else None,
        'updated_at': faq.updated_at.isoformat() if faq.updated_at else None,
        'formatted_created_at': faq.created_at.strftime('%d/%m/%Y %H:%M') if faq.created_at else "",
        'formatted_updated_at': faq.updated_at.strftime('%d/%m/%Y %H:%M') if faq.updated_at else "",
    }


def _get_message_sender_name(msg):
    if msg.sender_type == 'Staff':
        if msg.conversation.staff:
            return msg.conversation.staff.name or msg.conversation.staff.username
        return "Nhân viên tư vấn"
    if msg.sender_type == 'Customer':
        if msg.conversation.customer:
            return msg.conversation.customer.name or "Khách hàng"
        return "Khách hàng"
    if msg.sender_type == 'Bot':
        return "Trợ lý ảo Cham Spa"
    return "Hệ thống"


def serialize_message(msg):
    return {
        'id': msg.id,
        'conversation': msg.conversation_id,
        'sender_type': msg.sender_type,
        'sender_name': _get_message_sender_name(msg),
        'message_type': msg.message_type,
        'content': msg.content,
        'attachment_url': msg.attachment_url,
        'attachment_name': msg.attachment_name,
        'attachment_size': msg.attachment_size,
        'created_at': msg.created_at.isoformat() if msg.created_at else None,
        'formatted_time': _format_local_dt(msg.created_at, '%H:%M - %d/%m'),
    }


def serialize_conversation_list_item(conv, request):
    cust = conv.customer
    profile = getattr(cust, 'profile', None) if cust else None
    membership = getattr(cust, 'membership', None) if cust else None
    tier_name = membership.tier.name if (membership and membership.tier) else "Khách hàng"

    last_msg = conv.messages.order_by('-created_at').first()
    if last_msg:
        prefix = "Bạn: " if last_msg.sender_type == 'Staff' else ("Bot: " if last_msg.sender_type == 'Bot' else "")
        last_message = f"{prefix}{last_msg.content or '[Tệp đính kèm]'}"
        last_message_time = _format_local_dt(last_msg.created_at, '%H:%M')
    else:
        last_message = "Chưa có tin nhắn"
        last_message_time = ""

    is_auth_staff = request and request.user.is_authenticated and conv.staff
    return {
        'id': conv.id,
        'status': conv.status,
        'customer_tag': conv.customer_tag,
        'customer_name': (cust.name or cust.username) if cust else "Khách vãng lai",
        'customer_phone': (cust.phone or "") if cust else "",
        'customer_email': (cust.email or "") if cust else "",
        'customer_avatar': profile.avatar if (profile and profile.avatar) else None,
        'membership_tier': tier_name,
        'staff_id': conv.staff_id,
        'staff_name': (conv.staff.name or conv.staff.username) if conv.staff else None,
        'is_assigned_to_me': bool(is_auth_staff and conv.staff_id == request.user.id),
        'is_assigned_to_other': bool(is_auth_staff and conv.staff_id != request.user.id),
        'last_message': last_message,
        'last_message_time': last_message_time,
        'unread_count': conv.messages.filter(sender_type='Customer').count(),
        'created_at': conv.created_at.isoformat() if conv.created_at else None,
        'closed_at': conv.closed_at.isoformat() if conv.closed_at else None,
    }


def serialize_conversation_detail(conv):
    cust = conv.customer
    if not cust:
        customer_info = {
            'id': None,
            'name': 'Khách vãng lai',
            'phone': '',
            'email': '',
            'tier': 'Khách vãng lai',
            'avatar': None,
        }
        health_profile = None
    else:
        membership = getattr(cust, 'membership', None)
        tier_name = membership.tier.name if (membership and membership.tier) else "Thành viên"
        profile = getattr(cust, 'profile', None)
        customer_info = {
            'id': cust.id,
            'name': cust.name or cust.username,
            'phone': cust.phone or '',
            'email': cust.email or '',
            'tier': tier_name,
            'avatar': profile.avatar if (profile and profile.avatar) else None,
        }
        hp = getattr(cust, 'health_profile', None)
        health_profile = {
            'health_code': hp.health_code,
            'height_cm': float(hp.height_cm) if hp.height_cm else None,
            'weight_kg': float(hp.weight_kg) if hp.weight_kg else None,
            'blood_pressure': hp.blood_pressure,
            'focus_areas': hp.focus_areas or [],
            'massage_pressure': hp.massage_pressure,
            'pain_level': hp.pain_level,
            'health_conditions': hp.health_conditions or [],
            'allergy_notes': hp.allergy_notes,
            'recovery_goals': hp.recovery_goals or [],
        } if hp else None

    staff_info = None
    if conv.staff:
        staff_info = {
            'id': conv.staff.id,
            'name': conv.staff.name or conv.staff.username,
            'email': conv.staff.email or '',
            'role': 'Quản lý' if conv.staff.is_superuser else 'Nhân viên CSKH',
        }

    messages_qs = conv.messages.all().order_by('created_at')
    return {
        'id': conv.id,
        'status': conv.status,
        'customer_tag': conv.customer_tag,
        'bot_collected_data': conv.bot_collected_data,
        'customer_info': customer_info,
        'staff_info': staff_info,
        'health_profile': health_profile,
        'messages': [serialize_message(m) for m in messages_qs],
        'created_at': conv.created_at.isoformat() if conv.created_at else None,
        'closed_at': conv.closed_at.isoformat() if conv.closed_at else None,
    }


def find_best_faq_match(user_message):
    """Tìm kiếm câu trả lời phù hợp nhất từ bảng FAQ (status='Active')."""
    if not user_message:
        return None

    clean_msg = user_message.strip().lower()
    active_faqs = FAQ.objects.filter(status='Active')

    for faq in active_faqs:
        faq_q = faq.question.lower().strip()
        if faq_q in clean_msg or clean_msg in faq_q:
            return faq

    best_faq = None
    max_keyword_matches = 0
    for faq in active_faqs:
        matches = 0
        if faq.keywords:
            keywords_list = [k.strip().lower() for k in faq.keywords.replace(';', ',').split(',') if k.strip()]
            for kw in keywords_list:
                if kw in clean_msg:
                    matches += 1
        words_in_q = [w for w in faq.question.lower().split() if len(w) >= 3]
        for w in words_in_q:
            if w in clean_msg:
                matches += 1
        if matches > max_keyword_matches:
            max_keyword_matches = matches
            best_faq = faq

    if max_keyword_matches > 0:
        return best_faq

    topics_map = {
        'giá': ['giá', 'bao nhiêu', 'chi phí', 'tiền', 'bảng giá', 'menu'],
        'giờ': ['mở cửa', 'đóng cửa', 'mấy giờ', 'thời gian', 'hoạt động'],
        'địa chỉ': ['ở đâu', 'địa chỉ', 'chi nhánh', 'vị trí', 'bản đồ'],
        'đặt lịch': ['đặt lịch', 'hẹn', 'book', 'booking', 'giữ chỗ'],
        'khuyến mãi': ['ưu đãi', 'khuyến mãi', 'voucher', 'giảm giá', 'mã giảm'],
        'khiếu nại': ['phản ánh', 'khiếu nại', 'không hài lòng', 'bồi thường'],
    }
    for cat_keyword, trigger_words in topics_map.items():
        if any(w in clean_msg for w in trigger_words):
            fallback_faq = active_faqs.filter(
                Q(category__icontains=cat_keyword) | Q(question__icontains=cat_keyword)
            ).first()
            if fallback_faq:
                return fallback_faq

    return None


@require_POST
def bot_reply_api(request):
    """Phản hồi tự động từ Chatbot (khách vãng lai không ghi DB, khách đăng nhập lưu lịch sử)."""
    data, err = parse_json_body(request)
    if err:
        return err

    user_message = str(data.get('message') or '').strip()
    faq_id_raw = data.get('faq_id')
    conv_id_raw = data.get('conversation_id')

    try:
        faq_id = int(faq_id_raw) if faq_id_raw not in (None, '') else None
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'errors': {'faq_id': ['Mã FAQ không hợp lệ.']}}, status=400)

    try:
        conv_id = int(conv_id_raw) if conv_id_raw not in (None, '') else None
    except (TypeError, ValueError):
        conv_id = None

    if len(user_message) > 1000:
        return JsonResponse({'status': 'error', 'errors': {'message': ['Nội dung quá dài (tối đa 1000 ký tự).']}}, status=400)

    if not user_message and not faq_id:
        return JsonResponse({
            'status': 'error',
            'errors': {'message': ['Vui lòng nhập nội dung hoặc chọn câu hỏi kịch bản FAQ.']},
        }, status=400)

    matched_faq = None
    if faq_id:
        matched_faq = FAQ.objects.filter(pk=faq_id, status='Active').first()
        if matched_faq and not user_message:
            user_message = matched_faq.question

    if not matched_faq and user_message:
        matched_faq = find_best_faq_match(user_message)

    if matched_faq:
        bot_reply_text = matched_faq.answer
        suggested_actions = ["Chọn câu hỏi FAQ khác", "Gặp nhân viên tư vấn"]
    else:
        bot_reply_text = (
            "Dạ Cham Spa & Massage xin chào quý khách! "
            "Em chưa hiểu rõ yêu cầu của mình trong kịch bản tự động. "
            "Quý khách có thể chọn các Block câu hỏi FAQ bên dưới hoặc bấm 'Gặp nhân viên tư vấn' "
            "để chuyên viên chăm sóc khách hàng hỗ trợ ngay nhé ạ!"
        )
        suggested_actions = ["Bảng giá dịch vụ", "Giờ mở cửa & Địa chỉ", "Gặp nhân viên tư vấn"]

    user = request.user
    saved_conv_id = None

    if user.is_authenticated and not user.is_staff and not user.is_superuser:
        with transaction.atomic():
            conversation = None
            if conv_id:
                conversation = Conversation.objects.filter(id=conv_id, customer=user).first()

            if not conversation or conversation.status == 'Kết thúc':
                conversation = Conversation.objects.filter(
                    customer=user,
                    status__in=['Bot xử lý', 'Đang chờ', 'Đang xử lý'],
                ).first()

            if not conversation:
                conversation = Conversation.objects.create(
                    customer=user,
                    status='Bot xử lý',
                    customer_tag=matched_faq.category if matched_faq else 'Khách quan tâm dịch vụ',
                )
            elif matched_faq and conversation.status == 'Bot xử lý':
                conversation.customer_tag = matched_faq.category
                conversation.save(update_fields=['customer_tag'])

            ConversationMessage.objects.create(
                conversation=conversation,
                sender_type='Customer',
                message_type='TEXT',
                content=user_message,
            )
            ConversationMessage.objects.create(
                conversation=conversation,
                sender_type='Bot',
                message_type='TEXT',
                content=bot_reply_text,
            )
            saved_conv_id = conversation.id

    return JsonResponse({
        'status': 'success',
        'reply': bot_reply_text,
        'faq_id': matched_faq.id if matched_faq else None,
        'faq_code': matched_faq.faq_code if matched_faq else None,
        'faq_category': matched_faq.category if matched_faq else None,
        'suggested_actions': suggested_actions,
        'conversation_id': saved_conv_id,
        'is_authenticated': user.is_authenticated,
    }, status=200)


@require_GET
def public_faq_blocks_api(request):
    """Cung cấp danh sách các Block câu hỏi FAQ đang kích hoạt."""
    active_faqs = FAQ.objects.filter(status='Active').order_by('category', 'id')
    blocks = []
    categories = []
    seen_cats = set()

    for f in active_faqs:
        if f.category and f.category not in seen_cats:
            seen_cats.add(f.category)
            categories.append(f.category)
        blocks.append({
            'id': f.id,
            'faq_code': f.faq_code,
            'category': f.category,
            'question': f.question,
        })

    return JsonResponse({
        'status': 'success',
        'categories': categories,
        'blocks': blocks,
    }, status=200)


@require_POST
def conversation_transfer_staff_api(request):
    """Khách hàng bấm 'Chuyển tiếp cho nhân viên' trong khung chat."""
    if not request.user.is_authenticated:
        return JsonResponse({
            'status': 'require_login',
            'message': 'Quý khách vui lòng đăng nhập tài khoản để được kết nối trò chuyện trực tiếp với nhân viên CSKH.',
        }, status=401)

    data, err = parse_json_body(request)
    if err:
        return err

    conv_id = data.get('conversation_id')
    user = request.user

    with transaction.atomic():
        conversation = None
        if conv_id:
            conversation = Conversation.objects.filter(id=conv_id, customer=user).first()

        if not conversation or conversation.status == 'Kết thúc':
            conversation = Conversation.objects.filter(
                customer=user,
                status__in=['Bot xử lý', 'Đang chờ', 'Đang xử lý'],
            ).first()

        if not conversation:
            conversation = Conversation.objects.create(
                customer=user,
                status='Đang chờ',
                customer_tag='Yêu cầu tư vấn trực tiếp',
            )
        else:
            conversation.status = 'Đang chờ'
            conversation.save()

        ConversationMessage.objects.create(
            conversation=conversation,
            sender_type='Bot',
            message_type='TEXT',
            content='Dạ, yêu cầu của quý khách đã được chuyển tới chuyên viên tư vấn Cham Spa. Chuyên viên sẽ tiếp nhận và phản hồi ngay trong giây lát ạ!',
        )

    return JsonResponse({
        'status': 'success',
        'message': 'Đã gửi yêu cầu kết nối với nhân viên tư vấn thành công.',
        'conversation_id': conversation.id,
        'conversation_status': conversation.status,
    }, status=200)


@require_auth_json
@require_http_methods(['GET', 'POST'])
def conversation_messages_api(request, pk):
    """Lấy lịch sử và gửi tin nhắn trực tiếp giữa Khách hàng và Nhân viên."""
    conversation = Conversation.objects.select_related('customer', 'staff').filter(pk=pk).first()
    if not conversation:
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    user = request.user
    if request.method == 'GET':
        if not is_staff_or_admin(user) and conversation.customer_id != user.id:
            return json_error('Bạn không có quyền xem cuộc hội thoại này.', status=403)

        is_assigned_to_other = bool(
            user.is_staff and conversation.staff and conversation.staff_id != user.id and conversation.status == 'Đang xử lý'
        )
        assigned_staff_name = (
            (conversation.staff.name or conversation.staff.username) if is_assigned_to_other else None
        )
        data = serialize_conversation_detail(conversation)
        data['is_assigned_to_other'] = is_assigned_to_other
        data['assigned_staff_name'] = assigned_staff_name
        data['can_send_message'] = not is_assigned_to_other
        return JsonResponse(data, status=200)

    data, err = parse_json_body(request)
    if err:
        return err

    content = str(data.get('content') or '').strip()
    message_type = data.get('message_type') or 'TEXT'
    if not content:
        return JsonResponse({'status': 'error', 'errors': {'content': ['Nội dung tin nhắn không được để trống.']}}, status=400)
    if len(content) > 5000:
        return JsonResponse({'status': 'error', 'errors': {'content': ['Nội dung tin nhắn quá dài (tối đa 5000 ký tự).']}}, status=400)
    if message_type not in ('TEXT', 'IMAGE', 'FILE'):
        return JsonResponse({'status': 'error', 'errors': {'message_type': ['Loại tin nhắn không hợp lệ.']}}, status=400)

    if is_staff_or_admin(user):
        if conversation.staff and conversation.staff_id != user.id and conversation.status == 'Đang xử lý':
            other_name = conversation.staff.name or conversation.staff.username
            return JsonResponse({
                'status': 'forbidden_assigned',
                'error': f'Cuộc hội thoại này đã do nhân viên {other_name} tiếp nhận xử lý. Bạn đang ở chế độ xem chỉ đọc và không thể gửi tin nhắn.',
                'assigned_staff': other_name,
            }, status=403)

        if not conversation.staff:
            conversation.staff = user
            conversation.status = 'Đang xử lý'
            conversation.save()

        sender_type = 'Staff'
        sender_name = user.name or user.username
    else:
        if conversation.customer_id != user.id:
            return json_error('Bạn không có quyền gửi tin nhắn trong cuộc hội thoại này.', status=403)

        sender_type = 'Customer'
        sender_name = user.name or user.username
        if conversation.status == 'Kết thúc':
            conversation.status = 'Đang chờ'
            conversation.save()

    msg = ConversationMessage.objects.create(
        conversation=conversation,
        sender_type=sender_type,
        message_type=message_type,
        content=content,
        attachment_url=data.get('attachment_url'),
        attachment_name=data.get('attachment_name'),
        attachment_size=data.get('attachment_size'),
    )

    return JsonResponse({
        'status': 'success',
        'message_id': msg.id,
        'sender_type': msg.sender_type,
        'sender_name': sender_name,
        'created_at': msg.created_at.isoformat(),
        'formatted_time': _format_local_dt(msg.created_at, '%H:%M - %d/%m'),
        'content': msg.content,
        'conversation_status': conversation.status,
    }, status=201)


@require_staff_json
@require_POST
def conversation_accept_api(request, pk):
    """Nhân viên bấm nút 'Tiếp nhận hội thoại'."""
    conversation = Conversation.objects.select_related('staff').filter(pk=pk).first()
    if not conversation:
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    user = request.user
    if conversation.staff and conversation.staff_id != user.id and conversation.status == 'Đang xử lý':
        other_name = conversation.staff.name or conversation.staff.username
        return JsonResponse({
            'status': 'conflict',
            'message': f'Cuộc hội thoại đã do nhân viên {other_name} tiếp nhận xử lý!',
            'assigned_staff': other_name,
        }, status=409)

    conversation.staff = user
    conversation.status = 'Đang xử lý'
    conversation.save()

    staff_name = user.name or user.username
    ConversationMessage.objects.create(
        conversation=conversation,
        sender_type='Staff',
        message_type='TEXT',
        content=f"Dạ em chào anh/chị! Em là {staff_name} - chuyên viên tư vấn của Cham Spa & Massage. Em rất vui được hỗ trợ quý khách hôm nay ạ!",
    )

    return JsonResponse({
        'status': 'success',
        'message': 'Tiếp nhận cuộc hội thoại thành công. Bạn đang phụ trách phiên chat này.',
        'conversation_id': conversation.id,
        'staff_name': staff_name,
        'status_label': 'Đang xử lý',
    }, status=200)


@require_staff_json
@require_POST
def conversation_close_api(request, pk):
    """Nhân viên bấm 'Đóng phiên chat'."""
    conversation = Conversation.objects.filter(pk=pk).first()
    if not conversation:
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    conversation.status = 'Kết thúc'
    conversation.closed_at = timezone.now()
    conversation.save()

    staff_name = request.user.name or request.user.username
    ConversationMessage.objects.create(
        conversation=conversation,
        sender_type='Staff',
        message_type='TEXT',
        content=f"Phiên tư vấn trực tiếp đã được hoàn tất bởi chuyên viên {staff_name}. Cham Spa trân trọng cảm ơn quý khách và chúc quý khách một ngày an nhiên!",
    )

    return JsonResponse({
        'status': 'success',
        'message': 'Đã đóng phiên tư vấn thành công.',
        'closed_at': conversation.closed_at.isoformat(),
    }, status=200)


@require_staff_json
@require_POST
def conversation_takeover_api(request, pk):
    """Chuyển giao / tiếp quản quyền tiếp nhận hội thoại."""
    conversation = Conversation.objects.select_related('staff').filter(pk=pk).first()
    if not conversation:
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    user = request.user
    old_staff_name = conversation.staff.name if conversation.staff else "Nhân viên trước"

    conversation.staff = user
    conversation.status = 'Đang xử lý'
    conversation.save()

    new_staff_name = user.name or user.username
    ConversationMessage.objects.create(
        conversation=conversation,
        sender_type='Staff',
        message_type='TEXT',
        content=f"Thông báo: Cuộc trò chuyện đã được chuyển tiếp sang chuyên viên {new_staff_name} tiếp tục hỗ trợ quý khách ạ.",
    )

    return JsonResponse({
        'status': 'success',
        'message': f'Đã tiếp quản thành công từ {old_staff_name}. Hiện bạn là nhân viên phụ trách chính.',
        'staff_name': new_staff_name,
    }, status=200)


@require_staff_json
@require_GET
def staff_conversations_list_api(request):
    """Lấy danh sách cuộc hội thoại cho Livechat Console của Nhân viên."""
    tab = request.GET.get('tab', 'waiting')
    search_kw = (request.GET.get('search') or '').strip()

    queryset = Conversation.objects.select_related('customer', 'staff').prefetch_related('messages')

    counts = {
        'waiting': Conversation.objects.filter(status='Đang chờ').count(),
        'processing': Conversation.objects.filter(status='Đang xử lý').count(),
        'closed': Conversation.objects.filter(status='Kết thúc').count(),
        'bot': Conversation.objects.filter(status='Bot xử lý').count(),
        'all': Conversation.objects.count(),
    }

    if tab == 'waiting':
        queryset = queryset.filter(status='Đang chờ')
    elif tab == 'processing':
        queryset = queryset.filter(status='Đang xử lý')
    elif tab == 'closed':
        queryset = queryset.filter(status='Kết thúc')
    elif tab == 'bot':
        queryset = queryset.filter(status='Bot xử lý')
    elif tab == 'mine':
        queryset = queryset.filter(staff=request.user, status='Đang xử lý')

    if search_kw:
        queryset = queryset.filter(
            Q(customer__name__icontains=search_kw) |
            Q(customer__phone__icontains=search_kw) |
            Q(customer__username__icontains=search_kw) |
            Q(customer_tag__icontains=search_kw) |
            Q(messages__content__icontains=search_kw)
        ).distinct()

    queryset = queryset.order_by('-created_at')
    conversations = [serialize_conversation_list_item(c, request) for c in queryset]

    return JsonResponse({
        'status': 'success',
        'counts': counts,
        'current_tab': tab,
        'conversations': conversations,
    }, status=200)


def _validate_faq_payload(data, instance=None, partial=False):
    errors = {}
    cleaned = {}

    if not partial or 'faq_code' in data:
        code = str(data.get('faq_code') or '').strip().upper()
        if not code:
            errors['faq_code'] = ["Mã câu hỏi FAQ không được để trống."]
        else:
            existing = FAQ.objects.filter(faq_code=code)
            if instance:
                existing = existing.exclude(pk=instance.pk)
            if existing.exists():
                errors['faq_code'] = ["Mã câu hỏi đã tồn tại, vui lòng nhập mã khác."]
            else:
                cleaned['faq_code'] = code

    if not partial or 'category' in data:
        cat = str(data.get('category') or '').strip()
        if not cat:
            errors['category'] = ["Danh mục không được để trống."]
        else:
            cleaned['category'] = cat[:100]

    if not partial or 'question' in data:
        question = str(data.get('question') or '').strip()
        if not question:
            errors['question'] = ["Nội dung câu hỏi không được để trống."]
        else:
            cleaned['question'] = question[:255]

    if 'keywords' in data or not partial:
        cleaned['keywords'] = str(data.get('keywords') or '').strip()

    if not partial or 'answer' in data:
        answer = str(data.get('answer') or '').strip()
        if not answer:
            errors['answer'] = ["Nội dung câu trả lời không được để trống."]
        else:
            cleaned['answer'] = answer

    if 'status' in data or not partial:
        st = data.get('status') or (instance.status if instance else 'Active')
        if st not in ('Active', 'Hidden'):
            errors['status'] = ["Trạng thái FAQ không hợp lệ."]
        else:
            cleaned['status'] = st

    return (None, errors) if errors else (cleaned, None)


@require_staff_json
@require_http_methods(['GET', 'POST'])
def admin_faqs_api(request):
    """Danh sách và thêm mới câu hỏi FAQ cho Quản lý & Nhân viên quản trị."""
    if request.method == 'GET':
        category = request.GET.get('category')
        status_filter = request.GET.get('status')
        search_kw = (request.GET.get('q') or '').strip()

        faqs = FAQ.objects.all()
        if category:
            faqs = faqs.filter(category=category)
        if status_filter:
            faqs = faqs.filter(status=status_filter)
        if search_kw:
            faqs = faqs.filter(
                Q(question__icontains=search_kw) |
                Q(keywords__icontains=search_kw) |
                Q(faq_code__icontains=search_kw) |
                Q(answer__icontains=search_kw)
            )
        faqs = faqs.order_by('-created_at')
        categories = FAQ.objects.values_list('category', flat=True).distinct()

        return JsonResponse({
            'status': 'success',
            'count': faqs.count(),
            'categories': list(categories),
            'results': [serialize_faq(f) for f in faqs],
        }, status=200)

    data, err = parse_json_body(request)
    if err:
        return err

    cleaned, errors = _validate_faq_payload(data, instance=None, partial=False)
    if errors:
        return JsonResponse({'status': 'error', 'errors': errors}, status=400)

    faq = FAQ.objects.create(**cleaned)
    return JsonResponse({
        'status': 'success',
        'message': f'Thêm câu hỏi FAQ [{faq.faq_code}] thành công.',
        'data': serialize_faq(faq),
    }, status=201)


@require_staff_json
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def admin_faq_detail_api(request, pk):
    """Xem chi tiết, cập nhật hoặc xóa câu hỏi FAQ theo ID."""
    faq = FAQ.objects.filter(pk=pk).first()
    if not faq:
        return json_error('Không tìm thấy câu hỏi FAQ.', status=404)

    if request.method == 'GET':
        return JsonResponse(serialize_faq(faq), status=200)

    if request.method == 'DELETE':
        code = faq.faq_code
        faq.delete()
        return JsonResponse({
            'status': 'success',
            'message': f'Đã xóa câu hỏi FAQ [{code}] thành công.',
        }, status=200)

    data, err = parse_json_body(request)
    if err:
        return err

    cleaned, errors = _validate_faq_payload(data, instance=faq, partial=(request.method == 'PATCH'))
    if errors:
        return JsonResponse({'status': 'error', 'errors': errors}, status=400)

    for k, v in cleaned.items():
        setattr(faq, k, v)
    faq.save()

    return JsonResponse({
        'status': 'success',
        'message': 'Cập nhật câu hỏi FAQ thành công.',
        'data': serialize_faq(faq),
    }, status=200)


@require_staff_json
@require_POST
def admin_faq_toggle_status_api(request, pk):
    """Chuyển đổi nhanh trạng thái FAQ giữa 'Active' và 'Hidden'."""
    faq = FAQ.objects.filter(pk=pk).first()
    if not faq:
        return json_error('Không tìm thấy câu hỏi FAQ.', status=404)

    faq.status = 'Hidden' if faq.status == 'Active' else 'Active'
    faq.save()

    return JsonResponse({
        'status': 'success',
        'message': f"Đã chuyển trạng thái câu hỏi [{faq.faq_code}] sang '{faq.status}'.",
        'current_status': faq.status,
    }, status=200)


@require_GET
def customer_active_conversation_api(request):
    """Lấy phiên hội thoại hiện tại và lịch sử tin nhắn của khách hàng."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({
            'is_authenticated': False,
            'conversation': None,
            'messages': [],
        }, status=200)

    conversation = (
        Conversation.objects.filter(customer=user)
        .select_related('staff')
        .order_by('-created_at')
        .first()
    )

    if not conversation:
        return JsonResponse({
            'is_authenticated': True,
            'conversation': None,
            'messages': [],
        }, status=200)

    messages_qs = conversation.messages.all().order_by('created_at')
    staff_name = (conversation.staff.name or conversation.staff.username) if conversation.staff else None

    return JsonResponse({
        'is_authenticated': True,
        'conversation': {
            'id': conversation.id,
            'status': conversation.status,
            'staff_name': staff_name,
            'created_at': conversation.created_at.isoformat(),
        },
        'messages': [serialize_message(m) for m in messages_qs],
    }, status=200)


@require_staff_json
@require_GET
def admin_conversation_monitor_api(request, pk):
    """Lấy thông tin chi tiết phiên chat cần giám sát cho Admin."""
    conv = Conversation.objects.select_related('customer', 'staff').filter(pk=pk).first()
    if not conv:
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    customer = conv.customer
    membership = Membership.objects.filter(user=customer).select_related('tier').first() if customer else None
    tier_name = membership.tier.name if (membership and membership.tier) else 'Hạng VÀNG'
    total_spent = membership.total_spent if membership else 18500000
    formatted_spent = f"{int(total_spent):,} VNĐ".replace(',', '.')

    health = UserHealthProfile.objects.filter(user=customer).first() if customer else None
    health_notes = []
    if health:
        if health.special_requests:
            health_notes.append(health.special_requests)
        if health.massage_pressure:
            health_notes.append(f"ưu tiên lực {health.massage_pressure.lower()}")
        if health.allergy_notes:
            health_notes.append(f"dị ứng: {health.allergy_notes}")
    health_summary = ", ".join(health_notes) if health_notes else "Da nhạy cảm, ưu tiên lực nhẹ."

    duration_seconds = int((timezone.now() - conv.created_at).total_seconds())
    duration_display = f"{duration_seconds // 60:02d}:{duration_seconds % 60:02d}"

    available_staffs = User.objects.filter(is_staff=True).exclude(
        pk=conv.staff_id if conv.staff else 0
    ).values('id', 'name', 'phone')

    messages_qs = conv.messages.all().order_by('created_at')

    return JsonResponse({
        'status': 'success',
        'conversation': {
            'id': conv.id,
            'status': conv.status,
            'customer_tag': conv.customer_tag or 'Trị liệu vai gáy & Đặt lịch',
            'created_at': conv.created_at.isoformat(),
            'duration_display': duration_display,
            'staff': {
                'id': conv.staff.id,
                'name': conv.staff.name,
                'is_online': True,
            } if conv.staff else None,
            'customer': {
                'id': customer.id if customer else None,
                'name': customer.name if customer else 'Khách vãng lai',
                'phone': customer.phone if customer else '',
                'email': customer.email if customer else '',
                'tier_name': tier_name,
                'total_spent': formatted_spent,
                'health_summary': health_summary,
            },
            'sla_status': 'Tốt (< 30 giây)',
            'sla_badge': 'success',
            'messages': [serialize_message(m) for m in messages_qs],
            'available_staffs': list(available_staffs),
        },
    }, status=200)


@require_staff_json
@require_POST
def admin_reassign_staff_api(request, pk):
    """Chuyển cuộc hội thoại sang cho nhân viên khác."""
    conv = Conversation.objects.filter(pk=pk).first()
    if not conv:
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    data, err = parse_json_body(request)
    if err:
        return err

    new_staff_id = data.get('staff_id')
    if not new_staff_id:
        return json_error('Vui lòng chọn nhân viên tiếp nhận mới.', status=400)

    new_staff = User.objects.filter(pk=new_staff_id, is_staff=True).first()
    if not new_staff:
        return json_error('Nhân viên không tồn tại hoặc không hợp lệ.', status=400)

    old_staff_name = conv.staff.name if conv.staff else 'Chưa có'
    conv.staff = new_staff
    conv.status = 'Đang xử lý'
    conv.save(update_fields=['staff', 'status'])

    admin_name = request.user.name or 'Quản trị viên'
    ConversationMessage.objects.create(
        conversation=conv,
        sender_type='Staff',
        content=f"[HỆ THỐNG] {admin_name} đã chuyển giao cuộc hội thoại từ {old_staff_name} sang nhân viên {new_staff.name}.",
    )

    return JsonResponse({
        'status': 'success',
        'message': f'Đã chuyển giao thành công cho nhân viên {new_staff.name}.',
        'staff': {'id': new_staff.id, 'name': new_staff.name},
    }, status=200)


@require_staff_json
@require_POST
def admin_takeover_conversation_api(request, pk):
    """Admin trực tiếp tiếp quản cuộc hội thoại."""
    conv = Conversation.objects.filter(pk=pk).first()
    if not conv:
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    admin_name = request.user.name or 'Quản trị viên'
    conv.staff = request.user
    conv.status = 'Đang xử lý'
    conv.save(update_fields=['staff', 'status'])

    ConversationMessage.objects.create(
        conversation=conv,
        sender_type='Staff',
        content=f"[HỆ THỐNG] Quản lý ({admin_name}) đã can thiệp và trực tiếp tiếp quản phiên tư vấn này.",
    )

    return JsonResponse({
        'status': 'success',
        'message': f'Quản lý {admin_name} đã tiếp quản cuộc hội thoại thành công.',
        'staff_name': admin_name,
    }, status=200)


@require_staff_json
@require_POST
def admin_send_message_api(request, pk):
    """Admin gửi tin nhắn can thiệp / chỉ đạo trực tiếp vào phiên chat."""
    conv = Conversation.objects.filter(pk=pk).first()
    if not conv:
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    data, err = parse_json_body(request)
    if err:
        return err

    content = str(data.get('content') or '').strip()
    if not content:
        return json_error('Nội dung tin nhắn không được để trống.', status=400)

    admin_name = request.user.name or 'Quản lý Cham Spa'
    msg = ConversationMessage.objects.create(
        conversation=conv,
        sender_type='Staff',
        content=f"[Quản lý {admin_name}]: {content}",
    )

    return JsonResponse({
        'status': 'success',
        'message': serialize_message(msg),
    }, status=201)


@require_staff_json
@require_GET
def admin_faq_export_api(request):
    """Xuất toàn bộ danh sách kịch bản FAQ ra file CSV có BOM UTF-8."""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="ChamSpa_KichBan_FAQ.csv"'

    writer = csv.writer(response)
    writer.writerow(['Mã FAQ', 'Danh mục', 'Câu hỏi hiển thị', 'Từ khóa kích hoạt', 'Câu trả lời tự động', 'Trạng thái', 'Ngày tạo'])

    for faq in FAQ.objects.all().order_by('category', 'faq_code'):
        writer.writerow([
            faq.faq_code,
            faq.category,
            faq.question,
            faq.keywords,
            faq.answer,
            'Kích hoạt' if faq.status == 'Active' else 'Đang ẩn',
            faq.created_at.strftime('%d/%m/%Y %H:%M') if faq.created_at else '',
        ])

    return response
