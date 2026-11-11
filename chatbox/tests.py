"""
================================================================================
UNIT TESTS CHO PHÂN HỆ QUẢN LÝ BOXCHAT TƯ VẤN (MOD-02) - CHAMSPA CRM
================================================================================
"""

from django.test import TestCase, Client
from django.urls import reverse

from core.models import User, FAQ, Conversation, ConversationMessage, Service, Category


class ChatboxModuleTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.customer_user = User.objects.create_user(
            username='0909111222',
            phone='0909111222',
            email='customer.test@gmail.com',
            name='Nguyễn Khách Hàng',
            is_staff=False,
            is_superuser=False,
        )

        self.staff_user_1 = User.objects.create_user(
            username='0905111333',
            phone='0905111333',
            email='staff1@chamspa.vn',
            name='Thanh Thảo',
            is_staff=True,
            is_superuser=False,
        )

        self.staff_user_2 = User.objects.create_user(
            username='0905222444',
            phone='0905222444',
            email='staff2@chamspa.vn',
            name='Thảo Ngọc',
            is_staff=True,
            is_superuser=False,
        )

        self.admin_user = User.objects.create_superuser(
            username='admin_chamspa',
            phone='0905999888',
            email='admin@chamspa.vn',
            name='Quản Lý Cham Spa',
            password='adminpassword123',
        )

        self.category = Category.objects.create(
            name='Massage Body',
            slug='massage-body-test',
            status='Active',
        )
        self.service = Service.objects.create(
            category=self.category,
            name='Massage Body Đá Nóng 90p',
            slug='massage-body-da-nong-90p-test',
            price_vnd=550000,
            duration_minutes=90,
            status='Hoạt động',
        )

        self.faq_price = FAQ.objects.create(
            faq_code='FAQ-TEST-GIA',
            category='Bảng giá',
            question='Bảng giá dịch vụ massage tại Cham Spa?',
            keywords='giá, bao nhiêu tiền, chi phí, bảng giá',
            answer='Dạ các gói massage tại Cham Spa có giá từ 350.000đ đến 650.000đ ạ.',
            status='Active',
        )

    def test_uc21_anonymous_user_in_memory_only(self):
        """Khách vãng lai chat với bot -> Không được lưu vào bảng Conversation/ConversationMessage"""
        conv_count_before = Conversation.objects.count()
        msg_count_before = ConversationMessage.objects.count()

        response = self.client.post(
            '/chatbox/api/chat/bot-reply/',
            {'message': 'Cho mình hỏi giá dịch vụ thế nào ạ?'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('350.000đ', data['reply'])
        self.assertIsNone(data['conversation_id'])

        self.assertEqual(Conversation.objects.count(), conv_count_before)
        self.assertEqual(ConversationMessage.objects.count(), msg_count_before)

    def test_uc21_authenticated_user_saves_to_db(self):
        """Khách hàng đã đăng nhập chat với bot -> Tự động lưu vào Conversation và Message"""
        self.client.force_login(self.customer_user)

        response = self.client.post(
            '/chatbox/api/chat/bot-reply/',
            {'message': 'Cho mình hỏi bảng giá massage đá nóng?'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNotNone(data['conversation_id'])

        conv = Conversation.objects.get(pk=data['conversation_id'])
        self.assertEqual(conv.customer, self.customer_user)
        self.assertEqual(conv.status, 'Bot xử lý')
        self.assertEqual(conv.messages.count(), 2)

    def test_uc22_transfer_to_staff_requires_login(self):
        """Khách vãng lai bấm 'Gặp nhân viên tư vấn' -> Bị chặn 401 yêu cầu đăng nhập"""
        response = self.client.post('/chatbox/api/conversations/transfer/', {}, content_type='application/json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'require_login')

    def test_uc22_transfer_to_staff_success(self):
        """Khách hàng đăng nhập bấm 'Gặp nhân viên tư vấn' -> Status đổi sang 'Đang chờ'"""
        self.client.force_login(self.customer_user)

        response = self.client.post('/chatbox/api/conversations/transfer/', {}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['conversation_status'], 'Đang chờ')

        conv = Conversation.objects.get(pk=data['conversation_id'])
        self.assertEqual(conv.status, 'Đang chờ')

    def test_uc22_staff_accept_conversation(self):
        """Nhân viên bấm 'Tiếp nhận' -> Status sang 'Đang xử lý', staff được gán"""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            status='Đang chờ',
        )

        self.client.force_login(self.staff_user_1)
        response = self.client.post(f'/chatbox/api/conversations/{conv.id}/accept/')

        self.assertEqual(response.status_code, 200)
        conv.refresh_from_db()
        self.assertEqual(conv.status, 'Đang xử lý')
        self.assertEqual(conv.staff, self.staff_user_1)

    def test_uc22_conflict_when_other_staff_already_assigned(self):
        """Khi cuộc hội thoại đã có Nhân viên 1 xử lý, Nhân viên 2 gửi tin nhắn bị chặn 403."""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            staff=self.staff_user_1,
            status='Đang xử lý',
        )

        self.client.force_login(self.staff_user_2)
        response = self.client.post(
            f'/chatbox/api/conversations/{conv.id}/messages/',
            {'content': 'Em chào anh chị ạ!'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertEqual(data['status'], 'forbidden_assigned')
        self.assertIn('Thanh Thảo', data['error'])

    def test_uc22_assigned_staff_sends_message_with_name(self):
        """Nhân viên phụ trách gửi tin nhắn -> Lưu với sender_type='Staff', hiển thị tên nhân viên"""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            staff=self.staff_user_1,
            status='Đang xử lý',
        )

        self.client.force_login(self.staff_user_1)
        response = self.client.post(
            f'/chatbox/api/conversations/{conv.id}/messages/',
            {'content': 'Dạ em chào anh/chị, em có thể hỗ trợ gì ạ?'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['sender_type'], 'Staff')
        self.assertEqual(data['sender_name'], 'Thanh Thảo')

    def test_uc22_close_conversation(self):
        """Nhân viên bấm 'Đóng phiên chat' -> Status chuyển sang 'Kết thúc', lưu closed_at"""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            staff=self.staff_user_1,
            status='Đang xử lý',
        )

        self.client.force_login(self.staff_user_1)
        response = self.client.post(f'/chatbox/api/conversations/{conv.id}/close/')

        self.assertEqual(response.status_code, 200)
        conv.refresh_from_db()
        self.assertEqual(conv.status, 'Kết thúc')
        self.assertIsNotNone(conv.closed_at)

    def test_uc23_customer_cannot_manage_faqs_forbidden(self):
        """Khách hàng thông thường (Customer) không được phép quản lý FAQ -> Bị chặn 403 Forbidden"""
        self.client.force_login(self.customer_user)
        res = self.client.get('/chatbox/api/admin/faqs/')
        self.assertEqual(res.status_code, 403)

        res_post = self.client.post(
            '/chatbox/api/admin/faqs/',
            {
                'faq_code': 'FAQ-ILLEGAL',
                'category': 'Dịch vụ',
                'question': 'Customer cố tình tạo?',
                'keywords': 'test',
                'answer': 'Không được phép',
                'status': 'Active',
            },
            content_type='application/json',
        )
        self.assertEqual(res_post.status_code, 403)

    def test_uc23_create_faq_unique_code(self):
        """Quản lý tạo FAQ mới và bắt lỗi trùng mã faq_code"""
        self.client.force_login(self.admin_user)

        res1 = self.client.post(
            '/chatbox/api/admin/faqs/',
            {
                'faq_code': 'FAQ-MOI-01',
                'category': 'Khuyến mãi',
                'question': 'Cham Spa có ưu đãi sinh nhật không?',
                'keywords': 'sinh nhật, ưu đãi, giảm giá sinh nhật',
                'answer': 'Dạ Cham Spa giảm ngay 20% cho khách hàng trải nghiệm trong tuần sinh nhật ạ!',
                'status': 'Active',
            },
            content_type='application/json',
        )
        self.assertEqual(res1.status_code, 201)

        res2 = self.client.post(
            '/chatbox/api/admin/faqs/',
            {
                'faq_code': 'FAQ-MOI-01',
                'category': 'Khuyến mãi',
                'question': 'Câu hỏi khác nhưng trùng mã?',
                'keywords': 'test',
                'answer': 'Câu trả lời test',
                'status': 'Active',
            },
            content_type='application/json',
        )
        self.assertEqual(res2.status_code, 400)
        self.assertIn('faq_code', res2.json()['errors'])

    def test_uc23_toggle_faq_status(self):
        """Quản lý bật/tắt trạng thái Active <-> Hidden"""
        self.client.force_login(self.admin_user)

        self.assertEqual(self.faq_price.status, 'Active')
        res = self.client.post(f'/chatbox/api/admin/faqs/{self.faq_price.id}/toggle-status/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['current_status'], 'Hidden')

        self.faq_price.refresh_from_db()
        self.assertEqual(self.faq_price.status, 'Hidden')

    def test_customer_active_conversation_anonymous_returns_none(self):
        """Khách vãng lai gọi lấy lịch sử -> Trả về conversation = null, không lưu DB"""
        res = self.client.get('/chatbox/api/conversations/my-active/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data['is_authenticated'])
        self.assertIsNone(data['conversation'])
        self.assertEqual(len(data['messages']), 0)

    def test_customer_active_conversation_authenticated_returns_history(self):
        """Khách hàng đã đăng nhập -> Lấy lại toàn bộ lịch sử tin nhắn lưu trữ từ CSDL"""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            status='Bot xử lý',
        )
        ConversationMessage.objects.create(
            conversation=conv,
            sender_type='Customer',
            content='Tin nhắn cũ của khách',
        )
        ConversationMessage.objects.create(
            conversation=conv,
            sender_type='Bot',
            content='Tin nhắn phản hồi cũ của bot',
        )

        self.client.force_login(self.customer_user)
        res = self.client.get('/chatbox/api/conversations/my-active/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['is_authenticated'])
        self.assertIsNotNone(data['conversation'])
        self.assertEqual(len(data['messages']), 2)
        self.assertEqual(data['messages'][0]['content'], 'Tin nhắn cũ của khách')

    def test_homepage_chat_widget_visibility(self):
        """Khách vãng lai/khách hàng có chat widget trên homepage; Staff/Admin không có."""
        self.client.logout()
        res_anon = self.client.get('/')
        self.assertEqual(res_anon.status_code, 200)
        self.assertContains(res_anon, 'chamChatbotFab')

        self.client.force_login(self.customer_user)
        res_customer = self.client.get('/')
        self.assertEqual(res_customer.status_code, 200)
        self.assertContains(res_customer, 'chamChatbotFab')

        self.client.force_login(self.staff_user_1)
        res_staff = self.client.get('/')
        self.assertEqual(res_staff.status_code, 200)
        self.assertNotContains(res_staff, 'chamChatbotFab')

        self.client.force_login(self.admin_user)
        res_admin = self.client.get('/')
        self.assertEqual(res_admin.status_code, 200)
        self.assertNotContains(res_admin, 'chamChatbotFab')

    def test_admin_views_permission_and_rendering(self):
        """Admin và nhân sự quản trị truy cập màn hình Admin Boxchat (Giám sát & FAQ)."""
        self.client.force_login(self.admin_user)
        res_mon = self.client.get('/chatbox/admin/monitor/')
        self.assertEqual(res_mon.status_code, 200)
        self.assertContains(res_mon, 'Quản lý Boxchat')
        self.assertContains(res_mon, 'Giám sát Live chat')
        self.assertContains(res_mon, 'Quản lý kịch bản Chatbot')

        res_faq = self.client.get('/chatbox/admin/faqs/')
        self.assertEqual(res_faq.status_code, 200)
        self.assertContains(res_faq, 'Thêm câu hỏi FAQ mới')

        self.client.force_login(self.staff_user_1)
        res_staff_mon = self.client.get('/chatbox/admin/monitor/')
        self.assertEqual(res_staff_mon.status_code, 200)

        res_staff_faq = self.client.get('/chatbox/admin/faqs/')
        self.assertEqual(res_staff_faq.status_code, 200)
        self.assertContains(res_staff_faq, 'Quản lý kịch bản Chatbot')

        self.client.force_login(self.customer_user)
        res_cust_mon = self.client.get('/chatbox/admin/monitor/')
        self.assertEqual(res_cust_mon.status_code, 302)
        self.assertEqual(res_cust_mon.url, '/')

        res_cust_faq = self.client.get('/chatbox/admin/faqs/')
        self.assertEqual(res_cust_faq.status_code, 302)
        self.assertEqual(res_cust_faq.url, '/')

    def test_chatbox_index_role_dispatch(self):
        """Kiểm tra điều hướng tự động tại /chatbox/ theo đúng vai trò tài khoản"""
        self.client.force_login(self.admin_user)
        res_admin = self.client.get('/chatbox/')
        self.assertEqual(res_admin.status_code, 302)
        self.assertEqual(res_admin.url, '/chatbox/admin/monitor/')

        self.client.force_login(self.staff_user_1)
        res_staff = self.client.get('/chatbox/')
        self.assertEqual(res_staff.status_code, 302)
        self.assertEqual(res_staff.url, '/chatbox/inbox/')

        self.client.force_login(self.customer_user)
        res_cust = self.client.get('/chatbox/')
        self.assertEqual(res_cust.status_code, 302)
        self.assertEqual(res_cust.url, '/chatbox/customer/')

    def test_admin_monitor_and_reassign_apis(self):
        """Admin giám sát chi tiết và chuyển giao nhân viên tư vấn"""
        conv = Conversation.objects.create(
            customer=self.customer_user,
            staff=self.staff_user_1,
            status='Đang xử lý',
        )

        self.client.force_login(self.admin_user)
        res_mon = self.client.get(f'/chatbox/api/admin/conversations/{conv.id}/monitor/')
        self.assertEqual(res_mon.status_code, 200)
        self.assertEqual(res_mon.json()['conversation']['customer']['name'], 'Nguyễn Khách Hàng')

        res_reassign = self.client.post(
            f'/chatbox/api/admin/conversations/{conv.id}/reassign/',
            {'staff_id': self.staff_user_2.id},
            content_type='application/json',
        )
        self.assertEqual(res_reassign.status_code, 200)
        conv.refresh_from_db()
        self.assertEqual(conv.staff, self.staff_user_2)

    def test_admin_export_faqs_csv(self):
        """Admin xuất danh sách FAQ dạng CSV UTF-8 thành công"""
        self.client.force_login(self.admin_user)
        res = self.client.get('/chatbox/api/admin/faqs/export/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'text/csv; charset=utf-8-sig')

    def test_faq_blocks_sync_and_exact_answer(self):
        """Khối câu hỏi FAQ đồng bộ đúng với DB và chọn block trả lời chuẩn xác theo faq_id"""
        faq_schedule = FAQ.objects.create(
            faq_code='FAQ-TEST-LICH',
            category='Đặt lịch hẹn',
            question='Giờ mở cửa đón khách của Cham Spa?',
            keywords='giờ mở cửa, hoạt động',
            answer='Dạ Cham Spa mở cửa từ 08:30 đến 22:00 mỗi ngày kể cả cuối tuần ạ.',
            status='Active',
        )
        faq_hidden = FAQ.objects.create(
            faq_code='FAQ-TEST-AN',
            category='Nội bộ',
            question='Câu hỏi đang ẩn chưa công bố?',
            keywords='ẩn, nháp',
            answer='Nội dung chưa phát hành.',
            status='Hidden',
        )

        res = self.client.get('/chatbox/api/chat/faq-blocks/')
        self.assertEqual(res.status_code, 200)
        res_data = res.json()
        self.assertEqual(res_data['status'], 'success')
        block_ids = [b['id'] for b in res_data['blocks']]
        self.assertIn(self.faq_price.id, block_ids)
        self.assertIn(faq_schedule.id, block_ids)
        self.assertNotIn(faq_hidden.id, block_ids)
        self.assertEqual(res_data['categories'], ['Bảng giá', 'Đặt lịch hẹn'])

        conv_before = Conversation.objects.count()
        msg_before = ConversationMessage.objects.count()
        res_anon = self.client.post(
            '/chatbox/api/chat/bot-reply/',
            {'faq_id': faq_schedule.id, 'message': 'Một câu text không chứa từ khóa'},
            content_type='application/json',
        )
        self.assertEqual(res_anon.status_code, 200)
        anon_data = res_anon.json()
        self.assertEqual(anon_data['reply'], faq_schedule.answer)
        self.assertEqual(anon_data['faq_id'], faq_schedule.id)
        self.assertEqual(Conversation.objects.count(), conv_before)
        self.assertEqual(ConversationMessage.objects.count(), msg_before)

        self.client.force_login(self.customer_user)
        res_auth = self.client.post(
            '/chatbox/api/chat/bot-reply/',
            {'faq_id': self.faq_price.id},
            content_type='application/json',
        )
        self.assertEqual(res_auth.status_code, 200)
        auth_data = res_auth.json()
        self.assertEqual(auth_data['reply'], self.faq_price.answer)
        self.assertEqual(auth_data['faq_id'], self.faq_price.id)
        self.assertIsNotNone(auth_data['conversation_id'])
        saved_msgs = ConversationMessage.objects.filter(
            conversation_id=auth_data['conversation_id']
        ).order_by('created_at', 'id')
        self.assertEqual(saved_msgs.count(), 2)
        self.assertEqual(saved_msgs[0].content, self.faq_price.question)
        self.assertEqual(saved_msgs[1].content, self.faq_price.answer)

        res_hidden = self.client.post(
            '/chatbox/api/chat/bot-reply/',
            {'faq_id': faq_hidden.id, 'message': 'ẩn nháp'},
            content_type='application/json',
        )
        self.assertEqual(res_hidden.status_code, 200)
        self.assertNotEqual(res_hidden.json()['reply'], faq_hidden.answer)

    def test_faq_blocks_ui_and_admin_tabs_rendering(self):
        """Kiểm tra render UI khối FAQ (widget & customer_chat) và tab Quản lý Boxchat đồng bộ Admin"""
        res_home = self.client.get('/')
        self.assertEqual(res_home.status_code, 200)
        self.assertContains(res_home, 'chamFaqBlocksPanel')
        self.assertContains(res_home, 'sendWidgetFaqBlock')

        self.client.force_login(self.customer_user)
        res_cust = self.client.get('/chatbox/customer/')
        self.assertEqual(res_cust.status_code, 200)
        self.assertContains(res_cust, 'cust-faq-block')
        self.assertContains(res_cust, 'sendFaqBlockFromBtn')
        self.assertContains(res_cust, self.faq_price.question)

        self.client.force_login(self.admin_user)
        res_mon = self.client.get(reverse('chatbox:admin_monitor'))
        self.assertEqual(res_mon.status_code, 200)
        self.assertContains(res_mon, 'admin-chatbox-nav')
        self.assertContains(res_mon, 'admin-chatbox-nav-btn active')

        res_faq = self.client.get(reverse('chatbox:admin_faq'))
        self.assertEqual(res_faq.status_code, 200)
        self.assertContains(res_faq, 'admin-chatbox-nav')
        self.assertContains(res_faq, 'admin-chatbox-nav-btn active')

        self.client.force_login(self.staff_user_1)
        res_inbox = self.client.get(reverse('chatbox:inbox'))
        self.assertEqual(res_inbox.status_code, 200)
        self.assertNotContains(res_inbox, 'appointmentDirectCard')
        self.assertNotContains(res_inbox, 'Xác nhận lịch hẹn trực tiếp')
        self.assertNotContains(res_inbox, 'staff-unread-badge')
