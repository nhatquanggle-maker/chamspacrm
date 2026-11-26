"""
API Endpoints (Pure Django JsonResponse) cho Phân hệ Quản lý Boxchat Tư vấn - CHAMSPA CRM
"""

import csv
from datetime import date, time
import os
import uuid
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename
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
    require_superuser_json,
)
from core.models import (
    Conversation,
    ConversationMessage,
    FAQ,
    Membership,
    User,
    UserHealthProfile,
)

#chuyển thành múi giờ địa phương - local

def _format_local_dt(dt_val, fmt='%d/%m/%Y %H:%M'):
    if not dt_val:
        return ""
    return timezone.localtime(dt_val).strftime(fmt)

#chuyển định dạng sang dict

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
        return "Tư vấn viên Cham Spa"
    if msg.sender_type == 'Customer':
        if msg.conversation.customer:
            return msg.conversation.customer.name or "Khách hàng"
        return "Khách hàng"
    if msg.sender_type == 'Bot':
        return "Trợ lý ảo Cham Spa"
    return "Hệ thống"


def serialize_message(msg):
    import re
    raw_content = msg.content or ""
    clean_content = re.sub(r'^\[Quản lý.*?\]:\s*', '', raw_content)
    if msg.attachment_url and clean_content.startswith('Đã gửi '):
        clean_content = ""

    return {
        'id': msg.id,
        'conversation': msg.conversation_id,
        'sender_type': msg.sender_type,
        'sender_name': _get_message_sender_name(msg),
        'message_type': msg.message_type,
        'content': clean_content,
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
        last_message_time = _format_local_dt(conv.created_at, '%H:%M')

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
    # Định nghĩa hàm tìm câu hỏi thường gặp (FAQ) phù hợp nhất với nội dung khách hàng gửi.
    """Tìm kiếm câu trả lời phù hợp nhất từ bảng FAQ (status='Active')."""
    # Mô tả chức năng của hàm: chỉ tìm kiếm trong các FAQ đang ở trạng thái Active.
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


    # strip() loại bỏ khoảng trắng ở đầu và cuối tin nhắn.
    # lower() chuyển toàn bộ nội dung thành chữ thường để dễ so sánh.
    # Truy vấn bảng FAQ trong database.
    # Chỉ lấy những câu hỏi có status = 'Active'.
        # Duyệt lần lượt từng FAQ đang hoạt động trong database.
        # Lấy nội dung câu hỏi FAQ, chuyển thành chữ thường và bỏ khoảng trắng thừa.
            # Kiểm tra xem câu hỏi FAQ có nằm trong tin nhắn khách hàng không.
            # Hoặc tin nhắn khách hàng có nằm trong câu hỏi FAQ không.
            # Nếu tìm thấy câu hỏi trùng khớp trực tiếp, trả về FAQ đó ngay lập tức.
    # Khởi tạo biến lưu FAQ phù hợp nhất.
    # Ban đầu chưa tìm được FAQ nào nên gán bằng None.
    # Khởi tạo số lượng từ khóa trùng khớp lớn nhất bằng 0.
        # Tiếp tục duyệt từng FAQ đang hoạt động để tìm kiếm theo từ khóa.
        # Khởi tạo biến đếm số từ khóa trùng khớp của FAQ hiện tại.
            # Kiểm tra FAQ hiện tại có dữ liệu từ khóa hay không.
            # replace(';', ','): Thay dấu chấm phẩy bằng dấu phẩy.
            # split(','): Tách chuỗi từ khóa thành một danh sách.
            # strip(): Loại bỏ khoảng trắng thừa ở từng từ khóa.
            # lower(): Chuyển từ khóa thành chữ thường.
            # if k.strip(): Chỉ giữ lại những từ khóa không rỗng.
                # Duyệt từng từ khóa trong danh sách keywords_list.
                    # Kiểm tra từ khóa có xuất hiện trong tin nhắn khách hàng không.
                    # Nếu có, tăng số lượng từ khóa trùng khớp lên 1.
        # Lấy các từ trong câu hỏi FAQ.
        # lower(): Chuyển câu hỏi thành chữ thường.
        # split(): Tách câu hỏi thành các từ riêng biệt.
        # len(w) >= 3: Chỉ giữ lại những từ có ít nhất 3 ký tự.
        # Mục đích: Loại bỏ các từ quá ngắn như "là", "và", "ở".
            # Duyệt từng từ trong danh sách từ khóa lấy từ câu hỏi FAQ.
                # Kiểm tra từ hiện tại có xuất hiện trong tin nhắn khách hàng không.
                # Nếu có, tăng số lượng từ trùng khớp lên 1.
            # Kiểm tra FAQ hiện tại có số từ trùng khớp lớn hơn FAQ tốt nhất trước đó không.
            # Cập nhật số lượng từ trùng khớp lớn nhất.
            # Lưu FAQ hiện tại làm FAQ phù hợp nhất.
        # Kiểm tra có ít nhất một từ khóa trùng khớp hay không.
        # Nếu có, trả về FAQ có số từ khóa trùng khớp nhiều nhất.
        # Tạo từ điển ánh xạ giữa chủ đề và những từ/cụm từ khách hàng có thể sử dụng.
        # Chủ đề giá: nhận diện các câu hỏi liên quan đến giá dịch vụ.
        # Chủ đề giờ: nhận diện các câu hỏi liên quan đến thời gian hoạt động.
        # Chủ đề địa chỉ: nhận diện các câu hỏi về địa điểm và chi nhánh.
        # Chủ đề đặt lịch: nhận diện các yêu cầu đặt lịch hoặc giữ chỗ.
        # Chủ đề khuyến mãi: nhận diện các câu hỏi về chương trình ưu đãi.
        # Chủ đề khiếu nại: nhận diện các phản ánh hoặc vấn đề khách hàng gặp phải.
        # Duyệt từng cặp dữ liệu trong topics_map.
        # cat_keyword là tên chủ đề, ví dụ: 'giá'.
        # trigger_words là danh sách từ/cụm từ dùng để nhận diện chủ đề đó.
            # any() kiểm tra xem có ít nhất một từ trong trigger_words xuất hiện
            # trong tin nhắn khách hàng hay không.
                # Bắt đầu truy vấn FAQ dự phòng theo chủ đề đã nhận diện.
                # Q(category__icontains=cat_keyword):
                # Tìm FAQ có trường category chứa tên chủ đề.
                #
                # Dấu | có nghĩa là OR (hoặc).
                #
                # Q(question__icontains=cat_keyword):
                # Hoặc tìm FAQ có nội dung câu hỏi chứa tên chủ đề.
                #
                # icontains: Tìm kiếm không phân biệt chữ hoa và chữ thường.
            # first() lấy FAQ đầu tiên thỏa mãn điều kiện.
            # Nếu không có FAQ phù hợp, kết quả là None.
                # Kiểm tra có tìm thấy FAQ dự phòng hay không.
                # Nếu tìm thấy, trả về FAQ phù hợp với chủ đề.
    # Nếu đã thử tất cả các cách mà vẫn không tìm thấy FAQ phù hợp,
    # trả về None.
@require_POST
def bot_reply_api(request):
    # Hàm xử lý yêu cầu gửi tin nhắn đến Chatbot và trả về câu trả lời tự động.
    # Khách vãng lai không lưu lịch sử vào Database.
    # Khách hàng đăng nhập sẽ được lưu lịch sử hội thoại.
    # Đọc dữ liệu JSON được gửi từ Frontend và kiểm tra dữ liệu đầu vào.
    """Phản hồi tự động từ Chatbot (khách vãng lai không ghi DB, khách đăng nhập lưu lịch sử)."""
    data, err = parse_json_body(request)
    # Nếu dữ liệu JSON không hợp lệ thì trả về thông báo lỗi ngay lập tức.
    if err:
        return err

    # Lấy nội dung tin nhắn từ Frontend.
    # Nếu không có message hoặc message là None thì thay bằng chuỗi rỗng.
    # strip() loại bỏ khoảng trắng ở đầu và cuối chuỗi.
    user_message = str(data.get('message') or '').strip()
    # Lấy mã FAQ mà khách hàng có thể đã chọn từ danh sách câu hỏi thường gặp.
    faq_id_raw = data.get('faq_id')
    # Lấy mã cuộc hội thoại mà Frontend gửi lên (nếu có).
    conv_id_raw = data.get('conversation_id')

    try:
        faq_id = int(faq_id_raw) if faq_id_raw not in (None, '') else None
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'errors': {'faq_id': ['Mã FAQ không hợp lệ.']}}, status=400)

    try:
        # Nếu faq_id không phải None hoặc chuỗi rỗng thì chuyển thành số nguyên.
        # Nếu không có giá trị thì gán None.
    # Nếu không thể chuyển sang số nguyên thì phát sinh TypeError hoặc ValueError.
        # Trả về lỗi HTTP 400 vì mã FAQ không hợp lệ.
    # Bắt đầu chuyển conversation_id sang kiểu số nguyên.
        # Nếu conversation_id có giá trị thì chuyển thành int.
        # Nếu không có giá trị thì gán None.
        conv_id = int(conv_id_raw) if conv_id_raw not in (None, '') else None
    # Nếu chuyển đổi thất bại thì không trả lỗi mà bỏ qua mã hội thoại.
    except (TypeError, ValueError):
        # Gán None để hệ thống tự tìm hoặc tạo cuộc hội thoại phù hợp.
        conv_id = None

    # Kiểm tra độ dài nội dung tin nhắn của khách hàng.
    if len(user_message) > 1000:
        # Nếu nội dung vượt quá 1000 ký tự thì trả về lỗi HTTP 400.
        return JsonResponse({'status': 'error', 'errors': {'message': ['Nội dung quá dài (tối đa 1000 ký tự).']}}, status=400)

    if not user_message and not faq_id:
        # Nếu cả hai đều không có thì yêu cầu khách hàng nhập nội dung.
        return JsonResponse({
            'status': 'error',  # Trạng thái lỗi.
            'errors': {'message': ['Vui lòng nhập nội dung hoặc chọn câu hỏi thường gặp.']},
        }, status=400)

    # Khởi tạo biến matched_faq để lưu câu hỏi FAQ phù hợp.
    # Ban đầu chưa tìm thấy FAQ nên gán None.
    matched_faq = None
    # Kiểm tra khách hàng có chọn một FAQ cụ thể hay không.
    if faq_id:
        # Tìm FAQ trong Database theo khóa chính (pk) và chỉ lấy FAQ đang hoạt động.
        # first() trả về bản ghi đầu tiên nếu tìm thấy, nếu không trả về None.
        # Nếu tìm thấy FAQ và khách hàng chưa nhập nội dung tin nhắn.
        matched_faq = FAQ.objects.filter(pk=faq_id, status='Active').first()
        if matched_faq and not user_message:
            # Tự động lấy nội dung câu hỏi của FAQ làm tin nhắn của khách hàng.
            user_message = matched_faq.question

    # Nếu chưa tìm được FAQ bằng faq_id nhưng khách hàng có nhập nội dung.
    if not matched_faq and user_message:
        # Gọi hàm find_best_faq_match() để tìm FAQ có nội dung gần giống nhất.
        matched_faq = find_best_faq_match(user_message)

    # Kiểm tra hệ thống có tìm được câu hỏi FAQ phù hợp hay không.
    if matched_faq:
        # Nếu tìm thấy FAQ thì lấy câu trả lời tương ứng trong Database.
        bot_reply_text = matched_faq.answer
        # Tạo danh sách các thao tác gợi ý cho khách hàng.
    # Nếu không tìm được FAQ phù hợp với nội dung khách hàng gửi.
        suggested_actions = ["Chọn câu hỏi khác", "Gặp nhân viên tư vấn"]
    else:
        # Gán câu trả lời mặc định của Chatbot.
        bot_reply_text = (
            "Dạ Cham Spa & Massage xin chào quý khách! "
            "Em chưa hiểu rõ yêu cầu của mình. "
            "Quý khách có thể chọn các Câu hỏi thường gặp bên dưới hoặc bấm 'Gặp nhân viên tư vấn' "
            "để chuyên viên chăm sóc khách hàng hỗ trợ ngay nhé ạ!"
        )
        # Tạo danh sách thao tác gợi ý để khách hàng lựa chọn.
        suggested_actions = ["Bảng giá dịch vụ", "Giờ mở cửa & Địa chỉ", "Gặp nhân viên tư vấn"]

    user = request.user
    # Khởi tạo biến lưu ID cuộc hội thoại sau khi được lưu vào Database.
    # Ban đầu gán None vì có thể khách hàng không đăng nhập.
    saved_conv_id = None

    # Kiểm tra người dùng đã đăng nhập hay chưa.
    # Đồng thời loại trừ tài khoản nhân viên và tài khoản quản trị viên.
    if user.is_authenticated and not user.is_staff and not user.is_superuser:
        # transaction.atomic() đảm bảo các thao tác Database bên trong
        # được thực hiện thành một giao dịch thống nhất.
        # Nếu xảy ra lỗi thì các thay đổi sẽ được rollback.
        with transaction.atomic():
            # Khởi tạo biến conversation để lưu đối tượng hội thoại.
            conversation = None
            # Nếu Frontend có gửi conversation_id thì tìm cuộc hội thoại tương ứng.
            if conv_id:
                # Chỉ lấy cuộc hội thoại có ID tương ứng và thuộc về chính khách hàng đang đăng nhập.
                conversation = Conversation.objects.filter(id=conv_id, customer=user).first()

            if not conversation or conversation.status == 'Kết thúc':
                # Tìm cuộc hội thoại gần nhất của khách hàng có trạng thái còn hoạt động.
                conversation = (
                    Conversation.objects.filter(
                        customer=user,
                        # Chỉ tìm những cuộc hội thoại có trạng thái:
                        # Bot đang xử lý, đang chờ hoặc đang được nhân viên xử lý.
                        status__in=['Bot xử lý', 'Đang chờ', 'Đang xử lý'],
                    )
                    # Sắp xếp theo thời gian tạo giảm dần.
                    # Cuộc hội thoại mới nhất sẽ đứng đầu.
                    .order_by('-created_at')
                    # Lấy cuộc hội thoại đầu tiên.
                    .first()
                )

            # Nếu vẫn không tìm thấy cuộc hội thoại phù hợp.
            if not conversation:
                # Tạo một cuộc hội thoại mới trong Database.
                conversation = Conversation.objects.create(
                    # Gắn cuộc hội thoại với khách hàng đang đăng nhập.
                    customer=user,
                    # Đặt trạng thái ban đầu là Bot xử lý.
                    status='Bot xử lý',
                    # Gắn nhãn khách hàng theo danh mục FAQ đã tìm được.
                    # Nếu không tìm thấy FAQ thì sử dụng nhãn mặc định.
                    customer_tag=matched_faq.category if matched_faq else 'Khách quan tâm dịch vụ',
                )
            # Nếu đã có cuộc hội thoại và tìm được FAQ phù hợp.
            # Đồng thời cuộc hội thoại vẫn đang ở trạng thái Bot xử lý.
            elif matched_faq and conversation.status == 'Bot xử lý':
                # Cập nhật nhãn khách hàng theo danh mục của FAQ.
                conversation.customer_tag = matched_faq.category
                # Chỉ lưu trường customer_tag để tránh cập nhật các trường không cần thiết.
                conversation.save(update_fields=['customer_tag'])

            # Lưu tin nhắn của khách hàng vào bảng ConversationMessage.
            ConversationMessage.objects.create(
                # Liên kết tin nhắn với cuộc hội thoại hiện tại.
                conversation=conversation,
                # Xác định người gửi tin nhắn là khách hàng.
                sender_type='Customer',
                # Xác định loại tin nhắn là văn bản.
                message_type='TEXT',
                # Lưu nội dung tin nhắn của khách hàng.
                content=user_message,
            )
            # Lưu câu trả lời của Chatbot vào bảng ConversationMessage.
            ConversationMessage.objects.create(
                # Liên kết tin nhắn trả lời với cùng cuộc hội thoại.
                conversation=conversation,
                # Xác định người gửi tin nhắn là Bot.
                sender_type='Bot',
                # Xác định loại tin nhắn là văn bản.
                message_type='TEXT',
                # Lưu nội dung câu trả lời của Chatbot.
                content=bot_reply_text,
            )
            # Lấy ID của cuộc hội thoại vừa được sử dụng.
            # Gán vào saved_conv_id để trả về cho Frontend.
            saved_conv_id = conversation.id

    # Trả kết quả xử lý về Frontend dưới định dạng JSON.
    return JsonResponse({
        # Thông báo yêu cầu được xử lý thành công.
        'status': 'success',
        # Nội dung câu trả lời của Chatbot.
        'reply': bot_reply_text,
        # Trả về ID của FAQ phù hợp.
        # Nếu không tìm thấy FAQ thì trả về None.
        'faq_id': matched_faq.id if matched_faq else None,
        # Trả về mã FAQ.
        'faq_code': matched_faq.faq_code if matched_faq else None,
        # Trả về danh mục của FAQ.
        'faq_category': matched_faq.category if matched_faq else None,
        # Trả về danh sách các thao tác gợi ý cho khách hàng.
        'suggested_actions': suggested_actions,
        # Trả về ID cuộc hội thoại đã lưu.
        # Khách vãng lai sẽ nhận giá trị None.
        'conversation_id': saved_conv_id,
        # Cho Frontend biết người gửi yêu cầu đã đăng nhập hay chưa.
        'is_authenticated': user.is_authenticated,
    }, status=200)  # HTTP 200: Yêu cầu được xử lý thành công.


@require_GET
def public_faq_blocks_api(request):
    # Hàm API cung cấp danh sách các câu hỏi FAQ đang hoạt động
    # để Frontend hiển thị thành các Block câu hỏi cho khách hàng.
    # Truy vấn bảng FAQ trong Database.
    # Chỉ lấy những câu hỏi có trạng thái status = 'Active'.
    # order_by('category', 'id') sắp xếp dữ liệu:
    # Ưu tiên sắp xếp theo danh mục (category).
    # Nếu cùng danh mục thì sắp xếp theo ID tăng dần.
    # Khởi tạo danh sách blocks để chứa thông tin các câu hỏi FAQ.
    # Mỗi phần tử trong danh sách tương ứng với một Block FAQ.
    """Cung cấp danh sách các Block câu hỏi FAQ đang kích hoạt."""
    active_faqs = FAQ.objects.filter(status='Active').order_by('category', 'id')
    blocks = []
    # Khởi tạo danh sách categories để lưu các danh mục FAQ.
    categories = []
    # Khởi tạo một tập hợp (set) để kiểm tra danh mục đã xuất hiện hay chưa.
    # Set không cho phép lưu các giá trị trùng lặp.
    seen_cats = set()

    # Duyệt lần lượt từng bản ghi FAQ lấy được từ Database.
    # Mỗi bản ghi được đại diện bởi biến f.
    for f in active_faqs:
        # Kiểm tra FAQ có danh mục hay không.
        # Đồng thời kiểm tra danh mục này đã được thêm vào set chưa.
        if f.category and f.category not in seen_cats:
            # Nếu danh mục chưa xuất hiện thì thêm vào set seen_cats.
            # Mục đích là đánh dấu danh mục này đã được xử lý.
            seen_cats.add(f.category)
            # Thêm danh mục vào danh sách categories.
            # Nhờ điều kiện phía trên nên không có danh mục trùng lặp.
            categories.append(f.category)
        # Thêm thông tin của FAQ hiện tại vào danh sách blocks.
        blocks.append({
            # Lấy ID của câu hỏi FAQ từ Database.
            'id': f.id,
            # Lấy mã định danh của câu hỏi FAQ.
            'faq_code': f.faq_code,
            # Lấy tên danh mục mà câu hỏi FAQ thuộc về.
            'category': f.category,
            # Lấy nội dung câu hỏi FAQ để hiển thị trên Frontend.
            'question': f.question,
        })

    # Trả dữ liệu về Frontend dưới định dạng JSON.
    return JsonResponse({
        # Thông báo API đã xử lý thành công.
        'status': 'success',
        # Trả về danh sách các danh mục FAQ không trùng lặp.
        'categories': categories,
        # Trả về danh sách các Block câu hỏi FAQ.
        'blocks': blocks,
    }, status=200)  # HTTP 200: Yêu cầu được xử lý thành công.


@require_POST
def conversation_transfer_staff_api(request):
    # Hàm xử lý yêu cầu khách hàng chuyển cuộc hội thoại từ Chatbot
    # sang nhân viên chăm sóc khách hàng (CSKH).
    # Kiểm tra người dùng đã đăng nhập hay chưa.
    """Khách hàng bấm 'Chuyển tiếp cho nhân viên' trong khung chat."""
    if not request.user.is_authenticated:
        # Nếu chưa đăng nhập, trả về trạng thái require_login.
        # Đồng thời thông báo khách hàng cần đăng nhập để được gặp nhân viên.
        return JsonResponse({
            'status': 'require_login',  # Trạng thái yêu cầu đăng nhập.
            'message': 'Quý khách vui lòng đăng nhập tài khoản để được kết nối trò chuyện trực tiếp với nhân viên CSKH.',
            # Nội dung thông báo hiển thị trên giao diện Chatbot.
        }, status=401)  # HTTP 401: Unauthorized (chưa xác thực).

    # Kiểm tra tài khoản hiện tại có phải nhân viên hoặc quản trị viên hay không.
    if is_staff_or_admin(request.user):
        # Nếu là nhân viên hoặc quản lý thì không cho phép gửi yêu cầu
        # gặp tư vấn viên với tư cách khách hàng.
    # Đọc dữ liệu JSON được gửi từ Frontend.
        return json_error('Tài khoản nhân viên hoặc quản lý không thể gửi yêu cầu gặp tư vấn viên như khách hàng.', status=403)

    data, err = parse_json_body(request)
    # Nếu dữ liệu JSON không hợp lệ thì trả về lỗi ngay lập tức.
    if err:
        return err

    # Lấy ID cuộc hội thoại mà Frontend gửi lên.
    # ID này giúp hệ thống xác định phiên chat cần chuyển cho nhân viên.
    conv_id = data.get('conversation_id')
    # Lấy thông tin tài khoản người dùng đang thực hiện yêu cầu.
    user = request.user

    # Bắt đầu giao dịch Database.
    # Các thao tác thay đổi dữ liệu bên trong sẽ được thực hiện đồng bộ.
    # Nếu có lỗi phát sinh thì giao dịch có thể được rollback.
    with transaction.atomic():
        # Khởi tạo biến conversation để lưu thông tin cuộc hội thoại.
        # Ban đầu chưa tìm thấy nên gán giá trị None.
        conversation = None
        # Kiểm tra Frontend có gửi conversation_id hay không.
        if conv_id:
            # Tìm cuộc hội thoại theo ID được gửi lên.
            # Điều kiện customer=user đảm bảo chỉ lấy hội thoại thuộc về khách hàng này.
            # first() trả về bản ghi đầu tiên nếu tìm thấy, nếu không trả về None.
        # Nếu không tìm thấy cuộc hội thoại theo ID.
            conversation = Conversation.objects.filter(id=conv_id, customer=user).first()

        if not conversation or conversation.status == 'Kết thúc':
            # Tìm cuộc hội thoại gần nhất của khách hàng có trạng thái còn hoạt động.
            conversation = (
                Conversation.objects.filter(
                    # Chỉ tìm những cuộc hội thoại thuộc về khách hàng hiện tại.
                    customer=user,
                    # Chỉ lấy các cuộc hội thoại có trạng thái:
                    # Bot xử lý, Đang chờ hoặc Đang xử lý.
                    status__in=['Bot xử lý', 'Đang chờ', 'Đang xử lý'],
                )
                # Sắp xếp cuộc hội thoại theo thời gian tạo giảm dần.
                # Cuộc hội thoại mới nhất được đưa lên đầu.
                .order_by('-created_at')
                # Lấy cuộc hội thoại đầu tiên sau khi sắp xếp.
                .first()
            )

        # Nếu không tìm thấy bất kỳ cuộc hội thoại nào đang hoạt động.
        if not conversation:
            # Tạo một cuộc hội thoại mới trong Database.
            conversation = Conversation.objects.create(
                # Gắn cuộc hội thoại mới với khách hàng đang đăng nhập.
                customer=user,
                # Đặt trạng thái là Đang chờ để nhân viên tiếp nhận.
                status='Đang chờ',
                # Gắn nhãn khách hàng theo mục đích yêu cầu tư vấn trực tiếp.
                customer_tag='Yêu cầu tư vấn trực tiếp',
            )
            # Tạo một tin nhắn thông báo từ Chatbot.
            # Tin nhắn này được lưu vào bảng ConversationMessage.
            ConversationMessage.objects.create(
                # Liên kết tin nhắn với cuộc hội thoại vừa tạo.
                conversation=conversation,
                # Xác định người gửi là Chatbot.
                sender_type='Bot',
                # Xác định loại tin nhắn là văn bản.
                message_type='TEXT',
                # Nội dung thông báo khách hàng đã được chuyển yêu cầu tư vấn.
                content='Dạ, yêu cầu của quý khách đã được chuyển tới chuyên viên tư vấn Cham Spa. Chuyên viên sẽ tiếp nhận và phản hồi ngay trong giây lát ạ!',
            )
        elif conversation.status == 'Đang xử lý':
            return JsonResponse({
                'status': 'already_connected',
                'message': 'Quý khách đang được chuyên viên Cham Spa hỗ trợ trực tiếp trong phiên chat này rồi ạ!',
                'conversation_id': conversation.id,
                'conversation_status': conversation.status,
            }, status=200)
        elif conversation.status == 'Đang chờ':
            return JsonResponse({
                'status': 'already_waiting',
                'message': 'Yêu cầu của quý khách đang nằm trong hàng chờ, chuyên viên Cham Spa sẽ tiếp nhận trong giây lát ạ!',
                'conversation_id': conversation.id,
                'conversation_status': conversation.status,
            }, status=200)
        else:
            conversation.status = 'Đang chờ'
            conversation.save(update_fields=['status'])
            ConversationMessage.objects.create(
                conversation=conversation,
                sender_type='Bot',
                message_type='TEXT',
                content='Dạ, yêu cầu của quý khách đã được chuyển tới chuyên viên tư vấn Cham Spa. Chuyên viên sẽ tiếp nhận và phản hồi ngay trong giây lát ạ!',
            )

        # Nếu cuộc hội thoại hiện tại đã được nhân viên tiếp nhận và đang xử lý.
            # Trả về trạng thái already_connected.
            # Mục đích là thông báo khách hàng đã được nhân viên hỗ trợ.
    return JsonResponse({
                # Xác định khách hàng đã kết nối với nhân viên.
                # Nội dung thông báo khách hàng đang được hỗ trợ trực tiếp.
                # Trả về ID của cuộc hội thoại hiện tại.
                # Trả về trạng thái hiện tại của cuộc hội thoại.
        # Nếu cuộc hội thoại hiện tại đã nằm trong hàng chờ nhân viên.
            # Trả về trạng thái already_waiting.
            # Tránh tạo thêm yêu cầu chuyển tiếp trùng lặp.
                # Xác định yêu cầu đã được gửi trước đó.
                # Thông báo khách hàng đang nằm trong hàng chờ.
                # Trả về ID cuộc hội thoại đang chờ.
                # Trả về trạng thái hiện tại của cuộc hội thoại.
        # Trường hợp còn lại là cuộc hội thoại đang ở trạng thái Bot xử lý.
            # Chuyển trạng thái cuộc hội thoại từ Bot xử lý sang Đang chờ.
            # Lưu thay đổi trạng thái vào Database.
            # Chỉ cập nhật trường status.
            # Tạo tin nhắn thông báo Chatbot đã chuyển yêu cầu
            # của khách hàng đến nhân viên tư vấn.
                # Liên kết tin nhắn với cuộc hội thoại hiện tại.
                # Xác định người gửi là Chatbot.
                # Loại tin nhắn là văn bản.
                # Nội dung thông báo chuyển tiếp đến chuyên viên tư vấn.
    # Sau khi hoàn tất giao dịch Database, trả kết quả về Frontend.
    # Đoạn này chỉ chạy khi hệ thống tạo mới hoặc chuyển trạng thái thành công.
        # Thông báo yêu cầu chuyển tiếp đã được xử lý thành công.
        'status': 'success',
        # Nội dung thông báo gửi đến khách hàng.
        'message': 'Đã gửi yêu cầu kết nối với nhân viên tư vấn thành công.',
        # Trả về ID của cuộc hội thoại được chuyển tiếp.
        'conversation_id': conversation.id,
        # Trả về trạng thái hiện tại của cuộc hội thoại.
        'conversation_status': conversation.status,
    }, status=200)  # HTTP 200: Yêu cầu được xử lý thành công.


@require_auth_json
@require_http_methods(['GET', 'POST'])
def conversation_messages_api(request, pk):
    # Hàm API xử lý việc lấy lịch sử tin nhắn và gửi tin nhắn trực tiếp
    # giữa khách hàng và nhân viên tư vấn trong một cuộc hội thoại.
    # pk là ID của cuộc hội thoại được truyền vào từ URL.
    # Truy vấn bảng Conversation để tìm cuộc hội thoại theo ID (pk).
    # select_related('customer', 'staff') giúp lấy kèm thông tin khách hàng
    # và nhân viên liên quan trong cùng truy vấn Database.
    # filter(pk=pk) lọc cuộc hội thoại có khóa chính bằng pk.
    # first() lấy bản ghi đầu tiên, nếu không có thì trả về None.
    # Kiểm tra cuộc hội thoại có tồn tại trong Database hay không.
    """Lấy lịch sử và gửi tin nhắn trực tiếp giữa Khách hàng và Nhân viên."""
    conversation = Conversation.objects.select_related('customer', 'staff').filter(pk=pk).first()
    if not conversation:
        # Nếu không tìm thấy thì trả về lỗi HTTP 404.
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    user = request.user
    # Kiểm tra phương thức HTTP của yêu cầu có phải GET hay không.
    # GET được sử dụng để lấy lịch sử và thông tin cuộc hội thoại.
    if request.method == 'GET':
        # Kiểm tra quyền truy cập của người dùng.
        # Nếu người dùng không phải nhân viên hoặc quản trị viên
        # và ID khách hàng của cuộc hội thoại không trùng với ID người dùng
        # đang đăng nhập thì không cho phép xem.
        if not is_staff_or_admin(user) and conversation.customer_id != user.id:
            # Trả về lỗi HTTP 403 vì người dùng không có quyền xem.
            return json_error('Bạn không có quyền xem cuộc hội thoại này.', status=403)

        # Nhân viên (không phải Admin) chỉ xem được phiên chat của chính mình hoặc chưa ai tiếp nhận
        if user.is_staff and not user.is_superuser:
            # Nếu cuộc hội thoại đã được giao cho một nhân viên khác
            # thì nhân viên hiện tại không được phép xem.
            if conversation.staff and conversation.staff_id != user.id:
                # Trả về lỗi HTTP 403.
        # Chuyển thông tin cuộc hội thoại thành dữ liệu JSON.
        # Hàm serialize_conversation_detail() có nhiệm vụ định dạng
                return json_error('Bạn không có quyền xem cuộc hội thoại của nhân viên khác.', status=403)

        data = serialize_conversation_detail(conversation)
        # Thêm trường is_assigned_to_other vào dữ liệu trả về.
        # False nghĩa là không đánh dấu cuộc hội thoại đang được giao
        # cho một nhân viên khác trong phản hồi này.
        data['is_assigned_to_other'] = False
        # Thêm trường assigned_staff_name.
        # Giá trị None nghĩa là không cung cấp tên nhân viên được giao
        # trong phản hồi này.
        data['assigned_staff_name'] = None
        # Thêm trường can_send_message.
        # True cho biết API cho phép tiếp tục gửi tin nhắn
        # theo logic kiểm tra quyền hiện tại.
        data['can_send_message'] = True
        # Trả thông tin cuộc hội thoại và lịch sử tin nhắn về Frontend.
        return JsonResponse(data, status=200)

    # Nếu yêu cầu không phải GET thì hệ thống chuyển sang xử lý gửi tin nhắn.
    # Đọc dữ liệu JSON được gửi từ Frontend.
    data, err = parse_json_body(request)
    # Nếu dữ liệu JSON không hợp lệ thì trả về lỗi ngay lập tức.
    if err:
        return err

    # Lấy nội dung tin nhắn từ dữ liệu Frontend.
    # Nếu không có content hoặc content là None thì thay bằng chuỗi rỗng.
    # str() chuyển dữ liệu thành chuỗi.
    # strip() loại bỏ khoảng trắng ở đầu và cuối nội dung.
    content = str(data.get('content') or '').strip()
    # Lấy đường dẫn URL của tệp đính kèm nếu có.
    # Ví dụ: URL của hình ảnh hoặc tài liệu được tải lên.
    attachment_url = data.get('attachment_url')
    # Xác định loại tin nhắn được gửi.
    # Nếu Frontend có gửi message_type thì sử dụng giá trị đó.
    # Nếu không gửi thì:
    # - Có attachment_url: mặc định là IMAGE.
    # - Không có attachment_url: mặc định là TEXT.
    # Kiểm tra khách hàng hoặc nhân viên đã nhập nội dung
    # hoặc đính kèm tệp hay chưa.
    message_type = data.get('message_type') or ('IMAGE' if attachment_url else 'TEXT')
    if not content and not attachment_url:
        # Nếu không có cả nội dung và tệp đính kèm thì trả về lỗi HTTP 400.
    # Kiểm tra độ dài nội dung tin nhắn.
        return JsonResponse({'status': 'error', 'errors': {'content': ['Vui lòng nhập nội dung hoặc chọn tệp đính kèm.']}}, status=400)
    if len(content) > 5000:
        # Nếu nội dung vượt quá 5000 ký tự thì trả về lỗi HTTP 400.
    # Kiểm tra loại tin nhắn có thuộc các loại được hệ thống hỗ trợ hay không.
    # Hiện tại hệ thống chỉ chấp nhận TEXT, IMAGE và FILE.
        return JsonResponse({'status': 'error', 'errors': {'content': ['Nội dung tin nhắn quá dài (tối đa 5000 ký tự).']}}, status=400)
    if message_type not in ('TEXT', 'IMAGE', 'FILE'):
        # Nếu loại tin nhắn không hợp lệ thì trả về lỗi HTTP 400.
        return JsonResponse({'status': 'error', 'errors': {'message_type': ['Loại tin nhắn không hợp lệ.']}}, status=400)

    if is_staff_or_admin(user):
        # Nếu người gửi không phải Superuser,
        # đồng thời cuộc hội thoại đã được giao cho nhân viên khác
        # thì không cho phép gửi tin nhắn.
            # Trả về trạng thái forbidden_assigned.
            # Điều này giúp Frontend biết cuộc hội thoại đã có nhân viên khác phụ trách.
        if not user.is_superuser and conversation.staff and conversation.staff_id != user.id:
            return JsonResponse({
                # Mã trạng thái thể hiện người dùng không có quyền xử lý.
                'status': 'forbidden_assigned',
                # Nội dung thông báo lỗi.
                'error': 'Cuộc hội thoại này đã do nhân viên khác tiếp nhận xử lý.',
            }, status=403)

        # Kiểm tra cuộc hội thoại đã được giao cho nhân viên nào chưa.
        if not conversation.staff:
            # Nếu chưa có nhân viên tiếp nhận thì gán nhân viên hiện tại
            # làm người phụ trách cuộc hội thoại.
            conversation.staff = user
            # Chuyển trạng thái cuộc hội thoại thành Đang xử lý.
            conversation.status = 'Đang xử lý'
            # Lưu các thay đổi của cuộc hội thoại vào Database.
            # Không truyền update_fields nên Django lưu các trường
            # đã thay đổi và các trường khác của đối tượng theo cơ chế save().
            conversation.save()

        # Xác định loại người gửi tin nhắn là nhân viên.
        sender_type = 'Staff'
        # Lấy tên nhân viên để hiển thị trên giao diện.
        # Nếu user.name không có giá trị thì sử dụng username.
        sender_name = user.name or user.username
    # Nếu người gửi không phải nhân viên hoặc quản trị viên
    # thì hệ thống xử lý theo vai trò khách hàng.
    else:
        # Kiểm tra ID khách hàng sở hữu cuộc hội thoại
        # có trùng với ID người dùng hiện tại hay không.
        if conversation.customer_id != user.id:
            # Nếu không trùng thì không cho phép gửi tin nhắn.
            return json_error('Bạn không có quyền gửi tin nhắn trong cuộc hội thoại này.', status=403)

        sender_type = 'Customer'
        # Lấy tên khách hàng để hiển thị trên giao diện.
        # Nếu user.name không có giá trị thì sử dụng username.
        sender_name = user.name or user.username
        # Kiểm tra cuộc hội thoại có đang ở trạng thái Kết thúc hay không.
        if conversation.status == 'Kết thúc':
            # Nếu khách hàng gửi tin nhắn mới thì chuyển trạng thái
            # cuộc hội thoại trở lại Đang chờ.
            conversation.status = 'Đang chờ'
            # Lưu trạng thái mới vào Database.
            conversation.save()

    # Sau khi xác định người gửi và kiểm tra quyền,
    # tạo một bản ghi tin nhắn mới trong bảng ConversationMessage.
    msg = ConversationMessage.objects.create(
        # Liên kết tin nhắn với cuộc hội thoại hiện tại.
        conversation=conversation,
        # Xác định người gửi là Customer hoặc Staff.
        sender_type=sender_type,
        # Xác định loại tin nhắn là TEXT, IMAGE hoặc FILE.
        message_type=message_type,
        # Lưu nội dung văn bản của tin nhắn.
        content=content,
        # Lưu URL của tệp đính kèm nếu có.
        attachment_url=data.get('attachment_url'),
        # Lưu tên tệp đính kèm nếu có.
        attachment_name=data.get('attachment_name'),
        # Lưu dung lượng tệp đính kèm nếu có.
        attachment_size=data.get('attachment_size'),
    )

    # Sau khi lưu tin nhắn thành công,
    # trả kết quả về Frontend dưới định dạng JSON.
    return JsonResponse({
        # Thông báo gửi tin nhắn thành công.
        'status': 'success',
        # Trả về ID của tin nhắn vừa được tạo trong Database.
        'message_id': msg.id,
        # Trả về loại người gửi: Customer hoặc Staff.
        'sender_type': msg.sender_type,
        # Trả về tên người gửi để hiển thị trên giao diện Chatbox.
        'sender_name': sender_name,
        # Trả về thời gian tạo tin nhắn theo định dạng ISO 8601.
        # Ví dụ: 2026-11-26T09:30:00+07:00.
        'created_at': msg.created_at.isoformat(),
        # Chuyển thời gian tạo tin nhắn sang định dạng dễ đọc.
        # Ví dụ: 09:30 - 26/11.
        # Trả về nội dung tin nhắn vừa gửi.
        'formatted_time': _format_local_dt(msg.created_at, '%H:%M - %d/%m'),
        'content': msg.content,
        # Trả về trạng thái hiện tại của cuộc hội thoại.
        'conversation_status': conversation.status,
    }, status=201)  # HTTP 201: Đã tạo thành công một tin nhắn mới.


@require_staff_json
@require_POST
def conversation_accept_api(request, pk):  # Hàm API xử lý khi nhân viên nhấn nút "Tiếp nhận hội thoại".
    """Nhân viên bấm nút 'Tiếp nhận hội thoại'."""  # Mô tả chức năng của hàm.
    conversation = Conversation.objects.select_related('staff').filter(pk=pk).first()
    # Truy vấn bảng Conversation để tìm cuộc hội thoại có khóa chính (pk) bằng pk được truyền vào.
    # select_related('staff') lấy kèm thông tin nhân viên đang phụ trách để hạn chế truy vấn SQL.
    # filter(pk=pk) lọc đúng cuộc hội thoại cần tìm.
    # first() lấy bản ghi đầu tiên tìm được, nếu không có thì trả về None.
    if not conversation:  # Kiểm tra xem cuộc hội thoại có tồn tại hay không.
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    user = request.user  # Lấy thông tin tài khoản nhân viên đang đăng nhập và gửi yêu cầu API.
    if conversation.staff and conversation.staff_id != user.id and conversation.status == 'Đang xử lý':
        # Kiểm tra đồng thời 3 điều kiện:
        # 1. conversation.staff: Cuộc hội thoại đã có nhân viên phụ trách.
        # 2. conversation.staff_id != user.id: Nhân viên phụ trách hiện tại khác nhân viên đang đăng nhập.
        # 3. conversation.status == 'Đang xử lý': Cuộc hội thoại đang được xử lý.
        other_name = conversation.staff.name or conversation.staff.username
        # Lấy tên nhân viên đang phụ trách cuộc hội thoại.
        # Nếu nhân viên có trường name thì sử dụng name.
        # Nếu name trống thì sử dụng username thay thế.
        return JsonResponse({  # Trả về dữ liệu JSON thông báo xung đột khi tiếp nhận hội thoại.
            'status': 'conflict',  # Trạng thái phản hồi là conflict (xung đột).
            'message': f'Cuộc hội thoại đã do nhân viên {other_name} tiếp nhận xử lý!',
            # Thông báo cho nhân viên biết ai đang phụ trách cuộc hội thoại.
            'assigned_staff': other_name,  # Trả về tên nhân viên đang được phân công xử lý.
        }, status=409)  # HTTP 409 (Conflict): Yêu cầu bị xung đột với trạng thái hiện tại.

    conversation.staff = user  # Gán nhân viên đang đăng nhập làm người phụ trách cuộc hội thoại.
    conversation.status = 'Đang xử lý'  # Cập nhật trạng thái cuộc hội thoại thành "Đang xử lý".
    conversation.save()  # Lưu các thay đổi staff và status vào cơ sở dữ liệu.

    staff_name = user.name or user.username
    # Lấy tên nhân viên vừa tiếp nhận cuộc hội thoại.
    # Ưu tiên sử dụng name, nếu không có thì sử dụng username.
    ConversationMessage.objects.create(  # Tạo một tin nhắn mới trong bảng ConversationMessage.
        conversation=conversation,  # Xác định tin nhắn này thuộc cuộc hội thoại vừa tiếp nhận.
        sender_type='Staff',  # Xác định người gửi tin nhắn là nhân viên (Staff).
        message_type='TEXT',  # Xác định loại tin nhắn là văn bản (TEXT).
        content="Dạ em chào anh/chị! Chuyên viên tư vấn của Cham Spa & Massage đã tiếp nhận yêu cầu và rất vui được hỗ trợ quý khách hôm nay ạ!",
        # Nội dung tin nhắn chào khách hàng được hệ thống tự động tạo khi nhân viên tiếp nhận.
    )  # Kết thúc thao tác tạo tin nhắn mới.

    return JsonResponse({  # Trả về dữ liệu JSON thông báo tiếp nhận hội thoại thành công.
        'status': 'success',  # Trạng thái phản hồi là success (thành công).
        'message': 'Tiếp nhận cuộc hội thoại thành công. Bạn đang phụ trách phiên chat này.',
        # Thông báo cho nhân viên biết đã tiếp nhận hội thoại thành công.
        'conversation_id': conversation.id,  # Trả về ID của cuộc hội thoại vừa được tiếp nhận.
        'staff_name': staff_name,  # Trả về tên nhân viên đang phụ trách cuộc hội thoại.
        'status_label': 'Đang xử lý',  # Trả về trạng thái hiện tại của cuộc hội thoại.
    }, status=200)  # HTTP 200 (OK): Yêu cầu API được xử lý thành công.


@require_staff_json
@require_POST
def conversation_close_api(request, pk):  # Hàm API xử lý khi nhân viên nhấn nút "Đóng phiên chat".
    """Nhân viên bấm 'Đóng phiên chat'."""  # Mô tả chức năng của hàm.
    conversation = Conversation.objects.filter(pk=pk).first()
    # Truy vấn bảng Conversation để tìm cuộc hội thoại có ID bằng pk được truyền vào.
    # filter(pk=pk): Lọc ra cuộc hội thoại có khóa chính (Primary Key) tương ứng.
    # first(): Lấy bản ghi đầu tiên tìm được, nếu không có thì trả về None.
    if not conversation:  # Kiểm tra xem cuộc hội thoại có tồn tại trong database hay không.
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

        # status=404: Mã HTTP 404 (Not Found), nghĩa là không tìm thấy dữ liệu.
    conversation.status = 'Kết thúc'
    # Cập nhật trạng thái cuộc hội thoại thành "Kết thúc".
    # Điều này cho biết phiên tư vấn trực tiếp đã được đóng.
    conversation.closed_at = timezone.now()
    # Lấy thời gian hiện tại của hệ thống và gán vào trường closed_at.
    # timezone.now(): Hàm Django lấy thời gian hiện tại có hỗ trợ múi giờ.
    # closed_at lưu lại thời điểm nhân viên đóng phiên chat.
    conversation.save()

    # Bao gồm trạng thái "Kết thúc" và thời gian đóng phiên chat.
    ConversationMessage.objects.create(
        # Tạo một bản ghi tin nhắn mới trong bảng ConversationMessage.
        conversation=conversation,
        # Xác định tin nhắn này thuộc cuộc hội thoại vừa được đóng.
        sender_type='Staff',
        # Xác định người gửi tin nhắn là nhân viên (Staff).
        message_type='TEXT',
        # Xác định loại tin nhắn là văn bản (TEXT).
        content="Phiên tư vấn trực tiếp đã được hoàn tất. Cham Spa trân trọng cảm ơn quý khách và chúc quý khách một ngày an nhiên!",
        # Nội dung thông báo tự động gửi đến khách hàng khi phiên tư vấn kết thúc.
    )  # Kết thúc thao tác tạo tin nhắn mới.

    return JsonResponse({
        # Trả dữ liệu JSON từ backend Django về frontend.
        'status': 'success',
        # Trả về trạng thái success, nghĩa là đóng phiên chat thành công.
        'message': 'Đã đóng phiên tư vấn thành công.',
        # Nội dung thông báo kết quả cho frontend hiển thị.
        'closed_at': conversation.closed_at.isoformat(),
        # Lấy thời gian đóng phiên chat đã lưu trong database.
        # isoformat(): Chuyển đối tượng thời gian thành chuỗi theo định dạng ISO 8601.
        # Ví dụ: 2026-11-26T09:30:00+07:00.
    }, status=200)  # HTTP 200 (OK): Yêu cầu đóng phiên chat được xử lý thành công.


@require_superuser_json
@require_POST
def conversation_takeover_api(request, pk):  # Hàm API xử lý khi nhân viên muốn chuyển giao hoặc tiếp quản quyền phụ trách hội thoại.
    """Chuyển giao / tiếp quản quyền tiếp nhận hội thoại."""  # Mô tả chức năng của hàm.
    conversation = Conversation.objects.select_related('staff').filter(pk=pk).first()
    # Truy vấn bảng Conversation để tìm cuộc hội thoại có khóa chính (pk) tương ứng.
    # select_related('staff'): Lấy kèm thông tin nhân viên đang phụ trách cuộc hội thoại.
    # Việc này giúp hạn chế số lần truy vấn database khi cần lấy thông tin nhân viên.
    # filter(pk=pk): Lọc cuộc hội thoại theo ID được truyền vào.
    # first(): Lấy bản ghi đầu tiên tìm được, nếu không có thì trả về None.
    if not conversation:  # Kiểm tra xem cuộc hội thoại có tồn tại trong database hay không.
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

        # status=404: Mã HTTP 404 (Not Found), nghĩa là không tìm thấy dữ liệu.
    user = request.user
    # Lấy thông tin tài khoản nhân viên đang đăng nhập và gửi yêu cầu tiếp quản hội thoại.
    # request.user là đối tượng người dùng hiện tại trong Django.
    old_staff_name = conversation.staff.name if conversation.staff else "Nhân viên trước"

    # conversation.staff: Kiểm tra xem cuộc hội thoại đã có nhân viên phụ trách hay chưa.
    # Nếu đã có nhân viên: Lấy tên từ conversation.staff.name.
    # Nếu chưa có nhân viên: Gán giá trị mặc định là "Nhân viên trước".
    # Mục đích: Lưu lại tên nhân viên cũ để sử dụng trong thông báo tiếp quản.
    conversation.staff = user
    # Gán nhân viên đang đăng nhập làm người phụ trách mới của cuộc hội thoại.
    # Sau câu lệnh này, trường staff trong bảng Conversation tham chiếu đến user hiện tại.
    conversation.status = 'Đang xử lý'
    # Cập nhật trạng thái cuộc hội thoại thành "Đang xử lý".
    # Điều này thể hiện cuộc hội thoại đang được nhân viên mới tiếp quản và xử lý.
    conversation.save()
    # Lưu các thay đổi của conversation vào database.
    # Bao gồm nhân viên phụ trách mới và trạng thái cuộc hội thoại.

    new_staff_name = user.name or user.username

    # Ưu tiên sử dụng user.name nếu trường name có dữ liệu.
    # Nếu user.name trống hoặc không có giá trị thì sử dụng user.username.
    return JsonResponse({
        # Trả dữ liệu JSON từ backend Django về frontend.
        'status': 'success',
        # Trả về trạng thái success, nghĩa là tiếp quản hội thoại thành công.
        'message': f'Đã tiếp quản thành công từ {old_staff_name}. Hiện bạn là nhân viên phụ trách chính.',
        # Tạo thông báo xác nhận việc tiếp quản hội thoại.
        # {old_staff_name}: Chèn tên nhân viên phụ trách trước đó vào thông báo.
        'staff_name': new_staff_name,
        # Trả về tên nhân viên mới đang phụ trách cuộc hội thoại.
        # Frontend có thể sử dụng dữ liệu này để cập nhật giao diện.
    }, status=200)  # HTTP 200 (OK): Yêu cầu tiếp quản hội thoại được xử lý thành công.


@require_staff_json
@require_GET
def staff_conversations_list_api(request):  # Hàm API lấy danh sách cuộc hội thoại để hiển thị trên Livechat Console của nhân viên.
    """Lấy danh sách cuộc hội thoại cho Livechat Console của Nhân viên."""  # Mô tả chức năng của hàm.
    tab = (request.GET.get('tab') or 'processing').strip()
    # Lấy giá trị tham số tab từ URL mà frontend gửi lên.
    # request.GET.get('tab'): Lấy giá trị tab trong query string.
    # Nếu không có tab thì mặc định là 'processing' (Đang xử lý).
    # strip(): Loại bỏ khoảng trắng ở đầu và cuối chuỗi.
    status_filter = (request.GET.get('status') or '').strip()
    # Lấy bộ lọc trạng thái cuộc hội thoại từ URL.
    # Nếu frontend không gửi status thì sử dụng chuỗi rỗng.
    # strip(): Loại bỏ khoảng trắng thừa.
    date_filter = (request.GET.get('date') or '').strip()
    # Lấy ngày tạo cuộc hội thoại mà người dùng muốn lọc.
    # Nếu không có ngày thì sử dụng chuỗi rỗng.
    slot_filter = (request.GET.get('slot') or '').strip()
    # Lấy khung giờ mà người dùng muốn lọc cuộc hội thoại.
    # Ví dụ: 09:00, 14:00, 16:00 hoặc 18:30.
    search_kw = (request.GET.get('search') or '').strip()

    # Từ khóa có thể là tên khách hàng, số điện thoại, username, tag hoặc nội dung tin nhắn.
    is_admin = request.user.is_superuser
    # Kiểm tra tài khoản đang đăng nhập có phải tài khoản quản trị viên cấp cao hay không.
    # is_superuser = True: Người dùng có quyền superuser.
    # is_superuser = False: Người dùng không có quyền superuser.
    base_qs = Conversation.objects.select_related('customer', 'staff').prefetch_related('messages')
    # Tạo QuerySet cơ sở để truy vấn danh sách cuộc hội thoại.
    # Conversation.objects: Truy cập bảng Conversation trong database.
    # select_related('customer', 'staff'): Lấy kèm thông tin khách hàng và nhân viên phụ trách.
    # Cách này giúp giảm số lần truy vấn khi lấy dữ liệu từ các quan hệ ForeignKey hoặc OneToOneField.
    # prefetch_related('messages'): Lấy trước các tin nhắn liên quan đến từng cuộc hội thoại.
    # Cách này giúp hạn chế truy vấn riêng lẻ khi cần lấy nhiều tin nhắn.

    if not is_admin:  # Nếu người đang đăng nhập không phải quản trị viên cấp cao.
        # Nhân viên chỉ thấy phiên chat của chính mình hoặc chưa ai tiếp nhận (hoàn toàn không thấy của nhân viên khác)
        # Nhân viên chỉ thấy phiên chat của chính mình hoặc chưa ai tiếp nhận (hoàn toàn không thấy của nhân viên khác).
        waiting_qs = Conversation.objects.filter(status='Đang chờ', staff__isnull=True)
        # Lấy các cuộc hội thoại đang chờ và chưa được phân công cho nhân viên nào.
        # status='Đang chờ': Chỉ lấy những phiên chat đang chờ tiếp nhận.
        # staff__isnull=True: Chỉ lấy những phiên chưa có nhân viên phụ trách.
        # waiting_qs được sử dụng phía dưới để tính số lượng hội thoại đang chờ.
        processing_qs = Conversation.objects.filter(status='Đang xử lý', staff=request.user)
        # Lấy các cuộc hội thoại đang được chính nhân viên đăng nhập phụ trách.
        # status='Đang xử lý': Chỉ lấy các phiên chat đang xử lý.
        # staff=request.user: Chỉ lấy phiên chat được giao cho nhân viên hiện tại.
        base_qs = base_qs.filter(
            # Lọc QuerySet cơ sở để giới hạn danh sách hội thoại mà nhân viên được phép nhìn thấy.
            Q(status='Đang chờ', staff__isnull=True) |
            # Điều kiện thứ nhất: Lấy các cuộc hội thoại đang chờ và chưa có nhân viên tiếp nhận.
            # Q(): Tạo một điều kiện truy vấn trong Django ORM.
            # |: Toán tử OR, nghĩa là HOẶC.
            Q(status='Đang xử lý', staff=request.user)
            # Điều kiện thứ hai: Lấy các cuộc hội thoại đang xử lý do nhân viên hiện tại phụ trách.
            # Hai điều kiện được nối bằng OR nên chỉ cần thỏa mãn một trong hai là được lấy.
        )  # Kết thúc điều kiện lọc danh sách hội thoại dành cho nhân viên.
    else:  # Nếu người đang đăng nhập là quản trị viên cấp cao.
        waiting_qs = Conversation.objects.filter(status='Đang chờ')
        # Lấy toàn bộ cuộc hội thoại đang chờ, không giới hạn nhân viên phụ trách.
        # Dùng để tính tổng số phiên chat đang chờ.
        processing_qs = Conversation.objects.filter(status='Đang xử lý')
        # Lấy toàn bộ cuộc hội thoại đang xử lý của tất cả nhân viên.
        # Dùng để tính tổng số phiên chat đang xử lý.
        base_qs = base_qs.exclude(status='Kết thúc')

        # exclude(): Lọc bỏ những bản ghi thỏa mãn điều kiện được chỉ định.
        # Quản trị viên có thể xem các phiên đang chờ và đang xử lý của tất cả nhân viên.
    counts = {
        # Tạo dictionary chứa số lượng cuộc hội thoại theo từng nhóm trạng thái.
        'waiting': waiting_qs.count(),
        # Đếm tổng số cuộc hội thoại đang chờ.
        # count(): Đếm số bản ghi thỏa mãn điều kiện trong database.
        'processing': processing_qs.count(),
        # Đếm tổng số cuộc hội thoại đang được xử lý.
        'closed': 0,
        # Gán số lượng hội thoại đã kết thúc bằng 0.
        # Code hiện tại không truy vấn và đếm các cuộc hội thoại đã kết thúc.
        'bot': 0,
        # Gán số lượng hội thoại do bot xử lý bằng 0.
        # Code hiện tại chưa thực hiện truy vấn để đếm hội thoại của bot.
        'all': waiting_qs.count() + processing_qs.count(),
        # Tính tổng số cuộc hội thoại đang chờ và đang xử lý.
        # Cộng số lượng hai nhóm lại để hiển thị tổng số phiên chat hiện có.
    }  # Kết thúc dictionary thống kê số lượng hội thoại.

    if status_filter:  # Kiểm tra xem frontend có gửi bộ lọc trạng thái cụ thể hay không.
        queryset = base_qs.filter(status=status_filter)
        # Nếu có status_filter, lọc danh sách theo trạng thái được gửi lên.
        # Ví dụ: status='Đang xử lý' thì chỉ lấy các phiên đang xử lý.
        # Bộ lọc status được ưu tiên cao hơn bộ lọc tab.
    elif tab == 'waiting':  # Nếu không có status_filter và tab được chọn là waiting.
        queryset = base_qs.filter(status='Đang chờ')
        # Chỉ lấy các cuộc hội thoại đang chờ tiếp nhận.
    elif tab == 'processing':  # Nếu tab được chọn là processing.
        queryset = base_qs.filter(status='Đang xử lý')
        # Chỉ lấy các cuộc hội thoại đang được xử lý.
    elif tab == 'mine':  # Nếu tab được chọn là mine (của tôi).
        queryset = base_qs.filter(staff=request.user, status='Đang xử lý')
        # Chỉ lấy những cuộc hội thoại đang xử lý do nhân viên hiện tại phụ trách.
        # staff=request.user: Lọc theo nhân viên đang đăng nhập.
        # status='Đang xử lý': Loại bỏ các phiên chat không còn được xử lý.
    else:  # Nếu tab không thuộc các trường hợp waiting, processing hoặc mine.
        queryset = base_qs

        # Nhân viên thường chỉ thấy phiên của mình và phiên chưa có người tiếp nhận.
        # Quản trị viên thấy tất cả phiên chưa kết thúc.
    if date_filter:  # Kiểm tra xem người dùng có chọn ngày lọc hay không.
        try:  # Bắt đầu khối try để xử lý trường hợp ngày tháng không hợp lệ.
            queryset = queryset.filter(created_at__date=date.fromisoformat(date_filter))
            # Chuyển chuỗi ngày thành đối tượng date bằng date.fromisoformat().
            # Ví dụ: '2026-11-26' chuyển thành ngày 26/11/2026.
            # created_at__date: Chỉ lấy phần ngày của trường created_at.
            # filter(): Chỉ giữ lại các cuộc hội thoại được tạo trong ngày đã chọn.
        except ValueError:  # Nếu chuỗi ngày không đúng định dạng ISO hoặc không hợp lệ.
            pass  # Bỏ qua lỗi và giữ nguyên QuerySet trước khi lọc ngày.

    slot_ranges = {
        # Tạo dictionary quy định các khung giờ dùng để lọc cuộc hội thoại.
        # Mỗi key là giờ bắt đầu của khung giờ.
        # Mỗi value là một tuple gồm thời gian bắt đầu và kết thúc.
        '09:00': (time(9, 0), time(10, 30)),
        # Khung giờ 09:00: Từ 09 giờ 00 phút đến 10 giờ 30 phút.
        '14:00': (time(14, 0), time(15, 30)),
        # Khung giờ 14:00: Từ 14 giờ 00 phút đến 15 giờ 30 phút.
        '16:00': (time(16, 0), time(17, 30)),
        # Khung giờ 16:00: Từ 16 giờ 00 phút đến 17 giờ 30 phút.
        '18:30': (time(18, 30), time(20, 0)),
        # Khung giờ 18:30: Từ 18 giờ 30 phút đến 20 giờ 00 phút.
    }  # Kết thúc dictionary quy định các khung giờ.
    if slot_filter in slot_ranges:  # Kiểm tra khung giờ frontend gửi lên có tồn tại trong slot_ranges hay không.
        start_t, end_t = slot_ranges[slot_filter]
        # Lấy thời gian bắt đầu và kết thúc tương ứng với khung giờ được chọn.
        # Ví dụ slot_filter='09:00' thì:
        # start_t = 09:00 và end_t = 10:30.
        matched_ids = []
        # Tạo danh sách rỗng để lưu ID của những cuộc hội thoại phù hợp với khung giờ.
        for conv in queryset:  # Duyệt qua từng cuộc hội thoại trong QuerySet hiện tại.
            local_t = timezone.localtime(conv.created_at).time()
            # Chuyển thời gian tạo cuộc hội thoại sang múi giờ địa phương được cấu hình trong Django.
            # timezone.localtime(): Chuyển datetime sang giờ địa phương.
            # .time(): Chỉ lấy phần giờ, phút và giây, không lấy ngày tháng.
            if start_t <= local_t <= end_t:
                # Kiểm tra giờ tạo cuộc hội thoại có nằm trong khung giờ được chọn hay không.
                # Điều kiện này bao gồm cả thời điểm bắt đầu và kết thúc.
                matched_ids.append(conv.id)
                # Nếu thời gian phù hợp, thêm ID cuộc hội thoại vào danh sách matched_ids.
        queryset = queryset.filter(id__in=matched_ids)

        # __in: Kiểm tra giá trị có nằm trong danh sách được cung cấp hay không.
    if search_kw:  # Kiểm tra xem nhân viên có nhập từ khóa tìm kiếm hay không.
        queryset = queryset.filter(
            # Tiếp tục lọc danh sách cuộc hội thoại theo từ khóa tìm kiếm.
            Q(customer__name__icontains=search_kw) |
            # Tìm kiếm theo tên khách hàng.
            # customer__name: Truy cập trường name của khách hàng liên quan.
            # icontains: Tìm chuỗi có chứa từ khóa, không phân biệt chữ hoa và chữ thường.
            Q(customer__phone__icontains=search_kw) |
            # Tìm kiếm theo số điện thoại khách hàng.
            # Nếu số điện thoại có chứa từ khóa thì cuộc hội thoại được giữ lại.
            Q(customer__username__icontains=search_kw) |
            # Tìm kiếm theo username của khách hàng.
            Q(customer_tag__icontains=search_kw) |
            # Tìm kiếm theo thẻ khách hàng được lưu trong trường customer_tag.
            Q(messages__content__icontains=search_kw)
            # Tìm kiếm từ khóa trong nội dung các tin nhắn thuộc cuộc hội thoại.
            # messages__content: Truy cập trường content của các tin nhắn liên quan.
            # Nếu một tin nhắn có nội dung chứa từ khóa thì cuộc hội thoại được tìm thấy.
        ).distinct()

        # Điều này cần thiết vì một cuộc hội thoại có thể có nhiều tin nhắn cùng chứa từ khóa.
        # Nếu không dùng distinct(), một cuộc hội thoại có thể xuất hiện nhiều lần.
    queryset = queryset.order_by('-created_at')
    # Sắp xếp danh sách cuộc hội thoại theo thời gian tạo giảm dần.
    # Dấu '-' trước created_at có nghĩa là sắp xếp từ mới nhất đến cũ nhất.
    conversations = [serialize_conversation_list_item(c, request) for c in queryset]

    # serialize_conversation_list_item(c, request): Chuyển từng đối tượng Conversation thành dữ liệu có thể trả về JSON.
    # c: Đại diện cho một cuộc hội thoại trong vòng lặp.
    # request: Truyền thông tin request vào hàm serialize để xử lý dữ liệu theo ngữ cảnh người dùng.
    # Kết quả được lưu vào danh sách conversations.
    return JsonResponse({
        # Trả dữ liệu JSON từ backend Django về frontend.
        'status': 'success',
        # Thông báo API đã thực hiện thành công.
        'counts': counts,
        # Trả về dictionary thống kê số lượng hội thoại đang chờ, đang xử lý, đã đóng, bot và tổng số.
        # Frontend có thể sử dụng dữ liệu này để hiển thị các bộ đếm trên giao diện.
        'current_tab': tab,
        # Trả về tab hiện tại mà nhân viên đang xem.
        # Ví dụ: waiting, processing hoặc mine.
        'conversations': conversations,
        # Trả về danh sách các cuộc hội thoại đã được lọc, sắp xếp và chuyển đổi dữ liệu.
    }, status=200)  # HTTP 200 (OK): Yêu cầu lấy danh sách hội thoại thành công.


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


@require_superuser_json
@require_http_methods(['GET', 'POST'])
def admin_faqs_api(request):
    """Danh sách và thêm mới câu hỏi FAQ cho Quản lý & Nhân viên quản trị."""
    # Kiểm tra phương thức HTTP mà giao diện gửi đến API.
    # Nếu là GET thì thực hiện chức năng lấy danh sách FAQ.
    if request.method == 'GET':
        # Lấy giá trị category từ URL query parameters.
        # Ví dụ: /api/admin/faqs/?category=Đặt lịch
        category = request.GET.get('category')
        # Lấy trạng thái FAQ từ URL query parameters.
        # Ví dụ: Active hoặc Hidden.
        status_filter = request.GET.get('status')
        # Lấy từ khóa tìm kiếm từ tham số q.
        # Nếu không có q thì sử dụng chuỗi rỗng.
        # strip() loại bỏ khoảng trắng ở đầu và cuối chuỗi.
        search_kw = (request.GET.get('q') or '').strip()

        # Lấy toàn bộ bản ghi FAQ từ bảng FAQ.
        # Lúc này chưa áp dụng bất kỳ điều kiện lọc nào.
        faqs = FAQ.objects.all()
        # Nếu người dùng có chọn danh mục thì lọc FAQ theo category.
        if category:
            # Chỉ giữ lại những FAQ có category trùng với giá trị được chọn.
            faqs = faqs.filter(category=category)
        # Nếu người dùng có chọn trạng thái thì lọc theo status.
        if status_filter:
            # Chỉ lấy những FAQ có trạng thái tương ứng.
            faqs = faqs.filter(status=status_filter)
        # Nếu người dùng nhập từ khóa tìm kiếm thì thực hiện tìm kiếm.
        if search_kw:
            # Tìm kiếm từ khóa trong nhiều trường của bảng FAQ.
            # Q() cho phép kết hợp nhiều điều kiện truy vấn.
            # Dấu | tương đương với phép OR.
            # icontains tìm chuỗi con và không phân biệt chữ hoa, chữ thường.
            faqs = faqs.filter(
                # Tìm từ khóa trong nội dung câu hỏi.
                Q(question__icontains=search_kw) |
                # Hoặc tìm trong danh sách từ khóa liên quan.
                Q(keywords__icontains=search_kw) |
                # Hoặc tìm trong mã FAQ.
                Q(faq_code__icontains=search_kw) |
                # Hoặc tìm trong nội dung câu trả lời.
                Q(answer__icontains=search_kw)
            )
        # Sắp xếp danh sách FAQ theo thời gian tạo giảm dần.
        # Dấu '-' trước created_at có nghĩa là mới nhất được hiển thị trước.
        faqs = faqs.order_by('-created_at')
        # Lấy danh sách các danh mục FAQ hiện có trong cơ sở dữ liệu.
        # values_list('category', flat=True) chỉ lấy giá trị category.
        # distinct() loại bỏ những danh mục bị trùng lặp.
        categories = FAQ.objects.values_list('category', flat=True).distinct()

        return JsonResponse({
            # Thông báo API thực hiện thành công.
            'status': 'success',
            # Đếm tổng số FAQ sau khi đã áp dụng các điều kiện lọc.
            'count': faqs.count(),
            # Chuyển QuerySet danh mục thành danh sách Python.
            'categories': list(categories),
            # Duyệt từng FAQ và chuyển thành dữ liệu JSON
            # thông qua hàm serialize_faq().
            'results': [serialize_faq(f) for f in faqs],
        }, status=200)  # HTTP 200 nghĩa là lấy danh sách thành công.

    # Nếu không phải GET thì chuyển sang xử lý thêm mới FAQ (POST).
    # Đọc dữ liệu JSON mà giao diện gửi lên server.
    # data chứa dữ liệu sau khi phân tích.
    # err chứa phản hồi lỗi nếu dữ liệu không hợp lệ.
    data, err = parse_json_body(request)
    # Nếu quá trình đọc JSON xảy ra lỗi thì trả lỗi về giao diện.
    if err:
        return err

    # Kiểm tra và chuẩn hóa dữ liệu FAQ trước khi lưu vào cơ sở dữ liệu.
    # data: dữ liệu FAQ do giao diện gửi lên.
    # instance=None: đây là thao tác thêm mới, chưa có FAQ cũ.
    # partial=False: yêu cầu nhập đầy đủ các trường bắt buộc.
    # cleaned chứa dữ liệu hợp lệ đã được chuẩn hóa.
    # errors chứa danh sách lỗi nếu dữ liệu không hợp lệ.
    # Nếu dữ liệu có lỗi thì trả về JSON chứa danh sách lỗi.
    # HTTP 400 nghĩa là dữ liệu yêu cầu không hợp lệ.
    cleaned, errors = _validate_faq_payload(data, instance=None, partial=False)
    if errors:
    # Tạo một bản ghi FAQ mới trong cơ sở dữ liệu.
    # **cleaned dùng để truyền các phần tử của dictionary
        return JsonResponse({'status': 'error', 'errors': errors}, status=400)

    faq = FAQ.objects.create(**cleaned)
    # Trả thông báo thêm FAQ thành công về giao diện.
    return JsonResponse({
        # Xác nhận API thực hiện thành công.
        'status': 'success',
        # Tạo thông báo thành công kèm mã FAQ vừa được tạo.
        # faq.faq_code là mã định danh của câu hỏi FAQ mới.
        'message': f'Thêm câu hỏi FAQ [{faq.faq_code}] thành công.',
        # Chuyển đối tượng FAQ vừa tạo thành dữ liệu JSON.
        # serialize_faq() giúp chuẩn hóa các trường cần trả về.
        'data': serialize_faq(faq),
    }, status=201)  # HTTP 201 nghĩa là đã tạo tài nguyên mới thành công.


@require_superuser_json
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


@require_superuser_json
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
    staff_name = "Tư vấn viên Cham Spa" if conversation.staff else None

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


@require_superuser_json
@require_GET
def admin_conversation_monitor_api(request, pk):
    """Lấy thông tin chi tiết phiên chat cần giám sát cho Admin."""
    # Tìm cuộc hội thoại theo khóa chính (pk).
    # select_related() giúp lấy thông tin customer và staff cùng truy vấn,
    # hạn chế việc Django phải truy vấn cơ sở dữ liệu nhiều lần.
    # first() trả về bản ghi đầu tiên tìm được, nếu không có thì trả về None.
    # Nếu không tìm thấy cuộc hội thoại thì trả về thông báo lỗi 404.
    conv = Conversation.objects.select_related('customer', 'staff').filter(pk=pk).first()
    if not conv:
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    # Lấy thông tin khách hàng thuộc cuộc hội thoại.
    customer = conv.customer
    # Tìm thông tin Membership của khách hàng.
    # select_related('tier') lấy thêm thông tin hạng thành viên (tier).
    # Nếu không có khách hàng thì membership được gán bằng None.
    # Lấy tên hạng thành viên.
    # Nếu khách hàng không có Membership hoặc không có tier,
    # mặc định hiển thị là "Thành viên".
    # Lấy tổng số tiền khách hàng đã chi tiêu.
    # Nếu không có thông tin Membership thì mặc định bằng 0.
    membership = Membership.objects.filter(user=customer).select_related('tier').first() if customer else None
    tier_name = membership.tier.name if (membership and membership.tier) else 'Thành viên'
    total_spent = membership.total_spent if membership else 0
    # Chuyển tổng chi tiêu thành số nguyên, định dạng có dấu phân cách hàng nghìn.
    # Ví dụ: 1500000 thành "1.500.000 VNĐ".
    formatted_spent = f"{int(total_spent):,} VNĐ".replace(',', '.')
    # Import hàm build_health_summary từ module health.helpers.

    from health.helpers import build_health_summary

    # Tìm hồ sơ sức khỏe của khách hàng trong bảng UserHealthProfile.
    # Nếu không có khách hàng thì health được gán bằng None.
    # Chuyển hồ sơ sức khỏe thành nội dung tóm tắt dễ hiển thị.
    # Nếu health là None thì hàm build_health_summary cần xử lý trường hợp này.
    health = UserHealthProfile.objects.filter(user=customer).first() if customer else None
    health_summary = build_health_summary(health)

    duration_seconds = int((timezone.now() - conv.created_at).total_seconds())
    duration_display = f"{duration_seconds // 60:02d}:{duration_seconds % 60:02d}"

    # timezone.now() lấy thời gian hiện tại theo cấu hình múi giờ của Django.
    # total_seconds() chuyển khoảng thời gian thành số giây.
    # int() chuyển kết quả thành số nguyên.
    # Chuyển tổng số giây thành định dạng phút:giây.
    # // 60 lấy số phút; % 60 lấy số giây còn lại.
    # :02d đảm bảo mỗi phần luôn có ít nhất 2 chữ số.
    # Ví dụ: 125 giây thành "02:05".
    # Lấy danh sách nhân viên có quyền staff nhưng không phải superuser.
    # exclude() loại nhân viên đang phụ trách cuộc hội thoại hiện tại.
    # Nếu cuộc hội thoại chưa có nhân viên thì dùng 0 để không loại nhân viên nào.
    # values() chỉ lấy ba trường id, name và phone.
    available_staffs = User.objects.filter(is_staff=True, is_superuser=False).exclude(
        pk=conv.staff_id if conv.staff else 0
    # Lấy toàn bộ tin nhắn thuộc cuộc hội thoại hiện tại.
    # order_by('created_at') sắp xếp tin nhắn theo thời gian tăng dần,
    ).values('id', 'name', 'phone')

    messages_qs = conv.messages.all().order_by('created_at')

    # Trả dữ liệu về cho giao diện Admin dưới dạng JSON.
    return JsonResponse({
        # Trạng thái xử lý API thành công.
        'status': 'success',
        # Nhóm thông tin chi tiết của cuộc hội thoại.
        'conversation': {
            # ID của cuộc hội thoại.
            'id': conv.id,
            # Trạng thái hiện tại của cuộc hội thoại.
            'status': conv.status,
            # Chủ đề hoặc nhãn của cuộc hội thoại.
            # Nếu customer_tag trống thì sử dụng nội dung mặc định.
            # Thời điểm cuộc hội thoại được tạo.
            # isoformat() chuyển datetime thành chuỗi ISO 8601.
            'customer_tag': conv.customer_tag or 'Trị liệu vai gáy & Đặt lịch',
            'created_at': conv.created_at.isoformat(),
            # Thời gian cuộc hội thoại đã tồn tại theo định dạng phút:giây.
            'duration_display': duration_display,
            # Thông tin nhân viên đang phụ trách cuộc hội thoại.
            # Nếu có staff thì trả về thông tin nhân viên.
            # Nếu không có staff thì trả về None.
            'staff': {
                # ID của nhân viên.
                'id': conv.staff.id,
                # Tên nhân viên.
                'name': conv.staff.name,
                # Đang gán trạng thái online là True.
                'is_online': True,
            } if conv.staff else None,
            # Thông tin khách hàng tham gia cuộc hội thoại.
            'customer': {
                # ID khách hàng; nếu không có khách hàng thì trả về None.
                'id': customer.id if customer else None,
                # Tên khách hàng; nếu không có thì hiển thị Khách vãng lai.
                'name': customer.name if customer else 'Khách vãng lai',
                # Số điện thoại; nếu không có khách hàng thì trả chuỗi rỗng.
                'phone': customer.phone if customer else '',
                # Email; nếu không có khách hàng thì trả chuỗi rỗng.
                'email': customer.email if customer else '',
                # Tên hạng thành viên của khách hàng.
                'tier_name': tier_name,
                # Tổng số tiền khách hàng đã chi tiêu, có định dạng VNĐ.
                'total_spent': formatted_spent,
                # Nội dung tóm tắt hồ sơ sức khỏe của khách hàng.
                'health_summary': health_summary,
            },
            # Trạng thái SLA được gán cố định là Tốt (< 30 giây).
            'sla_status': 'Tốt (< 30 giây)',
            # Mã màu hoặc loại badge được giao diện sử dụng để hiển thị SLA.
            'sla_badge': 'success',
            # Chuyển từng tin nhắn thành dictionary/JSON bằng serialize_message().
            # List comprehension giúp xử lý toàn bộ tin nhắn trong một dòng.
            # Chuyển QuerySet nhân viên thành danh sách Python.
            # Danh sách này được trả về JSON để Admin có thể chọn nhân viên khác.
            'messages': [serialize_message(m) for m in messages_qs],
            'available_staffs': list(available_staffs),
        },
    }, status=200)  # Trả HTTP 200 nghĩa là API xử lý thành công.


@require_superuser_json
@require_POST
def admin_reassign_staff_api(request, pk):
    """Chuyển cuộc hội thoại sang cho nhân viên khác."""
    # Tìm cuộc hội thoại trong bảng Conversation theo khóa chính (pk).
    # first() lấy bản ghi đầu tiên nếu tìm thấy.
    # Nếu không tìm thấy thì trả về None.
    conv = Conversation.objects.filter(pk=pk).first()
    # Kiểm tra cuộc hội thoại có tồn tại hay không.
    # Nếu không tồn tại, trả về thông báo lỗi với HTTP 404.
    if not conv:
    # Đọc dữ liệu JSON được gửi từ giao diện Admin lên server.
    # data chứa dữ liệu sau khi phân tích JSON.
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    data, err = parse_json_body(request)
    # Nếu quá trình đọc hoặc phân tích JSON xảy ra lỗi,
    # trả ngay phản hồi lỗi về cho giao diện.
    if err:
        return err

    # Lấy ID của nhân viên mới từ dữ liệu JSON.
    # staff_id là tên trường mà giao diện gửi lên server.
    new_staff_id = data.get('staff_id')
    # Kiểm tra Admin đã chọn nhân viên mới hay chưa.
    # Nếu staff_id không tồn tại hoặc có giá trị rỗng,
    # trả về lỗi HTTP 400.
    if not new_staff_id:
        return json_error('Vui lòng chọn nhân viên tiếp nhận mới.', status=400)

    # Tìm nhân viên mới trong bảng User theo ID.
    # Điều kiện is_staff=True đảm bảo tài khoản có quyền nhân viên.
    # first() trả về đối tượng User nếu tìm thấy, nếu không thì None.
    # Kiểm tra nhân viên mới có tồn tại và hợp lệ hay không.
    # Nếu không tìm thấy, trả về lỗi HTTP 400.
    new_staff = User.objects.filter(pk=new_staff_id, is_staff=True).first()
    if not new_staff:
        return json_error('Nhân viên không tồn tại hoặc không hợp lệ.', status=400)

    # Lưu lại tên nhân viên đang phụ trách trước khi chuyển giao.
    # Nếu cuộc hội thoại chưa có nhân viên thì sử dụng "Chưa có".
    # Lưu ý: biến này hiện chưa được sử dụng ở phần code phía dưới.
    # Gán nhân viên mới vào trường staff của cuộc hội thoại.
    old_staff_name = conv.staff.name if conv.staff else 'Chưa có'
    conv.staff = new_staff
    # Chuyển trạng thái cuộc hội thoại thành "Đang xử lý".
    conv.status = 'Đang xử lý'
    # Lưu hai trường staff và status vào cơ sở dữ liệu.
    # update_fields giúp Django chỉ cập nhật hai trường được chỉ định.
    conv.save(update_fields=['staff', 'status'])

    # Trả kết quả JSON về giao diện Admin sau khi chuyển giao thành công.
    return JsonResponse({
        # Thông báo API thực hiện thành công.
        'status': 'success',
        # Thông báo cho biết cuộc hội thoại đã được chuyển cho nhân viên nào.
        # f-string cho phép chèn tên nhân viên vào chuỗi.
        'message': f'Đã chuyển giao thành công cho nhân viên {new_staff.name}.',
        # Trả thông tin nhân viên mới cho giao diện.
            # ID của nhân viên mới.
            # Tên của nhân viên mới.
        'staff': {'id': new_staff.id, 'name': new_staff.name},
    }, status=200)  # HTTP 200 nghĩa là yêu cầu xử lý thành công


@require_superuser_json
@require_POST
def admin_takeover_conversation_api(request, pk):
    """Admin trực tiếp tiếp quản cuộc hội thoại."""
    # Tìm cuộc hội thoại trong bảng Conversation theo khóa chính (pk).
    # first() lấy bản ghi đầu tiên nếu tìm thấy.
    # Nếu không tìm thấy thì trả về None.
    conv = Conversation.objects.filter(pk=pk).first()
    # Kiểm tra cuộc hội thoại có tồn tại hay không.
    # Nếu không tồn tại, trả về thông báo lỗi HTTP 404.
    if not conv:
    # Lấy tên của tài khoản đang đăng nhập và gửi yêu cầu lên API.
    # request.user đại diện cho người dùng hiện tại.
    # Nếu tài khoản không có tên (name rỗng hoặc None),
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

    admin_name = request.user.name or 'Quản trị viên'
    # Gán tài khoản Admin hiện tại làm nhân viên phụ trách cuộc hội thoại.
    # request.user chính là đối tượng User đang đăng nhập.
    conv.staff = request.user
    # Cập nhật trạng thái cuộc hội thoại thành "Đang xử lý".
    conv.status = 'Đang xử lý'
    # Lưu thông tin cập nhật vào cơ sở dữ liệu.
    # update_fields chỉ cập nhật hai trường staff và status,
    # không cập nhật các trường khác của Conversation.
    conv.save(update_fields=['staff', 'status'])

    # Trả kết quả JSON về giao diện Admin sau khi tiếp quản thành công.
    return JsonResponse({
        # Xác nhận API thực hiện thành công.
        'status': 'success',
        # Tạo thông báo có chứa tên Admin đang tiếp quản.
        # f-string cho phép chèn biến admin_name vào chuỗi.
        'message': f'Quản lý {admin_name} đã tiếp quản cuộc hội thoại thành công.',
        # Trả tên Admin về giao diện để hiển thị thông tin người phụ trách.
        'staff_name': admin_name,
    }, status=200)  # HTTP 200 nghĩa là yêu cầu được xử lý thành công.


@require_staff_json
@require_POST
def chat_upload_media_api(request):
    """Tải lên hình ảnh hoặc video đính kèm cho tin nhắn chat."""
    # Kiểm tra trong request.FILES có tệp được gửi lên với tên 'file' hay không.
    # request.FILES chứa các tệp mà người dùng tải lên thông qua form.
    if 'file' not in request.FILES:
        # Nếu không tìm thấy tệp, trả về thông báo lỗi HTTP 400.
        return json_error('Không tìm thấy tệp tải lên.', status=400)

    uploaded_file = request.FILES['file']
    # Tách phần đuôi mở rộng của tên tệp.
    # os.path.splitext() trả về hai phần:
    # (tên tệp, phần mở rộng).
    # [1] lấy phần mở rộng.
    # lower() chuyển phần mở rộng thành chữ thường.
    # Ví dụ: "ANH.JPG" sẽ có ext là ".jpg".
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    # Khai báo danh sách các định dạng tệp được phép tải lên.
    # Bao gồm hình ảnh: JPG, JPEG, PNG, WebP, GIF.
    # Bao gồm video: MP4, MOV, WebM.
    # Kiểm tra phần mở rộng của tệp có nằm trong danh sách cho phép không.
    allowed_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4', '.mov', '.webm')
    if ext not in allowed_exts:
        # Nếu định dạng không hợp lệ, trả về lỗi HTTP 400.
    # Kiểm tra dung lượng tệp có vượt quá 25 MB hay không.
    # 1024 * 1024 = 1 MB theo cách tính 1024 byte.
        return json_error('Định dạng tệp không được hỗ trợ. Vui lòng tải ảnh (JPG, PNG, WebP) hoặc video (MP4, MOV).', status=400)

    if uploaded_file.size > 25 * 1024 * 1024:
        return json_error('Dung lượng tệp vượt quá giới hạn 25MB.', status=400)

        # Nếu tệp vượt quá 25 MB, trả về thông báo lỗi HTTP 400.
    # Lấy tên tệp không bao gồm phần mở rộng.
    # get_valid_filename() chuẩn hóa tên tệp để phù hợp khi lưu trữ.
    # [:60] giới hạn tên tối đa 60 ký tự.
    # Nếu tên sau khi chuẩn hóa rỗng thì sử dụng tên mặc định "media".
    # Tạo đường dẫn lưu tệp trên hệ thống lưu trữ.
    # chat_media/: thư mục lưu tệp đính kèm chat.
    # %Y%m: thư mục theo năm và tháng, ví dụ 202611.
    # uuid.uuid4().hex[:8]: tạo 8 ký tự định danh ngẫu nhiên.
    # safe_stem: tên tệp đã được chuẩn hóa.
    # ext: phần mở rộng ban đầu.
    # Đọc nội dung tệp tải lên và chuyển thành ContentFile.
    # default_storage.save() lưu tệp vào hệ thống lưu trữ mặc định của Django.
    # Kết quả saved_path là đường dẫn thực tế mà hệ thống đã lưu.
    # Lấy URL truy cập tệp từ hệ thống lưu trữ.
    # URL này sẽ được gửi về giao diện để hiển thị hình ảnh hoặc video.
    safe_stem = get_valid_filename(os.path.splitext(uploaded_file.name)[0])[:60] or 'media'
    unique_filename = f"chat_media/{timezone.now().strftime('%Y%m')}/{uuid.uuid4().hex[:8]}_{safe_stem}{ext}"
    saved_path = default_storage.save(unique_filename, ContentFile(uploaded_file.read()))
    file_url = default_storage.url(saved_path)

    # Chuyển dung lượng tệp từ byte sang KB.
    # 1 KB = 1024 byte.
    size_kb = uploaded_file.size / 1024
    # Định dạng dung lượng tệp để hiển thị dễ đọc.
    # Nếu nhỏ hơn 1024 KB thì hiển thị bằng KB.
    # Nếu từ 1024 KB trở lên thì chuyển sang MB.
    # :.1f giữ lại một chữ số sau dấu thập phân.
    # Kiểm tra tệp có phải hình ảnh hay không.
    # Nếu phần mở rộng thuộc danh sách này thì is_image = True.
    # Nếu không thì is_image = False.
    # Xác định loại tin nhắn dựa trên loại tệp.
    # Nếu là hình ảnh thì message_type = 'IMAGE'.
    # Nếu là video thì message_type = 'FILE'.
    formatted_size = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
    is_image = ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    message_type = 'IMAGE' if is_image else 'FILE'

    # Trả kết quả JSON về giao diện sau khi tải tệp thành công.
    return JsonResponse({
        # Trạng thái API xử lý thành công.
        'status': 'success',
        # URL của tệp đã được lưu trên hệ thống.
        'file_url': file_url,
        # Tên gốc của tệp do người dùng tải lên.
        'file_name': uploaded_file.name,
        # Dung lượng tệp đã được định dạng thành KB hoặc MB.
        'file_size': formatted_size,
        # Loại tin nhắn tương ứng với tệp: IMAGE hoặc FILE.
        'message_type': message_type,
    }, status=200)  # HTTP 200 nghĩa là tải tệp thành công.


@require_superuser_json
@require_POST
def admin_send_message_api(request, pk):  # Hàm API cho phép Admin gửi tin nhắn trực tiếp vào cuộc hội thoại.
    """Admin gửi tin nhắn can thiệp / chỉ đạo trực tiếp vào phiên chat."""  # Mô tả chức năng của hàm.
    conv = Conversation.objects.filter(pk=pk).first()
    # Truy vấn bảng Conversation để tìm cuộc hội thoại có ID bằng pk được truyền vào.
    # filter(pk=pk): Lọc cuộc hội thoại theo khóa chính.
    # first(): Lấy bản ghi đầu tiên tìm được, nếu không có thì trả về None.
    # Kết quả được lưu vào biến conv.
    if not conv:  # Kiểm tra xem cuộc hội thoại có tồn tại hay không.
        return json_error('Không tìm thấy cuộc hội thoại.', status=404)

        # HTTP 404 (Not Found): Không tìm thấy dữ liệu.
    data, err = parse_json_body(request)
    # Gọi hàm parse_json_body() để đọc và phân tích dữ liệu JSON frontend gửi lên.
    # request: Chứa yêu cầu HTTP từ frontend.
    # Hàm trả về hai giá trị:
    # data: Dictionary chứa dữ liệu JSON đã đọc được.
    # err: Thông tin lỗi nếu quá trình đọc hoặc phân tích JSON thất bại.
    if err:  # Kiểm tra xem quá trình đọc dữ liệu JSON có phát sinh lỗi hay không.
        return err  # Nếu có lỗi, trả về phản hồi lỗi ngay lập tức.

    content = str(data.get('content') or '').strip()
    # Lấy nội dung tin nhắn từ trường content trong dữ liệu JSON.
    # data.get('content'): Lấy nội dung tin nhắn frontend gửi lên.
    # Nếu không có nội dung thì sử dụng chuỗi rỗng.
    # str(): Chuyển dữ liệu thành chuỗi.
    # strip(): Loại bỏ khoảng trắng ở đầu và cuối nội dung.
    attachment_url = data.get('attachment_url')
    # Lấy đường dẫn URL của tệp đính kèm từ frontend.
    # Ví dụ: URL hình ảnh hoặc tài liệu đã được tải lên hệ thống.
    # Nếu không có tệp đính kèm thì giá trị có thể là None.
    attachment_name = data.get('attachment_name')
    # Lấy tên tệp đính kèm do frontend gửi lên.
    # Ví dụ: hinh_anh.jpg hoặc tai_lieu.pdf.
    attachment_size = data.get('attachment_size')
    # Lấy dung lượng tệp đính kèm từ frontend.
    # Thông tin này có thể được dùng để hiển thị kích thước tệp trên giao diện.
    message_type = data.get('message_type') or ('IMAGE' if attachment_url else 'TEXT')

    # Nếu frontend có gửi message_type thì sử dụng giá trị đó.
    # Nếu không có message_type:
    # - Có attachment_url: Mặc định là IMAGE.
    # - Không có attachment_url: Mặc định là TEXT.
    # Toán tử điều kiện giúp lựa chọn loại tin nhắn phù hợp.
    if not content and not attachment_url:
        # Kiểm tra xem tin nhắn có đồng thời không có nội dung và không có tệp đính kèm hay không.
        # not content: Nội dung tin nhắn trống.
        # not attachment_url: Không có tệp đính kèm.
        return json_error('Nội dung tin nhắn hoặc tệp đính kèm không được để trống.', status=400)

        # HTTP 400 (Bad Request): Dữ liệu yêu cầu không hợp lệ.
    msg = ConversationMessage.objects.create(
        # Tạo một bản ghi tin nhắn mới trong bảng ConversationMessage.
        # Kết quả đối tượng tin nhắn mới được lưu vào biến msg.
        conversation=conv,
        # Liên kết tin nhắn mới với cuộc hội thoại vừa tìm được.
        # conversation là khóa ngoại tham chiếu đến bảng Conversation.
        sender_type='Staff',
        # Xác định loại người gửi là Staff (nhân viên).
        # Trong trường hợp này, Admin được hệ thống ghi nhận theo loại người gửi Staff.
        message_type=message_type,
        # Lưu loại tin nhắn đã xác định ở phía trên.
        # Có thể là TEXT hoặc IMAGE tùy dữ liệu gửi lên.
        content=content,
        # Lưu nội dung văn bản của tin nhắn vào database.
        attachment_url=attachment_url,
        # Lưu đường dẫn URL của tệp đính kèm.
        # Nếu không có tệp thì trường này có thể là None.
        attachment_name=attachment_name,
        # Lưu tên tệp đính kèm.
        attachment_size=attachment_size,
        # Lưu dung lượng tệp đính kèm.
    )  # Kết thúc thao tác tạo tin nhắn mới.

    return JsonResponse({
        'status': 'success',
        'message': serialize_message(msg),
    }, status=201)


        # Thông báo API đã gửi tin nhắn thành công.
        # Gọi serialize_message() để chuyển đối tượng tin nhắn thành dictionary JSON.
        # msg là tin nhắn vừa được tạo trong database.
        # Kết quả chứa thông tin tin nhắn để frontend cập nhật giao diện chat.
@require_superuser_json
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
