"""Exchange rate rules and payment approval helpers."""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import requests
from django.conf import settings
from django.utils import timezone

from payments.models import ExchangeRate

logger = logging.getLogger(__name__)

#: How far back to look when a business day's rate is missing.
MAX_LOOKBACK_DAYS = 15


def effective_rate_date(moment: dt.datetime | None = None) -> dt.date:
    """Return the date whose TCMB rate applies at ``moment``.

    TCMB publishes at 15:30 local time, so anything earlier in the day falls
    back to the previous day. Weekends and public holidays have no publication
    at all; :func:`get_rate` then walks further back to the nearest business day.
    """
    moment = timezone.localtime(moment or timezone.now())
    cutoff = moment.replace(
        hour=settings.TCMB_RATE_PUBLISH_HOUR,
        minute=settings.TCMB_RATE_PUBLISH_MINUTE,
        second=0,
        microsecond=0,
    )
    date = moment.date()
    if moment < cutoff:
        date -= dt.timedelta(days=1)
    return date


def get_rate(moment: dt.datetime | None = None) -> ExchangeRate | None:
    """Latest stored rate that is valid at ``moment``.

    Walks backwards day by day, which covers weekends and holidays alike
    (Saturday/Sunday → Friday's rate).
    """
    target = effective_rate_date(moment)
    earliest = target - dt.timedelta(days=MAX_LOOKBACK_DAYS)
    return (
        ExchangeRate.objects.filter(rate_date__lte=target, rate_date__gte=earliest)
        .order_by("-rate_date")
        .first()
    )


def current_rate_value(moment: dt.datetime | None = None) -> Decimal | None:
    rate = get_rate(moment)
    return rate.usd_try_rate if rate else None


def try_to_usd(amount_try: Decimal, rate: Decimal) -> Decimal:
    if not rate:
        return Decimal("0.00")
    return (Decimal(amount_try) / Decimal(rate)).quantize(Decimal("0.01"))


def usd_to_try(amount_usd: Decimal, rate: Decimal) -> Decimal:
    if not rate:
        return Decimal("0.00")
    return (Decimal(amount_usd) * Decimal(rate)).quantize(Decimal("0.01"))


def _parse_tcmb_xml(payload: bytes, currency_code: str = "USD") -> Decimal | None:
    """Pull one currency's effective selling rate out of a TCMB daily XML document."""
    root = ElementTree.fromstring(payload)
    for currency in root.findall("Currency"):
        if currency.get("CurrencyCode") != currency_code:
            continue
        for tag in ("BanknoteSelling", "ForexSelling"):
            node = currency.find(tag)
            if node is not None and (node.text or "").strip():
                try:
                    return Decimal(node.text.strip())
                except InvalidOperation:
                    continue
    return None


def fetch_tcmb_rate(date: dt.date | None = None) -> ExchangeRate | None:
    """Fetch and store the TCMB USD and CHF rates for ``date`` (today's file when omitted).

    A missing CHF figure never blocks the USD rate from being stored - CHF
    only feeds the small reprice step for Swiss-Franc list prices, USD/TRY is
    what the rest of the app depends on.
    """
    date = date or timezone.localdate()
    urls = [settings.TCMB_TODAY_URL] if date == timezone.localdate() else []
    urls.append(
        settings.TCMB_ARCHIVE_URL.format(
            yyyymm=date.strftime("%Y%m"), ddmmyyyy=date.strftime("%d%m%Y")
        )
    )
    for url in urls:
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("TCMB request failed (%s): %s", url, exc)
            continue
        try:
            usd_value = _parse_tcmb_xml(response.content, "USD")
            chf_value = _parse_tcmb_xml(response.content, "CHF")
        except ElementTree.ParseError as exc:
            logger.warning("TCMB response could not be parsed (%s): %s", url, exc)
            continue
        if usd_value is None:
            continue
        defaults = {"usd_try_rate": usd_value, "rate_type": "efektif satış", "source": "TCMB"}
        if chf_value is not None:
            defaults["chf_try_rate"] = chf_value
        rate, _created = ExchangeRate.objects.update_or_create(
            rate_date=date, defaults=defaults,
        )
        logger.info("TCMB rate stored: %s = %s (CHF %s)", date, usd_value, chf_value)
        reprice_chf_products(rate)
        return rate
    logger.warning("No TCMB rate available for %s (weekend or holiday?)", date)
    return None


def reprice_chf_products(rate: ExchangeRate) -> None:
    if not rate.chf_to_usd_rate:
        return
    from catalog.services import reprice_foreign_currency_products
    from core.constants import Currency

    try:
        reprice_foreign_currency_products(Currency.CHF, rate.chf_to_usd_rate)
    except Exception:
        logger.exception("Could not reprice CHF-listed products")


#: Placeholder rows a real fetch is allowed to overwrite. A MANUAL row is a
#: deliberate correction by an administrator and is never replaced on its own;
#: a DEMO row comes from ``seed_demo`` and must not shadow the live rate.
REPLACEABLE_SOURCES = {"DEMO"}


def backfill_rates(days: int = 10, force: bool = False) -> int:
    """Fetch the rates missing from the last ``days`` days.

    A date that only holds a placeholder row is fetched again, otherwise demo
    data seeded for today would permanently hide the real TCMB rate.
    """
    today = timezone.localdate()
    stored = 0
    for offset in range(days):
        date = today - dt.timedelta(days=offset)
        existing = ExchangeRate.objects.filter(rate_date=date).first()
        if existing and not force and existing.source not in REPLACEABLE_SOURCES:
            continue
        if fetch_tcmb_rate(date):
            stored += 1
    return stored
