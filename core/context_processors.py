from django.conf import settings

from core import navigation
from core.constants import Role


def site_context(request):
    user = getattr(request, "user", None)
    authenticated = getattr(user, "is_authenticated", False)
    match = getattr(request, "resolver_match", None)
    current_url_name = match.view_name if match else ""
    return {
        "COMPANY_NAME": settings.COMPANY_NAME,
        "COMPANY_LOGO": settings.COMPANY_LOGO,
        "BRAND_COLOR": settings.BRAND_COLOR,
        "current_role": user.role if authenticated else None,
        "Role": Role,
        "nav_items": navigation.items_for(user, current_url_name),
        "nav_role_label": navigation.role_label(user),
        "current_url_name": current_url_name,
    }
