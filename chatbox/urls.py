"""
================================================================================
URL CONFIGURATION CHO PHÂN HỆ QUẢN LÝ BOXCHAT TƯ VẤN (MOD-02) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc
Định tuyến toàn bộ Giao diện (Views) và RESTful API (DRF) cho Module 2.
Khớp 100% Thiết kế Figma:
  - Giao diện Livechat Console cho Staff: Node 207:1040
  - Giao diện xem chi tiết dịch vụ: Node 210:2465
  - Giao diện cuộc hội thoại đã do nhân viên khác tiếp nhận: Node 210:2465
================================================================================
"""

from django.urls import path
from . import views, api

app_name = 'chatbox'

urlpatterns = [
    # =========================================================================
    # 1. GIAO DIỆN WEB (VIEWS)
    # =========================================================================
    # Trang chủ module chatbox: Tự động phân luồng theo vai trò người dùng
    path('', views.livechat_staff_view, name='index'),
    path('livechat/', views.livechat_staff_view, name='livechat'),
    path('inbox/', views.livechat_staff_view, name='inbox'),
    path('faqs/', views.faq_management_view, name='faq_management'),
    path('customer/', views.customer_chat_view, name='customer_chat'),

    # =========================================================================
    # 2. RESTFUL API THEO HỢP ĐỒNG GIAO TIẾP (SPEC SHEET CHỐT)
    # =========================================================================
    # UC-2.1: Chatbot tự động phản hồi (POST /api/chat/bot-reply/)
    path('api/chat/bot-reply/', api.BotReplyAPI.as_view(), name='api_bot_reply'),
    path('api/bot-reply/', api.BotReplyAPI.as_view(), name='api_bot_reply_alias'),

    # UC-2.2: Yêu cầu chuyển tiếp sang nhân viên tư vấn
    path('api/chat/transfer-staff/', api.ConversationTransferStaffAPI.as_view(), name='api_transfer_staff'),
    path('api/conversations/transfer/', api.ConversationTransferStaffAPI.as_view(), name='api_conversations_transfer'),
    path('api/conversations/my-active/', api.CustomerActiveConversationAPI.as_view(), name='api_customer_active_conversation'),

    # UC-2.2: Lấy tin nhắn và Gửi tin nhắn trực tiếp giữa Khách và Nhân viên (POST & GET)
    path('api/chat/conversations/<int:pk>/messages/', api.ConversationMessageListSendAPI.as_view(), name='api_conversation_messages'),
    path('api/conversations/<int:pk>/messages/', api.ConversationMessageListSendAPI.as_view(), name='api_conversations_messages_alias'),

    # UC-2.2: Thao tác tiếp nhận, đóng phiên, tiếp quản hội thoại của Staff
    path('api/conversations/', api.StaffConversationListAPI.as_view(), name='api_staff_conversations_list'),
    path('api/conversations/<int:pk>/accept/', api.ConversationAcceptAPI.as_view(), name='api_conversation_accept'),
    path('api/conversations/<int:pk>/close/', api.ConversationCloseAPI.as_view(), name='api_conversation_close'),
    path('api/conversations/<int:pk>/takeover/', api.ConversationTakeoverAPI.as_view(), name='api_conversation_takeover'),

    # UC-2.3: Quản lý kịch bản Chatbot (FAQ) (GET, POST, PUT, DELETE)
    path('api/admin/faqs/', api.AdminFAQListCreateAPI.as_view(), name='api_admin_faqs'),
    path('api/admin/faqs/<int:pk>/', api.AdminFAQDetailAPI.as_view(), name='api_admin_faq_detail'),
    path('api/admin/faqs/<int:pk>/toggle-status/', api.AdminFAQToggleStatusAPI.as_view(), name='api_admin_faq_toggle'),
    path('api/faqs/', api.AdminFAQListCreateAPI.as_view(), name='api_faqs_alias'),
    path('api/faqs/<int:pk>/', api.AdminFAQDetailAPI.as_view(), name='api_faq_detail_alias'),

    # Tiện ích tra cứu nhanh dịch vụ cho Panel tư vấn (Figma Node 210:2465)
    path('api/services/lookup/', api.QuickServicesLookupAPI.as_view(), name='api_services_lookup'),
]
