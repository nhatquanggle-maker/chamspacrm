"""
Khởi tạo dữ liệu mẫu chuẩn 100% khớp 4 Node Figma:
  - Node 218:9398: Admin - Danh sách tài khoản KH
  - Node 221:481: Admin - Chi tiết khách hàng (Thông tin cá nhân & liên hệ)
  - Node 608:1773: Admin - Hồ sơ sức khỏe
  - Node 608:250: Admin - Hội viên và tích điểm
"""

import os
import sys
from decimal import Decimal
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from core.models import (
    User, UserProfile, UserHealthProfile, Tier, Membership,
    MembershipPoint, Appointment, Feedback, Service, Category
)


def seed_data():
    print("=== Khởi tạo dữ liệu mẫu Module 5 Admin theo chuẩn Figma ===")

    # 1. Khởi tạo / Đồng bộ Tiers
    tiers_data = [
        {'name': 'Thành viên', 'min_points': 0, 'discount_percent': 0, 'description': 'Hạng khởi đầu cho khách hàng mới'},
        {'name': 'Hạng Bạc', 'min_points': 500, 'discount_percent': 5, 'description': 'Tích lũy từ 500 điểm'},
        {'name': 'Hạng Vàng', 'min_points': 1500, 'discount_percent': 10, 'description': 'Tích lũy từ 1500 điểm'},
        {'name': 'Hạng Kim Cương', 'min_points': 3000, 'discount_percent': 15, 'description': 'Tích lũy từ 3000 điểm'},
    ]
    tier_objs = {}
    for td in tiers_data:
        t, _ = Tier.objects.update_or_create(
            name=td['name'],
            defaults={'min_points': td['min_points'], 'discount_percent': td['discount_percent'], 'description': td['description']}
        )
        tier_objs[td['name']] = t

    # 2. Khách hàng chính khớp Node 221:481, 608:1773, 608:250: Phạm Bảo Ngọc (#CUS042)
    ngoc_user, created = User.objects.get_or_create(
        username='0912845660',
        defaults={
            'name': 'Phạm Bảo Ngọc',
            'phone': '0912 845 660',
            'email': 'baongoc.pham@gmail.com',
            'is_staff': False,
            'is_superuser': False,
            'is_active': True,
        }
    )
    if not created:
        ngoc_user.name = 'Phạm Bảo Ngọc'
        ngoc_user.phone = '0912 845 660'
        ngoc_user.email = 'baongoc.pham@gmail.com'
        ngoc_user.is_active = True
        ngoc_user.save()
    ngoc_user.set_password('customer123456')
    ngoc_user.save()

    # UserProfile
    UserProfile.objects.update_or_create(
        user=ngoc_user,
        defaults={
            'birthday': date(1992, 8, 24),
            'gender': 'Nữ',
        }
    )

    # Membership
    ngoc_membership, _ = Membership.objects.update_or_create(
        user=ngoc_user,
        defaults={
            'tier': tier_objs['Hạng Kim Cương'],
            'current_points': 1500,
            'total_points_used': 350,
            'total_spent': Decimal('7500000.00'),
            'tier_expiration_date': date(2027, 12, 31),
        }
    )

    # Membership Points (Biến động điểm khớp Node 608:250)
    MembershipPoint.objects.filter(membership=ngoc_membership).delete()
    MembershipPoint.objects.create(
        membership=ngoc_membership,
        appointment_id='#HD-88392',
        points_amount=150,
        reason_description='Tích điểm dịch vụ Massage Body Đá Nóng',
        created_at=timezone.now() - timedelta(days=37)
    )
    MembershipPoint.objects.create(
        membership=ngoc_membership,
        appointment_id='#KM-CHAMGOLD',
        points_amount=50,
        reason_description='Tặng điểm sinh nhật thành viên Hạng Gold',
        created_at=timezone.now() - timedelta(days=49)
    )
    MembershipPoint.objects.create(
        membership=ngoc_membership,
        appointment_id='#HD-77120',
        points_amount=200,
        reason_description='Tích điểm Combo Chăm sóc chuyên sâu VIP',
        created_at=timezone.now() - timedelta(days=70)
    )

    # UserHealthProfile (Khớp 100% Node 608:1773)
    UserHealthProfile.objects.update_or_create(
        user=ngoc_user,
        defaults={
            'health_code': 'HS-20261002',
            'height_cm': Decimal('162.00'),
            'weight_kg': Decimal('52.00'),
            'blood_pressure': 'Bình thường',
            'focus_areas': ['Vai gáy', 'Thắt lưng'],
            'massage_pressure': 'Lực vừa',
            'pain_level': 6,
            'health_conditions': ['Da nhạy cảm'],
            'allergy_notes': 'Dị ứng tinh dầu sả chanh; dị ứng tinh dầu bạc hà',
            'special_requests': 'Ưu tiên phòng yên tĩnh; dị ứng tinh dầu bạc hà. KTV yêu thích: Trâm Anh.',
            'recovery_goals': ['Giảm đau mỏi vai gáy', 'Thư giãn cơ thắt lưng'],
        }
    )

    # 3. Tạo danh sách khách hàng khớp Bảng Node 218:9398
    customers_table_data = [
        {'code': 'USR089', 'name': 'Nguyễn Văn A', 'phone': '0905123457', 'email': 'a.nguyen@gmail.com', 'is_active': True, 'tier': 'Thành viên', 'date': '2026-09-22', 'gender': 'Nam', 'bday': '1990-05-12'},
        {'code': 'USR088', 'name': 'Trần Thanh Thảo', 'phone': '0901234568', 'email': 'thao.tran@gmail.com', 'is_active': True, 'tier': 'Hạng Bạc', 'date': '2026-09-20', 'gender': 'Nữ', 'bday': '1995-10-18'},
        {'code': 'USR087', 'name': 'Lê Hoàng Long', 'phone': '0918 345 678', 'email': 'long.le@gmail.com', 'is_active': True, 'tier': 'Hạng Vàng', 'date': '2026-09-18', 'gender': 'Nam', 'bday': '1988-12-04'},
        {'code': 'USR086', 'name': 'Đặng Thu Thảo', 'phone': '0935 456 789', 'email': 'thao.dang@gmail.com', 'is_active': False, 'tier': 'Thành viên', 'date': '2026-09-15', 'gender': 'Nữ', 'bday': '1994-07-29'},
        {'code': 'USR085', 'name': 'Võ Minh Trí', 'phone': '0903 567 890', 'email': 'tri.vo@gmail.com', 'is_active': True, 'tier': 'Hạng Bạc', 'date': '2026-09-12', 'gender': 'Nam', 'bday': '1991-03-15'},
        {'code': 'USR084', 'name': 'Bùi Phương Nga', 'phone': '0988 678 901', 'email': 'nga.bui@gmail.com', 'is_active': True, 'tier': 'Hạng Kim Cương', 'date': '2026-09-10', 'gender': 'Nữ', 'bday': '1989-11-20'},
        {'code': 'USR083', 'name': 'Hồ Quốc Cường', 'phone': '0979 789 012', 'email': 'cuong.ho@gmail.com', 'is_active': True, 'tier': 'Hạng Vàng', 'date': '2026-09-08', 'gender': 'Nam', 'bday': '1993-01-25'},
        {'code': 'USR082', 'name': 'Mai Anh Thư', 'phone': '0915 890 123', 'email': 'thu.mai@gmail.com', 'is_active': True, 'tier': 'Thành viên', 'date': '2026-09-05', 'gender': 'Nữ', 'bday': '1996-09-14'},
    ]

    for item in customers_table_data:
        clean_phone = item['phone'].replace(' ', '')
        u, _ = User.objects.get_or_create(
            username=clean_phone,
            defaults={
                'name': item['name'],
                'phone': item['phone'],
                'email': item['email'],
                'is_staff': False,
                'is_superuser': False,
                'is_active': item['is_active'],
            }
        )
        u.name = item['name']
        u.phone = item['phone']
        u.email = item['email']
        u.is_active = item['is_active']
        u.set_password('customer123456')
        u.save()

        UserProfile.objects.update_or_create(
            user=u,
            defaults={
                'gender': item['gender'],
                'birthday': datetime.strptime(item['bday'], '%Y-%m-%d').date()
            }
        )

        tier_choice = tier_objs.get(item['tier'], tier_objs['Thành viên'])
        Membership.objects.update_or_create(
            user=u,
            defaults={
                'tier': tier_choice,
                'current_points': tier_choice.min_points + 50,
                'total_spent': Decimal('2500000.00'),
            }
        )

    print("=== Hoàn tất khởi tạo dữ liệu mẫu thành công! ===")


if __name__ == '__main__':
    seed_data()


# Seed Appointments & Feedbacks for Pham Bao Ngoc
def seed_appointments_and_feedbacks():
    u = User.objects.get(name='Phạm Bảo Ngọc')
    Appointment.objects.filter(user=u).delete()
    Feedback.objects.filter(customer=u).delete()

    now = timezone.localdate()
    # 16 Completed appointments
    for i in range(16):
        d = now - timedelta(days=15 * (i + 1))
        appt = Appointment.objects.create(
            appointment_code=f"#LH88{i+100}",
            user=u,
            appointment_date=d,
            time_slot="14:00",
            total_guests=1,
            customer_name=u.name,
            customer_phone=u.phone,
            total_price=Decimal("1778125.00"),  # 16 * ~1.778.000 = 28.450.000
            status="Completed"
        )
        if i < 12:
            Feedback.objects.create(
                feedback_code=f"FB-BN-{i+1}",
                appointment=appt,
                customer=u,
                rating=5 if i != 3 else 4,
                comment="Dịch vụ rất tuyệt vời, KTV tay nghề tốt, không gian yên tĩnh.",
                status="Đã duyệt"
            )

    # 2 Cancelled appointments
    for j in range(2):
        d = now - timedelta(days=5 * (j + 1))
        Appointment.objects.create(
            appointment_code=f"#LH99{j+100}",
            user=u,
            appointment_date=d,
            time_slot="16:00",
            total_guests=1,
            customer_name=u.name,
            customer_phone=u.phone,
            total_price=Decimal("850000.00"),
            status="Cancelled",
            cancel_reason="Bận việc đột xuất"
        )

    print("=== Đã tạo 18 lịch hẹn (16 hoàn thành, 2 đã hủy) và 12 đánh giá cho Phạm Bảo Ngọc ===")

seed_appointments_and_feedbacks()
