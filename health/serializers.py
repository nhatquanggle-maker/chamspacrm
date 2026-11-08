"""
================================================================================
SERIALIZERS CHO PHÂN HỆ QUẢN LÝ HỒ SƠ SỨC KHỎE (MOD-08) - CHAMSPA CRM
Thành viên phụ trách: Thảo Ngọc (Meo)
Mục đích:
  - Chuyển đổi dữ liệu giữa Model Django (UserHealthProfile) và định dạng JSON phục vụ RESTful API.
  - Kiểm tra (validate) dữ liệu đầu vào theo đúng Hợp đồng API và Quy tắc nghiệp vụ chốt.
  - Phục vụ 2 Use Cases chính:
      + UC-8.1: Cập nhật hồ sơ sức khỏe khách hàng (Chuẩn 1-1 tối giản, ghi đè bản ghi cũ)
      + UC-8.2: Xem hồ sơ sức khỏe cá nhân (Phân quyền: User xem của mình, Staff xem mọi khách)
  - Khớp 100% thiết kế giao diện Figma:
      + Node 273:2545 (Giao diện xem hồ sơ sức khỏe & Cảnh báo an toàn y tế)
      + Node 273:2839 (Giao diện cập nhật / khảo sát thể trạng sức khỏe Body Map)
================================================================================
"""

from rest_framework import serializers
from django.utils import timezone
from core.models import UserHealthProfile, User, Appointment


class UserHealthProfileSerializer(serializers.ModelSerializer):
    """
    [MOD-08 - UC-8.2] Serializer hiển thị thông tin chi tiết Hồ sơ sức khỏe cá nhân.
    Bao gồm các trường sinh trắc học, body map vùng đau, chỉ số BMI tính toán tự động,
    phân loại mức độ đau và hệ thống cờ cảnh báo an toàn y tế cho Kỹ thuật viên (KTV).
    """
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    # Các trường tính toán thông minh phục vụ giao diện Figma Node 273:2545
    bmi = serializers.SerializerMethodField(read_only=True)
    bmi_classification = serializers.SerializerMethodField(read_only=True)
    bmi_badge_class = serializers.SerializerMethodField(read_only=True)
    pain_severity = serializers.SerializerMethodField(read_only=True)
    pain_color = serializers.SerializerMethodField(read_only=True)
    has_medical_alert = serializers.SerializerMethodField(read_only=True)
    alert_details = serializers.SerializerMethodField(read_only=True)
    formatted_updated_at = serializers.SerializerMethodField(read_only=True)
    formatted_height = serializers.SerializerMethodField(read_only=True)
    formatted_weight = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = UserHealthProfile
        fields = [
            'id',
            'health_code',
            'user_id',
            'user_name',
            'user_phone',
            'user_email',
            'height_cm',
            'weight_kg',
            'formatted_height',
            'formatted_weight',
            'blood_pressure',
            'focus_areas',
            'massage_pressure',
            'pain_level',
            'health_conditions',
            'allergy_notes',
            'special_requests',
            'recovery_goals',
            'created_at',
            # Computed fields
            'bmi',
            'bmi_classification',
            'bmi_badge_class',
            'pain_severity',
            'pain_color',
            'has_medical_alert',
            'alert_details',
            'formatted_updated_at',
        ]
        read_only_fields = ['id', 'health_code', 'created_at']

    def get_formatted_height(self, obj):
        """Format chiều cao đẹp mắt (165 thay vì 165.00)"""
        if obj.height_cm is not None:
            f = float(obj.height_cm)
            return str(int(f)) if f.is_integer() else f"{f:.1f}".rstrip('0').rstrip('.')
        return None

    def get_formatted_weight(self, obj):
        """Format cân nặng đẹp mắt (52 thay vì 52.00)"""
        if obj.weight_kg is not None:
            f = float(obj.weight_kg)
            return str(int(f)) if f.is_integer() else f"{f:.1f}".rstrip('0').rstrip('.')
        return None

    def get_bmi(self, obj):
        """Tính chỉ số BMI = weight_kg / (height_m ^ 2)"""
        if obj.height_cm and obj.weight_kg and obj.height_cm > 0:
            height_m = float(obj.height_cm) / 100.0
            bmi_val = float(obj.weight_kg) / (height_m * height_m)
            return round(bmi_val, 1)
        return None

    def get_bmi_classification(self, obj):
        """Phân loại chỉ số BMI theo chuẩn y tế châu Á (WHO-WPRO)"""
        bmi_val = self.get_bmi(obj)
        if bmi_val is None:
            return "Chưa xác định"
        if bmi_val < 18.5:
            return "Thể trạng gầy (Nhẹ cân)"
        elif bmi_val < 23.0:
            return "Thể trạng cân đối (Bình thường)"
        elif bmi_val < 25.0:
            return "Thể trạng thừa cân (Tiền béo phì)"
        else:
            return "Thể trạng béo phì (Cần lưu ý)"

    def get_bmi_badge_class(self, obj):
        """Class màu badge cho chỉ số BMI"""
        bmi_val = self.get_bmi(obj)
        if bmi_val is None:
            return "bg-secondary"
        if bmi_val < 18.5:
            return "bg-info text-dark"
        elif bmi_val < 23.0:
            return "bg-success"
        elif bmi_val < 25.0:
            return "bg-warning text-dark"
        else:
            return "bg-danger"

    def get_pain_severity(self, obj):
        """Mô tả mức độ đau mỏi dựa trên thang điểm 1-10"""
        level = obj.pain_level
        if level is None:
            return "Chưa khảo sát"
        if level <= 3:
            return "Đau nhẹ / Ê ẩm thoáng qua"
        elif level <= 6:
            return "Đau vừa / Căng cơ do áp lực công việc"
        elif level <= 8:
            return "Đau nhiều / Khó chịu, hạn chế vận động"
        else:
            return "Đau dữ dội / Co thắt cơ cấp tính"

    def get_pain_color(self, obj):
        """Mã màu biểu thị mức độ đau trên thanh trượt và sơ đồ giải phẫu"""
        level = obj.pain_level
        if level is None:
            return "#6c757d"
        if level <= 3:
            return "#2E7D32"  # Xanh lá dịu
        elif level <= 6:
            return "#F57F17"  # Vàng hổ phách
        elif level <= 8:
            return "#E65100"  # Cam đậm
        else:
            return "#781A24"  # Đỏ rượu vang hoàng gia Cham Spa

    def get_has_medical_alert(self, obj):
        """Cờ báo động an toàn: True nếu khách có bệnh lý nguy cơ hoặc huyết áp bất thường"""
        if obj.blood_pressure in ['Cao', 'Thấp']:
            return True
        if obj.health_conditions and len(obj.health_conditions) > 0:
            return True
        if obj.allergy_notes and obj.allergy_notes.strip():
            notes_lower = obj.allergy_notes.strip().lower()
            negative_words = ['không có', 'không', 'ko có', 'ko', 'none', 'bình thường']
            if not any(notes_lower == neg or notes_lower == f"{neg} dị ứng" for neg in negative_words):
                return True
        return False

    def get_alert_details(self, obj):
        """Danh sách các cảnh báo y tế cụ thể để hiển thị badge đỏ/vàng cho KTV"""
        alerts = []
        if obj.blood_pressure == 'Cao':
            alerts.append({"type": "danger", "title": "Huyết áp cao", "desc": "Tránh ấn mạnh huyệt vùng đầu cổ, tránh tắm nước quá nóng."})
        elif obj.blood_pressure == 'Thấp':
            alerts.append({"type": "warning", "title": "Huyết áp thấp", "desc": "Giữ ấm cơ thể, chuyển tư thế nhẹ nhàng, tránh xông hơi lâu."})

        # Phân tích mảng health_conditions
        conditions = obj.health_conditions or []
        for cond in conditions:
            cond_str = str(cond).strip()
            if 'thai' in cond_str.lower():
                alerts.append({"type": "danger", "title": "Đang mang thai", "desc": "TUYỆT ĐỐI KHÔNG ấn huyệt Hợp Cốc, Tam Âm Giao, Vai gáy mạnh."})
            elif 'tim' in cond_str.lower():
                alerts.append({"type": "danger", "title": "Bệnh tim mạch", "desc": "Massage nhẹ nhàng, không xoa bóp vùng ngực, phòng ấm thoáng."})
            elif 'nhạy cảm' in cond_str.lower() or 'da' in cond_str.lower():
                alerts.append({"type": "warning", "title": "Da nhạy cảm", "desc": "Dùng dầu nền tự nhiên tinh khiết, tránh chà xát mạnh gây kích ứng."})
            elif 'cột sống' in cond_str.lower() or 'thoát vị' in cond_str.lower():
                alerts.append({"type": "danger", "title": "Bệnh lý cột sống", "desc": "Không bẻ khớp, không giẫm lưng, chỉ xoa bóp cơ mềm xung quanh."})
            elif 'giãn tĩnh mạch' in cond_str.lower():
                alerts.append({"type": "warning", "title": "Suy giãn tĩnh mạch", "desc": "Tránh massage sâu vuốt ngược chiều tĩnh mạch ở bắp chân."})
            elif cond_str:
                alerts.append({"type": "warning", "title": cond_str, "desc": "Lưu ý thể trạng của khách trước khi thực hiện dịch vụ."})

        # Phân tích ghi chú dị ứng thông minh (loại trừ nếu khách ghi 'không có')
        if obj.allergy_notes and obj.allergy_notes.strip():
            notes_lower = obj.allergy_notes.strip().lower()
            negative_phrases = ['không có', 'không', 'ko có', 'ko', 'none', 'không có dị ứng', 'bình thường']
            is_negative = any(neg in notes_lower and len(notes_lower) < 40 for neg in negative_phrases)
            if not is_negative:
                alerts.append({
                    "type": "danger",
                    "title": "Dị ứng nguyên liệu",
                    "desc": f"Dị ứng ghi nhận: {obj.allergy_notes.strip()} - Tuyệt đối không sử dụng tinh dầu này!"
                })

        return alerts

    def get_formatted_updated_at(self, obj):
        """Định dạng ngày giờ cập nhật hồ sơ gần nhất"""
        if obj.created_at:
            return obj.created_at.strftime('%d/%m/%Y %H:%M')
        return ""


class HealthProfileUpdateInputSerializer(serializers.Serializer):
    """
    [MOD-08 - UC-8.1] Serializer kiểm tra dữ liệu đầu vào khi Khách hàng hoặc Nhân viên
    cập nhật / khảo sát hồ sơ sức khỏe.
    Khớp 100% Hợp đồng API: POST / PUT /api/health-profile/
    """
    height_cm = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    weight_kg = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    blood_pressure = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    focus_areas = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    massage_pressure = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    pain_level = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=10)
    health_conditions = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    allergy_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    special_requests = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    recovery_goals = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def validate_height_cm(self, value):
        """Kiểm tra chiều cao hợp lý (cm)"""
        if value is not None:
            if value <= 0 or value > 250:
                raise serializers.ValidationError("Chiều cao không hợp lý (phải từ 50 cm đến 250 cm).")
        return value

    def validate_weight_kg(self, value):
        """Kiểm tra cân nặng hợp lý (kg)"""
        if value is not None:
            if value <= 0 or value > 250:
                raise serializers.ValidationError("Cân nặng không hợp lý (phải từ 20 kg đến 250 kg).")
        return value

    def validate_blood_pressure(self, value):
        """Kiểm tra giá trị huyết áp chuẩn hóa"""
        if value:
            valid_choices = ['Bình thường', 'Thấp', 'Cao']
            clean_val = value.strip()
            # Cho phép ánh xạ nếu truyền dạng không dấu hoặc tiếng Anh
            mapping = {
                'binh thuong': 'Bình thường',
                'normal': 'Bình thường',
                'thap': 'Thấp',
                'low': 'Thấp',
                'cao': 'Cao',
                'high': 'Cao',
            }
            mapped = mapping.get(clean_val.lower(), clean_val)
            if mapped not in valid_choices:
                raise serializers.ValidationError(f"Huyết áp phải là một trong các giá trị: {', '.join(valid_choices)}")
            return mapped
        return value

    def validate_massage_pressure(self, value):
        """Kiểm tra lực massage mong muốn"""
        if value:
            valid_choices = ['Nhẹ nhàng', 'Lực vừa', 'Lực mạnh']
            clean_val = value.strip()
            mapping = {
                'nhe': 'Nhẹ nhàng',
                'nhe nhang': 'Nhẹ nhàng',
                'gentle': 'Nhẹ nhàng',
                'vua': 'Lực vừa',
                'luc vua': 'Lực vừa',
                'medium': 'Lực vừa',
                'manh': 'Lực mạnh',
                'luc manh': 'Lực mạnh',
                'strong': 'Lực mạnh',
                'deep': 'Lực mạnh',
            }
            mapped = mapping.get(clean_val.lower(), clean_val)
            if mapped not in valid_choices:
                # Nếu không khớp thì chuẩn hóa về 'Lực vừa'
                return 'Lực vừa'
            return mapped
        return value

    def validate_pain_level(self, value):
        """Kiểm tra thang điểm mức độ đau 1-10"""
        if value is not None:
            if value < 1 or value > 10:
                raise serializers.ValidationError("Mức độ đau phải từ 1 đến 10.")
        return value
