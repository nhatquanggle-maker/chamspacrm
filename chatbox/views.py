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

from core.models import FAQ, Conversation, ConversationMessage, User, Service, Voucher


def is_staff_or_superuser(user):
    """Kiểm tra quyền truy cập vào Workspace Nhân viên / Quản lý"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


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

    # Lấy danh sách hội thoại
    conversations = (
        Conversation.objects.select_related('customer', 'staff')
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
def faq_management_view(request):
    """
    [UC-2.3] Màn hình Quản lý kịch bản Chatbot (FAQ).
    NGHIÊM CẤM NHÂN VIÊN: CHỈ DUY NHẤT QUẢN LÝ (Admin / is_superuser=True) MỚI ĐƯỢC PHÉP TRUY CẬP.
    Nếu là Staff thường -> Chặn ngay và điều hướng về trang Livechat.
    """
    if not request.user.is_superuser:
        messages.error(request, "Quyền truy cập bị từ chối: Chỉ Quản lý (Admin) mới có quyền quản lý kịch bản Chatbot FAQ. Nhân viên chỉ phụ trách tư vấn trực tiếp với khách hàng.")
        return redirect('chatbox:inbox')

    faqs = FAQ.objects.all().order_by('-created_at')
    categories = FAQ.objects.values_list('category', flat=True).distinct()

    active_count = faqs.filter(status='Active').count()
    hidden_count = faqs.filter(status='Hidden').count()

    context = {
        'page_title': 'Quản lý kịch bản Chatbot (FAQ) | Dành riêng cho Quản lý',
        'faqs': faqs,
        'categories': list(categories),
        'active_count': active_count,
        'hidden_count': hidden_count,
        'total_faqs': faqs.count(),
    }

    return render(request, 'chatbox/faq_management.html', context)


def customer_chat_view(request):
    """
    [UC-2.1 & UC-2.2] Giao diện trang Chatbot & Trò chuyện trực tuyến dành cho Khách hàng.
    """
    quick_faqs = FAQ.objects.filter(status='Active')[:4]
    context = {
        'page_title': 'Trò chuyện tư vấn cùng Cham Spa & Massage',
        'quick_faqs': quick_faqs,
    }
    return render(request, 'chatbox/customer_chat.html', context)
