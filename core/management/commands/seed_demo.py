"""Create a realistic demo dataset for local development and screenshots."""
import datetime as dt
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import DealerSpecialPrice, Product
from core.constants import Role, UserStatus
from dealers.models import Dealer, DomainDealerMap
from orders import services as order_services
from payments.models import ExchangeRate

User = get_user_model()

BRANDS = ["Acme Diagnostics", "Vitalab", "Nordis", "Prime Bio"]


class Command(BaseCommand):
    help = "Creates demo dealers, products, users and orders."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="Demo12345!", help="Password for all demo users")
        parser.add_argument("--orders", type=int, default=12, help="Number of demo orders")

    def handle(self, *args, **options):
        password = options["password"]
        random.seed(42)

        ExchangeRate.objects.get_or_create(
            rate_date=timezone.localdate(),
            defaults={"usd_try_rate": Decimal("34.2150"), "source": "DEMO"},
        )
        ExchangeRate.objects.get_or_create(
            rate_date=timezone.localdate() - dt.timedelta(days=1),
            defaults={"usd_try_rate": Decimal("34.1080"), "source": "DEMO"},
        )

        dealers = []
        for index in range(1, 4):
            dealer, _created = Dealer.objects.get_or_create(
                name=f"Demo Bayi {index}",
                defaults={
                    "code": f"D-{index:03d}",
                    "tax_no": f"12345678{index:02d}",
                    "city": ["İstanbul", "Ankara", "İzmir"][index - 1],
                    "contact_person": f"Yetkili {index}",
                    "phone": f"+90 212 000 00 0{index}",
                    "address": f"Demo Mahallesi No {index}",
                },
            )
            dealers.append(dealer)
            DomainDealerMap.objects.get_or_create(
                email_domain=f"bayi{index}.com", defaults={"dealer": dealer}
            )

        products = []
        for index in range(1, 26):
            product, _created = Product.objects.get_or_create(
                code=f"PRD-{index:03d}",
                defaults={
                    "name": f"Demo Reaktif Kiti {index}",
                    "brand": BRANDS[index % len(BRANDS)],
                    "tests_per_pack": random.choice([50, 100, 200]),
                    "base_price_usd": Decimal(random.randrange(4000, 60000)) / 100,
                    "vat_rate": Decimal(random.choice(["10.00", "20.00"])),
                },
            )
            products.append(product)

        for product in products[:5]:
            DealerSpecialPrice.objects.get_or_create(
                dealer=dealers[0],
                product=product,
                defaults={"price_usd": (product.base_price_usd * Decimal("0.9")).quantize(Decimal("0.01"))},
            )

        staff = [
            ("admin@sirket.com", Role.ADMIN, "Sistem", "Yöneticisi"),
            ("finans@sirket.com", Role.FINANCE, "Finans", "Kullanıcısı"),
            ("lojistik@sirket.com", Role.LOGISTICS, "Lojistik", "Kullanıcısı"),
            ("yonetim@sirket.com", Role.MANAGEMENT, "Yönetim", "Kullanıcısı"),
        ]
        for email, role, first, last in staff:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email, "role": role, "first_name": first,
                    "last_name": last, "status": UserStatus.APPROVED,
                    "is_staff": role == Role.ADMIN, "is_superuser": role == Role.ADMIN,
                },
            )
            if created:
                user.set_password(password)
                user.save()

        dealer_users = []
        for index, dealer in enumerate(dealers, start=1):
            email = f"ali@bayi{index}.com"
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email, "role": Role.DEALER, "dealer": dealer,
                    "first_name": "Ali", "last_name": f"Bayi{index}",
                    "status": UserStatus.APPROVED,
                },
            )
            if created:
                user.set_password(password)
                user.save()
            dealer_users.append(user)

        created_orders = 0
        for _index in range(options["orders"]):
            user = random.choice(dealer_users)
            draft = order_services.get_or_create_draft(user)
            if draft.items.exists():
                continue
            for product in random.sample(products, random.randint(1, 5)):
                order_services.add_item(draft, product, random.randint(1, 10))
            order_services.submit_order(draft, user)
            created_orders += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {len(dealers)} dealers, {len(products)} products, "
                f"{created_orders} orders. Password: {password}"
            )
        )
