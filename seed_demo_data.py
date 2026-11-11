"""
Script dọn sạch dữ liệu mẫu cũ và khởi tạo bộ dữ liệu demo tinh gọn (mỗi phần 5-7 bản ghi).
Thiết lập sẵn 3 tài khoản demo chuẩn cho 3 phân quyền:
- Admin: admin@chamspa.vn / admin123
- Staff: staff@chamspa.vn / staff123
- Customer: customer@gmail.com / customer123
"""

import os
from datetime import date, timedelta
from decimal import Decimal

import django
from django.db import transaction
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group

from core.models import (
    Appointment,
    AppointmentDetail,
    Category,
    Complaint,
    Conversation,
    ConversationMessage,
    FAQ,
    Feedback,
    Invoice,
    Membership,
    MembershipPoint,
    Notification,
    Promotion,
    Service,
    ServiceImage,
    Tier,
    User,
    UserHealthProfile,
    UserProfile,
    Voucher,
)


def _preserve_core_credentials():
    """Lưu lại thông tin đăng nhập hiện tại của 'admin' và 'staff' trước khi làm sạch DB."""
    admin_old = User.objects.filter(username='admin').first() or User.objects.filter(is_superuser=True).order_by('id').first()
    staff_old = User.objects.filter(username='staff').first() or User.objects.filter(is_staff=True, is_superuser=False).order_by('id').first()

    admin_info = {
        'username': 'admin',
        'password_hash': admin_old.password if admin_old else make_password('Admin@2026'),
        'phone': (admin_old.phone if admin_old and admin_old.phone else '0886556303'),
        'email': (admin_old.email if admin_old and admin_old.email.endswith('@chamspa.vn') else 'admin@chamspa.vn'),
        'name': (admin_old.name if admin_old and admin_old.name else 'Quản trị viên Cham Spa'),
    }
    staff_info = {
        'username': 'staff',
        'password_hash': make_password('staff123'),
        'phone': (staff_old.phone if staff_old and staff_old.phone else '0905123456'),
        'email': 'staff@chamspa.vn',
        'name': (staff_old.name if staff_old and staff_old.name else 'Thanh Thỏ'),
    }
    if staff_info['phone'] == admin_info['phone']:
        staff_info['phone'] = '0905123456'
    return admin_info, staff_info


def _wipe_all_demo_data():
    """Xóa sạch toàn bộ dữ liệu các bảng nghiệp vụ theo đúng thứ tự khóa ngoại."""
    ConversationMessage.objects.all().delete()
    Conversation.objects.all().delete()
    FAQ.objects.all().delete()
    Notification.objects.all().delete()
    Voucher.objects.all().delete()
    Promotion.objects.all().delete()
    Complaint.objects.all().delete()
    Feedback.objects.all().delete()
    Invoice.objects.all().delete()
    AppointmentDetail.objects.all().delete()
    Appointment.objects.all().delete()
    MembershipPoint.objects.all().delete()
    Membership.objects.all().delete()
    UserHealthProfile.objects.all().delete()
    ServiceImage.objects.all().delete()
    Service.objects.all().delete()
    Category.objects.all().delete()
    Tier.objects.all().delete()
    UserProfile.objects.all().delete()
    User.objects.all().delete()


def reset_and_seed_demo():
    admin_info, staff_info = _preserve_core_credentials()
    now = timezone.now()
    today = timezone.localdate()

    with transaction.atomic():
        _wipe_all_demo_data()

        # 1. Hạng thẻ hội viên (4 hạng chuẩn hệ thống)
        tiers_spec = [
            ('Hạng Đồng', 0, 0, 'Hạng khởi đầu cho khách hàng mới tại Cham Spa.'),
            ('Hạng Bạc', 500, 5, 'Giảm 5% hóa đơn dịch vụ và ưu tiên đặt lịch.'),
            ('Hạng Vàng', 1500, 10, 'Giảm 10% hóa đơn, tặng kèm trà thảo mộc & ưu đãi sinh nhật.'),
            ('Hạng Kim Cương', 3000, 15, 'Giảm 15% mọi liệu trình, phòng VIP yên tĩnh và đặc quyền cao cấp.'),
        ]
        tiers = {}
        for name, min_pts, disc, desc in tiers_spec:
            tiers[name] = Tier.objects.create(
                name=name,
                min_points=min_pts,
                discount_percent=disc,
                description=desc,
            )

        staff_group, _ = Group.objects.get_or_create(name='Staff')

        # 2. Tài khoản Admin (1) & Staff (6) — @chamspa.vn
        admin_user = User.objects.create(
            username=admin_info['username'],
            password=admin_info['password_hash'],
            name=admin_info['name'],
            phone=admin_info['phone'],
            email=admin_info['email'],
            is_staff=True,
            is_superuser=True,
            is_active=True,
            first_name='Quản lý',
            last_name='Hoạt động',
        )
        UserProfile.objects.filter(user=admin_user).update(gender='Nam', birthday=date(1990, 5, 15), avatar=None)

        # Staff #1: giữ nguyên tài khoản staff chính
        staff_primary = User.objects.create(
            username=staff_info['username'],
            password=staff_info['password_hash'],
            name=staff_info['name'],
            phone=staff_info['phone'],
            email=staff_info['email'],
            is_staff=True,
            is_superuser=False,
            is_active=True,
            first_name='Staff',
            last_name='Hoạt động',
        )
        staff_primary.groups.add(staff_group)
        UserProfile.objects.filter(user=staff_primary).update(gender='Nữ', birthday=date(1996, 4, 20), avatar=None)

        extra_staff_specs = [
            ('0935820114', 'Lê Thị Mai', 'mai.le@chamspa.vn', 'Hoạt động', True, 'Nữ', date(1995, 3, 14)),
            ('0908211635', 'Nguyễn Trâm Anh', 'anh.nguyen@chamspa.vn', 'Hoạt động', True, 'Nữ', date(1997, 8, 21)),
            ('0982115920', 'Đỗ Minh Tuấn', 'tuan.do@chamspa.vn', 'Hoạt động', True, 'Nam', date(1993, 11, 5)),
            ('0908556677', 'Đinh Phương Thảo', 'thao.dinh@chamspa.vn', 'Hoạt động', True, 'Nữ', date(1998, 6, 19)),
            ('0934905117', 'Lê Quốc Dũng', 'dung.le@chamspa.vn', 'Tạm khóa', False, 'Nam', date(1992, 1, 30)),
        ]
        staff_list = [staff_primary]
        for phone, name, email, work_status, is_act, gender, bday in extra_staff_specs:
            if phone == admin_info['phone']:
                phone = '0939' + phone[4:]
            st = User.objects.create_user(
                username=phone,
                password='staff123',
                name=name,
                phone=phone,
                email=email,
                is_staff=True,
                is_superuser=False,
                is_active=is_act,
                first_name='Staff',
                last_name=work_status,
            )
            st.groups.add(staff_group)
            UserProfile.objects.filter(user=st).update(gender=gender, birthday=bday, avatar=None)
            staff_list.append(st)

        # 3. Tài khoản Khách hàng (6 khách) — @gmail.com
        customer_specs = [
            {
                'phone': '0912845660', 'name': 'Phạm Bảo Ngọc', 'email': 'customer@gmail.com',
                'is_active': True, 'gender': 'Nữ', 'birthday': date(1992, 8, 24),
                'tier': 'Hạng Kim Cương', 'points': 3200, 'spent': Decimal('18500000'),
                'health': {
                    'height': Decimal('162'), 'weight': Decimal('52'), 'bp': 'Bình thường',
                    'focus': ['Vai gáy', 'Thắt lưng'], 'pressure': 'Lực vừa', 'pain': 6,
                    'cond': [], 'allergy': '',
                    'req': 'Ưu tiên phòng yên tĩnh, trà gừng ấm sau liệu trình.',
                    'goals': ['Giảm đau vai gáy', 'Thư giãn ngủ ngon'],
                },
            },
            {
                'phone': '0938228814', 'name': 'Trần Gia Hân', 'email': 'giahan@gmail.com',
                'is_active': True, 'gender': 'Nữ', 'birthday': date(1995, 4, 12),
                'tier': 'Hạng Vàng', 'points': 1680, 'spent': Decimal('8200000'),
                'health': {
                    'height': Decimal('158'), 'weight': Decimal('54'), 'bp': 'Thấp',
                    'focus': ['Thắt lưng', 'Bàn chân'], 'pressure': 'Nhẹ nhàng', 'pain': 4,
                    'cond': [], 'allergy': '',
                    'req': 'Ưu tiên lực nhẹ nhàng, giữ ấm phòng trị liệu.',
                    'goals': ['Cải thiện tuần hoàn', 'Thư giãn ngủ ngon'],
                },
            },
            {
                'phone': '0906441290', 'name': 'Hoàng Bảo Long', 'email': 'baolong@gmail.com',
                'is_active': True, 'gender': 'Nam', 'birthday': date(1990, 9, 18),
                'tier': 'Hạng Bạc', 'points': 780, 'spent': Decimal('4600000'),
                'health': {
                    'height': Decimal('174'), 'weight': Decimal('75'), 'bp': 'Cao',
                    'focus': ['Vai gáy', 'Lưng trên'], 'pressure': 'Lực mạnh', 'pain': 8,
                    'cond': [], 'allergy': '',
                    'req': 'Không xông hơi quá nóng, tập trung ấn huyệt cổ vai.',
                    'goals': ['Giảm đau vai gáy', 'Phục hồi cơ bắp & Thải độc'],
                },
            },
            {
                'phone': '0977515006', 'name': 'Phạm Khánh Vy', 'email': 'khanhvy@gmail.com',
                'is_active': True, 'gender': 'Nữ', 'birthday': date(1996, 11, 25),
                'tier': 'Hạng Bạc', 'points': 620, 'spent': Decimal('3450000'),
                'health': {
                    'height': Decimal('160'), 'weight': Decimal('49'), 'bp': 'Bình thường',
                    'focus': ['Da mặt', 'Cổ'], 'pressure': 'Nhẹ nhàng', 'pain': 3,
                    'cond': [], 'allergy': '',
                    'req': 'Thích gội đầu nước bồ kết ấm.',
                    'goals': ['Giải tỏa căng thẳng', 'Thư giãn ngủ ngon'],
                },
            },
            {
                'phone': '0914206803', 'name': 'Lê Nhật Quang', 'email': 'nhatquang@gmail.com',
                'is_active': True, 'gender': 'Nam', 'birthday': date(1999, 2, 7),
                'tier': 'Hạng Đồng', 'points': 210, 'spent': Decimal('1400000'),
                'health': {
                    'height': Decimal('171'), 'weight': Decimal('66'), 'bp': 'Bình thường',
                    'focus': ['Bàn chân', 'Bắp chân'], 'pressure': 'Lực vừa', 'pain': 5,
                    'cond': [], 'allergy': '',
                    'req': 'Ngâm chân thảo dược 15 phút đầu.',
                    'goals': ['Phục hồi cơ bắp & Thải độc'],
                },
            },
            {
                'phone': '0935456789', 'name': 'Đặng Thu Thảo', 'email': 'thuthao.dang@gmail.com',
                'is_active': False, 'gender': 'Nữ', 'birthday': date(1994, 7, 29),
                'tier': 'Hạng Đồng', 'points': 120, 'spent': Decimal('850000'),
                'health': {
                    'height': Decimal('163'), 'weight': Decimal('51'), 'bp': 'Bình thường',
                    'focus': ['Vai gáy'], 'pressure': 'Lực vừa', 'pain': 5,
                    'cond': [], 'allergy': '',
                    'req': 'Tài khoản tạm khóa demo.',
                    'goals': ['Giải tỏa căng thẳng'],
                },
            },
        ]

        customers = []
        for idx, spec in enumerate(customer_specs, start=1):
            c = User.objects.create_user(
                username=spec['phone'],
                password='customer123',
                name=spec['name'],
                phone=spec['phone'],
                email=spec['email'],
                is_staff=False,
                is_superuser=False,
                is_active=spec['is_active'],
            )
            UserProfile.objects.filter(user=c).update(
                gender=spec['gender'],
                birthday=spec['birthday'],
                avatar=None,
            )
            Membership.objects.filter(user=c).update(
                tier=tiers[spec['tier']],
                current_points=spec['points'],
                total_points_used=100 if idx <= 2 else 0,
                total_spent=spec['spent'],
                tier_expiration_date=today + timedelta(days=365),
            )
            h = spec['health']
            UserHealthProfile.objects.filter(user=c).update(
                health_code=f'HS-2026{idx:03d}',
                height_cm=h['height'],
                weight_kg=h['weight'],
                blood_pressure=h['bp'],
                focus_areas=h['focus'],
                massage_pressure=h['pressure'],
                pain_level=h['pain'],
                health_conditions=h['cond'],
                allergy_notes=h['allergy'],
                special_requests=h['req'],
                recovery_goals=h['goals'],
            )
            customers.append(c)

        # 4. Danh mục (5) & Dịch vụ (6) + Ảnh Gallery (6)
        cats = {
            'body': Category.objects.create(name='Massage Body', slug='massage-body', status='Active'),
            'ther': Category.objects.create(name='Trị liệu Chuyên sâu', slug='tri-lieu-chuyen-sau', status='Active'),
            'hair': Category.objects.create(name='Gội đầu dưỡng sinh', slug='goi-dau-duong-sinh', status='Active'),
            'skin': Category.objects.create(name='Chăm sóc da Facial', slug='cham-soc-da-facial', status='Active'),
            'foot': Category.objects.create(name='Massage Foot', slug='massage-foot', status='Active'),
        }

        services_spec = [
            (cats['body'], 'Massage Body Trị Liệu Vai Gáy', 'massage-body-tri-lieu-vai-gay', '/media/services/service_1.jpg',
             Decimal('550000'), 60, 'Giải tỏa căng cơ vùng cổ, vai, gáy bằng tinh dầu thảo mộc Cham kết hợp ấn huyệt chuyên sâu.', ['/media/services/detail_main.jpg', '/media/services/gallery_1.jpg']),
            (cats['ther'], 'Massage Đá Nóng Champa', 'massage-da-nong-champa', '/media/services/service_2.jpg',
             Decimal('850000'), 90, 'Đá bazan núi lửa giữ nhiệt lan tỏa dọc sống lưng giúp lưu thông khí huyết và ngủ sâu giấc.', ['/media/services/gallery_2.jpg']),
            (cats['hair'], 'Gội Đầu Dưỡng Sinh Thảo Mộc', 'goi-dau-duong-sinh-thao-moc', '/media/services/service_3.jpg',
             Decimal('420000'), 60, 'Làm sạch da đầu bằng bồ kết - sả chanh kết hợp massage bấm huyệt đầu, cổ, vai thư thái.', ['/media/services/gallery_3.jpg']),
            (cats['skin'], 'Chăm Sóc Da Sen Vàng', 'cham-soc-da-sen-vang', '/media/services/service_4_hd.png',
             Decimal('690000'), 75, 'Cấp ẩm sâu và phục hồi làn da rạng rỡ với chiết xuất nhụy sen tinh khiết.', ['/media/services/gallery_1.jpg']),
            (cats['foot'], 'Massage Chân Phục Hồi Năng Lượng', 'massage-chan-phuc-hoi-nang-luong', '/media/services/service_5_hd.png',
             Decimal('350000'), 45, 'Ngâm chân thuốc Bắc ấm và bấm huyệt lòng bàn chân giảm nhức mỏi nhanh chóng.', ['/media/services/gallery_2.jpg']),
            (cats['ther'], 'Trị Liệu Cột Sống Chuyên Sâu', 'tri-lieu-cot-song-chuyen-sau', '/media/services/service_6_hd.png',
             Decimal('1250000'), 120, 'Liệu trình đặc biệt dành cho người đau lưng mãn tính, kết hợp chườm ngải cứu và kéo giãn cơ.', ['/media/services/gallery_3.jpg']),
        ]
        services = []
        for cat, name, slug, thumb, price, dur, desc, galleries in services_spec:
            svc = Service.objects.create(
                category=cat, name=name, slug=slug, thumbnail_url=thumb,
                price_vnd=price, duration_minutes=dur, status='Hoạt động', description=desc,
            )
            for g in galleries:
                ServiceImage.objects.create(service=svc, image_url=g)
            services.append(svc)

        # 5. Chương trình khuyến mãi (5)
        promos = [
            Promotion.objects.create(
                promotion_code='CHAMSPA20', title='Ưu Đãi Chào Thành Viên Mới - Giảm 20%',
                conditions_desc='Áp dụng cho toàn bộ dịch vụ Massage Body và Gội đầu dưỡng sinh.',
                valid_from=now - timedelta(days=10), valid_until=now + timedelta(days=30), status='Đang hoạt động',
            ),
            Promotion.objects.create(
                promotion_code='THUGIAN150', title='Thứ 7 Thư Thái - Giảm Ngay 150.000đ',
                conditions_desc='Áp dụng đơn dịch vụ từ 500.000đ trở lên.',
                valid_from=now - timedelta(days=5), valid_until=now + timedelta(days=20), status='Đang hoạt động',
            ),
            Promotion.objects.create(
                promotion_code='VIPSENVANG', title='Tuần Lễ Chăm Sóc Da Sen Vàng',
                conditions_desc='Tặng voucher ưu đãi chăm sóc da cho hội viên Bạc trở lên.',
                valid_from=now - timedelta(days=3), valid_until=now + timedelta(days=25), status='Đang hoạt động',
            ),
            Promotion.objects.create(
                promotion_code='NOELCHAM', title='Đón Mùa Lễ Hội An Yên',
                conditions_desc='Chương trình ưu đãi gói Combo cuối năm.',
                valid_from=now + timedelta(days=15), valid_until=now + timedelta(days=45), status='Sắp diễn ra',
            ),
            Promotion.objects.create(
                promotion_code='CHAOHE26', title='Rạng Rỡ Mùa Hè Champa',
                conditions_desc='Đã kết thúc thời gian áp dụng.',
                valid_from=now - timedelta(days=60), valid_until=now - timedelta(days=15), status='Hết hạn',
            ),
        ]

        # 6. Lịch hẹn (7) + Chi tiết (7) + Hóa đơn (7)
        # Tạo Hóa đơn trạng thái chờ trước rồi update() sau để tránh signal sinh thông báo/điểm tự động trùng lặp
        appt_specs = [
            ('#LH1001', customers[0], services[1], today - timedelta(days=6), '10:00', 'Completed', 'Đã thanh toán', Decimal('850000'), 'Lực vừa', 'Nữ', 'Khách VIP ghé thư giãn định kỳ'),
            ('#LH1002', customers[1], services[3], today - timedelta(days=4), '14:00', 'Completed', 'Đã thanh toán', Decimal('690000'), 'Nhẹ nhàng', 'Nữ', 'Mẹ bầu lưu ý tinh dầu dịu nhẹ'),
            ('#LH1003', customers[2], services[5], today - timedelta(days=3), '16:30', 'Completed', 'Đã thanh toán', Decimal('1250000'), 'Lực mạnh', 'Nam', 'Đau cổ vai nhiều'),
            ('#LH1004', customers[3], services[2], today - timedelta(days=2), '11:00', 'Completed', 'Đã thanh toán', Decimal('420000'), 'Nhẹ nhàng', 'Nữ', 'Gội đầu bồ kết ấm'),
            ('#LH1005', customers[4], services[0], today - timedelta(days=1), '15:00', 'Completed', 'Đã thanh toán', Decimal('550000'), 'Lực vừa', 'Nam', 'Thư giãn sau giờ làm'),
            ('#LH1006', customers[0], services[4], today, '17:00', 'Pending', 'Chờ xác nhận', Decimal('350000'), 'Lực vừa', 'Nữ', 'Đặt lịch ngâm chân thảo dược hôm nay'),
            ('#LH1007', customers[2], services[0], today - timedelta(days=1), '09:30', 'Cancelled', 'Không hợp lệ', Decimal('550000'), 'Lực mạnh', 'Nam', 'Bận công tác đột xuất'),
        ]
        appointments = []
        for idx, (code, cust, svc, adate, slot, st, inv_st, total, press, gender, note) in enumerate(appt_specs):
            is_cancelled = (st == 'Cancelled')
            appt = Appointment.objects.create(
                appointment_code=code,
                user=cust,
                appointment_date=adate,
                time_slot=slot,
                total_guests=1,
                male_guests=1 if gender == 'Nam' else 0,
                female_guests=1 if gender == 'Nữ' else 0,
                customer_name=cust.name,
                customer_phone=cust.phone,
                customer_email=cust.email,
                preferred_contact_channel='Zalo',
                note='' if is_cancelled else note,
                cancel_reason=note if is_cancelled else '',
                refund_account_number='1023456789 - Vietcombank' if is_cancelled else '',
                total_price=total,
                status=st,
            )
            created_dt = timezone.make_aware(timezone.datetime.combine(adate, timezone.datetime.min.time())) + timedelta(hours=9)
            Appointment.objects.filter(pk=appt.pk).update(created_at=created_dt)

            AppointmentDetail.objects.create(
                appointment=appt,
                service=svc,
                guest_index=1,
                gender=gender,
                massage_pressure=press,
            )

            inv = Invoice.objects.create(
                appointment=appt,
                amount=total,
                discount_applied=Decimal('0'),
                status='Chờ xác nhận',
            )
            Invoice.objects.filter(pk=inv.pk).update(
                status=inv_st,
                paid_at=created_dt if inv_st == 'Đã thanh toán' else None,
                reason_refuse='Khách đã hủy lịch trước giờ hẹn' if is_cancelled else None,
                created_at=created_dt,
            )
            appointments.append(appt)

        # 7. Đánh giá dịch vụ (5 đánh giá cho 5 lịch Hoàn thành)
        fb_specs = [
            ('FB-1001', appointments[0], customers[0], 5, 'KTV làm rất đều tay, phòng đá nóng thơm mùi thảo mộc cực kỳ dễ chịu.', 'Đã phản hồi', 'Cảm ơn chị Bảo Ngọc đã tin tưởng trải nghiệm dịch vụ tại Cham Spa!', staff_list[0]),
            ('FB-1002', appointments[1], customers[1], 4, 'Nhân viên nhẹ nhàng chu đáo, riêng lúc đầu hơi chờ nhận phòng khoảng 10 phút.', 'Đã phản hồi', 'Cham Spa rất trân trọng góp ý của chị Gia Hân và sẽ rút ngắn thời gian chuẩn bị phòng.', staff_list[1]),
            ('FB-1003', appointments[2], customers[2], 5, 'Ấn huyệt cột sống cực kỳ đã, hết hẳn nhức mỏi sau 120 phút trị liệu.', 'Chờ phản hồi', None, None),
            ('FB-1004', appointments[3], customers[3], 5, 'Nước gội bồ kết thơm dịu tự nhiên, gội xong ngủ ngon hẳn.', 'Chờ phản hồi', None, None),
            ('FB-1005', appointments[4], customers[4], 3, 'Lực massage ổn nhưng điều hòa trong phòng hơi lạnh lúc mới vào.', 'Đã ẩn', None, None),
        ]
        for fcode, appt, cust, rating, comment, fst, reply_txt, rep_by in fb_specs:
            Feedback.objects.create(
                feedback_code=fcode,
                appointment=appt,
                customer=cust,
                rating=rating,
                tags=['KTV chuyên nghiệp', 'Không gian yên tĩnh'] if rating >= 4 else ['Cần cải thiện nhiệt độ'],
                comment=comment,
                reply=reply_txt,
                replied_by=rep_by,
                replied_at=now - timedelta(hours=12) if rep_by else None,
                status=fst,
            )

        # Đồng bộ lại rating_avg và review_count trên 6 Service
        for svc in services:
            visible_fbs = Feedback.objects.filter(appointment__details__service=svc).exclude(status='Đã ẩn')
            cnt = visible_fbs.count()
            avg_val = sum(f.rating for f in visible_fbs) / cnt if cnt else 0
            svc.review_count = cnt
            svc.rating_avg = Decimal(str(round(avg_val, 1)))
            svc.save(update_fields=['review_count', 'rating_avg'])

        # 8. Khiếu nại (5 phiếu đủ các trạng thái)
        comp_specs = [
            ('KN-1001', appointments[1], customers[1], 'Thời gian chờ chuẩn bị phòng hơi lâu so với giờ hẹn 14:00.', 'Mong được hỗ trợ voucher cho lần sau', None, None, 'Chờ phân công'),
            ('KN-1002', appointments[4], customers[4], 'Điều hòa phòng trị liệu hơi lạnh trong 15 phút đầu trải nghiệm.', 'Nhân viên hỗ trợ điều chỉnh quy trình', staff_list[0], 'Đang trao đổi cùng bộ phận kỹ thuật kiểm tra nhiệt độ tiêu chuẩn.', 'Đang xử lý'),
            ('KN-1003', appointments[2], customers[2], 'Muốn đổi hương tinh dầu nhưng chưa được hỏi trước khi vào phòng.', 'Gọi điện tư vấn thêm', staff_list[1], 'Đã ghi nhận lịch gọi trao đổi khách vào 17h30.', 'Chờ liên hệ lại'),
            ('KN-1004', appointments[0], customers[0], 'Phòng VIP tầng 2 hơi có tiếng ồn bên ngoài hành lang lúc đầu ca.', 'Tặng mã ưu đãi bù trải nghiệm', staff_list[0], 'Đã xin lỗi trực tiếp và phát hành voucher đền bù 200.000đ cho chị Bảo Ngọc.', 'Đã xử lý'),
            ('KN-1005', appointments[3], customers[3], 'Khách yêu cầu hoàn tiền toàn bộ sau khi đã dùng trọn vẹn 60 phút dịch vụ không gặp sự cố.', 'Hoàn 100% chi phí', staff_list[2], 'Đã đối chiếu camera và phiếu xác nhận dịch vụ hoàn tất đúng quy chuẩn.', 'Đã từ chối'),
        ]
        complaints = []
        for ccode, appt, cust, desc, desired, astaff, note, cst in comp_specs:
            complaints.append(Complaint.objects.create(
                complaint_code=ccode,
                appointment=appt,
                customer=cust,
                description=desc,
                desired_resolution=desired,
                assigned_staff=astaff,
                resolution_note=note,
                status=cst,
            ))

        # 9. Mã Voucher (6 mã)
        Voucher.objects.create(
            voucher_code='CHAM20NEW', promotion=promos[0], customer=None,
            discount_type='PERCENT', discount_value=Decimal('20'), max_discount_amount=Decimal('300000'),
            min_order_amount=Decimal('300000'), status='Khả dụng', expiry_date=now + timedelta(days=30),
        )
        Voucher.objects.create(
            voucher_code='GIAM150K', promotion=promos[1], customer=None,
            discount_type='FIXED', discount_value=Decimal('150000'), max_discount_amount=None,
            min_order_amount=Decimal('500000'), status='Khả dụng', expiry_date=now + timedelta(days=20),
        )
        Voucher.objects.create(
            voucher_code='SENVANG100', promotion=promos[2], customer=customers[0],
            discount_type='FIXED', discount_value=Decimal('100000'), max_discount_amount=None,
            min_order_amount=Decimal('400000'), status='Khả dụng', expiry_date=now + timedelta(days=25),
        )
        Voucher.objects.create(
            voucher_code='DENBU200K', complaint=complaints[3], customer=customers[0],
            discount_type='FIXED', discount_value=Decimal('200000'), max_discount_amount=None,
            min_order_amount=Decimal('0'), status='Khả dụng', expiry_date=now + timedelta(days=45),
        )
        Voucher.objects.create(
            voucher_code='USED100K', promotion=promos[1], customer=customers[1],
            discount_type='FIXED', discount_value=Decimal('100000'), max_discount_amount=None,
            min_order_amount=Decimal('300000'), status='Đã dùng', used_at=now - timedelta(days=4),
            expiry_date=now + timedelta(days=10),
        )
        Voucher.objects.create(
            voucher_code='CHAOHE50K', promotion=promos[4], customer=customers[2],
            discount_type='FIXED', discount_value=Decimal('50000'), max_discount_amount=None,
            min_order_amount=Decimal('200000'), status='Hết hạn', expiry_date=now - timedelta(days=10),
        )

        # 10. Lịch sử tích điểm (6 bản ghi) - xóa sạch dòng auto nếu có trước khi tạo chuẩn
        MembershipPoint.objects.all().delete()
        mp_specs = [
            (customers[0].membership, '#LH1001', 85, 'Tích điểm dịch vụ Massage Đá Nóng Champa'),
            (customers[0].membership, '#VIP-GIFT', 150, 'Tặng điểm tri ân hội viên Hạng Kim Cương'),
            (customers[1].membership, '#LH1002', 69, 'Tích điểm dịch vụ Chăm Sóc Da Sen Vàng'),
            (customers[2].membership, '#LH1003', 125, 'Tích điểm dịch vụ Trị Liệu Cột Sống Chuyên Sâu'),
            (customers[3].membership, '#LH1004', 42, 'Tích điểm dịch vụ Gội Đầu Dưỡng Sinh Thảo Mộc'),
            (customers[4].membership, '#LH1005', 55, 'Tích điểm dịch vụ Massage Body Trị Liệu Vai Gáy'),
        ]
        for mem, appt_id, pts, reason in mp_specs:
            MembershipPoint.objects.create(
                membership=mem,
                appointment_id=appt_id,
                points_amount=pts,
                reason_description=reason,
            )

        # 11. Thông báo hệ thống (7 thông báo tinh gọn, phân loại rõ không trùng)
        Notification.objects.all().delete()
        notif_specs = [
            ('KM-1001', customers[0], 'Ưu Đãi Chào Thành Viên - Giảm 20%', 'Nhập mã CHAM20NEW khi đặt lịch Massage Body để được giảm 20% (tối đa 300.000đ).', promos[0]),
            ('APPT-1001', customers[0], 'Nhắc lịch hẹn #LH1006 hôm nay lúc 17:00', 'Cham Spa trân trọng nhắc chị Phạm Bảo Ngọc lịch trải nghiệm Massage Chân lúc 17:00 hôm nay.', None),
            ('KN-1001', customers[0], 'Khiếu nại #KN-1004 đã được xử lý xong', 'Cham Spa đã hoàn tất xử lý phiếu khiếu nại #KN-1004 và gửi tặng voucher DENBU200K vào ví của bạn.', None),
            ('DG-1001', customers[1], 'Cham Spa đã phản hồi đánh giá #FB-1002', 'Cảm ơn chị Trần Gia Hân đã đánh giá 4 sao. Mời chị xem phản hồi từ đại diện Cham Spa.', None),
            ('SYS-1001', customers[2], 'Cập nhật hồ sơ sức khỏe định kỳ', 'Vui lòng rà soát lại thông số huyết áp trong mục Hồ sơ sức khỏe trước ca trị liệu tiếp theo.', None),
            ('APPT-STAFF-1', staff_primary, 'Có lịch hẹn mới #LH1006 chờ xác nhận hôm nay', 'Khách hàng Phạm Bảo Ngọc vừa đặt lịch #LH1006 khung giờ 17:00 hôm nay.', None),
            ('KN-ADMIN-1', admin_user, 'Phiếu khiếu nại mới #KN-1001 cần phân công', 'Khách Trần Gia Hân vừa gửi phiếu khiếu nại #KN-1001 trạng thái Chờ phân công.', None),
        ]
        for ncode, u, title, content, promo in notif_specs:
            Notification.objects.create(
                notification_code=ncode,
                user=u,
                title=title,
                content=content,
                promotion=promo,
                delivery_channels='Web',
                status='Đã gửi',
            )

        # 12. FAQ Chatbot (6 câu hỏi)
        faq_specs = [
            ('FAQ-01', 'Giờ mở cửa', 'Cham Spa mở cửa từ mấy giờ đến mấy giờ?', 'giờ mở cửa, mấy giờ, đóng cửa, thời gian hoạt động', 'Cham Spa Đà Nẵng mở cửa phục vụ tất cả các ngày trong tuần từ 09:00 đến 22:00 (nhận khách cuối lúc 20:30).', 'Active'),
            ('FAQ-02', 'Bảng giá', 'Giá dịch vụ Massage Body và Đá Nóng bao nhiêu tiền?', 'giá, bao nhiêu tiền, bảng giá, massage body, đá nóng', 'Massage Body Trị Liệu 60 phút có giá 550.000đ và Massage Đá Nóng Champa 90 phút có giá 850.000đ. Hội viên Bạc/Vàng/Kim Cương được giảm thêm 5%-15%.', 'Active'),
            ('FAQ-03', 'Chính sách', 'Tôi muốn hủy hoặc dời lịch hẹn thì làm thế nào?', 'hủy lịch, dời lịch, hoàn tiền, đổi giờ', 'Quý khách có thể dời hoặc hủy lịch trực tiếp trong mục "Lịch hẹn của tôi" trước giờ hẹn và nhập số tài khoản nếu cần hoàn tiền.', 'Active'),
            ('FAQ-04', 'Thanh toán', 'Cham Spa hỗ trợ những hình thức thanh toán nào?', 'thanh toán, vietqr, chuyển khoản, tiền mặt', 'Spa hỗ trợ thanh toán chuyển khoản VietQR trực tuyến hoặc thanh toán trực tiếp tại quầy lễ tân sau khi hoàn thành dịch vụ.', 'Active'),
            ('FAQ-05', 'Sức khỏe', 'Mẹ bầu hoặc người huyết áp cao có sử dụng dịch vụ được không?', 'mẹ bầu, mang thai, huyết áp cao, dị ứng, sức khỏe', 'Có ạ! Quý khách chỉ cần cập nhật mục Hồ sơ sức khỏe để KTV điều chỉnh lực massage nhẹ nhàng và chọn tinh dầu an toàn.', 'Active'),
            ('FAQ-06', 'Hội viên', 'Quyền lợi tích điểm thẻ thành viên được tính ra sao?', 'hội viên, tích điểm, nâng hạng, kim cương', 'Mỗi 10.000đ thanh toán được quy đổi thành 1 điểm thưởng tích lũy để thăng hạng Bạc (500đ), Vàng (1.500đ), Kim Cương (3.000đ).', 'Hidden'),
        ]
        for code, cat, q, kw, ans, st in faq_specs:
            FAQ.objects.create(faq_code=code, category=cat, question=q, keywords=kw, answer=ans, status=st)

        # 13. Hội thoại Chatbox (5 phiên) & Tin nhắn mẫu (~15 tin)
        conv_specs = [
            (customers[0], staff_primary, 'Đang xử lý', 'Khách VIP', [
                ('Customer', 'Chào spa, chiều nay 17h mình qua làm chân có cần cọc trước không ạ?'),
                ('Bot', 'Dạ chào chị Bảo Ngọc, em đã chuyển yêu cầu của chị tới nhân viên tư vấn ngay ạ!'),
                ('Staff', 'Chào chị Ngọc, lịch #LH1006 lúc 17:00 hôm nay của chị đã được ghi nhận, chị ghé đúng giờ là được phục vụ ngay nhé.'),
            ]),
            (customers[1], None, 'Đang chờ', 'Mẹ bầu', [
                ('Customer', 'Mình đang mang thai tháng thứ 5 thì nên chọn gói massage nào phù hợp ạ?'),
                ('Bot', 'Dạ Cham Spa có bài massage nhẹ nhàng cho mẹ bầu và Gội đầu dưỡng sinh thảo mộc ạ. Em xin kết nối chuyên viên tư vấn kỹ hơn cho chị nhé.'),
                ('Customer', 'Vâng, nhờ bạn tư vấn giúp mình thêm về tinh dầu an toàn nha.'),
            ]),
            (customers[2], staff_list[1], 'Đang xử lý', 'Khách Body', [
                ('Customer', 'Hôm trước mình có bị đau vai gáy nặng, muốn đặt lại gói trị liệu cột sống.'),
                ('Staff', 'Chào anh Bảo Long, bên em gợi ý gói Trị Liệu Cột Sống Chuyên Sâu 120 phút kèm chườm ngải cứu cho anh ạ.'),
                ('Customer', 'Ok giữ giúp mình khung giờ cuối tuần nhé.'),
            ]),
            (customers[3], None, 'Bot xử lý', 'Gội đầu', [
                ('Customer', 'Cham Spa mở cửa tới mấy giờ vậy shop?'),
                ('Bot', 'Cham Spa Đà Nẵng mở cửa phục vụ tất cả các ngày trong tuần từ 09:00 đến 22:00 (nhận khách cuối lúc 20:30).'),
            ]),
            (customers[4], staff_list[0], 'Kết thúc', 'Khách mới', [
                ('Customer', 'Mình muốn hỏi cách dùng mã CHAM20NEW khi đặt lịch online.'),
                ('Staff', 'Bạn chọn dịch vụ và nhập mã CHAM20NEW ở bước xác nhận thanh toán là được giảm ngay 20% nhé!'),
                ('Customer', 'Mình áp dụng được rồi, cảm ơn spa nhiều ạ!'),
            ]),
        ]
        for cust, stf, cst, tag, msgs in conv_specs:
            conv = Conversation.objects.create(
                customer=cust,
                staff=stf,
                status=cst,
                customer_tag=tag,
                closed_at=now - timedelta(hours=2) if cst == 'Kết thúc' else None,
            )
            for sender_type, text in msgs:
                ConversationMessage.objects.create(
                    conversation=conv,
                    sender_type=sender_type,
                    message_type='TEXT',
                    content=text,
                )


if __name__ == '__main__':
    reset_and_seed_demo()
    print("=== ĐÃ LÀM SẠCH & KHỞI TẠO DỮ LIỆU DEMO CHUẨN (5-7 BẢN GHI/PHẦN) ===")
    summary_models = [
        ('Admin', User.objects.filter(is_superuser=True)),
        ('Staff', User.objects.filter(is_staff=True, is_superuser=False)),
        ('Customer', User.objects.filter(is_staff=False, is_superuser=False)),
        ('UserProfile', UserProfile.objects.all()),
        ('UserHealthProfile', UserHealthProfile.objects.all()),
        ('Category', Category.objects.all()),
        ('Service', Service.objects.all()),
        ('ServiceImage', ServiceImage.objects.all()),
        ('Tier', Tier.objects.all()),
        ('Membership', Membership.objects.all()),
        ('MembershipPoint', MembershipPoint.objects.all()),
        ('Promotion', Promotion.objects.all()),
        ('Voucher', Voucher.objects.all()),
        ('Notification', Notification.objects.all()),
        ('Appointment', Appointment.objects.all()),
        ('AppointmentDetail', AppointmentDetail.objects.all()),
        ('Invoice', Invoice.objects.all()),
        ('Feedback', Feedback.objects.all()),
        ('Complaint', Complaint.objects.all()),
        ('FAQ', FAQ.objects.all()),
        ('Conversation', Conversation.objects.all()),
        ('ConversationMessage', ConversationMessage.objects.all()),
    ]
    for label, qs in summary_models:
        print(f"- {label}: {qs.count()}")

