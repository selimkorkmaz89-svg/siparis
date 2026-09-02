from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel


class Dealer(TimeStampedModel):
    """Dealer account card (cari kart)."""

    name = models.CharField(_("dealer name"), max_length=200, unique=True)
    code = models.CharField(_("dealer code"), max_length=40, blank=True)
    tax_no = models.CharField(_("tax number"), max_length=40, blank=True)
    tax_office = models.CharField(_("tax office"), max_length=120, blank=True)
    address = models.TextField(_("address"), blank=True)
    city = models.CharField(_("city"), max_length=80, blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    email = models.EmailField(_("email"), blank=True)
    contact_person = models.CharField(_("contact person"), max_length=120, blank=True)
    logo = models.ImageField(
        _("dealer logo"), upload_to="dealer_logos/", blank=True, null=True,
        help_text=_("Square images work best; shown at 40x40 pixels in lists."),
    )
    notes = models.TextField(_("notes"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    allowed_device_models = models.ManyToManyField(
        "catalog.DeviceModel",
        verbose_name=_("allowed device models"),
        blank=True,
        related_name="dealers",
        help_text=_(
            "Restricts the catalogue to these device models. Leave empty to "
            "allow every device model (no restriction)."
        ),
    )

    class Meta:
        verbose_name = _("dealer")
        verbose_name_plural = _("dealers")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    @property
    def initials(self) -> str:
        """Two-letter fallback shown when a dealer has no logo."""
        parts = [word for word in self.name.split() if word]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return self.name[:2].upper()


class DomainDealerMap(TimeStampedModel):
    """Maps an email domain to the dealer new sign-ups belong to."""

    email_domain = models.CharField(_("email domain"), max_length=190, unique=True)
    dealer = models.ForeignKey(
        Dealer,
        verbose_name=_("dealer"),
        on_delete=models.CASCADE,
        related_name="domains",
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("domain mapping")
        verbose_name_plural = _("domain mappings")
        ordering = ("email_domain",)

    def __str__(self) -> str:
        return f"{self.email_domain} → {self.dealer.name}"

    def save(self, *args, **kwargs):
        self.email_domain = self.email_domain.strip().lower().lstrip("@")
        super().save(*args, **kwargs)

    @classmethod
    def resolve(cls, email: str):
        """Return the dealer registered for ``email``'s domain, or ``None``."""
        domain = (email or "").split("@")[-1].strip().lower()
        if not domain:
            return None
        mapping = cls.objects.filter(email_domain=domain, is_active=True).select_related(
            "dealer"
        ).first()
        return mapping.dealer if mapping else None
