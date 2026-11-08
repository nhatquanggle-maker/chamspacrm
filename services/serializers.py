"""
Serializers cho Phân hệ Quản lý Danh mục & Dịch vụ (MOD-03) - CHAMSPA CRM
Tác giả: Minh Khánh
Use Cases:
  - UC-3.1: Xem danh sách dịch vụ (lọc, tìm kiếm, phân trang, sắp xếp)
  - UC-3.2: Xem chi tiết dịch vụ (gallery ảnh, quy trình trải nghiệm, đánh giá thực tế)
  - UC-3.3: Quản lý danh mục & dịch vụ (CRUD, đổi giá, đổi ảnh, ẩn/hiện dịch vụ)
Tuân thủ chuẩn RESTful API, khớp 100% Hợp đồng API (Sheet 5) và Thiết kế Figma (Node 216-928, Node 216-929).
"""

from rest_framework import serializers
from django.utils.text import slugify
from core.models import Category, Service, ServiceImage, Feedback


class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer hiển thị thông tin danh mục dịch vụ (Category)
    Kèm tổng số dịch vụ đang hoạt động trong danh mục đó.
    """
    services_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'status', 'services_count', 'created_at', 'updated_at']

    def get_services_count(self, obj):
        return obj.services.filter(status='Hoạt động').count()


class ServiceImageSerializer(serializers.ModelSerializer):
    """
    Serializer cho bộ sưu tập ảnh (Gallery) của từng dịch vụ
    """
    class Meta:
        model = ServiceImage
        fields = ['id', 'image_url', 'created_at']


class ServiceFeedbackSerializer(serializers.ModelSerializer):
    """
    Serializer hiển thị đánh giá của khách hàng cho dịch vụ (UC-3.2)
    Lấy từ bảng Feedback thông qua các lịch hẹn hoàn tất có chứa dịch vụ này.
    """
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    customer_avatar = serializers.SerializerMethodField()
    date_formatted = serializers.SerializerMethodField()

    class Meta:
        model = Feedback
        fields = [
            'id', 'feedback_code', 'customer_name', 'customer_avatar',
            'rating', 'tags', 'comment', 'attached_media',
            'reply', 'replied_by', 'replied_at', 'date_formatted', 'created_at'
        ]

    def get_customer_avatar(self, obj):
        if hasattr(obj.customer, 'profile') and obj.customer.profile.avatar:
            avatar = obj.customer.profile.avatar
            if hasattr(avatar, 'url'):
                return avatar.url
            return str(avatar)
        return '/static/images/chamspa-logo.png'

    def get_date_formatted(self, obj):
        if obj.created_at:
            return obj.created_at.strftime('%d/%m/%Y')
        return ''


class ServiceListSerializer(serializers.ModelSerializer):
    """
    Serializer hiển thị danh sách thẻ dịch vụ (Service Card) dạng Grid (UC-3.1)
    Khớp 100% Figma Node 216-928:
      - Mã định danh dịch vụ: code (#DVO01, #DVO02...)
      - Ảnh đại diện: thumbnail_url
      - Tên dịch vụ: name
      - Danh mục phân loại: category (object gồm id, name, slug)
      - Giá tiền định dạng VNĐ: price_vnd & formatted_price
      - Thời lượng: duration_minutes (ví dụ 60 phút)
      - Đánh giá sao trung bình & Lượt review: rating_avg (4.9), review_count (128)
      - Trạng thái hiển thị: status ('Hoạt động', 'Ngừng hoạt động')
    """
    code = serializers.SerializerMethodField()
    formatted_price = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    updated_date_formatted = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            'id', 'code', 'name', 'slug', 'category', 'category_name',
            'thumbnail_url', 'description', 'price_vnd', 'formatted_price',
            'duration_minutes', 'status', 'rating_avg', 'review_count',
            'updated_date_formatted', 'created_at', 'updated_at'
        ]

    def get_code(self, obj):
        return f"#DVO{obj.id:02d}"

    def get_formatted_price(self, obj):
        try:
            return f"{int(obj.price_vnd):,}".replace(',', '.') + " VNĐ"
        except (ValueError, TypeError):
            return "0 VNĐ"

    def get_updated_date_formatted(self, obj):
        if obj.updated_at:
            return obj.updated_at.strftime('%d/%m/%Y')
        elif obj.created_at:
            return obj.created_at.strftime('%d/%m/%Y')
        return ''


class ServiceDetailSerializer(serializers.ModelSerializer):
    """
    Serializer chi tiết dịch vụ chuyên sâu (UC-3.2)
    Khớp 100% Figma Node 216-929:
      - Gallery ảnh: mảng images (chuỗi URL)
      - Quy trình trải nghiệm 4 bước chuẩn Champa Wellness
      - Danh sách nhận xét thực tế từ khách hàng (feedbacks)
    """
    code = serializers.SerializerMethodField()
    formatted_price = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    images = serializers.SerializerMethodField()
    feedbacks = serializers.SerializerMethodField()
    process_steps = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            'id', 'code', 'name', 'slug', 'category', 'category_name',
            'thumbnail_url', 'description', 'price_vnd', 'formatted_price',
            'duration_minutes', 'status', 'rating_avg', 'review_count',
            'images', 'feedbacks', 'process_steps', 'created_at', 'updated_at'
        ]

    def get_code(self, obj):
        return f"#DVO{obj.id:02d}"

    def get_formatted_price(self, obj):
        try:
            return f"{int(obj.price_vnd):,}".replace(',', '.') + " VNĐ"
        except (ValueError, TypeError):
            return "0 VNĐ"

    def get_images(self, obj):
        """Trả về mảng chuỗi URL hình ảnh trong gallery"""
        urls = list(obj.images.values_list('image_url', flat=True))
        if not urls and obj.thumbnail_url:
            urls = [obj.thumbnail_url]
        return urls

    def get_feedbacks(self, obj):
        """Truy vấn các đánh giá đã duyệt hoặc đã phản hồi từ khách hàng"""
        # Feedback liên kết với Appointment -> AppointmentDetail -> Service
        feedbacks = Feedback.objects.filter(
            appointment__details__service=obj
        ).exclude(status='Đã ẩn').select_related('customer').order_by('-created_at')[:10]
        return ServiceFeedbackSerializer(feedbacks, many=True).data

    def get_process_steps(self, obj):
        """
        Quy trình trải nghiệm 4 bước chuẩn Champa Wellness khớp Figma Node 216-929:
        1. Thăm vấn
        2. Khởi động
        3. Ấn huyệt trị liệu
        4. Đá nóng Champa / Thảo dược bí truyền
        """
        return [
            {
                "step": 1,
                "title": "Thăm vấn",
                "icon": "bi-chat-heart",
                "description": "Chuyên viên lắng nghe tình trạng cơ thể, xác định điểm căng cơ và mức áp lực phù hợp theo thể trạng riêng của quý khách."
            },
            {
                "step": 2,
                "title": "Khởi động",
                "icon": "bi-flower1",
                "description": "Thưởng thức trà thảo mộc ấm, ngâm chân muối khoáng thảo dược cổ truyền người Dao Đỏ và làm ấm cơ thể trong không gian thư thái."
            },
            {
                "step": 3,
                "title": "Ấn huyệt trị liệu",
                "icon": "bi-hand-index-thumb",
                "description": f"Áp dụng kỹ thuật bấm huyệt Đông y Champa chuyên sâu cho gói {obj.name}, giải phóng ứ trệ và đả thông kinh lạc toàn thân."
            },
            {
                "step": 4,
                "title": "Đá nóng Champa",
                "icon": "bi-gem",
                "description": "Sử dụng đá bazan núi lửa tự nhiên hấp nóng kết hợp tinh dầu trầm hương Cham Spa giúp thẩm thấu dưỡng chất và đưa cơ thể vào trạng thái thư giãn sâu."
            }
        ]


class AdminServiceWriteSerializer(serializers.ModelSerializer):
    """
    Serializer phục vụ thêm mới hoặc cập nhật Dịch vụ từ trang Quản trị (UC-3.3)
    Kiểm tra tính hợp lệ của dữ liệu đầu vào:
      - Giá tiền phải là số dương (> 0)
      - Thời lượng phải > 0
      - Tên không được để trống
      - Tự động tạo slug nếu chưa có
      - Hỗ trợ cập nhật mảng ảnh gallery
    """
    category_id = serializers.IntegerField(write_only=True, required=False)
    gallery_urls = serializers.ListField(
        child=serializers.CharField(max_length=500),
        required=False,
        write_only=True
    )

    class Meta:
        model = Service
        fields = [
            'id', 'category_id', 'name', 'slug', 'thumbnail_url',
            'description', 'price_vnd', 'duration_minutes', 'status',
            'gallery_urls'
        ]
        extra_kwargs = {
            'name': {'required': False},
            'slug': {'required': False},
            'thumbnail_url': {'required': False, 'allow_null': True, 'allow_blank': True},
            'description': {'required': False, 'allow_null': True, 'allow_blank': True},
            'price_vnd': {'required': False},
            'duration_minutes': {'required': False},
        }

    def validate_category_id(self, value):
        if value is not None and not Category.objects.filter(id=value).exists():
            raise serializers.ValidationError("Danh mục dịch vụ được chọn không tồn tại trên hệ thống.")
        return value

    def validate_price_vnd(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Giá niêm yết dịch vụ phải là số nguyên dương lớn hơn 0.")
        return value

    def validate_duration_minutes(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Thời lượng liệu trình phải lớn hơn 0 phút.")
        return value

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)

        # Nếu tạo mới, bắt buộc phải có name và category_id
        if not instance:
            if not attrs.get('name', '').strip():
                raise serializers.ValidationError({"name": "Tên dịch vụ là trường bắt buộc khi tạo mới."})
            if 'category_id' not in attrs:
                raise serializers.ValidationError({"category_id": "Vui lòng chọn danh mục cho dịch vụ."})

        # Nếu có truyền name thì kiểm tra không để trống và kiểm tra trùng lặp (Figma Node 216-2853)
        if 'name' in attrs:
            name = attrs['name'].strip()
            if not name:
                raise serializers.ValidationError({"name": "Tên dịch vụ không được để trống."})

            # Kiểm tra trùng tên dịch vụ (UC-3.4 Exception Flow 4b: Tên dịch vụ đã tồn tại)
            dup_qs = Service.objects.filter(name__iexact=name)
            if instance:
                dup_qs = dup_qs.exclude(id=instance.id)
            if dup_qs.exists():
                existing = dup_qs.first()
                cat_name = existing.category.name if existing.category else "Chung"
                raise serializers.ValidationError({
                    "name": f"Tên dịch vụ '{name}' đã tồn tại trong danh mục '{cat_name}'. Vui lòng chọn tên khác."
                })
            attrs['name'] = name

            # Tự động sinh slug nếu chưa có
            if not attrs.get('slug'):
                slug = slugify(name)
                attrs['slug'] = slug or f"service-{int(attrs.get('price_vnd', 100))}"

        # Kiểm tra trùng slug với bản ghi khác
        if 'slug' in attrs:
            slug = attrs['slug'].strip()
            qs = Service.objects.filter(slug=slug)
            if instance:
                qs = qs.exclude(id=instance.id)
            if qs.exists():
                import random
                attrs['slug'] = f"{slug}-{random.randint(10, 99)}"

        return attrs

    def create(self, validated_data):
        category_id = validated_data.pop('category_id')
        validated_data['category_id'] = category_id
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'category_id' in validated_data:
            instance.category_id = validated_data.pop('category_id')
        return super().update(instance, validated_data)


class AdminCategoryWriteSerializer(serializers.ModelSerializer):
    """
    Serializer phục vụ thêm mới hoặc sửa danh mục (Category) trong Quản trị (UC-3.3)
    """
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'status']
        extra_kwargs = {
            'slug': {'required': False}
        }

    def validate(self, attrs):
        name = attrs.get('name', '').strip()
        if not name:
            raise serializers.ValidationError({"name": "Tên danh mục không được để trống."})
        slug = attrs.get('slug', '').strip()
        if not slug:
            attrs['slug'] = slugify(name)
        return attrs
