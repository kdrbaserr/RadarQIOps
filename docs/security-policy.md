# Güvenlik ve bağımlılık politikası

`PR Security` workflow'u her `main` pull request'inde iki merge kapısı üretir:

- `pr-security-policy`: Git tarafından takip edilen bütün dosyalarda yeni secret arar ve istisna kayıtlarını doğrular.
- `pr-dependency-security`: Kilitli bağımlılıkların tamamını bilinen zafiyetler, runtime/serve bağımlılıklarını da lisanslar açısından inceler.

## Zafiyet eşiği

`pip-audit`, `uv.lock` içindeki üretim ve geliştirme bağımlılıklarının tamamını denetler. Politika yol haritasındaki high/critical eşiğinden daha sıkıdır: istisnası bulunmayan herhangi bir bilinen zafiyet PR'ı başarısız yapar. Yapılandırma `security/policy.yml` dosyasındadır.

## Lisanslar

Yalnız `security/policy.yml` içindeki lisanslar kabul edilir. Tarama ürüne dağıtılan core ve serve bağımlılıklarını kapsar; yalnız geliştirmede kullanılan ve ürüne dağıtılmayan lint/test araçları lisans merge kapısına dahil değildir. Listede olmayan lisans merge'i engeller.

## İstisnalar

Kalıcı veya sözlü istisna yoktur. Zorunlu bir istisna `security/exceptions.yml` içinde `kind`, `id`, `package`, `owner`, `reason`, `approved_on` ve `expires_on` alanlarıyla kaydedilir. Denetim araçları yalnız bu aktif kayıtları dikkate alır.

İstisna en fazla 90 gün geçerlidir. Süresi dolan veya eksik kayıt `pr-security-policy` kontrolünü durdurur.

Secret yanlışlıkla Git'e girdiyse yalnız dosyadan silmek yeterli değildir; ilgili anahtar sağlayıcı tarafında iptal edilmeli ve yenisi üretilmelidir. Gerçek secret değerleri hiçbir istisna dosyasına veya baseline'a eklenmez.
