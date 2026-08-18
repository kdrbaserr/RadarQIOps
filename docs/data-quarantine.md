# Quarantine manifesti ve veri kalite raporu

022, 020 validation ve 021 duplicate/leakage bulgularını eğitim uygunluğu kararına dönüştürür.
Quarantine raw örneği silmez, taşımaz veya değiştirmez; yalnız örneğin sonraki preprocessing ve
split aşamalarına girip giremeyeceğini sürümlü manifestlerle kaydeder. Gerçek veri çalıştırması
026'da Colab/DVC hattından yapılır; lokal testler yalnız küçük sentetik fixture kullanır.

## Karar politikası

[`configs/quarantine.example.yaml`](../configs/quarantine.example.yaml) ilk sürümün fail-closed
davranışını sabitler:

- 020 kalite hataları ilgili örneği quarantine eder.
- Aynı label'lı exact duplicate kümesinde sıralı en küçük `sample_id` canonical tutulur; diğerleri
  `duplicate_of` kanıtıyla quarantine edilir.
- Exact duplicate label çatışmasında kümenin tamamı quarantine edilir; doğru label tahmin edilmez.
- Near duplicate çiftlerinin iki tarafı similarity kanıtıyla incelemeye ayrılır.
- `group.unresolved` örnekleri raw açısından korunur fakat group-aware split'e gönderilmez.
- Verilmiş split atamasında bulunan group/exact/near leakage örnekleri dışlanır.

Politika davranışları config'te açıkça adlandırılır. Yeni otomatik karar türü eklemek sessiz config
değişikliği değil kod, test ve politika sürümü değişikliği gerektirir.

## Artifact sözleşmesi

Atomik ve immutable output dizini dört dosya içerir:

| Dosya | Amaç |
|---|---|
| `accepted-manifest.json` | Sonraki aşamaya geçebilen sıralı sample kimlikleri |
| `quarantine-manifest.json` | Hata kodu, neden, duplicate ilişkisi ve kanıtlar |
| `validation-report.json` | CI/DVC için tam makine-okunur karar ve sayımlar |
| `validation-report.md` | İnsan incelemesi için özet, hata dağılımı ve soy ağacı |

Her karar raw manifesti, validation/leakage policy hash'leri ve iki giriş raporunun hash'lerine
bağlanır. Çalışma saati veya mutlak makine yolu içermediği için aynı input aynı artifact byte'larını
üretir. Mevcut output aynıysa `reused` döner; farklı içerik aynı yolun üzerine yazılmaz.

Zorunlu invariant'lar:

```text
total_count = accepted_count + quarantine_count
accepted ∩ quarantine = ∅
accepted ∪ quarantine = bütün sample_id değerleri
```

021 yalnız 020 tarafından kabul edilmiş örneklerde çalışır. Bu nedenle leakage raporunun sample
kümesi validation raporundaki `valid_sample_ids` kümesine tam eşit değilse artifact yazımı
başlamadan işlem durur. Toplam evren yine validation raporundaki kabul ve ret örneklerinin
birleşimidir. İnsan raporundaki kanıt örnekleri sample kimliğine göre deterministik seçilir; tam
karar quarantine manifestinde korunur.
