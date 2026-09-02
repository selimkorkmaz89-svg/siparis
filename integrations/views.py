"""Mikro integration: an admin settings screen plus the connector's API.

The connector is a small script that runs inside the VPN network where
Mikro's API lives (this Django app cannot reach it directly - see
integrations/services.py). It authenticates with a single shared secret
token, not a user session, so the API views below are deliberately outside
the normal login/CSRF machinery; the settings screen is a normal admin page.
"""
import hmac
import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.constants import MikroSyncStatus, Role
from core.decorators import role_required
from integrations import services
from integrations.forms import MikroSettingsForm, VatRateMappingForm
from integrations.models import MikroSettings, VatRateMapping
from orders.models import Order


def _authorized(request) -> bool:
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip()
    expected = MikroSettings.load().connector_token
    return bool(token) and hmac.compare_digest(token, expected)


def _unauthorized():
    return JsonResponse({"detail": str(_("Invalid or missing connector token."))}, status=401)


@csrf_exempt
@require_GET
def ping(request):
    if not _authorized(request):
        return _unauthorized()
    settings_ = MikroSettings.load()
    return JsonResponse({"ok": True, "enabled": settings_.enabled})


@csrf_exempt
@require_GET
def pending_orders(request):
    if not _authorized(request):
        return _unauthorized()
    return JsonResponse({"orders": services.pending_payloads()})


@csrf_exempt
@require_POST
def mark_synced(request, order_id):
    if not _authorized(request):
        return _unauthorized()
    order = get_object_or_404(Order, pk=order_id)
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}
    services.mark_synced(order, reference=str(body.get("reference", "")))
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def mark_failed(request, order_id):
    if not _authorized(request):
        return _unauthorized()
    order = get_object_or_404(Order, pk=order_id)
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}
    error = str(body.get("error", "")) or str(_("The connector reported a failure."))
    services.mark_failed(order, error)
    return JsonResponse({"ok": True})


# -- Admin screen -------------------------------------------------------


@role_required(Role.ADMIN)
def settings_view(request):
    mikro_settings = MikroSettings.load()
    # Captured before any form binds to mikro_settings: ModelForm._post_clean()
    # writes cleaned values straight onto the instance during is_valid(), so
    # reading mikro_settings.sifre afterwards would already see the blank
    # submitted value rather than what was stored.
    stored_sifre = mikro_settings.sifre
    settings_form = MikroSettingsForm(instance=mikro_settings)
    vat_form = VatRateMappingForm()

    if request.method == "POST" and "save_settings" in request.POST:
        settings_form = MikroSettingsForm(request.POST, instance=mikro_settings)
        if settings_form.is_valid():
            saved = settings_form.save(commit=False)
            if not settings_form.cleaned_data.get("sifre"):
                saved.sifre = stored_sifre
            saved.updated_by = request.user
            saved.save()
            messages.success(request, _("Mikro settings saved."))
        else:
            messages.error(request, _("Please fix the errors below."))
        return redirect("integrations:settings")

    if request.method == "POST" and "add_vat_mapping" in request.POST:
        vat_form = VatRateMappingForm(request.POST)
        if vat_form.is_valid():
            vat_form.save()
            messages.success(request, _("VAT pointer mapping saved."))
            return redirect("integrations:settings")
        messages.error(request, _("Please fix the errors below."))

    if request.method == "POST" and "regenerate_token" in request.POST:
        mikro_settings.regenerate_token()
        messages.success(request, _("A new connector token has been generated."))
        return redirect("integrations:settings")

    orders = (
        Order.objects.exclude(mikro_sync_status=MikroSyncStatus.NOT_QUEUED)
        .select_related("dealer")
        .order_by("-mikro_synced_at", "-paid_at")
    )
    page = Paginator(orders, 25).get_page(request.GET.get("page"))

    return render(
        request,
        "integrations/settings.html",
        {
            "settings_form": settings_form,
            "vat_form": vat_form,
            "vat_mappings": VatRateMapping.objects.all(),
            "mikro_settings": mikro_settings,
            "page_obj": page,
            "orders": page.object_list,
            "connector_base_url": request.build_absolute_uri("/entegrasyon/mikro/"),
        },
    )


@role_required(Role.ADMIN)
@require_POST
def vat_mapping_delete(request, pk):
    mapping = get_object_or_404(VatRateMapping, pk=pk)
    mapping.delete()
    messages.success(request, _("VAT pointer mapping deleted."))
    return redirect("integrations:settings")


@role_required(Role.ADMIN)
@require_POST
def retry_sync(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    order.mikro_sync_status = MikroSyncStatus.PENDING
    order.mikro_sync_error = ""
    order.save(update_fields=["mikro_sync_status", "mikro_sync_error"])
    messages.success(
        request, _("Order %(no)s queued again for Mikro.") % {"no": order.order_no}
    )
    return redirect("integrations:settings")
