# Değişmez raw ingestion

Raw ingestion, checksum ve lisans manifesti doğrulanmış ZIP/TAR arşivini sürümlü bir raw stage'e
açar. Acquisition arşiv byte'larını korur; ingestion ise arşiv üyelerini güvenli biçimde yayımlar
ve sonraki validation aşamasının kullanacağı deterministik örnek kimliklerini üretir.

## Çalıştırma

[`configs/ingest.example.yaml`](../configs/ingest.example.yaml) içindeki yollar config dosyasının
bulunduğu dizine göre çözülür:

```json
{
  "archive_path": "../data/raw/downloads/dataset-2026.08.zip",
  "raw_root": "../data/raw/ingested",
  "source_id": "dataset-stable-id",
  "source_version": "2026.08"
}
```

```powershell
uv run radariq data ingest --config configs/ingest.yaml
```

Çıktı `raw_root/source_id/source_version` dizinidir. `source_id` ve `source_version` güvenli path
bileşenleridir; kaynak içeriği değiştiğinde yeni `source_version` kullanılması zorunludur.

## Deterministik manifest ve örnek kimliği

`manifest.json`, makineye özel mutlak yollar ve çalışma zamanı içermez. Arşiv SHA-256 değeri,
kaynak kimliği/sürümü ve arşiv içi yol sırasına göre kararlı JSON olarak yazılır. Her normal dosya
bir raw kayıt kabul edilir ve şu alanları taşır:

- arşiv içindeki normalize göreli yol;
- byte boyutu ve SHA-256;
- `source_id`, `source_version`, göreli yol ve içerik SHA-256 üzerinden üretilmiş `sample_id`.

Aynı arşiv aynı kaynak kimliğiyle farklı makine veya kök dizinde işlendiğinde aynı manifest
byte'ları ve manifest SHA-256 değeri oluşur.

## Atomiklik ve değişmezlik

Arşiv önce nihai sürüm dizininin yanında `.part` geçici dizinine açılır. Tüm üyeler okunup
hash'lendikten ve manifest diske aktarıldıktan sonra dizin tek adımla yayımlanır. Mutlak yollar,
`..` kaçışı, symlink/hardlink, özel dosyalar, şifreli ZIP üyeleri ve çakışan yollar reddedilir.

Mevcut sürüm tekrar çalıştırıldığında hiçbir dosya yazılmaz. Manifest, arşiv hash'i, dosya kümesi,
boyutlar, içerik hash'leri ve örnek kimlikleri yeniden doğrulanır. Eksik, eklenmiş veya değiştirilmiş
tek bir raw dosya `RawMutationError` üretir; ingestion mevcut raw alanı sessizce onarmaz.
