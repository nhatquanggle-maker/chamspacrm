"""
================================================================================
MODULE 06: QUẢN LÝ HỘI VIÊN & TÍCH ĐIỂM (MOD-06) - DJANGO SIGNALS
Thành viên phụ trách: MINH KHÁNH
Use Case: UC-6.3 - Tự động tích điểm & Thăng hạng thẻ hội viên
Bảng CSDL liên quan: Invoice, Membership, MembershipPoint, Tier, Notification, User

Quy tắc nghiệp vụ chuẩn README & Đồng bộ liên Module (MOD-01, 05, 06, 07, 09, 10):
  1. Trigger 1 (Đăng ký tài khoản - MOD-05): Khi User mới được tạo từ bất kỳ đâu
     (Form đăng ký, Admin, Staff, API), tự động khởi tạo Thẻ hội viên (Membership)
     với Hạng mặc định 'Hạng Đồng' (0 điểm, chiết khấu 0%).
  2. Trigger 2 (Thanh toán hóa đơn - MOD-09 & MOD-01): Khi Invoice chuyển sang 'Đã thanh toán'.
  3. Tỷ lệ quy đổi điểm chuẩn: 10.000 VNĐ = 1 điểm thưởng (VD: 750.000đ = 75 điểm).
  4. Ghi nhận lịch sử minh bạch: Tạo bản ghi MembershipPoint.
  5. Đối soát chống trùng lặp đa chiều (Idempotency Check):
     Kiểm tra cả appointment.id, appointment.appointment_code, invoice.id.
     Lưu appointment_id = str(appointment.id) để khớp logic kiểm tra của appointment/api.py,
     ngăn chặn triệt để việc cộng lặp điểm khi lịch hẹn chuyển sang 'Completed'.
  6. Đánh giá tự động thăng hạng (Tier Upgrade): Tự động xét duyệt thăng hạng
     (Hạng Đồng -> Hạng Bạc -> Hạng Vàng -> Hạng Kim Cương) khi điểm tích lũy chạm mốc min_points.
  7. Tự động đồng bộ thăng hạng khi điểm thay đổi từ bất kỳ module nào qua signal MembershipPoint.
  8. Gửi thông báo hệ thống (MOD-07): Sinh bản ghi Notification chúc mừng tích điểm và thăng hạng.
================================================================================
"""

import logging
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

# Tuyệt đối chỉ import model từ core.models theo đúng quy tắc dự án
from core.models import Invoice, Membership, MembershipPoint, Tier, Notification, User, Appointment

logger = logging.getLogger(__name__)


def evaluate_and_upgrade_tier(membership):
    """
    Hàm kiểm tra và tự động nâng hạng thẻ hội viên (Tier Upgrade) theo tiến trình điểm tích lũy:
    - Hạng Đồng (0 điểm, 0% giảm giá)
    - Hạng Bạc (500 điểm, 5% giảm giá)
    - Hạng Vàng (1500 điểm, 10% giảm giá)
    - Hạng Kim Cương (3000 điểm, 15% giảm giá)
    Quy tắc nghiệp vụ: Điểm tích lũy xét hạng không bị hạ khi khách đổi quà/dùng điểm.
    """
    if not membership:
        return False, None

    accumulated_points = max(
        membership.current_points,
        membership.current_points + getattr(membership, 'total_points_used', 0)
    )

    # Tìm hạng thẻ cao nhất mà khách hàng đạt điều kiện min_points
    eligible_tier = Tier.objects.filter(min_points__lte=accumulated_points).order_by('-min_points').first()
    if not eligible_tier:
        return False, None

    current_tier_min = membership.tier.min_points if membership.tier else -1
    if eligible_tier.min_points > current_tier_min:
        old_tier_name = membership.tier.name if membership.tier else "Hạng Đồng"
        membership.tier = eligible_tier
        membership.save(update_fields=['tier'])

        # Gửi thông báo chúc mừng thăng hạng VIP (MOD-07)
        user = membership.user
        try:
            from marketing.utils import create_unique_notification
            create_unique_notification(
                user=user,
                title=f"Chúc mừng bạn đã thăng hạng {eligible_tier.name}!",
                content=(
                    f"Chúc mừng quý khách {user.name} đã tích lũy đủ điểm và nâng hạng thành công lên "
                    f"{eligible_tier.name}. Đặc quyền giảm {eligible_tier.discount_percent}% cho mọi liệu trình "
                    f"tại Cham Spa đã được kích hoạt!"
                ),
                prefix="TB-TIER",
                delivery_channels="Web",
                status="Đã gửi",
                dedup_title_only=True,
            )
        except Exception as notif_err:
            logger.warning(f"Lỗi khi gửi thông báo thăng hạng: {notif_err}")

        logger.info(f"[MOD-06] Khách hàng {user.name} đã thăng hạng thành công: {old_tier_name} -> {eligible_tier.name}")
        return True, eligible_tier.name

    return False, membership.tier.name if membership.tier else "Hạng Đồng"


def process_invoice_membership_points(invoice):
    """
    Hàm xử lý nghiệp vụ tích điểm và thăng hạng khi hóa đơn thanh toán thành công.
    Được gọi từ Signal post_save Invoice hoặc có thể gọi trực tiếp từ các flow thanh toán.
    """
    # 1. Kiểm tra trạng thái hóa đơn: Chỉ tích điểm khi đã thanh toán thành công
    if invoice.status != 'Đã thanh toán':
        return {'status': 'skipped', 'reason': 'Hóa đơn chưa ở trạng thái Đã thanh toán'}

    # 2. Xác định lịch hẹn gắn với hóa đơn
    appointment = getattr(invoice, 'appointment', None)
    if not appointment:
        return {'status': 'skipped', 'reason': 'Hóa đơn không liên kết với lịch hẹn'}

    # 3. Xác định tài khoản khách hàng tích điểm
    user = appointment.user
    if not user and appointment.customer_phone:
        # Dự phòng trường hợp khách vãng lai đặt lịch bằng SĐT đã có tài khoản trong hệ thống
        clean_phone = appointment.customer_phone.replace(' ', '').replace('.', '').replace('-', '').strip()
        user = User.objects.filter(phone=clean_phone).first()

    if not user:
        return {'status': 'skipped', 'reason': 'Khách hàng chưa đăng ký tài khoản, không thể tích điểm'}

    # 4. Lấy hoặc khởi tạo Thẻ hội viên cho khách hàng (nếu chưa có)
    default_tier = Tier.objects.filter(min_points=0).order_by('min_points').first() or Tier.objects.order_by('min_points').first()
    membership, created = Membership.objects.get_or_create(
        user=user,
        defaults={
            'tier': default_tier,
            'current_points': 0,
            'total_points_used': 0,
            'total_spent': Decimal(0),
        }
    )

    if membership.tier is None and default_tier:
        membership.tier = default_tier
        membership.save(update_fields=['tier'])

    # 5. Đối soát đa chiều chống cộng lặp điểm (Idempotency Multi-Check)
    appt_code = appointment.appointment_code or f"LH-{appointment.id}"
    appt_id_str = str(appointment.id)
    clean_code = appt_code.replace('#', '')

    already_awarded = MembershipPoint.objects.filter(
        membership=membership,
        points_amount__gt=0
    ).filter(
        Q(appointment_id=appt_id_str) |
        Q(appointment_id=appt_code) |
        Q(appointment_id=f"#{clean_code}") |
        Q(appointment_id=clean_code) |
        Q(appointment_id=f"HD-{invoice.id}") |
        Q(reason_description__icontains=clean_code) |
        Q(reason_description__icontains=f"hóa đơn #{invoice.id}")
    ).exists()

    if already_awarded:
        # Điểm đã được cộng trước đó (ví dụ từ luồng hoàn thành lịch hẹn ở appointment/api.py),
        # kiểm tra và nâng hạng nếu chưa thăng hạng
        upgraded, tier_name = evaluate_and_upgrade_tier(membership)
        return {
            'status': 'already_processed',
            'message': f'Giao dịch {appt_code} đã được cộng điểm trước đó.',
            'upgraded': upgraded,
            'tier_name': tier_name
        }

    # 6. Tính số điểm thưởng được cộng theo công thức chuẩn README: 10.000 VNĐ = 1 điểm
    invoice_amount = float(invoice.amount or 0)
    points_to_add = int(invoice_amount) // 10000

    if points_to_add <= 0:
        return {'status': 'skipped', 'reason': 'Số tiền hóa đơn không đủ điều kiện tích tối thiểu 1 điểm'}

    # 7. Thực hiện ghi nhận điểm và kiểm tra thăng hạng trong một Database Transaction
    with transaction.atomic():
        # Ghi nhận lịch sử biến động điểm thưởng với mã lịch hẹn chuẩn (VD: AP-TEST-001, #LH35527)
        membership_point = MembershipPoint.objects.create(
            membership=membership,
            appointment_id=appt_code,
            points_amount=points_to_add,
            reason_description=f"Tích điểm tự động từ hóa đơn #{clean_code} (10.000đ = 1 điểm thưởng)"
        )

        # Lưu bản ghi đối soát appointment.id (0 điểm) để thỏa mãn kiểm tra chống lặp tại appointment/api.py
        if appointment and str(appointment.id) != appt_code:
            MembershipPoint.objects.get_or_create(
                membership=membership,
                appointment_id=appt_id_str,
                defaults={
                    'points_amount': 0,
                    'reason_description': f"Đối soát định danh lịch hẹn #{clean_code}"
                }
            )

        # Cập nhật số dư điểm hiện tại và tổng chi tiêu tích lũy
        membership.current_points += points_to_add
        membership.total_spent = (membership.total_spent or Decimal(0)) + Decimal(str(invoice.amount or 0))
        membership.save(update_fields=['current_points', 'total_spent'])

        # 8. Đánh giá tự động nâng hạng thẻ (Tier Upgrade)
        upgraded, new_tier_name = evaluate_and_upgrade_tier(membership)

        # 9. Tạo thông báo tích điểm thành công gửi vào Bảng tin thông báo của khách hàng (MOD-07)
        try:
            from marketing.utils import create_unique_notification
            create_unique_notification(
                user=user,
                title=f"Bạn vừa được cộng +{points_to_add} điểm thưởng!",
                content=(
                    f"Thanh toán lịch hẹn #{clean_code} thành công. Quý khách nhận được +{points_to_add} điểm thưởng. "
                    f"Số dư điểm hiện tại: {membership.current_points} điểm."
                ),
                prefix="TB-PTS",
                delivery_channels="Web",
                status="Đã gửi",
            )
        except Exception as notif_err:
            logger.warning(f"Lỗi khi gửi thông báo tích điểm: {notif_err}")

    logger.info(
        f"[MOD-06] Đã tích {points_to_add} điểm cho {user.name} ({user.phone}) từ hóa đơn #{clean_code}. "
        f"Thăng hạng: {upgraded} -> {new_tier_name}"
    )

    return {
        'status': 'success',
        'points_added': points_to_add,
        'current_points': membership.current_points,
        'total_spent': float(membership.total_spent),
        'upgraded': upgraded,
        'tier_name': new_tier_name,
        'appointment_code': appt_code,
    }


# ==============================================================================
# DJANGO SIGNAL RECEIVERS
# ==============================================================================

@receiver(post_save, sender=Invoice)
def invoice_post_save_points_receiver(sender, instance, created, **kwargs):
    """
    Django Signal Receiver: Lắng nghe sự kiện lưu bản ghi Invoice (MOD-09).
    Khi hóa đơn chuyển sang 'Đã thanh toán', tự động kích hoạt tính năng tích điểm hội viên.
    """
    try:
        if instance.status == 'Đã thanh toán':
            process_invoice_membership_points(instance)
    except Exception as e:
        logger.error(f"[MOD-06 Signal Error] Lỗi tự động tích điểm hóa đơn {instance.id}: {e}", exc_info=True)


@receiver(post_save, sender=MembershipPoint)
def membership_point_post_save_tier_receiver(sender, instance, created, **kwargs):
    """
    Django Signal Receiver: Lắng nghe sự kiện tạo bản ghi MembershipPoint.
    Nếu điểm số tăng lên (từ bất kỳ module nào như appointment/api.py, staff_lookup modal, hoặc signal),
    tự động thẩm định lại hạng thẻ và thăng hạng nếu đủ điều kiện min_points.
    """
    try:
        if created and instance.points_amount > 0 and instance.membership:
            evaluate_and_upgrade_tier(instance.membership)
    except Exception as e:
        logger.error(f"[MOD-06 Signal Error] Lỗi thẩm định thăng hạng từ MembershipPoint {instance.id}: {e}", exc_info=True)
