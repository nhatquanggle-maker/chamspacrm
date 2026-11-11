"""
================================================================================
MODULE 07: QUẢN LÝ THÔNG BÁO & KHUYẾN MÃI (MOD-07) - MODELS
Thành viên phụ trách: MINH KHA
Mục đích:
  - Tuân thủ nghiêm ngặt quy tắc dự án: TUYỆT ĐỐI CẤM TỰ Ý SỬA/TẠO MODEL MỚI VÀ CẤM CHẠY makemigrations.
  - Toàn bộ 20 Model chuẩn CSDL đã được dựng sẵn tại core/models.py.
  - Tại đây chỉ import các Model thuộc phạm vi phân hệ 07 để sử dụng:
    + Promotion: Chương trình khuyến mãi toàn Spa (Figma Card gradient).
    + Voucher: Mã giảm giá linh hoạt (giảm % có mức trần hoặc tiền mặt cố định).
    + Notification: Bảng tin thông báo hệ thống gửi đến người dùng (bỏ is_read).
================================================================================
"""

from core.models import Promotion, Voucher, Notification, User

# Xuất danh sách model dùng chung trong module
__all__ = ['Promotion', 'Voucher', 'Notification', 'User']
