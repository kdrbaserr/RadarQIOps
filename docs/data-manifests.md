# Checksum, lisans ve data manifest doğrulaması

Data manifest, raw dosyanın byte kimliğini, kaynağını ve kullanım koşullarını birlikte kaydeder.
Acquisition'ın dosyayı eksiksiz aktarması doğru veri setinin alındığını tek başına kanıtlamaz;
017 bu nedenle beklenen SHA-256 değerini zorunlu bir kabul kapısı yapar.

## Çalıştırma

[`configs/register.example.yaml`](../configs/register.example.yaml) yalnız yapı örneğidir. Gerçek
kayıt öncesinde checksum, kaynak sürümü, referans, lisans kimliği ve atıf doğrulanmış değerlerle
değiştirilmelidir.

```powershell
uv run radariq data register --config configs/register.yaml
```

Config, 016 acquisition alanlarına ek olarak şunları ister:

```json
{
  "expected_sha256": "64-karakterli-doğrulanmış-sha256",
  "manifest": {
    "path": "../data/manifests/dataset.json",
    "source_id": "dataset-stable-id",
    "source_version": "upstream-version",
    "source_reference": "yayıncı-sayfası-doi-veya-katalog-kaydı",
    "license": {
      "id": "SPDX-veya-açık-LicenseRef-kimliği",
      "attribution": "Kaynağın zorunlu atıf metni"
    }
  }
}
```

Eksik lisans kimliği veya atıf, dosya aktarımı başlamadan açık hatayla durur. Örnek config'teki
placeholder değerler gerçek veri kaydı için kabul kanıtı değildir.

## Streaming SHA-256 kapısı

Aktarılan her byte `.part` dosyasına yazılırken aynı anda SHA-256 hesabına eklenir. Hesaplanan
değer config'teki `expected_sha256` ile eşleşmeden nihai raw dosya yayımlanmaz. Uyuşmazlıkta
geçici dosya temizlenir, manifest yazılmaz ve pipeline başarısız olur.

Mevcut raw dosya yeniden kullanılacaksa SHA-256 tekrar hesaplanır. Dosyanın sonradan tek byte'ı
değişmiş olsa bile kayıt doğrulaması durur.

## Manifest şeması 1.0

Üretilen JSON aşağıdaki kanıtları taşır:

| Alan | Kanıt |
|---|---|
| `schema_version` | Manifest alanlarının hangi sözleşmeyle yorumlanacağı |
| `source.id` | Veri kaynağının projedeki sabit kimliği |
| `source.version` | Yayıncı/kaynak sürümü |
| `source.reference` | Kaynak sayfası, DOI veya katalog referansı |
| `source.access_method` | `http`, `local_file` veya `archive` erişim yöntemi |
| `file.name` | Kontrollü raw dosya adı |
| `file.size_bytes` | Dosyanın byte boyutu |
| `file.sha256` | Dosya içeriğinin değişmez kimliği |
| `license.id` | SPDX veya açık proje `LicenseRef` kimliği |
| `license.attribution` | Kaynağın gerekli atıf metni |
| `downloaded_at_utc` | Dosyanın kontrollü raw alana başarıyla alındığı UTC zamanı |

Manifest JSON'u sıralı anahtarlarla ve atomik `.part -> final` yazma yöntemiyle oluşturulur.
İkinci koşuda raw ve manifest birlikte doğrulanır; mevcut manifest yeniden yazılmaz ve ilk indirme
zamanı korunur.

## Tutarlılık ve fail-closed davranışı

Raw dosya ve manifest birlikte bulunmalı veya birlikte oluşturulmalıdır. Yalnız biri varsa sistem
otomatik tahmin veya onarım yapmaz. Bilinmeyen manifest sürümü, bozuk JSON, metadata değişimi,
checksum uyuşmazlığı veya eksik lisans G2 kapısını geçemez.

Manifest bir güven beyanıdır; yanlış girilmiş bir lisansı kendiliğinden doğru yapmaz. Lisans ve
atıf değerleri resmi kaynak sayfasından insan tarafından doğrulanmalıdır.
