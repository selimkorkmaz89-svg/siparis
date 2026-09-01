from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import Role, UserStatus


class UserManager(BaseUserManager):
    """Manager for a user model that authenticates by email address."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError(_("An email address is required."))
        email = self.normalize_email(email).lower()
        extra.setdefault("username", email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        extra.setdefault("role", Role.DEALER)
        extra.setdefault("status", UserStatus.PENDING_APPROVAL)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", Role.ADMIN)
        extra.setdefault("status", UserStatus.APPROVED)
        if extra.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Application user; dealers are bound to a dealer record, staff are not."""

    username = models.CharField(_("username"), max_length=150, unique=True)
    email = models.EmailField(_("email address"), unique=True)
    dealer = models.ForeignKey(
        "dealers.Dealer",
        verbose_name=_("dealer"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.CharField(
        _("role"), max_length=20, choices=Role.choices, default=Role.DEALER
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=UserStatus.choices,
        default=UserStatus.PENDING_APPROVAL,
    )
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    profile_photo = models.ImageField(
        _("profile photo"), upload_to="profile_photos/", blank=True, null=True
    )
    email_notifications_enabled = models.BooleanField(
        _("email notifications enabled"), default=True
    )
    language = models.CharField(
        _("interface language"),
        max_length=5,
        choices=[("tr", _("Turkish")), ("en", _("English"))],
        default="tr",
    )
    approved_by = models.ForeignKey(
        "self",
        verbose_name=_("approved by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_users",
    )
    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    rejection_reason = models.TextField(_("rejection reason"), blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("first_name", "last_name", "email")

    def __str__(self) -> str:
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    # -- role helpers -----------------------------------------------------
    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_finance(self) -> bool:
        return self.role == Role.FINANCE

    @property
    def is_logistics(self) -> bool:
        return self.role == Role.LOGISTICS

    @property
    def is_management(self) -> bool:
        return self.role == Role.MANAGEMENT

    @property
    def is_dealer_user(self) -> bool:
        return self.role == Role.DEALER

    @property
    def is_approved(self) -> bool:
        return self.status == UserStatus.APPROVED

    @property
    def can_see_all_dealers(self) -> bool:
        return self.role in (Role.ADMIN, Role.FINANCE, Role.LOGISTICS, Role.MANAGEMENT)

    @property
    def email_domain(self) -> str:
        return self.email.split("@")[-1].lower()
