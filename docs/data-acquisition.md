# Yapılandırılabilir veri edinimi

Acquisition aşaması, kaynak dosyayı değiştirmeden `data/raw` sınırına taşır. Kaynak biçimini
I/Q sözleşmesine dönüştürmez ve arşivi açmaz. Bu ayrım bilinçlidir: acquisition yalnız eksiksiz
byte aktarımından, 019 raw ingestion örnek kimliği ve içerik dönüşümünden sorumludur.

## Kaynak adapterleri

| `source.type` | Kaynak | Davranış |
|---|---|---|
| `http` | `http://` veya `https://` URL | Stream ederek indirir; timeout ve retry uygular |
| `local_file` | Kullanıcının yerel dosyası | Dosyayı aynı atomik yazma yoluyla raw hedefe kopyalar |
| `archive` | Kullanıcının yerel ZIP/TAR arşivi | Formatı doğrular, arşivi açmadan raw hedefe kopyalar |

Adapter yalnız kaynağı okunabilir stream olarak açar. Hedef dosyanın nasıl yazılacağı bütün
adapterler için aynı ortak kodda tutulur. Böylece HTTP ve yerel dosya yolları farklı güvenlik
davranışları geliştirmez.

## Config

Örnek yapılandırma [`configs/acquire.example.yaml`](../configs/acquire.example.yaml) dosyasındadır.
Göreli `location` ve `destination` yolları config dosyasının bulunduğu dizine göre çözülür.

```json
{
  "source": {
    "type": "http",
    "location": "https://example.org/dataset.zip"
  },
  "destination": "../data/raw/dataset.zip",
  "max_attempts": 3,
  "timeout_seconds": 30,
  "retry_delay_seconds": 1,
  "chunk_size_bytes": 1048576
}
```

Komut:

```powershell
uv run radariq data acquire --config configs/acquire.yaml
```

Başarılı ilk koşu `status=acquired` ve gerçek deneme sayısını döndürür. Hedef zaten varsa
`status=reused`, `attempts=0` döner ve mevcut dosyanın tek byte'ı dahi değiştirilmez.

## Atomik yazma

Aktarım doğrudan nihai hedef adına yapılmaz:

1. Hedefle aynı dizinde benzersiz `.part` dosyası oluşturulur.
1. Kaynak parça parça bu geçici dosyaya yazılır.
1. Kaynağın byte boyutu biliniyorsa alınan byte sayısıyla karşılaştırılır.
1. Dosya içeriği işletim sistemine `flush` ve `fsync` ile teslim edilir.
1. Yalnız eksiksiz aktarımda `os.replace` ile nihai hedef adına atomik geçirilir.
1. Her hata yolunda `.part` dosyası kaldırılır ve kurala göre yeniden denenir.

Bu nedenle işlem yarıda kesilirse `data/raw/dataset.zip` adıyla bozuk bir dosya görülmez.
Sonraki aşamalar yalnız nihai hedef adına bakarak eksik aktarımı gerçek ham veri sanmaz.

## Idempotency ve değişmez hedef

Aynı config ikinci kez çalıştırıldığında mevcut hedef tekrar indirilmez ve üzerine yazılmaz.
Config yeni kaynak sürümü için yeni destination yolu kullanmalıdır. 017 aşaması kaynak ve hedef
SHA-256 değerini manifeste bağlayarak mevcut dosyanın beklenen sürüm olduğunu ayrıca kanıtlar.

016'nın garantisi “mevcut hedefi değiştirme”dir; içeriğin doğru veri seti olduğunu tek başına
iddia etmez. İçerik kimliği, lisans ve provenance doğrulaması 017'nin sorumluluğudur.
