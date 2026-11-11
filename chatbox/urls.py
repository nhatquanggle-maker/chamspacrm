"""
URL Configuration cho Phân hệ Quản lý Boxchat Tư vấn - CHAMSPA CRM
"""

from django.urls import path
from . import views, api

app_name = 'chatbox'

urlpatterns = [
    # 1. Giao diện Web
    path('', views.chatbox_index_view, name='index'),
    path('livechat/', views.livechat_staff_view, name='livechat'),
    path('inbox/', views.livechat_staff_view, name='inbox'),
    path('faqs/', views.faq_management_view, name='faq_management'),
    path('customer/', views.customer_chat_view, name='customer_chat'),
    path('admin/monitor/', views.admin_livechat_monitor_view, name='admin_monitor'),
    path('admin/faqs/', views.faq_management_view, name='admin_faq'),
    path('admin/', views.admin_livechat_monitor_view, name='admin_index'),

    # 2. AJAX Endpoints
    path('api/chat/bot-reply/', api.bot_reply_api, name='api_bot_reply'),
    path('api/chat/faq-blocks/', api.public_faq_blocks_api, name='api_faq_blocks'),
    path('api/conversations/transfer/', api.conversation_transfer_staff_api, name='api_conversations_transfer'),
    path('api/conversations/my-active/', api.customer_active_conversation_api, name='api_customer_active_conversation'),
    path('api/conversations/<int:pk>/messages/', api.conversation_messages_api, name='api_conversations_messages_alias'),
    path('api/conversations/', api.staff_conversations_list_api, name='api_staff_conversations_list'),
    path('api/conversations/<int:pk>/accept/', api.conversation_accept_api, name='api_conversation_accept'),
    path('api/conversations/<int:pk>/close/', api.conversation_close_api, name='api_conversation_close'),
    path('api/conversations/<int:pk>/takeover/', api.conversation_takeover_api, name='api_conversation_takeover'),
    path('api/admin/conversations/<int:pk>/monitor/', api.admin_conversation_monitor_api, name='api_admin_conversation_monitor'),
    path('api/admin/conversations/<int:pk>/reassign/', api.admin_reassign_staff_api, name='api_admin_conversation_reassign'),
    path('api/admin/conversations/<int:pk>/takeover/', api.admin_takeover_conversation_api, name='api_admin_conversation_takeover'),
    path('api/admin/conversations/<int:pk>/messages/', api.admin_send_message_api, name='api_admin_conversation_send_message'),
    path('api/admin/faqs/', api.admin_faqs_api, name='api_admin_faqs'),
    path('api/admin/faqs/<int:pk>/', api.admin_faq_detail_api, name='api_admin_faq_detail'),
    path('api/admin/faqs/<int:pk>/toggle-status/', api.admin_faq_toggle_status_api, name='api_admin_faq_toggle'),
    path('api/admin/faqs/export/', api.admin_faq_export_api, name='api_admin_faq_export'),
]
