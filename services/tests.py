from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Appointment, AppointmentDetail, Category, Service

User = get_user_model()


class ServicesModuleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='0902000001',
            phone='0902000001',
            email='admin_svc@chamspa.local',
            name='Admin Service',
            password='Password123!',
            is_staff=True,
            is_superuser=True,
        )
        self.staff = User.objects.create_user(
            username='0902000002',
            phone='0902000002',
            email='staff_svc@chamspa.local',
            name='Staff Service',
            password='Password123!',
            is_staff=True,
            is_superuser=False,
        )
        self.customer = User.objects.create_user(
            username='0902000003',
            phone='0902000003',
            email='cust_svc@chamspa.local',
            name='Customer Service',
            password='Password123!',
        )
        self.category = Category.objects.create(
            name='Trị Liệu Chuyên Sâu',
            slug='tri-lieu-chuyen-sau',
            status='Active',
        )
        self.service = Service.objects.create(
            category=self.category,
            name='Gội Đầu Thảo Dược Cham Spa',
            slug='goi-dau-thao-duoc-cham-spa',
            price_vnd=Decimal('450000'),
            duration_minutes=60,
            status='Hoạt động',
            description='Liệu trình thư giãn đầu cổ vai gáy.',
        )

    def test_public_service_pages_and_apis(self):
        list_resp = self.client.get(reverse('services:service_list'))
        self.assertEqual(list_resp.status_code, 200)
        list_html = list_resp.content.decode('utf-8')
        self.assertIn(self.service.name, list_html)
        self.assertNotIn('#DVO', list_html)

        detail_resp = self.client.get(reverse('services:service_detail', args=[self.service.slug]))
        self.assertEqual(detail_resp.status_code, 200)
        detail_html = detail_resp.content.decode('utf-8')
        self.assertIn(self.service.name, detail_html)
        self.assertNotIn('#DVO', detail_html)

        api_list = self.client.get(reverse('services:api_service_list'))
        self.assertEqual(api_list.status_code, 200)
        self.assertEqual(api_list.json()['total'], 1)

        api_detail = self.client.get(reverse('services:api_service_detail', args=[self.service.slug]))
        self.assertEqual(api_detail.status_code, 200)
        self.assertEqual(api_detail.json()['name'], self.service.name)

    def test_service_admin_rbac_and_clean_ui(self):
        url = reverse('services:service_admin')

        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(url).status_code, 403)

        for privileged_user in (self.staff, self.admin):
            self.client.force_login(privileged_user)
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            html = resp.content.decode('utf-8')
            self.assertIn(self.service.name, html)
            self.assertNotIn('Mã DV', html)
            self.assertNotIn(f'#DVO{self.service.id:02d}', html)

    def test_service_admin_post_crud_and_permissions(self):
        url = reverse('services:service_admin')

        # Customer blocked from POST
        self.client.force_login(self.customer)
        resp_cust = self.client.post(url, {
            'action': 'save_service',
            'name': 'Unauthorized Service',
            'category_id': self.category.id,
            'price_vnd': '300000',
            'duration_minutes': '45',
        })
        self.assertEqual(resp_cust.status_code, 403)

        # Staff creates, edits, toggles, and deletes services via POST forms
        self.client.force_login(self.staff)
        create_resp = self.client.post(url, {
            'action': 'save_service',
            'name': 'Massage Đá Nóng Champa Mới',
            'category_id': self.category.id,
            'slug': 'massage-da-nong-champa-moi',
            'status': 'Hoạt động',
            'price_vnd': '650000',
            'duration_minutes': '90',
            'description': 'Liệu trình đá nóng núi lửa.',
        }, follow=True)
        self.assertEqual(create_resp.status_code, 200)
        created = Service.objects.get(name='Massage Đá Nóng Champa Mới')
        self.assertEqual(created.price_vnd, Decimal('650000'))

        # Duplicate name validation rejects duplicate creation
        dup_resp = self.client.post(url, {
            'action': 'save_service',
            'name': 'Massage Đá Nóng Champa Mới',
            'category_id': self.category.id,
            'price_vnd': '500000',
            'duration_minutes': '60',
        }, follow=True)
        self.assertEqual(dup_resp.status_code, 200)
        self.assertEqual(Service.objects.filter(name='Massage Đá Nóng Champa Mới').count(), 1)
        self.assertIn('đã tồn tại', dup_resp.content.decode('utf-8'))

        # Edit existing service via Admin
        self.client.force_login(self.admin)
        edit_resp = self.client.post(url, {
            'action': 'save_service',
            'service_id': created.id,
            'name': 'Massage Đá Nóng Champa VIP',
            'category_id': self.category.id,
            'slug': 'massage-da-nong-champa-vip',
            'status': 'Hoạt động',
            'price_vnd': '750000',
            'duration_minutes': '90',
            'description': 'Đã cập nhật mô tả.',
        }, follow=True)
        self.assertEqual(edit_resp.status_code, 200)
        created.refresh_from_db()
        self.assertEqual(created.name, 'Massage Đá Nóng Champa VIP')
        self.assertEqual(created.price_vnd, Decimal('750000'))

        # Toggle status
        toggle_resp = self.client.post(url, {
            'action': 'toggle_service',
            'service_id': created.id,
        }, follow=True)
        self.assertEqual(toggle_resp.status_code, 200)
        created.refresh_from_db()
        self.assertEqual(created.status, 'Ngừng hoạt động')

        # Hard delete unused service
        del_resp = self.client.post(url, {
            'action': 'delete_service',
            'service_id': created.id,
        }, follow=True)
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse(Service.objects.filter(id=created.id).exists())

        # Soft deactivate service already linked to an AppointmentDetail
        appt = Appointment.objects.create(
            appointment_code='LH-TEST-SVC-01',
            user=self.customer,
            appointment_date=date(2026, 11, 20),
            time_slot='14:00',
            customer_name=self.customer.name,
            customer_phone=self.customer.phone,
            total_price=self.service.price_vnd,
            status='Confirmed',
        )
        AppointmentDetail.objects.create(
            appointment=appt,
            service=self.service,
            guest_index=1,
            gender='Nữ',
        )
        soft_del_resp = self.client.post(url, {
            'action': 'delete_service',
            'service_id': self.service.id,
        }, follow=True)
        self.assertEqual(soft_del_resp.status_code, 200)
        self.service.refresh_from_db()
        self.assertEqual(self.service.status, 'Ngừng hoạt động')

    def test_service_admin_allows_arbitrary_price_and_duration(self):
        """Admin có thể nhập mức giá và thời lượng tùy ý (ví dụ 100000 VNĐ, 40 phút) không bị step chặn."""
        url = reverse('services:service_admin')
        self.client.force_login(self.admin)

        get_resp = self.client.get(url)
        self.assertEqual(get_resp.status_code, 200)
        html = get_resp.content.decode('utf-8')
        self.assertIn('id="formServicePrice" name="price_vnd" required min="1" step="1"', html)
        self.assertIn('id="formServiceDuration" name="duration_minutes" required min="1" step="1"', html)
        self.assertNotIn('step="10000"', html)

        post_resp = self.client.post(url, {
            'action': 'save_service',
            'category_id': self.category.id,
            'name': 'Gội Đầu 100K',
            'slug': 'goi-dau-100k',
            'status': 'Hoạt động',
            'price_vnd': '100000',
            'duration_minutes': '40',
            'description': 'Giá lẻ tùy chỉnh không phụ thuộc step.',
        }, follow=True)
        self.assertEqual(post_resp.status_code, 200)
        created = Service.objects.get(slug='goi-dau-100k')
        self.assertEqual(created.price_vnd, Decimal('100000'))
        self.assertEqual(created.duration_minutes, 40)

