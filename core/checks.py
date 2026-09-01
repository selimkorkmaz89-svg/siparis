"""Startup checks that turn confusing configuration into a readable message."""
import sys

from django.conf import settings
from django.core.checks import Warning, register


@register()
def local_server_uses_production_settings(app_configs, **kwargs):
    """Warn when ``runserver`` is started with a production configuration.

    Copying ``.env.example`` to ``.env`` for local work switches the project to
    Postgres, a public host name and the HTTPS redirect, which surfaces as an
    unrelated-looking connection error or an endless redirect. Say so plainly.
    """
    if "runserver" not in sys.argv or settings.DEBUG:
        return []
    return [
        Warning(
            "runserver is running with DEBUG=False (production settings).",
            hint=(
                "Local development needs no .env file: without one the project "
                "uses SQLite and plain HTTP. If you copied .env.example, delete "
                "the .env file (it is meant for the Docker/server setup), or set "
                "DEBUG=True and USE_SQLITE=True in it."
            ),
            id="core.W001",
        )
    ]
