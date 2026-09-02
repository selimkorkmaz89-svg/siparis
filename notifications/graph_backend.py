"""Sends email via Microsoft Graph (application permissions), not SMTP.

Office 365 tenants that enforce Security Defaults reject basic SMTP AUTH
(smtp.office365.com:587) with "535 5.7.139 Authentication unsuccessful" -
that policy should not be weakened just to keep SMTP working. This backend
instead authenticates as an Azure AD app registration (client credentials
grant, `Mail.Send` application permission with admin consent) and calls
``POST /v1.0/users/{sender}/sendMail`` directly.

Usable two ways, both supported here:
  - As the project-wide ``EMAIL_BACKEND``, reading MS_GRAPH_TENANT_ID /
    MS_GRAPH_CLIENT_ID / MS_GRAPH_CLIENT_SECRET / DEFAULT_FROM_EMAIL from
    the environment (see config/settings.py).
  - As the backend behind ``EmailSettings`` (System Settings screen), with
    its own tenant/client id/secret/sender stored in the database - see
    ``EmailSettings.get_connection()``.
"""
from __future__ import annotations

import base64
import logging
import threading
import time
from email.mime.base import MIMEBase
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"

# Access tokens are valid for ~1 hour; cached across backend instances (each
# ``send_mail()``/``EmailMessage.send()`` call can build a fresh one) so a
# burst of notifications does not re-authenticate for every message.
_token_cache: dict[tuple[str, str], tuple[str, float]] = {}
_token_lock = threading.Lock()


class GraphAPIError(Exception):
    """Microsoft Graph (or the token endpoint) returned an error response."""


def _fetch_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    key = (tenant_id, client_id)
    now = time.monotonic()
    with _token_lock:
        cached = _token_cache.get(key)
        if cached and cached[1] > now:
            return cached[0]
    response = requests.post(
        TOKEN_URL.format(tenant_id=tenant_id),
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": GRAPH_SCOPE,
        },
        timeout=15,
    )
    if response.status_code >= 400:
        raise GraphAPIError(
            f"Azure AD token request failed ({response.status_code}): {response.text[:500]}"
        )
    payload = response.json()
    token = payload["access_token"]
    # Refresh a minute early so a send never starts on a token about to expire.
    expiry = now + max(int(payload.get("expires_in", 3600)) - 60, 0)
    with _token_lock:
        _token_cache[key] = (token, expiry)
    return token


class GraphEmailBackend(BaseEmailBackend):
    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        sender_email: str | None = None,
        fail_silently: bool = False,
        **kwargs,
    ):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.tenant_id = tenant_id or getattr(settings, "MS_GRAPH_TENANT_ID", "")
        self.client_id = client_id or getattr(settings, "MS_GRAPH_CLIENT_ID", "")
        self.client_secret = client_secret or getattr(settings, "MS_GRAPH_CLIENT_SECRET", "")
        # Graph's sendMail URL takes a bare mailbox address, not "Name <addr>".
        self.sender_email = parseaddr(sender_email or settings.DEFAULT_FROM_EMAIL)[1]
        self._access_token: str | None = None

    def open(self) -> bool:
        if self._access_token:
            return False
        if not (self.tenant_id and self.client_id and self.client_secret and self.sender_email):
            if not self.fail_silently:
                raise ImproperlyConfigured(
                    _("Microsoft Graph needs a tenant ID, client ID, client secret and sender mailbox.")
                )
            return False
        try:
            self._access_token = _fetch_token(self.tenant_id, self.client_id, self.client_secret)
        except Exception:
            logger.exception("Could not obtain a Microsoft Graph access token")
            if not self.fail_silently:
                raise
            return False
        return True

    def close(self) -> None:
        self._access_token = None

    def send_messages(self, email_messages) -> int:
        if not email_messages:
            return 0
        opened = self.open()
        if not self._access_token:
            return 0
        sent = 0
        try:
            for message in email_messages:
                try:
                    self._send_one(message)
                    sent += 1
                except Exception:
                    logger.exception("Microsoft Graph could not send one message")
                    if not self.fail_silently:
                        raise
        finally:
            if opened:
                self.close()
        return sent

    def _send_one(self, message) -> None:
        response = requests.post(
            SEND_MAIL_URL.format(sender=self.sender_email),
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            json=self._payload(message),
            timeout=30,
        )
        if response.status_code >= 400:
            raise GraphAPIError(
                f"Microsoft Graph sendMail failed ({response.status_code}): {response.text[:500]}"
            )

    def _payload(self, message) -> dict:
        html_body = None
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                html_body = content
                break
        graph_message = {
            "subject": message.subject,
            "body": {
                "contentType": "HTML" if html_body else "Text",
                "content": html_body or message.body,
            },
            "toRecipients": self._recipients(message.to),
        }
        if message.cc:
            graph_message["ccRecipients"] = self._recipients(message.cc)
        if message.bcc:
            graph_message["bccRecipients"] = self._recipients(message.bcc)
        if message.reply_to:
            graph_message["replyTo"] = self._recipients(message.reply_to)
        attachments = self._attachments(message)
        if attachments:
            graph_message["attachments"] = attachments
        return {"message": graph_message, "saveToSentItems": "false"}

    @staticmethod
    def _recipients(addresses) -> list[dict]:
        recipients = []
        for address in addresses:
            name, email_address = parseaddr(address)
            entry = {"emailAddress": {"address": email_address}}
            if name:
                entry["emailAddress"]["name"] = name
            recipients.append(entry)
        return recipients

    @staticmethod
    def _attachments(message) -> list[dict]:
        result = []
        for attachment in getattr(message, "attachments", []):
            if isinstance(attachment, MIMEBase):
                filename = attachment.get_filename() or "attachment"
                content = attachment.get_payload(decode=True) or b""
                mimetype = attachment.get_content_type()
            else:
                filename, content, mimetype = attachment
                if isinstance(content, str):
                    content = content.encode("utf-8")
            result.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentType": mimetype or "application/octet-stream",
                "contentBytes": base64.b64encode(content).decode("ascii"),
            })
        return result
