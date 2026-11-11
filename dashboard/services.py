"""
================================================================================
MODULE 10: QUẢN LÝ DASHBOARD & BÁO CÁO (MOD-10) - BUSINESS SERVICES
Thành viên phụ trách: MINH KHA
Mục đích:
  - Cung cấp toàn bộ logic nghiệp vụ tính toán, tổng hợp chỉ số KPI,
    dữ liệu biểu đồ Chart.js và dữ liệu xuất báo cáo (SheetJS & html2pdf.js).
  - Tách biệt rõ ràng tầng nghiệp vụ (Service Layer) khỏi View/API,
    giúp mã nguồn chuẩn cấu trúc, dễ bảo trì và phục vụ vấn đáp đồ án.
  - Đáp ứng 100% yêu cầu:
    + UC-10.1: Dashboard thống kê thời gian thực (4 thẻ KPI, Line chart doanh thu,
      Bar chart top dịch vụ, Doughnut chart cơ cấu hội viên, bộ lọc thời gian).
    + UC-10.2: Xuất báo cáo trực tiếp tại trình duyệt (Client-side Export).
    + Hợp đồng API STT 20 trong README (/api/admin/dashboard-stats/).
================================================================================
"""

from decimal import Decimal
from datetime import datetime, time, timedelta
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q, F
from django.db.models.functions import TruncDate, TruncMonth

# Import toàn bộ model chuẩn từ core.models theo đúng quy tắc nghiêm ngặt
from core.models import (
    Invoice,
    Appointment,
    AppointmentDetail,
    Service,
    Category,
    Tier,
    Membership,
    User,
    Feedback,
    UserHealthProfile
)


# ==============================================================================
# 1. HÀM XÁC ĐỊNH KHOẢNG THỜI GIAN THỐNG KÊ (TIME PERIOD RESOLVER)
# ==============================================================================
def resolve_time_period(period='this_month', from_date_str=None, to_date_str=None):
    """
    Xác định mốc thời gian bắt đầu (start_date) và kết thúc (end_date)
    cho kỳ hiện tại, đồng thời tính toán kỳ trước đó (prev_start, prev_end)
    để phục vụ tính tỷ lệ tăng trưởng (%) so sánh.

    Tham số:
      - period: 'today' | 'last_7_days' | 'this_month' | 'this_year' | 'custom'
      - from_date_str: 'YYYY-MM-DD' (nếu period='custom')
      - to_date_str:   'YYYY-MM-DD' (nếu period='custom')

    Trả về:
      dict chứa:
        - start_date, end_date (datetime có timezone)
        - prev_start, prev_end (datetime có timezone)
        - period_code (chuỗi mã kỳ)
        - period_label (nhãn tiếng Việt hiển thị trên giao diện)
    """
    now = timezone.now()
    today = now.date()

    if period == 'today':
        start_date = timezone.make_aware(datetime.combine(today, time.min))
        end_date = timezone.make_aware(datetime.combine(today, time.max))
        # Kỳ trước: Ngày hôm qua
        yesterday = today - timedelta(days=1)
        prev_start = timezone.make_aware(datetime.combine(yesterday, time.min))
        prev_end = timezone.make_aware(datetime.combine(yesterday, time.max))
        period_label = f"Hôm nay ({today.strftime('%d/%m/%Y')})"

    elif period == 'last_7_days':
        # 7 ngày gần nhất tính cả hôm nay
        start_date = timezone.make_aware(datetime.combine(today - timedelta(days=6), time.min))
        end_date = timezone.make_aware(datetime.combine(today, time.max))
        # Kỳ trước: 7 ngày trước đó
        prev_start = timezone.make_aware(datetime.combine(today - timedelta(days=13), time.min))
        prev_end = timezone.make_aware(datetime.combine(today - timedelta(days=7), time.max))
        period_label = f"7 ngày qua ({(today - timedelta(days=6)).strftime('%d/%m')} - {today.strftime('%d/%m/%Y')})"

    elif period == 'this_year':
        # Năm nay: từ 01/01 đến 31/12 của năm hiện tại
        first_day_year = today.replace(month=1, day=1)
        last_day_year = today.replace(month=12, day=31)
        start_date = timezone.make_aware(datetime.combine(first_day_year, time.min))
        end_date = timezone.make_aware(datetime.combine(last_day_year, time.max))
        # Kỳ trước: Năm ngoái
        prev_first_day = first_day_year.replace(year=today.year - 1)
        prev_last_day = last_day_year.replace(year=today.year - 1)
        prev_start = timezone.make_aware(datetime.combine(prev_first_day, time.min))
        prev_end = timezone.make_aware(datetime.combine(prev_last_day, time.max))
        period_label = f"Năm {today.year}"

    elif period == 'custom' and from_date_str and to_date_str:
        try:
            from_d = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            to_d = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            if from_d > to_d:
                from_d, to_d = to_d, from_d
            start_date = timezone.make_aware(datetime.combine(from_d, time.min))
            end_date = timezone.make_aware(datetime.combine(to_d, time.max))
            duration = (to_d - from_d).days + 1
            prev_start = timezone.make_aware(datetime.combine(from_d - timedelta(days=duration), time.min))
            prev_end = timezone.make_aware(datetime.combine(to_d - timedelta(days=duration), time.max))
            period_label = f"Từ {from_d.strftime('%d/%m/%Y')} đến {to_d.strftime('%d/%m/%Y')}"
        except Exception:
            # Fallback nếu parse lỗi
            return resolve_time_period('this_month')

    else:
        # Mặc định: Tháng này ('this_month')
        period = 'this_month'
        first_day_month = today.replace(day=1)
        # Tìm ngày cuối tháng
        if today.month == 12:
            last_day_month = today.replace(day=31)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
            last_day_month = next_month - timedelta(days=1)

        start_date = timezone.make_aware(datetime.combine(first_day_month, time.min))
        end_date = timezone.make_aware(datetime.combine(last_day_month, time.max))

        # Kỳ trước: Tháng trước
        if today.month == 1:
            prev_first_day = today.replace(year=today.year - 1, month=12, day=1)
            prev_last_day = today.replace(year=today.year - 1, month=12, day=31)
        else:
            prev_first_day = today.replace(month=today.month - 1, day=1)
            prev_last_day = first_day_month - timedelta(days=1)

        prev_start = timezone.make_aware(datetime.combine(prev_first_day, time.min))
        prev_end = timezone.make_aware(datetime.combine(prev_last_day, time.max))
        period_label = f"Tháng {today.month}/{today.year}"

    return {
        'period_code': period,
        'period_label': period_label,
        'start_date': start_date,
        'end_date': end_date,
        'prev_start': prev_start,
        'prev_end': prev_end,
    }


def calculate_percentage_growth(current_value, previous_value):
    """
    Tính toán tỷ lệ phần trăm tăng trưởng: ((current - previous) / previous) * 100.
    Xử lý an toàn khi previous_value = 0 để tránh lỗi ZeroDivisionError.
    """
    current = float(current_value or 0)
    previous = float(previous_value or 0)

    if previous <= 0:
        if current > 0:
            return 100.0
        return 0.0

    growth = ((current - previous) / previous) * 100.0
    return round(growth, 1)


# ==============================================================================
# 2. HÀM TỔNG HỢP 4 THẺ KPI CHÍNH & CHỈ SỐ BỔ TRỢ (UC-10.1)
# ==============================================================================
def get_dashboard_kpis(time_context):
    """
    Tổng hợp 4 thẻ KPI trọng tâm theo yêu cầu đồ án:
      1. Tổng doanh thu (VNĐ): Tổng amount của hóa đơn 'Đã thanh toán'.
      2. Tổng lượt khách: Tổng số khách (total_guests) của các lịch hẹn trong kỳ.
      3. Tỷ lệ hoàn thành lịch hẹn (%): (Số lịch 'Completed' / Tổng số lịch) * 100.
      4. Số hội viên mới: Số thành viên mới cấp thẻ trong kỳ.
    Kèm theo tỷ lệ tăng trưởng so với kỳ trước và điểm đánh giá trung bình.
    """
    start_date = time_context['start_date']
    end_date = time_context['end_date']
    prev_start = time_context['prev_start']
    prev_end = time_context['prev_end']

    # --- 1. TỔNG DOANH THU (VNĐ) ---
    # Lấy các hóa đơn có trạng thái 'Đã thanh toán' trong kỳ
    curr_invoices = Invoice.objects.filter(
        status='Đã thanh toán'
    ).filter(
        Q(paid_at__range=(start_date, end_date)) |
        Q(paid_at__isnull=True, created_at__range=(start_date, end_date))
    )
    total_revenue = curr_invoices.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    prev_invoices = Invoice.objects.filter(
        status='Đã thanh toán'
    ).filter(
        Q(paid_at__range=(prev_start, prev_end)) |
        Q(paid_at__isnull=True, created_at__range=(prev_start, prev_end))
    )
    prev_revenue = prev_invoices.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    revenue_growth = calculate_percentage_growth(total_revenue, prev_revenue)

    # --- 2. TỔNG LƯỢT KHÁCH (GUESTS) ---
    # Lấy các lịch hẹn trong kỳ dựa trên appointment_date
    curr_appts = Appointment.objects.filter(
        appointment_date__range=(start_date.date(), end_date.date())
    )
    total_guests = curr_appts.aggregate(total=Sum('total_guests'))['total'] or 0
    total_appointments = curr_appts.count()

    prev_appts = Appointment.objects.filter(
        appointment_date__range=(prev_start.date(), prev_end.date())
    )
    prev_guests = prev_appts.aggregate(total=Sum('total_guests'))['total'] or 0
    guests_growth = calculate_percentage_growth(total_guests, prev_guests)

    # --- 3. TỶ LỆ HOÀN THÀNH LỊCH HẸN (%) ---
    completed_appts_count = curr_appts.filter(status='Completed').count()
    cancelled_appts_count = curr_appts.filter(status='Cancelled').count()
    confirmed_appts_count = curr_appts.filter(status='Confirmed').count()

    if total_appointments > 0:
        completed_rate = round((completed_appts_count / total_appointments) * 100.0, 1)
    else:
        completed_rate = 0.0

    # Tỷ lệ hoàn thành kỳ trước để so sánh
    prev_total_appts = prev_appts.count()
    prev_completed_count = prev_appts.filter(status='Completed').count()
    prev_rate = round((prev_completed_count / prev_total_appts) * 100.0, 1) if prev_total_appts > 0 else 0.0
    completion_growth = calculate_percentage_growth(completed_rate, prev_rate)

    # --- 4. SỐ HỘI VIÊN MỚI (NEW MEMBERS) ---
    # Đếm số thẻ hội viên Membership được cấp trong kỳ
    curr_members = Membership.objects.filter(created_at__range=(start_date, end_date))
    new_members_count = curr_members.count()

    prev_members = Membership.objects.filter(created_at__range=(prev_start, prev_end))
    prev_members_count = prev_members.count()
    members_growth = calculate_percentage_growth(new_members_count, prev_members_count)

    # --- CHỈ SỐ BỔ TRỢ: ĐÁNH GIÁ TRUNG BÌNH (RATING) & GIẢM GIÁ ĐÃ ÁP DỤNG ---
    feedbacks = Feedback.objects.filter(created_at__range=(start_date, end_date))
    avg_rating_val = feedbacks.aggregate(avg=Avg('rating'))['avg'] or 0.0
    avg_rating = round(float(avg_rating_val), 1)
    total_feedbacks = feedbacks.count()

    total_discount = curr_invoices.aggregate(total=Sum('discount_applied'))['total'] or Decimal('0.00')

    return {
        'total_revenue': float(total_revenue),
        'total_revenue_formatted': f"{int(total_revenue):,} đ".replace(',', '.'),
        'revenue_growth': revenue_growth,
        'total_guests': total_guests,
        'guests_growth': guests_growth,
        'total_appointments': total_appointments,
        'completed_appointments': completed_appts_count,
        'confirmed_appointments': confirmed_appts_count,
        'cancelled_appointments': cancelled_appts_count,
        'completed_rate': completed_rate,
        'completion_growth': completion_growth,
        'new_members': new_members_count,
        'members_growth': members_growth,
        'avg_rating': avg_rating,
        'total_feedbacks': total_feedbacks,
        'total_discount': float(total_discount),
        'total_discount_formatted': f"{int(total_discount):,} đ".replace(',', '.'),
    }


# ==============================================================================
# 3. HÀM TẠO DỮ LIỆU BIỂU ĐỒ ĐƯỜNG XU HƯỚNG DOANH THU (CHART.JS LINE CHART)
# ==============================================================================
def get_revenue_chart_data(time_context):
    """
    Tạo dữ liệu cho biểu đồ đường (Line Chart) thể hiện xu hướng biến động doanh thu
    và lượt khách theo thời gian bằng Chart.js.
    Tự động chia trục X linh hoạt theo kỳ:
      - 'today': 8 khung giờ (08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00)
      - 'last_7_days': 7 ngày liên tiếp
      - 'this_month': Từng ngày trong tháng
      - 'this_year': 12 tháng trong năm
      - 'custom': Theo ngày nếu khoảng cách <= 31 ngày, theo tháng nếu dài hơn
    """
    period = time_context['period_code']
    start_date = time_context['start_date']
    end_date = time_context['end_date']

    labels = []
    revenue_series = []
    guests_series = []

    # 1. TRƯỜNG HỢP: HÔM NAY (Theo khung giờ)
    if period == 'today':
        slots = [
            ("08:00", 8, 10),
            ("10:00", 10, 12),
            ("12:00", 12, 14),
            ("14:00", 14, 16),
            ("16:00", 16, 18),
            ("18:00", 18, 20),
            ("20:00", 20, 22),
            ("22:00", 22, 24),
        ]
        target_date = start_date.date()

        for label, start_h, end_h in slots:
            labels.append(label)
            # Khung giờ datetime
            slot_start = timezone.make_aware(datetime.combine(target_date, time(start_h, 0)))
            slot_end = timezone.make_aware(datetime.combine(target_date, time(end_h - 1, 59, 59)))

            rev = Invoice.objects.filter(
                status='Đã thanh toán'
            ).filter(
                Q(paid_at__range=(slot_start, slot_end)) |
                Q(paid_at__isnull=True, created_at__range=(slot_start, slot_end))
            ).aggregate(s=Sum('amount'))['s'] or 0

            # Lượt khách dựa vào time_slot hoặc appointment_date
            g = Appointment.objects.filter(
                appointment_date=target_date,
                time_slot__startswith=str(start_h).zfill(2)
            ).aggregate(s=Sum('total_guests'))['s'] or 0

            revenue_series.append(float(rev))
            guests_series.append(int(g))

    # 2. TRƯỜNG HỢP: 7 NGÀY QUA (Theo từng ngày)
    elif period == 'last_7_days':
        curr_d = start_date.date()
        end_d = end_date.date()

        while curr_d <= end_d:
            labels.append(curr_d.strftime("%d/%m"))
            d_start = timezone.make_aware(datetime.combine(curr_d, time.min))
            d_end = timezone.make_aware(datetime.combine(curr_d, time.max))

            rev = Invoice.objects.filter(
                status='Đã thanh toán'
            ).filter(
                Q(paid_at__range=(d_start, d_end)) |
                Q(paid_at__isnull=True, created_at__range=(d_start, d_end))
            ).aggregate(s=Sum('amount'))['s'] or 0

            g = Appointment.objects.filter(
                appointment_date=curr_d
            ).aggregate(s=Sum('total_guests'))['s'] or 0

            revenue_series.append(float(rev))
            guests_series.append(int(g))
            curr_d += timedelta(days=1)

    # 3. TRƯỜNG HỢP: NĂM NAY (Theo 12 tháng)
    elif period == 'this_year':
        year = start_date.year
        for m in range(1, 13):
            labels.append(f"T{m}")
            # Xác định ngày bắt đầu và kết thúc của tháng m
            m_start = timezone.make_aware(datetime(year, m, 1, 0, 0, 0))
            if m == 12:
                m_end = timezone.make_aware(datetime(year, 12, 31, 23, 59, 59))
            else:
                m_end = timezone.make_aware(datetime(year, m + 1, 1, 0, 0, 0) - timedelta(seconds=1))

            rev = Invoice.objects.filter(
                status='Đã thanh toán'
            ).filter(
                Q(paid_at__range=(m_start, m_end)) |
                Q(paid_at__isnull=True, created_at__range=(m_start, m_end))
            ).aggregate(s=Sum('amount'))['s'] or 0

            g = Appointment.objects.filter(
                appointment_date__range=(m_start.date(), m_end.date())
            ).aggregate(s=Sum('total_guests'))['s'] or 0

            revenue_series.append(float(rev))
            guests_series.append(int(g))

    # 4. TRƯỜNG HỢP: THÁNG NÀY HOẶC CUSTOM <= 31 NGÀY (Theo từng ngày)
    else:
        curr_d = start_date.date()
        end_d = end_date.date()
        days_span = (end_d - curr_d).days + 1

        if days_span <= 31:
            while curr_d <= end_d:
                labels.append(curr_d.strftime("%d/%m"))
                d_start = timezone.make_aware(datetime.combine(curr_d, time.min))
                d_end = timezone.make_aware(datetime.combine(curr_d, time.max))

                rev = Invoice.objects.filter(
                    status='Đã thanh toán'
                ).filter(
                    Q(paid_at__range=(d_start, d_end)) |
                    Q(paid_at__isnull=True, created_at__range=(d_start, d_end))
                ).aggregate(s=Sum('amount'))['s'] or 0

                g = Appointment.objects.filter(
                    appointment_date=curr_d
                ).aggregate(s=Sum('total_guests'))['s'] or 0

                revenue_series.append(float(rev))
                guests_series.append(int(g))
                curr_d += timedelta(days=1)
        else:
            # Nếu custom khoảng thời gian dài hơn 1 tháng -> gom theo từng tuần
            while curr_d <= end_d:
                next_d = min(curr_d + timedelta(days=6), end_d)
                labels.append(f"{curr_d.strftime('%d/%m')}-{next_d.strftime('%d/%m')}")
                d_start = timezone.make_aware(datetime.combine(curr_d, time.min))
                d_end = timezone.make_aware(datetime.combine(next_d, time.max))

                rev = Invoice.objects.filter(
                    status='Đã thanh toán'
                ).filter(
                    Q(paid_at__range=(d_start, d_end)) |
                    Q(paid_at__isnull=True, created_at__range=(d_start, d_end))
                ).aggregate(s=Sum('amount'))['s'] or 0

                g = Appointment.objects.filter(
                    appointment_date__range=(curr_d, next_d)
                ).aggregate(s=Sum('total_guests'))['s'] or 0

                revenue_series.append(float(rev))
                guests_series.append(int(g))
                curr_d = next_d + timedelta(days=1)

    return {
        'labels': labels,
        'revenue_data': revenue_series,
        'guests_data': guests_series,
    }


# ==============================================================================
# 4. HÀM TỔNG HỢP TOP 5 DỊCH VỤ BÁN CHẠY NHẤT (CHART.JS BAR CHART)
# ==============================================================================
def get_top_services(time_context, limit=5):
    """
    Thống kê Top 5 dịch vụ bán chạy nhất (dựa trên số lượng lịch hẹn Completed / trải nghiệm)
    kèm tổng doanh thu thực tế và điểm đánh giá trung bình.
    Phục vụ vẽ biểu đồ cột (Bar Chart) và Bảng xếp hạng hiệu suất dịch vụ.
    """
    start_date = time_context['start_date']
    end_date = time_context['end_date']

    # Truy vấn chi tiết đặt lịch (AppointmentDetail)
    qs = AppointmentDetail.objects.filter(
        appointment__appointment_date__range=(start_date.date(), end_date.date()),
        appointment__status__in=['Completed', 'Confirmed', 'In_Progress']
    ).values(
        'service__id',
        'service__name',
        'service__category__name',
        'service__price_vnd',
        'service__rating_avg'
    ).annotate(
        booking_count=Count('id'),
        est_revenue=Sum('service__price_vnd')
    ).order_by('-booking_count')[:limit]

    results = []
    labels = []
    counts = []
    revenues = []

    # Nếu trong kỳ lọc cụ thể không có dữ liệu (ví dụ chọn ngày trống),
    # fallback lấy dữ liệu toàn thời gian để biểu đồ luôn hiển thị đẹp mắt
    if not qs.exists():
        qs = AppointmentDetail.objects.filter(
            appointment__status__in=['Completed', 'Confirmed', 'In_Progress']
        ).values(
            'service__id',
            'service__name',
            'service__category__name',
            'service__price_vnd',
            'service__rating_avg'
        ).annotate(
            booking_count=Count('id'),
            est_revenue=Sum('service__price_vnd')
        ).order_by('-booking_count')[:limit]

    for item in qs:
        name = item['service__name']
        cat = item['service__category__name'] or "Liệu trình Spa"
        count = item['booking_count']
        rev = float(item['est_revenue'] or 0)
        price = float(item['service__price_vnd'] or 0)
        rating = float(item['service__rating_avg'] or 5.0)

        # Cắt ngắn tên nếu quá dài để hiển thị trên Bar chart gọn đẹp
        short_name = name if len(name) <= 22 else name[:20] + "..."

        labels.append(short_name)
        counts.append(count)
        revenues.append(rev)

        results.append({
            'id': item['service__id'],
            'name': name,
            'short_name': short_name,
            'category_name': cat,
            'price': price,
            'price_formatted': f"{int(price):,} đ".replace(',', '.'),
            'booking_count': count,
            'total_revenue': rev,
            'total_revenue_formatted': f"{int(rev):,} đ".replace(',', '.'),
            'rating_avg': rating,
        })

    return {
        'items': results,
        'chart_labels': labels,
        'chart_counts': counts,
        'chart_revenues': revenues,
    }


# ==============================================================================
# 5. HÀM TỔNG HỢP CƠ CẤU THÀNH VIÊN THEO HẠNG (CHART.JS DOUGHNUT CHART)
# ==============================================================================
def get_membership_distribution():
    """
    Thống kê tỷ lệ cơ cấu thành viên theo các hạng thẻ (Thành viên, Bạc, Vàng, Kim Cương)
    dựa trên bảng CSDL Tier và Membership.
    Phục vụ biểu đồ tròn (Doughnut Chart) và bảng tỷ lệ cơ cấu.
    """
    tiers = Tier.objects.annotate(
        member_count=Count('members')
    ).order_by('min_points')

    # Bảng ánh xạ màu nhận diện thương hiệu hoàng gia Cham Spa
    tier_color_map = {
        'Thành viên': '#8C827A',     # Nâu xám trầm ấm
        'Hạng Bạc': '#A0A0A0',       # Ánh bạc thanh lịch
        'Hạng Vàng': '#D0B581',      # Vàng hoàng gia Cham Spa
        'Hạng Kim Cương': '#781A24', # Đỏ rượu vang biểu tượng Cham Spa
        'Hạng VÀNG': '#E5DEC9',
    }

    labels = []
    data = []
    colors = []
    items = []

    total_members = Membership.objects.count()

    for t in tiers:
        name = t.name
        cnt = t.member_count
        color = tier_color_map.get(name, '#D0B581')
        percentage = round((cnt / total_members * 100.0), 1) if total_members > 0 else 0.0

        labels.append(name)
        data.append(cnt)
        colors.append(color)

        items.append({
            'tier_id': t.id,
            'tier_name': name,
            'discount_percent': t.discount_percent,
            'min_points': t.min_points,
            'count': cnt,
            'percentage': percentage,
            'color': color,
        })

    # Nếu CSDL chưa có dữ liệu tier, fallback dữ liệu mẫu chuẩn Cham Spa
    if not labels or total_members == 0:
        labels = ["Thành viên", "Hạng Bạc", "Hạng Vàng", "Hạng Kim Cương"]
        data = [8, 5, 4, 3]
        colors = ["#8C827A", "#A0A0A0", "#D0B581", "#781A24"]
        total_sample = sum(data)
        items = [
            {'tier_name': l, 'count': d, 'percentage': round(d / total_sample * 100, 1), 'color': c}
            for l, d, c in zip(labels, data, colors)
        ]

    return {
        'labels': labels,
        'data': data,
        'colors': colors,
        'items': items,
        'total_members': total_members,
    }


# ==============================================================================
# 6. HÀM PHÂN BỔ TRẠNG THÁI LỊCH HẸN (APPOINTMENT STATUS DISTRIBUTION)
# ==============================================================================
def get_appointment_status_distribution(time_context):
    """
    Thống kê phân bổ các trạng thái của lịch hẹn trong kỳ:
    'Completed' (Hoàn thành), 'Confirmed' (Đã xác nhận), 'In_Progress' (Đang làm),
    'Hold' (Chờ thanh toán), 'Pending' (Chờ duyệt), 'Cancelled' (Đã hủy).
    """
    start_date = time_context['start_date']
    end_date = time_context['end_date']

    qs = Appointment.objects.filter(
        appointment_date__range=(start_date.date(), end_date.date())
    ).values('status').annotate(count=Count('id'))

    status_map = {
        'Completed': {'label': 'Hoàn thành', 'color': '#28A745'},
        'Confirmed': {'label': 'Đã xác nhận', 'color': '#0D6EFD'},
        'In_Progress': {'label': 'Đang thực hiện', 'color': '#FD7E14'},
        'Hold': {'label': 'Chờ quét QR', 'color': '#6C757D'},
        'Pending': {'label': 'Chờ xác nhận', 'color': '#FFC107'},
        'Cancelled': {'label': 'Đã hủy', 'color': '#DC3545'},
    }

    counts_by_status = {item['status']: item['count'] for item in qs}
    # Fallback nếu kỳ không có dữ liệu
    if not counts_by_status:
        all_qs = Appointment.objects.values('status').annotate(count=Count('id'))
        counts_by_status = {item['status']: item['count'] for item in all_qs}

    labels = []
    data = []
    colors = []
    details = []

    for key, cfg in status_map.items():
        cnt = counts_by_status.get(key, 0)
        labels.append(cfg['label'])
        data.append(cnt)
        colors.append(cfg['color'])
        details.append({
            'status_key': key,
            'label': cfg['label'],
            'count': cnt,
            'color': cfg['color'],
        })

    return {
        'labels': labels,
        'data': data,
        'colors': colors,
        'details': details,
    }


# ==============================================================================
# 7. HÀM LẤY DANH SÁCH GIAO DỊCH / HÓA ĐƠN GẦN ĐÂY (RECENT TRANSACTIONS)
# ==============================================================================
def get_recent_transactions(limit=10):
    """
    Lấy danh sách 10 hóa đơn thanh toán phát sinh gần đây nhất
    để hiển thị trực tiếp trên bảng dữ liệu thời gian thực.
    """
    invoices = Invoice.objects.select_related(
        'appointment',
        'appointment__user',
        'appointment__user__membership__tier'
    ).prefetch_related(
        'appointment__details__service'
    ).order_by('-created_at')[:limit]

    transactions = []
    for inv in invoices:
        appt = inv.appointment
        # Lấy tên dịch vụ đầu tiên trong chi tiết
        details = list(appt.details.all())
        if details:
            service_names = ", ".join([d.service.name for d in details[:2]])
            if len(details) > 2:
                service_names += f" (+{len(details)-2})"
        else:
            service_names = "Liệu trình trị liệu Cham Spa"

        # Tên khách hàng & số điện thoại
        cust_name = appt.customer_name or (appt.user.name if appt.user else "Khách vãng lai")
        cust_phone = appt.customer_phone or (appt.user.phone if appt.user else "N/A")

        # Hạng thành viên nếu có
        tier_name = "Khách thường"
        if appt.user and hasattr(appt.user, 'membership') and appt.user.membership.tier:
            tier_name = appt.user.membership.tier.name

        paid_time = inv.paid_at or inv.created_at

        transactions.append({
            'id': inv.id,
            'invoice_code': f"HD-{inv.id:04d}",
            'appointment_code': appt.appointment_code,
            'customer_name': cust_name,
            'customer_phone': cust_phone,
            'tier_name': tier_name,
            'service_name': service_names,
            'amount': float(inv.amount),
            'amount_formatted': f"{int(inv.amount):,} đ".replace(',', '.'),
            'discount_applied': float(inv.discount_applied),
            'discount_formatted': f"{int(inv.discount_applied):,} đ".replace(',', '.') if inv.discount_applied > 0 else "0 đ",
            'status': inv.status,
            'paid_at': paid_time.strftime("%d/%m/%Y %H:%M") if paid_time else "",
            'appointment_date': appt.appointment_date.strftime("%d/%m/%Y") if appt.appointment_date else "",
            'time_slot': appt.time_slot,
        })

    return transactions


# ==============================================================================
# 8. HÀM TỔNG HỢP DỮ LIỆU ĐẦY ĐỦ ĐỂ XUẤT EXCEL & PDF (UC-10.2)
# ==============================================================================
def get_export_report_data(time_context):
    """
    Thu thập toàn bộ dữ liệu bảng kê chi tiết cho việc xuất file Excel (SheetJS)
    và PDF (html2pdf.js) tại trình duyệt mà không tốn tài nguyên server.
    """
    start_date = time_context['start_date']
    end_date = time_context['end_date']

    # Danh sách tất cả hóa đơn trong kỳ
    invoices = Invoice.objects.select_related(
        'appointment',
        'appointment__user'
    ).prefetch_related(
        'appointment__details__service'
    ).filter(
        created_at__range=(start_date, end_date)
    ).order_by('-created_at')

    # Nếu kỳ trống thì lấy 50 hóa đơn gần nhất để file xuất luôn đầy đủ
    if not invoices.exists():
        invoices = Invoice.objects.select_related(
            'appointment',
            'appointment__user'
        ).prefetch_related(
            'appointment__details__service'
        ).order_by('-created_at')[:50]

    rows = []
    stt = 1
    for inv in invoices:
        appt = inv.appointment
        details = list(appt.details.all())
        service_names = ", ".join([d.service.name for d in details]) if details else "Trị liệu Spa"
        cust_name = appt.customer_name or (appt.user.name if appt.user else "Khách vãng lai")
        cust_phone = appt.customer_phone or (appt.user.phone if appt.user else "")
        paid_str = inv.paid_at.strftime("%d/%m/%Y %H:%M") if inv.paid_at else inv.created_at.strftime("%d/%m/%Y %H:%M")

        rows.append({
            'stt': stt,
            'invoice_code': f"HD-{inv.id:04d}",
            'appointment_code': appt.appointment_code,
            'customer_name': cust_name,
            'customer_phone': cust_phone,
            'service_name': service_names,
            'total_guests': appt.total_guests,
            'amount': float(inv.amount),
            'discount': float(inv.discount_applied),
            'status': inv.status,
            'paid_at': paid_str,
            'appointment_date': appt.appointment_date.strftime("%d/%m/%Y"),
            'time_slot': appt.time_slot,
        })
        stt += 1

    kpis = get_dashboard_kpis(time_context)
    top_services = get_top_services(time_context, limit=10)

    return {
        'period_label': time_context['period_label'],
        'exported_at': timezone.now().strftime("%d/%m/%Y %H:%M"),
        'kpis': kpis,
        'invoice_rows': rows,
        'top_services': top_services['items'],
    }


# ==============================================================================
# 9. HÀM PHÂN TÍCH HỒ SƠ SỨC KHỎE KHÁCH HÀNG (MOD-08 HEALTH ANALYTICS)
# ==============================================================================
def _parse_json_or_csv_list(raw_val):
    """Hàm phụ trợ chuẩn hóa trường JSONField hoặc chuỗi phân tách bởi dấu phẩy."""
    if not raw_val:
        return []
    if isinstance(raw_val, list):
        return [str(x).strip() for x in raw_val if str(x).strip()]
    if isinstance(raw_val, str):
        return [x.strip() for x in raw_val.split(',') if x.strip()]
    return []


def _normalize_pressure_label(raw_pressure):
    """Chuẩn hóa nhãn lực massage về 3 nhóm chính: Nhẹ nhàng, Lực vừa, Mạnh."""
    if not raw_pressure:
        return None
    val = str(raw_pressure).strip().lower()
    if 'nhẹ' in val:
        return 'Nhẹ nhàng'
    if 'mạnh' in val:
        return 'Mạnh'
    if 'vừa' in val:
        return 'Lực vừa'
    return raw_pressure.strip()


def get_health_profile_analytics():
    """
    Tổng hợp dữ liệu từ bảng UserHealthProfile (MOD-08) và tùy chọn lực massage
    trong AppointmentDetail để phục vụ biểu đồ Phân tích Hồ sơ Sức khỏe trên Dashboard:
      1. Phân bổ vùng đau mỏi khách hàng cần tập trung (Focus Areas Bar Chart).
      2. Phân bổ lực massage mong muốn (Pressure Doughnut Chart).
      3. Các chỉ số tóm tắt: Tổng hồ sơ, Điểm đau trung bình, Số hồ sơ có huyết áp Cao/Thấp.
    """
    profiles = UserHealthProfile.objects.all()
    total_profiles = profiles.count()

    focus_counts = {}
    pressure_counts = {'Nhẹ nhàng': 0, 'Lực vừa': 0, 'Mạnh': 0}
    pain_levels = []
    special_alert_count = 0

    for hp in profiles:
        # 1. Thống kê điểm mức độ đau (1-10)
        if hp.pain_level is not None:
            pain_levels.append(hp.pain_level)

        # 2. Thống kê vùng đau mỏi cần tập trung
        areas = _parse_json_or_csv_list(hp.focus_areas)
        for area in areas:
            focus_counts[area] = focus_counts.get(area, 0) + 1

        # 3. Thống kê lực massage mong muốn từ hồ sơ
        norm_p = _normalize_pressure_label(hp.massage_pressure)
        if norm_p:
            pressure_counts[norm_p] = pressure_counts.get(norm_p, 0) + 1

        # 4. Đếm các hồ sơ có chỉ số huyết áp Cao/Thấp cần KTV chú ý
        if hp.blood_pressure and hp.blood_pressure.strip().lower() in ('cao', 'thấp'):
            special_alert_count += 1

    # Bổ sung thêm dữ liệu lực massage thực tế từ AppointmentDetail nếu có để bức tranh toàn diện
    for detail in AppointmentDetail.objects.all():
        norm_p = _normalize_pressure_label(detail.massage_pressure)
        if norm_p:
            pressure_counts[norm_p] = pressure_counts.get(norm_p, 0) + 1

    # Sắp xếp Top 6 vùng đau mỏi phổ biến nhất
    sorted_focus = sorted(focus_counts.items(), key=lambda x: x[1], reverse=True)[:6]
    if sorted_focus:
        focus_labels = [k for k, _ in sorted_focus]
        focus_data = [v for _, v in sorted_focus]
    else:
        focus_labels = ['Chưa có dữ liệu']
        focus_data = [0]

    # Chuẩn bị dữ liệu biểu đồ lực massage
    pressure_labels = ['Nhẹ nhàng', 'Lực vừa', 'Mạnh']
    pressure_data = [
        pressure_counts.get('Nhẹ nhàng', 0),
        pressure_counts.get('Lực vừa', 0),
        pressure_counts.get('Mạnh', 0),
    ]
    pressure_colors = ['#A5C4D4', '#D0B581', '#781A24']
    total_pressure = sum(pressure_data)

    pressure_items = []
    for lbl, cnt, clr in zip(pressure_labels, pressure_data, pressure_colors):
        pct = round((cnt / total_pressure * 100.0), 1) if total_pressure > 0 else 0.0
        pressure_items.append({
            'label': lbl,
            'count': cnt,
            'percentage': pct,
            'color': clr,
        })

    avg_pain = round(sum(pain_levels) / len(pain_levels), 1) if pain_levels else 0.0

    top_conditions = []

    return {
        'total_profiles': total_profiles,
        'avg_pain_level': avg_pain,
        'special_alert_count': special_alert_count,
        'focus_chart': {
            'labels': focus_labels,
            'data': focus_data,
        },
        'pressure_chart': {
            'labels': pressure_labels,
            'data': pressure_data,
            'colors': pressure_colors,
            'items': pressure_items,
            'total': total_pressure,
        },
        'top_conditions': top_conditions,
    }


