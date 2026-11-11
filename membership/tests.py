"""
================================================================================
MODULE 06: QUẢN LÝ HỘI VIÊN & TÍCH ĐIỂM (MOD-06) - UNIT & INTEGRATION TESTS
Thành viên phụ trách: MINH KHÁNH
Mục đích:
  - Kiểm thử toàn diện 3 Use Cases của phân hệ:
    + UC-6.1: Thẻ hội viên điện tử & Tiến trình thăng hạng
    + UC-6.2: Tra cứu thông tin hội viên & Điều chỉnh điểm thủ công tại quầy
    + UC-6.3: Tự động tích điểm & thăng hạng qua Django Signal trên Invoice (10.000đ = 1 điểm)
================================================================================
"""

from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from core.models import (
    User,
    Tier,
    Membership,
    MembershipPoint,
    Appointment,
    Invoice,
    Notification,
    Voucher
)
from datetime import timedelta
from membership.signals import process_invoice_membership_points


class MembershipModuleTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Tạo 4 Hạng thẻ mẫu chuẩn Cham Spa (Đồng, Bạc, Vàng, Kim Cương)
        self.tier_member = Tier.objects.create(
            name="Hạng Đồng",
            min_points=0,
            discount_percent=0,
            description="Hạng khởi đầu cho khách hàng mới"
        )
        self.tier_silver = Tier.objects.create(
            name="Hạng Bạc",
            min_points=500,
            discount_percent=5,
            description="Giảm 5% dịch vụ"
        )
        self.tier_gold = Tier.objects.create(
            name="Hạng Vàng",
            min_points=1500,
            discount_percent=10,
            description="Giảm 10% dịch vụ"
        )
        self.tier_diamond = Tier.objects.create(
            name="Hạng Kim Cương",
            min_points=3000,
            discount_percent=15,
            description="Giảm 15% dịch vụ"
        )

        # 2. Tạo User Khách hàng demo
        self.customer = User.objects.create_user(
            username="0905123456",
            phone="0905123456",
            email="khanh_customer@chamspa.vn",
            name="Trần Minh Khánh",
            password="Password123!"
        )

        # 3. Tạo User Nhân viên demo
        self.staff_user = User.objects.create_user(
            username="0905999888",
            phone="0905999888",
            email="staff_khanh@chamspa.vn",
            name="Nhân viên Lễ Tân",
            password="Password123!",
            is_staff=True
        )

        # 4. Tạo User Quản trị demo
        self.admin_user = User.objects.create_user(
            username="0905777666",
            phone="0905777666",
            email="admin_khanh@chamspa.vn",
            name="Quản Trị Viên",
            password="Password123!",
            is_superuser=True,
            is_staff=True
        )

        # 5. Tạo / Cập nhật Thẻ hội viên ban đầu cho khách hàng
        self.membership, _ = Membership.objects.update_or_create(
            user=self.customer,
            defaults={
                'tier': self.tier_member,
                'current_points': 100,
                'total_points_used': 0,
                'total_spent': Decimal(1000000)
            }
        )

    # -------------------------------------------------------------------------
    # TEST USE CASE 6.1: XEM THẺ HỘI VIÊN & HỢP ĐỒNG API (TABLE VIII ROW 16)
    # -------------------------------------------------------------------------
    def test_uc61_customer_card_view(self):
        """Khách hàng đăng nhập có thể xem giao diện Thẻ hội viên cá nhân (200 OK)"""
        self.client.login(username="0905123456", password="Password123!")
        response = self.client.get(reverse('membership:my_card'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trần Minh Khánh")
        self.assertContains(response, "Hạng Đồng")

    def test_uc61_voucher_wallet_tab(self):
        """Trang Thẻ hội viên hiển thị đầy đủ tab Ví Voucher và danh sách voucher khả dụng"""
        Voucher.objects.create(
            voucher_code="CHAMTEST20",
            customer=self.customer,
            discount_type="PERCENT",
            discount_value=Decimal(20),
            min_order_amount=Decimal(300000),
            status="Khả dụng",
            expiry_date=timezone.now() + timedelta(days=30),
        )
        self.client.login(username="0905123456", password="Password123!")
        response = self.client.get(reverse('membership:my_card') + "?tab=vouchers")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ví Voucher")
        self.assertContains(response, "CHAMTEST20")

    def test_uc61_my_card_displays_tier_and_points(self):
        """Khách hàng xem thẻ hội viên HTML hiển thị đúng hạng thẻ & điểm hiện có"""
        self.client.login(username="0905123456", password="Password123!")
        response = self.client.get(reverse('membership:my_card'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hạng Đồng')
        self.assertContains(response, '100')

    def test_uc62_lookup_forbidden_for_customer(self):
        """Khách hàng thường gọi /membership/api/lookup/ phải bị chặn 403"""
        self.client.login(username="0905123456", password="Password123!")
        response = self.client.get(reverse('membership:api_lookup') + "?q=0905123456")
        self.assertEqual(response.status_code, 403)

    # -------------------------------------------------------------------------
    # TEST USE CASE 6.2: TRA CỨU HỘI VIÊN TẠI QUẦY & ĐIỀU CHỈNH ĐIỂM THỦ CÔNG
    # -------------------------------------------------------------------------
    def test_uc62_api_lookup_by_phone(self):
        """Nhân viên có thể tra cứu hội viên qua số điện thoại để lấy mức chiết khấu"""
        self.client.login(username="0905999888", password="Password123!")
        url = reverse('membership:api_lookup') + "?q=0905123456"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertTrue(data.get('count') >= 1)
        first_result = data['results'][0]
        self.assertEqual(first_result['customer_phone'], '0905123456')
        self.assertEqual(first_result['customer_name'], 'Trần Minh Khánh')

    def test_uc62_post_adjust_points_add(self):
        """Nhân viên có thể cộng điểm thưởng thủ công qua Form POST kèm lý do cụ thể"""
        self.client.login(username="0905999888", password="Password123!")
        url = reverse('membership:staff_lookup')
        payload = {
            "form_action": "adjust_points",
            "membership_id": self.membership.id,
            "adjust_action": "ADD",
            "points_amount": 150,
            "reason_description": "Tặng điểm sinh nhật khách hàng thân thiết"
        }
        response = self.client.post(url, data=payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cộng +150 điểm thưởng")

        # Kiểm tra bản ghi MembershipPoint được tạo
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.current_points, 250)
        latest_point = self.membership.point_history.first()
        self.assertEqual(latest_point.points_amount, 150)
        self.assertIn("Tặng điểm sinh nhật", latest_point.reason_description)

    def test_uc62_post_adjust_points_deduct_insufficient(self):
        """Trừ điểm vượt quá số dư hiện có không làm thay đổi điểm và hiển thị thông báo lỗi"""
        self.client.login(username="0905999888", password="Password123!")
        url = reverse('membership:staff_lookup')
        payload = {
            "form_action": "adjust_points",
            "membership_id": self.membership.id,
            "adjust_action": "DEDUCT",
            "points_amount": 9999,  # Vượt quá số dư 100
            "reason_description": "Khấu trừ điểm đổi quà"
        }
        response = self.client.post(url, data=payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "không đủ để trừ 9999 điểm")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.current_points, 100)

    def test_uc62_post_update_tier_and_customer_forbidden(self):
        """Nhân viên đổi hạng thẻ thành công qua Form POST; khách hàng bị chặn 403"""
        url = reverse('membership:staff_lookup')
        self.client.login(username="0905123456", password="Password123!")
        resp_cust = self.client.post(url, {
            "form_action": "update_tier",
            "membership_id": self.membership.id,
            "tier_id": self.tier_gold.id,
        })
        self.assertEqual(resp_cust.status_code, 403)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.tier, self.tier_member)

        self.client.login(username="0905999888", password="Password123!")
        resp_staff = self.client.post(url, {
            "form_action": "update_tier",
            "membership_id": self.membership.id,
            "tier_id": self.tier_gold.id,
            "reason_description": "Khách VIP lâu năm",
        }, follow=True)
        self.assertEqual(resp_staff.status_code, 200)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.tier, self.tier_gold)

    # -------------------------------------------------------------------------
    # TEST USE CASE 6.3: TỰ ĐỘNG TÍCH ĐIỂM QUA INVOICE SIGNAL (10.000Đ = 1 ĐIỂM)
    # -------------------------------------------------------------------------
    def test_uc63_auto_earn_points_on_invoice_paid(self):
        """
        Khi Invoice chuyển sang 'Đã thanh toán', Django Signal tự động tính điểm
        (10.000 VNĐ = 1 điểm), cộng điểm, cộng total_spent và nâng hạng thẻ.
        """
        # Tạo lịch hẹn gắn với khách hàng
        appointment = Appointment.objects.create(
            appointment_code="AP-TEST-001",
            user=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=timezone.now().date(),
            time_slot="14:00",
            total_guests=1,
            total_price=Decimal(5000000),  # 5.000.000 VNĐ -> 500 điểm
            status="In_Progress"
        )

        # Tạo hóa đơn với trạng thái ban đầu 'Chờ xác nhận'
        invoice = Invoice.objects.create(
            appointment=appointment,
            amount=Decimal(5000000),
            status="Chờ xác nhận"
        )

        initial_points = self.membership.current_points  # 100

        # Cập nhật hóa đơn thành 'Đã thanh toán' -> Kích hoạt Signal post_save
        invoice.status = "Đã thanh toán"
        invoice.paid_at = timezone.now()
        invoice.save()

        # Kiểm tra kết quả tích điểm tự động
        self.membership.refresh_from_db()
        expected_points = initial_points + (5000000 // 10000)  # 100 + 500 = 600
        self.assertEqual(self.membership.current_points, expected_points)
        self.assertEqual(self.membership.total_spent, Decimal(6000000))

        # Kiểm tra thăng hạng thẻ tự động (600 điểm >= 500 điểm -> Hạng Bạc)
        self.assertEqual(self.membership.tier.name, "Hạng Bạc")

        # Kiểm tra bản ghi MembershipPoint
        point_record = MembershipPoint.objects.filter(
            membership=self.membership,
            appointment_id="AP-TEST-001"
        ).first()
        self.assertIsNotNone(point_record)
        self.assertEqual(point_record.points_amount, 500)

        # Kiểm tra thông báo Notification được tạo
        notifs = Notification.objects.filter(user=self.customer)
        self.assertTrue(notifs.exists())

    def test_uc63_idempotency_prevents_duplicate_points(self):
        """Lưu Invoice nhiều lần ở trạng thái 'Đã thanh toán' không được cộng điểm trùng lặp"""
        appointment = Appointment.objects.create(
            appointment_code="AP-TEST-DUP",
            user=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=timezone.now().date(),
            time_slot="16:00",
            total_guests=1,
            total_price=Decimal(1000000),
            status="In_Progress"
        )
        invoice = Invoice.objects.create(
            appointment=appointment,
            amount=Decimal(1000000),
            status="Chờ xác nhận"
        )

        # Lần 1: Thanh toán thành công (+100 điểm)
        invoice.status = "Đã thanh toán"
        invoice.save()
        self.membership.refresh_from_db()
        pts_after_first = self.membership.current_points

        # Lần 2: Save lại Invoice mà không đổi trạng thái
        invoice.reason_refuse = "Test note"
        invoice.save()
        self.membership.refresh_from_db()

        # Điểm không được tăng lần 2!
        self.assertEqual(self.membership.current_points, pts_after_first)
