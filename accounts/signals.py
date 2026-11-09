"""
================================================================================
MODULE 05: QUẢN TRỊ TÀI KHOẢN, PHÂN QUYỀN & KHÁCH HÀNG (MOD-05) - SIGNALS
Đồng bộ tự động dữ liệu liên module:
  - Khi tạo User mới:
    1. Tự động khởi tạo UserProfile (MOD-05).
    2. Nếu là Khách hàng (is_staff=False, is_superuser=False):
       - Tự động cấp Thẻ hội viên điện tử Membership (MOD-06) với hạng mặc định.
       - Tự động lập Hồ sơ thể trạng sức khỏe UserHealthProfile (MOD-08) với mã HS chuẩn.
       - Tự động liên kết các Lịch hẹn (MOD-01) đã đặt trước đó theo Số điện thoại.
================================================================================
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import User, UserProfile, Membership, Tier, UserHealthProfile, Appointment

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def user_post_save_sync_receiver(sender, instance, created, **kwargs):
    """
    Tự động đồng bộ các bảng dữ liệu phụ thuộc khi tạo tài khoản User.
    """
    if created:
        try:
            # 1. Luôn bảo đảm UserProfile tồn tại (MOD-05)
            UserProfile.objects.get_or_create(user=instance)

            # 2. Đồng bộ các phân hệ dành riêng cho Khách hàng
            if not instance.is_staff and not instance.is_superuser:
                # 2.1. Thẻ hội viên điện tử Membership (MOD-06)
                default_tier = Tier.objects.filter(min_points=0).order_by('min_points').first() or Tier.objects.first()
                Membership.objects.get_or_create(
                    user=instance,
                    defaults={
                        'tier': default_tier,
                        'current_points': 0,
                        'total_points_used': 0,
                        'total_spent': 0,
                    }
                )

                # 2.2. Hồ sơ sức khỏe UserHealthProfile (MOD-08)
                cand_code = f"HS-{instance.id:04d}"
                suffix = 1
                while UserHealthProfile.objects.filter(health_code=cand_code).exists():
                    cand_code = f"HS-{instance.id:04d}-{suffix}"
                    suffix += 1

                UserHealthProfile.objects.get_or_create(
                    user=instance,
                    defaults={
                        'health_code': cand_code,
                        'focus_areas': ['Vai gáy'],
                        'massage_pressure': 'Lực vừa',
                        'pain_level': 5,
                        'special_requests': 'Ưu tiên không gian yên tĩnh, thư giãn nhẹ nhàng.'
                    }
                )

                # 2.3. Tự động liên kết các lịch hẹn trước đây (MOD-01) nếu khách từng đặt bằng số điện thoại này
                if instance.phone:
                    clean_phone = instance.phone.replace(' ', '').replace('.', '').strip()
                    Appointment.objects.filter(user__isnull=True, customer_phone=clean_phone).update(user=instance)

        except Exception as e:
            logger.error(f"[MOD-05 Signal Error] Lỗi tự động đồng bộ dữ liệu cho User {instance.id}: {e}", exc_info=True)
