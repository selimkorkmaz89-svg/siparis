"""Builds the SiparisKaydetV2 payload for a paid order and tracks sync state.

This app never talks to Mikro directly: Mikro's API only listens on the
private network its virtual server sits on (reached by this company's staff
over VPN), while this system runs outside it. Instead, a small relay script
running inside that network polls the endpoints in ``integrations/views.py``
for ready-to-send payloads and posts them to Mikro itself, then reports back
whether each one succeeded.

The exact request shape and the password hashing rule below come from
Mikro's own OpenAPI description for ``POST /Api/apiMethods/SiparisKaydetV2``
and ``POST /Api/APIMethods/APILogin`` (2025 edition) - not guessed.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from core.constants import MikroSyncStatus, PaymentStatus
from integrations.models import MikroSettings, VatRateMapping
from orders.models import Order
from payments import services as fx

logger = logging.getLogger(__name__)


class MikroPayloadError(Exception):
    """The order cannot be turned into a valid Mikro payload yet."""


def hash_sifre(raw_password: str, when: date | None = None) -> str:
    """Mikro's daily-rotating password hash: MD5("YYYY-MM-DD " + password).

    Confirmed from Mikro's own API docs (APILogin / SiparisKaydetV2 examples):
    "(MD5 Formatında Günün tarihi + Boşluk + Şifre ile hashli) Şifreniz
    hergün Günün tarihi ile birlikte yeniden hashlenmelidir." Must be
    recomputed for "today" at the moment of the actual request to Mikro, not
    cached - which is why this stays unhashed in MikroSettings.sifre and is
    only hashed here, at payload-build time.
    """
    when = when or timezone.localdate()
    raw = f"{when.isoformat()} {raw_password}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _amount_for(item, currency: str, rate: Decimal | None) -> tuple[Decimal, Decimal]:
    """(unit price, line total) for one order item, in ``currency``."""
    if currency == "TRY":
        if not rate:
            raise MikroPayloadError(
                _("No exchange rate is on record for this order's approved payment.")
            )
        return (
            fx.usd_to_try(item.unit_price_usd, rate),
            fx.usd_to_try(item.line_total_usd, rate),
        )
    return item.unit_price_usd, item.line_total_usd


def build_siparis_payload(order: Order) -> dict:
    """The full ``{"Mikro": {...}}`` body for one order's SiparisKaydetV2 call.

    Raises ``MikroPayloadError`` with a human-readable reason when the order,
    its dealer or one of its products is missing a piece of Mikro-side setup
    (customer code, stock code, VAT pointer) - the caller is expected to
    store that message on ``Order.mikro_sync_error`` rather than let it
    surface as a crash.
    """
    settings_ = MikroSettings.load()
    if not settings_.enabled:
        raise MikroPayloadError(_("The Mikro integration is currently disabled."))

    dealer = order.dealer
    if not dealer.mikro_cari_kodu:
        raise MikroPayloadError(
            _('Dealer "%(dealer)s" has no Mikro customer code assigned.')
            % {"dealer": dealer.name}
        )

    rate = None
    if settings_.para_birimi == "TRY":
        payment = (
            order.payments.filter(status=PaymentStatus.APPROVED)
            .order_by("-created_at")
            .first()
        )
        rate = payment.exchange_rate if payment else None

    vat_pointers = {
        row.vat_rate: row.mikro_vergi_pntr for row in VatRateMapping.objects.all()
    }

    satirlar = []
    for item in order.items.select_related("product").all():
        if not item.product.mikro_stok_kodu:
            raise MikroPayloadError(
                _('Product "%(code)s" has no Mikro stock code assigned.')
                % {"code": item.product_code}
            )
        vergi_pntr = vat_pointers.get(item.vat_rate)
        if vergi_pntr is None:
            raise MikroPayloadError(
                _("No Mikro VAT pointer is mapped for the %(rate)s%% VAT rate.")
                % {"rate": item.vat_rate}
            )
        unit_price, line_total = _amount_for(item, settings_.para_birimi, rate)
        satirlar.append({
            "seriler": "",
            "sip_b_fiyat": float(unit_price),
            "sip_birim_pntr": settings_.birim_pntr,
            "sip_cins": settings_.sip_cins,
            "sip_depono": settings_.depo_no,
            "sip_evrakno_seri": settings_.evrak_seri,
            "sip_miktar": item.quantity,
            "sip_musteri_kod": dealer.mikro_cari_kodu,
            "sip_stok_kod": item.product.mikro_stok_kodu,
            "sip_stok_sormerk": "",
            "sip_tarih": (order.paid_at or timezone.now()).strftime("%d.%m.%Y"),
            "sip_tip": settings_.sip_tip,
            "sip_tutar": float(line_total),
            "sip_vergi_pntr": vergi_pntr,
            "sip_vergisiz_fl": int(settings_.vergisiz_fl),
            "user_tablo": [],
            "varyant": [],
        })

    aciklamalar = [order.order_no or order.reference]
    if order.note:
        aciklamalar.append(order.note)

    return {
        "Mikro": {
            "ApiKey": settings_.api_key,
            "CalismaYili": settings_.calisma_yili,
            "FirmaKodu": settings_.firma_kodu,
            "KullaniciKodu": settings_.kullanici_kodu,
            "Sifre": hash_sifre(settings_.sifre),
            "evraklar": [
                {
                    "evrak_aciklamalari": [{"aciklama": text} for text in aciklamalar],
                    "satirlar": satirlar,
                }
            ],
        }
    }


def queue_for_sync(order: Order) -> None:
    """Mark a freshly paid order for the connector to pick up.

    Safe to call even when the integration is off or unconfigured - the
    order simply stays ``NOT_QUEUED``. Never raises: a Mikro setup problem
    must not get in the way of approving a payment.
    """
    try:
        if not MikroSettings.load().enabled:
            return
        order.mikro_sync_status = MikroSyncStatus.PENDING
        order.mikro_sync_error = ""
        order.save(update_fields=["mikro_sync_status", "mikro_sync_error"])
    except Exception:
        logger.exception("Could not queue order %s for Mikro sync", order.pk)


def pending_payloads(limit: int = 50) -> list[dict]:
    """Payloads for the connector's next poll.

    An order whose payload cannot be built yet (missing mapping) is flipped
    straight to FAILED with the reason, instead of being handed to the
    connector - so the queue keeps flowing and the problem shows up on the
    sync status screen for someone to fix.
    """
    orders = (
        Order.objects.filter(mikro_sync_status=MikroSyncStatus.PENDING)
        .select_related("dealer")
        .prefetch_related("items__product", "payments")
        .order_by("paid_at")[:limit]
    )
    results = []
    for order in orders:
        try:
            payload = build_siparis_payload(order)
        except MikroPayloadError as exc:
            mark_failed(order, str(exc))
            continue
        results.append({"order_id": order.pk, "order_no": order.order_no, "payload": payload})
    return results


def mark_synced(order: Order, reference: str = "") -> None:
    order.mikro_sync_status = MikroSyncStatus.SYNCED
    order.mikro_synced_at = timezone.now()
    order.mikro_reference = reference[:120]
    order.mikro_sync_error = ""
    order.save(
        update_fields=[
            "mikro_sync_status", "mikro_synced_at", "mikro_reference", "mikro_sync_error",
        ]
    )


def mark_failed(order: Order, error: str) -> None:
    order.mikro_sync_status = MikroSyncStatus.FAILED
    order.mikro_sync_error = error[:4000]
    order.save(update_fields=["mikro_sync_status", "mikro_sync_error"])
