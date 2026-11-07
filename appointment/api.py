import random
from decimal import Decimal
from datetime import datetime, time, timedelta

from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from core.models import Appointment, AppointmentDetail, Service, Voucher, Notification
from .serializers import (
    AppointmentCreateSerializer,
    AppointmentFullSerializer,
    ServiceSimpleSerializer
)


class AvailableSlotsAPI(APIView):
    """
    API kiểm tra khung giờ còn trống (UC-1.1)
    Giới hạn tối đa 10 khách / khung giờ
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

        # Danh sách các khung giờ hoạt động chuẩn Cham Spa
        standard_slots = [
            "09:00", "10:00", "11:00", "13:30", "14:00",
            "15:00", "16:00", "17:00", "18:30", "19:00", "20:00"
        ]

        # Truy vấn số lượng khách đã đặt cho từng slot trong ngày (bỏ qua lịch đã Hủy)
        bookings = Appointment.objects.filter(
            appointment_date=target_date
        ).exclude(status='Cancelled').values('time_slot').annotate(booked_guests=Sum('total_guests'))

        booked_map = {b['time_slot']: b['booked_guests'] or 0 for b in bookings}

        result = []
        for slot in standard_slots:
            booked = booked_map.get(slot, 0)
            remaining = max(0, 10 - booked)
            result.append({
                'slot': slot,
                'booked': booked,
                'remaining': remaining,
                'is_available': remaining > 0,
                'status_label': 'Còn chỗ' if remaining > 0 else 'Hết chỗ'
            })

        return Response({
            'date': target_date.strftime('%Y-%m-%d'),
            'slots': result
        }, status=status.HTTP_200_OK)


class ApplyVoucherAPI(APIView):
    """
    API kiểm tra và tính toán giảm giá của Voucher (UC-1.1)
    Khớp mã 'CHARMSPA' trong Figma Node 828:515 (-111.000 VNĐ)
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        code = request.data.get('code', '').strip().upper()
        order_total = Decimal(str(request.data.get('order_total', 0)))

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

        # Tính toán tiền giảm giá
        if voucher.discount_type == 'Phần trăm':
            discount_amount = (order_total * Decimal(voucher.discount_value)) / Decimal(100)
            if voucher.max_discount_amount and discount_amount > voucher.max_discount_amount:
                discount_amount = voucher.max_discount_amount
        else:
            discount_amount = Decimal(voucher.discount_value)

        # Làm tròn tiền giảm giá
        discount_amount = min(discount_amount, order_total)
        final_total = max(Decimal(0), order_total - discount_amount)

        return Response({
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
    Khớp 100% Figma Node 828:515 & Node 818:2
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = AppointmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

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
            return Response({
                'error': f'Khung giờ {time_slot} ngày {appointment_date} chỉ còn {max(0, 10 - booked)} chỗ trống. Quý khách vui lòng chọn khung giờ khác.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Xử lý tính toán tổng tiền từ danh sách dịch vụ
        guest_details = data.get('guest_details', [])
        default_service = Service.objects.filter(status='Hoạt động').first()

        calculated_total = Decimal(0)
        details_to_create = []

        if not guest_details:
            # Nếu không truyền chi tiết từng khách, mặc định lấy dịch vụ đầu tiên
            if not default_service:
                return Response({'error': 'Hiện chưa có dịch vụ nào hoạt động trong hệ thống.'}, status=status.HTTP_400_BAD_REQUEST)
            for idx in range(1, total_guests + 1):
                gender = 'Nam' if idx <= data['male_guests'] else 'Nữ'
                details_to_create.append({
                    'guest_index': idx,
                    'gender': gender,
                    'service': default_service,
                    'massage_pressure': 'Vừa'
                })
                calculated_total += default_service.price_vnd
        else:
            for g in guest_details:
                svc = Service.objects.filter(id=g.get('service_id')).first() or default_service
                if not svc:
                    continue
                details_to_create.append({
                    'guest_index': g.get('guest_index', 1),
                    'gender': g.get('gender', 'Nam'),
                    'service': svc,
                    'massage_pressure': g.get('massage_pressure', 'Vừa')
                })
                calculated_total += svc.price_vnd

        # 3. Áp dụng Voucher nếu có
        applied_voucher = None
        discount_amount = Decimal(0)
        voucher_code = data.get('voucher_code', '').strip().upper()
        if voucher_code:
            voucher = Voucher.objects.filter(voucher_code=voucher_code, status='Khả dụng').first()
            if voucher and (not voucher.expiry_date or voucher.expiry_date >= timezone.now()):
                if not voucher.min_order_amount or calculated_total >= voucher.min_order_amount:
                    applied_voucher = voucher
                    if voucher.discount_type == 'Phần trăm':
                        discount_amount = (calculated_total * Decimal(voucher.discount_value)) / Decimal(100)
                        if voucher.max_discount_amount and discount_amount > voucher.max_discount_amount:
                            discount_amount = voucher.max_discount_amount
                    else:
                        discount_amount = Decimal(voucher.discount_value)

        final_total = max(Decimal(0), calculated_total - discount_amount)

        # 4. Tạo mã lịch hẹn độc nhất vô nhị: #LH + 5 chữ số ngẫu nhiên (Ví dụ: #LH88392)
        code = None
        for _ in range(10):
            cand = f"#LH{random.randint(10000, 99999)}"
            if not Appointment.objects.filter(appointment_code=cand).exists():
                code = cand
                break
        if not code:
            code = f"#LH{int(timezone.now().timestamp()) % 100000}"

        # 5. Gắn User nếu đã đăng nhập
        user = request.user if request.user.is_authenticated else None

        # 6. Tạo bản ghi Appointment với trạng thái ban đầu 'Hold' (Giữ chỗ chờ quét QR)
        appointment = Appointment.objects.create(
            appointment_code=code,
            user=user,
            voucher=applied_voucher,
            appointment_date=appointment_date,
            time_slot=time_slot,
            total_guests=total_guests,
            male_guests=data['male_guests'],
            female_guests=data['female_guests'],
            customer_name=data['customer_name'],
            customer_phone=data['customer_phone'],
            customer_email=data.get('customer_email', ''),
            preferred_contact_channel=data.get('preferred_contact_channel', 'Zalo / Điện thoại'),
            note=data.get('note', ''),
            total_price=final_total,
            status='Hold'
        )

        # 7. Tạo bản ghi chi tiết AppointmentDetail
        for d in details_to_create:
            AppointmentDetail.objects.create(
                appointment=appointment,
                service=d['service'],
                guest_index=d['guest_index'],
                gender=d['gender'],
                massage_pressure=d['massage_pressure']
            )

        # 8. Tạo URL VietQR chuẩn NAPAS theo đúng thông tin MB Bank trong Figma Node 818:2
        # MB Bank | Số tài khoản: 0946020526 | Chủ TK: CHAM SPA MASSAGE
        account_no = "0946020526"
        bank_id = "MB"
        qr_memo = f"CHAMSPA {appointment.appointment_code.replace('#', '')}"
        vietqr_url = f"https://img.vietqr.io/image/{bank_id}-{account_no}-compact2.png?amount={int(final_total)}&addInfo={qr_memo}&accountName=CHAM%20SPA%20MASSAGE"

        return Response({
            'success': True,
            'message': 'Đặt lịch giữ chỗ thành công! Vui lòng quét mã QR để hoàn tất.',
            'appointment_id': appointment.id,
            'appointment_code': appointment.appointment_code,
            'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
            'date_display': f"Thứ {appointment.appointment_date.weekday() + 2 if appointment.appointment_date.weekday() < 6 else 'Chủ Nhật'}, {appointment.appointment_date.day}/{appointment.appointment_date.month}/{appointment.appointment_date.year}",
            'time_slot': appointment.time_slot,
            'customer_name': appointment.customer_name,
            'customer_phone': appointment.customer_phone,
            'total_guests': appointment.total_guests,
            'total_price': float(appointment.total_price),
            'formatted_total_price': f"{int(final_total):,}".replace(',', '.') + " VNĐ",
            'discount_amount': float(discount_amount),
            'vietqr_url': vietqr_url,
            'bank_info': {
                'bank_name': 'MB BANK',
                'account_number': '0946 020 526',
                'account_name': 'CHAM SPA MASSAGE',
                'amount': int(final_total),
                'memo': qr_memo
            }
        }, status=status.HTTP_201_CREATED)


class ConfirmPaymentAPI(APIView):
    """
    API xác nhận đã quét QR thanh toán thành công (Node 818:2 -> Node 154:4478)
    Chuyển trạng thái Appointment từ 'Hold' sang 'Confirmed'
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, pk):
        appointment = Appointment.objects.filter(id=pk).first()
        if not appointment:
            # Thử tìm theo appointment_code
            code = request.data.get('appointment_code', '')
            appointment = Appointment.objects.filter(appointment_code=code).first()

        if not appointment:
            return Response({'error': 'Không tìm thấy thông tin lịch hẹn.'}, status=status.HTTP_404_NOT_FOUND)

        # Chuyển trạng thái thành 'Confirmed'
        appointment.status = 'Confirmed'
        appointment.save()

        # Tạo thông báo xác nhận nếu có user
        if appointment.user:
            Notification.objects.create(
                user=appointment.user,
                title="Đặt lịch thành công!",
                content=f"Lịch hẹn {appointment.appointment_code} lúc {appointment.time_slot} ngày {appointment.appointment_date} đã được xác nhận thanh toán.",
                notification_type="Lịch hẹn"
            )

        return Response({
            'success': True,
            'message': 'Xác nhận thanh toán thành công!',
            'appointment_code': appointment.appointment_code,
            'redirect_url': f"/appointment/success/{appointment.appointment_code.replace('#', '')}/"
        }, status=status.HTTP_200_OK)


class AppointmentDetailAPI(APIView):
    """
    API lấy thông tin chi tiết một lịch hẹn (Theo ID hoặc Mã lịch hẹn)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, identifier):
        if str(identifier).isdigit():
            appointment = Appointment.objects.filter(id=int(identifier)).first()
        else:
            code = identifier if identifier.startswith('#') else f"#{identifier}"
            appointment = Appointment.objects.filter(appointment_code=code).first()

        if not appointment:
            return Response({'error': 'Không tìm thấy lịch hẹn.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AppointmentFullSerializer(appointment)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MyAppointmentsAPI(APIView):
    """
    API Quản lý lịch hẹn cá nhân của Khách hàng (UC-1.2)
    Lọc theo các tabs: 'upcoming' (Hold, Pending, Confirmed), 'in_progress', 'completed', 'cancelled'
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tab = request.query_params.get('tab', 'upcoming')
        user = request.user

        qs = Appointment.objects.filter(user=user)

        if tab == 'upcoming':
            qs = qs.filter(status__in=['Hold', 'Pending', 'Confirmed']).order_by('appointment_date', 'time_slot')
        elif tab == 'in_progress':
            qs = qs.filter(status='In_Progress').order_by('-appointment_date')
        elif tab == 'completed':
            qs = qs.filter(status='Completed').order_by('-appointment_date')
        elif tab == 'cancelled':
            qs = qs.filter(status='Cancelled').order_by('-appointment_date')
        else:
            qs = qs.order_by('-created_at')

        serializer = AppointmentFullSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RescheduleAPI(APIView):
    """
    API Dời lịch hẹn (UC-1.3)
    Điều kiện: Cách giờ hẹn cũ >= 2 tiếng, khung giờ mới còn < 10 khách
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        appointment = Appointment.objects.filter(id=pk, user=request.user).first()
        if not appointment:
            return Response({'error': 'Không tìm thấy lịch hẹn hoặc bạn không có quyền thao tác.'}, status=status.HTTP_404_NOT_FOUND)

        if appointment.status not in ['Hold', 'Pending', 'Confirmed']:
            return Response({'error': f'Lịch hẹn ở trạng thái {appointment.status} không được phép dời lịch.'}, status=status.HTTP_400_BAD_REQUEST)

        # Kiểm tra điều kiện >= 2 tiếng
        try:
            slot_hour, slot_min = map(int, appointment.time_slot.split(':'))
            appt_dt = datetime.combine(appointment.appointment_date, time(slot_hour, slot_min))
            appt_dt = timezone.make_aware(appt_dt, timezone.get_current_timezone())
            if appt_dt - timezone.now() < timedelta(hours=2):
                return Response({'error': 'Không thể dời lịch trước giờ hẹn dưới 2 tiếng. Quý khách vui lòng liên hệ hotline 0987 773 777 để được hỗ trợ.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            pass

        new_date_str = request.data.get('appointment_date')
        new_slot = request.data.get('time_slot')

        try:
            new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        except Exception:
            return Response({'error': 'Ngày hẹn mới không hợp lệ.'}, status=status.HTTP_400_BAD_REQUEST)

        # Kiểm tra slot mới còn chỗ trống
        booked = Appointment.objects.filter(
            appointment_date=new_date,
            time_slot=new_slot
        ).exclude(id=appointment.id).exclude(status='Cancelled').aggregate(t=Sum('total_guests'))['t'] or 0

        if booked + appointment.total_guests > 10:
            return Response({'error': f'Khung giờ {new_slot} ngày {new_date} đã kín lịch, vui lòng chọn khung giờ khác.'}, status=status.HTTP_400_BAD_REQUEST)

        appointment.appointment_date = new_date
        appointment.time_slot = new_slot
        appointment.save()

        Notification.objects.create(
            user=request.user,
            title="Dời lịch hẹn thành công",
            content=f"Lịch hẹn {appointment.appointment_code} đã được dời sang ngày {new_date} lúc {new_slot}.",
            notification_type="Lịch hẹn"
        )

        return Response({
            'success': True,
            'message': 'Dời lịch hẹn thành công!',
            'appointment': AppointmentFullSerializer(appointment).data
        }, status=status.HTTP_200_OK)


class CancelAPI(APIView):
    """
    API Hủy lịch hẹn (UC-1.4)
    Điều kiện: Cách giờ hẹn cũ >= 4 tiếng, yêu cầu cung cấp lý do hủy & STK nhận hoàn tiền
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        appointment = Appointment.objects.filter(id=pk, user=request.user).first()
        if not appointment:
            return Response({'error': 'Không tìm thấy lịch hẹn.'}, status=status.HTTP_404_NOT_FOUND)

        if appointment.status in ['Completed', 'Cancelled']:
            return Response({'error': f'Lịch hẹn đã ở trạng thái {appointment.status}, không thể hủy.'}, status=status.HTTP_400_BAD_REQUEST)

        cancel_reason = request.data.get('cancel_reason', '').strip()
        refund_account_number = request.data.get('refund_account_number', '').strip()

        if not cancel_reason:
            return Response({'error': 'Vui lòng cung cấp lý do hủy lịch hẹn.'}, status=status.HTTP_400_BAD_REQUEST)

        if not refund_account_number:
            return Response({'error': 'Vui lòng cung cấp số tài khoản ngân hàng để bộ phận kế toán hoàn tiền cọc.'}, status=status.HTTP_400_BAD_REQUEST)

        # Cập nhật trạng thái
        appointment.status = 'Cancelled'
        appointment.cancel_reason = cancel_reason
        appointment.refund_account_number = refund_account_number
        appointment.save()

        Notification.objects.create(
            user=request.user,
            title="Đã hủy lịch hẹn",
            content=f"Lịch hẹn {appointment.appointment_code} đã được hủy. Kế toán sẽ đối soát và hoàn tiền cọc về STK {refund_account_number} theo quy định.",
            notification_type="Lịch hẹn"
        )

        return Response({
            'success': True,
            'message': 'Hủy lịch hẹn thành công. Bộ phận kế toán Spa sẽ đối soát số tài khoản và tiến hành hoàn tiền cho quý khách theo quy định.'
        }, status=status.HTTP_200_OK)


class AdminAppointmentListAPI(APIView):
    """
    API Quản lý lịch hẹn toàn Spa cho Lễ tân & Quản lý (UC-1.5)
    Hỗ trợ tìm kiếm theo Tên, SĐT, Mã lịch, lọc Ngày, Trạng thái, và đổi trạng thái
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        qs = Appointment.objects.all().order_by('-appointment_date', '-time_slot')

        # Bộ lọc ngày
        date_filter = request.query_params.get('date')
        if date_filter:
            qs = qs.filter(appointment_date=date_filter)

        # Bộ lọc trạng thái
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        # Tìm kiếm từ khóa
        q = request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(appointment_code__icontains=q) |
                Q(customer_name__icontains=q) |
                Q(customer_phone__icontains=q)
            )

        serializer = AppointmentFullSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk=None):
        """Đổi trạng thái vận hành lịch hẹn (Confirmed -> In_Progress -> Completed -> Cancelled)"""
        target_id = pk or request.data.get('id')
        appointment = Appointment.objects.filter(id=target_id).first()
        if not appointment:
            return Response({'error': 'Không tìm thấy lịch hẹn.'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        valid_statuses = ['Hold', 'Pending', 'Confirmed', 'In_Progress', 'Completed', 'Cancelled']
        if new_status not in valid_statuses:
            return Response({'error': f'Trạng thái không hợp lệ. Chỉ chấp nhận: {", ".join(valid_statuses)}'}, status=status.HTTP_400_BAD_REQUEST)

        appointment.status = new_status
        appointment.save()

        return Response({
            'success': True,
            'message': f"Đã chuyển trạng thái lịch hẹn {appointment.appointment_code} thành '{new_status}'.",
            'appointment': AppointmentFullSerializer(appointment).data
        }, status=status.HTTP_200_OK)
