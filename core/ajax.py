import json
from functools import wraps
from django.http import JsonResponse


def is_staff_or_admin(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def is_admin(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def json_error(message, status=400, **extra):
    payload = {'error': message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def parse_json_body(request):
    """Parse JSON request body or fallback to POST form data. Returns (data, error_response)."""
    content_type = request.META.get('CONTENT_TYPE', '') or ''
    raw = request.body.decode('utf-8').strip() if request.body else ''
    if 'application/json' in content_type or raw.startswith(('{', '[')):
        if not raw:
            return {}, None
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None, json_error('Dữ liệu JSON không hợp lệ.', status=400)
        if not isinstance(data, dict):
            return None, json_error('Dữ liệu gửi lên phải là JSON object.', status=400)
        return data, None
    return request.POST, None


def require_auth_json(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_error('Vui lòng đăng nhập để thực hiện thao tác này.', status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped


def require_staff_json(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_error('Vui lòng đăng nhập để tiếp tục.', status=401)
        if not is_staff_or_admin(request.user):
            return json_error('Bạn không có quyền thực hiện thao tác này.', status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


def require_admin_json(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_error('Vui lòng đăng nhập để tiếp tục.', status=401)
        if not is_admin(request.user):
            return json_error('Chỉ Quản trị viên mới có quyền thực hiện.', status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped

