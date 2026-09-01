from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from core.constants import UserStatus

UserModel = get_user_model()


class EmailBackend(ModelBackend):
    """Authenticate by email and refuse users that are not approved yet."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (username or kwargs.get("email") or "").strip().lower()
        if not email or password is None:
            return None
        try:
            user = UserModel.objects.get(email=email)
        except UserModel.DoesNotExist:
            UserModel().set_password(password)  # equalise timing
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def user_can_authenticate(self, user) -> bool:
        if not super().user_can_authenticate(user):
            return False
        return user.is_superuser or user.status == UserStatus.APPROVED
