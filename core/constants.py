"""Shared enumerations used across the whole system."""
from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    ADMIN = "ADMIN", _("Admin")
    FINANCE = "FINANCE", _("Finance")
    LOGISTICS = "LOGISTICS", _("Logistics")
    MANAGEMENT = "MANAGEMENT", _("Management")
    DEALER = "DEALER", _("Dealer")


class UserStatus(models.TextChoices):
    PENDING_APPROVAL = "PENDING_APPROVAL", _("Pending approval")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")


class OrderStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    PENDING_PAYMENT = "PENDING_PAYMENT", _("Awaiting payment approval")
    PAID = "PAID", _("Paid")
    SHIPPED = "SHIPPED", _("Shipped")
    CANCELLED = "CANCELLED", _("Cancelled")


class ShipmentStatus(models.TextChoices):
    NOT_SHIPPED = "NOT_SHIPPED", _("Not shipped")
    SHIPPED = "SHIPPED", _("Shipped")


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")


class NotificationEvent(models.TextChoices):
    ORDER_SUBMITTED = "ORDER_SUBMITTED", _("Order submitted to finance")
    PAYMENT_APPROVED = "PAYMENT_APPROVED", _("Payment approved")
    PAYMENT_REJECTED = "PAYMENT_REJECTED", _("Payment rejected")
    ORDER_SHIPPED = "ORDER_SHIPPED", _("Order shipped")
    USER_REGISTERED = "USER_REGISTERED", _("New user awaiting approval")
    USER_APPROVED = "USER_APPROVED", _("User account approved")


class NotificationChannel(models.TextChoices):
    EMAIL = "EMAIL", _("Email")
    INAPP = "INAPP", _("In-app")


class Currency(models.TextChoices):
    USD = "USD", _("USD")
    TRY = "TRY", _("TRY")
    CHF = "CHF", _("CHF")


class ProductGroup(models.TextChoices):
    DEVICE = "DEVICE", _("Device")
    CONSUMABLE = "CONSUMABLE", _("Consumable")
    SPARE_PART = "SPARE_PART", _("Spare part")


class MikroSyncStatus(models.TextChoices):
    NOT_QUEUED = "NOT_QUEUED", _("Not queued")
    PENDING = "PENDING", _("Waiting to be sent")
    SYNCED = "SYNCED", _("Sent to Mikro")
    FAILED = "FAILED", _("Failed")


