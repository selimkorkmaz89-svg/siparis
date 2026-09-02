"""Role based sidebar navigation.

The menu lives here rather than in the template so each role gets one flat,
readable list — section headings were what made the sidebar hard to scan — and
so the entries can be asserted in tests.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.constants import Role


@dataclass(frozen=True)
class NavItem:
    url_name: str
    label: str
    icon: str
    #: URL names that should also light this entry up (detail screens).
    also_active_for: tuple = ()

    @property
    def url(self) -> str:
        return reverse(self.url_name)

    def is_active(self, current: str) -> bool:
        return current == self.url_name or current in self.also_active_for


HOME = NavItem("core:home", _("Overview"), "home")
PROFILE = NavItem("accounts:profile", _("My profile"), "profile")
NOTIFICATIONS = NavItem("notifications:list", _("Notifications"), "bell")
ALL_ORDERS = NavItem(
    "orders:list", _("All orders"), "orders",
    also_active_for=("orders:detail", "orders:pdf"),
)
PAYMENT_HISTORY = NavItem("payments:history", _("Payment history"), "payments")
DEALER_HISTORY = NavItem(
    "dealers:history", _("Dealer history"), "dealers",
    also_active_for=("dealers:history_detail",),
)
REPORTS = NavItem("reports:dashboard", _("Reports"), "reports")

NAV: dict[str, tuple[NavItem, ...]] = {
    Role.DEALER: (
        HOME,
        NavItem("orders:create", _("Create order"), "new-order",
                also_active_for=("orders:review",)),
        NavItem("orders:list", _("My orders"), "orders",
                also_active_for=("orders:detail", "orders:pdf")),
        NavItem("orders:drafts", _("My drafts"), "drafts"),
        NavItem("payments:history", _("My payment history"), "payments"),
        NavItem("reports:mine", _("My reports"), "reports"),
        NOTIFICATIONS,
        PROFILE,
    ),
    Role.FINANCE: (
        HOME,
        NavItem("payments:pending", _("Awaiting approval"), "pending-approval",
                also_active_for=("payments:approve", "payments:declare")),
        ALL_ORDERS,
        PAYMENT_HISTORY,
        DEALER_HISTORY,
        REPORTS,
        NOTIFICATIONS,
        PROFILE,
    ),
    Role.LOGISTICS: (
        HOME,
        NavItem("logistics:pending", _("Awaiting shipment"), "shipment",
                also_active_for=("logistics:mark_shipped",)),
        ALL_ORDERS,
        PAYMENT_HISTORY,
        DEALER_HISTORY,
        NOTIFICATIONS,
        PROFILE,
    ),
    Role.MANAGEMENT: (
        HOME,
        ALL_ORDERS,
        REPORTS,
        NavItem("reports:finance", _("Finance and operations"), "payments"),
        NOTIFICATIONS,
        PROFILE,
    ),
    Role.ADMIN: (
        HOME,
        ALL_ORDERS,
        NavItem("catalog:product_list", _("Product management"), "products",
                also_active_for=("catalog:product_create", "catalog:product_edit")),
        NavItem("catalog:special_price_list", _("Dealer special prices"), "price-tag",
                also_active_for=("catalog:special_price_create",
                                 "catalog:special_price_edit")),
        NavItem("dealers:list", _("Dealer management"), "dealers",
                also_active_for=("dealers:create", "dealers:edit",
                                 "dealers:domain_list", "dealers:domain_create",
                                 "dealers:domain_edit", "dealers:domain_delete")),
        NavItem("catalog:import_upload", _("Excel import"), "import"),
        REPORTS,
        NavItem("accounts:pending_users", _("User approvals"), "user-check",
                also_active_for=("accounts:reject_user",)),
        NavItem("accounts:user_list", _("User management"), "users",
                also_active_for=("accounts:user_create", "accounts:user_edit")),
        NavItem("payments:exchange_rates", _("System settings"), "settings"),
        NOTIFICATIONS,
        PROFILE,
    ),
}

ROLE_LABELS = {
    Role.DEALER: _("Dealer"),
    Role.FINANCE: _("Finance"),
    Role.LOGISTICS: _("Logistics"),
    Role.MANAGEMENT: _("Management"),
    Role.ADMIN: _("System administrator"),
}


def items_for(user, current_url_name: str = "") -> list[dict]:
    """Menu entries for ``user``, with the active one already resolved.

    Returning plain dictionaries keeps the template free of any branching.
    """
    if not getattr(user, "is_authenticated", False):
        return []
    return [
        {
            "url": item.url,
            "label": item.label,
            "icon": item.icon,
            "active": item.is_active(current_url_name),
        }
        for item in NAV.get(user.role, ())
    ]


def role_label(user) -> str:
    if not getattr(user, "is_authenticated", False):
        return ""
    return ROLE_LABELS.get(user.role, "")
