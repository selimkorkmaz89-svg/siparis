import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import Currency


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


class MikroSettings(models.Model):
    """Connection details for the Mikro Desktop API (SiparisKaydetV2).

    A singleton row, editable from System Settings. Mikro's API only listens
    on the private network where it is installed (see the VPN/virtual server
    setup this account uses), so this Django app never calls Mikro directly:
    it only builds ready-to-send payloads and hands them, over
    ``connector_token``, to a small relay script that runs inside that
    network and does the actual POST to Mikro.
    """

    SINGLETON_ID = 1

    enabled = models.BooleanField(
        _("enabled"),
        default=False,
        help_text=_("While off, approved orders are not queued for Mikro at all."),
    )

    # -- Mikro credentials (sent as-is in every SiparisKaydetV2 request) ----
    api_key = models.CharField(_("Mikro API key"), max_length=255, blank=True)
    firma_kodu = models.CharField(_("company code (FirmaKodu)"), max_length=40, blank=True)
    kullanici_kodu = models.CharField(_("user code (KullaniciKodu)"), max_length=40, blank=True)
    sifre = models.CharField(
        _("password (Sifre)"), max_length=255, blank=True,
        help_text=_(
            "The plain Mikro user password. Mikro requires it hashed with the "
            "day's date (MD5 of “YYYY-MM-DD ” + password) on every request, "
            "recomputed fresh each time - this is done automatically and the "
            "plain value is never shown again once saved."
        ),
    )
    calisma_yili = models.PositiveIntegerField(
        _("working year (CalismaYili)"), default=0,
        help_text=_("Mikro's fiscal year. Update this when the fiscal year rolls over."),
    )

    # -- Fixed document fields, the same for every order sent ---------------
    depo_no = models.PositiveIntegerField(_("warehouse number (sip_depono)"), default=0)
    evrak_seri = models.CharField(_("document series (sip_evrakno_seri)"), max_length=10, blank=True)
    sip_tip = models.CharField(_("order type (sip_tip)"), max_length=10, default="1")
    sip_cins = models.CharField(_("order kind (sip_cins)"), max_length=10, default="0")
    birim_pntr = models.PositiveIntegerField(_("default unit pointer (sip_birim_pntr)"), default=1)
    vergisiz_fl = models.BooleanField(
        _("prices are VAT-exclusive (sip_vergisiz_fl)"), default=False,
    )
    para_birimi = models.CharField(
        _("currency sent to Mikro"), max_length=3, choices=Currency.choices,
        default=Currency.TRY,
        help_text=_("Order amounts are converted to this currency before being sent."),
    )

    connector_token = models.CharField(
        _("connector token"), max_length=64, default=_generate_token, editable=False,
    )

    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("updated by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Mikro settings")
        verbose_name_plural = _("Mikro settings")

    def __str__(self) -> str:
        return str(_("Mikro settings"))

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "MikroSettings":
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return obj

    def regenerate_token(self) -> None:
        self.connector_token = _generate_token()
        self.save(update_fields=["connector_token"])


class VatRateMapping(models.Model):
    """Maps a product's VAT rate (%) to Mikro's ``sip_vergi_pntr`` code.

    Mikro's VAT pointers are specific to each company's own setup (looked up
    via VergiListesiV2 in Mikro), so this has to be entered by hand once per
    rate actually used in the catalogue.
    """

    vat_rate = models.DecimalField(
        _("VAT rate (%)"), max_digits=5, decimal_places=2, unique=True,
    )
    mikro_vergi_pntr = models.PositiveIntegerField(_("Mikro VAT pointer (sip_vergi_pntr)"))

    class Meta:
        verbose_name = _("VAT pointer mapping")
        verbose_name_plural = _("VAT pointer mappings")
        ordering = ("vat_rate",)

    def __str__(self) -> str:
        return f"%{self.vat_rate} → {self.mikro_vergi_pntr}"
