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
4. [Güncelleme](#güncelleme--staying-up-to-date)
5. [Sipariş Formu](#sipariş-formu--order-form)
6. [Kurumsal kimlik](#kurumsal-kimlik--branding)
7. [E-posta ayarları](#e-posta-ayarları--email-settings)
8. [Mikro entegrasyonu](#mikro-entegrasyonu--mikro-integration)
9. [Dil desteği](#dil-desteği--language-support)
10. [İş kuralları](#iş-kuralları--business-rules)
11. [VPS kurulumu](#vps-kurulumu--production-deployment)
12. [Yedekleme](#yedekleme--backups)
13. [Testler](#testler--tests)

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

> **Yerelde `.env` dosyası oluşturmayın.** Dosya yokken proje SQLite ve düz
> HTTP ile çalışır; Postgres, Redis veya Celery gerekmez. `.env.example`
> sunucu (Docker) kurulumu içindir — yerelde kopyalarsanız `DEBUG=False`
> devreye girer ve `runserver` sizi HTTPS'e yönlendirir. Yanlışlıkla
> kopyaladıysanız `runserver` başlangıçta `core.W001` uyarısıyla bunu söyler;
> çözüm `.env` dosyasını silmektir.

## Güncelleme / Staying up to date

Depoda yeni bir değişiklik olduğunda yereldeki kopyanızı güncellemek için tek
komut yeterli:

```powershell
# Windows (PowerShell)
.\scripts\update.ps1
```

```bash
# macOS / Linux / WSL
./scripts/update.sh
```

Betik sırayla: kaydedilmemiş değişiklik var mı bakar → `git pull` yapar →
`requirements.txt` değiştiyse paketleri kurar → bekleyen migration varsa
uygular. Hiçbir şey değişmediyse hepsi boş geçer, zararsızdır.

Elle yapmak isterseniz karşılığı şudur:

```bash
git pull
pip install -r requirements.txt   # yalnızca requirements.txt değiştiyse
python manage.py migrate          # yalnızca yeni migration geldiyse
```

Çeviri (`.mo`) ve statik dosyalar depoda hazır geldiği için `compilemessages`
veya `collectstatic` çalıştırmanız gerekmez. Sunucu çalışırken `git pull`
yaparsanız Django kod değişikliklerini kendi yeniden yükler; şablon veya CSS
değişikliği için tarayıcıda sayfayı yenilemek yeterlidir.

## Sipariş Formu / Order form

Sipariş formu iki şekilde açılabilir:

| Yol | Ne yapar | Gereksinim |
|---|---|---|
| **Sipariş Formu (PDF) indir** | WeasyPrint ile PDF üretir | cairo/pango sistem kütüphaneleri |
| **Önizleme** | Aynı belgeyi tarayıcıda açar, `Yazdır / PDF olarak kaydet` butonu ile PDF alınır | yok |

Windows'ta WeasyPrint genellikle GTK olmadan çalışmaz. Bu durumda PDF butonu
hata vermez: formu yazdırılabilir sayfa olarak açar ve bunu size söyler.
Sunucuda (Docker imajında) gerekli kütüphaneler zaten kuruludur, PDF çalışır.

## Kurumsal kimlik / Branding

Firma adı, logo ve vurgu rengi ayardan gelir; şablonlarda sabit yazılmaz.

| Ayar | Varsayılan | Nerede görünür |
|---|---|---|
| `COMPANY_NAME` | `BASH Medikal` | Sayfa başlıkları, `alt` metni, PDF |
| `COMPANY_LOGO` | `img/logo.png` | Sol menü, mobil başlık, giriş ekranı, PDF |
| `BRAND_COLOR` | `#0D8DBE` | PDF vurgu rengi |

Kendi logo dosyanızı kullanmak için dosyayı `static/img/` altına koyup `.env`
içinde yolunu verin:

```env
COMPANY_LOGO=img/logo.png
```

Sol menüde artık yazı yok — sadece logo (büyütülmüş) ve altında "SİPARİŞ
SİSTEMİ" satırı var (çeviriden gelir, `Order System`); `COMPANY_NAME` yalnızca
sayfa başlığında, `alt` metninde ve PDF'te kullanılır. Şeffaf arka planlı,
kare olmayan bir dosya (PNG/SVG) en iyi sonucu verir — sol menüde 56px
yükseklikte, giriş ekranında 64px yükseklikte, oranı korunarak gösterilir.

## E-posta ayarları / Email settings

SMTP ayarları (`.env` dosyasındaki `EMAIL_*` değişkenleri) yalnızca **başlangıç
yedeğidir**. Asıl ayar yönetimi *Sistem Ayarları* ekranından (Admin →
Sistem Ayarları → E-posta Bildirimleri) yapılır ve veritabanında saklanır —
sunucuyu yeniden başlatmadan değiştirilebilir:

| Alan | Açıklama |
|---|---|
| Etkin | Kapalıyken `.env`'deki (veya geliştirmede konsol) yedek ayar kullanılır |
| Gönderim yöntemi | SMTP veya Microsoft Graph |
| SMTP sunucusu / portu / kullanıcı adı / şifresi | SMTP seçiliyken kullanılan standart kimlik bilgileri |
| TLS / SSL | Aynı anda ikisi birden açılamaz |
| Azure kiracı / uygulama kimliği / istemci gizli anahtarı | Microsoft Graph seçiliyken kullanılan kimlik bilgileri |
| Gönderen adresi | Örn. `"BASH Medikal" <noreply@example.com>`; Microsoft Graph ile bu, uygulamanın adına gönderim yapabileceği gerçek bir posta kutusu olmalı |

Şifre / istemci gizli anahtarı alanları **hiçbir zaman tarayıcıya geri
gönderilmez** — kaydedilmiş değeri korumak için alanı boş bırakmanız yeterlidir,
sadece değiştirmek istediğinizde yenisini yazın.

### Microsoft Graph ile gönderim (Office 365 Security Defaults engeli için)

Office 365 kiracınızın **Security Defaults (Güvenlik Varsayılanları)**
politikası, geleneksel SMTP kimlik doğrulamasını (`smtp.office365.com:587`)
`535 5.7.139 Authentication unsuccessful` hatasıyla engelliyorsa, bu
politikayı zayıflatmadan **Microsoft Graph (App-Only / Client Credentials)**
üzerinden gönderime geçebilirsiniz — SMTP tamamen devre dışı kalır,
kimlik doğrulama bir Azure AD uygulama kaydı ile yapılır.

**Azure/Microsoft Entra ID tarafında gerekenler** (bir kere yapılır):

1. Microsoft Entra ID → App registrations → **New registration** (tek kiracılı/Single tenant).
2. **Certificates & secrets** → yeni bir **Client secret** oluşturun, değeri kopyalayın (bir daha gösterilmez).
3. **API permissions** → Microsoft Graph → **Application permissions** → **`Mail.Send`** ekleyin.
4. Aynı ekranda **Grant admin consent** ile bu izni kiracı düzeyinde onaylayın.
5. Uygulamanın **Overview** sekmesinden **Tenant ID** ve **Application (client) ID** değerlerini not edin.

**Sistem tarafında** (Admin → Sistem Ayarları → E-posta Bildirimleri):

- Gönderim yöntemi: **Microsoft Graph (Office 365)**
- Azure kiracı kimliği / uygulama kimliği / istemci gizli anahtarı: yukarıdaki 5 değer
- Gönderen adresi: uygulamanın adına gönderim yapabileceği gerçek bir posta kutusu (örn. `b2b@sirket.com`) — Graph bu kutu **için** kimlik doğrular, ondan **olarak** e-posta gönderir

Aynı üç değer isterseniz sunucuyu yeniden başlatmadan değiştirilmesin diye
`.env`'e de yazılabilir (`MS_GRAPH_TENANT_ID`, `MS_GRAPH_CLIENT_ID`,
`MS_GRAPH_CLIENT_SECRET`) — Sistem Ayarları ekranındaki değerler her zaman
önceliklidir, `.env`'dekiler sadece hiç girilmemişse kullanılır. Kaydettikten
sonra **Test e-postası gönder** ile doğrulayın; `535` yerine bir Graph hatası
alırsanız (401/403), önce `Mail.Send` iznine yönetici onayı verildiğini ve
gönderen adresin gerçek bir posta kutusu olduğunu kontrol edin.

Ayarları kaydettikten sonra aynı ekrandaki **Test e-postası gönder** ile
herhangi bir adrese anında bir deneme e-postası atıp yapılandırmayı
doğrulayabilirsiniz.

**Kullanıcı bazında açma/kapama** ayrı bir konudur ve zaten mevcuttu: her
kullanıcı kendi *Profilim* ekranından e-posta bildirimlerini açıp kapatabilir
(`E-posta bildirimlerini gönder` anahtarı). Sistem geneli SMTP anahtarı ile bu
kullanıcı tercihi birbirinden bağımsızdır — SMTP etkin olsa bile, bildirimi
kapatan bir kullanıcıya e-posta gitmez; sistem içi (zil) bildirim bundan
etkilenmeden her zaman oluşur.

## Mikro entegrasyonu / Mikro integration

Onaylanan (PAID) siparişler, Mikro ERP'ye (`SiparisKaydetV2`) otomatik olarak
gönderilebilir. Admin → **Mikro entegrasyonu** ekranından yönetilir.

**Neden bu sistem Mikro'ya doğrudan bağlanmıyor:** Mikro'nun API'si (Mikro
Desktop API) sadece kurulu olduğu sunucunun bulunduğu özel ağda/VPN'de
dinliyor; bu sistem ise dışarıda, ayrı bir sunucuda çalışıyor. Bu yüzden akış
tersine çevrilmiştir:

1. Bir sipariş onaylandığında (ödeme onayı → PAID), sipariş "gönderim bekliyor"
   durumuna kuyruğa alınır.
2. VPN ağının içinde çalışan küçük bir **aktarım scripti** (bu depoda yer
   almaz, ayrıca yazılmalı/kurulmalıdır), Mikro entegrasyonu ekranındaki
   token ile şu uç noktaları dinler:
   - `GET /entegrasyon/mikro/api/bekleyen/` — gönderilmeyi bekleyen
     siparişlerin, doğrudan Mikro'nun `SiparisKaydetV2`'sine POST edilebilecek
     hazır JSON gövdelerini döner.
   - `POST /entegrasyon/mikro/api/siparisler/<id>/tamamlandi/` — script,
     Mikro'ya başarıyla yazdıktan sonra siparişi "gönderildi" işaretler.
   - `POST /entegrasyon/mikro/api/siparisler/<id>/hata/` — Mikro bir hata
     döndürürse, hata mesajını sipariş üzerine kaydeder.
   - `GET /entegrasyon/mikro/api/ping/` — bağlantı/token testi.
3. Her istek `Authorization: Bearer <token>` başlığı ile doğrulanır (kullanıcı
   girişi değildir); token, ayarlar ekranından görüntülenebilir ve
   yenilenebilir.

**Kurulumdan önce doldurulması gerekenler:**

| Ayar | Nerede |
|---|---|
| Mikro API anahtarı, firma/kullanıcı kodu, şifre, çalışma yılı | Mikro entegrasyonu ekranı |
| Depo no, evrak seri, sipariş tipi/cinsi, birim pointer, para birimi | Mikro entegrasyonu ekranı |
| Her bayinin Mikro cari kodu | Bayi düzenleme formu → *Mikro entegrasyonu* bölümü |
| Her ürünün Mikro stok kodu | Ürün düzenleme formu |
| Kullanılan her KDV oranının Mikro `sip_vergi_pntr` karşılığı | Mikro entegrasyonu ekranı (Mikro'da `VergiListesiV2` ile bulunur) |

Şifre alanı da SMTP ayarlarındaki gibi çalışır: kaydedilmiş değer tarayıcıya
geri gönderilmez, boş bırakmak mevcut şifreyi korur. Mikro her istekte
şifrenin günün tarihiyle (`MD5("YYYY-AA-GG " + şifre)`) hashlenmesini
istediğinden, bu hash her sorguda otomatik ve taze hesaplanır — düz şifre
sadece veritabanında saklanır.

Eksik bir eşleme (bayi/ürün/KDV) varsa, o siparişin gönderimi otomatik olarak
"başarısız" işaretlenir ve hata mesajı ekranda görünür; eksik bilgi
tamamlandıktan sonra **Yeniden dene** ile tekrar kuyruğa alınabilir.

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
* **Kuru kim çeker?** Üretimde Celery Beat (15:35, iş günleri). Celery
  çalışmıyorsa hiçbir şey kuru çekmez — bu durumda *Sistem Ayarları* ekranındaki
  **Kuru şimdi çek** butonunu kullanın veya sunucuda şu komutu çalıştırın:

  ```bash
  python manage.py fetch_rates          # bugün + eksik son 7 gün
  python manage.py fetch_rates --days 30
  python manage.py fetch_rates --date 2026-09-01
  ```

  Kur güncel değilse *Sistem Ayarları* ekranı bunu uyarı olarak gösterir.
  Sunucunun `www.tcmb.gov.tr` adresine erişebilmesi gerekir.
* **Demo kuru gerçek kuru gölgelemez.** `seed_demo`, tabloda gerçek bir kur
  varsa demo kuru hiç eklemez; `fetch_rates` ise demo satırların üzerine yazar.
  Elle girilmiş (`MANUAL`) kurlar korunur, onları da tazelemek için
  `python manage.py fetch_rates --force` kullanın.
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
python manage.py test              # 104 test: iş kuralları, yetkiler, i18n, PDF, Excel
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
