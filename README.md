# Bayi Sipariş Yönetim Sistemi / Dealer Order Management System

Bayilerin sipariş oluşturduğu, finansın ödemeyi onayladığı, lojistiğin sevkiyatı
işaretlediği ve yönetimin raporladığı web tabanlı sipariş yönetim sistemi.
Arayüz **Türkçe ve İngilizce** olarak tam desteklenir.

A web based order management system where dealers create orders, finance
approves payments, logistics marks shipments and management reports on the
data. The interface is fully available in **Turkish and English**.

---

## İçindekiler / Contents

1. [Özellikler](#özellikler--features)
2. [Mimari](#mimari--architecture)
3. [Hızlı başlangıç](#hızlı-başlangıç--quick-start)
4. [Dil desteği](#dil-desteği--language-support)
5. [İş kuralları](#iş-kuralları--business-rules)
6. [VPS kurulumu](#vps-kurulumu--production-deployment)
7. [Yedekleme](#yedekleme--backups)
8. [Testler](#testler--tests)

---

## Özellikler / Features

| Modül | Kapsam |
|---|---|
| **Kullanıcı & rol** | Admin, Finans, Lojistik, Yönetim, Bayi; e-posta domaini üzerinden otomatik bayi eşleştirme, yönetici onaylı kayıt akışı |
| **Katalog** | Ürün kartları (USD fiyat + ürün bazlı KDV), bayi özel fiyatları, Excel şablonu ile içe aktarma (önizleme + onay) |
| **Sipariş** | Canlı arama + sepet ekranı, `django-fsm` ile denetimli durum makinesi, yıl bazlı sipariş numarası, kalem bazında donmuş fiyat/KDV |
| **Ödeme** | Manuel dekont eşleştirme, TCMB kuru (Celery), sipariş bazında tek onaylı ödeme, tolerans dışı tutarda uyarı |
| **Lojistik** | Sipariş bazlı "gönderildi" işaretleme, kargo/takip bilgisi |
| **Bildirim** | Sistem içi zil paneli (kapatılamaz) + kullanıcı tercihine bağlı e-posta, şablon ve gönderim logu |
| **Raporlama** | Bayi / ürün / marka / finans / operasyon kırılımları, Chart.js grafikleri, USD-TL toggle, Excel export |
| **Belge** | WeasyPrint ile Sipariş Formu PDF'i (resmi belge değildir, her aşamada indirilebilir) |

## Mimari / Architecture

```
config/         Django project settings, URLs, Celery
core/           Shared enums, permissions, list filters, Excel export, template tags
accounts/       Custom User (email login), roles, registration + approval flow
dealers/        Dealer (cari kart), DomainDealerMap
catalog/        Product, DealerSpecialPrice, Excel import (preview/confirm)
orders/         Order, OrderItem, OrderStatusHistory, FSM, order numbering, PDF
payments/       Payment, ExchangeRate, TCMB fetch (Celery), finance approval
logistics/      Shipment marking (order level)
reports/        Dealer/product/brand/finance/operations reporting
notifications/  In-app + email notifications, templates, delivery log
locale/         tr + en message catalogues (locale/_source/tr.py is the editable source)
docker/         nginx.conf, backup.sh
```

| Katman | Seçim |
|---|---|
| Backend | Django 5.1 + Django REST Framework |
| Veritabanı | PostgreSQL (geliştirmede SQLite) |
| Frontend | Django template + vanilla JS (build adımı yok) |
| Durum makinesi | django-fsm |
| PDF | WeasyPrint |
| Excel | openpyxl |
| Grafikler | Chart.js (yerel olarak paketlenmiştir) |
| Zamanlanmış görevler | Celery + Celery Beat + Redis |
| Sunum | Gunicorn + Nginx + Let's Encrypt |

## Hızlı başlangıç / Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py compilemessages          # tr/en katalogları derle
python manage.py seed_notification_templates
python manage.py seed_demo                # örnek bayi/ürün/sipariş verisi
python manage.py createsuperuser
python manage.py runserver
```

`seed_demo` ile oluşan demo hesaplar (şifre: `Demo12345!`):

| E-posta | Rol |
|---|---|
| `admin@sirket.com` | Admin |
| `finans@sirket.com` | Finans |
| `lojistik@sirket.com` | Lojistik |
| `yonetim@sirket.com` | Yönetim |
| `ali@bayi1.com` | Bayi |

> Varsayılan olarak SQLite kullanılır. PostgreSQL için `.env` içinde
> `USE_SQLITE=False` yapıp `POSTGRES_*` değerlerini doldurun.

## Dil desteği / Language support

Sistemin tamamı (menüler, formlar, doğrulama mesajları, bildirimler, PDF ve
Excel çıktıları) Türkçe ve İngilizce olarak çalışır.

* **Varsayılan dil** Türkçe'dir (`LANGUAGE_CODE=tr`).
* Kullanıcı dili **Profilim** ekranından kalıcı olarak seçebilir
  (`User.language`); bu tercih her cihazda geçerlidir.
* Üst çubuktaki **TR/EN** seçici anlık geçiş yapar (çerez + oturum).
* Bildirim e-postaları ve sistem içi bildirimler **alıcının kendi dilinde**
  üretilir (`NotificationTemplate` satırları dil bazlıdır).
* Sipariş Formu PDF'i geçerli dile göre üretilir.

Kaynak dizeler İngilizce yazılır, Türkçe çeviri katalogdan gelir:

```bash
# 1) Yeni dizeleri topla
python manage.py makemessages -l tr -l en --ignore=.venv --ignore=staticfiles
# 2) Türkçe karşılıkları locale/_source/tr.py içine ekle, sonra:
python manage.py sync_translations      # eksik çeviri varsa listeler
# 3) Derle
python manage.py compilemessages --ignore=.venv
```

`sync_translations` çevirisi olmayan dizeleri raporlar, bu yüzden yeni bir
ekran eklendiğinde eksik çeviri gözden kaçmaz.

## İş kuralları / Business rules

**Sipariş yaşam döngüsü**

```
DRAFT ──submit──► PENDING_PAYMENT ──approve──► PAID ──ship──► SHIPPED
                        │
                        └──reject (açıklama zorunlu)──► DRAFT
DRAFT / PENDING_PAYMENT ──cancel──► CANCELLED
```

* Geçişler `django-fsm` ile korunur; finans onayı olmadan sevkiyat yapılamaz.
* Her geçiş `OrderStatusHistory` tablosuna yazılır (kim, ne zaman, hangi
  durumdan hangi duruma, not/red sebebi, o anki sipariş numarası).
* **Taslakta resmi numara verilmez** ("Taslak #14"). `PENDING_PAYMENT`
  geçişinde `BSH-YYYY-NNNNNN` atanır. Red sonrası tekrar gönderimde **yeni**
  numara üretilir; eski numara geçmişte izlenebilir kalır.
* Sayaç `OrderNumberSequence` üzerinde `SELECT FOR UPDATE` ile korunur.
* Kısmi ödeme ve kısmi sevkiyat yoktur.

**Fiyat ve KDV**

* Tüm fiyatlar USD'dir. Bayiye özel fiyat (`DealerSpecialPrice`) varsa liste
  fiyatının önüne geçer.
* Sipariş kalemi oluşturulduğunda birim fiyat ve KDV oranı **kopyalanır ve
  donar**; katalogdaki sonraki değişiklikler geçmiş siparişleri etkilemez.

**Kur**

* TCMB kuru her iş günü 15:30'da açıklanır; Celery Beat 15:35'te çeker.
* 15:30 öncesi işlemler bir önceki iş gününün kuruna tabidir.
* Hafta sonu/tatil günleri geriye doğru en yakın iş gününün kurunu kullanır.
* Ödeme onaylandığı anda kullanılan kur `Payment.exchange_rate` alanına
  **donar**; raporlama ekranlarındaki USD/TL toggle ise **güncel** kur ile
  çalışır.
* Girilen TL tutar sipariş toplamından `PAYMENT_MISMATCH_TOLERANCE` oranından
  fazla saparsa uyarı gösterilir, ancak onay **engellenmez**.

**Excel içe aktarma**

* Dosya içinde **mükerrer kod** varsa import tamamen durur, hiçbir kayıt
  yazılmaz, hatalı satırlar listelenir.
* Diğer satırlar önizleme ekranında "yeni eklenecek" / "güncellenecek (eski →
  yeni)" olarak gösterilir; yazma işlemi yalnızca yönetici onayından sonra olur.

**Kapsam dışı** (bilinçli olarak): stok/envanter yönetimi, maliyet/kârlılık
raporlaması, navlun/gümrük dağıtımı, resmi e-fatura/e-irsaliye üretimi.

## VPS kurulumu / Production deployment

```bash
git clone <repo> /opt/siparis && cd /opt/siparis
cp .env.example .env          # SECRET_KEY, ALLOWED_HOSTS, DB, SMTP değerlerini doldurun
docker compose build
docker compose up -d db redis
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_notification_templates
docker compose run --rm web python manage.py createsuperuser
docker compose up -d
```

**HTTPS (Let's Encrypt)**

```bash
# 1) Sertifikayı alın (nginx 80 portunda ayakta olmalı)
docker compose run --rm certbot certonly --webroot -w /var/www/certbot \
    -d siparis.example.com --email admin@example.com --agree-tos --no-eff-email
# 2) docker/nginx.conf içindeki SIPARIS_DOMAIN yerine alan adınızı yazın
# 3) Nginx'i yeniden yükleyin
docker compose restart nginx
```

`certbot` servisi 12 saatte bir yenileme kontrolü yapar.

**Staging ortamı**: aynı compose dosyasını ayrı bir `.env` ve
`-p siparis-staging` proje adı ile çalıştırın.

## Yedekleme / Backups

`docker/backup.sh` PostgreSQL dökümünü ve `media/` klasörünü sıkıştırarak
`backups/` altına yazar, 30 günden eski dosyaları siler. Host crontab'ına
ekleyin:

```cron
0 2 * * * /opt/siparis/docker/backup.sh >> /var/log/siparis-backup.log 2>&1
```

Geri yükleme:

```bash
gunzip -c backups/db-20260901-020000.sql.gz | \
    docker compose exec -T db psql -U siparis siparis
```

## Testler / Tests

```bash
python manage.py test              # 67 test: iş kuralları, yetkiler, i18n, PDF, Excel
python manage.py test orders        # sipariş durum makinesi ve numaralandırma
python manage.py test payments      # kur kuralları (15:30, hafta sonu, tatil)
python manage.py test catalog       # Excel import doğrulaması
python manage.py test notifications # bildirim kanalları ve dil bazlı içerik
python manage.py test reports       # raporlama kırılımları ve USD/TL çevrimi
python manage.py test accounts      # kayıt/onay akışı ve dil desteği
python manage.py test core          # rol bazlı erişim + ekran smoke testleri
```

## İleride / Roadmap (Faz 2)

Micro Muhasebe entegrasyonu, ürün maliyeti ve brüt/net kâr raporlaması,
ithalat/navlun maliyet dağıtımı (landed cost), bayi kredi limiti/bakiye takibi.
