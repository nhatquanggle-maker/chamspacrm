"""
================================================================================
MODULE 10: QUẢN LÝ DASHBOARD & BÁO CÁO (MOD-10) - AUTOMATED UNIT & API TESTS
Thành viên phụ trách: MINH KHA
Mục đích:
  - Kiểm thử tự động khép kín toàn bộ tính năng Module 10:
    1. Kiểm thử phân quyền truy cập (Admin/Staff truy cập thành công, Khách thường/Vãng lai bị chặn).
    2. Kiểm thử API Thống kê Thời gian thực (/dashboard/api/stats/ & /dashboard/api/admin/dashboard-stats/).
    3. Kiểm thử các bộ lọc thời gian: Hôm nay, 7 ngày qua, Tháng này, Năm nay, Tùy chọn.
    4. Kiểm thử API Xuất dữ liệu Báo cáo phục vụ SheetJS & html2pdf.js (/dashboard/api/export-data/).
    5. Kiểm thử độ chính xác của các hàm tính toán KPI trong services.py.
================================================================================
"""

from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse

from core.models import (
    User,
    Category,
    Service,
    Tier,
    Membership,
    Appointment,
    AppointmentDetail,
    Invoice,
    Feedback,
    UserHealthProfile
)
from dashboard import services


class DashboardModuleTests(TestCase):
    """
    Tập hợp các ca kiểm thử tự động cho Module 10: Dashboard.
    """

    def setUp(self):
        # 1. Tạo tài khoản Quản trị viên (Superuser)
        self.admin_user = User.objects.create_superuser(
            username='admin_test',
            name='Quản trị viên Test',
            email='admin_test@chamspa.com',
            phone='0909999001',
            password='AdminPassword123@'
        )

        # 2. Tạo tài khoản Kỹ thuật viên (Staff)
        self.staff_user = User.objects.create_user(
            username='staff_test',
            name='Nhân viên Test',
            email='staff_test@chamspa.com',
            phone='0909999002',
            password='StaffPassword123@',
            is_staff=True
        )

        # 3. Tạo tài khoản Khách hàng thông thường (Customer)
        self.customer_user = User.objects.create_user(
            username='cust_test',
            name='Khách hàng Test',
            email='cust_test@gmail.com',
            phone='0909999003',
            password='CustPassword123@',
            is_staff=False,
            is_superuser=False
        )

        # 4. Tạo Danh mục & Dịch vụ mẫu
        self.category = Category.objects.create(
            name='Massage Body Champa',
            slug='massage-body-champa-test',
            status='Hoạt động'
        )

        self.service = Service.objects.create(
            category=self.category,
            name='Massage Body Đá Nóng 90p Test',
            slug='massage-body-da-nong-90p-test',
            price_vnd=Decimal('500000.00'),
            duration_minutes=90,
            status='Hoạt động'
        )

        # 5. Tạo Hạng thẻ & Thẻ hội viên
        self.tier = Tier.objects.create(
            name='Hạng Vàng Test',
            min_points=500,
            discount_percent=10
        )

        self.membership, _ = Membership.objects.update_or_create(
            user=self.customer_user,
            defaults={
                'tier': self.tier,
                'current_points': 600,
                'total_spent': Decimal('6000000.00')
            }
        )

        # 6. Tạo Lịch hẹn & Hóa đơn
        self.appointment = Appointment.objects.create(
            appointment_code='AP-TEST-001',
            user=self.customer_user,
            appointment_date=timezone.now().date(),
            time_slot='14:00',
            total_guests=2,
            customer_name='Khách hàng Test',
            customer_phone='0909999003',
            status='Completed'
        )

        self.appt_detail = AppointmentDetail.objects.create(
            appointment=self.appointment,
            service=self.service,
            guest_index=1,
            gender='Nữ',
            massage_pressure='Lực vừa'
        )

        self.invoice = Invoice.objects.create(
            appointment=self.appointment,
            amount=Decimal('1000000.00'),
            discount_applied=Decimal('100000.00'),
            status='Đã thanh toán',
            paid_at=timezone.now()
        )

        # 7. Cập nhật/Tạo Hồ sơ Sức khỏe mẫu (MOD-08)
        self.health_profile, _ = UserHealthProfile.objects.update_or_create(
            user=self.customer_user,
            defaults={
                'health_code': 'HP-TEST-001',
                'blood_pressure': 'Cao',
                'focus_areas': ['Vai gáy', 'Thắt lưng'],
                'massage_pressure': 'Lực vừa',
                'pain_level': 6,
                'health_conditions': [],
                'allergy_notes': '',
            }
        )

        self.client = Client()

    def test_anonymous_access_denied(self):
        """Khách vãng lai chưa đăng nhập gọi API thống kê phải bị từ chối 401."""
        response = self.client.get('/dashboard/api/stats/')
        self.assertEqual(response.status_code, 401)

    def test_customer_access_forbidden(self):
        """Khách hàng thường không có quyền xem thống kê -> 403 Forbidden."""
        self.client.force_login(self.customer_user)
        response = self.client.get('/dashboard/api/stats/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/dashboard/').status_code, 403)
        self.assertEqual(self.client.get('/dashboard/admin/').status_code, 403)
        self.assertEqual(self.client.get('/dashboard/staff/').status_code, 403)

    def test_admin_access_allowed(self):
        """Quản lý (Admin) truy cập hợp lệ -> 200 OK."""
        self.client.force_login(self.admin_user)
        response = self.client.get('/dashboard/api/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

    def test_staff_access_allowed(self):
        """Nhân viên (Staff) truy cập hợp lệ -> 200 OK."""
        self.client.force_login(self.staff_user)
        response = self.client.get('/dashboard/api/stats/')
        self.assertEqual(response.status_code, 200)

    def test_api_contract_20_schema(self):
        """Kiểm tra cấu trúc JSON trả về của /dashboard/api/stats/."""
        self.client.force_login(self.admin_user)
        response = self.client.get('/dashboard/api/stats/?period=this_month')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        expected_keys = [
            'total_revenue',
            'total_appointments',
            'completed_rate',
            'new_members',
            'revenue_chart',
            'top_services',
            'membership_chart',
            'health_analytics',
            'kpi',
            'recent_transactions'
        ]
        for key in expected_keys:
            self.assertIn(key, data, f"Thiếu trường '{key}'")

        self.assertGreaterEqual(data['total_revenue'], 1000000.0)
        self.assertGreaterEqual(data['total_appointments'], 1)
        self.assertGreaterEqual(data['completed_rate'], 0.0)
        self.assertGreaterEqual(data['health_analytics']['total_profiles'], 1)
        self.assertGreaterEqual(data['health_analytics']['avg_pain_level'], 0.0)
        self.assertGreaterEqual(data['health_analytics']['special_alert_count'], 1)
        self.assertEqual(data['health_analytics']['top_conditions'], [])
        self.assertIn('Vai gáy', data['health_analytics']['focus_chart']['labels'])

    def test_period_filters(self):
        """Kiểm tra phản hồi của tất cả các bộ lọc thời gian."""
        self.client.force_login(self.admin_user)

        periods = ['today', 'last_7_days', 'this_month', 'this_year']
        for p in periods:
            resp = self.client.get(f'/dashboard/api/stats/?period={p}')
            self.assertEqual(resp.status_code, 200)
            payload = resp.json()
            self.assertEqual(payload['status'], 'success')
            self.assertIn('period_label', payload)

        today_str = timezone.now().date().strftime('%Y-%m-%d')
        resp_custom = self.client.get(f'/dashboard/api/stats/?period=custom&from_date={today_str}&to_date={today_str}')
        self.assertEqual(resp_custom.status_code, 200)
        self.assertEqual(resp_custom.json()['period'], 'custom')

    def test_export_data_api(self):
        """Kiểm tra API cung cấp dữ liệu xuất Excel & PDF."""
        self.client.force_login(self.admin_user)
        response = self.client.get('/dashboard/api/export-data/?period=this_month')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'success')

        export_data = payload['data']
        self.assertIn('kpis', export_data)
        self.assertIn('invoice_rows', export_data)
        self.assertIn('top_services', export_data)
        self.assertGreaterEqual(len(export_data['invoice_rows']), 1)

    def test_admin_dashboard_template_view(self):
        """Kiểm tra trang HTML Dashboard của Quản trị viên render thành công."""
        self.client.force_login(self.admin_user)
        response = self.client.get('/dashboard/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'BẢNG ĐIỀU KHIỂN & BÁO CÁO DOANH THU')
        self.assertContains(response, 'revenueTrendChart')
        self.assertContains(response, 'topServicesChart')
        self.assertContains(response, 'membershipDoughnutChart')
        self.assertContains(response, 'healthFocusChart')
        self.assertContains(response, 'healthPressureChart')
        # Xác nhận đã bỏ phần ảnh 1, ảnh 2, bộ lọc ngày tùy chỉnh và SĐT/hạng thành viên ở cột Khách hàng
        self.assertNotContains(response, 'Dữ liệu tự động đồng bộ từ CSDL SQLite')
        self.assertNotContains(response, '<div class="dashboard-actions">')
        self.assertNotContains(response, 'id="btn-export-excel"')
        self.assertNotContains(response, 'id="filter-from-date"')
        self.assertNotContains(response, 'id="btn-apply-custom-date"')
        self.assertNotContains(response, 'id="period-display-label"')
        self.assertContains(response, 'Khách hàng Test')
        self.assertNotContains(response, '0909999003')
        self.assertNotContains(response, '<th class="text-center">Trạng thái</th>')
        self.assertNotContains(response, 'cảnh báo an toàn')
        self.assertContains(response, 'Huyết áp Cao/Thấp')

    def test_staff_dashboard_template_view(self):
        """Kiểm tra trang HTML Dashboard của Kỹ thuật viên render thành công."""
        self.client.force_login(self.staff_user)
        response = self.client.get('/dashboard/staff/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'BẢNG ĐIỀU KHIỂN CA TRỰC KỸ THUẬT VIÊN')
