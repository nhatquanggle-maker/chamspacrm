"""
================================================================================
UNIT TESTS CHO PHÂN HỆ QUẢN LÝ BOXCHAT TƯ VẤN (MOD-02) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc
Kiểm thử toàn diện 3 Use Cases và các ràng buộc nghiệp vụ:
  - UC-2.1: Chatbot tự động trả lời (Vãng lai in-memory vs Đăng nhập lưu DB)
  - UC-2.2: Trò chuyện trực tiếp & Phân quyền tiếp nhận (Figma Node 210:2465)
  - UC-2.3: Quản lý kịch bản Chatbot FAQ (CRUD, unique faq_code)
  - Tiện ích tra cứu dịch vụ & Mẫu câu tư vấn (Figma Node 210:2465)
================================================================================
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from core.models import User, FAQ, Conversation, ConversationMessage, Service, Category


class ChatboxModuleTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Tạo người dùng test
        self.customer_user = User.objects.create_user(
            username='0909111222',
            phone='0909111222',
            email='customer.test@gmail.com',
            name='Nguyễn Khách Hàng',
            is_staff=False,
            is_superuser=False
        )

        self.staff_user_1 = User.objects.create_user(
            username='0905111333',
            phone='0905111333',
            email='staff1@chamspa.vn',
            name='Thanh Thảo',
            is_staff=True,
            is_superuser=False
        )

        self.staff_user_2 = User.objects.create_user(
            username='0905222444',
            phone='0905222444',
            email='staff2@chamspa.vn',
            name='Thảo Ngọc',
            is_staff=True,
            is_superuser=False
        )

        # Quản trị viên (Admin) duy nhất có quyền quản lý FAQ kịch bản bot
        self.admin_user = User.objects.create_superuser(
            username='admin_chamspa',
            phone='0905999888',
            email='admin@chamspa.vn',
            name='Quản Lý Cham Spa',
            password='adminpassword123'
        )

        # Tạo danh mục và dịch vụ test
        self.category = Category.objects.create(
            name='Massage Body',
            slug='massage-body-test',
            status='Active'
        )
        self.service = Service.objects.create(
            category=self.category,
            name='Massage Body Đá Nóng 90p',
            slug='massage-body-da-nong-90p-test',
            price_vnd=550000,
            duration_minutes=90,
            status='Hoạt động'
        )

        # Tạo FAQ mẫu
        self.faq_price = FAQ.objects.create(
            faq_code='FAQ-TEST-GIA',
            category='Bảng giá',
            question='Bảng giá dịch vụ massage tại Cham Spa?',
            keywords='giá, bao nhiêu tiền, chi phí, bảng giá',
            answer='Dạ các gói massage tại Cham Spa có giá từ 350.000đ đến 650.000đ ạ.',
            status='Active'
        )

    # --------------------------------------------------------------------------
    # 1. TEST UC-2.1: CHATBOT TỰ ĐỘNG (FAQ THUẦN TEXT)
    # --------------------------------------------------------------------------
    def test_uc21_anonymous_user_in_memory_only(self):
        """Khách vãng lai chat với bot -> Không được lưu vào bảng Conversation/ConversationMessage"""
        conv_count_before = Conversation.objects.count()
        msg_count_before = ConversationMessage.objects.count()

        response = self.client.post('/chatbox/api/chat/bot-reply/', {
            'message': 'Cho mình hỏi giá dịch vụ thế nào ạ?'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertIn('350.000đ', response.data['reply'])
        self.assertIsNone(response.data['conversation_id'])

        # Kiểm tra CSDL không tăng bản ghi
        self.assertEqual(Conversation.objects.count(), conv_count_before)
        self.assertEqual(ConversationMessage.objects.count(), msg_count_before)

    def test_uc21_authenticated_user_saves_to_db(self):
        """Khách hàng đã đăng nhập chat với bot -> Tự động lưu vào Conversation và Message"""
        self.client.force_authenticate(user=self.customer_user)

        response = self.client.post('/chatbox/api/chat/bot-reply/', {
            'message': 'Cho mình hỏi bảng giá massage đá nóng?'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['conversation_id'])

        conv_id = response.data['conversation_id']
        conv = Conversation.objects.get(pk=conv_id)
        self.assertEqual(conv.customer, self.customer_user)
        self.assertEqual(conv.status, 'Bot xử lý')
        self.assertEqual(conv.messages.count(), 2)  # 1 tin khách, 1 tin bot

    # --------------------------------------------------------------------------
    # 2. TEST UC-2.2: KẾT NỐI NHÂN VIÊN TƯ VẤN & BẢO VỆ PHÂN QUYỀN TIẾP NHẬN
    # --------------------------------------------------------------------------
    def test_uc22_transfer_to_staff_requires_login(self):
        """Khách vãng lai bấm 'Gặp nhân viên tư vấn' -> Bị chặn 401 yêu cầu đăng nhập"""
        response = self.client.post('/chatbox/api/conversations/transfer/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['status'], 'require_login')

    def test_uc22_transfer_to_staff_success(self):
        """Khách hàng đăng nhập bấm 'Gặp nhân viên tư vấn' -> Status đổi sang 'Đang chờ'"""
        self.client.force_authenticate(user=self.customer_user)

        response = self.client.post('/chatbox/api/conversations/transfer/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['conversation_status'], 'Đang chờ')

        conv = Conversation.objects.get(pk=response.data['conversation_id'])
        self.assertEqual(conv.status, 'Đang chờ')

    def test_uc22_staff_accept_conversation(self):
        """Nhân viên bấm 'Tiếp nhận' -> Status sang 'Đang xử lý', staff được gán"""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            status='Đang chờ'
        )

        self.client.force_authenticate(user=self.staff_user_1)
        response = self.client.post(f'/chatbox/api/conversations/{conv.id}/accept/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conv.refresh_from_db()
        self.assertEqual(conv.status, 'Đang xử lý')
        self.assertEqual(conv.staff, self.staff_user_1)

    def test_uc22_conflict_when_other_staff_already_assigned(self):
        """
        RÀNG BUỘC FIGMA NODE 210:2465:
        Khi cuộc hội thoại đã được Nhân viên 1 tiếp nhận và đang xử lý,
        Nhân viên 2 cố tình gửi tin nhắn -> Hệ thống BẢO VỆ và CHẶN (HTTP 403 Forbidden).
        """
        conv = Conversation.objects.create(
            customer=self.customer_user,
            staff=self.staff_user_1,
            status='Đang xử lý'
        )

        # Nhân viên 2 (Thảo Ngọc) cố tình gửi tin nhắn vào cuộc hội thoại của Nhân viên 1 (Thanh Thảo)
        self.client.force_authenticate(user=self.staff_user_2)
        response = self.client.post(f'/chatbox/api/conversations/{conv.id}/messages/', {
            'content': 'Em chào anh chị ạ!'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'forbidden_assigned')
        self.assertIn('Thanh Thảo', response.data['error'])

    def test_uc22_assigned_staff_sends_message_with_name(self):
        """Nhân viên phụ trách gửi tin nhắn -> Lưu với sender_type='Staff', hiển thị tên nhân viên"""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            staff=self.staff_user_1,
            status='Đang xử lý'
        )

        self.client.force_authenticate(user=self.staff_user_1)
        response = self.client.post(f'/chatbox/api/conversations/{conv.id}/messages/', {
            'content': 'Dạ em chào anh/chị, em có thể hỗ trợ gì ạ?'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['sender_type'], 'Staff')
        self.assertEqual(response.data['sender_name'], 'Thanh Thảo')

    def test_uc22_close_conversation(self):
        """Nhân viên bấm 'Đóng phiên chat' -> Status chuyển sang 'Kết thúc', lưu closed_at"""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            staff=self.staff_user_1,
            status='Đang xử lý'
        )

        self.client.force_authenticate(user=self.staff_user_1)
        response = self.client.post(f'/chatbox/api/conversations/{conv.id}/close/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conv.refresh_from_db()
        self.assertEqual(conv.status, 'Kết thúc')
        self.assertIsNotNone(conv.closed_at)

    # --------------------------------------------------------------------------
    # 3. TEST UC-2.3: QUẢN LÝ KỊCH BẢN CHATBOT (FAQ) - CHỈ DÀNH CHO QUẢN TRỊ VIÊN
    # --------------------------------------------------------------------------
    def test_uc23_staff_cannot_manage_faqs_forbidden(self):
        """YÊU CẦU NGHIÊM NGẶT: Nhân viên (Staff) không được quản lý FAQ -> Bị chặn 403 Forbidden"""
        self.client.force_authenticate(user=self.staff_user_1)
        res = self.client.get('/chatbox/api/admin/faqs/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res_post = self.client.post('/chatbox/api/admin/faqs/', {
            'faq_code': 'FAQ-ILLEGAL',
            'category': 'Dịch vụ',
            'question': 'Staff cố tình tạo?',
            'keywords': 'test',
            'answer': 'Không được phép',
            'status': 'Active'
        }, format='json')
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

    def test_uc23_create_faq_unique_code(self):
        """Quản lý tạo FAQ mới và bắt lỗi trùng mã faq_code"""
        self.client.force_authenticate(user=self.admin_user)

        # 1. Tạo mới hợp lệ
        res1 = self.client.post('/chatbox/api/admin/faqs/', {
            'faq_code': 'FAQ-MOI-01',
            'category': 'Khuyến mãi',
            'question': 'Cham Spa có ưu đãi sinh nhật không?',
            'keywords': 'sinh nhật, ưu đãi, giảm giá sinh nhật',
            'answer': 'Dạ Cham Spa giảm ngay 20% cho khách hàng trải nghiệm trong tuần sinh nhật ạ!',
            'status': 'Active'
        }, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # 2. Cố tình tạo trùng mã FAQ-MOI-01
        res2 = self.client.post('/chatbox/api/admin/faqs/', {
            'faq_code': 'FAQ-MOI-01',
            'category': 'Khuyến mãi',
            'question': 'Câu hỏi khác nhưng trùng mã?',
            'keywords': 'test',
            'answer': 'Câu trả lời test',
            'status': 'Active'
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('faq_code', res2.data['errors'])

    def test_uc23_toggle_faq_status(self):
        """Quản lý bật/tắt trạng thái Active <-> Hidden"""
        self.client.force_authenticate(user=self.admin_user)

        self.assertEqual(self.faq_price.status, 'Active')
        res = self.client.post(f'/chatbox/api/admin/faqs/{self.faq_price.id}/toggle-status/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['current_status'], 'Hidden')

        self.faq_price.refresh_from_db()
        self.assertEqual(self.faq_price.status, 'Hidden')

    # --------------------------------------------------------------------------
    # 4. TEST TIỆN ÍCH TRA CỨU DỊCH VỤ (FIGMA NODE 210:2465)
    # --------------------------------------------------------------------------
    def test_quick_services_lookup(self):
        """Tra cứu dịch vụ và sinh mẫu câu tư vấn (pitch_template)"""
        self.client.force_authenticate(user=self.staff_user_1)

        res = self.client.get(f'/chatbox/api/services/lookup/?service_id={self.service.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['service']['name'], 'Massage Body Đá Nóng 90p')
        self.assertIn('Massage Body Đá Nóng 90p', res.data['service']['pitch_template'])
        self.assertIn('550.000 VNĐ', res.data['service']['pitch_template'])

    # --------------------------------------------------------------------------
    # 5. TEST LƯU TRỮ LỊCH SỬ CHAT (ĐĂNG NHẬP VS VÃNG LAI)
    # --------------------------------------------------------------------------
    def test_customer_active_conversation_anonymous_returns_none(self):
        """Khách vãng lai gọi lấy lịch sử -> Trả về conversation = null, không lưu DB"""
        res = self.client.get('/chatbox/api/conversations/my-active/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data['is_authenticated'])
        self.assertIsNone(res.data['conversation'])
        self.assertEqual(len(res.data['messages']), 0)

    def test_customer_active_conversation_authenticated_returns_history(self):
        """Khách hàng đã đăng nhập -> Lấy lại toàn bộ lịch sử tin nhắn lưu trữ từ CSDL"""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            status='Bot xử lý'
        )
        ConversationMessage.objects.create(
            conversation=conv,
            sender_type='Customer',
            content='Tin nhắn cũ của khách'
        )
        ConversationMessage.objects.create(
            conversation=conv,
            sender_type='Bot',
            content='Tin nhắn phản hồi cũ của bot'
        )

        self.client.force_authenticate(user=self.customer_user)
        res = self.client.get('/chatbox/api/conversations/my-active/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['is_authenticated'])
        self.assertIsNotNone(res.data['conversation'])
        self.assertEqual(len(res.data['messages']), 2)
        self.assertEqual(res.data['messages'][0]['content'], 'Tin nhắn cũ của khách')

    # --------------------------------------------------------------------------
    # 6. TEST PHÂN QUYỀN HIỂN THỊ CHAT WIDGET TRÊN HOMEPAGE
    # --------------------------------------------------------------------------
    def test_homepage_chat_widget_visibility(self):
        """
        Ràng buộc giao diện:
        - Khách vãng lai và Khách hàng: CÓ Chat Widget (chamChatbotFab).
        - Nhân viên (Staff) và Quản lý (Admin): KHÔNG ĐƯỢC CÓ Chat Widget ngay chỗ homepage.
        """
        # 1. Khách vãng lai truy cập Homepage -> CÓ chat widget
        self.client.logout()
        res_anon = self.client.get('/')
        self.assertEqual(res_anon.status_code, 200)
        self.assertContains(res_anon, 'chamChatbotFab')

        # 2. Khách hàng đã đăng nhập truy cập Homepage -> CÓ chat widget
        self.client.force_login(self.customer_user)
        res_customer = self.client.get('/')
        self.assertEqual(res_customer.status_code, 200)
        self.assertContains(res_customer, 'chamChatbotFab')

        # 3. Nhân viên (Staff) truy cập Homepage -> KHÔNG CÓ chat widget
        self.client.force_login(self.staff_user_1)
        res_staff = self.client.get('/')
        self.assertEqual(res_staff.status_code, 200)
        self.assertNotContains(res_staff, 'chamChatbotFab')

        # 4. Quản trị viên (Admin) truy cập Homepage -> KHÔNG CÓ chat widget
        self.client.force_login(self.admin_user)
        res_admin = self.client.get('/')
        self.assertEqual(res_admin.status_code, 200)
        self.assertNotContains(res_admin, 'chamChatbotFab')
