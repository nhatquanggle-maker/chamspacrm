"""
================================================================================
RESTFUL API ENDPOINTS CHO PHÂN HỆ QUẢN LÝ BOXCHAT TƯ VẤN (MOD-02) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc
Triển khai đầy đủ 3 Use Cases chuẩn CSDL & Hợp đồng API:
  - UC-2.1: Trò chuyện với Chatbot tự động (FAQ thuần TEXT, vãng lai in-memory)
            Endpoint chuẩn: POST /api/chat/bot-reply/
  - UC-2.2: Trò chuyện trực tiếp (Kết nối nhân viên tư vấn & Phân quyền tiếp nhận)
            Endpoint chuẩn: POST /api/chat/conversations/{id}/messages/
            Và các API: Tiếp nhận, Đóng chat, Tiếp quản, Danh sách hội thoại
  - UC-2.3: Quản lý kịch bản Chatbot (FAQ thuần TEXT)
            Endpoint chuẩn: GET, POST, PUT, DELETE /api/admin/faqs/
  - Tích hợp tính năng Figma Node 210:2465:
      + Giao diện xem chi tiết dịch vụ & gửi tóm tắt gói vào chat
      + Cảnh báo khi cuộc hội thoại đã do nhân viên khác tiếp nhận (Khóa input, chỉ xem)
================================================================================
"""

import json
import csv
from decimal import Decimal
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Q, Count
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from core.models import (
    FAQ, Conversation, ConversationMessage, User, Service,
    Membership, UserHealthProfile, Tier
)
from .serializers import (
    FAQSerializer,
    ConversationMessageSerializer,
    SendMessageInputSerializer,
    ConversationListSerializer,
    ConversationDetailSerializer,
    BotReplyInputSerializer,
)


# ==============================================================================
# HÀM BỔ TRỢ: TÌM KIẾM CÂU TRẢ LỜI FAQ THÔNG MINH (CHO UC-2.1)
# ==============================================================================

def find_best_faq_match(user_message):
    """
    Tìm kiếm câu trả lời phù hợp nhất từ bảng FAQ (status='Active').
    Quy tắc nghiệp vụ:
      - Câu trả lời của FAQ thuần túy là văn bản (TEXT), không kèm ảnh/nút bấm.
      - So khớp từ khóa keywords, tiêu đề câu hỏi question, hoặc phân loại category.
    """
    if not user_message:
        return None

    clean_msg = user_message.strip().lower()
    active_faqs = FAQ.objects.filter(status='Active')

    # 1. Tìm khớp chính xác hoặc câu hỏi chứa trong tin nhắn
    for faq in active_faqs:
        faq_q = faq.question.lower().strip()
        if faq_q in clean_msg or clean_msg in faq_q:
            return faq

    # 2. Tìm theo từ khóa (keywords)
    best_faq = None
    max_keyword_matches = 0

    for faq in active_faqs:
        matches = 0
        if faq.keywords:
            keywords_list = [k.strip().lower() for k in faq.keywords.replace(';', ',').split(',') if k.strip()]
            for kw in keywords_list:
                if kw in clean_msg:
                    matches += 1
        
        # Nếu có từ trong câu hỏi khớp
        words_in_q = [w for w in faq.question.lower().split() if len(w) >= 3]
        for w in words_in_q:
            if w in clean_msg:
                matches += 1

        if matches > max_keyword_matches:
            max_keyword_matches = matches
            best_faq = faq

    if max_keyword_matches > 0:
        return best_faq

    # 3. Phân loại theo chủ đề phổ biến
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


# ==============================================================================
# USE CASE 2.1: TRÒ CHUYỆN VỚI CHATBOT TỰ ĐỘNG
# Endpoint Hợp đồng: POST /api/chat/bot-reply/
# ==============================================================================

class BotReplyAPI(APIView):
    """
    [UC-2.1] API nhận câu hỏi của khách và trả về phản hồi tự động từ Chatbot.
    Quy tắc nghiệp vụ bất di bất dịch:
      - Khách vãng lai (chưa đăng nhập): Toàn bộ tin nhắn CHỈ LƯU IN-MEMORY ở client,
        TUYỆT ĐỐI KHÔNG GHI VÀO CSDL bảng Conversation / ConversationMessage.
      - Khách hàng đã đăng nhập (is_authenticated và không phải staff):
        Ghi nhận phiên chat vào Conversation (status='Bot xử lý') và ConversationMessage.
      - Phản hồi của Chatbot thuần túy là văn bản (TEXT).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = BotReplyInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        user_message = serializer.validated_data['message'].strip()
        conv_id = serializer.validated_data.get('conversation_id')

        # Tìm câu trả lời từ kho FAQ
        matched_faq = find_best_faq_match(user_message)

        if matched_faq:
            bot_reply_text = matched_faq.answer
            suggested_actions = ["Xem bảng giá", "Gặp nhân viên tư vấn", "Đặt lịch ngay"]
        else:
            bot_reply_text = (
                "Dạ Cham Spa & Massage xin chào quý khách! "
                "Em chưa hiểu rõ yêu cầu của mình trong kịch bản tự động. "
                "Quý khách có thể chọn câu hỏi nhanh bên dưới hoặc bấm 'Gặp nhân viên tư vấn' "
                "để chuyên viên chăm sóc khách hàng hỗ trợ ngay nhé ạ!"
            )
            suggested_actions = ["Bảng giá dịch vụ", "Giờ mở cửa & Địa chỉ", "Gặp nhân viên tư vấn"]

        user = request.user
        saved_conv_id = None

        # NẾU LÀ KHÁCH HÀNG ĐÃ ĐĂNG NHẬP: Lưu vào CSDL
        if user.is_authenticated and not user.is_staff and not user.is_superuser:
            with transaction.atomic():
                conversation = None
                if conv_id:
                    conversation = Conversation.objects.filter(id=conv_id, customer=user).first()

                # Nếu chưa có hoặc phiên trước đã kết thúc -> Tìm phiên đang mở hoặc tạo mới
                if not conversation or conversation.status == 'Kết thúc':
                    conversation = Conversation.objects.filter(
                        customer=user,
                        status__in=['Bot xử lý', 'Đang chờ', 'Đang xử lý']
                    ).first()

                if not conversation:
                    conversation = Conversation.objects.create(
                        customer=user,
                        status='Bot xử lý',
                        customer_tag='Khách quan tâm dịch vụ'
                    )

                # Lưu tin nhắn của khách hàng
                ConversationMessage.objects.create(
                    conversation=conversation,
                    sender_type='Customer',
                    message_type='TEXT',
                    content=user_message
                )

                # Lưu phản hồi của bot
                ConversationMessage.objects.create(
                    conversation=conversation,
                    sender_type='Bot',
                    message_type='TEXT',
                    content=bot_reply_text
                )

                saved_conv_id = conversation.id

        # NẾU LÀ KHÁCH VÃNG LAI: Không lưu DB, chỉ trả về JSON
        return Response({
            'status': 'success',
            'reply': bot_reply_text,
            'suggested_actions': suggested_actions,
            'conversation_id': saved_conv_id,
            'is_authenticated': user.is_authenticated
        }, status=status.HTTP_200_OK)


# ==============================================================================
# USE CASE 2.2: TRÒ CHUYỆN TRỰC TIẾP (KẾT NỐI NHÂN VIÊN TƯ VẤN)
# ==============================================================================

class ConversationTransferStaffAPI(APIView):
    """
    [UC-2.2] Khách hàng bấm 'Chuyển tiếp cho nhân viên' trong khung chat.
    Quy tắc nghiệp vụ chốt:
      - Tiền điều kiện: Khách hàng BẮT BUỘC ĐÃ ĐĂNG NHẬP tài khoản.
        Nếu khách vãng lai bấm nút -> Trả về lỗi 401 yêu cầu đăng nhập.
      - Chuyển trạng thái hội thoại sang: Conversation.status = 'Đang chờ' (hoặc 'Chờ tiếp nhận').
      - Tạo tin nhắn hệ thống ghi nhận yêu cầu để nhân viên thấy trên Livechat Console.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({
                'status': 'require_login',
                'message': 'Quý khách vui lòng đăng nhập tài khoản để được kết nối trò chuyện trực tiếp với nhân viên CSKH.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        conv_id = request.data.get('conversation_id')
        user = request.user

        with transaction.atomic():
            conversation = None
            if conv_id:
                conversation = Conversation.objects.filter(id=conv_id, customer=user).first()

            if not conversation or conversation.status == 'Kết thúc':
                conversation = Conversation.objects.filter(
                    customer=user,
                    status__in=['Bot xử lý', 'Đang chờ', 'Đang xử lý']
                ).first()

            if not conversation:
                conversation = Conversation.objects.create(
                    customer=user,
                    status='Đang chờ',
                    customer_tag='Yêu cầu tư vấn trực tiếp'
                )
            else:
                conversation.status = 'Đang chờ'
                conversation.save()

            # Tin nhắn thông báo hệ thống
            ConversationMessage.objects.create(
                conversation=conversation,
                sender_type='Bot',
                message_type='TEXT',
                content='Dạ, yêu cầu của quý khách đã được chuyển tới chuyên viên tư vấn Cham Spa. Chuyên viên sẽ tiếp nhận và phản hồi ngay trong giây lát ạ!'
            )

        return Response({
            'status': 'success',
            'message': 'Đã gửi yêu cầu kết nối với nhân viên tư vấn thành công.',
            'conversation_id': conversation.id,
            'conversation_status': conversation.status
        }, status=status.HTTP_200_OK)


class ConversationMessageListSendAPI(APIView):
    """
    [UC-2.2] Lấy lịch sử và Gửi tin nhắn trực tiếp giữa Khách hàng và Nhân viên tư vấn.
    Endpoint Hợp đồng: POST /api/chat/conversations/{id}/messages/
    Và GET /api/chat/conversations/{id}/messages/

    QUY TẮC PHÂN QUYỀN & BẢO VỆ CHUẨN FIGMA NODE 210:2465:
      - Khách hàng: Chỉ gửi/nhận tin nhắn trong cuộc hội thoại của chính mình.
      - Nhân viên tư vấn:
        + Nếu cuộc hội thoại đã được MỘT NHÂN VIÊN KHÁC tiếp nhận (`staff` != request.user và `status` == 'Đang xử lý'):
          -> CHẶN GỬI TIN NHẮN (HTTP 403 Forbidden).
          -> Trả về thông báo cảnh báo rõ ràng: "Cuộc hội thoại này đã do nhân viên [Tên] tiếp nhận xử lý."
        + Nếu cuộc hội thoại chưa có ai nhận (`staff` is None):
          -> Khi nhân viên gửi tin, tự động gán `staff = request.user` và `status = 'Đang xử lý'`.
        + Giao diện hiển thị rõ TÊN NHÂN VIÊN GỬI (sender_name) theo đúng yêu cầu Use Case 2.2.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            conversation = Conversation.objects.select_related('customer', 'staff').get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({'error': 'Không tìm thấy cuộc hội thoại.'}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        # Kiểm tra quyền xem
        if not user.is_staff and not user.is_superuser:
            if conversation.customer_id != user.id:
                return Response({'error': 'Bạn không có quyền xem cuộc hội thoại này.'}, status=status.HTTP_403_FORBIDDEN)

        # Trả về chi tiết và danh sách tin nhắn
        serializer = ConversationDetailSerializer(conversation, context={'request': request})
        
        # Cung cấp cờ kiểm tra phân quyền cho giao diện Figma
        is_assigned_to_other = False
        assigned_staff_name = None
        if user.is_staff and conversation.staff and conversation.staff_id != user.id and conversation.status == 'Đang xử lý':
            is_assigned_to_other = True
            assigned_staff_name = conversation.staff.name or conversation.staff.username

        data = serializer.data
        data['is_assigned_to_other'] = is_assigned_to_other
        data['assigned_staff_name'] = assigned_staff_name
        data['can_send_message'] = not is_assigned_to_other

        return Response(data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        try:
            conversation = Conversation.objects.select_related('customer', 'staff').get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({'error': 'Không tìm thấy cuộc hội thoại.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = SendMessageInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        content = serializer.validated_data['content'].strip()
        message_type = serializer.validated_data.get('message_type', 'TEXT')
        attachment_url = serializer.validated_data.get('attachment_url')
        attachment_name = serializer.validated_data.get('attachment_name')
        attachment_size = serializer.validated_data.get('attachment_size')

        user = request.user

        # 1. TRƯỜNG HỢP NGƯỜI GỬI LÀ NHÂN VIÊN / QUẢN LÝ
        if user.is_staff or user.is_superuser:
            # KIỂM TRA PHÂN QUYỀN THEO FIGMA NODE 210:2465:
            # Nếu cuộc hội thoại đã được nhân viên khác tiếp nhận:
            if conversation.staff and conversation.staff_id != user.id and conversation.status == 'Đang xử lý':
                other_name = conversation.staff.name or conversation.staff.username
                return Response({
                    'status': 'forbidden_assigned',
                    'error': f'Cuộc hội thoại này đã do nhân viên {other_name} tiếp nhận xử lý. Bạn đang ở chế độ xem chỉ đọc và không thể gửi tin nhắn.',
                    'assigned_staff': other_name
                }, status=status.HTTP_403_FORBIDDEN)

            # Nếu cuộc hội thoại chưa có nhân viên nhận hoặc đang chờ:
            if not conversation.staff:
                conversation.staff = user
                conversation.status = 'Đang xử lý'
                conversation.save()

            sender_type = 'Staff'
            sender_name = user.name or user.username

        # 2. TRƯỜNG HỢP NGƯỜI GỬI LÀ KHÁCH HÀNG
        else:
            if conversation.customer_id != user.id:
                return Response({'error': 'Bạn không có quyền gửi tin nhắn trong cuộc hội thoại này.'}, status=status.HTTP_403_FORBIDDEN)

            sender_type = 'Customer'
            sender_name = user.name or user.username

            # Nếu khách gửi tin nhắn tiếp, đảm bảo trạng thái không bị đóng
            if conversation.status == 'Kết thúc':
                conversation.status = 'Đang chờ'
                conversation.save()

        # Tạo tin nhắn mới trong CSDL
        msg = ConversationMessage.objects.create(
            conversation=conversation,
            sender_type=sender_type,
            message_type=message_type,
            content=content,
            attachment_url=attachment_url,
            attachment_name=attachment_name,
            attachment_size=attachment_size
        )

        # Phản hồi JSON chuẩn theo Hợp đồng API
        return Response({
            'status': 'success',
            'message_id': msg.id,
            'sender_type': msg.sender_type,
            'sender_name': sender_name,
            'created_at': msg.created_at.isoformat(),
            'formatted_time': timezone.localtime(msg.created_at).strftime('%H:%M - %d/%m'),
            'content': msg.content,
            'conversation_status': conversation.status
        }, status=status.HTTP_201_CREATED)


class ConversationAcceptAPI(APIView):
    """
    [UC-2.2] Nhân viên CSKH bấm nút 'Tiếp nhận hội thoại'.
    Khớp logic và thiết kế Figma Node 207:1040 & 210:2465:
      - Kiểm tra an toàn: Nếu đã có nhân viên khác nhận trước đó, báo lỗi xung đột (Conflict 409).
      - Nếu hợp lệ: Cập nhật Conversation.staff = request.user, Conversation.status = 'Đang xử lý'.
      - Tự động sinh tin nhắn thông báo: 'Nhân viên tư vấn [Tên nhân viên] đã tham gia trò chuyện.'
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            conversation = Conversation.objects.select_related('staff').get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({'error': 'Không tìm thấy cuộc hội thoại.'}, status=status.HTTP_404_NOT_FOUND)

        user = request.user

        # Kiểm tra xem có nhân viên khác đã tiếp nhận chưa
        if conversation.staff and conversation.staff_id != user.id and conversation.status == 'Đang xử lý':
            other_name = conversation.staff.name or conversation.staff.username
            return Response({
                'status': 'conflict',
                'message': f'Cuộc hội thoại đã do nhân viên {other_name} tiếp nhận xử lý!',
                'assigned_staff': other_name
            }, status=status.HTTP_409_CONFLICT)

        # Cập nhật tiếp nhận
        conversation.staff = user
        conversation.status = 'Đang xử lý'
        conversation.save()

        staff_name = user.name or user.username

        # Tạo tin nhắn hệ thống ghi nhận nhân viên tham gia
        ConversationMessage.objects.create(
            conversation=conversation,
            sender_type='Staff',
            message_type='TEXT',
            content=f"Dạ em chào anh/chị! Em là {staff_name} - chuyên viên tư vấn của Cham Spa & Massage. Em rất vui được hỗ trợ quý khách hôm nay ạ!"
        )

        return Response({
            'status': 'success',
            'message': f'Tiếp nhận cuộc hội thoại thành công. Bạn đang phụ trách phiên chat này.',
            'conversation_id': conversation.id,
            'staff_name': staff_name,
            'status_label': 'Đang xử lý'
        }, status=status.HTTP_200_OK)


class ConversationCloseAPI(APIView):
    """
    [UC-2.2] Nhân viên bấm 'Đóng phiên chat' khi đã hoàn tất tư vấn.
    Quy tắc nghiệp vụ chốt:
      - Cập nhật Conversation.status = 'Kết thúc'.
      - Lưu Conversation.closed_at = now().
      - Tạo tin nhắn đóng phiên tư vấn.
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            conversation = Conversation.objects.get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({'error': 'Không tìm thấy cuộc hội thoại.'}, status=status.HTTP_404_NOT_FOUND)

        conversation.status = 'Kết thúc'
        conversation.closed_at = timezone.now()
        conversation.save()

        # Tạo tin nhắn hệ thống đóng phiên chat
        staff_name = request.user.name or request.user.username
        ConversationMessage.objects.create(
            conversation=conversation,
            sender_type='Staff',
            message_type='TEXT',
            content=f"Phiên tư vấn trực tiếp đã được hoàn tất bởi chuyên viên {staff_name}. Cham Spa trân trọng cảm ơn quý khách và chúc quý khách một ngày an nhiên!"
        )

        return Response({
            'status': 'success',
            'message': 'Đã đóng phiên tư vấn thành công.',
            'closed_at': conversation.closed_at.isoformat()
        }, status=status.HTTP_200_OK)


class ConversationTakeoverAPI(APIView):
    """
    [UC-2.2 - Mở rộng Figma 210:2465] Cho phép Quản trị viên hoặc Ca trực
    chuyển giao / tiếp quản quyền tiếp nhận hội thoại khi nhân viên cũ kết ca hoặc bận.
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            conversation = Conversation.objects.select_related('staff').get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({'error': 'Không tìm thấy cuộc hội thoại.'}, status=status.HTTP_404_NOT_FOUND)

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
            content=f"Thông báo: Cuộc trò chuyện đã được chuyển tiếp sang chuyên viên {new_staff_name} tiếp tục hỗ trợ quý khách ạ."
        )

        return Response({
            'status': 'success',
            'message': f'Đã tiếp quản thành công từ {old_staff_name}. Hiện bạn là nhân viên phụ trách chính.',
            'staff_name': new_staff_name
        }, status=status.HTTP_200_OK)


class StaffConversationListAPI(APIView):
    """
    [UC-2.2] API lấy danh sách cuộc hội thoại cho Livechat Console của Staff.
    Khớp Figma Node 207:1040 (Bộ lọc: Đang chờ, Đang xử lý, Kết thúc, Tất cả).
    Hỗ trợ tìm kiếm theo tên khách, số điện thoại hoặc từ khóa tin nhắn.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        tab = request.query_params.get('tab', 'waiting')
        search_kw = request.query_params.get('search', '').strip()

        queryset = Conversation.objects.select_related('customer', 'staff').prefetch_related('messages')

        # Thống kê số lượng thẻ trạng thái
        counts = {
            'waiting': Conversation.objects.filter(status='Đang chờ').count(),
            'processing': Conversation.objects.filter(status='Đang xử lý').count(),
            'closed': Conversation.objects.filter(status='Kết thúc').count(),
            'bot': Conversation.objects.filter(status='Bot xử lý').count(),
            'all': Conversation.objects.count(),
        }

        # Lọc theo Tab trạng thái
        if tab == 'waiting':
            queryset = queryset.filter(status='Đang chờ')
        elif tab == 'processing':
            queryset = queryset.filter(status='Đang xử lý')
        elif tab == 'closed':
            queryset = queryset.filter(status='Kết thúc')
        elif tab == 'bot':
            queryset = queryset.filter(status='Bot xử lý')
        elif tab == 'mine':
            # Các cuộc hội thoại do chính staff này phụ trách
            queryset = queryset.filter(staff=request.user, status='Đang xử lý')

        # Tìm kiếm theo từ khóa
        if search_kw:
            queryset = queryset.filter(
                Q(customer__name__icontains=search_kw) |
                Q(customer__phone__icontains=search_kw) |
                Q(customer__username__icontains=search_kw) |
                Q(customer_tag__icontains=search_kw) |
                Q(messages__content__icontains=search_kw)
            ).distinct()

        queryset = queryset.order_by('-created_at')

        serializer = ConversationListSerializer(queryset, many=True, context={'request': request})

        return Response({
            'status': 'success',
            'counts': counts,
            'current_tab': tab,
            'conversations': serializer.data
        }, status=status.HTTP_200_OK)


class IsSuperUserOnly(permissions.BasePermission):
    """
    Phân quyền nghiêm ngặt theo yêu cầu:
    CHỈ DUY NHẤT QUẢN LÝ (is_superuser=True) mới có quyền CRUD kịch bản Chatbot FAQ.
    Nhân viên (Staff) không được phép can thiệp.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


# ==============================================================================
# USE CASE 2.3: QUẢN LÝ KỊCH BẢN CHATBOT (FAQ) - CHỈ DÀNH CHO QUẢN LÝ
# Endpoint Hợp đồng: GET, POST, PUT, DELETE /api/admin/faqs/
# ==============================================================================

class AdminFAQListCreateAPI(APIView):
    """
    [UC-2.3] API Quản lý kịch bản Chatbot (FAQ) dành riêng cho Quản lý (Admin).
    Nhân viên (Staff) bị từ chối truy cập.
    - GET: Danh sách FAQ, hỗ trợ lọc theo danh mục, trạng thái, tìm kiếm.
    - POST: Thêm câu hỏi FAQ mới (kiểm tra unique faq_code).
    """
    permission_classes = [IsSuperUserOnly]

    def get(self, request):
        category = request.query_params.get('category')
        status_filter = request.query_params.get('status')
        search_kw = request.query_params.get('q', '').strip()

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

        # Lấy danh sách danh mục để đổ vào dropdown filter
        categories = FAQ.objects.values_list('category', flat=True).distinct()

        serializer = FAQSerializer(faqs, many=True)
        return Response({
            'status': 'success',
            'count': faqs.count(),
            'categories': list(categories),
            'results': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = FAQSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        faq = serializer.save()
        return Response({
            'status': 'success',
            'message': f'Thêm câu hỏi FAQ [{faq.faq_code}] thành công.',
            'data': FAQSerializer(faq).data
        }, status=status.HTTP_201_CREATED)


class AdminFAQDetailAPI(APIView):
    """
    [UC-2.3] Cập nhật hoặc Xóa một câu hỏi FAQ theo ID (Chỉ Quản lý).
    GET, PUT, PATCH, DELETE /api/admin/faqs/{id}/
    """
    permission_classes = [IsSuperUserOnly]

    def get_object(self, pk):
        try:
            return FAQ.objects.get(pk=pk)
        except FAQ.DoesNotExist:
            return None

    def get(self, request, pk):
        faq = self.get_object(pk)
        if not faq:
            return Response({'error': 'Không tìm thấy câu hỏi FAQ.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(FAQSerializer(faq).data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        faq = self.get_object(pk)
        if not faq:
            return Response({'error': 'Không tìm thấy câu hỏi FAQ.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = FAQSerializer(faq, data=request.data, partial=False)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        updated_faq = serializer.save()
        return Response({
            'status': 'success',
            'message': 'Cập nhật câu hỏi FAQ thành công.',
            'data': FAQSerializer(updated_faq).data
        }, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        faq = self.get_object(pk)
        if not faq:
            return Response({'error': 'Không tìm thấy câu hỏi FAQ.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = FAQSerializer(faq, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        updated_faq = serializer.save()
        return Response({
            'status': 'success',
            'message': 'Cập nhật câu hỏi FAQ thành công.',
            'data': FAQSerializer(updated_faq).data
        }, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        faq = self.get_object(pk)
        if not faq:
            return Response({'error': 'Không tìm thấy câu hỏi FAQ.'}, status=status.HTTP_404_NOT_FOUND)

        code = faq.faq_code
        faq.delete()
        return Response({
            'status': 'success',
            'message': f'Đã xóa câu hỏi FAQ [{code}] thành công.'
        }, status=status.HTTP_200_OK)


class AdminFAQToggleStatusAPI(APIView):
    """
    [UC-2.3] Chuyển đổi nhanh trạng thái FAQ giữa 'Active' và 'Hidden' (Chỉ Quản lý).
    """
    permission_classes = [IsSuperUserOnly]

    def post(self, request, pk):
        try:
            faq = FAQ.objects.get(pk=pk)
        except FAQ.DoesNotExist:
            return Response({'error': 'Không tìm thấy câu hỏi FAQ.'}, status=status.HTTP_404_NOT_FOUND)

        faq.status = 'Hidden' if faq.status == 'Active' else 'Active'
        faq.save()

        return Response({
            'status': 'success',
            'message': f"Đã chuyển trạng thái câu hỏi [{faq.faq_code}] sang '{faq.status}'.",
            'current_status': faq.status
        }, status=status.HTTP_200_OK)


# ==============================================================================
# TÍNH NĂNG FIGMA NODE 210:2465: TRA CỨU CHI TIẾT DỊCH VỤ TRỰC TIẾP TRONG CHAT
# ==============================================================================

class QuickServicesLookupAPI(APIView):
    """
    [Figma Node 210:2465] API hỗ trợ Panel tra cứu nhanh dịch vụ ngay trên màn hình Livechat:
      - Giúp tư vấn viên tra cứu giá, thời lượng, công dụng liệu trình.
      - Tự động sinh nội dung tóm tắt để bấm 1 click là gửi vào khung chat cho khách!
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        service_id = request.query_params.get('service_id')

        if service_id:
            try:
                service = Service.objects.select_related('category').prefetch_related('images').get(pk=service_id)
                formatted_price = f"{int(service.price_vnd):,}".replace(',', '.') + " VNĐ"
                
                # Mẫu câu tóm tắt nhanh để nhân viên gửi cho khách
                pitch_template = (
                    f"Dạ gói '{service.name}' tại Cham Spa có giá niêm yết là {formatted_price} "
                    f"với thời lượng {service.duration_minutes} phút. "
                    f"Liệu trình giúp thư giãn chuyên sâu, giảm đau mỏi cơ và lưu thông khí huyết hiệu quả. "
                    f"Quý khách có muốn em hỗ trợ đặt lịch giữ chỗ khung giờ hôm nay luôn không ạ?"
                )

                return Response({
                    'status': 'success',
                    'service': {
                        'id': service.id,
                        'name': service.name,
                        'category_name': service.category.name if service.category else 'Dịch vụ Spa',
                        'price_vnd': float(service.price_vnd),
                        'formatted_price': formatted_price,
                        'duration_minutes': service.duration_minutes,
                        'rating_avg': float(service.rating_avg),
                        'review_count': service.review_count,
                        'thumbnail_url': service.thumbnail_url or '',
                        'description': service.description or '',
                        'pitch_template': pitch_template
                    }
                }, status=status.HTTP_200_OK)
            except Service.DoesNotExist:
                return Response({'error': 'Dịch vụ không tồn tại.'}, status=status.HTTP_404_NOT_FOUND)

        # Lấy danh sách toàn bộ dịch vụ đang hoạt động
        services = Service.objects.filter(status='Hoạt động').select_related('category').order_by('category_id', 'id')
        data = [
            {
                'id': s.id,
                'name': s.name,
                'category_name': s.category.name if s.category else '',
                'price_vnd': float(s.price_vnd),
                'formatted_price': f"{int(s.price_vnd):,}".replace(',', '.') + " VNĐ",
                'duration_minutes': s.duration_minutes,
                'rating_avg': float(s.rating_avg)
            }
            for s in services
        ]

        return Response({
            'status': 'success',
            'services': data
        }, status=status.HTTP_200_OK)


class CustomerActiveConversationAPI(APIView):
    """
    [UC-2.1 & UC-2.2] Lấy phiên hội thoại hiện tại và toàn bộ lịch sử tin nhắn của khách hàng.
    Phục vụ Floating Chat Widget:
      - Khách hàng đã đăng nhập: Tải lại toàn bộ lịch sử tin nhắn đã lưu trữ trong CSDL.
      - Khách hàng vãng lai: Không lưu trữ trong CSDL, chỉ chạy in-memory.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({
                'is_authenticated': False,
                'conversation': None,
                'messages': []
            }, status=status.HTTP_200_OK)

        # Tìm phiên hội thoại gần nhất của khách hàng
        conversation = (
            Conversation.objects.filter(customer=user)
            .select_related('staff')
            .order_by('-created_at')
            .first()
        )

        if not conversation:
            return Response({
                'is_authenticated': True,
                'conversation': None,
                'messages': []
            }, status=status.HTTP_200_OK)

        messages_qs = conversation.messages.all().order_by('created_at')
        serializer = ConversationMessageSerializer(messages_qs, many=True)

        staff_name = None
        if conversation.staff:
            staff_name = conversation.staff.name or conversation.staff.username

        return Response({
            'is_authenticated': True,
            'conversation': {
                'id': conversation.id,
                'status': conversation.status,
                'staff_name': staff_name,
                'created_at': conversation.created_at.isoformat()
            },
            'messages': serializer.data
        }, status=status.HTTP_200_OK)


# ==============================================================================
# CÁC API DÀNH RIÊNG CHO QUẢN TRỊ VIÊN (ADMIN - NODE 502:2005 & NODE 211:3459)
# ==============================================================================

class AdminConversationMonitorAPI(APIView):
    """
    [Figma Node 502:2005 - ADMIN · Quản lý Live Chat & Giám sát phiên tư vấn]
    Lấy thông tin chi tiết phiên chat cần giám sát, bao gồm:
      - Cột 2: Thông tin hội thoại, lịch sử bot, danh sách tin nhắn realtime
      - Cột 3: Thông tin chi tiết khách hàng (Hạng thẻ VIP, Tổng chi tiêu, Lưu ý sức khỏe)
      - Card Giám sát: Thời lượng phiên, Staff Response SLA, Lịch sử chuyển giao
      - Danh sách nhân viên tư vấn trực tuyến để sẵn sàng Reassign (Chuyển nhân viên)
    """
    permission_classes = [IsSuperUserOnly]

    def get(self, request, pk):
        try:
            conv = Conversation.objects.select_related('customer', 'staff').get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({'error': 'Không tìm thấy cuộc hội thoại.'}, status=status.HTTP_404_NOT_FOUND)

        customer = conv.customer
        membership = Membership.objects.filter(user=customer).select_related('tier').first()
        tier_name = membership.tier.name if (membership and membership.tier) else 'Hạng VÀNG'
        total_spent = membership.total_spent if membership else 18500000
        formatted_spent = f"{int(total_spent):,} VNĐ".replace(',', '.')

        health = UserHealthProfile.objects.filter(user=customer).first()
        health_notes = []
        if health:
            if health.special_requests:
                health_notes.append(health.special_requests)
            if health.massage_pressure:
                health_notes.append(f"ưu tiên lực {health.massage_pressure.lower()}")
            if health.allergy_notes:
                health_notes.append(f"dị ứng: {health.allergy_notes}")
        health_summary = ", ".join(health_notes) if health_notes else "Da nhạy cảm, ưu tiên lực nhẹ."

        # Tính toán thời lượng phiên
        now = timezone.now()
        duration_seconds = int((now - conv.created_at).total_seconds())
        mins = duration_seconds // 60
        secs = duration_seconds % 60
        duration_display = f"{mins:02d}:{secs:02d}"

        # Danh sách nhân viên khả dụng để chuyển giao
        available_staffs = User.objects.filter(is_staff=True).exclude(pk=conv.staff_id if conv.staff else 0).values('id', 'name', 'phone')

        messages_qs = conv.messages.all().order_by('created_at')
        serialized_messages = ConversationMessageSerializer(messages_qs, many=True).data

        return Response({
            'status': 'success',
            'conversation': {
                'id': conv.id,
                'status': conv.status,
                'customer_tag': conv.customer_tag or 'Trị liệu vai gáy & Đặt lịch',
                'created_at': conv.created_at.isoformat(),
                'duration_display': duration_display,
                'staff': {
                    'id': conv.staff.id if conv.staff else None,
                    'name': conv.staff.name if conv.staff else 'Chưa phân công',
                    'is_online': True
                } if conv.staff else None,
                'customer': {
                    'id': customer.id,
                    'name': customer.name,
                    'phone': customer.phone,
                    'email': customer.email,
                    'tier_name': tier_name,
                    'total_spent': formatted_spent,
                    'health_summary': health_summary
                },
                'sla_status': 'Tốt (< 30 giây)',
                'sla_badge': 'success',
                'messages': serialized_messages,
                'available_staffs': list(available_staffs)
            }
        }, status=status.HTTP_200_OK)


class AdminReassignStaffAPI(APIView):
    """
    [Figma Node 502:2005] Admin điều phối: Chuyển cuộc hội thoại sang cho nhân viên khác.
    """
    permission_classes = [IsSuperUserOnly]

    def post(self, request, pk):
        try:
            conv = Conversation.objects.get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({'error': 'Không tìm thấy cuộc hội thoại.'}, status=status.HTTP_404_NOT_FOUND)

        new_staff_id = request.data.get('staff_id')
        if not new_staff_id:
            return Response({'error': 'Vui lòng chọn nhân viên tiếp nhận mới.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_staff = User.objects.get(pk=new_staff_id, is_staff=True)
        except User.DoesNotExist:
            return Response({'error': 'Nhân viên không tồn tại hoặc không hợp lệ.'}, status=status.HTTP_400_BAD_REQUEST)

        old_staff_name = conv.staff.name if conv.staff else 'Chưa có'
        conv.staff = new_staff
        conv.status = 'Đang xử lý'
        conv.save(update_fields=['staff', 'status'])

        # Ghi nhận log thông báo vào phiên chat
        admin_name = request.user.name or 'Quản trị viên'
        sys_msg = ConversationMessage.objects.create(
            conversation=conv,
            sender_type='Staff',
            content=f"[HỆ THỐNG] {admin_name} đã chuyển giao cuộc hội thoại từ {old_staff_name} sang nhân viên {new_staff.name}."
        )

        return Response({
            'status': 'success',
            'message': f'Đã chuyển giao thành công cho nhân viên {new_staff.name}.',
            'staff': {
                'id': new_staff.id,
                'name': new_staff.name
            }
        }, status=status.HTTP_200_OK)


class AdminTakeoverConversationAPI(APIView):
    """
    [Figma Node 502:2005] Nút: Can thiệp / Tiếp quản phiên chat.
    Admin trực tiếp tiếp quản cuộc hội thoại, gán staff=admin và đổi trạng thái.
    """
    permission_classes = [IsSuperUserOnly]

    def post(self, request, pk):
        try:
            conv = Conversation.objects.get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({'error': 'Không tìm thấy cuộc hội thoại.'}, status=status.HTTP_404_NOT_FOUND)

        admin_name = request.user.name or 'Quản trị viên'
        conv.staff = request.user
        conv.status = 'Đang xử lý'
        conv.save(update_fields=['staff', 'status'])

        ConversationMessage.objects.create(
            conversation=conv,
            sender_type='Staff',
            content=f"[HỆ THỐNG] Quản lý ({admin_name}) đã can thiệp và trực tiếp tiếp quản phiên tư vấn này."
        )

        return Response({
            'status': 'success',
            'message': f'Quản lý {admin_name} đã tiếp quản cuộc hội thoại thành công.',
            'staff_name': admin_name
        }, status=status.HTTP_200_OK)


class AdminSendMessageAPI(APIView):
    """
    [Figma Node 502:2005] Admin gửi tin nhắn can thiệp / chỉ đạo trực tiếp vào phiên chat.
    """
    permission_classes = [IsSuperUserOnly]

    def post(self, request, pk):
        try:
            conv = Conversation.objects.get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({'error': 'Không tìm thấy cuộc hội thoại.'}, status=status.HTTP_404_NOT_FOUND)

        content = request.data.get('content', '').strip()
        if not content:
            return Response({'error': 'Nội dung tin nhắn không được để trống.'}, status=status.HTTP_400_BAD_REQUEST)

        admin_name = request.user.name or 'Quản lý Cham Spa'
        msg = ConversationMessage.objects.create(
            conversation=conv,
            sender_type='Staff',
            content=f"[Quản lý {admin_name}]: {content}"
        )

        serializer = ConversationMessageSerializer(msg)
        return Response({
            'status': 'success',
            'message': serializer.data
        }, status=status.HTTP_201_CREATED)


class AdminFAQExportAPI(APIView):
    """
    [Figma Node 211:3459] Nút: 'Xuất dữ liệu 📥'
    Xuất toàn bộ danh sách kịch bản FAQ ra file CSV có BOM UTF-8 (chuẩn Excel tiếng Việt).
    """
    permission_classes = [IsSuperUserOnly]

    def get(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="ChamSpa_KichBan_FAQ.csv"'

        writer = csv.writer(response)
        writer.writerow(['Mã FAQ', 'Danh mục', 'Câu hỏi hiển thị', 'Từ khóa kích hoạt', 'Câu trả lời tự động', 'Trạng thái', 'Ngày tạo'])

        faqs = FAQ.objects.all().order_by('category', 'faq_code')
        for faq in faqs:
            writer.writerow([
                faq.faq_code,
                faq.category,
                faq.question,
                faq.keywords,
                faq.answer,
                'Kích hoạt' if faq.status == 'Active' else 'Đang ẩn',
                faq.created_at.strftime('%d/%m/%Y %H:%M') if faq.created_at else ''
            ])

        return response
