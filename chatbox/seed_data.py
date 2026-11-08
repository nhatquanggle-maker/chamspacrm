"""
Script khởi tạo dữ liệu mẫu cho Phân hệ Quản lý Boxchat tư vấn (MOD-02)
Thành viên phụ trách: Thảo Ngọc
Tạo sẵn kịch bản FAQ và các cuộc hội thoại thử nghiệm chuẩn 100% Ảnh 1 Figma Node 207:1040:
  - Khách hàng 1: Thanh Thỏ (+84 901 234 567 - Vai gáy / Trị liệu)
  - Khách hàng 2: Trần Gia Hân (+84 938 228 814 - Thư giãn toàn thân)
  - Khách hàng 3: Hoàng Bảo Long (+84 906 441 290 - Đặt lịch đôi)
  - Khách hàng 4: Phạm Khánh Vy (+84 977 515 006 - Voucher ưu đãi)
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from core.models import FAQ, Conversation, ConversationMessage, User


def seed_chatbox_data():
    print("--- Bắt đầu khởi tạo dữ liệu mẫu chuẩn Ảnh 1 Figma Node 207:1040 ---")

    # 1. TẠO CÂU HỎI THƯỜNG GẶP FAQ (UC-2.3 & UC-2.1)
    faqs_data = [
        {
            'faq_code': 'FAQ-GIA-01',
            'category': 'Bảng giá',
            'question': 'Bảng giá dịch vụ tại Cham Spa & Massage là bao nhiêu?',
            'keywords': 'giá, bao nhiêu tiền, chi phí, bảng giá, menu giá, giá dịch vụ',
            'answer': 'Dạ, các gói trị liệu tại Cham Spa & Massage có mức giá dao động từ 350.000đ đến 1.250.000đ tùy theo liệu trình và thời lượng (60p - 90p - 120p). Chi tiết bảng giá từng gói quý khách có thể tham khảo tại mục Dịch vụ trên website ạ.',
            'status': 'Active'
        },
        {
            'faq_code': 'FAQ-GIO-01',
            'category': 'Giờ mở cửa',
            'question': 'Giờ hoạt động mở cửa đón khách của Cham Spa?',
            'keywords': 'giờ mở cửa, mấy giờ mở, thời gian làm việc, mở đến mấy giờ, giờ đón khách',
            'answer': 'Cham Spa & Massage phục vụ quý khách từ 09:00 sáng đến 22:00 đêm tất cả các ngày trong tuần (bao gồm cả thứ Bảy, Chủ Nhật và các ngày Lễ, Tết) ạ.',
            'status': 'Active'
        },
        {
            'faq_code': 'FAQ-CHI-01',
            'category': 'Chi nhánh & Địa chỉ',
            'question': 'Địa chỉ Cham Spa & Massage nằm ở đâu?',
            'keywords': 'địa chỉ, chi nhánh, ở đâu, vị trí, đường nào, cơ sở',
            'answer': 'Dạ Cham Spa & Massage tọa lạc tại địa chỉ: 05 Lê Quang Hoà, Khu đô thị sinh thái Hoà Xuân, Cẩm Lệ, Đà Nẵng (bên bờ sông Cẩm Lệ thơ mộng) ạ.',
            'status': 'Active'
        },
        {
            'faq_code': 'FAQ-DAT-01',
            'category': 'Đặt lịch hẹn',
            'question': 'Làm sao để đặt lịch hẹn trước tại Cham Spa?',
            'keywords': 'đặt lịch, hẹn trước, book phòng, giữ chỗ, cách đặt',
            'answer': 'Quý khách có thể dễ dàng đặt lịch trực tuyến 24/7 bằng cách bấm nút "Đặt lịch ngay" trên website, chọn ngày giờ và dịch vụ mong muốn, hoặc liên hệ hotline 0987 773 777 để được xếp phòng ưu tiên ạ.',
            'status': 'Active'
        },
        {
            'faq_code': 'FAQ-DOI-01',
            'category': 'Chính sách',
            'question': 'Tôi có thể dời lịch hẹn sang ngày khác được không?',
            'keywords': 'dời lịch, đổi giờ, đổi ngày, dời hẹn, lùi lịch',
            'answer': 'Dạ hoàn toàn được ạ! Quý khách có thể dời lịch tối đa 2 lần thông qua trang "Lịch hẹn của tôi", miễn là thao tác trước giờ hẹn cũ tối thiểu 2 tiếng theo quy định của Spa ạ.',
            'status': 'Active'
        },
        {
            'faq_code': 'FAQ-HUY-01',
            'category': 'Chính sách',
            'question': 'Chính sách hủy lịch hẹn và hoàn tiền như thế nào?',
            'keywords': 'hủy lịch, hoàn tiền, hủy hẹn, trả lại tiền, không đến được',
            'answer': 'Nếu có việc bận đột xuất, quý khách có thể bấm Hủy lịch trước giờ hẹn tối thiểu 4 tiếng và nhập số tài khoản ngân hàng. Bộ phận kế toán Spa sẽ đối soát và hoàn tiền cọc trong vòng 24 giờ ạ.',
            'status': 'Active'
        },
        {
            'faq_code': 'FAQ-THANH-01',
            'category': 'Thanh toán',
            'question': 'Cham Spa hỗ trợ những hình thức thanh toán nào?',
            'keywords': 'thanh toán, vietqr, chuyển khoản, quét mã, tiền mặt, qr',
            'answer': 'Cham Spa hỗ trợ thanh toán trực tuyến nhanh chóng và tự động qua quét mã Napas247 VietQR của mọi ngân hàng, thanh toán qua thẻ tín dụng và tiền mặt trực tiếp tại quầy lễ tân ạ.',
            'status': 'Active'
        },
        {
            'faq_code': 'FAQ-KHOE-01',
            'category': 'Hồ sơ sức khỏe',
            'question': 'Khảo sát hồ sơ sức khỏe trước khi làm dịch vụ có tác dụng gì?',
            'keywords': 'sức khỏe, hồ sơ sức khỏe, khảo sát, vùng đau, lực massage, huyết áp',
            'answer': 'Hồ sơ sức khỏe giúp kỹ thuật viên nắm rõ vùng đau mỏi cần tập trung, mức độ đau, huyết áp và các lưu ý đặc biệt (như mang thai, da nhạy cảm) để điều chỉnh lực massage và phác đồ an toàn nhất cho quý khách ạ.',
            'status': 'Active'
        },
    ]

    for item in faqs_data:
        faq, _ = FAQ.objects.update_or_create(
            faq_code=item['faq_code'],
            defaults=item
        )

    # 2. TẠO 4 KHÁCH HÀNG MẪU KHỚP 100% ẢNH 1 FIGMA
    customers_mock = [
        {
            'name': 'Thanh Thỏ',
            'phone': '0901234567',
            'email': 'thanhtho@gmail.com',
            'tag': 'Vai gáy / Trị liệu',
            'minutes_ago': 3,
            'is_selected': True
        },
        {
            'name': 'Trần Gia Hân',
            'phone': '0938228814',
            'email': 'giahan@gmail.com',
            'tag': 'Thư giãn toàn thân',
            'minutes_ago': 5,
            'is_selected': False
        },
        {
            'name': 'Hoàng Bảo Long',
            'phone': '0906441290',
            'email': 'baolong@gmail.com',
            'tag': 'Đặt lịch đôi',
            'minutes_ago': 8,
            'is_selected': False
        },
        {
            'name': 'Phạm Khánh Vy',
            'phone': '0977515006',
            'email': 'khanhvy@gmail.com',
            'tag': 'Voucher ưu đãi',
            'minutes_ago': 12,
            'is_selected': False
        },
    ]

    staff_user = User.objects.filter(is_staff=True).first()
    if not staff_user:
        staff_user = User.objects.create_user(
            username='0905123456',
            phone='0905123456',
            name='Lê Thị Mai',
            email='lethimai@chamspa.vn',
            is_staff=True
        )

    for cdata in customers_mock:
        user, _ = User.objects.get_or_create(
            phone=cdata['phone'],
            defaults={
                'username': cdata['phone'],
                'name': cdata['name'],
                'email': cdata['email'],
                'is_staff': False,
                'is_superuser': False
            }
        )

        conv, _ = Conversation.objects.get_or_create(
            customer=user,
            defaults={
                'status': 'Đang chờ',
                'customer_tag': cdata['tag'],
                'created_at': timezone.now() - timedelta(minutes=cdata['minutes_ago'])
            }
        )
        conv.customer_tag = cdata['tag']
        conv.save()

        # Nếu là Thanh Thỏ -> Tạo chuỗi tin nhắn y hệt như trên Ảnh 1
        if cdata['is_selected']:
            conv.messages.all().delete()
            # Tin nhắn 1 của khách
            ConversationMessage.objects.create(
                conversation=conv,
                sender_type='Customer',
                content='Chào bạn, mình bị đau mỏi vai phải do ngồi làm việc lâu. Spa có liệu trình nào phù hợp không?',
                created_at=timezone.now() - timedelta(minutes=15)
            )
            # Tin nhắn 2 của nhân viên tư vấn
            staff_display_name = staff_user.name or 'Lê Thị Mai'
            ConversationMessage.objects.create(
                conversation=conv,
                sender_type='Staff',
                content=f'Chào chị Thỏ, em là {staff_display_name}. Với tình trạng của chị, liệu trình Massage Body Trị Liệu Vai Gáy 60 phút sẽ phù hợp nhất ạ.',
                created_at=timezone.now() - timedelta(minutes=14)
            )
            # Tin nhắn 3 của khách
            ConversationMessage.objects.create(
                conversation=conv,
                sender_type='Customer',
                content='Mình muốn lực nhẹ và ưu tiên KTV nữ. Tối nay còn lịch không bạn?',
                created_at=timezone.now() - timedelta(minutes=5)
            )
            # Tin nhắn 4 của nhân viên có đính kèm dịch vụ
            ConversationMessage.objects.create(
                conversation=conv,
                sender_type='Staff',
                content='Dạ còn lịch 18:30 với KTV Lan. Em có thể giữ chỗ trong 10 phút và gửi liên kết xác nhận trực tiếp cho chị',
                attachment_name='Phac-do-vai-gay-60p.pdf',
                attachment_size='1.5 MB',
                created_at=timezone.now() - timedelta(minutes=3)
            )
            print(f"  + Đã tạo hội thoại mẫu chi tiết khớp Ảnh 1 cho: {cdata['name']}")
        else:
            if not conv.messages.exists():
                ConversationMessage.objects.create(
                    conversation=conv,
                    sender_type='Customer',
                    content=f"Dạ em cần tư vấn về nhu cầu: {cdata['tag']} ạ.",
                    created_at=timezone.now() - timedelta(minutes=cdata['minutes_ago'])
                )

    print("--- Hoàn tất khởi tạo dữ liệu mẫu chuẩn Ảnh 1 Figma Node 207:1040 ---")


if __name__ == '__main__':
    seed_chatbox_data()
