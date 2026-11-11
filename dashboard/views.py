"""
================================================================================
MODULE 10: QUẢN LÝ DASHBOARD & BÁO CÁO (MOD-10) - TEMPLATE VIEWS
Thành viên phụ trách: MINH KHA
Mục đích:
  - Điều phối và kết xuất (render) giao diện Bảng điều khiển Quản trị viên
    và Ca trực Kỹ thuật viên / CSKH Cham Spa.
  - Kế thừa chuẩn Figma Design System:
    + Admin Workspace: layouts/admin_layout.html (Figma 772:2 & 576:1396)
    + Staff Workspace: layouts/staff_layout.html (Figma 760:751)
  - Áp dụng Server-Side Rendering (SSR) cho lần tải đầu tiên giúp giao diện
    mượt mà, lập tức hiển thị đủ 4 thẻ KPI, biểu đồ Chart.js và bảng hóa đơn;
    đồng thời nhúng sẵn API URL để Vanilla JS gọi Fetch API động.
================================================================================
"""

import json
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q

from core.models import Appointment, Invoice, Membership, Feedback, Service, Tier
from .services import (
    resolve_time_period,
    get_dashboard_kpis,
    get_revenue_chart_data,
    get_top_services,
    get_membership_distribution,
    get_appointment_status_distribution,
    get_health_profile_analytics,
    get_recent_transactions,
)


def _require_staff_access(user):
    if not (user.is_staff or user.is_superuser):
        raise PermissionDenied("Bạn không có quyền truy cập bảng điều khiển.")


@login_required
def admin_dashboard(request):
    """
    [UC-10.1, UC-10.2] BẢNG ĐIỀU KHIỂN & BÁO CÁO KINH DOANH DÀNH CHO QUẢN TRỊ VIÊN
    Figma Screen: Node 772:2 & Node 576:1396
    Hiển thị:
      - 4 Thẻ KPI: Doanh thu (VNĐ), Lượt khách, Tỷ lệ hoàn thành %, Hội viên mới.
      - 3 Biểu đồ Chart.js: Line chart doanh thu, Bar chart top dịch vụ, Doughnut chart hội viên.
      - 1 Biểu đồ phân bổ trạng thái lịch hẹn.
      - Bảng dữ liệu hóa đơn giao dịch gần đây & Hiệu suất dịch vụ.
      - Công cụ lọc thời gian (Hôm nay, 7 ngày, Tháng này, Năm nay, Tùy chọn).
      - Nút xuất báo cáo trực tiếp tại trình duyệt (SheetJS Excel & html2pdf.js PDF).
    """
    _require_staff_access(request.user)
    # 1. Hỗ trợ chuyển hướng tiện ích theo query tab nếu có
    tab = request.GET.get('tab')
    if tab == 'customers':
        return redirect('accounts:admin_customer_list')
    if tab == 'staff':
        return redirect('accounts:admin_staff_list')
    if tab == 'chatbox':
        return redirect('chatbox:admin_monitor')
    if tab == 'appointments':
        return redirect('appointment:admin_appointments')
    if tab == 'feedbacks':
        return redirect('feedbacks:admin_management')
    if tab == 'complaints':
        return redirect('/feedbacks/manage/?tab=complaints')
    if tab == 'notifications':
        return redirect('marketing:admin_notifications')
    if tab == 'promotions':
        return redirect('marketing:admin_promotions')

    # 2. Thu thập dữ liệu khởi tạo cho kỳ mặc định: 'this_month' (Server-Side Rendering)
    period = request.GET.get('period', 'this_month')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    time_context = resolve_time_period(period, from_date, to_date)
    kpis = get_dashboard_kpis(time_context)
    revenue_chart = get_revenue_chart_data(time_context)
    top_services_data = get_top_services(time_context, limit=5)
    membership_chart = get_membership_distribution()
    status_chart = get_appointment_status_distribution(time_context)
    health_analytics = get_health_profile_analytics()
    recent_transactions = get_recent_transactions(limit=10)

    context = {
        'page_title': 'Dashboard Quản trị & Báo cáo Doanh thu',
        'active_menu': 'dashboard',
        'current_period': time_context['period_code'],
        'period_label': time_context['period_label'],
        'kpis': kpis,
        'revenue_chart_json': json.dumps(revenue_chart),
        'top_services': top_services_data['items'],
        'top_services_json': json.dumps({
            'labels': top_services_data['chart_labels'],
            'counts': top_services_data['chart_counts'],
            'revenues': top_services_data['chart_revenues'],
        }),
        'membership_chart_json': json.dumps(membership_chart),
        'status_chart_json': json.dumps(status_chart),
        'health_analytics': health_analytics,
        'health_analytics_json': json.dumps(health_analytics),
        'recent_transactions': recent_transactions,
        'today_str': timezone.now().strftime('%Y-%m-%d'),
    }

    return render(request, 'dashboard/admin_dashboard.html', context)


@login_required
def staff_dashboard(request):
    """
    BẢNG ĐIỀU KHIỂN CA TRỰC DÀNH CHO KỸ THUẬT VIÊN & CSKH CHAM SPA
    Figma Screen: Node 760:751
    Hiển thị:
      - Thống kê ca trực hôm nay (Lịch hẹn tiếp nhận, Đang thực hiện, Đã xong).
      - Danh sách lịch hẹn hôm nay cần phục vụ.
      - Phím tắt tra cứu nhanh thể trạng sức khỏe & lực massage của khách.
    """
    _require_staff_access(request.user)
    tab = request.GET.get('tab')
    if tab == 'inbox':
        return redirect('chatbox:inbox')
    if tab == 'customers':
        return redirect('health:staff_lookup')
    if tab == 'feedbacks':
        return redirect('feedbacks:admin_management')
    if tab == 'complaints':
        return redirect('/feedbacks/manage/?tab=complaints')
    if tab == 'appointments':
        return redirect('appointment:staff_appointments')
    if tab == 'notifications':
        return redirect('marketing:staff_notifications')

    # Thống kê ca trực trong ngày hôm nay
    today = timezone.now().date()
    today_appts = Appointment.objects.filter(appointment_date=today).order_by('time_slot')

    total_today = today_appts.count()
    completed_today = today_appts.filter(status='Completed').count()
    in_progress_today = today_appts.filter(status='In_Progress').count()
    confirmed_today = today_appts.filter(status='Confirmed').count()

    # Doanh thu quầy đã thu hôm nay
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    today_end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))

    today_revenue = Invoice.objects.filter(
        status='Đã thanh toán'
    ).filter(
        Q(paid_at__range=(today_start, today_end)) |
        Q(paid_at__isnull=True, created_at__range=(today_start, today_end))
    ).aggregate(s=Sum('amount'))['s'] or 0

    context = {
        'page_title': 'Bảng điều khiển Ca trực Kỹ thuật viên',
        'active_menu': 'dashboard',
        'today_str': today.strftime('%d/%m/%Y'),
        'total_today': total_today,
        'completed_today': completed_today,
        'in_progress_today': in_progress_today,
        'confirmed_today': confirmed_today,
        'today_revenue_formatted': f"{int(today_revenue):,} đ".replace(',', '.'),
        'today_appointments': today_appts[:15],
    }

    return render(request, 'dashboard/staff_dashboard.html', context)
