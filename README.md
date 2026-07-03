# Selenay & Ahmet — Düğün Fotoğraf Paylaşım Uygulaması

## Özellikler
- Modern, düğün temalı tasarım
- Büyük fotoğraf yükleme butonu (çoklu seçim)
- İsteğe bağlı isim alanı
- Gerçek zamanlı yükleme ilerleme çubuğu
- Başarılı yüklemede konfeti animasyonu
- Telegram Bot entegrasyonu — fotoğraflar **belge (document)** olarak gönderildiği için sıkıştırılmadan, orijinal kalitede sana ulaşır
- Yönetici paneli (admin girişi ile yüklenen tüm fotoğrafları görüntüleme)

## Yerelde çalıştırma

```bash
pip install -r requirements.txt
python app.py
```

Uygulama `http://localhost:5000` adresinde açılır.

## Ortam Değişkenleri

| Değişken | Açıklama | Zorunlu mu? |
|---|---|---|
| `SECRET_KEY` | Flask oturum şifreleme anahtarı | Evet (prod) |
| `ADMIN_USER` | Yönetici paneli kullanıcı adı | Evet (prod) |
| `ADMIN_PASS` | Yönetici paneli şifresi | Evet (prod) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token'ı | Hayır (yoksa Telegram gönderimi atlanır) |
| `TELEGRAM_CHAT_ID` | Fotoğrafların gönderileceği sohbet/kanal ID'si | Hayır |
| `UPLOAD_FOLDER` | Fotoğrafların diskte saklanacağı klasör | Hayır (varsayılan: `uploads`) |

`SECRET_KEY`, `ADMIN_USER`, `ADMIN_PASS` ayarlanmazsa uygulama yine çalışır ama
**varsayılan admin şifresi `1234` olur ve her yeniden başlatmada oturumlar sıfırlanır.**
Canlıya almadan önce bunları mutlaka Render panelinden ortam değişkeni olarak girin.

## Telegram Bot Kurulumu

1. Telegram'da **@BotFather**'a git, `/newbot` komutuyla yeni bir bot oluştur, sana verdiği
   **token**'ı kopyala.
2. Fotoğrafların düşmesini istediğin bir Telegram sohbeti (kendi hesabın, bir grup veya kanal) belirle.
3. Sohbet ID'sini öğrenmek için:
   - Bota (veya eklediğin gruba) bir mesaj gönder.
   - Tarayıcıda şu adresi aç: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Dönen JSON içindeki `chat` → `id` alanını al (gruplarda genelde `-` ile başlar).
4. Render'da (veya yerelde `.env`) şu iki ortam değişkenini ekle:
   ```
   TELEGRAM_BOT_TOKEN=123456789:AA...
   TELEGRAM_CHAT_ID=123456789
   ```
5. Bu iki değişken tanımlıysa, her yüklenen fotoğraf otomatik olarak bota **belge**
   olarak gönderilir (misafir ismi varsa açıklama olarak eklenir). Değişkenler
   tanımlı değilse uygulama normal çalışmaya devam eder, sadece Telegram'a gönderim yapılmaz.

## Render'a Deploy Etme

1. Bu klasörü bir GitHub reposuna yükle.
2. Render'da **New → Web Service** oluştur, repoyu seç.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app` (Procfile zaten bunu tanımlıyor)
5. Environment sekmesinden yukarıdaki ortam değişkenlerini ekle.
6. Deploy et.

> Not: Render'ın ücretsiz planında disk kalıcı değildir — servis yeniden başladığında
> `uploads` klasöründeki dosyalar silinebilir. Bu yüzden Telegram entegrasyonu asıl
> yedekleme/arşiv yöntemin olsun; fotoğraflar her yüklendiğinde anında Telegram'a düşer.

## Güvenlik notları
- Admin şifresi ortam değişkeninden okunur, kodda sabit yazılı değildir.
- Dosya adları `uuid` ile yeniden üretilir, kullanıcıdan gelen dosya adı doğrudan diskte kullanılmaz.
- Sadece resim uzantılarına (`png, jpg, jpeg, webp, heic, heif`) izin verilir.
- Tek istekte en fazla 25MB yüklenebilir.
- `/uploads/<dosya>` erişimi artık sadece admin oturumu ile mümkündür.
