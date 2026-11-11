"""
================================================================================
MODULE 06: QUẢN LÝ HỘI VIÊN & TÍCH ĐIỂM (MOD-06) - APP CONFIGURATION
Thành viên phụ trách: MINH KHÁNH
Mục đích:
  - Khai báo cấu hình ứng dụng membership.
  - Tự động nạp Signals (post_save Invoice, post_save User, post_save MembershipPoint)
    để thực hiện tích điểm tự động (UC-6.3), thăng hạng tự động, và đồng bộ dữ liệu
    toàn vẹn với tất cả các module khác trong hệ thống Cham Spa.
================================================================================
"""

from django.apps import AppConfig


class MembershipConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'membership'
    verbose_name = 'MOD-06: Quản lý Hội viên & Tích điểm'

    def ready(self):
        """
        Nạp signals khi Django khởi động để lắng nghe sự kiện từ Invoice, User, MembershipPoint.
        Tuân thủ quy tắc kiến trúc: Không chỉnh sửa core hay các module khác,
        lắng nghe và xử lý đồng bộ độc lập qua Django Signals mà không truy vấn DB trong ready().
        """
        try:
            import membership.signals  # noqa: F401
        except ImportError:
            pass
