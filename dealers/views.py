from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from core.constants import OrderStatus, Role
from core.decorators import role_required
from core.exports import excel_response
from core.filters import ListFilter
from dealers.forms import DealerForm, DomainDealerMapForm
from dealers.models import Dealer, DomainDealerMap
from orders.models import Order


@role_required(Role.ADMIN)
def dealer_list(request):
    queryset = Dealer.objects.annotate(
        order_count=Count("orders", distinct=True),
        user_count=Count("users", distinct=True),
    )
    list_filter = ListFilter(
        request,
        search_fields=("name", "code", "tax_no", "city", "contact_person"),
        ordering_map={
            "name": "name", "code": "code", "city": "city", "orders": "order_count",
            "date": "created_at",
        },
        default_ordering="name",
    )
    queryset = list_filter.apply(queryset)
    if request.GET.get("export") == "excel":
        return excel_response(
            "dealers",
            str(_("Dealers")),
            [_("Dealer name"), _("Dealer code"), _("Tax number"), _("Tax office"),
             _("Contact person"), _("Phone"), _("Email"), _("City"), _("Address"),
             _("Active"), _("Order count")],
            [
                (d.name, d.code, d.tax_no, d.tax_office, d.contact_person, d.phone,
                 d.email, d.city, d.address, _("Yes") if d.is_active else _("No"),
                 d.order_count)
                for d in queryset
            ],
        )
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "dealers/dealer_list.html",
        {"page_obj": page, "dealers": page.object_list, **list_filter.as_context()},
    )


@role_required(Role.ADMIN)
def dealer_form(request, pk=None):
    instance = get_object_or_404(Dealer, pk=pk) if pk else None
    form = DealerForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        dealer = form.save()
        messages.success(request, _("Dealer saved: %(name)s") % {"name": dealer.name})
        return redirect("dealers:list")
    return render(request, "dealers/dealer_form.html", {"form": form, "object": instance})


@role_required(Role.FINANCE, Role.LOGISTICS, Role.MANAGEMENT)
def dealer_history(request, pk=None):
    """Dealer-by-dealer order history for finance, logistics and management."""
    dealers = Dealer.objects.filter(is_active=True).order_by("name")
    dealer = get_object_or_404(Dealer, pk=pk) if pk else dealers.first()
    orders = Order.objects.none()
    totals = {}
    if dealer is not None:
        orders = (
            Order.objects.filter(dealer=dealer)
            .exclude(status=OrderStatus.DRAFT)
            .select_related("created_by")
            .prefetch_related("items")
        )
        list_filter = ListFilter(
            request,
            search_fields=("order_no", "items__product_code", "items__product_name"),
            ordering_map={"order_no": "order_no", "date": "created_at",
                          "total": "total_amount_usd", "status": "status"},
        )
        orders = list_filter.apply(orders).distinct()
        totals = orders.aggregate(total_usd=Sum("total_amount_usd"), count=Count("id"))
        if request.GET.get("export") == "excel":
            return excel_response(
                f"dealer-history-{dealer.name}",
                str(_("Dealer history")),
                [_("Order number"), _("Date"), _("Status"), _("Subtotal (USD)"),
                 _("VAT total (USD)"), _("Grand total (USD)"), _("Created by")],
                [
                    (o.order_no or "-", o.created_at, o.get_status_display(),
                     o.subtotal_usd, o.vat_total_usd, o.total_amount_usd,
                     str(o.created_by))
                    for o in orders
                ],
            )
        context_filter = list_filter.as_context()
    else:
        context_filter = {}
    page = Paginator(orders, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "dealers/dealer_history.html",
        {
            "dealers": dealers,
            "dealer": dealer,
            "page_obj": page,
            "orders": page.object_list,
            "totals": totals,
            **context_filter,
        },
    )


@role_required(Role.ADMIN)
def domain_list(request):
    queryset = DomainDealerMap.objects.select_related("dealer")
    list_filter = ListFilter(
        request,
        search_fields=("email_domain", "dealer__name"),
        ordering_map={"domain": "email_domain", "dealer": "dealer__name"},
        default_ordering="email_domain",
    )
    queryset = list_filter.apply(queryset)
    if request.GET.get("export") == "excel":
        return excel_response(
            "domains",
            str(_("Domain mappings")),
            [_("Email domain"), _("Dealer"), _("Active")],
            [(m.email_domain, m.dealer.name, _("Yes") if m.is_active else _("No"))
             for m in queryset],
        )
    return render(
        request,
        "dealers/domain_list.html",
        {"mappings": queryset, **list_filter.as_context()},
    )


@role_required(Role.ADMIN)
def domain_form(request, pk=None):
    instance = get_object_or_404(DomainDealerMap, pk=pk) if pk else None
    form = DomainDealerMapForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        mapping = form.save()
        messages.success(
            request, _("Domain mapping saved: %(domain)s") % {"domain": mapping.email_domain}
        )
        return redirect("dealers:domain_list")
    return render(
        request, "dealers/domain_form.html", {"form": form, "object": instance}
    )


@role_required(Role.ADMIN)
def domain_delete(request, pk):
    mapping = get_object_or_404(DomainDealerMap, pk=pk)
    if request.method == "POST":
        mapping.delete()
        messages.success(request, _("Domain mapping deleted."))
        return redirect("dealers:domain_list")
    return render(request, "dealers/domain_confirm_delete.html", {"object": mapping})
