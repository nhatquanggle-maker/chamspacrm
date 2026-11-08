"""
API Endpoints cho Phân hệ Quản lý Lịch hẹn (MOD-01) - CHAMSPA CRM
Tác giả: Nhật Quang (Leader)
Khớp 100% Bảng Đặc tả Chốt & Thiết kế Figma:
  - Form đặt lịch hẹn trực tuyến: Node 828:515
  - Modal thanh toán VietQR: Node 818:2
  - Phiếu xác nhận đặt lịch hoàn tất (Digital Pass): Node 154:4478
"""

import random
from decimal import Decimal
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from core.models import Appointment, AppointmentDetail, Service, Voucher, Notification, User
from .serializers import (
    AppointmentCreateSerializer,
    AppointmentFullSerializer,
    ServiceSimpleSerializer,
    StaffQuickCreateSerializer
)


class AvailableSlotsAPI(APIView):
    """
    API kiểm tra danh sách khung giờ và số chỗ còn trống (UC-1.1)
    Khớp thiết kế Figma Node 828:515: Khung giờ còn trống
    Quy tắc nghiệp vụ: Giới hạn tối đa 10 khách / khung giờ
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        date_str = request.query_params.get('date')
        if not date_str:
            target_date = timezone.localdate()
        else:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({'error': 'Định dạng ngày không hợp lệ (YYYY-MM-DD)'}, status=status.HTTP_400_BAD_REQUEST)

        # Danh sách khung giờ chuẩn khớp Figma (Node 828:515 & Node 172:3086)
        standard_slots = [
            "09:00", "09:30", "10:00", "10:30", "14:00", "14:30",
            "15:00", "15:30", "16:00", "17:00", "17:30", "19:00"
        ]

        # Lấy số lượng khách đã đặt cho từng slot (trừ lịch đã Hủy)
        bookings = Appointment.objects.filter(
            appointment_date=target_date
        ).exclude(status='Cancelled').values('time_slot').annotate(booked_guests=Sum('total_guests'))

        booked_map = {b['time_slot']: (b['booked_guests'] or 0) for b in bookings}

        result = []
        for slot in standard_slots:
            booked = booked_map.get(slot, 0)
            remaining = max(0, 10 - booked)
            result.append({
                'slot': slot,
                'booked': booked,
                'remaining': remaining,
                'is_available': remaining > 0,
                'status_label': 'Còn chỗ' if remaining > 0 else 'Kín lịch'
            })

        return Response({
            'status': 'success',
            'date': target_date.strftime('%Y-%m-%d'),
            'slots': result
        }, status=status.HTTP_200_OK)


class ApplyVoucherAPI(APIView):
    """
    API kiểm tra và tính toán giảm giá của Voucher (UC-1.1)
    Khớp mã 'CHARMSPA' trong Figma Node 828:515 & Node 818:2 & Node 154:4478 (-111.000 VNĐ)
    Hỗ trợ cả voucher giảm theo % có trần (max_discount_amount) và giảm tiền mặt cố định.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        code = request.data.get('code', '').strip().upper()
        try:
            order_total = Decimal(str(request.data.get('order_total', 0)))
        except Exception:
            order_total = Decimal(0)

        if not code:
            return Response({'error': 'Vui lòng nhập mã Voucher'}, status=status.HTTP_400_BAD_REQUEST)

        voucher = Voucher.objects.filter(voucher_code=code, status='Khả dụng').first()
        if not voucher:
            return Response({'error': 'Mã Voucher không tồn tại hoặc đã hết lượt sử dụng.'}, status=status.HTTP_400_BAD_REQUEST)

        if voucher.expiry_date and voucher.expiry_date < timezone.now():
            return Response({'error': 'Mã Voucher đã hết hạn sử dụng.'}, status=status.HTTP_400_BAD_REQUEST)

        if voucher.min_order_amount and order_total < voucher.min_order_amount:
            min_fmt = f"{int(voucher.min_order_amount):,}".replace(',', '.')
            return Response({'error': f'Voucher chỉ áp dụng cho đơn hàng từ {min_fmt} VNĐ trở lên.'}, status=status.HTTP_400_BAD_REQUEST)

        # Tính toán mức giảm
        if voucher.discount_type in ['PERCENT', 'Phần trăm']:
            discount_amount = (order_total * Decimal(voucher.discount_value)) / Decimal(100)
            if voucher.max_discount_amount and discount_amount > voucher.max_discount_amount:
                discount_amount = Decimal(voucher.max_discount_amount)
        else:
            discount_amount = Decimal(voucher.discount_value)

        # Chặn mức giảm tối đa không vượt quá giá trị đơn hàng
        discount_amount = min(discount_amount, order_total)
        final_total = max(Decimal(0), order_total - discount_amount)

        return Response({
            'status': 'success',
            'success': True,
            'voucher_code': voucher.voucher_code,
            'discount_type': voucher.discount_type,
            'discount_value': float(voucher.discount_value),
            'discount_amount': float(discount_amount),
            'formatted_discount': f"-{int(discount_amount):,}".replace(',', '.') + " VNĐ",
            'final_total': float(final_total),
            'formatted_final_total': f"{int(final_total):,}".replace(',', '.') + " VNĐ"
        }, status=status.HTTP_200_OK)


class AppointmentCreateAPI(APIView):
    """
    API Tạo Lịch hẹn mới trực tuyến (UC-1.1)
    Khớp 100% Figma Node 828:515 (Form đặt lịch) & Node 818:2 (Modal VietQR)
    PHÂN QUYỀN NGHIÊM NGẶT:
      - BẮT BUỘC khách hàng phải đăng nhập (is_authenticated). Khách chưa đăng nhập -> 401 Unauthorized.
      - Staff / Admin (is_staff hoặc is_superuser) -> 403 Forbidden (chỉ dành riêng cho tài khoản Khách hàng).
      - Tự động điền và đồng bộ thông tin khách hàng từ tài khoản chính chủ đã đăng nhập.
      - Trạng thái sau tạo là 'Hold' (Chờ thanh toán QR).
      - Tạo bản ghi Appointment & AppointmentDetail trong 1 atomic transaction.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # 0. Kiểm tra phân quyền bắt buộc
        if not request.user.is_authenticated:
            return Response({
                'status': 'error',
                'error': 'Vui lòng đăng nhập tài khoản Khách hàng để thực hiện đặt lịch trải nghiệm.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        if request.user.is_staff or request.user.is_superuser:
            return Response({
                'status': 'error',
                'error': 'Tài khoản Quản trị viên (Admin) hoặc Nhân viên (Staff) không có quyền đặt lịch trải nghiệm. Chức năng này chỉ dành riêng cho Khách hàng.'
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = AppointmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        appointment_date = data['appointment_date']
        time_slot = data['time_slot']
        total_guests = data['total_guests']

        # 1. Kiểm tra sức chứa (Tối đa 10 khách/slot)
        booked = Appointment.objects.filter(
            appointment_date=appointment_date,
            time_slot=time_slot
        ).exclude(status='Cancelled').aggregate(total=Sum('total_guests'))['total'] or 0

        if booked + total_guests > 10:
            remaining = max(0, 10 - booked)
            return Response({
                'status': 'error',
                'error': f'Khung giờ {time_slot} ngày {appointment_date} chỉ còn {remaining} chỗ trống. Quý khách vui lòng chọn khung giờ khác.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Xử lý dịch vụ & tính toán tổng tiền
        guest_details = data.get('guest_details', [])
        default_service = None

        root_service_id = data.get('service_id')
        if root_service_id:
            default_service = Service.objects.filter(id=root_service_id, status='Hoạt động').first()
        if not default_service:
            default_service = Service.objects.filter(status='Hoạt động').first()

        if not default_service:
            return Response({
                'status': 'error',
                'error': 'Hiện chưa có dịch vụ nào đang hoạt động trong hệ thống Spa.'
            }, status=status.HTTP_400_BAD_REQUEST)

        calculated_total = Decimal(0)
        details_to_create = []

        if not guest_details:
            for idx in range(1, total_guests + 1):
                gender = 'Nam' if idx <= data.get('male_guests', 0) else 'Nữ'
                details_to_create.append({
                    'guest_index': idx,
                    'gender': gender,
                    'service': default_service,
                    'massage_pressure': 'Vừa'
                })
                calculated_total += default_service.price_vnd
        else:
            for idx, g in enumerate(guest_details, start=1):
                svc_id = g.get('service_id')
                svc = Service.objects.filter(id=svc_id, status='Hoạt động').first() if svc_id else default_service
                if not svc:
                    svc = default_service

                details_to_create.append({
                    'guest_index': g.get('guest_index', idx),
                    'gender': g.get('gender', 'Nam'),
                    'service': svc,
                    'massage_pressure': g.get('massage_pressure', 'Vừa')
                })
                calculated_total += svc.price_vnd

        # 3. Áp dụng Voucher nếu có
        applied_voucher = None
        discount_amount = Decimal(0)
        voucher_code = (data.get('voucher_code') or '').strip().upper()

        if voucher_code:
            voucher = Voucher.objects.filter(voucher_code=voucher_code, status='Khả dụng').first()
            if voucher and (not voucher.expiry_date or voucher.expiry_date >= timezone.now()):
                if not voucher.min_order_amount or calculated_total >= voucher.min_order_amount:
                    applied_voucher = voucher
                    if voucher.discount_type in ['PERCENT', 'Phần trăm']:
                        discount_amount = (calculated_total * Decimal(voucher.discount_value)) / Decimal(100)
                        if voucher.max_discount_amount and discount_amount > voucher.max_discount_amount:
                            discount_amount = Decimal(voucher.max_discount_amount)
                    else:
                        discount_amount = Decimal(voucher.discount_value)

        discount_amount = min(discount_amount, calculated_total)
        final_total = max(Decimal(0), calculated_total - discount_amount)

        # 4. Sinh mã lịch hẹn độc nhất: #LH + 5 chữ số (Khớp Figma: #LH88392)
        code = None
        for _ in range(15):
            cand = f"#LH{random.randint(10000, 99999)}"
            if not Appointment.objects.filter(appointment_code=cand).exists():
                code = cand
                break
        if not code:
            code = f"#LH{int(timezone.now().timestamp()) % 100000}"

        # 5. Gắn User chính chủ từ tài khoản khách hàng đã đăng nhập
        auth_user = request.user
        cust_name = (data.get('customer_name') or '').strip() or (auth_user.name or '').strip() or auth_user.get_full_name().strip() or auth_user.username
        cust_phone = (data.get('customer_phone') or '').strip() or (auth_user.phone or '').strip() or (auth_user.username if auth_user.username.isdigit() else '')
        cust_email = (data.get('customer_email') or '').strip() or (auth_user.email or '').strip()

        # 6. Tạo Appointment và AppointmentDetail trong 1 atomic transaction
        with transaction.atomic():
            appointment = Appointment.objects.create(
                appointment_code=code,
                user=auth_user,
                voucher=applied_voucher,
                appointment_date=appointment_date,
                time_slot=time_slot,
                total_guests=total_guests,
                male_guests=data.get('male_guests', 0),
                female_guests=data.get('female_guests', 0),
                customer_name=cust_name,
                customer_phone=cust_phone,
                customer_email=cust_email,
                preferred_contact_channel='Điện thoại',
                note=(data.get('note') or '').strip(),
                total_price=final_total,
                status='Hold'  # Khớp quy tắc Spec: Hold (Chờ thanh toán QR)
            )

            for item in details_to_create:
                AppointmentDetail.objects.create(
                    appointment=appointment,
                    service=item['service'],
                    guest_index=item['guest_index'],
                    gender=item['gender'],
                    massage_pressure=item['massage_pressure']
                )

        # 7. Tạo mã VietQR chuẩn Napas 247 theo MB Bank trong Figma Node 818:2
        bank_id = "MB"
        account_no = "0946020526"
        account_name = "CHAM SPA MASSAGE"
        clean_code_num = appointment.appointment_code.replace('#', '')
        qr_memo = f"CHAMSPA {clean_code_num}"
        vietqr_url = f"https://img.vietqr.io/image/{bank_id}-{account_no}-compact2.png?amount={int(final_total)}&addInfo={qr_memo}&accountName=CHAM%20SPA%20MASSAGE"

        weekday_map = {0: 'Thứ Hai', 1: 'Thứ Ba', 2: 'Thứ Tư', 3: 'Thứ Năm', 4: 'Thứ Sáu', 5: 'Thứ Bảy', 6: 'Chủ Nhật'}
        d = appointment.appointment_date
        date_display = f"{weekday_map.get(d.weekday(), '')}, ngày {d.day:02d}/{d.month:02d}/{d.year}"

        # 8. Trả về kết quả
        return Response({
            'status': 'success',
            'success': True,
            'message': 'Đặt lịch thành công',
            'id': appointment.id,
            'appointment_id': appointment.id,
            'appointment_code': appointment.appointment_code,
            'total_price': float(appointment.total_price),
            'formatted_total_price': f"{int(final_total):,}".replace(',', '.') + " VNĐ",
            'discount_applied': float(discount_amount),
            'discount_amount': float(discount_amount),
            'status_label': 'Hold',
            'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
            'date_display': date_display,
            'time_slot': appointment.time_slot,
            'customer_name': appointment.customer_name,
            'customer_phone': appointment.customer_phone,
            'total_guests': appointment.total_guests,
            'vietqr_url': vietqr_url,
            'bank_info': {
                'bank_name': 'MB BANK',
                'account_number': '0946 020 526',
                'account_name': account_name,
                'amount': int(final_total),
                'memo': qr_memo
            }
        }, status=status.HTTP_201_CREATED)


class ConfirmPaymentAPI(APIView):
    """
    API xác nhận đã quét QR thanh toán thành công (Figma Node 818:2 -> Node 154:4478)
    Chuyển trạng thái Appointment từ 'Hold'/'Pending' sang 'Confirmed'.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, pk=None):
        target_id = pk or request.data.get('appointment_id')
        code = request.data.get('appointment_code', '')

        appointment = None
        if target_id:
            appointment = Appointment.objects.filter(id=target_id).first()
        if not appointment and code:
            clean_code = code if code.startswith('#') else f"#{code}"
            appointment = Appointment.objects.filter(appointment_code=clean_code).first()

        if not appointment:
            return Response({'status': 'error', 'error': 'Không tìm thấy thông tin lịch hẹn.'}, status=status.HTTP_404_NOT_FOUND)

        # Chuyển trạng thái sang Confirmed
        appointment.status = 'Confirmed'
        appointment.save()

        # Tạo thông báo xác nhận nếu có liên kết tài khoản User
        if appointment.user:
            Notification.objects.create(
                user=appointment.user,
                title="Lịch hẹn đã được xác nhận!",
                content=f"Lịch hẹn {appointment.appointment_code} lúc {appointment.time_slot} ngày {appointment.appointment_date} đã được thanh toán và xác nhận thành công.",
                delivery_channels="Web",
                status="Đã gửi"
            )

        clean_code_redirect = appointment.appointment_code.replace('#', '')
        return Response({
            'status': 'success',
            'success': True,
            'message': 'Thanh toán thành công! Lịch hẹn của bạn đã được xác nhận.',
            'appointment_code': appointment.appointment_code,
            'appointment_status': 'Confirmed',
            'redirect_url': f"/appointment/success/{clean_code_redirect}/"
        }, status=status.HTTP_200_OK)


class AppointmentDetailAPI(APIView):
    """
    API lấy thông tin chi tiết một lịch hẹn (theo ID hoặc Mã lịch hẹn)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, identifier):
        appointment = None
        if str(identifier).isdigit():
            appointment = Appointment.objects.filter(id=int(identifier)).first()
        if not appointment:
            code = identifier if identifier.startswith('#') else f"#{identifier}"
            appointment = Appointment.objects.filter(appointment_code=code).first()

        if not appointment:
            return Response({'status': 'error', 'error': 'Không tìm thấy lịch hẹn.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AppointmentFullSerializer(appointment)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MyAppointmentsAPI(APIView):
    """
    API Quản lý lịch hẹn cá nhân của Khách hàng (UC-1.2)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        status_param = request.query_params.get('status')
        tab_param = request.query_params.get('tab')

        qs = Appointment.objects.filter(user=request.user).select_related('voucher').prefetch_related('details__service')

        if status_param:
            if status_param in ['Hold', 'Pending', 'Confirmed', 'In_Progress', 'Completed', 'Cancelled']:
                qs = qs.filter(status=status_param)
            elif status_param == 'upcoming':
                qs = qs.filter(status__in=['Hold', 'Pending', 'Confirmed'])
        elif tab_param:
            if tab_param == 'upcoming':
                qs = qs.filter(status__in=['Hold', 'Pending', 'Confirmed'])
            elif tab_param == 'in_progress':
                qs = qs.filter(status='In_Progress')
            elif tab_param == 'completed':
                qs = qs.filter(status='Completed')
            elif tab_param == 'cancelled':
                qs = qs.filter(status='Cancelled')

        qs = qs.order_by('-appointment_date', '-time_slot')
        serializer = AppointmentFullSerializer(qs, many=True)
        return Response({
            'status': 'success',
            'appointments': serializer.data
        }, status=status.HTTP_200_OK)


class RescheduleAPI(APIView):
    """
    API Dời lịch hẹn sang ngày giờ mới (UC-1.3)
    Khớp 100% Figma Node 172:3086 (Modal Dời lịch)
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        appointment = Appointment.objects.filter(id=pk, user=request.user).first()
        if not appointment:
            return Response({'status': 'error', 'error': 'Không tìm thấy lịch hẹn hoặc bạn không có quyền thao tác.'}, status=status.HTTP_404_NOT_FOUND)

        if appointment.status not in ['Hold', 'Pending', 'Confirmed']:
            return Response({'status': 'error', 'error': f'Lịch hẹn ở trạng thái {appointment.status} không được phép dời lịch.'}, status=status.HTTP_400_BAD_REQUEST)

        new_date_str = request.data.get('new_date') or request.data.get('appointment_date')
        new_slot = request.data.get('new_time_slot') or request.data.get('time_slot')

        if not new_date_str or not new_slot:
            return Response({'status': 'error', 'error': 'Vui lòng chọn ngày và khung giờ mới.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        except Exception:
            return Response({'status': 'error', 'error': 'Ngày mới không đúng định dạng (YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)

        # Kiểm tra không chọn ngày trong quá khứ
        if new_date < timezone.localdate():
            return Response({'status': 'error', 'error': 'Không thể dời lịch hẹn về ngày trong quá khứ.'}, status=status.HTTP_400_BAD_REQUEST)

        # Kiểm tra sức chứa tại khung giờ mới (Tối đa 10 khách/slot)
        booked_new = Appointment.objects.filter(
            appointment_date=new_date,
            time_slot=new_slot
        ).exclude(id=appointment.id).exclude(status='Cancelled').aggregate(t=Sum('total_guests'))['t'] or 0

        if booked_new + appointment.total_guests > 10:
            remaining = max(0, 10 - booked_new)
            return Response({'status': 'error', 'error': f'Khung giờ {new_slot} ngày {new_date_str} chỉ còn {remaining} chỗ, không đủ cho {appointment.total_guests} khách.'}, status=status.HTTP_400_BAD_REQUEST)

        old_date = appointment.appointment_date
        old_slot = appointment.time_slot

        appointment.appointment_date = new_date
        appointment.time_slot = new_slot
        appointment.save()

        # Tạo thông báo thông báo dời lịch
        if appointment.user:
            try:
                Notification.objects.create(
                    notification_code=f"TB{int(timezone.now().timestamp())}",
                    user=appointment.user,
                    title="Dời lịch hẹn thành công!",
                    content=f"Lịch hẹn {appointment.appointment_code} đã được dời từ ({old_slot} ngày {old_date}) sang ({new_slot} ngày {new_date}).",
                    delivery_channels="Web",
                    status="Đã gửi"
                )
            except Exception:
                pass

        weekday_map = {
            0: 'Thứ Hai', 1: 'Thứ Ba', 2: 'Thứ Tư', 3: 'Thứ Năm',
            4: 'Thứ Sáu', 5: 'Thứ Bảy', 6: 'Chủ Nhật'
        }
        w_name = weekday_map.get(new_date.weekday(), '')
        date_display = f"{new_slot}, {w_name} - {new_date.strftime('%d/%m/%Y')}"

        return Response({
            'status': 'success',
            'success': True,
            'message': f'Dời lịch hẹn {appointment.appointment_code} sang {date_display} thành công!',
            'appointment_code': appointment.appointment_code,
            'new_date': str(new_date),
            'new_time_slot': new_slot,
            'date_display': date_display
        }, status=status.HTTP_200_OK)


class CancelAPI(APIView):
    """
    API Hủy lịch hẹn kèm STK hoàn tiền (UC-1.4)
    Khớp 100% Figma Node 172:3088 (Modal Hủy lịch)
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        appointment = Appointment.objects.filter(id=pk, user=request.user).first()
        if not appointment:
            return Response({'status': 'error', 'error': 'Không tìm thấy lịch hẹn hoặc bạn không có quyền thao tác.'}, status=status.HTTP_404_NOT_FOUND)

        if appointment.status in ['Completed', 'Cancelled']:
            return Response({'status': 'error', 'error': f'Lịch hẹn đã {appointment.status}, không thể thực hiện thao tác hủy.'}, status=status.HTTP_400_BAD_REQUEST)

        cancel_reason = (request.data.get('cancel_reason') or '').strip()
        refund_account_number = (request.data.get('refund_account_number') or '').strip()
        bank_name = (request.data.get('bank_name') or '').strip()
        account_holder = (request.data.get('account_holder') or '').strip()

        if not cancel_reason:
            return Response({'status': 'error', 'error': 'Vui lòng chọn hoặc nhập lý do hủy lịch.'}, status=status.HTTP_400_BAD_REQUEST)

        if not refund_account_number:
            return Response({'status': 'error', 'error': 'Vui lòng cung cấp số tài khoản ngân hàng để nhận hoàn tiền cọc.'}, status=status.HTTP_400_BAD_REQUEST)

        # Ghép chuỗi thông tin STK hoàn tiền
        refund_info_parts = []
        if bank_name:
            refund_info_parts.append(bank_name)
        refund_info_parts.append(refund_account_number)
        if account_holder:
            refund_info_parts.append(f"({account_holder})")

        full_refund_account = " - ".join(refund_info_parts)

        appointment.status = 'Cancelled'
        appointment.cancel_reason = cancel_reason
        appointment.refund_account_number = full_refund_account
        appointment.save()

        # Tạo thông báo xác nhận hủy lịch
        if appointment.user:
            try:
                Notification.objects.create(
                    notification_code=f"TB{int(timezone.now().timestamp())}",
                    user=appointment.user,
                    title="Xác nhận yêu cầu hủy lịch hẹn",
                    content=f"Yêu cầu hủy lịch hẹn {appointment.appointment_code} đã được tiếp nhận. Bộ phận Kế toán sẽ hoàn tất đối soát hoàn cọc về tài khoản {full_refund_account} trong 24h làm việc.",
                    delivery_channels="Web",
                    status="Đã gửi"
                )
            except Exception:
                pass

        return Response({
            'status': 'success',
            'success': True,
            'message': f'Lịch hẹn {appointment.appointment_code} đã được hủy thành công. Kế toán sẽ đối soát và hoàn tiền cọc trong vòng 24 giờ.',
            'appointment_code': appointment.appointment_code,
            'cancel_reason': cancel_reason,
            'refund_account': full_refund_account
        }, status=status.HTTP_200_OK)


class AdminAppointmentListAPI(APIView):
    """
    API Quản lý danh sách lịch hẹn toàn Spa (UC-1.5)
    Dành cho Quản lý (is_superuser) và Nhân viên Lễ tân / CSKH (is_staff)
    Khớp 100% Figma Node 110:4969 (Staff Dashboard / Quản lý lịch hẹn)
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, pk=None):
        if pk:
            appointment = Appointment.objects.filter(id=pk).select_related('voucher', 'user').prefetch_related('details__service').first()
            if not appointment:
                return Response({'status': 'error', 'error': 'Không tìm thấy lịch hẹn.'}, status=status.HTTP_404_NOT_FOUND)
            serializer = AppointmentFullSerializer(appointment)
            return Response(serializer.data, status=status.HTTP_200_OK)

        qs = Appointment.objects.all().select_related('voucher', 'user').prefetch_related('details__service')

        # 1. Lọc theo ngày
        date_filter = request.query_params.get('date')
        if date_filter:
            try:
                d = datetime.strptime(date_filter, '%Y-%m-%d').date()
                qs = qs.filter(appointment_date=d)
            except ValueError:
                pass

        # 2. Lọc theo khung giờ
        time_slot = request.query_params.get('time_slot')
        if time_slot and time_slot != 'all' and time_slot != 'Tất cả khung giờ':
            qs = qs.filter(time_slot=time_slot)

        # 3. Lọc theo trạng thái
        status_filter = request.query_params.get('status')
        if status_filter and status_filter != 'all' and status_filter != 'Tất cả trạng thái':
            if status_filter in ['Hold', 'Pending', 'Confirmed', 'In_Progress', 'Completed', 'Cancelled']:
                qs = qs.filter(status=status_filter)
            elif status_filter == 'upcoming':
                qs = qs.filter(status__in=['Hold', 'Pending', 'Confirmed'])

        # 4. Tìm kiếm từ khóa (Mã đơn, Tên khách, SĐT)
        search_query = request.query_params.get('search') or request.query_params.get('q')
        if search_query:
            search_query = search_query.strip()
            qs = qs.filter(
                Q(appointment_code__icontains=search_query) |
                Q(customer_name__icontains=search_query) |
                Q(customer_phone__icontains=search_query)
            )

        # Thống kê nhanh theo tập dữ liệu hiện tại
        today_date = timezone.localdate()
        today_qs = Appointment.objects.filter(appointment_date=today_date)
        
        counts = {
            'total_today': today_qs.count(),
            'in_progress': today_qs.filter(status='In_Progress').count(),
            'confirmed': today_qs.filter(status='Confirmed').count(),
            'pending': today_qs.filter(status__in=['Hold', 'Pending']).count(),
            'completed': today_qs.filter(status='Completed').count(),
            'cancelled': today_qs.filter(status='Cancelled').count(),
        }

        qs = qs.order_by('time_slot', '-created_at')
        serializer = AppointmentFullSerializer(qs, many=True)
        return Response({
            'status': 'success',
            'counts': counts,
            'total_count': qs.count(),
            'appointments': serializer.data
        }, status=status.HTTP_200_OK)

    def put(self, request, pk=None):
        return self._update_status(request, pk)

    def post(self, request, pk=None):
        return self._update_status(request, pk)

    def _update_status(self, request, pk=None):
        target_id = pk or request.data.get('id') or request.data.get('appointment_id')
        appointment = Appointment.objects.filter(id=target_id).first()
        if not appointment:
            return Response({'status': 'error', 'error': 'Không tìm thấy lịch hẹn.'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        valid_statuses = ['Hold', 'Pending', 'Confirmed', 'In_Progress', 'Completed', 'Cancelled']
        if new_status not in valid_statuses:
            return Response({'status': 'error', 'error': f"Trạng thái '{new_status}' không hợp lệ."}, status=status.HTTP_400_BAD_REQUEST)

        old_status = appointment.status
        appointment.status = new_status
        appointment.save()

        # Tạo thông báo thông báo cho khách hàng nếu có tài khoản User
        if appointment.user and old_status != new_status:
            status_labels = {
                'Confirmed': 'đã được xác nhận',
                'In_Progress': 'đang được phục vụ',
                'Completed': 'đã hoàn thành',
                'Cancelled': 'đã bị hủy'
            }
            label_txt = status_labels.get(new_status, new_status)
            try:
                Notification.objects.create(
                    notification_code=f"TB{int(timezone.now().timestamp())}",
                    user=appointment.user,
                    title=f"Lịch hẹn {appointment.appointment_code} {label_txt}",
                    content=f"Lịch hẹn {appointment.appointment_code} ({appointment.time_slot} ngày {appointment.appointment_date}) hiện {label_txt}.",
                    delivery_channels="Web",
                    status="Đã gửi"
                )
            except Exception:
                pass

        return Response({
            'status': 'success',
            'success': True,
            'appointment_id': appointment.id,
            'appointment_code': appointment.appointment_code,
            'old_status': old_status,
            'updated_status': new_status,
            'message': f"Đã cập nhật trạng thái lịch hẹn {appointment.appointment_code} thành '{new_status}'."
        }, status=status.HTTP_200_OK)


class StaffQuickCreateAppointmentAPI(APIView):
    """
    API tạo nhanh lịch hẹn tại quầy dành cho Nhân viên Lễ tân / CSKH (UC-1.5 Step 4)
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        serializer = StaffQuickCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        service = Service.objects.filter(id=data['service_id'], status='Hoạt động').first()
        if not service:
            return Response({'status': 'error', 'error': 'Dịch vụ được chọn không khả dụng.'}, status=status.HTTP_400_BAD_REQUEST)

        total_guests = data.get('total_guests', 1)
        total_price = service.price_vnd * total_guests

        # Sinh mã lịch hẹn độc nhất #LHxxxxx
        code = None
        for _ in range(10):
            rand_code = f"#{random.randint(10000, 99999)}"
            if not Appointment.objects.filter(appointment_code=rand_code).exists():
                code = rand_code
                break
        if not code:
            code = f"#LH{int(timezone.now().timestamp()) % 100000:05d}"

        appointment = Appointment.objects.create(
            appointment_code=code,
            user=None, # Đặt tại quầy
            customer_name=data['customer_name'],
            customer_phone=data['customer_phone'],
            customer_email=data.get('customer_email', ''),
            appointment_date=data['appointment_date'],
            time_slot=data['time_slot'],
            total_guests=total_guests,
            male_guests=data.get('male_guests', 0),
            female_guests=data.get('female_guests', total_guests),
            preferred_contact_channel='Quầy lễ tân',
            note=data.get('note', 'Đặt trực tiếp tại quầy'),
            total_price=total_price,
            status=data.get('status', 'Confirmed')
        )

        # Tạo chi tiết dịch vụ
        for idx in range(1, total_guests + 1):
            gender = 'Nam' if idx <= data.get('male_guests', 0) else 'Nữ'
            AppointmentDetail.objects.create(
                appointment=appointment,
                guest_index=idx,
                gender=gender,
                service=service,
                massage_pressure='Vừa'
            )

        full_serializer = AppointmentFullSerializer(appointment)
        return Response({
            'status': 'success',
            'success': True,
            'message': f'Tiếp nhận lịch hẹn {appointment.appointment_code} tại quầy thành công!',
            'appointment': full_serializer.data
        }, status=status.HTTP_201_CREATED)
