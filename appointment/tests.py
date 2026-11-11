"""
================================================================================
MODULE 01: QUẢN LÝ LỊCH HẸN (MOD-01) - COMPREHENSIVE INTEGRATION TESTS
Tác giả: Nhật Quang (Leader)
Kiểm thử toàn diện tính đồng bộ giữa Module 01 với toàn bộ hệ thống CHAMSPA CRM:
  - Module 02: Dịch vụ (Services)
  - Module 03: Hồ sơ sức khỏe (Health Profiles)
  - Module 05: Tài khoản khách hàng & nhân viên (Accounts)
  - Module 06: Hội viên & Tích điểm (Membership & Loyalty)
  - Module 07: Đánh giá & Khiếu nại (Feedbacks & Complaints)
  - Module 08: Khuyến mãi, Voucher & Thông báo (Marketing & Notifications)
  - Module 09: Hóa đơn & Thanh toán (Invoices & Payments)
  - Module 10: Báo cáo & Dashboard (Dashboard & Reports)
================================================================================
"""

from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse

from core.models import (
    User,
    Tier,
    Membership,
    MembershipPoint,
    UserHealthProfile,
    Category,
    Service,
    Voucher,
    Appointment,
    AppointmentDetail,
    Invoice,
    Notification,
    Feedback
)


class AppointmentIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Khởi tạo Hạng thẻ chuẩn Cham Spa
        self.tier_member = Tier.objects.create(
            name="Thành viên",
            min_points=0,
            discount_percent=0,
            description="Hạng khởi đầu"
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

        # 2. Khởi tạo Danh mục & Dịch vụ Spa (Module 02)
        self.category = Category.objects.create(
            name="Massage Trị Liệu",
            slug="massage-tri-lieu",
            status="Hoạt động"
        )
        self.service1 = Service.objects.create(
            category=self.category,
            name="Massage Body Trị Liệu Vai Gáy",
            slug="massage-body-tri-lieu-vai-gay",
            price_vnd=Decimal('550000.00'),
            duration_minutes=60,
            rating_avg=Decimal('4.9'),
            status="Hoạt động"
        )
        self.service2 = Service.objects.create(
            category=self.category,
            name="Gội Đầu Dưỡng Sinh Thảo Mộc",
            slug="goi-dau-duong-sinh-thao-moc",
            price_vnd=Decimal('450000.00'),
            duration_minutes=45,
            rating_avg=Decimal('4.8'),
            status="Hoạt động"
        )

        # 3. Khởi tạo Khách hàng & Hồ sơ sức khỏe (Module 03 & 05)
        self.customer = User.objects.create_user(
            username="0901234567",
            phone="0901234567",
            email="quang_cust@chamspa.vn",
            name="Nguyễn Nhật Quang",
            password="Password123!"
        )
        self.membership, _ = Membership.objects.update_or_create(
            user=self.customer,
            defaults={
                'tier': self.tier_member,
                'current_points': 50,
                'total_points_used': 0,
                'total_spent': Decimal('500000.00')
            }
        )
        self.health_profile, _ = UserHealthProfile.objects.update_or_create(
            user=self.customer,
            defaults={
                'health_code': "HP-KH0001",
                'blood_pressure': "120/80",
                'focus_areas': ["Cổ vai gáy", "Thắt lưng"],
                'massage_pressure': "Vừa",
                'pain_level': 4
            }
        )

        # 4. Khởi tạo Nhân viên Lễ tân & Quản trị viên (Module 05)
        self.staff_user = User.objects.create_user(
            username="0909888999",
            phone="0909888999",
            email="staff@chamspa.vn",
            name="Lễ Tân Thanh Thảo",
            password="Password123!",
            is_staff=True
        )
        self.admin_user = User.objects.create_user(
            username="0909777888",
            phone="0909777888",
            email="admin@chamspa.vn",
            name="Quản Trị Viên",
            password="Password123!",
            is_staff=True,
            is_superuser=True
        )

        # 5. Khởi tạo Voucher khuyến mãi (Module 08)
        self.voucher_general = Voucher.objects.create(
            voucher_code="CHARMSPA10",
            discount_type="PERCENT",
            discount_value=Decimal('10.00'),
            min_order_amount=Decimal('500000.00'),
            max_discount_amount=Decimal('100000.00'),
            status="Khả dụng",
            expiry_date=timezone.now() + timedelta(days=30)
        )
        self.voucher_personal = Voucher.objects.create(
            voucher_code="VIPCARE100",
            customer=self.customer,
            discount_type="FIXED",
            discount_value=Decimal('100000.00'),
            min_order_amount=Decimal('300000.00'),
            status="Khả dụng",
            expiry_date=timezone.now() + timedelta(days=30)
        )

    def test_01_online_booking_and_invoice_sync(self):
        """
        Kiểm thử quy trình đặt lịch trực tuyến (UC-1.1):
        - Bắt buộc đăng nhập
        - Tính giá dịch vụ, áp dụng voucher
        - Đồng bộ tạo Hóa đơn (Module 09) trạng thái 'Chờ xác nhận'
        - Trả về mã VietQR
        """
        self.client.force_login(self.customer)
        target_date = (timezone.now() + timedelta(days=2)).date().strftime('%Y-%m-%d')

        payload = {
            'appointment_date': target_date,
            'time_slot': '14:00',
            'total_guests': 2,
            'male_guests': 1,
            'female_guests': 1,
            'customer_name': self.customer.name,
            'customer_phone': self.customer.phone,
            'service_id': self.service1.id,
            'voucher_code': 'CHARMSPA10',
            'guests': [
                {'guest_index': 1, 'gender': 'Nam', 'service_id': self.service1.id, 'massage_pressure': 'Vừa'},
                {'guest_index': 2, 'gender': 'Nữ', 'service_id': self.service2.id, 'massage_pressure': 'Nhẹ'}
            ]
        }

        res = self.client.post(reverse('appointment:api_create'), payload, content_type='application/json')
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['appointment_code'].startswith('#LH'))

        # Tổng tiền gốc = 550k + 450k = 1.000k. Giảm 10% = 100k -> Tổng = 900.000đ
        self.assertEqual(data['total_price'], 900000.0)
        self.assertEqual(data['discount_amount'], 100000.0)

        # Kiểm tra CSDL Appointment & Invoice đồng bộ
        appt = Appointment.objects.get(id=data['appointment_id'])
        self.assertEqual(appt.user, self.customer)
        self.assertEqual(appt.status, 'Hold')
        self.assertEqual(appt.details.count(), 2)

        # Kiểm tra Hóa đơn (Module 09) được tạo tự động 1-1
        self.assertTrue(hasattr(appt, 'invoice'))
        self.assertEqual(appt.invoice.amount, Decimal('900000.00'))
        self.assertEqual(appt.invoice.status, 'Chờ xác nhận')
        self.assertIn('VietQR', appt.invoice.reason_refuse)

    def test_02_confirm_payment_syncs_invoice_and_voucher(self):
        """
        Kiểm thử xác nhận thanh toán VietQR (ConfirmPaymentAPI):
        - Chuyển trạng thái lịch hẹn sang 'Confirmed'
        - Chuyển Invoice sang 'Đã thanh toán' (Module 09)
        - Đánh dấu voucher cá nhân sang 'Đã dùng' (Module 08)
        - Gửi thông báo đến tài khoản khách hàng
        """
        appt = Appointment.objects.create(
            appointment_code="#LH77701",
            user=self.customer,
            voucher=self.voucher_personal,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=timezone.now().date(),
            time_slot="10:00",
            total_guests=1,
            total_price=Decimal('450000.00'),
            status="Hold"
        )
        Invoice.objects.create(
            appointment=appt,
            amount=Decimal('450000.00'),
            status="Chờ xác nhận"
        )

        self.client.force_login(self.customer)
        res = self.client.post(reverse('appointment:api_confirm_payment', kwargs={'pk': appt.id}))
        self.assertEqual(res.status_code, 200)

        appt.refresh_from_db()
        self.assertEqual(appt.status, 'Confirmed')

        # Hóa đơn đồng bộ 'Đã thanh toán'
        appt.invoice.refresh_from_db()
        self.assertEqual(appt.invoice.status, 'Đã thanh toán')
        self.assertIsNotNone(appt.invoice.paid_at)

        # Voucher cá nhân được cập nhật 'Đã dùng'
        self.voucher_personal.refresh_from_db()
        self.assertEqual(self.voucher_personal.status, 'Đã dùng')
        self.assertIsNotNone(self.voucher_personal.used_at)

        # Kiểm tra thông báo được gửi
        notif = Notification.objects.filter(user=self.customer, title="Lịch hẹn đã được xác nhận!").first()
        self.assertIsNotNone(notif)

    def test_03_completed_appointment_triggers_loyalty_points_and_tier_upgrade(self):
        """
        Kiểm thử hoàn thành lịch hẹn kích hoạt tích điểm và nâng hạng tự động (Module 01 -> 09 -> 06):
        - Đơn hàng 5.000.000 VNĐ -> Tích 500 điểm thưởng (10.000đ = 1 điểm)
        - Điểm tích lũy chạm mốc 500đ -> Tự động thăng hạng lên 'Hạng Bạc'
        - Ghi nhận MembershipPoint và thông báo chúc mừng thăng hạng
        """
        self.client.force_login(self.admin_user)
        appt = Appointment.objects.create(
            appointment_code="#LH77702",
            user=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=timezone.now().date(),
            time_slot="14:00",
            total_guests=1,
            total_price=Decimal('5000000.00'),
            status="Confirmed"
        )
        Invoice.objects.create(
            appointment=appt,
            amount=Decimal('5000000.00'),
            status="Chờ xác nhận"
        )

        initial_points = self.membership.current_points  # 50 điểm

        # Chuyển trạng thái sang Completed qua API Quản trị
        res = self.client.post(
            reverse('appointment:api_admin_appointment_status', kwargs={'pk': appt.id}),
            {'status': 'Completed'},
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['updated_status'], 'Completed')

        # 1. Hóa đơn chuyển 'Đã thanh toán' (Module 09)
        appt.invoice.refresh_from_db()
        self.assertEqual(appt.invoice.status, 'Đã thanh toán')

        # 2. Điểm thưởng và thăng hạng thành viên (Module 06)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.current_points, initial_points + 500)
        self.assertEqual(self.membership.tier.name, "Hạng Bạc")

        # 3. Ghi nhận giao dịch lịch sử điểm MembershipPoint
        pt = MembershipPoint.objects.filter(membership=self.membership, appointment_id="#LH77702").first()
        self.assertIsNotNone(pt)
        self.assertEqual(pt.points_amount, 500)

    def test_04_desk_quick_create_auto_links_registered_member_and_health_profile(self):
        """
        Kiểm thử tiếp nhận lịch hẹn tại quầy (StaffQuickCreateAppointmentAPI):
        - Nhân viên nhập số điện thoại khách hàng '0901234567'
        - Hệ thống tự động nhận diện thành viên 'Nguyễn Nhật Quang' và gán user
        - Serializer trả về đầy đủ Hạng thẻ hội viên và Hồ sơ sức khỏe
        """
        self.client.force_login(self.staff_user)
        payload = {
            'customer_name': 'Anh Quang Khách Quen',
            'customer_phone': '0901234567',
            'customer_email': 'quang_desk@chamspa.vn',
            'appointment_date': (timezone.localdate() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'time_slot': '16:00',
            'service_id': self.service1.id,
            'total_guests': 1,
            'male_guests': 1,
            'female_guests': 0,
            'note': 'Khách yêu cầu KTV tay nghề cao',
            'status': 'Confirmed'
        }

        res = self.client.post(reverse('appointment:api_staff_quick_create'), payload, content_type='application/json')
        self.assertEqual(res.status_code, 201)
        data = res.json()

        appt_id = data['appointment']['id']
        appt = Appointment.objects.get(id=appt_id)

        # Tự động gán user = self.customer
        self.assertEqual(appt.user, self.customer)

        # Kiểm tra Hóa đơn tự động sinh tại quầy
        self.assertTrue(hasattr(appt, 'invoice'))
        self.assertEqual(appt.invoice.reason_refuse, 'Tại quầy (Tiền mặt/POS)')

        # Kiểm tra dữ liệu user trong serializer
        user_info = data['appointment']['user']
        self.assertIsNotNone(user_info)
        self.assertEqual(user_info['membership_tier'], 'Thành viên')
        self.assertTrue(user_info['has_health_profile'])
        self.assertEqual(user_info['health_code'], 'HP-KH0001')
        self.assertEqual(user_info['blood_pressure'], '120/80')

    def test_05_feedback_integration_allowed_only_when_completed(self):
        """
        Kiểm thử tích hợp Module 07 (Đánh giá & Khiếu nại):
        - Lịch hẹn chưa hoàn thành -> Không được gửi đánh giá
        - Lịch hẹn đã hoàn thành -> Gửi đánh giá 5 sao thành công
        """
        appt = Appointment.objects.create(
            appointment_code="#LH77703",
            user=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=timezone.now().date(),
            time_slot="10:00",
            total_guests=1,
            total_price=Decimal('550000.00'),
            status="Confirmed"
        )

        self.client.force_login(self.customer)

        # 1. Thử gửi đánh giá khi đơn chưa hoàn thành -> Phải bị từ chối
        fb_url = reverse('feedbacks:customer_tracking')
        fb_payload = {
            'action': 'submit_feedback',
            'appointment_id': appt.id,
            'rating': 5,
            'comment': 'Dịch vụ rất tốt!'
        }
        res_fail = self.client.post(fb_url, fb_payload)
        self.assertEqual(res_fail.status_code, 302)
        self.assertFalse(Feedback.objects.filter(appointment=appt).exists())

        # 2. Hoàn thành lịch hẹn
        appt.status = 'Completed'
        appt.save()

        # 3. Gửi đánh giá sau khi hoàn thành -> Thành công
        res_ok = self.client.post(fb_url, fb_payload)
        self.assertEqual(res_ok.status_code, 302)
        self.assertTrue(Feedback.objects.filter(appointment=appt).exists())

    def test_06_cancellation_restores_voucher_and_invalidates_invoice(self):
        """
        Kiểm thử hủy lịch hẹn (CancelAPI):
        - Chuyển trạng thái Appointment sang 'Cancelled'
        - Chuyển Invoice sang 'Không hợp lệ'
        - Khôi phục voucher đã dùng nếu có
        - Gửi thông báo hoàn tiền cọc
        """
        self.voucher_personal.status = 'Đã dùng'
        self.voucher_personal.used_at = timezone.now()
        self.voucher_personal.save()

        appt = Appointment.objects.create(
            appointment_code="#LH77704",
            user=self.customer,
            voucher=self.voucher_personal,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=timezone.now().date() + timedelta(days=1),
            time_slot="15:00",
            total_guests=1,
            total_price=Decimal('450000.00'),
            status="Confirmed"
        )
        inv = Invoice.objects.create(
            appointment=appt,
            amount=Decimal('450000.00'),
            status="Chờ xác nhận"
        )

        self.client.force_login(self.customer)
        cancel_payload = {
            'cancel_reason': 'Bận việc gia đình đột xuất',
            'refund_account_number': '1903666888',
            'bank_name': 'Techcombank',
            'account_holder': 'NGUYEN NHAT QUANG'
        }

        res = self.client.post(reverse('appointment:api_cancel', kwargs={'pk': appt.id}), cancel_payload, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        appt.refresh_from_db()
        self.assertEqual(appt.status, 'Cancelled')
        self.assertIn('Techcombank', appt.refund_account_number)

        # Hóa đơn chuyển 'Không hợp lệ'
        inv.refresh_from_db()
        self.assertEqual(inv.status, 'Không hợp lệ')

        # Voucher được hoàn trả 'Khả dụng'
        self.voucher_personal.refresh_from_db()
        self.assertEqual(self.voucher_personal.status, 'Khả dụng')
        self.assertIsNone(self.voucher_personal.used_at)

    def test_07_confirm_status_updates_payment_to_bank_transfer(self):
        """
        Kiểm thử bấm nút Xác nhận ở bảng quản lý (AdminAppointmentListAPI -> 'Confirmed'):
        - Trạng thái lịch hẹn chuyển sang 'Confirmed'
        - Hóa đơn chuyển sang 'Đã thanh toán' với phương thức 'Chuyển khoản VietQR'
        - API chi tiết lịch hẹn trả về payment.status_label == 'Đã chuyển khoản'
        - Khi Hoàn thành sau đó không cộng trùng điểm thưởng
        """
        self.client.force_login(self.staff_user)
        appt = Appointment.objects.create(
            appointment_code="#LH88379",
            user=self.customer,
            voucher=self.voucher_personal,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=timezone.now().date(),
            time_slot="16:00",
            total_guests=1,
            total_price=Decimal('550000.00'),
            status="Hold"
        )
        inv = Invoice.objects.create(
            appointment=appt,
            amount=Decimal('550000.00'),
            status="Chờ xác nhận",
            reason_refuse="Tại quầy (Tiền mặt/POS)"
        )

        initial_points = self.membership.current_points  # 50 điểm

        # 1. Bấm nút Xác nhận từ bảng ngoài -> gọi api_admin_appointment_status với status='Confirmed'
        res = self.client.post(
            reverse('appointment:api_admin_appointment_status', kwargs={'pk': appt.id}),
            {'status': 'Confirmed'},
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['updated_status'], 'Confirmed')
        self.assertEqual(data['payment']['method'], 'transfer')
        self.assertTrue(data['payment']['is_paid'])
        self.assertEqual(data['payment']['status_label'], 'Đã chuyển khoản')

        # Kiểm tra DB đồng bộ
        appt.refresh_from_db()
        inv.refresh_from_db()
        self.voucher_personal.refresh_from_db()
        self.assertEqual(appt.status, 'Confirmed')
        self.assertEqual(inv.status, 'Đã thanh toán')
        self.assertEqual(inv.reason_refuse, 'Chuyển khoản VietQR')
        self.assertIsNotNone(inv.paid_at)
        self.assertEqual(self.voucher_personal.status, 'Đã dùng')

        # 2. Mở xem chi tiết lịch hẹn -> payment hiển thị 'Đã chuyển khoản'
        detail_res = self.client.get(reverse('appointment:api_detail', kwargs={'identifier': appt.id}))
        self.assertEqual(detail_res.status_code, 200)
        detail_data = detail_res.json()
        self.assertEqual(detail_data['payment']['status_label'], 'Đã chuyển khoản')
        self.assertEqual(detail_data['payment']['method_label'], 'Chuyển khoản (VietQR)')
        self.assertTrue(detail_data['payment']['is_paid'])

        # 3. Sau đó bấm Hoàn thành -> không cộng trùng điểm thưởng (550.000đ = 55 điểm chỉ cộng 1 lần)
        self.client.post(
            reverse('appointment:api_admin_appointment_status', kwargs={'pk': appt.id}),
            {'status': 'Completed'},
            content_type='application/json'
        )
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.current_points, initial_points + 55)

    def test_08_reject_past_appointment_date_and_allow_today(self):
        """
        Kiểm thử quy tắc đặt lịch & đổi lịch theo đúng ngày và giờ thực:
        - AvailableSlotsAPI: đánh dấu các khung giờ <= giờ hiện tại hôm nay là is_available=False, is_past=True, status_label='Đã qua'
        - Đặt lịch trực tuyến (AppointmentCreateAPI): từ chối ngày hôm qua (400), từ chối giờ đã qua trong hôm nay (400), cho phép giờ tương lai hôm nay (201)
        - Đặt lịch tại quầy (StaffQuickCreateAppointmentAPI): từ chối ngày hôm qua (400), từ chối giờ đã qua trong hôm nay (400), cho phép giờ tương lai hôm nay (201)
        - Đổi lịch (RescheduleAPI): từ chối ngày/giờ đã qua trong hôm nay (400), cho phép giờ tương lai hôm nay (200)
        - Giao diện booking_view, admin_appointments_view, staff_appointments_view hiển thị biến giờ thực now_time_str & khóa ngày/giờ quá khứ
        """
        from unittest.mock import patch

        real_localtime = timezone.localtime
        mock_now = real_localtime().replace(hour=11, minute=25, second=0, microsecond=0)

        def fake_localtime(value=None, timezone=None):
            if value is None:
                return mock_now
            return real_localtime(value, timezone)

        today = mock_now.date()
        yesterday_str = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        today_str = today.strftime('%Y-%m-%d')

        with patch('django.utils.timezone.localtime', side_effect=fake_localtime):
            # 0. Kiểm tra API khung giờ hôm nay theo giờ thực (11:25)
            slots_res = self.client.get(reverse('appointment:api_available_slots'), {'date': today_str})
            self.assertEqual(slots_res.status_code, 200)
            slots_data = slots_res.json()
            self.assertEqual(slots_data.get('server_now'), f"{today_str} 11:25")
            slots_by_time = {s['slot']: s for s in slots_data['slots']}
            self.assertFalse(slots_by_time['09:00']['is_available'])
            self.assertTrue(slots_by_time['09:00']['is_past'])
            self.assertEqual(slots_by_time['09:00']['status_label'], 'Đã qua')
            self.assertFalse(slots_by_time['10:30']['is_available'])
            self.assertTrue(slots_by_time['10:30']['is_past'])
            self.assertTrue(slots_by_time['14:00']['is_available'])
            self.assertFalse(slots_by_time['14:00']['is_past'])

            # 1. Online booking (Customer)
            self.client.force_login(self.customer)
            online_payload = {
                'appointment_date': yesterday_str,
                'time_slot': '14:00',
                'total_guests': 1,
                'male_guests': 1,
                'female_guests': 0,
                'customer_name': self.customer.name,
                'customer_phone': self.customer.phone,
                'service_id': self.service1.id,
            }
            res_past = self.client.post(reverse('appointment:api_create'), online_payload, content_type='application/json')
            self.assertEqual(res_past.status_code, 400)
            self.assertIn('appointment_date', res_past.json()['error'])

            online_payload['appointment_date'] = today_str
            online_payload['time_slot'] = '10:30'
            res_past_slot = self.client.post(reverse('appointment:api_create'), online_payload, content_type='application/json')
            self.assertEqual(res_past_slot.status_code, 400)
            self.assertIn('time_slot', res_past_slot.json()['error'])

            online_payload['time_slot'] = '14:00'
            res_today = self.client.post(reverse('appointment:api_create'), online_payload, content_type='application/json')
            self.assertEqual(res_today.status_code, 201)
            created_apt_id = res_today.json()['id']

            # Đổi lịch (RescheduleAPI): từ chối giờ đã qua trong hôm nay, cho phép giờ tương lai
            res_resched_past = self.client.post(
                reverse('appointment:api_reschedule', kwargs={'pk': created_apt_id}),
                {'appointment_date': today_str, 'time_slot': '10:30'},
                content_type='application/json',
            )
            self.assertEqual(res_resched_past.status_code, 400)

            res_resched_ok = self.client.post(
                reverse('appointment:api_reschedule', kwargs={'pk': created_apt_id}),
                {'appointment_date': today_str, 'time_slot': '15:00'},
                content_type='application/json',
            )
            self.assertEqual(res_resched_ok.status_code, 200)

            # Kiểm tra trang đặt lịch mặc định từ hôm nay, khóa ngày < today và nhận giờ thực
            booking_page = self.client.get(reverse('appointment:booking'))
            self.assertEqual(booking_page.status_code, 200)
            booking_html = booking_page.content.decode('utf-8')
            self.assertIn('if (thisDate < today)', booking_html)
            self.assertNotIn('new Date(2026, 9, 16)', booking_html)
            self.assertIn('11:25', booking_html)

            # 2. Desk quick-create (Staff) & giao diện quản lý Staff/Admin
            self.client.force_login(self.staff_user)
            desk_payload = {
                'customer_name': 'Khách tại quầy',
                'customer_phone': '0911222333',
                'appointment_date': yesterday_str,
                'time_slot': '15:00',
                'service_id': self.service1.id,
                'total_guests': 1,
                'male_guests': 0,
                'female_guests': 1,
                'status': 'Confirmed',
            }
            res_desk_past = self.client.post(reverse('appointment:api_staff_quick_create'), desk_payload, content_type='application/json')
            self.assertEqual(res_desk_past.status_code, 400)
            self.assertIn('appointment_date', res_desk_past.json()['error'])

            desk_payload['appointment_date'] = today_str
            desk_payload['time_slot'] = '09:00'
            res_desk_past_slot = self.client.post(reverse('appointment:api_staff_quick_create'), desk_payload, content_type='application/json')
            self.assertEqual(res_desk_past_slot.status_code, 400)
            self.assertIn('time_slot', res_desk_past_slot.json()['error'])

            desk_payload['time_slot'] = '15:00'
            res_desk_today = self.client.post(reverse('appointment:api_staff_quick_create'), desk_payload, content_type='application/json')
            self.assertEqual(res_desk_today.status_code, 201)

            staff_page = self.client.get(reverse('appointment:staff_appointments'))
            self.assertEqual(staff_page.status_code, 200)
            staff_html = staff_page.content.decode('utf-8')
            self.assertIn('syncQuickCreateTimeSlots', staff_html)
            self.assertIn('11:25', staff_html)

            self.client.force_login(self.admin_user)
            admin_page = self.client.get(reverse('appointment:admin_appointments'))
            self.assertEqual(admin_page.status_code, 200)
            admin_html = admin_page.content.decode('utf-8')
            self.assertIn('syncQuickCreateTimeSlots', admin_html)
            self.assertIn('11:25', admin_html)

    def test_09_appointment_idor_and_payment_protection(self):
        """Khách hàng khác hoặc người lạ không được xem chi tiết, xác nhận thanh toán hoặc ép is_paid trên lịch hẹn người khác."""
        other_customer = User.objects.create_user(
            username="0901999888",
            phone="0901999888",
            email="other_cust@chamspa.vn",
            name="Khách Hàng Khác",
            password="Password123!",
        )
        appt = Appointment.objects.create(
            appointment_code="#LH99111",
            user=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=timezone.localdate() + timedelta(days=1),
            time_slot="14:00",
            total_guests=1,
            total_price=Decimal('550000.00'),
            status="Hold",
        )
        Invoice.objects.create(
            appointment=appt,
            amount=Decimal('550000.00'),
            status="Chờ xác nhận",
        )

        # 1. Anonymous user bị chặn 403 trên chi tiết, xác nhận thanh toán và cập nhật thanh toán
        self.client.logout()
        self.assertEqual(self.client.get(reverse('appointment:api_detail', kwargs={'identifier': appt.id})).status_code, 403)
        self.assertEqual(self.client.post(reverse('appointment:api_confirm_payment', kwargs={'pk': appt.id})).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse('appointment:api_update_payment', kwargs={'pk': appt.id}),
                {'payment_method': 'counter'},
                content_type='application/json',
            ).status_code,
            403,
        )

        # 2. Khách hàng khác bị chặn 403
        self.client.force_login(other_customer)
        self.assertEqual(self.client.get(reverse('appointment:api_detail', kwargs={'identifier': appt.id})).status_code, 403)
        self.assertEqual(self.client.post(reverse('appointment:api_confirm_payment', kwargs={'pk': appt.id})).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse('appointment:api_update_payment', kwargs={'pk': appt.id}),
                {'is_paid': True},
                content_type='application/json',
            ).status_code,
            403,
        )

        # 3. Chính chủ được phép chọn tới quầy trả tiền nhưng bị chặn 403 nếu tự gửi is_paid=True
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('appointment:api_detail', kwargs={'identifier': appt.id})).status_code, 200)
        res_counter = self.client.post(
            reverse('appointment:api_update_payment', kwargs={'pk': appt.id}),
            {'payment_method': 'counter'},
            content_type='application/json',
        )
        self.assertEqual(res_counter.status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse('appointment:api_update_payment', kwargs={'pk': appt.id}),
                {'is_paid': True},
                content_type='application/json',
            ).status_code,
            403,
        )

        # 4. Staff được phép xem chi tiết và cập nhật is_paid=True
        self.client.force_login(self.staff_user)
        res_staff_paid = self.client.post(
            reverse('appointment:api_update_payment', kwargs={'pk': appt.id}),
            {'payment_method': 'counter', 'is_paid': True},
            content_type='application/json',
        )
        self.assertEqual(res_staff_paid.status_code, 200)
        appt.invoice.refresh_from_db()
        self.assertEqual(appt.invoice.status, 'Đã thanh toán')

    def test_10_admin_and_staff_appointments_default_no_date_selected(self):
        """Mở trang quản lý lịch hẹn mặc định không chọn sẵn ngày và hiển thị toàn bộ lịch hẹn."""
        today = timezone.localdate()
        future_date = today + timedelta(days=2)

        Appointment.objects.create(
            appointment_code="#LH99112",
            user=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=today,
            time_slot="14:00",
            total_guests=1,
            total_price=Decimal('420000'),
            status="Pending",
        )
        Appointment.objects.create(
            appointment_code="#LH99113",
            user=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            appointment_date=future_date,
            time_slot="16:00",
            total_guests=1,
            total_price=Decimal('420000'),
            status="Confirmed",
        )

        for user, url_name in [
            (self.admin_user, 'appointment:admin_appointments'),
            (self.staff_user, 'appointment:staff_appointments'),
        ]:
            self.client.force_login(user)
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.context['selected_date'], '')
            self.assertEqual(resp.context['selected_date_display'], 'Tất cả các ngày')
            html = resp.content.decode('utf-8')
            self.assertIn('#LH99112', html)
            self.assertIn('#LH99113', html)
            self.assertRegex(html, r'<input[^>]*id="filterDateInput"[^>]*value=""')

            filtered = self.client.get(reverse(url_name), {'date': future_date.strftime('%Y-%m-%d')})
            self.assertEqual(filtered.status_code, 200)
            self.assertEqual(filtered.context['selected_date'], future_date.strftime('%Y-%m-%d'))
            filtered_html = filtered.content.decode('utf-8')
            self.assertIn('#LH99113', filtered_html)
            self.assertNotIn('#LH99112', filtered_html)


