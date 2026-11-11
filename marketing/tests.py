"""
================================================================================
MODULE 07: QUẢN LÝ THÔNG BÁO & KHUYẾN MÃI (MOD-07) - AUTOMATED TESTS
Thành viên phụ trách: MINH KHA
Mục đích:
  - Kiểm thử tự động (Unit Test / Integration Test) toàn diện cho Module 7:
    + UC-7.1: API Dropdown thông báo tại quả chuông và Timeline thông báo.
    + UC-7.2: Trang Ưu đãi & Kho Voucher (Card gradient, nút copy).
    + UC-7.3: Soạn và phát thông báo hàng loạt (bulk_create).
    + UC-7.4: Hợp đồng API 17 (Tạo Voucher linh hoạt % có trần hoặc tiền mặt).
    + UC-7.5: Hàm helper create_system_notification() dùng chung toàn Spa.
================================================================================
"""

from pathlib import Path
from decimal import Decimal
from django.conf import settings
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from core.models import User, Promotion, Voucher, Notification
from marketing.utils import create_system_notification, create_unique_notification


class MarketingModuleTestCase(TestCase):
    def setUp(self):
        """Khởi tạo môi trường kiểm thử với các tài khoản Admin, Staff, Customer"""
        self.client = Client()

        # 1. Tạo tài khoản Admin (Quản trị viên)
        self.admin = User.objects.create_superuser(
            username='admin_kha',
            phone='0905999001',
            email='admin_kha@chamspa.vn',
            name='Minh Kha Admin',
            password='TestPassword123!'
        )

        # 2. Tạo tài khoản Staff (Kỹ thuật viên / CSKH)
        self.staff = User.objects.create_user(
            username='staff_thao',
            phone='0905999002',
            email='staff_thao@chamspa.vn',
            name='Thanh Thảo KTV',
            is_staff=True,
            password='TestPassword123!'
        )

        # 3. Tạo tài khoản Customer (Khách hàng thân thiết)
        self.customer = User.objects.create_user(
            username='customer_quang',
            phone='0905999003',
            email='customer_quang@gmail.com',
            name='Lê Nhật Quang',
            password='TestPassword123!'
        )

        # 4. Tạo chương trình khuyến mãi mẫu
        self.promo = Promotion.objects.create(
            promotion_code='CHAMTEST2026',
            title='Đón Xuân An Yên - Giảm 20% Dịch Vụ',
            conditions_desc='Áp dụng từ thứ 2 đến thứ 6 cho dịch vụ Massage Body',
            status='Đang hoạt động',
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=30)
        )

        # 5. Tạo mã Voucher mẫu (% có trần)
        self.voucher_percent = Voucher.objects.create(
            voucher_code='CHAMSPA20',
            promotion=self.promo,
            discount_type='PERCENT',
            discount_value=Decimal('20.00'),
            max_discount_amount=Decimal('150000.00'),
            min_order_amount=Decimal('500000.00'),
            status='Khả dụng',
            expiry_date=timezone.now() + timedelta(days=30)
        )

        # 6. Tạo mã Voucher mẫu (Tiền mặt cố định)
        self.voucher_fixed = Voucher.objects.create(
            voucher_code='CHAM100K',
            promotion=self.promo,
            discount_type='FIXED',
            discount_value=Decimal('100000.00'),
            min_order_amount=Decimal('400000.00'),
            status='Khả dụng',
            expiry_date=timezone.now() + timedelta(days=30)
        )

    def test_uc_7_5_create_system_notification_helper_single(self):
        """[UC-7.5] Kiểm tra hàm helper create_system_notification gửi cho 1 User"""
        notif = create_system_notification(
            user=self.customer,
            title="Nhắc lịch hẹn dịch vụ Massage",
            content="Quý khách có lịch hẹn vào 14:00 ngày mai tại Phòng VIP 01.",
            promotion=self.promo
        )
        self.assertIsNotNone(notif.id)
        self.assertEqual(notif.user, self.customer)
        self.assertEqual(notif.promotion, self.promo)
        self.assertTrue(notif.notification_code.startswith("TB-"))

    def test_uc_7_5_create_system_notification_helper_bulk(self):
        """[UC-7.5] Kiểm tra hàm helper create_system_notification gửi hàng loạt (bulk_create)"""
        users = [self.admin, self.staff, self.customer]
        notifs = create_system_notification(
            user=users,
            title="Thông báo toàn hệ thống",
            content="Bảo trì nâng cấp hạ tầng Cham Spa lúc 23:00 tối nay."
        )
        self.assertEqual(len(notifs), 3)
        self.assertEqual(Notification.objects.filter(title="Thông báo toàn hệ thống").count(), 3)

    def test_uc_7_1_notification_dropdown_api(self):
        """[UC-7.1] Kiểm tra API Dropdown tại quả chuông (Top-bar Bell Icon)"""
        # Tạo thông báo cho customer
        create_system_notification(
            user=self.customer,
            title="Tặng mã voucher 20%",
            content="Cham Spa tặng bạn mã voucher CHAMSPA20."
        )

        # Đăng nhập với tài khoản customer
        self.client.force_login(self.customer)
        url = reverse('marketing:api_notification_dropdown')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['role'], 'CUSTOMER')
        self.assertGreaterEqual(len(data['notifications']), 1)

    def test_uc_7_1_notification_timeline_view(self):
        """[UC-7.1] Kiểm tra giao diện danh sách thông báo dạng Timeline bảng tin"""
        self.client.force_login(self.customer)
        url = reverse('marketing:notifications')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'marketing/notifications.html')

    def test_uc_7_2_promotions_and_vouchers_view(self):
        """[UC-7.2] Kiểm tra Trang Ưu đãi 2 tab: Khuyến mãi & Ví Voucher"""
        url = reverse('marketing:promotions')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'marketing/promotions.html')
        self.assertIn('promotions', response.context)
        self.assertIn('available_vouchers', response.context)

    def test_uc_7_3_admin_notification_post_bulk_and_delete(self):
        """[UC-7.3] Kiểm tra Admin gửi thông báo hàng loạt & xóa broadcast qua Form POST (non-superuser bị 403)"""
        url = reverse('marketing:admin_notifications')

        # Nhân viên (Staff) gửi POST phải bị từ chối 403
        self.client.force_login(self.staff)
        forbidden_resp = self.client.post(url, {
            'action': 'create_notification',
            'title': 'Thử quyền',
            'content': 'Không hợp lệ',
        })
        self.assertEqual(forbidden_resp.status_code, 403)

        # Admin gửi thông báo hàng loạt cho khách hàng
        self.client.force_login(self.admin)
        payload = {
            'action': 'create_notification',
            'title': 'Ưu đãi tri ân thành viên mới',
            'content': 'Nhận ngay giảm 20% khi đặt liệu trình xông hơi.',
            'target_type': 'all_customers',
            'delivery_channels': 'Web',
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        created_qs = Notification.objects.filter(title='Ưu đãi tri ân thành viên mới')
        self.assertGreater(created_qs.count(), 0)

        # Admin xóa hàng loạt broadcast theo notification_id đại diện
        sample_id = created_qs.first().id
        del_resp = self.client.post(url, {
            'action': 'delete_notification',
            'notification_id': sample_id,
            'scope': 'broadcast',
        })
        self.assertEqual(del_resp.status_code, 302)
        self.assertEqual(Notification.objects.filter(title='Ưu đãi tri ân thành viên mới').count(), 0)

    def test_uc_7_4_admin_promotions_and_vouchers_post(self):
        """[UC-7.4] Kiểm tra Admin CRUD Khuyến mãi & phát hành/xóa Voucher qua Form POST (non-superuser bị 403)"""
        url = reverse('marketing:admin_promotions')
        expiry = (timezone.now() + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M")

        # Nhân viên (Staff) gửi POST phải bị từ chối 403
        self.client.force_login(self.staff)
        forbidden_resp = self.client.post(url, {'action': 'create_voucher', 'voucher_code': 'DENIED'})
        self.assertEqual(forbidden_resp.status_code, 403)

        # 1. Admin tạo chương trình khuyến mãi
        self.client.force_login(self.admin)
        promo_resp = self.client.post(url, {
            'action': 'create_promotion',
            'promotion_code': 'SPRING26',
            'title': 'Ưu đãi Xuân',
            'conditions_desc': 'Áp dụng cuối tuần',
            'status': 'Đang hoạt động',
            'valid_from': '2026-05-01',
            'valid_until': '2026-05-31',
        })
        self.assertEqual(promo_resp.status_code, 302)
        promo = Promotion.objects.get(promotion_code='SPRING26')

        # 2. Đổi trạng thái chiến dịch
        toggle_resp = self.client.post(url, {'action': 'toggle_promotion', 'promotion_id': promo.id})
        self.assertEqual(toggle_resp.status_code, 302)
        promo.refresh_from_db()
        self.assertEqual(promo.status, 'Hết hạn')

        # 3. Phát hành Voucher gắn chiến dịch
        voucher_resp = self.client.post(url, {
            'action': 'create_voucher',
            'voucher_code': 'CHAMSPA25',
            'discount_type': 'PERCENT',
            'discount_value': '25',
            'max_discount_amount': '150000',
            'min_order_amount': '500000',
            'expiry_date': expiry,
            'promotion_id': promo.id,
        })
        self.assertEqual(voucher_resp.status_code, 302)
        vouch = Voucher.objects.get(voucher_code='CHAMSPA25')
        self.assertEqual(vouch.discount_type, 'PERCENT')
        self.assertEqual(vouch.discount_value, Decimal('25.00'))
        self.assertEqual(vouch.max_discount_amount, Decimal('150000.00'))
        self.assertEqual(vouch.promotion_id, promo.id)

        # 4. Xóa Voucher và Khuyến mãi
        self.client.post(url, {'action': 'delete_voucher', 'voucher_id': vouch.id})
        self.assertFalse(Voucher.objects.filter(id=vouch.id).exists())
        self.client.post(url, {'action': 'delete_promotion', 'promotion_id': promo.id})
        self.assertFalse(Promotion.objects.filter(id=promo.id).exists())

    def test_internal_roles_exclude_customer_notifications(self):
        """[UC-7.1] Staff và Admin không hiển thị thông báo nghiệp vụ của Khách hàng dù gắn nhầm user"""
        # Tạo các thông báo kiểu Khách hàng gắn nhầm vào Admin và Staff
        Notification.objects.create(
            notification_code='TB-PTS-999999-1',
            user=self.admin,
            title='Bạn vừa được cộng +55 điểm thưởng!',
            content='Thanh toán lịch hẹn #LH88392 thành công. Quý khách nhận được +55 điểm thưởng.',
            status='Đã gửi',
        )
        Notification.objects.create(
            notification_code='TB-PTS-999999-2',
            user=self.staff,
            title='Bạn vừa được cộng +109 điểm thưởng!',
            content='Thanh toán lịch hẹn #LH32520 thành công. Quý khách nhận được +109 điểm thưởng.',
            status='Đã gửi',
        )
        Notification.objects.create(
            notification_code='TB-STF-999999-1',
            user=self.staff,
            title='Phân công xử lý khiếu nại mới',
            content='Quản lý đã phân công bạn xử lý khiếu nại #KN-200.',
            status='Đã gửi',
        )
        Notification.objects.create(
            notification_code='TB-ADM-999999-1',
            user=self.admin,
            title='Cập nhật chương trình khuyến mãi',
            content="Chiến dịch 'Ưu đãi mùa thu' đã kích hoạt thành công.",
            status='Đã gửi',
        )

        # Kiểm tra chuông Admin và Staff không chứa thông báo cộng điểm của khách
        self.client.force_login(self.admin)
        admin_drop = self.client.get(reverse('marketing:api_notification_dropdown')).json()
        admin_titles = [n['title'] for n in admin_drop['notifications']]
        self.assertNotIn('Bạn vừa được cộng +55 điểm thưởng!', admin_titles)
        self.assertIn('Cập nhật chương trình khuyến mãi', admin_titles)

        self.client.force_login(self.staff)
        staff_drop = self.client.get(reverse('marketing:api_notification_dropdown')).json()
        staff_titles = [n['title'] for n in staff_drop['notifications']]
        self.assertNotIn('Bạn vừa được cộng +109 điểm thưởng!', staff_titles)
        self.assertIn('Phân công xử lý khiếu nại mới', staff_titles)

        # Kiểm tra trang danh sách thông báo Staff (/marketing/staff/)
        staff_page = self.client.get(reverse('marketing:staff_notifications'))
        self.assertEqual(staff_page.status_code, 200)
        staff_html = staff_page.content.decode('utf-8')
        self.assertNotIn('Bạn vừa được cộng +109 điểm thưởng!', staff_html)
        self.assertIn('Phân công xử lý khiếu nại mới', staff_html)

    def test_uc_7_4_voucher_validate_api(self):
        """[UC-7.4] Kiểm tra tính toán giảm giá của Voucher khi áp dụng đơn hàng"""
        url = reverse('marketing:api_voucher_validate')

        # Đơn hàng 1.000.000đ áp voucher 20% trần 150.000đ -> Giảm đúng 150.000đ
        payload = {
            'voucher_code': 'CHAMSPA20',
            'order_amount': 1000000
        }
        response = self.client.post(url, payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['valid'])
        self.assertEqual(data['discount_amount'], 150000.0)
        self.assertEqual(data['final_amount'], 850000.0)

    def test_notification_classification_exclusive_no_duplicates_and_no_refresh_btn(self):
        """Phân loại thông báo đúng loại không chồng chéo, chống trùng lặp và bỏ nút Làm mới"""
        # Dọn thông báo mẫu cũ của customer/staff nếu có để kiểm đếm chính xác từng loại
        Notification.objects.filter(user__in=[self.customer, self.staff]).delete()

        # 1. Tạo đủ các loại thông báo cho Customer & Staff (trước khi gọi view auto-seed sample)
        create_unique_notification(
            user=self.staff,
            title='Phân công xử lý khiếu nại mới',
            content='Quản lý đã phân công bạn xử lý khiếu nại COMP-001.',
            prefix='TB-COMP',
        )
        create_unique_notification(
            user=self.staff,
            title='Khách hàng gửi yêu cầu tư vấn',
            content='Khách hàng Nguyễn Văn A đang chờ tư vấn trên Livechat Console.',
            prefix='TB-STF',
        )
        create_system_notification(
            user=self.staff,
            title='Lịch họp giao ban đầu tuần',
            content='Toàn bộ nhân viên có mặt lúc 08:30 thứ Hai.',
        )

        n_voucher = create_unique_notification(
            user=self.customer,
            title='Tặng bạn mã Voucher ưu đãi 20%',
            content='Giảm 20% cho đơn tiếp theo.',
            prefix='TB-CUS',
        )
        # Gọi lại cùng nội dung -> không được tạo bản ghi trùng
        dup_voucher = create_unique_notification(
            user=self.customer,
            title='Tặng bạn mã Voucher ưu đãi 20%',
            content='Giảm 20% cho đơn tiếp theo.',
            prefix='TB-CUS',
        )
        self.assertEqual(n_voucher.id, dup_voucher.id)

        create_unique_notification(
            user=self.customer,
            title='Bạn vừa được cộng +76 điểm thưởng!',
            content='Thanh toán lịch hẹn #LH94191 thành công. Số dư điểm hiện tại: 76 điểm.',
            prefix='TB-PTS',
        )
        create_unique_notification(
            user=self.customer,
            title='Lịch hẹn #LH94191 đã hoàn thành (+76 điểm thưởng)',
            content='Lịch hẹn #LH94191 (14:30 ngày 2026-11-14) đã hoàn thành.',
            prefix='TB-STATUS',
        )
        create_unique_notification(
            user=self.customer,
            title='Cham Spa đã xử lý khiếu nại COMP-20261111-109F',
            content='Đã xử lý và gửi tặng bạn mã Voucher đền bù DENBU-001.',
            prefix='TB-COMP',
        )
        create_system_notification(
            user=self.customer,
            title='Chúc mừng năm mới 2026',
            content='Cham Spa kính chúc quý khách một năm mới an khang thịnh vượng.',
        )
        # Thử tạo trùng với create_system_notification
        create_system_notification(
            user=self.customer,
            title='Chúc mừng năm mới 2026',
            content='Cham Spa kính chúc quý khách một năm mới an khang thịnh vượng.',
        )
        self.assertEqual(Notification.objects.filter(user=self.customer).count(), 5)

        self.client.force_login(self.customer)
        timeline_resp = self.client.get(reverse('marketing:notifications'))
        self.assertEqual(timeline_resp.status_code, 200)
        stats = timeline_resp.context['stats']
        self.assertEqual(stats['all'], 5)
        self.assertEqual(stats['appointment'], 1)
        self.assertEqual(stats['voucher'], 1)
        self.assertEqual(stats['complaint'], 1)
        self.assertEqual(stats['membership'], 1)
        self.assertEqual(stats['system'], 1)

        # Kiểm tra API dropdown cũng phân loại chuẩn xác từng thông báo
        drop_resp = self.client.get(reverse('marketing:api_notification_dropdown'))
        self.assertEqual(drop_resp.status_code, 200)
        cat_by_title = {item['title']: item['category'] for item in drop_resp.json()['notifications']}
        self.assertEqual(cat_by_title['Bạn vừa được cộng +76 điểm thưởng!'], 'membership')
        self.assertEqual(cat_by_title['Lịch hẹn #LH94191 đã hoàn thành (+76 điểm thưởng)'], 'appointment')
        self.assertEqual(cat_by_title['Cham Spa đã xử lý khiếu nại COMP-20261111-109F'], 'complaint')
        self.assertEqual(cat_by_title['Tặng bạn mã Voucher ưu đãi 20%'], 'voucher')
        self.assertEqual(cat_by_title['Chúc mừng năm mới 2026'], 'system')

        # 2. Kiểm tra Staff tabs phân loại tách biệt, không đếm trùng
        self.client.force_login(self.staff)
        staff_resp = self.client.get(reverse('marketing:staff_notifications'))
        self.assertEqual(staff_resp.status_code, 200)
        self.assertNotContains(staff_resp, 'Làm mới')
        staff_stats = staff_resp.context['stats']
        self.assertEqual(
            staff_stats['all'],
            staff_stats['complaints'] + staff_stats['consultation'] + staff_stats['internal'],
        )
        self.assertEqual(staff_stats['complaints'], 1)
        self.assertEqual(staff_stats['consultation'], 1)
        self.assertEqual(staff_stats['internal'], 1)

        # 3. Đảm bảo nút Làm mới đã được gỡ ở cả trang Staff và template Admin Marketing
        self.client.force_login(self.admin)
        admin_notif_resp = self.client.get(reverse('marketing:admin_notifications'))
        self.assertEqual(admin_notif_resp.status_code, 200)
        self.assertNotContains(admin_notif_resp, 'Làm mới')
        admin_mkt_html = Path(settings.BASE_DIR, 'templates', 'marketing', 'admin_marketing.html').read_text(encoding='utf-8')
        self.assertNotIn('Làm mới', admin_mkt_html)
