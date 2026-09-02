from decimal import Decimal

from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from core.constants import Currency, Role
from core.decorators import role_required
from core.exports import excel_response
from core.filters import parse_date
from dealers.models import Dealer
from payments import services as fx
from reports import services


def _scope(request):
    """Dealer users only ever see their own dealer's numbers."""
    if request.user.can_see_all_dealers:
        dealer_id = request.GET.get("dealer") or ""
        dealer = Dealer.objects.filter(pk=dealer_id).first() if dealer_id else None
        return dealer, True
    return request.user.dealer, False


def _common_context(request):
    date_from = parse_date(request.GET.get("date_from"))
    date_to = parse_date(request.GET.get("date_to"))
    dealer, can_choose_dealer = _scope(request)
    currency = request.GET.get("currency") or Currency.USD
    if currency not in Currency.values:
        currency = Currency.USD
    rate = fx.current_rate_value()
    return {
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "_date_from": date_from,
        "_date_to": date_to,
        "dealer": dealer,
        "dealers": Dealer.objects.filter(is_active=True) if can_choose_dealer else [],
        "can_choose_dealer": can_choose_dealer,
        "currency": currency,
        # Reporting screens convert with the live rate, independent of the
        # rate frozen on any individual payment.
        "exchange_rate": rate,
        "conversion_factor": float(rate) if (rate and currency == Currency.TRY) else 1.0,
        "filters_active": bool(date_from or date_to or request.GET.get("dealer")),
    }


def _convert(value, factor) -> Decimal:
    return (Decimal(value or 0) * Decimal(str(factor))).quantize(Decimal("0.01"))


@role_required(Role.FINANCE, Role.MANAGEMENT, Role.DEALER)
def dashboard(request):
    """Main reporting screen: dealer, product, brand and trend breakdowns.

    One screen for everyone; the queryset is scoped by role, so a dealer sees
    only its own figures and the menu simply labels it "My reports".
    """
    context = _common_context(request)
    orders = services.base_orders(context["_date_from"], context["_date_to"], context["dealer"])
    factor = context["conversion_factor"]
    dealers = services.dealer_breakdown(orders)
    products = services.product_breakdown(orders)
    brands = services.brand_breakdown(orders)
    trend = services.monthly_trend(orders)
    summary = services.totals(orders)

    if request.GET.get("export") == "excel":
        return excel_response(
            "report-dealers",
            str(_("Dealer report")),
            [_("Dealer"), _("Order count"), _("Total"), _("Average order size")],
            [
                (row["dealer__name"], row["count"], _convert(row["total"], factor),
                 _convert(row["average"], factor))
                for row in dealers
            ],
        )

    context.update(
        {
            "summary": {
                "count": summary["count"],
                "total": _convert(summary["total"], factor),
                "subtotal": _convert(summary["subtotal"], factor),
                "vat": _convert(summary["vat"], factor),
                "average": _convert(summary["average"], factor),
            },
            "dealer_rows": [
                {
                    "id": row["dealer__id"],
                    "name": row["dealer__name"],
                    "count": row["count"],
                    "total": _convert(row["total"], factor),
                    "average": _convert(row["average"], factor),
                }
                for row in dealers
            ],
            "product_rows": [
                {
                    "code": row["product_code"],
                    "name": row["product_name"],
                    "quantity": row["quantity"],
                    "total": _convert(row["total"], factor),
                }
                for row in products
            ],
            "brand_rows": [
                {
                    "brand": row["brand"],
                    "quantity": row["quantity"],
                    "total": _convert(row["total"], factor),
                }
                for row in brands
            ],
            "trend_rows": [
                {
                    "month": row["month"].strftime("%Y-%m") if row["month"] else "",
                    "count": row["count"],
                    "total": _convert(row["total"], factor),
                }
                for row in trend
            ],
        }
    )
    context["chart_data"] = {
        "dealers": {
            "labels": [row["name"] for row in context["dealer_rows"][:10]],
            "values": [float(row["total"]) for row in context["dealer_rows"][:10]],
        },
        "products": {
            "labels": [row["code"] for row in context["product_rows"][:10]],
            "values": [float(row["total"]) for row in context["product_rows"][:10]],
        },
        "brands": {
            "labels": [row["brand"] for row in context["brand_rows"][:10]],
            "values": [float(row["total"]) for row in context["brand_rows"][:10]],
        },
        "trend": {
            "labels": [row["month"] for row in context["trend_rows"]],
            "values": [float(row["total"]) for row in context["trend_rows"]],
        },
    }
    return render(request, "reports/dashboard.html", context)


@role_required(Role.FINANCE, Role.MANAGEMENT)
def finance_report(request):
    context = _common_context(request)
    factor = context["conversion_factor"]
    summary = services.finance_summary(
        context["_date_from"], context["_date_to"], context["dealer"]
    )
    operations = services.operations_summary(
        context["_date_from"], context["_date_to"], context["dealer"]
    )
    if request.GET.get("export") == "excel":
        return excel_response(
            "report-finance",
            str(_("Finance report")),
            [_("Metric"), _("Value")],
            [
                (_("Collected (TRY)"), summary["collected"]["total_try"]),
                (_("Collected (USD)"), summary["collected"]["total_usd"]),
                (_("Approved payment count"), summary["collected"]["count"]),
                (_("Outstanding payments (USD)"), summary["outstanding"]["total_usd"]),
                (_("Orders awaiting payment"), summary["outstanding"]["count"]),
                (_("Rejection rate (%)"), summary["rejection_rate"]),
                (_("Average hours to payment"), operations["avg_hours_to_payment"]),
                (_("Average hours to shipment"), operations["avg_hours_to_shipment"]),
                (_("Average hours end to end"), operations["avg_hours_end_to_end"]),
            ],
        )
    context.update(
        {
            "summary": summary,
            "operations": operations,
            "outstanding_converted": _convert(summary["outstanding"]["total_usd"], factor),
            "collected_converted": _convert(summary["collected"]["total_usd"], factor),
        }
    )
    return render(request, "reports/finance.html", context)
