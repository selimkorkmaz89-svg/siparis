from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from catalog import imports
from catalog.forms import DealerSpecialPriceForm, ImportUploadForm, ProductForm
from catalog.models import DealerSpecialPrice, Product
from core.constants import Role
from core.decorators import role_required
from core.exports import excel_response
from core.filters import ListFilter

SESSION_KEY = "catalog_import_preview"


def _product_queryset(request):
    queryset = Product.objects.all()
    brand = request.GET.get("brand") or ""
    if brand:
        queryset = queryset.filter(brand=brand)
    if request.GET.get("active") == "1":
        queryset = queryset.filter(is_active=True)
    list_filter = ListFilter(
        request,
        search_fields=("code", "name", "brand"),
        ordering_map={
            "code": "code", "name": "name", "brand": "brand",
            "price": "base_price_usd", "date": "created_at",
        },
        default_ordering="code",
    )
    return list_filter.apply(queryset), list_filter, brand


@role_required(Role.ADMIN)
def product_list(request):
    queryset, list_filter, brand = _product_queryset(request)
    if request.GET.get("export") == "excel":
        return excel_response(
            "products",
            str(_("Products")),
            [_("Product code"), _("Product name"), _("Brand"), _("Tests per pack"),
             _("List price (USD)"), _("VAT rate (%)"), _("Active")],
            [
                (p.code, p.name, p.brand, p.tests_per_pack, p.base_price_usd,
                 p.vat_rate, _("Yes") if p.is_active else _("No"))
                for p in queryset
            ],
        )
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    brands = (
        Product.objects.exclude(brand="")
        .values_list("brand", flat=True)
        .distinct()
        .order_by("brand")
    )
    return render(
        request,
        "catalog/product_list.html",
        {
            "page_obj": page,
            "products": page.object_list,
            "brands": brands,
            "selected_brand": brand,
            **list_filter.as_context(),
        },
    )


@role_required(Role.ADMIN)
def product_form(request, pk=None):
    instance = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        messages.success(request, _("Product saved: %(code)s") % {"code": product.code})
        return redirect("catalog:product_list")
    special_prices = (
        instance.special_prices.select_related("dealer") if instance else []
    )
    return render(
        request,
        "catalog/product_form.html",
        {"form": form, "object": instance, "special_prices": special_prices},
    )


@role_required(Role.ADMIN)
def special_price_list(request):
    queryset = DealerSpecialPrice.objects.select_related("dealer", "product")
    list_filter = ListFilter(
        request,
        search_fields=("product__code", "product__name", "dealer__name"),
        ordering_map={
            "dealer": "dealer__name", "code": "product__code", "price": "price_usd",
        },
        default_ordering="dealer__name",
    )
    queryset = list_filter.apply(queryset)
    if request.GET.get("export") == "excel":
        return excel_response(
            "special-prices",
            str(_("Dealer special prices")),
            [_("Dealer"), _("Product code"), _("Product name"), _("Special price (USD)")],
            [(sp.dealer.name, sp.product.code, sp.product.name, sp.price_usd)
             for sp in queryset],
        )
    return render(
        request,
        "catalog/special_price_list.html",
        {"special_prices": queryset, **list_filter.as_context()},
    )


@role_required(Role.ADMIN)
def special_price_form(request, pk=None):
    instance = get_object_or_404(DealerSpecialPrice, pk=pk) if pk else None
    form = DealerSpecialPriceForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Special price saved."))
        return redirect("catalog:special_price_list")
    return render(
        request, "catalog/special_price_form.html", {"form": form, "object": instance}
    )


@role_required(Role.ADMIN)
@require_POST
def special_price_delete(request, pk):
    get_object_or_404(DealerSpecialPrice, pk=pk).delete()
    messages.success(request, _("Special price deleted."))
    return redirect("catalog:special_price_list")


@role_required(Role.ADMIN)
def import_template(request, kind):
    if kind not in ("product", "dealer"):
        kind = "product"
    payload = imports.build_template(kind)
    response = HttpResponse(
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{kind}-import-template.xlsx"'
    return response


@role_required(Role.ADMIN)
def import_upload(request):
    """Step 1: upload and validate. Nothing is written yet."""
    form = ImportUploadForm(request.POST or None, request.FILES or None)
    preview = None
    if request.method == "POST" and form.is_valid():
        preview = imports.parse_workbook(
            form.cleaned_data["file"], form.cleaned_data["kind"]
        )
        if preview.blocked:
            request.session.pop(SESSION_KEY, None)
            messages.error(
                request,
                _("The import was stopped: no records were saved. Please fix the errors below."),
            )
        else:
            request.session[SESSION_KEY] = imports.preview_to_session(preview)
            return render(
                request,
                "catalog/import_preview.html",
                {"preview": preview, "kind": form.cleaned_data["kind"]},
            )
    return render(request, "catalog/import_upload.html", {"form": form, "preview": preview})


@role_required(Role.ADMIN)
@require_POST
def import_confirm(request):
    """Step 2: the administrator confirmed the preview, so write the rows."""
    payload = request.session.get(SESSION_KEY)
    if not payload:
        messages.error(request, _("The import session has expired. Please upload the file again."))
        return redirect("catalog:import_upload")
    preview = imports.preview_from_session(payload)
    result = imports.apply_preview(preview)
    request.session.pop(SESSION_KEY, None)
    messages.success(
        request,
        _("Import completed: %(created)s new records, %(updated)s updated records.")
        % result,
    )
    target = "catalog:product_list" if preview.kind == "product" else "dealers:list"
    return redirect(target)


@role_required(Role.ADMIN)
@require_POST
def import_cancel(request):
    request.session.pop(SESSION_KEY, None)
    messages.info(request, _("The import was cancelled; nothing was saved."))
    return redirect("catalog:import_upload")


def product_search_api(request):
    """Live product search used by the dealer's order screen."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"results": []}, status=403)
    dealer = user.dealer if user.is_dealer_user else None
    term = (request.GET.get("q") or "").strip()
    brand = (request.GET.get("brand") or "").strip()
    queryset = Product.objects.filter(is_active=True)
    if term:
        queryset = queryset.filter(code__icontains=term) | queryset.filter(
            name__icontains=term
        )
    if brand:
        queryset = queryset.filter(brand=brand)
    queryset = queryset.order_by("code")[:50]
    results = [
        {
            "id": product.pk,
            "code": product.code,
            "name": product.name,
            "brand": product.brand,
            "tests_per_pack": product.tests_per_pack,
            "price": f"{product.price_for(dealer):.2f}",
            "vat_rate": f"{product.vat_rate:.2f}",
        }
        for product in queryset
    ]
    return JsonResponse({"results": results})
