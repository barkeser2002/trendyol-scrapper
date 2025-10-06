# Trendyol Ürün Arama Platformu

Bu proje, Trendyol üzerinde metin tabanlı arama yapıp sonuçları satıcı bazında zenginleştirilmiş Excel dosyası olarak sunan Flask tabanlı bir web uygulamasıdır. Arama işlemi arka planda yürütülürken web arayüzünde canlı bir progress bar ile ilerleme takip edilebilir.

## Özellikler

- Selenium ile arama sonuçlarının birden çok sayfasını (`pi` parametresi) gezerek 24'ten fazla ürün kartını toplar.
- Ürün detay sayfasındaki gömülü JSON'dan kategori, marka, ürün kodu, görseller ve satıcı listesini ayrıştırır.
- Ana satıcıya ek olarak tüm diğer satıcıları ayrı satırlar halinde Excel'e yazar.
- Primary ve Other satıcıların kurumsal verilerini (resmî ünvan, şehir, kayıtlı e-posta, vergi numarası) satıcı mağaza sayfasından gerektiğinde çekerek doldurur.
- Bootstrap 5 tabanlı, Font Awesome ikonları kullanan responsive bir arayüz sunar; tema düğmesiyle açık/koyu mod arasında tek tıkla geçiş yapılabilir.
- Web arayüzünde progress bar ile ilerleme durumu, tamamlandığında indirme bağlantısı gösterilir.
- Flask sunucusu varsayılan olarak `http://localhost:26888` adresinde çalışır.

## Ön Gereksinimler

- Python 3.10+ (geliştirme makinesi için)
- Google Chrome veya Chromium tarayıcısı (yerel çalıştırma için)
- Docker ve Docker Compose (opsiyonel, konteynerle çalıştırmak için)

## Kurulum

1. Depoyu açın ve proje klasörüne geçin:

	```powershell
	cd c:\Users\bkese\Desktop\sss
	```

2. Gerekli Python paketlerini yükleyin:

	```powershell
	python -m pip install -r requirements.txt
	```

> Not: Uygulama sistemde Chrome/Chromium tarayıcısının yüklü olduğunu varsayar. Selenium 4'ün Selenium Manager bileşeni uygun sürücüleri çalışırken indirip kullanır.

### Yapılandırma

- Toplanacak maksimum sayfa sayısı `TRENDYOL_MAX_PAGES` ortam değişkeniyle ayarlanabilir (varsayılan `7`). Örneğin 10 sayfa gezmek için:

	```powershell
	$env:TRENDYOL_MAX_PAGES=10
	python app.py
	```
- Excel çıktıları varsayılan olarak proje kökündeki `outputs/` klasörüne kaydedilir.

## Çalıştırma

1. Flask uygulamasını başlatın:

	```powershell
	python app.py
	```

2. Tarayıcıda `http://localhost:26888` adresini açın.
3. Aramak istediğiniz anahtar kelimeyi yazıp aramayı başlatın.
4. Progress bar ilerlemesini izleyin; işlem tamamlandığında Excel dosyasını indirin.
5. Sağ üstteki "Siyah Tema" düğmesini kullanarak açık/koyu mod arasında geçiş yapabilirsiniz.

## Excel Çıktısı

Her satır bir ürün-satıcı kombinasyonunu temsil eder ve aşağıdaki sütunları içerir:

- Product ID
- Product Name
- Product Code
- Brand
- Category Name
- Category Hierarchy
- Category ID (Boutique ID)
- Product URL
- Image URLs (birden çok görsel `|` ile ayrılır)
- Merchant Type (Primary/Other)
- Merchant ID
- Merchant Name
- officialName
- cityName
- registeredEmailAddress
- taxNumber
- sellerLink
- Price Text
- Price Value
- Currency
- Listing ID
- Stock
- Fulfilment Type
- isTyPlusEligible

## Alternatif: Komut Satırından Kullanım

Grafik arayüz olmadan tek seferlik çıktı almak için `trendyol_search.py` dosyasını doğrudan çalıştırabilir ve metin tabanlı ilerleme bilgisiyle Excel çıktısı oluşturabilirsiniz.

```powershell
python trendyol_search.py
```

## Docker ile Çalıştırma

Uygulamayı konteynerde çalıştırmak için depo kökünde sağlanan `Dockerfile` ve `docker-compose.yml` dosyalarını kullanabilirsiniz.

1. İmajı oluşturup konteyneri başlatın:

	```powershell
	docker compose up --build
	```

2. Uygulama `http://localhost:26888` adresinde yayına girecektir.

3. Üretilen Excel dosyaları yerel makinedeki `outputs/` klasörüne bind edildiği için konteyner kapatılsa dahi dosyalar korunur.

Varsayılan maksimum sayfa sınırını konteyner içinde güncellemek için (ör. 5 sayfa):

```powershell
docker compose run --rm -e TRENDYOL_MAX_PAGES=5 web
```

Arka planda (detached) çalıştırmak isterseniz:

```powershell
docker compose up --build -d
```

Konteyneri durdurmak için:

```powershell
docker compose down
```

## Notlar

- Trendyol tarafındaki güvenlik doğrulamaları zaman zaman isteği reddedebilir; böyle bir durumda uygulamayı yeniden başlatıp tekrar denemeniz gerekebilir.
- Bazı satıcılar kurumsal bilgilerini paylaşmadığı için ilgili alanlar "N/A" olarak kalabilir.
- Satıcı sayısı fazla olan aramalarda işin tamamlanması birkaç dakika sürebilir; progress bar güncel durumu gösterir.
- Konteynerde Selenium'un Chromium'u başlatabilmesi için yeterli bellek ayırdığınızdan emin olun (minimum 512 MB önerilir).

## Sorun Giderme

- **`chrome not reachable` / `DevToolsActivePort file doesn't exist`**: Headless tarayıcıyı başlatmak için makinenizde yeterli RAM olduğundan emin olun. Docker kullanıyorsanız konteyner belleğini artırın.
- **`Access Denied` veya Trendyol doğrulama hataları**: Aynı sorguyu kısa aralıklarla tekrarlamamak ve gerektiğinde farklı anahtar kelimeler denemek işe yarar.
- **`TRENDYOL_MAX_PAGES` değiştirilmesine rağmen sonuçlar sınırlı**: Aranan anahtar kelime daha az sonuç döndürüyor olabilir. Loglarda sayfa sayısı mesajlarını kontrol edin.