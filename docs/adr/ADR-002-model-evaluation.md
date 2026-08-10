# ADR-002: Model değerlendirme metrikleri ve başarı iddiaları

- Durum: Kabul edildi
- Tarih: 9 Ağustos 2026
- Karar sahipleri: RadarIQops ürün ve mühendislik ekibi
- İlgili karar: [ADR-001 görev tanımı](ADR-001-task-definition.md)
- İlgili belgeler: [Ürün çerçevesi](../product-charter.md), [veri inceleme sözleşmesi](../data-inspect.md), [ML yaşam döngüsü mimarisi](../architecture/ml-lifecycle.md)

## Bağlam

Tek bir doğruluk yüzdesi; sınıf dengesizliğini, düşük SNR davranışını, güven skorlarının doğruluğunu ve çalışma maliyetini gizler. Özellikle “%90 başarılı” gibi veri seti, test bölmesi, SNR ve donanım bağlamı olmayan sabit bir ifade yeniden üretilebilir veya ürün açısından anlamlı değildir.

Bu karar, `modulation_classification` görevi için zorunlu değerlendirme sözleşmesini tanımlar. Yeni bir görev ADR-001'in yerini alırsa aynı metriklerin uygunluğu yeni görev için ayrıca değerlendirilir.

## Karar özeti

Bir model aşağıdaki ölçümlerin tamamı olmadan “değerlendirildi” veya “kabul edildi” sayılmaz:

| Alan | Zorunlu ölçüm | Yön |
|---|---|---|
| Birincil kalite | Macro-F1 | Yüksek daha iyi |
| Sınıf davranışı | Sınıf başına recall ve support | Recall yüksek daha iyi |
| Gürültü dayanımı | SNR dilimi başına Macro-F1 ve sınıf recall | Yüksek daha iyi |
| Kalibrasyon | ECE-15; ikincil olarak NLL ve Brier skoru | Düşük daha iyi |
| Dağıtım maliyeti | Model artifact boyutu ve parametre sayısı | Kullanım sınırına göre düşük daha iyi |
| Gecikme | Batch 1 uçtan uca p95 gecikme | Düşük daha iyi |
| Güvenilirlik | Çıkarım hata oranı; geçersiz girdi ret oranı ayrıca | Düşük daha iyi |

Genel accuracy yardımcı metrik olarak raporlanabilir ancak birincil metrik olamaz ve tek başına kabul kararı verdirmez.

## 1. Birincil metrik: Macro-F1

Her sınıf `c` için:

```text
precision_c = TP_c / (TP_c + FP_c)
recall_c    = TP_c / (TP_c + FN_c)
F1_c        = 2 * precision_c * recall_c / (precision_c + recall_c)
Macro-F1    = (1 / K) * sum(F1_c), c = 1..K
```

Kurallar:

- Her sınıf toplam sonuca eşit ağırlık verir.
- Paydanın sıfır olduğu durumda ilgili precision, recall veya F1 değeri `0` kabul edilir ve raporda uyarı üretilir.
- Test bölmesinde sözleşmedeki bir sınıfın hiç örneği yoksa sınıf sessizce ortalamadan çıkarılmaz; değerlendirme bölmesi geçersiz sayılır.
- Macro-F1 değeri `0–1` aralığında ham oran ve isteğe bağlı yüzde gösterimiyle raporlanır.
- Confusion matrix ve toplam örnek sayısı aynı raporda bulunur.

## 2. Sınıf başına recall

Her sınıf için aşağıdaki alanlar raporlanır:

```json
{
  "class_id": 0,
  "class_name": "BPSK",
  "recall": 0.0,
  "support": 0,
  "true_positive": 0,
  "false_negative": 0
}
```

Recall, gerçek bir sınıfa ait örneklerin ne kadarının doğru bulunduğunu gösterir. Yalnızca macro ortalama vermek yasaktır; düşük performanslı sınıflar görünür kalmalıdır. Support değeri olmadan recall yayımlanamaz.

## 3. SNR dilimi performansı

RadioML'nin 2 dB adımlı yaygın SNR düzeni için varsayılan dilimler:

| Dilim | SNR aralığı |
|---|---|
| `low` | `snr_db <= -8` |
| `mid` | `-6 <= snr_db <= 4` |
| `high` | `snr_db >= 6` |

Her dilimde en az şunlar raporlanır:

- Örnek sayısı.
- Macro-F1.
- Sınıf başına recall ve support.
- Dilimde bulunan en düşük ve en yüksek gerçek SNR değeri.

Ek olarak mevcut her tekil SNR değeri için Macro-F1 eğrisi üretilir. Tek bir “ortalama SNR performansı” dilimlerin yerine geçemez.

Farklı SNR aralığı veya adımı kullanan veri setinde sınırlar test sonuçları görülmeden önce deney manifestinde tanımlanabilir. Değişiklik gerekçesi kaydedilir. Kaynakta SNR bulunmuyorsa alan `null` kalır; SNR dilimi metriği üretilmez ve model için SNR dayanıklılığı iddia edilemez.

## 4. Kalibrasyon

Bir örneğin güveni, seçilen sınıf için modelin verdiği en yüksek normalize olasılıktır. Logit değerleri doğrudan güven olarak kullanılamaz.

Birincil kalibrasyon metriği 15 eşit genişlikli güven aralığıyla Expected Calibration Error'dır (`ECE-15`):

```text
ECE = sum((|B_m| / n) * |accuracy(B_m) - confidence(B_m)|), m = 1..15
```

Şunlar birlikte raporlanır:

- `ECE-15`.
- Negatif log-likelihood (`NLL`).
- Çok sınıflı Brier skoru.
- 15 dilimli reliability diagram için dilim sayıları, ortalama güven ve accuracy.

Temperature scaling gibi bir kalibrasyon yöntemi kullanılırsa yalnızca validation bölmesinde ayarlanır. Kalibrasyon öncesi ve sonrası sonuçlar test bölmesinde ayrı raporlanır; test verisi kalibrasyon parametresi seçmek için kullanılamaz.

## 5. Model boyutu

İki ayrı değer zorunludur:

1. **Artifact boyutu:** Dağıtılan model dosyasının byte cinsinden gerçek dosya boyutu.
1. **Parametre sayısı:** Eğitilebilir ve toplam parametre sayısı.

MiB gösterimi şu şekilde hesaplanır:

```text
model_size_mib = model_size_bytes / 1_048_576
```

Framework, ağırlık hassasiyeti (`float32`, `float16`, `int8`), sıkıştırma/quantization ve dosya formatı kaydedilir. Yalnızca bellekte tahmin edilen parametre boyutu artifact boyutu olarak raporlanamaz. Çalışma zamanı veya bağımlılık paketi boyutu dağıtım açısından önemliyse ayrı `runtime_size_bytes` alanında verilir.

## 6. p95 gecikme

Birincil gecikme ölçümü `batch_size=1` için uçtan uca yerel çıkarım süresidir:

```text
doğrulanmış tensör -> ön işleme -> model -> olasılık/etiket çıktısı
```

Diskten veri okuma, ağ aktarımı ve kullanıcı arayüzü bu ölçüme dahil edilmez; gerekiyorsa ayrı ölçülür.

Ölçüm protokolü:

- Donanım modeli, işletim sistemi, Python/runtime, model framework sürümü ve thread ayarları kaydedilir.
- En az 50 ısınma çalıştırması sonuçlara dahil edilmez.
- En az 1.000 ölçümlü çalıştırma yapılır.
- GPU veya asenkron hızlandırıcı kullanılıyorsa zaman ölçümünden önce/sonra cihaz senkronize edilir.
- Aynı giriş sözleşmesi ve `batch_size=1` kullanılır.
- `p50`, `p95`, `p99`, ortalama ve ölçüm sayısı raporlanır.
- p95, sıralı ölçümlerde deneylerin en az %95'ini kapsayan gözlenen gecikme değeri olarak hesaplanır.

Farklı donanımlarda ölçülen gecikmeler tek bir sayı altında birleştirilemez.

## 7. Hata oranı

Çıkarım hata oranı:

```text
inference_error_rate = failed_inference_count / attempted_valid_inference_count
```

Başarısız çıkarım aşağıdakilerden en az birini içerir:

- Yakalanmamış veya işlem sonucunu engelleyen exception.
- Timeout.
- NaN/Infinity içeren model çıktısı.
- Beklenen sınıf sayısı veya JSON çıktı şemasıyla uyuşmayan sonuç.
- Geçerli giriş için etiket/olasılık üretilememesi.

Şema, shape veya dtype kontrolünden geçmeyen girdiler model hatası sayılmaz. Bunlar ayrıca raporlanır:

```text
invalid_input_rejection_rate = rejected_invalid_input_count / attempted_input_count
```

Hata oranı raporu pay ve paydayı birlikte içermelidir. Yalnızca `%0 hata` yazılması yeterli değildir.

## Değerlendirme protokolü

- Veri seti sürümü, kaynak URL, dosya checksum'ları ve `radariq data inspect` çıktısı kaydedilir.
- Eğitim, validation ve test bölmeleri model eğitilmeden önce sabitlenir.
- Varsa `group_id` veya `sequence_id` farklı bölmelere sızamaz.
- Model ve hiperparametre seçimi yalnızca eğitim/validation verisiyle yapılır.
- Test bölmesi nihai aday başına bir kez değerlendirilir; test sonucuna bakarak eşik veya model seçilip aynı sonuç nihai diye yayımlanamaz.
- Random seed, ön işleme, sınıf sırası ve kullanılan commit SHA rapora eklenir.
- En iyi tek koşu yerine önceden tanımlanan seed'lerin ortalaması ve standart sapması verilir; tek koşu kullanılırsa açıkça belirtilir.

## Zorunlu rapor sözleşmesi

Her nihai değerlendirme makinece okunabilir bir JSON dosyası üretir. Asgari yapı:

```json
{
  "task_id": "modulation_classification",
  "dataset": {
    "name": "example",
    "version": "example",
    "test_samples": 0,
    "split_strategy": "group_or_sequence"
  },
  "quality": {
    "macro_f1": 0.0,
    "accuracy": 0.0,
    "per_class": [],
    "snr_slices": {},
    "snr_curve": []
  },
  "calibration": {
    "ece_15": 0.0,
    "nll": 0.0,
    "brier": 0.0,
    "method": "none"
  },
  "artifact": {
    "model_size_bytes": 0,
    "model_size_mib": 0.0,
    "trainable_parameters": 0,
    "total_parameters": 0,
    "precision": "float32"
  },
  "latency": {
    "batch_size": 1,
    "samples": 1000,
    "p50_ms": 0.0,
    "p95_ms": 0.0,
    "p99_ms": 0.0,
    "hardware": "example"
  },
  "reliability": {
    "attempted_valid_inference_count": 0,
    "failed_inference_count": 0,
    "inference_error_rate": 0.0,
    "attempted_input_count": 0,
    "rejected_invalid_input_count": 0,
    "invalid_input_rejection_rate": 0.0
  }
}
```

Örnekteki `0` değerleri hedef veya varsayılan başarı değeri değildir; alan tipini gösteren yer tutuculardır.

## Sabit yüzde 90 iddiası

Aşağıdaki genel ifadeler yasaktır:

- “Model %90 başarılıdır.”
- “Doğruluk en az %90'dır.”
- Veri seti, test bölmesi, SNR aralığı ve sınıf dağılımı belirtilmeden verilen benzer başarı yüzdeleri.

Repo taramasında bu karar tarihinde kaldırılacak mevcut bir `%90` ifadesi bulunmamıştır. Bu ADR, böyle bir iddianın ileride bağlamsız biçimde eklenmesini engeller.

Bir kabul eşiği gerekiyorsa:

- Ürün senaryosu ve hata maliyetinden türetilir.
- Test sonucu görülmeden önce deney/kabul manifestinde yazılır.
- Macro-F1, kritik sınıf recall'u, düşük SNR performansı, ECE, p95 gecikme ve hata oranı için ayrı eşikler içerir.
- Veri seti, sürüm, donanım ve çalışma koşullarıyla birlikte ifade edilir.
- Yeni veri setine veya donanıma otomatik olarak taşınmaz.

## Sonuçlar

- Birincil model sıralaması Macro-F1 ile yapılır.
- Sınıf veya düşük SNR başarısızlığı genel ortalamayla gizlenemez.
- Yüksek sınıflandırma skoru tek başına dağıtıma kabul anlamına gelmez.
- Kalibrasyon, boyut, gecikme ve hata oranı model kartının zorunlu bölümleridir.
- Pazarlama veya README başarı iddiası, bu ADR'ye uygun sürümlenmiş değerlendirme raporuna bağlanmalıdır.
