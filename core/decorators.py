from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from core.constants import Role


def role_required(*roles, allow_admin: bool = True):
    """Restrict a function based view to the given roles.

    The admin inherits every other role's permissions, so it passes by default.
    Pass ``allow_admin=False`` for a screen that only makes sense for the role
    itself - a dealer's basket needs ``user.dealer``, which an admin lacks.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            allowed = user.role in roles or (allow_admin and user.role == Role.ADMIN)
            if not allowed:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
