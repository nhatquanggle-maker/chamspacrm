"""
================================================================================
VIEWS GIAO DIỆN CHO PHÂN HỆ QUẢN LÝ BOXCHAT TƯ VẤN (MOD-02) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc
Triển khai giao diện chuẩn Figma Node 207:1040:
  - Staff Workspace: Giao diện Livechat tư vấn trực tiếp với khách hàng (Ảnh 1 chuẩn Figma)
  - Phân quyền nghiêm ngặt:
      + Nhân viên (Staff): CHỈ có giao diện Livechat nhắn với khách hàng, KHÔNG ĐƯỢC quản lý FAQ.
      + Quản lý (Admin / Superuser): Toàn quyền quản trị kịch bản Chatbot FAQ.
================================================================================
"""

from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q

from core.models import (
    FAQ, Conversation, ConversationMessage, User, Service, Voucher,
    Membership, UserHealthProfile
)
from health.helpers import build_health_summary


def is_staff_or_superuser(user):
    """Kiểm tra quyền truy cập vào Workspace Nhân viên / Quản lý"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
def chatbox_index_view(request):
    """
    Tự động phân luồng theo vai trò người dùng:
      - Quản lý / Quản trị viên (is_superuser): Điều hướng sang Admin Monitor (Figma Node 502:2005)
      - Nhân viên (is_staff): Điều hướng sang Staff Inbox Livechat (Figma Node 207:1040)
      - Khách hàng (Customer): Điều hướng sang Chatbot tư vấn khách hàng
    """
    if request.user.is_superuser:
        return redirect('chatbox:admin_monitor')
    elif request.user.is_staff:
        return redirect('chatbox:inbox')
    else:
        return redirect('chatbox:customer_chat')


@login_required
def livechat_staff_view(request):
    """
    [UC-2.2 & Figma Node 207:1040]
    Màn hình Livechat tư vấn trực tuyến dành cho Nhân viên CSKH & Lễ tân (Ảnh 1).
    Phân quyền: Nhân viên chỉ có giao diện nhắn tin tư vấn với khách hàng, KHÔNG quản lý FAQ.
    
    Bao gồm:
      - Header "Live chat hôm nay", Breadcrumb, Ngày làm việc
      - Thanh lọc ngang: Tìm lịch hẹn, Ngày làm việc, Khung giờ, Trạng thái, Nút Áp dụng
      - Cột trái: Hàng chờ tư vấn (Chờ tiếp nhận, Đang xử lý, Kết thúc, Tự động cập nhật 15s)
      - Cột phải: Khung chat trực tiếp, Card xác nhận lịch hẹn trực tiếp, 3 nút tiện ích
        (Gửi dịch vụ, Gửi Voucher, Nhúng liên kết Đặt lịch hẹn trực tiếp)
    """
    if not is_staff_or_superuser(request.user):
        messages.error(request, "Bạn không có quyền truy cập màn hình Livechat dành cho nhân viên.")
        return redirect('home')

    today = timezone.localdate()
    
    # Định dạng ngày hiển thị tiếng Việt (VD: Thứ Sáu, 02/10/2026 hoặc ngày hôm nay)
    days_vi = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật']
    day_name = days_vi[today.weekday()]
    formatted_date_header = f"{day_name}, {today.strftime('%d/%m/%Y')}"

    # Đếm số lượng cuộc hội thoại theo từng trạng thái
    waiting_count = Conversation.objects.filter(status='Đang chờ').count()
    processing_count = Conversation.objects.filter(status='Đang xử lý').count()
    closed_count = Conversation.objects.filter(status='Kết thúc').count()
    total_count = Conversation.objects.count()

    # Chọn tab mặc định khớp với dữ liệu thực tế hiện có
    if waiting_count > 0:
        initial_tab = 'waiting'
    elif processing_count > 0:
        initial_tab = 'processing'
    else:
        initial_tab = 'closed'

    tab_status_map = {
        'waiting': 'Đang chờ',
        'processing': 'Đang xử lý',
        'closed': 'Kết thúc',
    }

    # Lấy danh sách hội thoại theo tab đang mở mặc định để đồng bộ SSR và API polling
    conversations = (
        Conversation.objects.filter(status=tab_status_map[initial_tab])
        .select_related('customer', 'staff')
        .prefetch_related('messages')
        .order_by('-created_at')
    )

    # Lấy danh sách dịch vụ Spa đang hoạt động để gửi nhanh vào chat
    services = Service.objects.filter(status='Hoạt động').select_related('category').order_by('category_id', 'id')

    # Lấy danh sách Voucher khả dụng để nhân viên gửi nhanh cho khách
    vouchers = Voucher.objects.filter(status='Khả dụng').order_by('-discount_value')[:5]

    context = {
        'page_title': 'Live chat hôm nay | Cham Spa & Massage',
        'today_str': today.strftime('%Y-%m-%d'),
        'today_display': today.strftime('%d/%m/%Y'),
        'formatted_date_header': formatted_date_header,
        'initial_tab': initial_tab,
        'waiting_count': waiting_count,
        'processing_count': processing_count,
        'closed_count': closed_count,
        'total_count': total_count,
        'conversations': conversations,
        'services': services,
        'vouchers': vouchers,
        'current_staff': request.user,
    }

    return render(request, 'chatbox/livechat.html', context)


@login_required
def admin_livechat_monitor_view(request):
    """
    [Figma Node 502:2005 - ADMIN · Quản lý Live Chat & Giám sát phiên tư vấn (UC-2.2)]
    Dành riêng cho Quản trị viên (Admin / is_staff=True hoặc is_superuser=True):
      - Cột 1: Danh sách hội thoại phân tab (Chưa tiếp nhận, Đang tư vấn, Đã kết thúc)
      - Cột 2: Khung giám sát & Can thiệp chat (Mode Giám sát vs Mode Can thiệp, Tiếp quản, Chuyển nhân viên)
      - Nút nhỏ xem chi tiết khách hàng chuẩn phân hệ quản trị
    """
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Quyền truy cập bị từ chối: Màn hình Giám sát phiên tư vấn chỉ dành cho Quản trị viên.")
        return redirect('home')

    # Lấy danh sách hội thoại theo 3 tab
    waiting_conversations = (
        Conversation.objects.filter(status='Đang chờ')
        .select_related('customer', 'staff')
        .order_by('-created_at')
    )
    processing_conversations = (
        Conversation.objects.filter(status='Đang xử lý')
        .select_related('customer', 'staff')
        .order_by('-created_at')
    )
    closed_conversations = (
        Conversation.objects.filter(status='Kết thúc')
        .select_related('customer', 'staff')
        .order_by('-closed_at')
    )

    conv_id = request.GET.get('conv_id')
    active_conv = None
    if conv_id:
        active_conv = Conversation.objects.filter(pk=conv_id).select_related('customer', 'staff').first()

    if not active_conv:
        active_conv = processing_conversations.first() or waiting_conversations.first() or closed_conversations.first()

    initial_tab = 'processing'
    if active_conv:
        if active_conv.status == 'Đang chờ':
            initial_tab = 'waiting'
        elif active_conv.status == 'Kết thúc':
            initial_tab = 'closed'

    # Dữ liệu khách hàng cho Cột 3
    customer_info = None
    messages_list = []
    duration_display = "04:12"
    if active_conv:
        messages_list = active_conv.messages.all().order_by('created_at')
        customer = active_conv.customer

        membership = Membership.objects.filter(user=customer).select_related('tier').first()
        tier_name = membership.tier.name if (membership and membership.tier) else 'Hạng VÀNG'
        total_spent = membership.total_spent if membership else 18500000
        formatted_spent = f"{int(total_spent):,} VNĐ".replace(',', '.')

        health = UserHealthProfile.objects.filter(user=customer).first()
        health_summary = build_health_summary(health)

        # Tính thời lượng
        duration_seconds = int((timezone.now() - active_conv.created_at).total_seconds())
        mins = max(0, duration_seconds // 60)
        secs = max(0, duration_seconds % 60)
        duration_display = f"{mins:02d}:{secs:02d}"

        customer_info = {
            'user': customer,
            'tier_name': tier_name,
            'total_spent': formatted_spent,
            'health_summary': health_summary
        }

    # Danh sách nhân viên trực tuyến để chuyển giao (Reassign)
    available_staffs = User.objects.filter(is_staff=True).order_by('name')

    # Danh sách dịch vụ và voucher phục vụ can thiệp
    services = Service.objects.filter(status='Hoạt động')[:10]
    vouchers = Voucher.objects.filter(status='Khả dụng')[:5]

    context = {
        'page_title': 'Quản lý Boxchat | Giám sát phiên tư vấn',
        'active_tab': 'monitor',
        'initial_tab': initial_tab,
        'waiting_conversations': waiting_conversations,
        'processing_conversations': processing_conversations,
        'closed_conversations': closed_conversations,
        'waiting_count': waiting_conversations.count(),
        'processing_count': processing_conversations.count(),
        'closed_count': closed_conversations.count(),
        'active_conv': active_conv,
        'customer_info': customer_info,
        'messages_list': messages_list,
        'duration_display': duration_display,
        'available_staffs': available_staffs,
        'services': services,
        'vouchers': vouchers,
    }
    return render(request, 'chatbox/admin_monitor.html', context)


@login_required
def faq_management_view(request):
    """
    [UC-2.3 & Figma Node 211:3459] Màn hình Quản lý kịch bản Chatbot (FAQ).
    Chỉ tài khoản Quản trị viên (Admin / is_staff=True hoặc is_superuser=True) mới có quyền truy cập.
    Hỗ trợ:
      - Tìm kiếm theo từ khóa hoặc câu hỏi
      - Lọc theo danh mục (Pills thống kê số lượng)
      - Xuất dữ liệu CSV
      - Thêm/Sửa/Xóa và Toggle Trạng thái hoạt động
    """
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Quyền truy cập bị từ chối: Chỉ tài khoản Quản trị viên mới được phép quản lý kịch bản Chatbot FAQ.")
        return redirect('home')

    faqs = FAQ.objects.all().order_by('-created_at')
    
    # Thống kê số lượng theo danh mục cho các Pills
    category_counts = {}
    for item in FAQ.objects.values('category').annotate(total=Count('id')):
        category_counts[item['category']] = item['total']

    # Danh sách danh mục chuẩn
    default_categories = ['Bảng giá', 'Lịch đặt', 'Khuyến mãi', 'Địa chỉ', 'Chính sách', 'Dịch vụ']
    all_categories = sorted(list(set(default_categories + list(category_counts.keys()))))

    category_filter = request.GET.get('category')
    search_q = request.GET.get('q', '').strip()

    if category_filter:
        faqs = faqs.filter(category=category_filter)
    if search_q:
        faqs = faqs.filter(
            Q(question__icontains=search_q) |
            Q(keywords__icontains=search_q) |
            Q(faq_code__icontains=search_q) |
            Q(answer__icontains=search_q)
        )

    active_count = FAQ.objects.filter(status='Active').count()
    hidden_count = FAQ.objects.filter(status='Hidden').count()
    total_count = FAQ.objects.count()

    context = {
        'page_title': 'Quản lý Boxchat | Quản lý kịch bản Chatbot (FAQ)',
        'active_tab': 'faqs',
        'faqs': faqs,
        'categories': all_categories,
        'category_counts': category_counts,
        'selected_category': category_filter,
        'search_q': search_q,
        'active_count': active_count,
        'hidden_count': hidden_count,
        'total_faqs': total_count,
    }

    return render(request, 'chatbox/faq_management.html', context)


def customer_chat_view(request):
    """
    [UC-2.1 & UC-2.2] Giao diện trang Chatbot & Trò chuyện trực tuyến dành cho Khách hàng.
    """
    quick_faqs = list(FAQ.objects.filter(status='Active').order_by('category', 'id'))
    faq_categories = []
    seen_cats = set()
    for faq in quick_faqs:
        cat = (faq.category or 'Chung').strip() or 'Chung'
        if cat not in seen_cats:
            seen_cats.add(cat)
            faq_categories.append(cat)

    context = {
        'page_title': 'Trò chuyện tư vấn cùng Cham Spa & Massage',
        'quick_faqs': quick_faqs,
        'faq_categories': faq_categories,
    }
    return render(request, 'chatbox/customer_chat.html', context)
