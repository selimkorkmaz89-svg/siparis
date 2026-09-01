"""Install the default Turkish and English notification templates."""
from django.core.management.base import BaseCommand

from core.constants import NotificationEvent
from notifications.models import NotificationTemplate

TEMPLATES = {
    NotificationEvent.ORDER_SUBMITTED: {
        "tr": (
            "Yeni sipariş onay bekliyor: {{ order }}",
            "{{ dealer }} bayisinden gelen {{ order }} numaralı sipariş "
            "({{ total }} USD) ödeme onayınızı bekliyor.",
            "{{ dealer }} · {{ total }} USD · ödeme onayı bekliyor.",
        ),
        "en": (
            "New order awaiting payment approval: {{ order }}",
            "Order {{ order }} from {{ dealer }} totalling {{ total }} USD is waiting "
            "for your payment approval.",
            "{{ dealer }} · {{ total }} USD · awaiting payment approval.",
        ),
    },
    NotificationEvent.PAYMENT_APPROVED: {
        "tr": (
            "Ödeme onaylandı: {{ order }}",
            "{{ order }} numaralı siparişin ödemesi onaylandı. Sipariş sevkiyata hazır.",
            "{{ order }} · ödeme onaylandı, sevkiyat bekliyor.",
        ),
        "en": (
            "Payment approved: {{ order }}",
            "The payment for order {{ order }} has been approved. The order is ready "
            "for shipment.",
            "{{ order }} · payment approved, awaiting shipment.",
        ),
    },
    NotificationEvent.PAYMENT_REJECTED: {
        "tr": (
            "Ödeme reddedildi: {{ order }}",
            "{{ order }} numaralı siparişin ödemesi reddedildi. Sebep: {{ note }}",
            "{{ order }} · reddedildi. Sebep: {{ note }}",
        ),
        "en": (
            "Payment rejected: {{ order }}",
            "The payment for order {{ order }} was rejected. Reason: {{ note }}",
            "{{ order }} · rejected. Reason: {{ note }}",
        ),
    },
    NotificationEvent.ORDER_SHIPPED: {
        "tr": (
            "Siparişiniz gönderildi: {{ order }}",
            "{{ order }} numaralı siparişiniz sevk edildi.",
            "{{ order }} · gönderildi.",
        ),
        "en": (
            "Your order has been shipped: {{ order }}",
            "Order {{ order }} has been shipped.",
            "{{ order }} · shipped.",
        ),
    },
    NotificationEvent.USER_REGISTERED: {
        "tr": (
            "Yeni kullanıcı onayı bekliyor: {{ user }}",
            "{{ user }} kullanıcısı {{ dealer }} bayisi için kayıt oldu ve onay bekliyor.",
            "{{ user }} · {{ dealer }} · onay bekliyor.",
        ),
        "en": (
            "New user awaiting approval: {{ user }}",
            "{{ user }} signed up for dealer {{ dealer }} and is waiting for approval.",
            "{{ user }} · {{ dealer }} · awaiting approval.",
        ),
    },
    NotificationEvent.USER_APPROVED: {
        "tr": (
            "Hesabınız onaylandı",
            "Hesabınız onaylandı. Artık sisteme giriş yapabilirsiniz.",
            "Hesabınız onaylandı.",
        ),
        "en": (
            "Your account has been approved",
            "Your account has been approved. You can now sign in.",
            "Your account has been approved.",
        ),
    },
}


class Command(BaseCommand):
    help = "Creates the default notification templates in Turkish and English."

    def handle(self, *args, **options):
        created = updated = 0
        for event, languages in TEMPLATES.items():
            for language, (subject, email_body, inapp_body) in languages.items():
                _obj, was_created = NotificationTemplate.objects.update_or_create(
                    event_type=event,
                    language=language,
                    defaults={
                        "subject": subject,
                        "email_body_template": email_body,
                        "inapp_body_template": inapp_body,
                        "is_active": True,
                    },
                )
                created += int(was_created)
                updated += int(not was_created)
        self.stdout.write(
            self.style.SUCCESS(f"Notification templates: {created} created, {updated} updated.")
        )
