"""
================================================================================
MODELS CHO PHÂN HỆ QUẢN LÝ HỒ SƠ SỨC KHỎE (MOD-08) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc (Meo)

LƯU Ý QUAN TRỌNG:
Theo quy định chuẩn kiến trúc hệ thống ChamSpa CRM:
  - Toàn bộ 20 Models chuẩn CSDL đã được định nghĩa tập trung tại core/models.py.
  - Model quản lý hồ sơ sức khỏe là `UserHealthProfile` (MOD-08, Bảng số 3 trong CSDL).
  - TUYỆT ĐỐI CẤM tự ý sửa/tạo model mới và CẤM chạy makemigrations trong app này.
  - Tất cả nghiệp vụ và API của Module 8 đều import trực tiếp:
      `from core.models import UserHealthProfile, User, Appointment`
================================================================================
"""

from django.db import models
from core.models import UserHealthProfile

# Re-export để thuận tiện truy xuất nếu cần thiết
__all__ = ['UserHealthProfile']
