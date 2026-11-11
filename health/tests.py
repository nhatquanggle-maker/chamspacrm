"""
================================================================================
UNIT TESTS CHO PHÂN HỆ QUẢN LÝ HỒ SƠ SỨC KHỎE (MOD-08) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc (Meo)
Kiểm thử toàn diện:
  - UC-8.1: Cập nhật hồ sơ sức khỏe khách hàng 1-1 (Ghi đè, tính BMI, validate dữ liệu)
  - UC-8.2: Xem hồ sơ sức khỏe cá nhân & Phân quyền bảo mật (User / Staff)
  - Tiện ích đồng bộ lực massage sang form đặt lịch
  - Tính toán chỉ số sinh trắc học và hệ thống cờ cảnh báo an toàn y tế cho KTV
================================================================================
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from core.models import UserHealthProfile, Appointment
from .helpers import serialize_health_profile

User = get_user_model()


class HealthProfileModelAndAPITest(TestCase):
    """
    Tập hợp các ca kiểm thử cho Module 8: Quản lý Hồ sơ Sức khỏe
    """

    def setUp(self):
        # 1. Tạo tài khoản Khách hàng (Customer)
        self.customer = User.objects.create_user(
            username='khachhang_test',
            phone='0988112233',
            email='khachhang@example.com',
            name='Nguyễn Thị Hoa',
            password='Password123!',
            is_staff=False,
            is_superuser=False
        )

        # 2. Tạo tài khoản Khách hàng thứ 2
        self.customer2 = User.objects.create_user(
            username='khachhang2_test',
            phone='0988445566',
            email='khachhang2@example.com',
            name='Trần Văn Nam',
            password='Password123!',
            is_staff=False,
            is_superuser=False
        )

        # 3. Tạo tài khoản Nhân viên (Staff)
        self.staff_user = User.objects.create_user(
            username='staff_test',
            phone='0905999888',
            email='staff@chamspa.vn',
            name='KTV Thảo CSKH',
            password='Password123!',
            is_staff=True,
            is_superuser=False
        )

        # 4. Tạo tài khoản Quản trị viên (Admin)
        self.admin_user = User.objects.create_user(
            username='admin_test',
            phone='0901000111',
            email='admin@chamspa.vn',
            name='Quản trị Cham Spa',
            password='Password123!',
            is_staff=True,
            is_superuser=True
        )

        # Test Clients
        self.client_customer = Client()
        self.client_customer.force_login(self.customer)

        self.client_staff = Client()
        self.client_staff.force_login(self.staff_user)

        self.client_anonymous = Client()

    # -------------------------------------------------------------------------
    # TEST 1: UC-8.1 - TẠO MỚI VÀ GHI ĐÈ HỒ SƠ SỨC KHỎE CHUẨN 1-1
    # -------------------------------------------------------------------------
    def test_create_and_overwrite_health_profile_1to1(self):
        """
        Kiểm tra nghiệp vụ chuẩn 1-1 tối giản:
        Lần 1 tạo mới sinh mã HP-KH...
        Lần 2 cập nhật ghi đè bản ghi cũ, số lượng bản ghi trong DB vẫn là 1.
        """
        # Xóa bản ghi auto-sync từ accounts.signals để test kịch bản tạo mới từ đầu
        UserHealthProfile.objects.filter(user=self.customer).delete()

        url = reverse('health:update')
        payload1 = {
            "height_cm": "160.0",
            "weight_kg": "50.0",
            "blood_pressure": "Bình thường",
            "focus_areas": ["Vai gáy", "Cổ gáy"],
            "massage_pressure": "Lực vừa",
            "pain_level": "6",
            "health_conditions": ["Da nhạy cảm"],
            "allergy_notes": "Dị ứng tinh dầu sả chanh",
            "recovery_goals": ["Giảm đau mỏi cổ vai gáy"],
            "special_requests": "Phòng ấm 26 độ",
        }

        # Lần 1: Tạo mới hồ sơ qua Form POST (bỏ qua các trường bệnh lý/dị ứng cũ)
        response1 = self.client_customer.post(url, payload1)
        self.assertEqual(response1.status_code, 302)
        self.assertEqual(response1.url, reverse('health:profile'))

        # Kiểm tra trong DB
        self.assertEqual(UserHealthProfile.objects.filter(user=self.customer).count(), 1)
        hp = UserHealthProfile.objects.get(user=self.customer)
        self.assertTrue(hp.health_code.startswith('HP-KH'))
        self.assertEqual(hp.pain_level, 6)
        self.assertEqual(hp.massage_pressure, 'Lực vừa')
        self.assertIn('Vai gáy', hp.focus_areas)
        self.assertEqual(hp.health_conditions, [])
        self.assertEqual(hp.allergy_notes, '')

        # Lần 2: Cập nhật lại (Ghi đè bản ghi cũ)
        payload2 = {
            "height_cm": "162.0",
            "weight_kg": "52.0",
            "blood_pressure": "Thấp",
            "focus_areas": ["Thắt lưng", "Bắp chân"],
            "massage_pressure": "Nhẹ nhàng",
            "pain_level": "4",
            "health_conditions": ["Đang mang thai"],
            "allergy_notes": "Dị ứng gừng",
            "recovery_goals": ["Thư giãn giảm stress"],
            "special_requests": "Không ấn huyệt chân",
        }
        response2 = self.client_customer.post(url, payload2)
        self.assertEqual(response2.status_code, 302)
        self.assertEqual(response2.url, reverse('health:profile'))

        # Kiểm tra số lượng bản ghi vẫn là 1 (Tuyệt đối không sinh thêm bản ghi thứ 2)
        self.assertEqual(UserHealthProfile.objects.filter(user=self.customer).count(), 1)
        hp.refresh_from_db()
        self.assertEqual(hp.pain_level, 4)
        self.assertEqual(hp.blood_pressure, 'Thấp')
        self.assertEqual(hp.massage_pressure, 'Nhẹ nhàng')
        self.assertIn('Thắt lưng', hp.focus_areas)
        self.assertEqual(hp.health_conditions, [])
        self.assertEqual(hp.allergy_notes, '')

    def test_bmi_calculation_and_classification(self):
        """Kiểm tra công thức tính BMI và hiển thị trên giao diện."""
        hp, _ = UserHealthProfile.objects.update_or_create(
            user=self.customer,
            defaults={
                'health_code': 'HP-KH0099',
                'height_cm': 160.0,
                'weight_kg': 50.0,
                'blood_pressure': 'Bình thường',
                'massage_pressure': 'Lực vừa',
                'pain_level': 3,
            }
        )

        data = serialize_health_profile(hp)
        self.assertEqual(data['bmi'], 19.5)
        self.assertIn('bình thường', data['bmi_classification'].lower())

        res = self.client_customer.get(reverse('health:profile'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '19.5')

    def test_medical_safety_alert_flags(self):
        """Chỉ giữ lại cảnh báo huyết áp; không sinh cảnh báo bệnh lý hoặc dị ứng."""
        hp, _ = UserHealthProfile.objects.update_or_create(
            user=self.customer,
            defaults={
                'health_code': 'HP-KH0077',
                'height_cm': 165.0,
                'weight_kg': 55.0,
                'blood_pressure': 'Cao',
                'health_conditions': ['Đang mang thai', 'Da nhạy cảm'],
                'allergy_notes': 'Dị ứng sả chanh',
                'massage_pressure': 'Nhẹ nhàng',
                'pain_level': 7,
            }
        )

        data = serialize_health_profile(hp)
        self.assertTrue(data['has_medical_alert'])
        self.assertNotIn('health_conditions', data)
        self.assertNotIn('allergy_notes', data)
        alerts = data['alert_details']
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['title'], 'Huyết áp cao')
        self.assertFalse(any('mang thai' in a['title'].lower() for a in alerts))
        self.assertFalse(any('dị ứng' in a['title'].lower() for a in alerts))

    def test_invalid_input_validation(self):
        """Kiểm tra bắt lỗi chiều cao/cân nặng/mức đau phi lý trên form POST."""
        url = reverse('health:update')

        res1 = self.client_customer.post(url, {"height_cm": "-10"})
        self.assertEqual(res1.status_code, 302)
        self.assertEqual(res1.url, url)

        res2 = self.client_customer.post(url, {"weight_kg": "350"})
        self.assertEqual(res2.status_code, 302)
        self.assertEqual(res2.url, url)

        res3 = self.client_customer.post(url, {"pain_level": "15"})
        self.assertEqual(res3.status_code, 302)
        self.assertEqual(res3.url, url)

        hp = UserHealthProfile.objects.get(user=self.customer)
        self.assertIsNone(hp.height_cm)
        self.assertIsNone(hp.weight_kg)

    def test_access_permissions_user_vs_staff(self):
        """Kiểm tra phân quyền: Khách ẩn danh redirect login, khách hàng bị chặn trang Staff, Staff xem được."""
        UserHealthProfile.objects.update_or_create(
            user=self.customer,
            defaults={
                'health_code': 'HP-KH001',
                'blood_pressure': 'Bình thường',
                'massage_pressure': 'Lực vừa',
                'pain_level': 5,
            }
        )

        # Khách chưa đăng nhập gửi form cập nhật -> redirect về login
        res_anon = self.client_anonymous.post(reverse('health:update'), {})
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn(reverse('accounts:login'), res_anon.url)

        # Khách hàng 1 xem hồ sơ của chính mình -> 200
        res1 = self.client_customer.get(reverse('health:profile'))
        self.assertEqual(res1.status_code, 200)

        # Khách hàng 2 vào màn hình tra cứu của nhân viên -> bị chặn redirect về home
        client_customer2 = Client()
        client_customer2.force_login(self.customer2)
        res2 = client_customer2.get(reverse('health:staff_lookup'))
        self.assertEqual(res2.status_code, 302)

        # Nhân viên trực xem hồ sơ chi tiết KTV của Khách hàng 1 -> 200 OK
        res3 = self.client_staff.get(reverse('health:staff_detail', kwargs={'user_id': self.customer.id}) + '?view=ktv')
        self.assertEqual(res3.status_code, 200)
        self.assertContains(res3, 'Nguyễn Thị Hoa')

    # -------------------------------------------------------------------------
    # TEST 7: KIỂM TRA CÁC GIAO DIỆN WEB (DJANGO VIEWS & TEMPLATES)
    # -------------------------------------------------------------------------
    def test_web_views_render_success(self):
        """
        Kiểm tra các trang web của Module 8 render thành công (Status 200 OK):
        - /health/ (Trang xem hồ sơ cá nhân)
        - /health/update/ (Trang khảo sát / cập nhật)
        - /health/staff/ (Trang tra cứu cho Staff)
        - /health/staff/<id>/ (Trang chi tiết cho Staff)
        """
        web_client_customer = Client()
        web_client_customer.force_login(self.customer)

        web_client_staff = Client()
        web_client_staff.force_login(self.staff_user)

        # 1. Trang xem hồ sơ (Customer)
        res_view = web_client_customer.get(reverse('health:profile'))
        self.assertEqual(res_view.status_code, 200)

        # 2. Trang cập nhật form (Customer)
        res_form = web_client_customer.get(reverse('health:update'))
        self.assertEqual(res_form.status_code, 200)

        # 3. Trang tra cứu cho Staff
        res_staff_lookup = web_client_staff.get(reverse('health:staff_lookup'))
        self.assertEqual(res_staff_lookup.status_code, 200)

        # 4. Trang chi tiết cho Staff (Chuyển hướng đồng bộ sang 3-tab detail view của Staff)
        res_staff_detail = web_client_staff.get(reverse('health:staff_detail', kwargs={'user_id': self.customer.id}), follow=True)
        self.assertEqual(res_staff_detail.status_code, 200)

        # 5. Giao diện chuyên sâu KTV (Figma Node 279:1633)
        res_ktv = web_client_staff.get(reverse('health:staff_detail', kwargs={'user_id': self.customer.id}) + '?view=ktv')
        self.assertEqual(res_ktv.status_code, 200)

    # -------------------------------------------------------------------------
    # TEST 8: PHÂN TRANG 7 HỒ SƠ/TRANG & LOẠI BỎ BADGE "CA TRỰC" TRÊN STAFF LOOKUP
    # -------------------------------------------------------------------------
    def test_staff_lookup_pagination_and_compact_layout(self):
        """
        Kiểm tra:
        - Bảng tra cứu Staff hiển thị tối đa 7 hồ sơ mỗi trang và phân trang chính xác
        - Giữ nguyên tham số ?q= và ?alert= trên liên kết phân trang
        - Không còn nút/badge "Ca trực:" ở thanh tiêu đề
        - Trả về bmi_short_label gọn cho giao diện bảng
        """
        for idx in range(1, 10):
            u = User.objects.create_user(
                username=f'paging_kh_{idx}',
                phone=f'091100000{idx}',
                email=f'paging_{idx}@chamspa.vn',
                name=f'Khách Phân Trang {idx}',
                password='Password123!',
                is_staff=False,
            )
            UserHealthProfile.objects.update_or_create(
                user=u,
                defaults={
                    'height_cm': 165.0,
                    'weight_kg': 55.0,
                    'blood_pressure': 'Bình thường',
                    'massage_pressure': 'Lực vừa',
                    'pain_level': 4,
                }
            )

        web_client_staff = Client()
        web_client_staff.force_login(self.staff_user)

        # Trang 1: 7 hồ sơ (tổng 11 gồm customer, customer2 auto-sync + 9 khách mới)
        res_p1 = web_client_staff.get(reverse('health:staff_lookup'))
        self.assertEqual(res_p1.status_code, 200)
        self.assertEqual(len(res_p1.context['page_obj']), 7)
        self.assertEqual(res_p1.context['page_obj'].paginator.num_pages, 2)
        self.assertEqual(res_p1.context['total_profiles'], 11)

        html_p1 = res_p1.content.decode('utf-8')
        self.assertNotIn('Ca trực:', html_p1)
        self.assertNotIn('<th>Cập nhật</th>', html_p1)
        self.assertNotIn('>Cảnh báo KTV</th>', html_p1)
        self.assertNotIn('{%', html_p1)
        self.assertNotIn('{{', html_p1)
        self.assertIn('<colgroup>', html_p1)
        self.assertIn('<th>Khách hàng</th>', html_p1)
        self.assertIn('Cân đối', html_p1)
        self.assertIn('text-center', html_p1)
        self.assertIn('page=2', html_p1)

        # Trang 2: 4 hồ sơ còn lại
        res_p2 = web_client_staff.get(reverse('health:staff_lookup') + '?page=2')
        self.assertEqual(res_p2.status_code, 200)
        self.assertEqual(len(res_p2.context['page_obj']), 4)

        # Tìm kiếm kèm phân trang vẫn giữ nguyên q= (9 khớp -> 7 trang 1, 2 trang 2)
        res_q = web_client_staff.get(reverse('health:staff_lookup'), {'q': 'Khách Phân Trang'})
        self.assertEqual(res_q.status_code, 200)
        self.assertEqual(len(res_q.context['page_obj']), 7)
        self.assertIn('q=Kh%C3%A1ch%20Ph%C3%A2n%20Trang&amp;page=2', res_q.content.decode('utf-8'))

        res_q_p2 = web_client_staff.get(reverse('health:staff_lookup'), {'q': 'Khách Phân Trang', 'page': 2})
        self.assertEqual(res_q_p2.status_code, 200)
        self.assertEqual(len(res_q_p2.context['page_obj']), 2)

        # Tab Thông tin cá nhân trên chi tiết khách hàng đã bỏ khối "GHI CHÚ CHĂM SÓC"
        res_detail_info = web_client_staff.get(
            reverse('accounts:admin_customer_detail', kwargs={'pk': self.customer.id}) + '?tab=info'
        )
        self.assertEqual(res_detail_info.status_code, 200)
        self.assertNotIn('GHI CHÚ CHĂM SÓC', res_detail_info.content.decode('utf-8'))

        # Kiểm tra lọc theo Huyết áp (?bp=Cao) giữ tham số filter
        UserHealthProfile.objects.filter(user=self.customer).update(blood_pressure='Cao')
        res_bp_high = web_client_staff.get(reverse('health:staff_lookup'), {'bp': 'Cao'})
        self.assertEqual(res_bp_high.status_code, 200)
        self.assertEqual(res_bp_high.context['page_obj'].paginator.count, 1)

    def test_removed_conditions_allergies_and_staff_admin_medical_warnings(self):
        """Xác nhận chỉ giữ lại Huyết áp ở hồ sơ sức khỏe và bỏ hẳn Cảnh báo y tế / Dị ứng trên Staff & Admin."""
        UserHealthProfile.objects.update_or_create(
            user=self.customer,
            defaults={
                'health_code': 'HP-KH8888',
                'height_cm': 162.0,
                'weight_kg': 52.0,
                'blood_pressure': 'Bình thường',
                'massage_pressure': 'Lực vừa',
                'pain_level': 6,
            }
        )

        removed_terms = [
            'Thai kỳ', 'Tim mạch', 'Giãn tĩnh mạch', 'Da nhạy cảm',
            'Phẫu thuật', 'Bệnh nền', 'Cảnh báo y tế', 'Cảnh báo An toàn Y tế',
            'Dị ứng', 'dị ứng', 'allergy_notes', 'health_conditions',
        ]

        # 1. Giao diện Khách hàng: xem & cập nhật hồ sơ
        for url in [reverse('health:profile'), reverse('health:update')]:
            res = self.client_customer.get(url)
            self.assertEqual(res.status_code, 200)
            html = res.content.decode('utf-8')
            self.assertIn('Huyết áp', html)
            for term in removed_terms:
                self.assertNotIn(term, html, f"Không được hiển thị '{term}' tại {url}")

        # 2. Giao diện Staff tra cứu & in phiếu KTV & chi tiết 360 độ
        staff_urls = [
            reverse('health:staff_lookup'),
            reverse('health:staff_detail', kwargs={'user_id': self.customer.id}) + '?view=ktv',
            reverse('accounts:admin_customer_detail', kwargs={'pk': self.customer.id}) + '?tab=health',
            reverse('accounts:admin_customer_list'),
        ]
        for url in staff_urls:
            res = self.client_staff.get(url)
            self.assertEqual(res.status_code, 200)
            html = res.content.decode('utf-8')
            for term in removed_terms:
                self.assertNotIn(term, html, f"Không được hiển thị '{term}' cho Staff tại {url}")

        # 3. Giao diện Admin: chi tiết khách hàng tab health & dashboard admin
        client_admin = Client()
        client_admin.force_login(self.admin_user)
        for url in [
            reverse('accounts:admin_customer_detail', kwargs={'pk': self.customer.id}) + '?tab=health',
            reverse('dashboard:admin'),
        ]:
            res = client_admin.get(url)
            self.assertEqual(res.status_code, 200)
            html = res.content.decode('utf-8')
            self.assertNotIn('cảnh báo an toàn', html.lower())
            for term in removed_terms:
                self.assertNotIn(term, html, f"Không được hiển thị '{term}' cho Admin tại {url}")

