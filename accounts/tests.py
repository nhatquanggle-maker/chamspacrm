from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import UserProfile, UserHealthProfile

User = get_user_model()


class AccountsAdminViewsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='0900000001',
            phone='0900000001',
            email='admin_acc@chamspa.local',
            name='Quản Trị Viên',
            password='Password123!',
            is_staff=True,
            is_superuser=True,
        )
        self.staff = User.objects.create_user(
            username='0900000002',
            phone='0900000002',
            email='staff_acc@chamspa.local',
            name='Nhân Viên Lễ Tân',
            password='Password123!',
            is_staff=True,
            is_superuser=False,
        )
        self.customer = User.objects.create_user(
            username='0900000003',
            phone='0900000003',
            email='cust_acc@chamspa.local',
            name='Khách Hàng A',
            password='Password123!',
            is_staff=False,
            is_superuser=False,
        )

    def test_admin_staff_detail_rbac_and_render(self):
        url = reverse('accounts:admin_staff_detail', args=[self.staff.pk])

        self.client.force_login(self.admin)
        resp_admin = self.client.get(url)
        self.assertEqual(resp_admin.status_code, 200)
        self.assertContains(resp_admin, self.staff.name)

        self.client.force_login(self.customer)
        resp_cust = self.client.get(url)
        self.assertEqual(resp_cust.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp_cust.url)

    def test_admin_customer_list_rbac_and_clean_ui(self):
        url = reverse('accounts:admin_customer_list')

        self.client.force_login(self.admin)
        resp_admin = self.client.get(url)
        self.assertEqual(resp_admin.status_code, 200)
        html_admin = resp_admin.content.decode('utf-8')
        self.assertIn(self.customer.name, html_admin)
        self.assertNotIn('Mã TK', html_admin)
        self.assertNotIn(f'#CUS{self.customer.id:03d}', html_admin)

        self.client.force_login(self.staff)
        resp_staff = self.client.get(url)
        self.assertEqual(resp_staff.status_code, 200)

        self.client.force_login(self.customer)
        resp_cust = self.client.get(url)
        self.assertEqual(resp_cust.status_code, 302)
        self.assertEqual(resp_cust.url, reverse('home'))

    def test_profile_update_preserves_admin_staff_username_and_blocks_spaced_phone_collision(self):
        fixed_admin = User.objects.create_user(
            username='admin',
            phone='0901234599',
            email='admin_fixed@chamspa.vn',
            name='Admin Fixed',
            password='Password123!',
            is_staff=True,
            is_superuser=True,
        )
        fixed_staff = User.objects.create_user(
            username='staff',
            phone='0905123499',
            email='staff_fixed@chamspa.vn',
            name='Staff Fixed',
            password='Password123!',
            is_staff=True,
            is_superuser=False,
        )
        spaced_cust = User.objects.create_user(
            username='0912000111',
            phone='0912 000 111',
            email='spaced_cust@gmail.com',
            name='Spaced Cust',
            password='Password123!',
        )

        profile_url = reverse('accounts:profile')

        # Admin cập nhật thông tin không làm mất username='admin' hay lỗi IntegrityError
        self.client.force_login(fixed_admin)
        resp_a = self.client.post(profile_url, {
            'action': 'update_profile',
            'name': 'Quản Trị Mới',
            'phone': '0901 234 598',
            'email': 'admin_new@chamspa.vn',
            'gender': 'Nam',
            'birthday': '1991-02-03',
        })
        self.assertEqual(resp_a.status_code, 302)
        fixed_admin.refresh_from_db()
        self.assertEqual(fixed_admin.username, 'admin')
        self.assertEqual(fixed_admin.phone, '0901234598')
        self.assertEqual(fixed_admin.email, 'admin_new@chamspa.vn')
        self.assertEqual(fixed_admin.profile.birthday, date(1991, 2, 3))

        # Staff cập nhật thông tin không làm mất username='staff'
        self.client.force_login(fixed_staff)
        resp_s = self.client.post(profile_url, {
            'action': 'update_profile',
            'name': 'Nhân Viên Mới',
            'phone': '0905123498',
            'email': 'staff_new@chamspa.vn',
            'gender': 'Nữ',
            'birthday': '',
        })
        self.assertEqual(resp_s.status_code, 302)
        fixed_staff.refresh_from_db()
        self.assertEqual(fixed_staff.username, 'staff')
        self.assertEqual(fixed_staff.email, 'staff_new@chamspa.vn')

        # Khách hàng nhập trùng SĐT (dù bản ghi khác lưu có dấu cách) bị chặn sạch sẽ, không 500
        self.client.force_login(self.customer)
        resp_dup = self.client.post(profile_url, {
            'action': 'update_profile',
            'name': 'Khách A',
            'phone': '0912000111',
            'email': 'khacha@gmail.com',
            'gender': 'Nữ',
            'birthday': '',
        })
        self.assertEqual(resp_dup.status_code, 200)
        self.assertIn('alert-danger', resp_dup.content.decode('utf-8'))
        self.assertTrue(User.objects.filter(pk=spaced_cust.pk).exists())
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.phone, '0900000003')

    def test_email_domain_policy_and_admin_update_modals(self):
        # 1. Đăng ký công khai bắt buộc @gmail.com
        reg_url = reverse('accounts:register')
        bad_reg = self.client.post(reg_url, {
            'name': 'Khách Sai Domain',
            'email': 'bad@chamspa.vn',
            'phone': '0981111222',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
        })
        self.assertEqual(bad_reg.status_code, 200)
        self.assertFalse(User.objects.filter(phone='0981111222').exists())

        ok_reg = self.client.post(reg_url, {
            'name': 'Khách Đúng Domain',
            'email': 'goodcust@gmail.com',
            'phone': '0981111333',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
        })
        self.assertEqual(ok_reg.status_code, 302)
        self.assertTrue(User.objects.filter(email='goodcust@gmail.com').exists())

        # 2. Admin profile chặn @gmail.com, Customer profile chặn @chamspa.vn
        profile_url = reverse('accounts:profile')
        self.client.force_login(self.admin)
        bad_admin_prof = self.client.post(profile_url, {
            'action': 'update_profile',
            'name': self.admin.name,
            'phone': self.admin.phone,
            'email': 'admin_sai@gmail.com',
        })
        self.assertEqual(bad_admin_prof.status_code, 200)
        self.admin.refresh_from_db()
        self.assertNotEqual(self.admin.email, 'admin_sai@gmail.com')

        self.client.force_login(self.customer)
        bad_cust_prof = self.client.post(profile_url, {
            'action': 'update_profile',
            'name': self.customer.name,
            'phone': self.customer.phone,
            'email': 'cust_sai@chamspa.vn',
        })
        self.assertEqual(bad_cust_prof.status_code, 200)
        self.customer.refresh_from_db()
        self.assertNotEqual(self.customer.email, 'cust_sai@chamspa.vn')

        # 3. Admin cập nhật Customer (cần @gmail.com) & Staff (cần @chamspa.vn)
        self.client.force_login(self.admin)
        cust_detail_url = reverse('accounts:admin_customer_detail', args=[self.customer.pk])
        bad_cust_edit = self.client.post(cust_detail_url, {
            'action': 'edit_customer_detail',
            'name': 'Tên Bị Chặn',
            'phone': self.customer.phone,
            'email': 'khach_sai@chamspa.vn',
            'gender': 'Nam',
        }, follow=True)
        self.assertEqual(bad_cust_edit.status_code, 200)
        self.assertIn('alert-danger', bad_cust_edit.content.decode('utf-8'))
        self.customer.refresh_from_db()
        self.assertNotEqual(self.customer.name, 'Tên Bị Chặn')

        ok_cust_edit = self.client.post(cust_detail_url, {
            'action': 'edit_customer_detail',
            'name': 'Khách Cập Nhật Đúng',
            'phone': '0900 000 099',
            'email': 'khachdung@gmail.com',
            'gender': 'Nam',
            'birthday': '1994-05-06',
            'care_note': 'Thích phòng yên tĩnh',
        }, follow=True)
        self.assertEqual(ok_cust_edit.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, 'Khách Cập Nhật Đúng')
        self.assertEqual(self.customer.phone, '0900000099')
        self.assertEqual(self.customer.email, 'khachdung@gmail.com')
        self.assertEqual(self.customer.profile.birthday, date(1994, 5, 6))
        self.assertEqual(UserHealthProfile.objects.get(user=self.customer).special_requests, 'Thích phòng yên tĩnh')

        staff_list_url = reverse('accounts:admin_staff_list')
        bad_staff_edit = self.client.post(staff_list_url, {
            'action': 'edit_staff',
            'staff_id': self.staff.pk,
            'name': 'NV Sai Domain',
            'phone': self.staff.phone,
            'email': 'staff_sai@gmail.com',
            'work_status': 'Hoạt động',
        }, follow=True)
        self.assertEqual(bad_staff_edit.status_code, 200)
        self.assertIn('alert-danger', bad_staff_edit.content.decode('utf-8'))
        self.staff.refresh_from_db()
        self.assertNotEqual(self.staff.name, 'NV Sai Domain')

        ok_staff_edit = self.client.post(staff_list_url, {
            'action': 'edit_staff',
            'staff_id': self.staff.pk,
            'name': 'NV Đúng Domain',
            'phone': self.staff.phone,
            'email': 'staff_dung@chamspa.vn',
            'work_status': 'Hoạt động',
            'gender': 'Nữ',
            'birthday': '1996-07-08',
        }, follow=True)
        self.assertEqual(ok_staff_edit.status_code, 200)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.name, 'NV Đúng Domain')
        self.assertEqual(self.staff.email, 'staff_dung@chamspa.vn')
        self.assertEqual(self.staff.profile.birthday, date(1996, 7, 8))

    def test_staff_only_supports_active_and_locked_statuses(self):
        """Nhân viên chỉ có đúng 2 trạng thái: Hoạt động và Tạm khóa (không còn Nghỉ phép)."""
        self.client.force_login(self.admin)
        staff_list_url = reverse('accounts:admin_staff_list')

        resp = self.client.get(staff_list_url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertNotIn('Nghỉ phép', html)
        self.assertIn('Hoạt động (', html)
        self.assertIn('Tạm khóa (', html)
        self.assertNotIn('leave_count', resp.context)

        # Tạo mới với giá trị cũ/lạ không phải khóa -> tự chuẩn hóa về Hoạt động
        create_resp = self.client.post(staff_list_url, {
            'action': 'create_staff',
            'name': 'NV Hai Trạng Thái',
            'phone': '0911223344',
            'email': 'haitrangthai@chamspa.vn',
            'work_status': 'Nghỉ phép',
            'gender': 'Nữ',
        }, follow=True)
        self.assertEqual(create_resp.status_code, 200)
        created = User.objects.get(phone='0911223344')
        self.assertTrue(created.is_active)
        self.assertEqual(created.last_name, 'Hoạt động')

        # Khóa nhân viên -> Tạm khóa & is_active=False
        lock_resp = self.client.post(staff_list_url, {
            'action': 'toggle_status',
            'staff_id': created.pk,
        }, follow=True)
        self.assertEqual(lock_resp.status_code, 200)
        created.refresh_from_db()
        self.assertFalse(created.is_active)
        self.assertEqual(created.last_name, 'Tạm khóa')


