from django.conf import settings

from core.constants import Role


def site_context(request):
    user = getattr(request, "user", None)
    role = getattr(user, "role", None) if getattr(user, "is_authenticated", False) else None
    return {
        "COMPANY_NAME": settings.COMPANY_NAME,
        "COMPANY_LOGO": settings.COMPANY_LOGO,
        "BRAND_COLOR": settings.BRAND_COLOR,
        "current_role": role,
        "Role": Role,
    }
