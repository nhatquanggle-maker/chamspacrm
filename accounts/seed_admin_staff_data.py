"""
Seed data chuẩn xác 100% theo thiết kế Figma Node 221:3117:
- Admin - Danh sách tài khoản nhân viên
- Chức vụ: Lễ tân / CSKH, Kỹ thuật viên (KTV), Thu ngân, Quản lý ca
- Trạng thái: Hoạt động, Nghỉ phép, Tạm khóa
"""
import os
import sys
import django

if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

from django.contrib.auth.models import Group
from core.models import User, UserProfile
from datetime import date

def run_seed():
    print("-> Bắt đầu nạp dữ liệu nhân viên chuẩn Figma Node 221:3117...")

    # Tạo các nhóm chức vụ Group
    departments = [
        'Lễ tân / CSKH',
        'Kỹ thuật viên (KTV)',
        'Thu ngân',
        'Quản lý ca',
        'Bác sĩ / Chuyên gia'
    ]
    group_map = {}
    for d in departments:
        grp, _ = Group.objects.get_or_create(name=d)
        group_map[d] = grp

    # Danh sách 7 nhân viên chuẩn mẫu trong Figma 221:3117
    figma_staff_list = [
        {
            'name': 'Lê Thị Mai',
            'phone': '0935820114',
            'display_phone': '0935 820 114',
            'email': 'mai.le@chamspa.vn',
            'position': 'Lễ tân / CSKH',
            'status': 'Hoạt động',
            'is_active': True,
            'gender': 'Nữ',
            'birthday': date(1996, 5, 12),
        },
        {
            'name': 'Nguyễn Trâm Anh',
            'phone': '0908211635',
            'display_phone': '0908 211 635',
            'email': 'anh.nt@chamspa.vn',
            'position': 'Kỹ thuật viên (KTV)',
            'status': 'Hoạt động',
            'is_active': True,
            'gender': 'Nữ',
            'birthday': date(1998, 8, 20),
        },
        {
            'name': 'Đỗ Minh Tuấn',
            'phone': '0982115920',
            'display_phone': '0982 115 920',
            'email': 'tuan.do@chamspa.vn',
            'position': 'Quản lý ca',
            'status': 'Hoạt động',
            'is_active': True,
            'gender': 'Nam',
            'birthday': date(1992, 11, 4),
        },
        {
            'name': 'Trần Hải Phong',
            'phone': '0913730522',
            'display_phone': '0913 730 522',
            'email': 'phong.tran@chamspa.vn',
            'position': 'Thu ngân',
            'status': 'Nghỉ phép',
            'is_active': True,
            'gender': 'Nam',
            'birthday': date(1997, 2, 18),
        },
        {
            'name': 'Võ Ngọc Lan',
            'phone': '0905446883',
            'display_phone': '0905 446 883',
            'email': 'lan.vo@chamspa.vn',
            'position': 'Kỹ thuật viên (KTV)',
            'status': 'Hoạt động',
            'is_active': True,
            'gender': 'Nữ',
            'birthday': date(1995, 9, 30),
        },
        {
            'name': 'Lê Quốc Dũng',
            'phone': '0934905117',
            'display_phone': '0934 905 117',
            'email': 'dung.le@chamspa.vn',
            'position': 'Kỹ thuật viên (KTV)',
            'status': 'Tạm khóa',
            'is_active': False,
            'gender': 'Nam',
            'birthday': date(1994, 7, 15),
        },
        {
            'name': 'Phạm Hồng Nhung',
            'phone': '0902611093',
            'display_phone': '0902 611 093',
            'email': 'nhung.pham@chamspa.vn',
            'position': 'Lễ tân / CSKH',
            'status': 'Hoạt động',
            'is_active': True,
            'gender': 'Nữ',
            'birthday': date(1999, 12, 8),
        },
    ]

    # Thêm các nhân viên bổ sung để đạt quy mô 18–25 nhân viên như Figma
    additional_staff = [
        ('Hoàng Diệu Linh', '0903112233', 'linh.hoang@chamspa.vn', 'Lễ tân / CSKH', 'Hoạt động', True, 'Nữ'),
        ('Nguyễn Đức Thắng', '0905223344', 'thang.nguyen@chamspa.vn', 'Kỹ thuật viên (KTV)', 'Hoạt động', True, 'Nam'),
        ('Bùi Quỳnh Nga', '0906334455', 'nga.bui@chamspa.vn', 'Thu ngân', 'Hoạt động', True, 'Nữ'),
        ('Trịnh Gia Bảo', '0907445566', 'bao.trinh@chamspa.vn', 'Quản lý ca', 'Hoạt động', True, 'Nam'),
        ('Đinh Phương Thảo', '0908556677', 'thao.dinh@chamspa.vn', 'Kỹ thuật viên (KTV)', 'Nghỉ phép', True, 'Nữ'),
        ('Phan Văn Toàn', '0909667788', 'toan.phan@chamspa.vn', 'Kỹ thuật viên (KTV)', 'Hoạt động', True, 'Nam'),
        ('Vũ Thùy Chi', '0910778899', 'chi.vu@chamspa.vn', 'Lễ tân / CSKH', 'Hoạt động', True, 'Nữ'),
        ('Cao Minh Nhật', '0911889900', 'nhat.cao@chamspa.vn', 'Kỹ thuật viên (KTV)', 'Hoạt động', True, 'Nam'),
        ('Lý Mỹ Dung', '0912990011', 'dung.ly@chamspa.vn', 'Thu ngân', 'Hoạt động', True, 'Nữ'),
        ('Dương Khắc Tiệp', '0913001122', 'tiep.duong@chamspa.vn', 'Bác sĩ / Chuyên gia', 'Hoạt động', True, 'Nam'),
        ('Tạ Bảo Uyên', '0914112233', 'uyen.ta@chamspa.vn', 'Kỹ thuật viên (KTV)', 'Tạm khóa', False, 'Nữ'),
    ]

    for item in additional_staff:
        figma_staff_list.append({
            'name': item[0],
            'phone': item[1],
            'display_phone': item[1],
            'email': item[2],
            'position': item[3],
            'status': item[4],
            'is_active': item[5],
            'gender': item[6],
            'birthday': date(1996, 1, 1),
        })

    seeded_count = 0
    for s in figma_staff_list:
        u, created = User.objects.get_or_create(
            phone=s['phone'],
            defaults={
                'username': s['phone'],
                'name': s['name'],
                'email': s['email'],
                'is_staff': True,
                'is_superuser': False,
                'is_active': s['is_active'],
                'first_name': s['position'],
                'last_name': s['status'],
            }
        )
        # Cập nhật thông tin nếu đã tồn tại
        u.name = s['name']
        u.email = s['email']
        u.is_staff = True
        u.is_active = s['is_active']
        u.first_name = s['position']  # Chức vụ
        u.last_name = s['status']    # Trạng thái làm việc
        u.set_password('Cham@2026')
        u.save()

        # Nhóm quyền Group
        if s['position'] in group_map:
            u.groups.set([group_map[s['position']]])

        # UserProfile
        p, _ = UserProfile.objects.get_or_create(user=u)
        p.gender = s['gender']
        p.birthday = s['birthday']
        p.save()
        seeded_count += 1

    print(f"-> Đã nạp thành công {seeded_count} nhân viên Cham Spa chuẩn Figma Node 221:3117!")

if __name__ == '__main__':
    run_seed()
