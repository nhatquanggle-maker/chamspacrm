from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Appointment, Complaint, Feedback, Notification, Voucher

User = get_user_model()


class FeedbacksAccessAndTrackingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='0901000001',
            phone='0901000001',
            email='admin_fb@chamspa.local',
            name='Admin Feedback',
            password='Password123!',
            is_staff=True,
            is_superuser=True,
        )
        self.staff = User.objects.create_user(
            username='0901000002',
            phone='0901000002',
            email='staff_fb@chamspa.local',
            name='Staff Feedback',
            password='Password123!',
            is_staff=True,
            is_superuser=False,
        )
        self.customer_a = User.objects.create_user(
            username='0901000003',
            phone='0901000003',
            email='custa_fb@chamspa.local',
            name='Khách A',
            password='Password123!',
        )
        self.customer_b = User.objects.create_user(
            username='0901000004',
            phone='0901000004',
            email='custb_fb@chamspa.local',
            name='Khách B',
            password='Password123!',
        )

        self.appt = Appointment.objects.create(
            appointment_code='LH-TEST-001',
            user=self.customer_a,
            appointment_date=date(2026, 11, 10),
            time_slot='14:00',
            customer_name=self.customer_a.name,
            customer_phone=self.customer_a.phone,
            status='Completed',
        )
        self.hidden_feedback = Feedback.objects.create(
            feedback_code='FB-TEST-001',
            appointment=self.appt,
            customer=self.customer_a,
            rating=2,
            comment='Đánh giá đã ẩn',
            status='Đã ẩn',
        )

    def test_customer_with_zero_completed_appointments_can_open_feedback_pages(self):
        self.client.force_login(self.customer_b)
        for route_name in ('feedbacks:my_feedbacks', 'feedbacks:customer_tracking'):
            resp = self.client.get(reverse(route_name))
            self.assertEqual(resp.status_code, 200)

    def test_hidden_feedback_tracking_and_admin_rbac(self):
        # Other customer cannot see owner's hidden feedback and gets 403 posting on owner's appointment or admin POST
        self.client.force_login(self.customer_b)
        tracking_resp = self.client.get(reverse('feedbacks:customer_tracking'))
        self.assertEqual(tracking_resp.status_code, 200)
        self.assertNotIn(self.hidden_feedback, tracking_resp.context['feedbacks'])

        self.assertEqual(
            self.client.post(reverse('feedbacks:customer_tracking'), {
                'action': 'submit_feedback',
                'appointment_id': self.appt.id,
                'rating': 5,
            }).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse('feedbacks:admin_management'), {
                'action': 'toggle_feedback_status',
                'feedback_id': self.hidden_feedback.pk,
            }).status_code,
            403,
        )

        # Owner can see own hidden feedback in tracking
        self.client.force_login(self.customer_a)
        owner_resp = self.client.get(reverse('feedbacks:customer_tracking'))
        self.assertEqual(owner_resp.status_code, 200)
        self.assertIn(self.hidden_feedback, owner_resp.context['feedbacks'])

        # Staff and Admin can view hidden feedback in admin_management detail panel
        manage_url = f"{reverse('feedbacks:admin_management')}?tab=feedbacks&fb_id={self.hidden_feedback.pk}"
        for user in (self.staff, self.admin):
            self.client.force_login(user)
            resp = self.client.get(manage_url)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.context['selected_feedback'].pk, self.hidden_feedback.pk)

    def test_customer_complaint_post_and_staff_admin_workflow(self):
        tracking_url = reverse('feedbacks:customer_tracking')
        manage_url = reverse('feedbacks:admin_management')

        # 1. Customer submits complaint with image attachment
        self.client.force_login(self.customer_a)
        proof_file = SimpleUploadedFile('proof.png', b'\x89PNG\r\n\x1a\n', content_type='image/png')
        comp_resp = self.client.post(tracking_url, {
            'action': 'submit_complaint',
            'appointment_id': self.appt.id,
            'category': 'Chất lượng dịch vụ',
            'description': 'Phòng xông hơi chưa đủ nóng khi mới vào.',
            'proof_files': [proof_file],
        })
        self.assertEqual(comp_resp.status_code, 302)
        complaint = Complaint.objects.get(appointment=self.appt)
        self.assertEqual(complaint.status, 'Chờ phân công')
        self.assertEqual(len(complaint.attached_proofs), 1)

        try:
            # 2. Staff toggles & replies to feedback
            self.client.force_login(self.staff)
            self.assertEqual(
                self.client.post(manage_url, {
                    'action': 'toggle_feedback_status',
                    'feedback_id': self.hidden_feedback.pk,
                }).status_code,
                302,
            )
            self.hidden_feedback.refresh_from_db()
            self.assertEqual(self.hidden_feedback.status, 'Chờ phản hồi')

            self.assertEqual(
                self.client.post(manage_url, {
                    'action': 'reply_feedback',
                    'feedback_id': self.hidden_feedback.pk,
                    'reply': 'Cham Spa chân thành cảm ơn góp ý của bạn.',
                }).status_code,
                302,
            )
            self.hidden_feedback.refresh_from_db()
            self.assertEqual(self.hidden_feedback.status, 'Đã phản hồi')

            # 3. Staff cannot assign or reject complaint (Admin only -> 403)
            self.assertEqual(
                self.client.post(manage_url, {
                    'action': 'assign_complaint',
                    'complaint_id': complaint.pk,
                    'assigned_staff_id': self.staff.pk,
                }).status_code,
                403,
            )

            # 4. Admin assigns complaint to Staff
            self.client.force_login(self.admin)
            self.assertEqual(
                self.client.post(manage_url, {
                    'action': 'assign_complaint',
                    'complaint_id': complaint.pk,
                    'assigned_staff_id': self.staff.pk,
                    'instruction_note': 'Liên hệ khách kiểm tra ngay',
                }).status_code,
                302,
            )
            complaint.refresh_from_db()
            self.assertEqual(complaint.assigned_staff_id, self.staff.pk)
            self.assertEqual(complaint.status, 'Đang xử lý')

            # 5. Staff resolves complaint with compensation voucher
            self.client.force_login(self.staff)
            self.assertEqual(
                self.client.post(manage_url, {
                    'action': 'resolve_complaint',
                    'complaint_id': complaint.pk,
                    'status': 'Đã xử lý',
                    'resolution_note': 'Đã gọi xin lỗi và tặng voucher đền bù.',
                    'issue_voucher': 'true',
                    'discount_value': '100000',
                    'expiry_days': '30',
                }).status_code,
                302,
            )
            complaint.refresh_from_db()
            self.assertEqual(complaint.status, 'Đã xử lý')
            voucher = Voucher.objects.get(complaint=complaint)
            self.assertEqual(voucher.customer_id, self.customer_a.pk)
        finally:
            media_prefix = getattr(settings, 'MEDIA_URL', '/media/')
            for proof_url in complaint.attached_proofs or []:
                rel_path = proof_url[len(media_prefix):] if proof_url.startswith(media_prefix) else proof_url.lstrip('/')
                if rel_path and default_storage.exists(rel_path):
                    default_storage.delete(rel_path)

    def test_resolved_and_rejected_complaints_are_locked_and_no_duplicate_notifications(self):
        manage_url = reverse('feedbacks:admin_management')

        # 1. Reply feedback multiple times -> only 1 notification per feedback/appointment
        self.client.force_login(self.staff)
        for reply_txt in ('Cảm ơn bạn lần 1', 'Cảm ơn bạn lần 2 (cập nhật)'):
            self.assertEqual(
                self.client.post(manage_url, {
                    'action': 'reply_feedback',
                    'feedback_id': self.hidden_feedback.pk,
                    'reply': reply_txt,
                }).status_code,
                302,
            )
        fb_notifs = Notification.objects.filter(
            user=self.customer_a,
            title='Cham Spa đã phản hồi đánh giá của bạn',
        )
        self.assertEqual(fb_notifs.count(), 1)
        self.assertIn('lần 2', fb_notifs.first().content)

        # 2. Repeated assign to the same staff -> only 1 assignment notification
        resolved_comp = Complaint.objects.create(
            complaint_code='COMP-LOCK-001',
            appointment=self.appt,
            customer=self.customer_a,
            description='[Thái độ] Cần xử lý và khóa sau khi hoàn tất',
            status='Chờ phân công',
        )
        self.client.force_login(self.admin)
        for _ in range(2):
            self.client.post(manage_url, {
                'action': 'assign_complaint',
                'complaint_id': resolved_comp.pk,
                'assigned_staff_id': self.staff.pk,
            })
        self.assertEqual(
            Notification.objects.filter(
                user=self.staff,
                title='Phân công xử lý khiếu nại mới',
                content__contains='COMP-LOCK-001',
            ).count(),
            1,
        )

        # 3. Resolve complaint -> locks ticket for BOTH Staff and Admin
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.post(manage_url, {
                'action': 'resolve_complaint',
                'complaint_id': resolved_comp.pk,
                'status': 'Đã xử lý',
                'resolution_note': 'Đã xử lý dứt điểm.',
                'issue_voucher': 'true',
                'discount_value': '100000',
            }).status_code,
            302,
        )
        resolved_comp.refresh_from_db()
        self.assertEqual(resolved_comp.status, 'Đã xử lý')

        # Staff tries to re-resolve / modify -> blocked; UI hides edit form
        self.client.post(manage_url, {
            'action': 'resolve_complaint',
            'complaint_id': resolved_comp.pk,
            'status': 'Đang xử lý',
            'resolution_note': 'Ghi đè trái phép',
        })
        resolved_comp.refresh_from_db()
        self.assertEqual(resolved_comp.status, 'Đã xử lý')
        self.assertEqual(resolved_comp.resolution_note, 'Đã xử lý dứt điểm.')
        self.assertEqual(
            Notification.objects.filter(
                user=self.customer_a,
                title='Cham Spa đã xử lý khiếu nại COMP-LOCK-001',
            ).count(),
            1,
        )
        staff_page = self.client.get(f'{manage_url}?tab=complaints&comp_id={resolved_comp.pk}')
        self.assertEqual(staff_page.status_code, 200)
        self.assertNotContains(staff_page, 'id="formStaffResolve"')
        self.assertContains(staff_page, 'Hồ sơ khiếu nại đã khóa')

        # Admin tries to assign or reject resolved complaint -> blocked; UI hides assign form
        self.client.force_login(self.admin)
        self.client.post(manage_url, {
            'action': 'reject_complaint',
            'complaint_id': resolved_comp.pk,
            'reject_reason': 'Không thể từ chối lại',
        })
        resolved_comp.refresh_from_db()
        self.assertEqual(resolved_comp.status, 'Đã xử lý')
        admin_page = self.client.get(f'{manage_url}?tab=complaints&comp_id={resolved_comp.pk}')
        self.assertEqual(admin_page.status_code, 200)
        self.assertNotContains(admin_page, 'id="formAssignStaff"')
        self.assertContains(admin_page, 'Hồ sơ khiếu nại đã khóa')

        # 4. Rejected complaint is also locked
        rejected_comp = Complaint.objects.create(
            complaint_code='COMP-LOCK-002',
            appointment=self.appt,
            customer=self.customer_a,
            description='[Khác] Ticket kiểm tra khóa sau khi từ chối',
            status='Chờ phân công',
        )
        self.client.post(manage_url, {
            'action': 'reject_complaint',
            'complaint_id': rejected_comp.pk,
            'reject_reason': 'Không đủ căn cứ',
        })
        rejected_comp.refresh_from_db()
        self.assertEqual(rejected_comp.status, 'Đã từ chối')
        self.client.force_login(self.staff)
        self.client.post(manage_url, {
            'action': 'take_complaint',
            'complaint_id': rejected_comp.pk,
        })
        rejected_comp.refresh_from_db()
        self.assertEqual(rejected_comp.status, 'Đã từ chối')
        self.assertIsNone(rejected_comp.assigned_staff)

