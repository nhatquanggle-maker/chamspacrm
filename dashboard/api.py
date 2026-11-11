from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.ajax import require_staff_json
from .services import (
    resolve_time_period,
    get_dashboard_kpis,
    get_revenue_chart_data,
    get_top_services,
    get_membership_distribution,
    get_appointment_status_distribution,
    get_health_profile_analytics,
    get_recent_transactions,
    get_export_report_data,
)


@require_GET
@require_staff_json
def stats_api(request):
    """API thống kê Dashboard thời gian thực (GET /dashboard/api/stats/)."""
    period = request.GET.get('period', 'this_month')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    time_context = resolve_time_period(
        period=period,
        from_date_str=from_date,
        to_date_str=to_date,
    )

    kpi_data = get_dashboard_kpis(time_context)
    revenue_chart = get_revenue_chart_data(time_context)
    top_services_data = get_top_services(time_context, limit=5)
    membership_chart = get_membership_distribution()
    status_chart = get_appointment_status_distribution(time_context)
    health_analytics = get_health_profile_analytics()
    recent_txs = get_recent_transactions(limit=10)

    payload = {
        'status': 'success',
        'period': time_context['period_code'],
        'period_label': time_context['period_label'],
        'kpi': kpi_data,
        'revenue_chart': revenue_chart,
        'top_services': top_services_data['items'],
        'membership_chart': membership_chart,
        'appointment_status_chart': status_chart,
        'health_analytics': health_analytics,
        'recent_transactions': recent_txs,
        'total_revenue': float(kpi_data.get('total_revenue', 0) or 0),
        'total_appointments': int(kpi_data.get('total_appointments', 0) or 0),
        'completed_rate': float(kpi_data.get('completed_rate', 0) or 0),
        'new_members': int(kpi_data.get('new_members', 0) or 0),
    }
    return JsonResponse(payload)


@require_GET
@require_staff_json
def export_data_api(request):
    """API cung cấp dữ liệu xuất báo cáo (GET /dashboard/api/export-data/)."""
    period = request.GET.get('period', 'this_month')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    time_context = resolve_time_period(period, from_date, to_date)
    export_data = get_export_report_data(time_context)

    return JsonResponse({
        'status': 'success',
        'data': export_data,
    })
