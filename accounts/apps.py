from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = 'MOD-05: Quản lý Tài khoản & Khách hàng'

    def ready(self):
        try:
            import accounts.signals  # noqa: F401
        except ImportError:
            pass
