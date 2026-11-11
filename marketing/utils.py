"""
================================================================================
MODULE 07: QUẢN LÝ THÔNG BÁO & KHUYẾN MÃI (MOD-07) - UTILITIES & HELPERS
Thành viên phụ trách: MINH KHA
Mục đích:
  - Cung cấp hàm helper chuẩn create_system_notification() dùng chung toàn Spa (UC-7.5).
  - Tối ưu hóa hiệu năng gửi thông báo hàng loạt (bulk_create) cho toàn bộ khách hàng/nhân viên (UC-7.3).
  - Cung cấp hàm khởi tạo dữ liệu mẫu phong phú phục vụ vấn đáp và bảo vệ đồ án.
================================================================================
"""

import time
import uuid
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from core.models import Notification, Promotion, Voucher, User


def exclude_ktv_shift_notifications(qs):
    """Loại bỏ thông báo ca trực và lịch hẹn KTV khỏi luồng thông báo Staff."""
    return qs.exclude(
        Q(title__icontains='ca trực')
        | Q(content__icontains='ca trực')
        | Q(content__icontains='ca trị liệu')
        | Q(title__icontains='lịch hẹn')
    )


def exclude_customer_notifications(qs):
    """
    Loại bỏ các thông báo nghiệp vụ dành cho Khách hàng (tích điểm, thăng hạng,
    nhắc/xác nhận lịch hẹn cá nhân, tặng voucher, phản hồi gửi quý khách...)
    khi hiển thị ở luồng thông báo của Admin hoặc Staff.
    """
    return qs.exclude(
        Q(notification_code__startswith='TB-PTS-')
        | Q(notification_code__startswith='TB-TIER-')
        | Q(notification_code__startswith='TB-CUS-')
        | Q(notification_code__startswith='TB-CONF')
        | Q(notification_code__startswith='TB-STAT')
        | Q(promotion__isnull=False)
        | Q(title__icontains='điểm thưởng')
        | Q(title__icontains='bạn vừa được cộng')
        | Q(title__icontains='thăng hạng')
        | Q(title__icontains='nhắc lịch hẹn')
        | Q(title__icontains='tặng bạn')
        | Q(title__icontains='tặng mã voucher')
        | Q(title__icontains='chào mừng bạn')
        | Q(title__icontains='lịch hẹn đã được xác nhận')
        | Q(title__icontains='đặt lịch thành công')
        | Q(title__icontains='dời lịch thành công')
        | Q(title__icontains='đã hủy lịch hẹn')
        | Q(title__icontains='xác nhận yêu cầu hủy lịch hẹn')
        | Q(title__icontains='cập nhật lịch hẹn #')
        | Q(title__icontains='cham spa đã')
        | Q(title__icontains='khiếu nại của bạn')
        | Q(content__icontains='quý khách')
        | Q(content__icontains='số dư điểm hiện tại')
        | Q(content__icontains='trong ví voucher')
    )


def filter_notifications_for_user(qs, user):
    """
    Lọc thông báo phù hợp đúng vai trò người dùng:
      - Admin: loại trừ thông báo của Khách hàng nếu bị gắn nhầm vào tài khoản quản trị.
      - Staff: loại trừ cả thông báo của Khách hàng lẫn ca trực / lịch hẹn KTV.
      - Customer: giữ nguyên toàn bộ thông báo của khách hàng.
    """
    if user and getattr(user, 'is_superuser', False):
        return exclude_customer_notifications(qs)
    if user and getattr(user, 'is_staff', False):
        return exclude_ktv_shift_notifications(exclude_customer_notifications(qs))
    return qs


def generate_notification_code(prefix="TB"):
    """
    Sinh mã thông báo duy nhất theo thời gian thực (Timestamp + UUID rút gọn).
    Ví dụ: TB-1731112233-A1B2
    """
    timestamp = int(timezone.now().timestamp())
    rand_suffix = uuid.uuid4().hex[:4].upper()
    return f"{prefix}-{timestamp}-{rand_suffix}"


_CATEGORY_METADATA = {
    'appointment': {
        'category': 'appointment',
        'label': 'Lịch hẹn',
        'badge_label': 'Lịch hẹn',
        'icon': 'bi-calendar-check',
        'color': '#0D6EFD',
        'badge_class': 'badge bg-primary text-white px-2 py-1',
        'badge_style': 'font-size: 11px;',
        'action_url_name': 'appointment:my_appointments',
        'action_query': '',
        'action_label': 'Xem lịch hẹn',
    },
    'voucher': {
        'category': 'voucher',
        'label': 'Ưu đãi & Voucher',
        'badge_label': 'Ưu đãi',
        'icon': 'bi-tag-fill',
        'color': '#781A24',
        'badge_class': 'badge text-white px-2 py-1',
        'badge_style': 'background-color: #781A24; font-size: 11px;',
        'action_url_name': 'marketing:promotions',
        'action_query': '?tab=vouchers',
        'action_label': 'Xem ví Voucher',
    },
    'complaint': {
        'category': 'complaint',
        'label': 'Khiếu nại & CSKH',
        'badge_label': 'Khiếu nại',
        'icon': 'bi-shield-exclamation',
        'color': '#DC3545',
        'badge_class': 'badge bg-danger text-white px-2 py-1',
        'badge_style': 'font-size: 11px;',
        'action_url_name': 'feedbacks:my_feedbacks',
        'action_query': '',
        'action_label': 'Xem tiến độ xử lý',
    },
    'membership': {
        'category': 'membership',
        'label': 'Hội viên & Điểm thưởng',
        'badge_label': 'Hội viên',
        'icon': 'bi-gem',
        'color': '#D0B581',
        'badge_class': 'badge px-2 py-1',
        'badge_style': 'background-color: #F4EFE3; color: #781A24; border: 1px solid #D0B581; font-size: 11px;',
        'action_url_name': 'membership:my_card',
        'action_query': '',
        'action_label': 'Xem thẻ Hội viên',
    },
    'payment': {
        'category': 'payment',
        'label': 'Thanh toán',
        'badge_label': 'Thanh toán',
        'icon': 'bi-receipt-cutoff',
        'color': '#198754',
        'badge_class': 'badge bg-success text-white px-2 py-1',
        'badge_style': 'font-size: 11px;',
        'action_url_name': None,
        'action_query': '',
        'action_label': '',
    },
    'system': {
        'category': 'system',
        'label': 'Hệ thống',
        'badge_label': 'Hệ thống',
        'icon': 'bi-bell-fill',
        'color': '#6C757D',
        'badge_class': 'badge bg-secondary text-white px-2 py-1',
        'badge_style': 'font-size: 11px;',
        'action_url_name': None,
        'action_query': '',
        'action_label': '',
    },
}


def classify_notification(notif):
    """
    Phân loại duy nhất và loại trừ lẫn nhau cho từng Notification (1 thông báo = 1 loại).
    Thứ tự ưu tiên:
      1. Tiền tố notification_code (TB-COMP, TB-FB, TB-PTS/TIER/ADJ, TB-CONFIRM/RESCHED/CANCEL/STATUS)
      2. Có gắn promotion -> voucher
      3. Từ khóa trong title (tránh từ khóa phụ trong content kéo nhầm loại)
      4. Fallback từ khóa trong content nếu title không đặc thù
      5. Mặc định -> system
    """
    code = (getattr(notif, 'notification_code', None) or '').upper()
    title_l = (getattr(notif, 'title', None) or '').lower()
    content_l = (getattr(notif, 'content', None) or '').lower()

    cat = None
    is_feedback_reply = False

    if code.startswith('TB-FB-'):
        cat = 'complaint'
        is_feedback_reply = True
    elif code.startswith('TB-COMP-'):
        cat = 'complaint'
    elif code.startswith(('TB-PTS-', 'TB-TIER-', 'TB-ADJ-')):
        cat = 'membership'
    elif code.startswith(('TB-CONFIRM-', 'TB-CONF-', 'TB-RESCHED-', 'TB-CANCEL-', 'TB-STATUS-')):
        cat = 'appointment'
    elif getattr(notif, 'promotion_id', None):
        cat = 'voucher'
    elif 'phản hồi đánh giá' in title_l:
        cat = 'complaint'
        is_feedback_reply = True
    elif 'khiếu nại' in title_l:
        cat = 'complaint'
    elif any(kw in title_l for kw in ('điểm thưởng', 'thăng hạng', 'hạng thẻ', 'hội viên')):
        cat = 'membership'
    elif any(kw in title_l for kw in ('voucher', 'khuyến mãi', 'ưu đãi', 'mã quà tặng')):
        cat = 'voucher'
    elif any(kw in title_l for kw in ('lịch hẹn', 'đặt lịch', 'dời lịch', 'hủy lịch', 'ca trực')):
        cat = 'appointment'
    elif any(kw in title_l for kw in ('hóa đơn', 'thanh toán', 'vietqr')):
        cat = 'payment'
    else:
        if any(kw in content_l for kw in ('khiếu nại', 'phản hồi đánh giá')):
            cat = 'complaint'
        elif any(kw in content_l for kw in ('điểm thưởng', 'thăng hạng', 'hạng thẻ', 'thẻ hội viên')):
            cat = 'membership'
        elif any(kw in content_l for kw in ('voucher', 'khuyến mãi', 'ưu đãi', 'mã quà tặng', 'giảm giá')):
            cat = 'voucher'
        elif any(kw in content_l for kw in ('lịch hẹn', 'đặt lịch', 'dời lịch', 'hủy lịch', 'ca trực')):
            cat = 'appointment'
        elif any(kw in content_l for kw in ('hóa đơn', 'thanh toán', 'vietqr')):
            cat = 'payment'
        else:
            cat = 'system'

    meta = dict(_CATEGORY_METADATA[cat])
    if is_feedback_reply:
        meta['badge_label'] = 'Phản hồi CSKH'
        meta['action_label'] = 'Xem đánh giá & phản hồi'
    return meta


def classify_staff_notification(notif):
    """
    Phân loại duy nhất và không chồng chéo cho luồng nhiệm vụ Staff:
      - 'complaints': Thông báo liên quan đến khiếu nại khách hàng
      - 'consultation': Yêu cầu tư vấn / Livechat
      - 'internal': Thông báo nội bộ / điều phối chung từ Admin
    """
    code = (getattr(notif, 'notification_code', None) or '').upper()
    title_l = (getattr(notif, 'title', None) or '').lower()
    content_l = (getattr(notif, 'content', None) or '').lower()

    if code.startswith('TB-COMP') or 'khiếu nại' in title_l or 'khiếu nại' in content_l:
        return {
            'category': 'complaints',
            'badge_label': 'Khiếu nại',
            'badge_class': 'badge bg-danger text-white px-2 py-1',
            'action_url_name': 'feedbacks:admin_management',
            'action_query': '?tab=complaints',
            'action_label': 'Xử lý Khiếu nại',
        }
    if any(kw in title_l or kw in content_l for kw in ('tư vấn', 'livechat')):
        return {
            'category': 'consultation',
            'badge_label': 'Tư vấn',
            'badge_class': 'badge bg-info text-dark px-2 py-1',
            'action_url_name': 'chatbox:inbox',
            'action_query': '',
            'action_label': 'Mở Livechat Console',
        }
    return {
        'category': 'internal',
        'badge_label': 'Nội bộ',
        'badge_class': 'badge bg-secondary text-white px-2 py-1',
        'action_url_name': None,
        'action_query': '',
        'action_label': '',
    }


def create_unique_notification(
    user,
    title,
    content,
    prefix="TB",
    promotion=None,
    delivery_channels="Web",
    status="Đã gửi",
    dedup_title_only=False,
):
    """
    Tạo Notification có mã định danh chuẩn và chống trùng lặp theo (user, title[, content]).
    Nếu thông báo giống hệt đã tồn tại cho user thì trả về bản ghi sẵn có thay vì tạo trùng.
    """
    if not user:
        return None
    filters = {'user': user, 'title': title}
    if not dedup_title_only:
        filters['content'] = content
    existing = Notification.objects.filter(**filters).order_by('-id').first()
    if existing:
        return existing

    return Notification.objects.create(
        notification_code=generate_notification_code(prefix),
        user=user,
        title=title,
        content=content,
        promotion=promotion,
        delivery_channels=delivery_channels,
        status=status,
    )


def create_system_notification(
    user,
    title,
    content,
    promotion=None,
    delivery_channels="Web",
    status="Đã gửi"
):
    """
    [UC-7.5] HÀM HELPER GỬI THÔNG BÁO HỆ THỐNG DÙNG CHUNG TOÀN HỆ THỐNG CHAM SPA.
    Các module khác (MOD-01 Đặt lịch, MOD-04 Khiếu nại, MOD-06 Tích điểm, MOD-09 Thanh toán)
    có thể import trực tiếp hàm này để tự động gửi thông báo cho người dùng khi có sự kiện.

    Tham số:
      - user: Đối tượng User hoặc danh sách User nhận thông báo (hỗ trợ cả gửi đơn hoặc gửi nhiều).
      - title: Tiêu đề ngắn gọn của thông báo (max_length=255).
      - content: Nội dung chi tiết của thông báo.
      - promotion: Đối tượng Promotion đính kèm (tùy chọn, default=None).
      - delivery_channels: Kênh phát thông báo ('Web', 'Email', 'SMS', default='Web').
      - status: Trạng thái thông báo ('Đã gửi', 'Chờ gửi', default='Đã gửi').

    Trả về:
      - Đối tượng Notification đơn lẻ nếu truyền 1 user.
      - Danh sách các đối tượng Notification đã tạo nếu truyền nhiều users.
    """
    # Trường hợp 1: Truyền vào danh sách nhiều User -> Dùng bulk_create để tối ưu truy vấn CSDL
    if isinstance(user, (list, tuple, set)) or hasattr(user, '__iter__') and not isinstance(user, User):
        users_list = list(user)
        if not users_list:
            return []
        existing_user_ids = set(
            Notification.objects.filter(
                user__in=users_list,
                title=title,
                content=content,
            ).values_list('user_id', flat=True)
        )
        notif_objects = []
        seen_uids = set()
        for idx, u in enumerate(users_list):
            if u.id in existing_user_ids or u.id in seen_uids:
                continue
            seen_uids.add(u.id)
            code = f"TB-{int(timezone.now().timestamp())}-{uuid.uuid4().hex[:4].upper()}-{idx+1}"
            notif_objects.append(
                Notification(
                    notification_code=code,
                    user=u,
                    title=title,
                    content=content,
                    promotion=promotion,
                    delivery_channels=delivery_channels,
                    status=status
                )
            )
        if not notif_objects:
            return list(
                Notification.objects.filter(
                    user__in=users_list,
                    title=title,
                    content=content,
                )
            )
        # Sử dụng bulk_create để ghi toàn bộ danh sách chỉ trong 1 câu lệnh SQL INSERT duy nhất
        created_records = Notification.objects.bulk_create(notif_objects)
        return created_records

    # Trường hợp 2: Truyền vào 1 đối tượng User đơn lẻ
    return create_unique_notification(
        user=user,
        title=title,
        content=content,
        prefix="TB",
        promotion=promotion,
        delivery_channels=delivery_channels,
        status=status,
    )


def ensure_sample_notifications_for_roles():
    """Giữ chữ ký tương thích ngược; không tự chèn thông báo mẫu ảo khi mở trang."""
    return 0

