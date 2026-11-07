# HỆ THỐNG QUẢN LÝ QUAN HỆ KHÁCH HÀNG & ĐẶT LỊCH DỊCH VỤ SPA (CHAMSPA CRM)

[![Django](https://img.shields.io/badge/Django-6.1.2-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/Django_REST_Framework-3.18.3-red?style=for-the-badge&logo=django&logoColor=white)](https://www.django-rest-framework.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![VietQR](https://img.shields.io/badge/Payment-VietQR-blue?style=for-the-badge)](https://vietqr.io/)

---

## 📌 I. THÔNG TIN CHUNG DỰ ÁN

* **Tên đề tài:** Hệ thống Quản lý Quan hệ Khách hàng & Đặt lịch dịch vụ Spa (**ChamSPA CRM**)
* **Đơn vị đào tạo:** Trường Đại học Kinh tế – Đại học Đà Nẵng (**DUE**)
* **Học phần:** Lập trình Web
* **Doanh nghiệp nghiên cứu:** **ChamSpa & Massage Đà Nẵng** (Dịch vụ Massage trị liệu Đông y & Thư giãn chuyên sâu)
* **Địa chỉ cơ sở:** 05 Lê Quang Hoà, Hoà Xuân, Cẩm Lệ, TP. Đà Nẵng
* **Đội ngũ sinh viên thực hiện (Nhóm 5 thành viên):**
  1. **Lê Nhật Quang (Leader)** – Phụ trách MOD-01, MOD-05 & Kiến trúc Framework nền tảng
  2. **Thảo Ngọc (Meo)** – Phụ trách MOD-02 & MOD-08
  3. **Minh Khánh** – Phụ trách MOD-03 & MOD-06
  4. **Thanh Thảo** – Phụ trách MOD-04 & MOD-09
  5. **Minh Kha** – Phụ trách MOD-07 & MOD-10

---

## 🛠️ II. BỘ TECH STACK & DESIGN SYSTEM

### 1. Kiến trúc Công nghệ
* **Backend & Xử lý nghiệp vụ:** Python 3.10+ kết hợp **Django 6.1.2** và **Django REST Framework (DRF)**.
* **Cơ sở dữ liệu (Database):** **SQLite** (`db.sqlite3`) chuẩn hóa tập trung 20 bảng tại app `core`, loại bỏ hoàn toàn xung đột migration khi làm việc nhóm.
* **Giao diện & Trang trí (UI/CSS):** 
  * HTML5 kết hợp hệ thống kế thừa Django Template (`{% extends %}`).
  * **Bootstrap 5.3** & **Bootstrap Icons v1.11+**.
  * CSS Custom chuẩn hóa bộ màu nhận diện thương hiệu ChamSpa.
* **Tương tác động (Client-side):** Vanilla JavaScript (**Fetch API**) gọi ngầm REST API, xử lý cập nhật trạng thái, phân trang, Modal popup, thông báo Toast mà không cần tải lại trang.
* **Thư viện mở rộng:**
  * `FullCalendar.js`: Quản lý lịch hẹn động trực quan.
  * `Chart.js`: Kết xuất biểu đồ Dashboard thời gian thực.
  * `SheetJS (xlsx)` & `html2pdf.js`: Kết xuất và tải báo cáo Excel/PDF trực tiếp tại trình duyệt.
* **Cổng thanh toán:** Thanh toán trực tuyến qua chuẩn mã **VietQR (Napas247)**.

### 2. Bộ nhận diện thương hiệu (Design Tokens)
* **Màu chủ đạo (Cham Red):** `#781A24` (Đỏ rượu vang Đông y hoàng gia)
* **Màu nền tổng thể:** `#F4EFE3` (Be kem ấm áp, thư thái)
* **Màu điểm nhấn (Gold):** `#D0B581` & `#E8D8B5` (Vàng kim cao cấp)
* **Màu Header:** `#3D271D` (Nâu gỗ trầm)
* **Màu Footer:** `#000000` (Đen tuyền tuyệt đối)
* **Typography:**
  * **Tiêu đề (Headings):** `Lora` & `Tinos` (Serif quý phái)
  * **Nội dung (Body):** `Cabin` (Sans-serif thanh lịch, dễ đọc)
  * **Thanh điều hướng (Nav):** `Manrope`

---

## 👥 III. CƠ CHẾ PHÂN QUYỀN NGƯỜI DÙNG (3 CẤP ĐỘ)

Hệ thống sử dụng Custom User Model kế thừa `AbstractUser`, định danh bằng **Số điện thoại (Unique, Not Null)**:
1. **Khách hàng (`is_staff=False, is_superuser=False`):** Đặt lịch hẹn, khảo sát hồ sơ sức khỏe, quản lý lịch sử cá nhân, tích điểm hội viên VIP, gửi đánh giá / khiếu nại, chat với Bot/nhân viên.
2. **Nhân viên (`is_staff=True, is_superuser=False`):** Vận hành lịch hẹn, tư vấn chat trực tiếp, phản hồi đánh giá khách hàng, đối soát hóa đơn VietQR tại quầy.
3. **Quản lý / Admin (`is_superuser=True`):** Toàn quyền quản trị danh mục dịch vụ, nhân sự, khóa/mở tài khoản (`is_active`), phát hành khuyến mãi & voucher, theo dõi Dashboard báo cáo.

---

## 📦 IV. TỔNG HỢP 10 PHÂN HỆ VÀ MA TRẬN TRÁCH NHIỆM

| Mã Module | Tên Phân hệ | Số lượng UC | Phụ trách | Tác nhân chính | Bảng CSDL cốt lõi |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **MOD-01** | Đặt lịch & Quản lý lịch hẹn | 5 UC | **Nhật Quang** | Khách hàng, Staff, Admin | `Appointment`, `AppointmentDetail`, `Voucher`, `Service` |
| **MOD-02** | Quản lý Boxchat tư vấn | 3 UC | **Thảo Ngọc** | Khách hàng, Vãng lai, Staff, Admin | `FAQ`, `Conversation`, `ConversationMessage` |
| **MOD-03** | Quản lý Danh mục Dịch vụ | 3 UC | **Minh Khánh** | Khách hàng, Vãng lai, Admin | `Category`, `Service`, `ServiceImage` |
| **MOD-04** | Quản lý Phản hồi & Khiếu nại | 5 UC | **Thanh Thảo** | Khách hàng, Staff, Admin | `Feedback`, `Complaint`, `Voucher` |
| **MOD-05** | Quản lý Tài khoản & Phân quyền | 14 UC | **Nhật Quang** | Khách hàng, Staff, Admin, Vãng lai | `User`, `UserProfile` |
| **MOD-06** | Quản lý Hội viên & Tích điểm | 3 UC | **Minh Khánh** | Khách hàng, Staff, Admin, Hệ thống | `Tier`, `Membership`, `MembershipPoint` |
| **MOD-07** | Quản lý Thông báo & Khuyến mãi | 5 UC | **Minh Kha** | Khách hàng, Staff, Admin, Hệ thống | `Promotion`, `Voucher`, `Notification` |
| **MOD-08** | Quản lý Hồ sơ Sức khỏe | 2 UC | **Thảo Ngọc** | Khách hàng, Staff, Admin | `UserHealthProfile` (1-1 tối giản) |
| **MOD-09** | Quản lý Thanh toán & Hóa đơn | 3 UC | **Thanh Thảo** | Khách hàng, Thu ngân/Kế toán, Admin | `Invoice`, `Appointment`, `MembershipPoint` |
| **MOD-10** | Quản lý Dashboard & Báo cáo | 2 UC | **Minh Kha** | Quản lý / Ban Giám đốc | `Invoice`, `Appointment`, `Service`, `User` |

---

## 🗄️ V. CƠ SỞ DỮ LIỆU TẬP TRUNG (20 BẢNG CHUẨN HÓA)

Toàn bộ 20 bảng CSDL được định nghĩa tập trung trong **`core/models.py`** để bảo vệ toàn vẹn liên kết khóa ngoại và ngăn ngừa lỗi xung đột migration:

```
core/models.py
├── [MOD-05] User (Custom User Model)
├── [MOD-05] UserProfile
├── [MOD-08] UserHealthProfile
├── [MOD-03] Category
├── [MOD-03] Service
├── [MOD-03] ServiceImage
├── [MOD-06] Tier
├── [MOD-06] Membership
├── [MOD-06] MembershipPoint
├── [MOD-07] Promotion
├── [MOD-07] Voucher
├── [MOD-07] Notification
├── [MOD-01] Appointment
├── [MOD-01] AppointmentDetail
├── [MOD-09] Invoice
├── [MOD-04] Feedback
├── [MOD-04] Complaint
├── [MOD-02] FAQ
├── [MOD-02] Conversation
└── [MOD-02] ConversationMessage
```
*(Bảng `Report_export` đã được lược bỏ khỏi CSDL do cơ chế xuất báo cáo được xử lý trực tiếp tại Client bằng JavaScript).*

---

## 📂 VI. CẤU TRÚC THƯ MỤC DỰ ÁN

```text
CHAMSPA CRM/
│
├── config/                  # Cấu hình dự án Django chính (settings, urls, wsgi)
├── core/                    # App Database dùng chung chứa 20 Models & Admin setup
├── static/                  # Tài nguyên tĩnh
│   ├── css/                 # chamspa.css (bộ màu, typography, resets)
│   ├── js/                  # helper API, format tiền tệ, toast
│   └── images/              # Logo ChamSpa, banner, ảnh liệu trình
│
├── templates/               # Hệ thống giao diện Django Template
│   ├── base.html            # Khung HTML gốc nạp CSS, CDN, Fonts
│   ├── home.html            # Trang chủ ChamSpa (Hero, Philosophy, Signature, Treatments)
│   ├── components/          # Header, Footer, Topbar, 3 Sidebar, Chatbot Widget
│   ├── layouts/             # 4 Khung màn hình: public, customer, staff, admin
│   │
│   ├── accounts/            # Templates MOD-05 (Login, Register, Profile, Admin Users)
│   ├── appointment/         # Templates MOD-01 (Booking wizard, Lịch cá nhân, Quản lý lịch)
│   ├── chatbox/             # Templates MOD-02 (Live Chat Console, Quản lý FAQ)
│   ├── dashboard/           # Templates MOD-10 (Overview KPI, Biểu đồ Chart.js)
│   ├── feedbacks/           # Templates MOD-04 (Đánh giá, Xử lý khiếu nại, Cấp voucher)
│   ├── health/              # Templates MOD-08 (Khảo sát Body map 1-1, Thẻ sức khỏe)
│   ├── marketing/           # Templates MOD-07 (Ví voucher, Bảng tin thông báo, Khuyến mãi)
│   ├── membership/          # Templates MOD-06 (Thẻ VIP điện tử, Tra cứu hội viên)
│   ├── payments/            # Templates MOD-09 (VietQR checkout, Đối soát hóa đơn)
│   └── services/            # Templates MOD-03 (Danh sách dịch vụ, Chi tiết dịch vụ)
│
├── db.sqlite3               # Cơ sở dữ liệu SQLite cục bộ đã nạp sẵn cấu trúc
├── manage.py                # File thực thi lệnh Django
└── requirements.txt         # Danh sách thư viện Python cần thiết
```

---

## 🚀 VII. HƯỚNG DẪN CÀI ĐẶT & CHẠY LOCAL (GETTING STARTED)

### 1. Yêu cầu hệ thống
* **Python:** Phiên bản `3.10` trở lên.
* **Git:** Quản lý mã nguồn.
* **Trình duyệt khuyến nghị:** Google Chrome, Microsoft Edge hoặc Antigravity IDE Simple Browser.

### 2. Các bước cài đặt chi tiết

```bash
# Bước 1: Clone dự án về máy tính
git clone https://github.com/<your-username>/chamspa-crm.git
cd "chamspa-crm"

# Bước 2: Tạo và kích hoạt môi trường ảo (Virtual Environment)
# Trên Windows:
python -m venv .venv
.venv\Scripts\activate

# Bước 3: Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt

# Bước 4: Đồng bộ CSDL (Đã cấu hình sẵn)
python manage.py migrate

# Bước 5: Tạo tài khoản Quản trị tối cao (Superuser)
python manage.py createsuperuser

# Bước 6: Khởi chạy máy chủ phát triển
python manage.py runserver
```

Truy cập hệ thống tại: **`http://127.0.0.1:8000/`**  
Trang quản trị Django Admin: **`http://127.0.0.1:8000/admin/`**

---

## 🔒 VIII. QUY TẮC PHÁT TRIỂN DÀNH CHO THÀNH VIÊN NHÓM

1. **TUYỆT ĐỐI KHÔNG TẠO MODEL MỚI HOẶC CHẠY `makemigrations`:**
   * Toàn bộ 20 Model chuẩn đã nằm trong `core/models.py`.
   * Mọi thao tác truy vấn đều import từ `core.models` (ví dụ: `from core.models import Appointment, Service, User`).
2. **PHẠM VI CODE ĐỘC LẬP:**
   * Mỗi thành viên chỉ làm việc trong app và thư mục `templates/[tên_module]/` được phân công.
   * Cấm tự ý sửa đổi file cấu hình chung `config/settings.py` hoặc `config/urls.py`.
3. **QUY TRÌNH GIT BRANCHING:**
   * Tuyệt đối **KHÔNG PUSH TRỰC TIẾP VÀO NHÁNH `main`**.
   * Mỗi thành viên tự tạo nhánh tính năng: `git checkout -b feature/module-[tên-module]`.
   * Sau khi hoàn tất và test kỹ, đẩy code lên nhánh feature và thông báo Leader kiểm tra để merge vào `main`.

---

## 📄 IX. BẢN QUYỀN & GIẤY PHÉP

Dự án được xây dựng phục vụ mục đích học tập và nghiên cứu thực tế tại **Trường Đại học Kinh tế – Đại học Đà Nẵng (DUE)**.  
Mọi quyền sở hữu thương hiệu và hình ảnh thuộc về **ChamSpa & Massage Đà Nẵng**.  
© 2026 Cham Spa & Massage. All rights reserved.
