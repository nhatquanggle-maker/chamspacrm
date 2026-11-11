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

    def test_admin_promotions_full_crud_and_existing_voucher_selection(self):
        """[UC-7.4] Admin Thêm/Xem/Sửa/Xóa Khuyến mãi và chọn gắn Voucher hiện có."""
        url = reverse('marketing:admin_promotions')

        # Tạo thêm 1 voucher độc lập và 1 voucher cá nhân để kiểm tra gắn/gỡ
        free_voucher = Voucher.objects.create(
            voucher_code='FREEVOUCH50',
            promotion=None,
            discount_type='FIXED',
            discount_value=Decimal('50000.00'),
            min_order_amount=Decimal('200000.00'),
            status='Khả dụng',
            expiry_date=timezone.now() + timedelta(days=20),
        )
        personal_voucher = Voucher.objects.create(
            voucher_code='PRIVSPEC100',
            promotion=None,
            customer=self.customer,
            discount_type='FIXED',
            discount_value=Decimal('100000.00'),
            min_order_amount=Decimal('0.00'),
            status='Khả dụng',
            expiry_date=timezone.now() + timedelta(days=20),
        )

        # Non-superuser bị chặn sửa Promotion
        self.client.force_login(self.staff)
        resp_forbidden = self.client.post(url, {
            'action': 'update_promotion',
            'promotion_id': self.promo.id,
            'promotion_code': 'HACK',
            'title': 'Hacked',
        })
        self.assertEqual(resp_forbidden.status_code, 403)

        # 1. Admin tạo chương trình khuyến mãi mới và chọn sẵn 2 voucher hiện có
        self.client.force_login(self.admin)
        create_resp = self.client.post(url, {
            'action': 'create_promotion',
            'promotion_code': 'AUTUMN2026',
            'title': 'Ưu đãi Thu Vàng',
            'conditions_desc': 'Áp dụng liệu trình thảo dược',
            'valid_from': '2026-10-01',
            'valid_until': '2026-12-31',
            'status': 'Đang hoạt động',
            'voucher_ids': [str(free_voucher.id), str(self.voucher_fixed.id)],
        })
        self.assertEqual(create_resp.status_code, 302)
        new_promo = Promotion.objects.get(promotion_code='AUTUMN2026')
        free_voucher.refresh_from_db()
        self.voucher_fixed.refresh_from_db()
        self.assertEqual(free_voucher.promotion_id, new_promo.id)
        self.assertEqual(self.voucher_fixed.promotion_id, new_promo.id)

        # 2. Kiểm tra GET trang Admin Promotions (có nút Xem/Sửa/Xóa & JSON dữ liệu modal + không chứa Làm mới)
        page_resp = self.client.get(url)
        self.assertEqual(page_resp.status_code, 200)
        self.assertNotContains(page_resp, 'Làm mới')
        self.assertIn(str(new_promo.id), page_resp.context['promo_map'])
        promo_payload = page_resp.context['promo_map'][str(new_promo.id)]
        self.assertEqual(set(promo_payload['voucher_ids']), {free_voucher.id, self.voucher_fixed.id})
        self.assertContains(page_resp, f'openViewPromoModal({new_promo.id})')
        self.assertContains(page_resp, f'openEditPromoModal({new_promo.id})')

        # 3. Kiểm tra validation ngày kết thúc < ngày bắt đầu & trùng mã khi sửa
        bad_date_resp = self.client.post(url, {
            'action': 'update_promotion',
            'promotion_id': new_promo.id,
            'promotion_code': 'AUTUMN2026',
            'title': 'Ưu đãi Thu Vàng',
            'valid_from': '2026-12-31',
            'valid_until': '2026-10-01',
            'status': 'Đang hoạt động',
        })
        self.assertEqual(bad_date_resp.status_code, 302)
        new_promo.refresh_from_db()
        self.assertEqual(timezone.localtime(new_promo.valid_from).month, 10)

        dup_code_resp = self.client.post(url, {
            'action': 'update_promotion',
            'promotion_id': new_promo.id,
            'promotion_code': self.promo.promotion_code,
            'title': 'Trùng mã',
            'status': 'Đang hoạt động',
        })
        self.assertEqual(dup_code_resp.status_code, 302)
        new_promo.refresh_from_db()
        self.assertEqual(new_promo.promotion_code, 'AUTUMN2026')

        # 4. Sửa khuyến mãi: đổi thông tin, giữ free_voucher, bỏ voucher_fixed, gắn thêm personal_voucher
        edit_resp = self.client.post(url, {
            'action': 'update_promotion',
            'promotion_id': new_promo.id,
            'promotion_code': 'AUTUMN26VIP',
            'title': 'Ưu đãi Thu Vàng VIP',
            'conditions_desc': 'Áp dụng cuối tuần và ngày lễ',
            'valid_from': '2026-10-05',
            'valid_until': '2026-12-20',
            'status': 'Sắp diễn ra',
            'voucher_ids': [str(free_voucher.id), str(personal_voucher.id)],
        })
        self.assertEqual(edit_resp.status_code, 302)
        new_promo.refresh_from_db()
        free_voucher.refresh_from_db()
        self.voucher_fixed.refresh_from_db()
        personal_voucher.refresh_from_db()

        self.assertEqual(new_promo.promotion_code, 'AUTUMN26VIP')
        self.assertEqual(new_promo.title, 'Ưu đãi Thu Vàng VIP')
        self.assertEqual(new_promo.status, 'Sắp diễn ra')
        self.assertEqual(free_voucher.promotion_id, new_promo.id)
        self.assertEqual(personal_voucher.promotion_id, new_promo.id)
        self.assertIsNone(self.voucher_fixed.promotion_id)

        # 5. Kiểm tra trang công khai /marketing/ chỉ hiển thị voucher chung, không lộ voucher cá nhân
        pub_resp = self.client.get(reverse('marketing:promotions'))
        self.assertEqual(pub_resp.status_code, 200)
        matched_promo = [p for p in pub_resp.context['promotions'] if p.id == new_promo.id][0]
        pub_codes = [v.voucher_code for v in matched_promo.public_vouchers]
        self.assertIn('FREEVOUCH50', pub_codes)
        self.assertNotIn('PRIVSPEC100', pub_codes)

    def test_admin_vouchers_full_crud_and_validation(self):
        """[UC-7.4] Admin Thêm/Xem/Sửa/Xóa Mã Voucher và đồng bộ trạng thái sử dụng."""
        url = reverse('marketing:admin_promotions')
        future_expiry = (timezone.now() + timedelta(days=45)).strftime('%Y-%m-%dT%H:%M')
        past_expiry = (timezone.now() - timedelta(days=5)).strftime('%Y-%m-%dT%H:%M')

        # Non-superuser bị chặn sửa Voucher
        self.client.force_login(self.staff)
        forbidden = self.client.post(url, {
            'action': 'update_voucher',
            'voucher_id': self.voucher_percent.id,
            'voucher_code': 'HACKVOUCH',
            'discount_type': 'FIXED',
            'discount_value': '10000',
            'expiry_date': future_expiry,
        })
        self.assertEqual(forbidden.status_code, 403)

        # Admin xem danh sách và payload Xem/Sửa
        self.client.force_login(self.admin)
        get_resp = self.client.get(f"{url}?subtab=vouchers")
        self.assertEqual(get_resp.status_code, 200)
        self.assertIn(str(self.voucher_percent.id), get_resp.context['voucher_map'])
        self.assertContains(get_resp, f'openViewVoucherModal({self.voucher_percent.id})')
        self.assertContains(get_resp, f'openEditVoucherModal({self.voucher_percent.id})')

        # Sửa voucher % -> FIXED, đổi mã, gắn khách hàng và chuyển sang Đã dùng
        edit_resp = self.client.post(url, {
            'action': 'update_voucher',
            'voucher_id': self.voucher_percent.id,
            'voucher_code': 'CHAMFIXED250',
            'promotion_id': '',
            'discount_type': 'FIXED',
            'discount_value': '250000',
            'max_discount_amount': '999999',
            'min_order_amount': '800000',
            'expiry_date': future_expiry,
            'status': 'Đã dùng',
            'customer_id': str(self.customer.id),
        })
        self.assertEqual(edit_resp.status_code, 302)
        self.voucher_percent.refresh_from_db()
        self.assertEqual(self.voucher_percent.voucher_code, 'CHAMFIXED250')
        self.assertIsNone(self.voucher_percent.promotion_id)
        self.assertEqual(self.voucher_percent.discount_type, 'FIXED')
        self.assertEqual(self.voucher_percent.discount_value, Decimal('250000.00'))
        self.assertIsNone(self.voucher_percent.max_discount_amount)
        self.assertEqual(self.voucher_percent.min_order_amount, Decimal('800000.00'))
        self.assertEqual(self.voucher_percent.status, 'Đã dùng')
        self.assertEqual(self.voucher_percent.customer_id, self.customer.id)
        self.assertIsNotNone(self.voucher_percent.used_at)

        # Sửa lại thành Hết hạn với ngày quá khứ (cho phép giữ trạng thái Hết hạn)
        expired_edit = self.client.post(url, {
            'action': 'update_voucher',
            'voucher_id': self.voucher_percent.id,
            'voucher_code': 'CHAMFIXED250',
            'discount_type': 'FIXED',
            'discount_value': '250000',
            'min_order_amount': '800000',
            'expiry_date': past_expiry,
            'status': 'Hết hạn',
        })
        self.assertEqual(expired_edit.status_code, 302)
        self.voucher_percent.refresh_from_db()
        self.assertEqual(self.voucher_percent.status, 'Hết hạn')

        # Không cho chuyển lại Khả dụng nếu expiry vẫn ở quá khứ
        bad_reactivate = self.client.post(url, {
            'action': 'update_voucher',
            'voucher_id': self.voucher_percent.id,
            'voucher_code': 'CHAMFIXED250',
            'discount_type': 'FIXED',
            'discount_value': '250000',
            'min_order_amount': '800000',
            'expiry_date': past_expiry,
            'status': 'Khả dụng',
        })
        self.assertEqual(bad_reactivate.status_code, 302)
        self.voucher_percent.refresh_from_db()
        self.assertEqual(self.voucher_percent.status, 'Hết hạn')

        # Gia hạn và chuyển lại Khả dụng -> xóa used_at
        reactivate_ok = self.client.post(url, {
            'action': 'update_voucher',
            'voucher_id': self.voucher_percent.id,
            'voucher_code': 'CHAMFIXED250',
            'discount_type': 'PERCENT',
            'discount_value': '15',
            'max_discount_amount': '120000',
            'min_order_amount': '500000',
            'expiry_date': future_expiry,
            'status': 'Khả dụng',
        })
        self.assertEqual(reactivate_ok.status_code, 302)
        self.voucher_percent.refresh_from_db()
        self.assertEqual(self.voucher_percent.status, 'Khả dụng')
        self.assertIsNone(self.voucher_percent.used_at)
        self.assertEqual(self.voucher_percent.max_discount_amount, Decimal('120000.00'))

    def test_admin_notifications_full_crud_all_targets(self):
        """[UC-7.3] Admin Thêm/Xem/Sửa/Xóa Thông báo cho khách hàng, nhân viên và cá nhân."""
        url = reverse('marketing:admin_notifications')
        User.objects.create_user(
            username='customer_two',
            phone='0905999004',
            email='cus2@gmail.com',
            name='Khách Hai',
            password='TestPassword123!',
        )

        # Non-superuser bị chặn update_notification
        self.client.force_login(self.staff)
        forbidden = self.client.post(url, {
            'action': 'update_notification',
            'notification_id': 1,
            'title': 'Hack',
            'content': 'Hack',
        })
        self.assertEqual(forbidden.status_code, 403)

        # 1. Admin phát thông báo tới toàn bộ khách hàng (2 khách) ở trạng thái Chờ gửi
        self.client.force_login(self.admin)
        self.client.post(url, {
            'action': 'create_notification',
            'title': 'Thông báo bảo trì tối nay',
            'content': 'Hệ thống bảo trì từ 23:00 đến 23:30.',
            'target_type': 'all_customers',
            'delivery_channels': 'Web & Email',
            'status': 'Chờ gửi',
        })
        batch_qs = Notification.objects.filter(title='Thông báo bảo trì tối nay')
        self.assertEqual(batch_qs.count(), 2)
        self.assertTrue(all(n.status == 'Chờ gửi' for n in batch_qs))

        # 2. Admin tạo thêm thông báo gửi Staff (all_staff) và gửi 1 cá nhân (single_user)
        self.client.post(url, {
            'action': 'create_notification',
            'title': 'Họp giao ban KTV',
            'content': 'Có mặt đúng 08:30 tại phòng họp tầng 2.',
            'target_type': 'all_staff',
            'delivery_channels': 'In-App',
            'status': 'Đã gửi',
        })
        self.client.post(url, {
            'action': 'create_notification',
            'title': 'Quà sinh nhật riêng',
            'content': 'Chúc mừng sinh nhật quý khách Lê Nhật Quang.',
            'target_type': 'single_user',
            'user_id': str(self.customer.id),
            'promotion_id': str(self.promo.id),
            'delivery_channels': 'Web',
            'status': 'Đã gửi',
        })

        # 3. Trang Admin Notifications hiển thị đủ cả 3 đợt cùng nút Xem/Sửa/Xóa
        list_resp = self.client.get(url)
        self.assertEqual(list_resp.status_code, 200)
        self.assertNotContains(list_resp, 'Làm mới')
        titles = {n.title: n for n in list_resp.context['notifications']}
        self.assertIn('Thông báo bảo trì tối nay', titles)
        self.assertIn('Họp giao ban KTV', titles)
        self.assertIn('Quà sinh nhật riêng', titles)

        rep_broadcast = titles['Thông báo bảo trì tối nay']
        self.assertEqual(rep_broadcast.recipient_count, 2)
        self.assertContains(list_resp, f'openViewNotifModal({rep_broadcast.id})')
        self.assertContains(list_resp, f'openEditNotifModal({rep_broadcast.id})')

        # 4. Sửa đợt thông báo chung -> đồng bộ toàn bộ bản ghi trong đợt và chuyển Đã gửi
        self.client.post(url, {
            'action': 'update_notification',
            'notification_id': rep_broadcast.id,
            'scope': 'broadcast',
            'title': 'Lịch nâng cấp hệ thống (Đã cập nhật)',
            'content': 'Hệ thống đã hoàn tất nâng cấp lúc 23:15.',
            'delivery_channels': 'Toàn bộ (In-App, SMS, Email)',
            'promotion_id': str(self.promo.id),
            'status': 'Đã gửi',
        })
        updated_qs = Notification.objects.filter(title='Lịch nâng cấp hệ thống (Đã cập nhật)')
        self.assertEqual(updated_qs.count(), 2)
        self.assertTrue(all(n.status == 'Đã gửi' and n.promotion_id == self.promo.id for n in updated_qs))

        # 5. Xóa đợt thông báo Staff
        rep_staff = titles['Họp giao ban KTV']
        self.client.post(url, {
            'action': 'delete_notification',
            'notification_id': rep_staff.id,
            'scope': 'broadcast',
        })
        self.assertEqual(Notification.objects.filter(title='Họp giao ban KTV').count(), 0)

        # 6. Sửa và xóa thông báo cá nhân (scope='single')
        rep_single = titles['Quà sinh nhật riêng']
        self.client.post(url, {
            'action': 'update_notification',
            'notification_id': rep_single.id,
            'scope': 'single',
            'title': 'Quà sinh nhật VIP',
            'content': 'Tặng bạn gói xông hơi miễn phí.',
            'delivery_channels': 'Web & Email',
            'promotion_id': '',
            'status': 'Đã gửi',
        })
        rep_single.refresh_from_db()
        self.assertEqual(rep_single.title, 'Quà sinh nhật VIP')
        self.assertIsNone(rep_single.promotion_id)

        self.client.post(url, {
            'action': 'delete_notification',
            'notification_id': rep_single.id,
            'scope': 'single',
        })
        self.assertFalse(Notification.objects.filter(id=rep_single.id).exists())
