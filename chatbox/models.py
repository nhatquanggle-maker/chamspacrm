"""
================================================================================
PHÂN HỆ 02: QUẢN LÝ BOXCHAT TƯ VẤN (MOD-02) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc
Use Cases:
  - UC-2.1: Trò chuyện với Chatbot tự động (FAQ thuần TEXT, vãng lai in-memory)
  - UC-2.2: Trò chuyện trực tiếp (Kết nối nhân viên tư vấn & Phân quyền tiếp nhận)
  - UC-2.3: Quản lý kịch bản Chatbot (FAQ)
Bảng CSDL trọng tâm: FAQ, Conversation, ConversationMessage
================================================================================
LƯU Ý QUAN TRỌNG:
  - Tuyệt đối không khai báo Model mới hoặc chạy makemigrations.
  - Toàn bộ 20 Model chuẩn CSDL đã được định nghĩa sẵn tại core/models.py.
  - Tại đây chỉ import các Model chuẩn để phục vụ views, serializers và api.
"""

from core.models import FAQ, Conversation, ConversationMessage, User, Service

__all__ = ['FAQ', 'Conversation', 'ConversationMessage', 'User', 'Service']
