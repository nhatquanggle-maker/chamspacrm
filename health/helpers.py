import json
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from core.models import UserHealthProfile


def generate_unique_health_code(user):
    """Sinh mã định danh hồ sơ sức khỏe duy nhất dạng HP-KH0001."""
    base_code = f"HP-KH{user.id:04d}"
    if not UserHealthProfile.objects.filter(health_code=base_code).exists():
        return base_code
    suffix = timezone.now().strftime("%y%m%d%H%M")
    return f"HP-KH{user.id:03d}-{suffix[-4:]}"


def format_metric_value(val):
    """Định dạng số đo chiều cao / cân nặng, loại bỏ phần thập phân .00 thừa."""
    if val is None:
        return ""
    f = float(val)
    return str(int(f)) if f.is_integer() else f"{f:.1f}".rstrip('0').rstrip('.')


def parse_conditions_list(raw_conditions):
    """Chuẩn hóa danh sách bệnh lý từ list, JSON string hoặc chuỗi phân tách dấu phẩy."""
    if not raw_conditions:
        return []
    if isinstance(raw_conditions, list):
        return [str(c).strip() for c in raw_conditions if len(str(c).strip()) > 1]
    if isinstance(raw_conditions, str):
        raw_str = raw_conditions.strip()
        if len(raw_str) <= 1:
            return []
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, list):
                return [str(c).strip() for c in parsed if len(str(c).strip()) > 1]
            if isinstance(parsed, str) and len(parsed.strip()) > 1:
                return [parsed.strip()]
        except Exception:
            pass
        if ',' in raw_str:
            return [c.strip() for c in raw_str.split(',') if len(c.strip()) > 1]
        return [raw_str]
    val = str(raw_conditions).strip()
    return [val] if len(val) > 1 else []


def compute_bmi(height_cm, weight_kg):
    if height_cm and weight_kg and float(height_cm) > 0:
        height_m = float(height_cm) / 100.0
        return round(float(weight_kg) / (height_m * height_m), 1)
    return None


def get_bmi_meta(bmi_val):
    if bmi_val is None:
        return "Chưa xác định", "Chưa đo", "bg-secondary"
    if bmi_val < 18.5:
        return "Thể trạng gầy (Nhẹ cân)", "Nhẹ cân", "bg-info text-dark"
    if bmi_val < 23.0:
        return "Thể trạng cân đối (Bình thường)", "Cân đối", "bg-success"
    if bmi_val < 25.0:
        return "Thể trạng thừa cân (Tiền béo phì)", "Thừa cân", "bg-warning text-dark"
    return "Thể trạng béo phì (Cần lưu ý)", "Béo phì", "bg-danger"


def get_pain_meta(level):
    if level is None:
        return "Chưa khảo sát", "#6c757d"
    if level <= 3:
        return "Đau nhẹ / Ê ẩm thoáng qua", "#2E7D32"
    if level <= 6:
        return "Đau vừa / Căng cơ do áp lực công việc", "#F57F17"
    if level <= 8:
        return "Đau nhiều / Khó chịu, hạn chế vận động", "#E65100"
    return "Đau dữ dội / Co thắt cơ cấp tính", "#781A24"


def get_health_alerts(obj):
    alerts = []
    if obj.blood_pressure == 'Cao':
        alerts.append({"type": "danger", "title": "Huyết áp cao", "desc": "Tránh ấn mạnh huyệt vùng đầu cổ, tránh tắm nước quá nóng."})
    elif obj.blood_pressure == 'Thấp':
        alerts.append({"type": "warning", "title": "Huyết áp thấp", "desc": "Giữ ấm cơ thể, chuyển tư thế nhẹ nhàng, tránh xông hơi lâu."})

    for cond_str in parse_conditions_list(obj.health_conditions):
        cond_lower = cond_str.lower()
        if 'thai' in cond_lower:
            alerts.append({"type": "danger", "title": "Đang mang thai", "desc": "TUYỆT ĐỐI KHÔNG ấn huyệt Hợp Cốc, Tam Âm Giao, Vai gáy mạnh."})
        elif 'tim' in cond_lower:
            alerts.append({"type": "danger", "title": "Bệnh tim mạch", "desc": "Massage nhẹ nhàng, không xoa bóp vùng ngực, phòng ấm thoáng."})
        elif 'nhạy cảm' in cond_lower or 'kích ứng' in cond_lower:
            alerts.append({"type": "warning", "title": "Da nhạy cảm", "desc": "Dùng dầu nền tự nhiên tinh khiết, tránh chà xát mạnh gây kích ứng."})
        elif 'cột sống' in cond_lower or 'thoát vị' in cond_lower:
            alerts.append({"type": "danger", "title": "Bệnh lý cột sống", "desc": "Không bẻ khớp, không giẫm lưng, chỉ xoa bóp cơ mềm xung quanh."})
        elif 'giãn tĩnh mạch' in cond_lower or 'tĩnh mạch' in cond_lower:
            alerts.append({"type": "warning", "title": "Suy giãn tĩnh mạch", "desc": "Tránh massage sâu vuốt ngược chiều tĩnh mạch ở bắp chân."})
        elif 'phẫu thuật' in cond_lower:
            alerts.append({"type": "danger", "title": "Phẫu thuật gần đây", "desc": "Tránh tác động mạnh vào khu vực có vết thương/mổ."})
        elif any(k in cond_lower for k in ['tiểu đường', 'ung thư', 'tai biến', 'gãy xương']):
            alerts.append({"type": "danger", "title": cond_str, "desc": "Lưu ý thể trạng đặc biệt của khách trước khi trị liệu."})

    if obj.allergy_notes and str(obj.allergy_notes).strip():
        notes_str = str(obj.allergy_notes).strip()
        notes_lower = notes_str.lower()
        negative_phrases = ['không có', 'không', 'ko có', 'ko', 'none', 'không có dị ứng', 'bình thường', 'không dị ứng']
        if not any(neg in notes_lower and len(notes_lower) < 40 for neg in negative_phrases):
            alerts.append({
                "type": "danger",
                "title": "Dị ứng nguyên liệu",
                "desc": f"Dị ứng ghi nhận: {notes_str} - Tuyệt đối không sử dụng tinh dầu này!",
            })
    return alerts


def serialize_health_profile(obj):
    """Chuyển UserHealthProfile thành dict đầy đủ các trường tính toán BMI, pain, alert."""
    bmi_val = compute_bmi(obj.height_cm, obj.weight_kg)
    bmi_cls, bmi_short, bmi_badge = get_bmi_meta(bmi_val)
    pain_sev, pain_color = get_pain_meta(obj.pain_level)
    alerts = get_health_alerts(obj)
    return {
        'id': obj.id,
        'health_code': obj.health_code,
        'user_id': obj.user_id,
        'user_name': obj.user.name if obj.user else '',
        'user_phone': obj.user.phone if obj.user else '',
        'user_email': obj.user.email if obj.user else '',
        'height_cm': float(obj.height_cm) if obj.height_cm is not None else None,
        'weight_kg': float(obj.weight_kg) if obj.weight_kg is not None else None,
        'formatted_height': format_metric_value(obj.height_cm) or None,
        'formatted_weight': format_metric_value(obj.weight_kg) or None,
        'blood_pressure': obj.blood_pressure,
        'focus_areas': obj.focus_areas or [],
        'massage_pressure': obj.massage_pressure,
        'pain_level': obj.pain_level,
        'health_conditions': obj.health_conditions or [],
        'allergy_notes': obj.allergy_notes or '',
        'special_requests': obj.special_requests or '',
        'recovery_goals': obj.recovery_goals or [],
        'created_at': obj.created_at.isoformat() if obj.created_at else None,
        'bmi': bmi_val,
        'bmi_classification': bmi_cls,
        'bmi_short_label': bmi_short,
        'bmi_badge_class': bmi_badge,
        'pain_severity': pain_sev,
        'pain_color': pain_color,
        'has_medical_alert': len(alerts) > 0,
        'alert_details': alerts,
        'formatted_updated_at': obj.created_at.strftime('%d/%m/%Y %H:%M') if obj.created_at else '',
    }


def _parse_decimal(raw_val, field_label, max_val):
    if raw_val in (None, ''):
        return None, None
    try:
        val = Decimal(str(raw_val).strip())
    except (InvalidOperation, ValueError):
        return None, f"{field_label} phải là một số hợp lệ."
    if val <= 0 or val > max_val:
        return None, f"{field_label} không hợp lý (phải > 0 và <= {max_val})."
    return val, None


def validate_health_payload(data):
    """Kiểm tra và chuẩn hóa dữ liệu cập nhật hồ sơ sức khỏe. Trả về (cleaned, errors)."""
    errors = {}

    height_cm, h_err = _parse_decimal(data.get('height_cm'), 'Chiều cao', 250)
    if h_err:
        errors['height_cm'] = h_err

    weight_kg, w_err = _parse_decimal(data.get('weight_kg'), 'Cân nặng', 250)
    if w_err:
        errors['weight_kg'] = w_err

    bp_raw = (data.get('blood_pressure') or '').strip()
    bp_map = {
        'binh thuong': 'Bình thường', 'normal': 'Bình thường',
        'thap': 'Thấp', 'low': 'Thấp',
        'cao': 'Cao', 'high': 'Cao',
    }
    blood_pressure = 'Bình thường'
    if bp_raw:
        blood_pressure = bp_map.get(bp_raw.lower(), bp_raw)
        if blood_pressure not in ('Bình thường', 'Thấp', 'Cao'):
            errors['blood_pressure'] = "Huyết áp phải là Bình thường, Thấp hoặc Cao."

    pressure_raw = (data.get('massage_pressure') or '').strip()
    pressure_map = {
        'nhe': 'Nhẹ nhàng', 'nhe nhang': 'Nhẹ nhàng', 'gentle': 'Nhẹ nhàng',
        'vua': 'Lực vừa', 'luc vua': 'Lực vừa', 'medium': 'Lực vừa',
        'manh': 'Lực mạnh', 'luc manh': 'Lực mạnh', 'strong': 'Lực mạnh', 'deep': 'Lực mạnh',
    }
    massage_pressure = 'Lực vừa'
    if pressure_raw:
        mapped_pressure = pressure_map.get(pressure_raw.lower(), pressure_raw)
        massage_pressure = mapped_pressure if mapped_pressure in ('Nhẹ nhàng', 'Lực vừa', 'Lực mạnh') else 'Lực vừa'

    pain_level = 5
    if data.get('pain_level') not in (None, ''):
        try:
            pain_level = int(data.get('pain_level'))
            if pain_level < 1 or pain_level > 10:
                errors['pain_level'] = "Mức độ đau phải từ 1 đến 10."
        except (ValueError, TypeError):
            errors['pain_level'] = "Mức độ đau phải là số nguyên từ 1 đến 10."

    if errors:
        return None, errors

    def _clean_list(key):
        val = data.get(key, [])
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        return []

    return {
        'height_cm': height_cm,
        'weight_kg': weight_kg,
        'blood_pressure': blood_pressure,
        'focus_areas': _clean_list('focus_areas'),
        'massage_pressure': massage_pressure,
        'pain_level': pain_level,
        'health_conditions': _clean_list('health_conditions'),
        'allergy_notes': (data.get('allergy_notes') or '').strip(),
        'special_requests': (data.get('special_requests') or '').strip(),
        'recovery_goals': _clean_list('recovery_goals'),
    }, None

