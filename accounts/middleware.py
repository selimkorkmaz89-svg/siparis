from django.utils import translation


class UserLanguageMiddleware:
    """Activate the language stored on the user's profile.

    ``LocaleMiddleware`` has already picked a language from the cookie or the
    ``Accept-Language`` header; for authenticated users the profile preference
    wins so the interface follows them across devices.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False) and user.language:
            if translation.get_language() != user.language:
                translation.activate(user.language)
                request.LANGUAGE_CODE = user.language
        return self.get_response(request)
