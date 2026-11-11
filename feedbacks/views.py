"""
================================================================================
MODULE 04: QUẢN LÝ ĐÁNH GIÁ VÀ KHIẾU NẠI (MOD-04) - TEMPLATE VIEWS
Thành viên phụ trách: NGUYỄN THỊ THANH THẢO
Mục đích:
  - Điều phối và kết xuất (Render) các giao diện HTML cho Module 4:
    1. Giao diện Theo dõi Đánh giá & Phản hồi cá nhân của Khách hàng (Figma Node 217:4864 & Node 694:4).
    2. Giao diện Quản lý Đánh giá & Xử lý Khiếu nại toàn diện của Staff/Admin (UC-4.2, UC-4.3, UC-4.4).
  - Tích hợp chuẩn bộ màu nhận diện Cham Spa, kế thừa layout chung của dự án.
================================================================================
"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation
import os
from urllib.parse import urlencode
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

# Models chuẩn từ core (TUYỆT ĐỐI KHÔNG TẠO MODEL MỚI)
from core.models import (
    Feedback,
    Complaint,
    Appointment,
    AppointmentDetail,
    Notification,
    Voucher,
    User,
)
from marketing.utils import create_unique_notification, generate_notification_code

LOCKED_COMPLAINT_STATUSES = ('Đã xử lý', 'Đã từ chối')
ALLOWED_MEDIA_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov')


def _is_staff_or_admin(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def _save_uploaded_media(files_list):
    """Lưu tối đa 3 ảnh/video tải lên từ form multipart và trả về (urls, had_invalid_only)."""
    if not files_list:
        return [], False
    uploaded_urls = []
    for f in files_list[:3]:
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in ALLOWED_MEDIA_EXTS:
            continue
        unique_filename = f"feedbacks/{timezone.now().strftime('%Y%m')}/{uuid.uuid4().hex[:8]}_{f.name}"
        saved_path = default_storage.save(unique_filename, ContentFile(f.read()))
        uploaded_urls.append(default_storage.url(saved_path))
    return uploaded_urls, (len(uploaded_urls) == 0)


def _validate_completed_appointment(appt_id, user, require_no_feedback=False):
    if not appt_id:
        return None, 'Vui lòng chọn lịch hẹn cần phản hồi.', False
    try:
        appointment = Appointment.objects.get(pk=int(appt_id))
    except (Appointment.DoesNotExist, ValueError, TypeError):
        return None, 'Lịch hẹn không tồn tại trong hệ thống.', False

    if not _is_staff_or_admin(user) and appointment.user_id and appointment.user_id != user.id:
        return None, 'Bạn không có quyền gửi phản hồi cho lịch hẹn này.', True

    if appointment.status != 'Completed':
        return None, f'Chỉ có thể gửi cho lịch hẹn đã hoàn thành (Trạng thái hiện tại: {appointment.status}).', False

    if require_no_feedback and hasattr(appointment, 'feedback') and appointment.feedback:
        return None, 'Lịch hẹn này đã được gửi đánh giá trước đó.', False

    return appointment, None, False


def _handle_customer_feedback_post(request):
    """Xử lý Form POST gửi Đánh giá hoặc Khiếu nại từ khách hàng."""
    action = (request.POST.get('action') or '').strip()
    reviews_url = f"{reverse('feedbacks:customer_tracking')}?tab=reviews"
    complaints_url = f"{reverse('feedbacks:customer_tracking')}?tab=complaints"

    if action == 'submit_feedback':
        appointment, err_msg, is_forbidden = _validate_completed_appointment(
            request.POST.get('appointment_id'), request.user, require_no_feedback=True
        )
        if is_forbidden:
            raise PermissionDenied(err_msg)
        if err_msg:
            messages.error(request, err_msg)
            return redirect(reviews_url)

        try:
            rating = int(request.POST.get('rating', 0))
            if not 1 <= rating <= 5:
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, 'Điểm đánh giá phải từ 1 đến 5 sao.')
            return redirect(reviews_url)

        tags = [str(t).strip()[:100] for t in request.POST.getlist('tags') if str(t).strip()]
        comment = str(request.POST.get('comment') or '').strip()
        attached_media, invalid_media = _save_uploaded_media(request.FILES.getlist('media_files'))
        if invalid_media:
            messages.error(request, 'Định dạng tệp không được hỗ trợ. Vui lòng chọn ảnh (jpg, png, webp) hoặc video ngắn.')
            return redirect(reviews_url)

        customer = request.user
        today_str = timezone.now().strftime('%Y%m%d')
        fb_code = f'FB-{today_str}-{uuid.uuid4().hex[:4].upper()}'

        feedback = Feedback.objects.create(
            feedback_code=fb_code,
            appointment=appointment,
            customer=customer,
            rating=rating,
            tags=tags,
            comment=comment,
            attached_media=attached_media,
            status='Chờ phản hồi',
        )
        messages.success(request, f'Đã gửi đánh giá {feedback.feedback_code} thành công! Cảm ơn bạn đã tin tưởng Cham Spa.')
        return redirect(reviews_url)

    if action == 'submit_complaint':
        appointment, err_msg, is_forbidden = _validate_completed_appointment(
            request.POST.get('appointment_id'), request.user, require_no_feedback=False
        )
        if is_forbidden:
            raise PermissionDenied(err_msg)
        if err_msg:
            messages.error(request, err_msg)
            return redirect(complaints_url)

        desc_text = str(request.POST.get('description') or '').strip()
        if len(desc_text) < 5:
            messages.error(request, 'Vui lòng nhập mô tả sự cố tối thiểu 5 ký tự.')
            return redirect(complaints_url)

        category = str(request.POST.get('category') or 'Chất lượng dịch vụ').strip()
        desired_resolution = str(request.POST.get('desired_resolution') or '').strip()[:200]
        attached_proofs, invalid_proofs = _save_uploaded_media(request.FILES.getlist('proof_files'))
        if invalid_proofs:
            messages.error(request, 'Định dạng tệp bằng chứng không được hỗ trợ. Vui lòng chọn ảnh (jpg, png, webp) hoặc video ngắn.')
            return redirect(complaints_url)

        today_str = timezone.now().strftime('%Y%m%d')
        comp_code = f'COMP-{today_str}-{uuid.uuid4().hex[:4].upper()}'

        complaint = Complaint.objects.create(
            complaint_code=comp_code,
            appointment=appointment,
            customer=request.user,
            description=f'[{category}] {desc_text}',
            desired_resolution=desired_resolution,
            attached_proofs=attached_proofs,
            status='Chờ phân công',
        )

        try:
            for adm in User.objects.filter(is_superuser=True, is_active=True):
                create_unique_notification(
                    user=adm,
                    title=f'Khiếu nại dịch vụ mới: {comp_code}',
                    content=(
                        f'Khách hàng {request.user.name or request.user.username} vừa gửi khiếu nại '
                        f'liên quan đến lịch hẹn {appointment.appointment_code}: "{desc_text[:100]}..."'
                    ),
                    prefix='TB-COMP',
                    delivery_channels='Web',
                    status='Đã gửi',
                )
        except Exception:
            pass

        messages.success(request, f'Đã tiếp nhận khiếu nại {complaint.complaint_code}. Bộ phận CSKH sẽ liên hệ hỗ trợ bạn sớm nhất.')
        return redirect(complaints_url)

    messages.error(request, 'Thao tác không hợp lệ.')
    return redirect(reviews_url)


@login_required
def customer_feedback_tracking(request):
    """
    [Figma Node 217:4864 & 694:4] Giao diện cá nhân dành cho Khách hàng:
    - Tab 1 (Node 217:4864): Tiến độ xử lý khiếu nại (Gửi -> Tiếp nhận -> Xử lý & Voucher).
    - Tab 2 (Node 694:4): Lịch sử các đánh giá sao và phản hồi từ đại diện Cham Spa.
    - Tích hợp Modal đánh giá & khiếu nại qua Form POST chuẩn.
    - Tự động mở Modal đánh giá nếu có tham số ?appointment=<id> trên URL.
    """
    if request.method == 'POST':
        return _handle_customer_feedback_post(request)

    user = request.user

    # 1. Lấy danh sách đánh giá của khách hàng (sắp xếp mới nhất)
    feedbacks_qs = Feedback.objects.filter(customer=user).select_related(
        'appointment', 'replied_by'
    ).prefetch_related('appointment__details__service').order_by('-created_at')

    # 2. Lấy danh sách khiếu nại của khách hàng (kèm voucher đền bù)
    complaints_qs = Complaint.objects.filter(customer=user).select_related(
        'appointment', 'assigned_staff', 'compensated_voucher'
    ).prefetch_related('appointment__details__service').order_by('-created_at')

    # 3. Đếm số lượng thống kê theo trạng thái khiếu nại (Node 217:4864 Sub-tabs)
    complaint_counts = {
        'all': complaints_qs.count(),
        'pending': complaints_qs.filter(status__in=['Chờ phân công', 'Đang xử lý', 'Chờ liên hệ lại']).count(),
        'resolved': complaints_qs.filter(status='Đã xử lý').count(),
        'rejected': complaints_qs.filter(status='Đã từ chối').count(),
    }

    # Đếm số lượng đánh giá
    feedback_counts = {
        'all': feedbacks_qs.count(),
        'replied': feedbacks_qs.filter(status='Đã phản hồi').count(),
        'waiting': feedbacks_qs.filter(status='Chờ phản hồi').count(),
    }

    # 4. Bộ lọc trên giao diện
    active_tab = request.GET.get('tab', 'complaints')  # Mặc định theo Node 217:4864 là tab khiếu nại
    complaint_filter = request.GET.get('status', 'all')

    filtered_complaints = complaints_qs
    if complaint_filter == 'pending':
        filtered_complaints = complaints_qs.filter(status__in=['Chờ phân công', 'Đang xử lý', 'Chờ liên hệ lại'])
    elif complaint_filter == 'resolved':
        filtered_complaints = complaints_qs.filter(status='Đã xử lý')
    elif complaint_filter == 'rejected':
        filtered_complaints = complaints_qs.filter(status='Đã từ chối')

    # 5. Danh sách các lịch hẹn đã hoàn thành (Completed) của khách hàng
    # Phục vụ người dùng chọn lịch hẹn khi gửi Đánh giá hoặc Khiếu nại mới
    completed_appointments = Appointment.objects.filter(
        user=user,
        status='Completed'
    ).select_related('feedback').prefetch_related('details__service').order_by('-appointment_date', '-time_slot')

    # 6. Kiểm tra nếu có appointment ID được chỉ định qua Query Param (ví dụ từ trang Lịch cá nhân sang)
    target_appointment_id = request.GET.get('appointment')
    target_appointment = None
    if target_appointment_id:
        try:
            target_appointment = Appointment.objects.filter(
                pk=target_appointment_id,
                user=user,
                status='Completed'
            ).select_related('feedback').prefetch_related('details__service').first()
        except Exception:
            target_appointment = None

    first_completed = completed_appointments.first()
    default_appointment_id = (
        target_appointment.id if target_appointment
        else (first_completed.id if first_completed else '')
    )

    context = {
        'user': user,
        'feedbacks': feedbacks_qs,
        'complaints': filtered_complaints,
        'complaint_counts': complaint_counts,
        'feedback_counts': feedback_counts,
        'active_tab': active_tab,
        'complaint_filter': complaint_filter,
        'completed_appointments': completed_appointments,
        'target_appointment': target_appointment,
        'target_appointment_id': target_appointment.id if target_appointment else None,
        'default_appointment_id': default_appointment_id,
    }

    return render(request, 'feedbacks/customer_tracking.html', context)


def _admin_redirect_url(request, tab, obj_id=None):
    base = reverse('feedbacks:admin_management')
    params = {'tab': tab}
    if tab == 'feedbacks':
        if obj_id:
            params['fb_id'] = obj_id
        for post_key, qs_key in (('filter_rating_tab', 'rating_tab'), ('filter_q', 'q'), ('filter_page', 'page')):
            val = (request.POST.get(post_key) or '').strip()
            if val:
                params[qs_key] = val
    else:
        if obj_id:
            params['comp_id'] = obj_id
        for post_key, qs_key in (
            ('filter_comp_tab', 'comp_tab'),
            ('filter_staff_id', 'staff_id'),
            ('filter_comp_q', 'comp_q'),
            ('filter_comp_page', 'comp_page'),
        ):
            val = (request.POST.get(post_key) or '').strip()
            if val:
                params[qs_key] = val
    return f"{base}?{urlencode(params)}"


def _redirect_if_complaint_locked(request, complaint):
    """Khóa khiếu nại sau khi đã xử lý xong hoặc đã từ chối."""
    if complaint.status in LOCKED_COMPLAINT_STATUSES:
        messages.error(
            request,
            f'Khiếu nại {complaint.complaint_code} đã hoàn tất ({complaint.status}) và được khóa, không thể chỉnh sửa thêm.',
        )
        return redirect(_admin_redirect_url(request, 'complaints', complaint.id))
    return None


def _handle_admin_feedback_post(request):
    """Xử lý các thao tác Form POST trên Dashboard Quản lý Đánh giá & Khiếu nại."""
    action = (request.POST.get('action') or '').strip()

    if action == 'toggle_feedback_status':
        fb_id = (request.POST.get('feedback_id') or '').strip()
        if not fb_id.isdigit():
            messages.error(request, "Không tìm thấy đánh giá cần cập nhật.")
            return redirect(_admin_redirect_url(request, 'feedbacks'))
        feedback = get_object_or_404(Feedback, pk=int(fb_id))
        toggle_action = (request.POST.get('toggle_action') or 'toggle').strip()
        if toggle_action == 'hide' or (toggle_action == 'toggle' and feedback.status != 'Đã ẩn'):
            feedback.status = 'Đã ẩn'
            msg = f'Đã ẩn đánh giá {feedback.feedback_code} thành công!'
        else:
            feedback.status = 'Đã phản hồi' if feedback.reply else 'Chờ phản hồi'
            msg = f'Đã hiển thị lại đánh giá {feedback.feedback_code} thành công!'
        feedback.save(update_fields=['status'])
        messages.success(request, msg)
        selected_fb_id = (request.POST.get('selected_fb_id') or '').strip()
        target_id = int(selected_fb_id) if selected_fb_id.isdigit() else feedback.id
        return redirect(_admin_redirect_url(request, 'feedbacks', target_id))

    if action == 'reply_feedback':
        fb_id = (request.POST.get('feedback_id') or '').strip()
        if not fb_id.isdigit():
            messages.error(request, "Không tìm thấy đánh giá cần phản hồi.")
            return redirect(_admin_redirect_url(request, 'feedbacks'))
        feedback = get_object_or_404(Feedback, pk=int(fb_id))
        reply_text = str(request.POST.get('reply') or '').strip()
        if len(reply_text) < 2:
            messages.error(request, "Nội dung phản hồi phải có ít nhất 2 ký tự.")
            return redirect(_admin_redirect_url(request, 'feedbacks', feedback.id))

        feedback.reply = reply_text
        feedback.replied_by = request.user
        feedback.replied_at = timezone.now()
        feedback.status = 'Đã phản hồi'
        feedback.save()

        try:
            reply_title = 'Cham Spa đã phản hồi đánh giá của bạn'
            reply_content = (
                f'Đại diện Cham Spa ({feedback.replied_by.name or feedback.replied_by.username}) '
                f'đã phản hồi đánh giá của bạn cho lịch hẹn {feedback.appointment.appointment_code}: "{feedback.reply}"'
            )
            existing_fb_notif = Notification.objects.filter(
                user=feedback.customer,
                title=reply_title,
                content__contains=feedback.appointment.appointment_code,
            ).order_by('-id').first()
            if existing_fb_notif:
                changed_fields = []
                if existing_fb_notif.content != reply_content:
                    existing_fb_notif.content = reply_content
                    changed_fields.append('content')
                if not existing_fb_notif.notification_code:
                    existing_fb_notif.notification_code = generate_notification_code('TB-FB')
                    changed_fields.append('notification_code')
                if changed_fields:
                    existing_fb_notif.save(update_fields=changed_fields)
            else:
                create_unique_notification(
                    user=feedback.customer,
                    title=reply_title,
                    content=reply_content,
                    prefix='TB-FB',
                    delivery_channels='Web',
                    status='Đã gửi',
                )
        except Exception:
            pass

        messages.success(request, f'Đã gửi phản hồi công khai cho đánh giá {feedback.feedback_code} thành công!')
        return redirect(_admin_redirect_url(request, 'feedbacks', feedback.id))

    if action in ('assign_complaint', 'reject_complaint'):
        if not request.user.is_superuser:
            raise PermissionDenied("Chỉ Quản lý mới có quyền phân công hoặc từ chối khiếu nại.")

        comp_id = (request.POST.get('complaint_id') or '').strip()
        if not comp_id.isdigit():
            messages.error(request, "Không tìm thấy ticket khiếu nại.")
            return redirect(_admin_redirect_url(request, 'complaints'))
        complaint = get_object_or_404(Complaint, pk=int(comp_id))

        locked_resp = _redirect_if_complaint_locked(request, complaint)
        if locked_resp:
            return locked_resp

        if action == 'reject_complaint':
            complaint.status = 'Đã từ chối'
            reject_reason = str(request.POST.get('reject_reason') or request.POST.get('instruction_note') or '').strip()
            if reject_reason:
                complaint.resolution_note = f'Từ chối: {reject_reason}'
            complaint.save()
            messages.success(request, f'Đã từ chối khiếu nại {complaint.complaint_code}.')
            return redirect(_admin_redirect_url(request, 'complaints', complaint.id))

        staff_id = (request.POST.get('assigned_staff_id') or '').strip()
        if not staff_id.isdigit():
            messages.error(request, "Vui lòng chọn nhân viên CSKH phụ trách.")
            return redirect(_admin_redirect_url(request, 'complaints', complaint.id))

        staff = get_object_or_404(User, pk=int(staff_id))
        prev_staff_id = complaint.assigned_staff_id
        complaint.assigned_staff = staff
        if complaint.status == 'Chờ phân công':
            complaint.status = 'Đang xử lý'

        instruction = str(request.POST.get('instruction_note') or '').strip()
        if instruction:
            complaint.resolution_note = f'[Chỉ đạo quản lý]: {instruction}'
        complaint.save()

        try:
            assign_title = 'Phân công xử lý khiếu nại mới'
            assign_content = f'Quản lý đã phân công bạn xử lý khiếu nại {complaint.complaint_code} từ khách hàng {complaint.customer.name or complaint.customer.username}.'
            if prev_staff_id != staff.id or not Notification.objects.filter(
                user=staff,
                title=assign_title,
                content__contains=complaint.complaint_code,
            ).exists():
                create_unique_notification(
                    user=staff,
                    title=assign_title,
                    content=assign_content,
                    prefix='TB-COMP',
                    delivery_channels='Web',
                    status='Đã gửi',
                )
        except Exception:
            pass

        messages.success(
            request,
            f'Đã phân công khiếu nại {complaint.complaint_code} cho chuyên viên {staff.name or staff.username} thành công!',
        )
        return redirect(_admin_redirect_url(request, 'complaints', complaint.id))

    if action == 'take_complaint':
        comp_id = (request.POST.get('complaint_id') or '').strip()
        if not comp_id.isdigit():
            messages.error(request, "Không tìm thấy ticket khiếu nại.")
            return redirect(_admin_redirect_url(request, 'complaints'))
        complaint = get_object_or_404(Complaint, pk=int(comp_id))

        locked_resp = _redirect_if_complaint_locked(request, complaint)
        if locked_resp:
            return locked_resp

        complaint.assigned_staff = request.user
        if complaint.status == 'Chờ phân công':
            complaint.status = 'Đang xử lý'
        complaint.save()
        messages.success(request, f'Đã tiếp nhận xử lý ticket {complaint.complaint_code} thành công!')
        return redirect(_admin_redirect_url(request, 'complaints', complaint.id))

    if action == 'resolve_complaint':
        comp_id = (request.POST.get('complaint_id') or '').strip()
        if not comp_id.isdigit():
            messages.error(request, "Không tìm thấy ticket khiếu nại.")
            return redirect(_admin_redirect_url(request, 'complaints'))
        complaint = get_object_or_404(Complaint, pk=int(comp_id))

        locked_resp = _redirect_if_complaint_locked(request, complaint)
        if locked_resp:
            return locked_resp

        resolution_note = str(request.POST.get('resolution_note') or '').strip()
        if len(resolution_note) < 2:
            messages.error(request, "Ghi chú xử lý phải có ít nhất 2 ký tự.")
            return redirect(_admin_redirect_url(request, 'complaints', complaint.id))

        new_status = (request.POST.get('status') or 'Đã xử lý').strip()
        valid_statuses = {c[0] for c in Complaint.STATUS_CHOICES}
        if new_status not in valid_statuses:
            messages.error(request, "Trạng thái xử lý khiếu nại không hợp lệ.")
            return redirect(_admin_redirect_url(request, 'complaints', complaint.id))

        issue_voucher = str(request.POST.get('issue_voucher') or '').lower() in ('on', 'true', '1', 'yes')
        created_voucher = None

        with transaction.atomic():
            complaint.status = new_status
            complaint.resolution_note = resolution_note

            if not request.user.is_superuser:
                if not complaint.assigned_staff:
                    complaint.assigned_staff = request.user
            else:
                assigned_staff_id = (request.POST.get('assigned_staff_id') or '').strip()
                if assigned_staff_id.isdigit():
                    staff_user = User.objects.filter(pk=int(assigned_staff_id), is_staff=True).first()
                    if staff_user:
                        complaint.assigned_staff = staff_user
                elif not complaint.assigned_staff:
                    complaint.assigned_staff = request.user

            complaint.save()

            if issue_voucher and not getattr(complaint, 'compensated_voucher', None):
                base_code = complaint.complaint_code.replace('-', '')
                voucher_code = f'DENBU-{base_code[-6:]}'
                cnt = 1
                while Voucher.objects.filter(voucher_code=voucher_code).exists():
                    voucher_code = f'DENBU-{base_code[-6:]}-{cnt}'
                    cnt += 1

                try:
                    expiry_days = max(1, int(request.POST.get('expiry_days') or 30))
                except (TypeError, ValueError):
                    expiry_days = 30
                expiry_date = timezone.now() + timedelta(days=expiry_days)

                try:
                    disc_val = Decimal(str(request.POST.get('discount_value') or 100000))
                except (InvalidOperation, ValueError):
                    disc_val = Decimal(100000)

                max_disc = None
                raw_max = (request.POST.get('max_discount_amount') or '').strip()
                if raw_max:
                    try:
                        max_disc = Decimal(raw_max)
                    except (InvalidOperation, ValueError):
                        pass

                try:
                    min_ord = Decimal(str(request.POST.get('min_order_amount') or 0))
                except (InvalidOperation, ValueError):
                    min_ord = Decimal(0)

                disc_type = (request.POST.get('discount_type') or 'FIXED').strip()
                created_voucher = Voucher.objects.create(
                    voucher_code=voucher_code,
                    complaint=complaint,
                    customer=complaint.customer,
                    discount_type=disc_type,
                    discount_value=disc_val,
                    max_discount_amount=max_disc,
                    min_order_amount=min_ord,
                    status='Khả dụng',
                    expiry_date=expiry_date,
                )

                val_display = f'{int(created_voucher.discount_value)}%' if created_voucher.discount_type == 'PERCENT' else f'{int(created_voucher.discount_value):,}đ'
                create_unique_notification(
                    user=complaint.customer,
                    title=f'Cham Spa đã xử lý khiếu nại {complaint.complaint_code}',
                    content=(
                        f'Kính gửi quý khách, khiếu nại {complaint.complaint_code} đã được ghi nhận và xử lý: '
                        f'"{complaint.resolution_note}". Cham Spa xin gửi tặng bạn mã Voucher đền bù '
                        f'{created_voucher.voucher_code} (Giảm {val_display}, hạn dùng đến {expiry_date.strftime("%d/%m/%Y")}).'
                    ),
                    prefix='TB-COMP',
                    delivery_channels='Web',
                    status='Đã gửi',
                    dedup_title_only=True,
                )
            elif complaint.status == 'Đã xử lý':
                try:
                    create_unique_notification(
                        user=complaint.customer,
                        title=f'Cham Spa đã xử lý khiếu nại {complaint.complaint_code}',
                        content=(
                            f'Kính gửi quý khách, khiếu nại {complaint.complaint_code} đã được xử lý thỏa đáng: '
                            f'"{complaint.resolution_note}". Cham Spa xin chân thành cảm ơn phản hồi đóng góp của quý khách!'
                        ),
                        prefix='TB-COMP',
                        delivery_channels='Web',
                        status='Đã gửi',
                        dedup_title_only=True,
                    )
                except Exception:
                    pass

        msg = f'Đã cập nhật kết quả xử lý khiếu nại {complaint.complaint_code} thành công!'
        if created_voucher:
            msg += f' Đã tạo mã voucher đền bù: {created_voucher.voucher_code}.'
        messages.success(request, msg)
        return redirect(_admin_redirect_url(request, 'complaints', complaint.id))

    messages.error(request, "Thao tác không hợp lệ.")
    return redirect(_admin_redirect_url(request, 'feedbacks'))


@login_required
def admin_feedback_management(request):
    """
    [UC-4.2, UC-4.3, UC-4.4] Master-Detail Dashboard Quản lý Đánh giá & Khiếu nại (Figma Node 217-7569 & 217-6127):
    - Kế thừa động layout: layouts/admin_layout.html (Admin) hoặc layouts/staff_layout.html (Staff).
    - Tab 1: Quản lý Đánh giá (Figma 217-7569): KPI cards, Danh sách Master, Panel Detail phản hồi công khai & duyệt/ẩn.
    - Tab 2: Quản lý Khiếu nại (Figma 217-6127): KPI tickets, Danh sách Master, Stepper quy trình, Phân công CSKH & SLA.
    """
    # Ràng buộc bảo mật: Chỉ cho phép Nhân viên hoặc Quản lý truy cập
    if not _is_staff_or_admin(request.user):
        if request.method == 'POST':
            raise PermissionDenied("Bạn không có quyền thực hiện thao tác này.")
        messages.error(request, "Bạn không có quyền truy cập trang quản lý đánh giá và khiếu nại.")
        return redirect('home')

    if request.method == 'POST':
        return _handle_admin_feedback_post(request)

    # Xác định layout kế thừa tương ứng
    base_layout = "layouts/admin_layout.html" if request.user.is_superuser else "layouts/staff_layout.html"

    # Tab đang chọn: 'feedbacks' (Mặc định) hoặc 'complaints'
    active_tab = request.GET.get('tab', 'feedbacks')
    now = timezone.now()

    # =========================================================================
    # 1. DỮ LIỆU TAB ĐÁNH GIÁ (FEEDBACKS - FIGMA NODE 217-7569)
    # =========================================================================
    feedbacks_base_qs = Feedback.objects.all().select_related(
        'appointment', 'customer', 'replied_by'
    ).prefetch_related('appointment__details__service').order_by('-created_at')

    # Thống kê tổng quan Feedbacks (Figma 217-7569 KPI)
    total_feedbacks = feedbacks_base_qs.count()
    avg_rating = feedbacks_base_qs.aggregate(avg=Avg('rating'))['avg'] or 5.0
    waiting_feedbacks_count = feedbacks_base_qs.filter(status='Chờ phản hồi').count()
    hidden_feedbacks_count = feedbacks_base_qs.filter(status='Đã ẩn').count()
    monthly_feedbacks_count = feedbacks_base_qs.filter(created_at__year=now.year, created_at__month=now.month).count()
    approval_rate = int(((total_feedbacks - hidden_feedbacks_count) / total_feedbacks * 100)) if total_feedbacks > 0 else 100

    # Bộ lọc tab pills cho Feedbacks
    rating_tab = request.GET.get('rating_tab', 'all')
    feedbacks_filtered_qs = feedbacks_base_qs

    if rating_tab == '5':
        feedbacks_filtered_qs = feedbacks_filtered_qs.filter(rating=5)
    elif rating_tab == 'low':
        feedbacks_filtered_qs = feedbacks_filtered_qs.filter(rating__lte=3)
    elif rating_tab == 'waiting':
        feedbacks_filtered_qs = feedbacks_filtered_qs.filter(status='Chờ phản hồi')

    # Tìm kiếm theo tên khách, mã lịch hẹn, mã đánh giá, nhận xét
    fb_search = request.GET.get('q', '').strip()
    if fb_search:
        feedbacks_filtered_qs = feedbacks_filtered_qs.filter(
            Q(feedback_code__icontains=fb_search) |
            Q(customer__name__icontains=fb_search) |
            Q(customer__phone__icontains=fb_search) |
            Q(appointment__appointment_code__icontains=fb_search) |
            Q(comment__icontains=fb_search)
        )

    # Phân trang cho Feedbacks (6 bản ghi / trang để vừa vặn Master list)
    fb_paginator = Paginator(feedbacks_filtered_qs, 6)
    fb_page_number = request.GET.get('page', 1)
    feedbacks_page = fb_paginator.get_page(fb_page_number)

    # Feedback được chọn hiển thị ở Cột phải (Detail Panel)
    selected_fb_id = request.GET.get('fb_id')
    selected_feedback = None
    if selected_fb_id:
        selected_feedback = feedbacks_base_qs.filter(pk=selected_fb_id).first()
    if not selected_feedback and feedbacks_page.object_list:
        selected_feedback = feedbacks_page.object_list[0]

    # =========================================================================
    # 2. DỮ LIỆU TAB KHIẾU NẠI (COMPLAINTS - FIGMA NODE 217-6127)
    # =========================================================================
    complaints_base_qs = Complaint.objects.all().select_related(
        'appointment', 'customer', 'assigned_staff', 'compensated_voucher'
    ).prefetch_related('appointment__details__service').order_by('-created_at')

    # Thống kê tổng quan Complaints (Figma 217-6127 KPI)
    total_complaints = complaints_base_qs.count()
    pending_assign_count = complaints_base_qs.filter(status='Chờ phân công').count()
    processing_count = complaints_base_qs.filter(status__in=['Đang xử lý', 'Chờ liên hệ lại']).count()
    resolved_complaints_count = complaints_base_qs.filter(status='Đã xử lý').count()
    rejected_complaints_count = complaints_base_qs.filter(status='Đã từ chối').count()

    # Bộ lọc tab pills cho Complaints
    comp_tab = request.GET.get('comp_tab', 'all')
    complaints_filtered_qs = complaints_base_qs

    if comp_tab == 'pending_assign':
        complaints_filtered_qs = complaints_filtered_qs.filter(status='Chờ phân công')
    elif comp_tab == 'processing':
        complaints_filtered_qs = complaints_filtered_qs.filter(status__in=['Đang xử lý', 'Chờ liên hệ lại'])
    elif comp_tab == 'resolved':
        complaints_filtered_qs = complaints_filtered_qs.filter(status='Đã xử lý')

    # Lọc theo nhân viên CSKH
    staff_filter = request.GET.get('staff_id', 'all')
    if staff_filter and staff_filter != 'all':
        try:
            complaints_filtered_qs = complaints_filtered_qs.filter(assigned_staff_id=int(staff_filter))
        except (ValueError, TypeError):
            pass

    # Tìm kiếm khiếu nại
    comp_search = request.GET.get('comp_q', '').strip()
    if comp_search:
        complaints_filtered_qs = complaints_filtered_qs.filter(
            Q(complaint_code__icontains=comp_search) |
            Q(customer__name__icontains=comp_search) |
            Q(customer__phone__icontains=comp_search) |
            Q(appointment__appointment_code__icontains=comp_search) |
            Q(description__icontains=comp_search)
        )

    # Phân trang cho Complaints (6 ticket / trang)
    comp_paginator = Paginator(complaints_filtered_qs, 6)
    comp_page_number = request.GET.get('comp_page', 1)
    complaints_page = comp_paginator.get_page(comp_page_number)

    # Complaint được chọn hiển thị ở Cột phải (Detail Panel)
    selected_comp_id = request.GET.get('comp_id')
    selected_complaint = None
    if selected_comp_id:
        selected_complaint = complaints_base_qs.filter(pk=selected_comp_id).first()
    if not selected_complaint and complaints_page.object_list:
        selected_complaint = complaints_page.object_list[0]

    # Danh sách nhân viên CSKH / Staff để phân công
    staff_list = User.objects.filter(is_staff=True, is_active=True).order_by('name')

    context = {
        'base_layout': base_layout,
        'active_tab': active_tab,

        # Feedbacks Context (Figma 217-7569)
        'feedbacks': feedbacks_page,
        'selected_feedback': selected_feedback,
        'total_feedbacks': total_feedbacks,
        'avg_rating': f"{avg_rating:.1f}",
        'avg_rating_float': avg_rating,
        'waiting_feedbacks_count': waiting_feedbacks_count,
        'monthly_feedbacks_count': monthly_feedbacks_count,
        'approval_rate': approval_rate,
        'hidden_feedbacks_count': hidden_feedbacks_count,
        'rating_tab': rating_tab,
        'fb_search': fb_search,

        # Complaints Context (Figma 217-6127)
        'complaints': complaints_page,
        'selected_complaint': selected_complaint,
        'total_complaints': total_complaints,
        'pending_assign_count': pending_assign_count,
        'processing_count': processing_count,
        'resolved_complaints_count': resolved_complaints_count,
        'rejected_complaints_count': rejected_complaints_count,
        'comp_tab': comp_tab,
        'staff_filter': staff_filter,
        'comp_search': comp_search,

        # Nhân sự phân công
        'staff_list': staff_list,
    }

    return render(request, 'feedbacks/admin_management.html', context)
