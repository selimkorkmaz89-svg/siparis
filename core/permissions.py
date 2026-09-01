"""Role based access helpers for class based views."""
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied

from core.constants import Role


class RoleRequiredMixin(AccessMixin):
    """Allow access only to the roles listed in ``allowed_roles``.

    ``Role.ADMIN`` is always allowed: the admin inherits every other role's
    permissions per the specification.
    """

    allowed_roles: tuple = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.has_role(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def has_role(self, user) -> bool:
        if user.role == Role.ADMIN:
            return True
        return user.role in self.allowed_roles


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.ADMIN,)


class FinanceRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.FINANCE,)


class LogisticsRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.LOGISTICS,)


class DealerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.DEALER,)


class OrderViewerMixin(RoleRequiredMixin):
    """Everybody may reach order listings; the queryset is scoped per role."""

    allowed_roles = (Role.FINANCE, Role.LOGISTICS, Role.MANAGEMENT, Role.DEALER)


class StaffOrderViewerMixin(RoleRequiredMixin):
    """Roles that may see every dealer's orders."""

    allowed_roles = (Role.FINANCE, Role.LOGISTICS, Role.MANAGEMENT)
