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
from rest_framework import status
from rest_framework.test import APIClient

from core.models import UserHealthProfile, Appointment

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

        # API Clients
        self.client_customer = APIClient()
        self.client_customer.force_authenticate(user=self.customer)

        self.client_staff = APIClient()
        self.client_staff.force_authenticate(user=self.staff_user)

        self.client_anonymous = APIClient()

    # -------------------------------------------------------------------------
    # TEST 1: UC-8.1 - TẠO MỚI VÀ GHI ĐÈ HỒ SƠ SỨC KHỎE CHUẨN 1-1
    # -------------------------------------------------------------------------
    def test_create_and_overwrite_health_profile_1to1(self):
        """
        Kiểm tra nghiệp vụ chuẩn 1-1 tối giản:
        Lần 1 tạo mới sinh mã HP-KH...
        Lần 2 cập nhật ghi đè bản ghi cũ, số lượng bản ghi trong DB vẫn là 1.
        """
        url = reverse('health:api_update')
        payload1 = {
            "height_cm": 160.0,
            "weight_kg": 50.0,
            "blood_pressure": "Bình thường",
            "focus_areas": ["Vai gáy", "Cổ gáy"],
            "massage_pressure": "Lực vừa",
            "pain_level": 6,
            "health_conditions": ["Da nhạy cảm"],
            "allergy_notes": "Dị ứng tinh dầu sả chanh",
            "recovery_goals": ["Giảm đau mỏi cổ vai gáy"],
            "special_requests": "Phòng ấm 26 độ"
        }

        # Lần 1: Tạo mới hồ sơ
        response1 = self.client_customer.post(url, payload1, format='json')
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response1.data['status'], 'success')
        self.assertTrue(response1.data['health_code'].startswith('HP-KH'))

        # Kiểm tra trong DB
        self.assertEqual(UserHealthProfile.objects.filter(user=self.customer).count(), 1)
        hp = UserHealthProfile.objects.get(user=self.customer)
        self.assertEqual(hp.pain_level, 6)
        self.assertEqual(hp.massage_pressure, 'Lực vừa')
        self.assertIn('Vai gáy', hp.focus_areas)

        # Lần 2: Cập nhật lại (Ghi đè bản ghi cũ)
        payload2 = {
            "height_cm": 162.0,
            "weight_kg": 52.0,
            "blood_pressure": "Thấp",
            "focus_areas": ["Thắt lưng", "Bắp chân"],
            "massage_pressure": "Nhẹ nhàng",
            "pain_level": 4,
            "health_conditions": ["Đang mang thai"],
            "allergy_notes": "Dị ứng gừng",
            "recovery_goals": ["Thư giãn giảm stress"],
            "special_requests": "Không ấn huyệt chân"
        }
        response2 = self.client_customer.put(url, payload2, format='json')
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data['status'], 'success')

        # Kiểm tra số lượng bản ghi vẫn là 1 (Tuyệt đối không sinh thêm bản ghi thứ 2)
        self.assertEqual(UserHealthProfile.objects.filter(user=self.customer).count(), 1)
        hp.refresh_from_db()
        self.assertEqual(hp.pain_level, 4)
        self.assertEqual(hp.blood_pressure, 'Thấp')
        self.assertEqual(hp.massage_pressure, 'Nhẹ nhàng')
        self.assertIn('Thắt lưng', hp.focus_areas)
        self.assertIn('Đang mang thai', hp.health_conditions)

    # -------------------------------------------------------------------------
    # TEST 2: KIỂM TRA TỰ ĐỘNG TÍNH CHỈ SỐ BMI VÀ PHÂN LOẠI
    # -------------------------------------------------------------------------
    def test_bmi_calculation_and_classification(self):
        """
        Kiểm tra công thức tính BMI = weight / (height/100)^2
        và phân loại thể trạng tự động.
        Ví dụ: Cao 160cm, Nặng 50kg -> BMI = 50 / (1.6 * 1.6) = 19.5 (Cân đối)
        """
        UserHealthProfile.objects.create(
            user=self.customer,
            health_code='HP-KH0099',
            height_cm=160.0,
            weight_kg=50.0,
            blood_pressure='Bình thường',
            massage_pressure='Lực vừa',
            pain_level=3
        )

        url = reverse('health:api_profile')
        res = self.client_customer.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['has_profile'], True)
        self.assertEqual(res.data['data']['bmi'], 19.5)
        self.assertIn('bình thường', res.data['data']['bmi_classification'].lower())

    # -------------------------------------------------------------------------
    # TEST 3: KIỂM TRA HỆ THỐNG CỜ CẢNH BÁO Y TẾ ĐỎ (SAFETY ALERTS)
    # -------------------------------------------------------------------------
    def test_medical_safety_alert_flags(self):
        """
        Kiểm tra hệ thống phát hiện các nguy cơ:
        - Đang mang thai -> Cảnh báo nguy cơ cao (tránh bấm huyệt Hợp Cốc)
        - Huyết áp cao -> Cảnh báo cao
        - Dị ứng tinh dầu -> Cảnh báo cấm dùng
        """
        hp = UserHealthProfile.objects.create(
            user=self.customer,
            health_code='HP-KH0077',
            height_cm=165.0,
            weight_kg=55.0,
            blood_pressure='Cao',
            health_conditions=['Đang mang thai', 'Da nhạy cảm'],
            allergy_notes='Dị ứng sả chanh',
            massage_pressure='Nhẹ nhàng',
            pain_level=7
        )

        url = reverse('health:api_profile')
        res = self.client_customer.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['data']['has_medical_alert'])
        alerts = res.data['data']['alert_details']
        self.assertTrue(any(a['title'] == 'Huyết áp cao' for a in alerts))
        self.assertTrue(any('mang thai' in a['title'].lower() for a in alerts))
        self.assertTrue(any('dị ứng' in a['title'].lower() for a in alerts))

    # -------------------------------------------------------------------------
    # TEST 4: VALIDATION DỮ LIỆU ĐẦU VÀO PHI LÝ
    # -------------------------------------------------------------------------
    def test_invalid_input_validation(self):
        """
        Kiểm tra bắt lỗi:
        - Chiều cao âm hoặc quá 250cm -> Báo lỗi 400
        - Cân nặng âm hoặc quá 250kg -> Báo lỗi 400
        - Mức độ đau ngoài khoảng 1-10 -> Báo lỗi 400
        """
        url = reverse('health:api_update')

        # Thử chiều cao âm
        bad_payload_height = {"height_cm": -10}
        res1 = self.client_customer.post(url, bad_payload_height, format='json')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        # Thử cân nặng vượt quá 300kg
        bad_payload_weight = {"weight_kg": 350}
        res2 = self.client_customer.post(url, bad_payload_weight, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

        # Thử mức đau 15/10
        bad_payload_pain = {"pain_level": 15}
        res3 = self.client_customer.post(url, bad_payload_pain, format='json')
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------------------
    # TEST 5: PHÂN QUYỀN XEM HỒ SƠ (UC-8.2)
    # -------------------------------------------------------------------------
    def test_access_permissions_user_vs_staff(self):
        """
        - Khách hàng xem của chính mình -> Được phép.
        - Khách hàng xem của người khác qua user_id -> Không được phép (Bảo mật).
        - Nhân viên / Quản lý xem của khách bất kỳ -> Được phép để chuẩn bị ca trực.
        """
        hp1 = UserHealthProfile.objects.create(
            user=self.customer,
            health_code='HP-KH001',
            blood_pressure='Bình thường',
            massage_pressure='Lực vừa',
            pain_level=5
        )

        # 1. Khách hàng 1 xem của chính mình -> OK
        res1 = self.client_customer.get(reverse('health:api_profile'))
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data['data']['health_code'], 'HP-KH001')

        # 2. Khách hàng 2 đăng nhập và thử xem qua API customer của Staff -> Bị chặn 403 Forbidden
        client_customer2 = APIClient()
        client_customer2.force_authenticate(user=self.customer2)
        res2 = client_customer2.get(reverse('health:api_customer_health', kwargs={'user_id': self.customer.id}))
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Nhân viên trực xem hồ sơ của Khách hàng 1 -> Được phép 200 OK
        res3 = self.client_staff.get(reverse('health:api_customer_health', kwargs={'user_id': self.customer.id}))
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertEqual(res3.data['health_profile']['health_code'], 'HP-KH001')

    # -------------------------------------------------------------------------
    # TEST 6: TIỆN ÍCH ĐỒNG BỘ LỰC MASSAGE SANG FORM ĐẶT LỊCH
    # -------------------------------------------------------------------------
    def test_sync_pressure_to_booking_api(self):
        """
        Kiểm tra API /health/api/sync-pressure/ trả về lực massage mong muốn
        để auto-fill vào form Đặt lịch hẹn Module 1.
        """
        UserHealthProfile.objects.create(
            user=self.customer,
            health_code='HP-KH0055',
            massage_pressure='Lực mạnh',
            focus_areas=['Vai gáy', 'Thắt lưng'],
            pain_level=8
        )

        res = self.client_customer.get(reverse('health:api_sync_pressure'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['preferred_pressure'], 'Lực mạnh')
        self.assertIn('Vai gáy', res.data['focus_areas'])

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

        # 4. Trang chi tiết cho Staff
        res_staff_detail = web_client_staff.get(reverse('health:staff_detail', kwargs={'user_id': self.customer.id}))
        self.assertEqual(res_staff_detail.status_code, 200)
