"""
================================================================================
SERIALIZERS CHO PHÂN HỆ QUẢN LÝ BOXCHAT TƯ VẤN (MOD-02) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc
Mục đích:
  - Chuyển đổi dữ liệu giữa Model Django và định dạng JSON phục vụ RESTful API.
  - Kiểm tra (validate) dữ liệu đầu vào theo đúng Hợp đồng API và Quy tắc nghiệp vụ.
  - Phục vụ 3 Use Cases chính:
      + UC-2.1: Trò chuyện với Chatbot tự động (FAQ thuần TEXT)
      + UC-2.2: Trò chuyện trực tiếp (Kết nối nhân viên tư vấn & Phân quyền)
      + UC-2.3: Quản lý kịch bản Chatbot (FAQ)
================================================================================
"""

from rest_framework import serializers
from django.utils import timezone
from core.models import FAQ, Conversation, ConversationMessage, User, Service


# ==============================================================================
# 1. SERIALIZER QUẢN LÝ KỊCH BẢN CHATBOT (FAQ) - UC-2.3
# ==============================================================================

class FAQSerializer(serializers.ModelSerializer):
    """
    Serializer phục vụ CRUD kịch bản câu hỏi thường gặp FAQ (UC-2.3).
    Quy tắc nghiệp vụ chốt:
      - Mã faq_code là duy nhất trong hệ thống.
      - Câu trả lời answer thuần túy là văn bản (TEXT), không kèm ảnh hay nút bấm phức tạp.
      - Hỗ trợ trạng thái Active (Đang dùng) và Hidden (Ẩn tạm thời).
    """
    formatted_created_at = serializers.SerializerMethodField(read_only=True)
    formatted_updated_at = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = FAQ
        fields = [
            'id',
            'faq_code',
            'category',
            'question',
            'keywords',
            'answer',
            'status',
            'created_at',
            'updated_at',
            'formatted_created_at',
            'formatted_updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_formatted_created_at(self, obj):
        if obj.created_at:
            return obj.created_at.strftime('%d/%m/%Y %H:%M')
        return ""

    def get_formatted_updated_at(self, obj):
        if obj.updated_at:
            return obj.updated_at.strftime('%d/%m/%Y %H:%M')
        return ""

    def validate_faq_code(self, value):
        """Kiểm tra tính duy nhất của mã câu hỏi FAQ"""
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("Mã câu hỏi FAQ không được để trống.")
        
        # Nếu là cập nhật, bỏ qua kiểm tra chính bản ghi đang sửa
        existing = FAQ.objects.filter(faq_code=value)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        
        if existing.exists():
            raise serializers.ValidationError("Mã câu hỏi đã tồn tại, vui lòng nhập mã khác.")
        return value

    def validate_answer(self, value):
        """Kiểm tra nội dung câu trả lời TEXT"""
        if not value or not value.strip():
            raise serializers.ValidationError("Nội dung câu trả lời không được để trống.")
        return value.strip()


# ==============================================================================
# 2. SERIALIZERS TIN NHẮN HỘI THOẠI - UC-2.1 & UC-2.2
# ==============================================================================

class ConversationMessageSerializer(serializers.ModelSerializer):
    """
    Serializer hiển thị chi tiết từng tin nhắn trong cuộc hội thoại (UC-2.2).
    Quy tắc nghiệp vụ chốt:
      - Khi nhân viên chat, hiển thị rõ TÊN NHÂN VIÊN GỬI (sender_name)
        theo đúng thỏa thuận chốt tài liệu và thiết kế Figma.
      - Định dạng thời gian rõ ràng (ví dụ: '14:05', '07/11 14:05').
    """
    sender_name = serializers.SerializerMethodField()
    formatted_time = serializers.SerializerMethodField()

    class Meta:
        model = ConversationMessage
        fields = [
            'id',
            'conversation',
            'sender_type',
            'sender_name',
            'message_type',
            'content',
            'attachment_url',
            'attachment_name',
            'attachment_size',
            'created_at',
            'formatted_time',
        ]
        read_only_fields = ['id', 'created_at']

    def get_sender_name(self, obj):
        """
        Lấy tên người gửi tương ứng:
          - Staff: Tên nhân viên phụ trách phiên chat hoặc staff gửi tin nhắn
          - Customer: Tên khách hàng (hoặc 'Khách hàng')
          - Bot: 'Trợ lý ảo Cham Spa'
        """
        if obj.sender_type == 'Staff':
            if obj.conversation.staff:
                return obj.conversation.staff.name or obj.conversation.staff.username
            return "Nhân viên tư vấn"
        elif obj.sender_type == 'Customer':
            if obj.conversation.customer:
                return obj.conversation.customer.name or "Khách hàng"
            return "Khách hàng"
        elif obj.sender_type == 'Bot':
            return "Trợ lý ảo Cham Spa"
        return "Hệ thống"

    def get_formatted_time(self, obj):
        if obj.created_at:
            local_dt = timezone.localtime(obj.created_at)
            return local_dt.strftime('%H:%M - %d/%m')
        return ""


class SendMessageInputSerializer(serializers.Serializer):
    """
    Serializer tiếp nhận dữ liệu khi gửi tin nhắn mới (POST /api/chat/conversations/{id}/messages/)
    """
    content = serializers.CharField(required=True, allow_blank=False, max_length=5000)
    message_type = serializers.ChoiceField(choices=['TEXT', 'IMAGE', 'FILE'], default='TEXT', required=False)
    attachment_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    attachment_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    attachment_size = serializers.CharField(required=False, allow_blank=True, allow_null=True)


# ==============================================================================
# 3. SERIALIZERS DANH SÁCH & CHI TIẾT CUỘC HỘI THOẠI CHO STAFF CONSOLE - UC-2.2
# ==============================================================================

class ConversationListSerializer(serializers.ModelSerializer):
    """
    Serializer danh sách cuộc hội thoại cho màn hình Livechat của Nhân viên & Quản lý.
    Khớp thiết kế Figma Node 207:1040 (Danh sách hội thoại phân loại theo trạng thái).
    Cung cấp thông tin khách hàng, thẻ phân loại, tin nhắn gần nhất và trạng thái phân công.
    """
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    customer_email = serializers.SerializerMethodField()
    customer_avatar = serializers.SerializerMethodField()
    membership_tier = serializers.SerializerMethodField()

    staff_name = serializers.SerializerMethodField()
    is_assigned_to_me = serializers.SerializerMethodField()
    is_assigned_to_other = serializers.SerializerMethodField()

    last_message = serializers.SerializerMethodField()
    last_message_time = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id',
            'status',
            'customer_tag',
            'customer_name',
            'customer_phone',
            'customer_email',
            'customer_avatar',
            'membership_tier',
            'staff_id',
            'staff_name',
            'is_assigned_to_me',
            'is_assigned_to_other',
            'last_message',
            'last_message_time',
            'unread_count',
            'created_at',
            'closed_at',
        ]

    def get_customer_name(self, obj):
        if obj.customer:
            return obj.customer.name or obj.customer.username
        return "Khách vãng lai"

    def get_customer_phone(self, obj):
        if obj.customer:
            return obj.customer.phone or ""
        return ""

    def get_customer_email(self, obj):
        if obj.customer:
            return obj.customer.email or ""
        return ""

    def get_customer_avatar(self, obj):
        if obj.customer and hasattr(obj.customer, 'profile') and obj.customer.profile.avatar:
            return obj.customer.profile.avatar
        return None

    def get_membership_tier(self, obj):
        """Lấy tên hạng hội viên nếu khách đã đăng ký thẻ"""
        if obj.customer and hasattr(obj.customer, 'membership') and obj.customer.membership.tier:
            return obj.customer.membership.tier.name
        return "Khách hàng"

    def get_staff_name(self, obj):
        if obj.staff:
            return obj.staff.name or obj.staff.username
        return None

    def get_is_assigned_to_me(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated and obj.staff:
            return obj.staff_id == request.user.id
        return False

    def get_is_assigned_to_other(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated and obj.staff:
            return obj.staff_id != request.user.id
        return False

    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            prefix = ""
            if last_msg.sender_type == 'Staff':
                prefix = "Bạn: "
            elif last_msg.sender_type == 'Bot':
                prefix = "Bot: "
            return f"{prefix}{last_msg.content or '[Tệp đính kèm]'}"
        return "Chưa có tin nhắn"

    def get_last_message_time(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg and last_msg.created_at:
            local_dt = timezone.localtime(last_msg.created_at)
            return local_dt.strftime('%H:%M')
        return ""

    def get_unread_count(self, obj):
        # Đếm số tin nhắn của khách hàng gần nhất
        return obj.messages.filter(sender_type='Customer').count()


class ConversationDetailSerializer(serializers.ModelSerializer):
    """
    Serializer chi tiết phiên hội thoại kèm lịch sử tin nhắn đầy đủ (UC-2.2).
    Hỗ trợ hiển thị hồ sơ sức khỏe 1-1 của khách hàng (UC-8.2) để tư vấn viên tham khảo.
    """
    customer_info = serializers.SerializerMethodField()
    staff_info = serializers.SerializerMethodField()
    messages = ConversationMessageSerializer(many=True, read_only=True)
    health_profile = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id',
            'status',
            'customer_tag',
            'bot_collected_data',
            'customer_info',
            'staff_info',
            'health_profile',
            'messages',
            'created_at',
            'closed_at',
        ]

    def get_customer_info(self, obj):
        if not obj.customer:
            return {
                'id': None,
                'name': 'Khách vãng lai',
                'phone': '',
                'email': '',
                'tier': 'Khách vãng lai',
                'avatar': None
            }
        
        tier_name = "Thành viên"
        if hasattr(obj.customer, 'membership') and obj.customer.membership.tier:
            tier_name = obj.customer.membership.tier.name

        avatar = None
        if hasattr(obj.customer, 'profile') and obj.customer.profile.avatar:
            avatar = obj.customer.profile.avatar

        return {
            'id': obj.customer.id,
            'name': obj.customer.name or obj.customer.username,
            'phone': obj.customer.phone or '',
            'email': obj.customer.email or '',
            'tier': tier_name,
            'avatar': avatar
        }

    def get_staff_info(self, obj):
        if not obj.staff:
            return None
        return {
            'id': obj.staff.id,
            'name': obj.staff.name or obj.staff.username,
            'email': obj.staff.email or '',
            'role': 'Quản lý' if obj.staff.is_superuser else 'Nhân viên CSKH'
        }

    def get_health_profile(self, obj):
        """
        Lấy thông tin thể trạng hồ sơ sức khỏe 1-1 (UC-8.2) nếu có
        giúp tư vấn viên nắm bắt nhanh nhu cầu trị liệu của khách hàng.
        """
        if obj.customer and hasattr(obj.customer, 'health_profile'):
            hp = obj.customer.health_profile
            return {
                'health_code': hp.health_code,
                'height_cm': float(hp.height_cm) if hp.height_cm else None,
                'weight_kg': float(hp.weight_kg) if hp.weight_kg else None,
                'blood_pressure': hp.blood_pressure,
                'focus_areas': hp.focus_areas or [],
                'massage_pressure': hp.massage_pressure,
                'pain_level': hp.pain_level,
                'health_conditions': hp.health_conditions or [],
                'allergy_notes': hp.allergy_notes,
                'recovery_goals': hp.recovery_goals or []
            }
        return None


# ==============================================================================
# 4. SERIALIZER PHẢN HỒI TỰ ĐỘNG CHATBOT (UC-2.1)
# ==============================================================================

class BotReplyInputSerializer(serializers.Serializer):
    """
    Serializer nhận request từ client gửi tới Chatbot tự động:
    POST /api/chat/bot-reply/
    Body:
      {
        "message": "Cho mình xin bảng giá massage body",
        "conversation_id": null
      }
    """
    message = serializers.CharField(required=True, allow_blank=False, max_length=1000)
    conversation_id = serializers.IntegerField(required=False, allow_null=True)
