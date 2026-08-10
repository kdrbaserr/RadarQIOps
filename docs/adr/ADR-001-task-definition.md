# ADR-001: ML görev adının ve etiket semantiğinin sabitlenmesi

- Durum: Kabul edildi
- Tarih: 9 Ağustos 2026
- Karar sahipleri: RadarIQops ürün ve mühendislik ekibi
- İlgili belgeler: [Ürün çerçevesi](../product-charter.md), [veri seti değerlendirmesi](../dataset-evaluation.md), [`data inspect` sözleşmesi](../data-inspect.md), [ADR-002 model değerlendirmesi](ADR-002-model-evaluation.md), [ML yaşam döngüsü mimarisi](../architecture/ml-lifecycle.md)

## Bağlam

RadarIQops kapsamında iki farklı problem adı kullanılabilir:

1. **Gerçek radar hedef sınıflandırması:** Radar ölçümünden otomobil, yaya, gemi, uçak veya askerî araç gibi fiziksel bir hedef sınıfını tahmin etmek.
1. **Modülasyon sınıflandırması:** Bir I/Q sinyal penceresinden BPSK, QPSK, QAM veya FM gibi haberleşme modülasyon türünü tahmin etmek.

Bu görevler aynı değildir. RadioML/DeepSig etiketleri fiziksel hedefi değil sinyalin modülasyon biçimini temsil eder. Buna rağmen görev yalnızca “radar sınıflandırması” olarak adlandırılırsa kullanıcı, model çıktısını gerçek hedef teşhisi sanabilir.

Projede henüz kabul kontrolünden geçmiş, lisansı doğrulanmış ve fiziksel hedef etiketleri taşıyan gerçek radar hedef verisi bulunmamaktadır. Mevcut ürün çerçevesi de bu koşul sağlanmadan ürünün hedef sınıflandırıcı olarak sunulmasını yasaklar.

## Karar

Mevcut ML görevinin bağlayıcı adı:

> **Radyo sinyali modülasyon sınıflandırması araştırma prototipi**

Teknik görev kimliği:

```text
modulation_classification
```

İngilizce karşılığı:

```text
Automatic Modulation Classification (AMC) research prototype
```

Kod, yapılandırma, metrik, deney kaydı, API, arayüz ve dokümantasyonda bu görev için `modulation_classification` adı kullanılacaktır.

Şu adlar mevcut görev için kullanılamaz:

- `radar_target_classification`
- `target_classification`
- “gerçek radar hedef sınıflandırması”
- “otomatik hedef tanıma” veya `automatic target recognition (ATR)`
- “hedef teşhisi”

Bu karar, RadioML kullanımını zorunlu kılmaz. RadioML dışındaki bir veri seti aynı görevde kullanılacaksa etiketlerinin yine modülasyon biçimini temsil etmesi ve veri kabul kontrolünden geçmesi gerekir.

## Etiket semantiği

Model girdisi, belirli uzunluktaki sayısal bir I/Q sinyal penceresidir. Model etiketi, bu pencereyi üretmek için kullanılan veya pencereye atanmış **modülasyon ailesi/türüdür**.

Örnek etiketler:

- Faz kaydırmalı anahtarlama: `BPSK`, `QPSK`, `8PSK`.
- Genlik/faz modülasyonu: `16QAM`, `64QAM`.
- Frekans tabanlı modülasyon: `GFSK`, `CPFSK`, `WBFM`.
- Genlik modülasyonu: `AM-DSB`, `AM-SSB`.

Kesin sınıf listesi veri seti sürümüne bağlıdır. Her deney, veri seti manifestinde sıralı `class_id -> class_name` eşlemesini saklamalıdır. RadioML 2016 ve RadioML 2018 sınıf uzayları aynı kabul edilemez.

Bir modülasyon etiketi aşağıdakilerin hiçbirini ifade etmez:

- Fiziksel hedef türü veya kimliği.
- Sinyal yayıcının araç, uçak, gemi ya da başka bir platform olması.
- Dost/düşman, tehdit veya angajman durumu.
- Radar hedefinin konumu, menzili, hızı veya radar kesit alanı.
- Sinyalin gerçek sahada belirli bir cihazdan kaydedildiği.

SNR ayrı bir koşul/üstveri alanıdır; sınıf etiketi değildir. Sentetik veri setindeki SNR, veri üretim ayarını ifade edebilir ve bağımsız saha ölçümü olarak sunulamaz.

## Veri kabul sözleşmesi

Bir veri seti bu görevde kullanılmadan önce aşağıdaki kayıt üretilmelidir:

```powershell
radariq data inspect `
  --dataset <aday> `
  --path <veri-yolu> `
  --sample-index 0 `
  --output inspection.json
```

`inspection.json` içinde en az şu alanlar doğrulanmalıdır:

- `shape` ve `dtype` model giriş sözleşmesiyle uyumlu olmalı.
- `label` açık bir modülasyon sınıfına çözümlenmeli.
- `snr_db` yoksa `null` kalmalı; tahmin edilmemeli.
- `group_id` ve `sequence_id` varsa veri bölme sırasında korunmalı.
- Sınıf eşleme dosyası, veri seti sürümü ve checksum'lar deney manifestine eklenmeli.

Pickle tabanlı RadioML 2016 verisi yalnızca güvenilir kaynaktan indirildikten ve checksum'u doğrulandıktan sonra `--allow-unsafe-pickle` ile açılabilir.

## Bilinen sınırlamalar

- RadioML açık sürümleri sentetik veya simüle edilmiş kanal etkileri içerir; gerçek saha dağılımını temsil ettiği varsayılamaz.
- Modülasyon başarımı, fiziksel radar hedeflerini ayırt etme başarımına çevrilemez.
- SNR kırılımındaki doğruluk yalnızca veri setinin SNR üretim ve etiketleme yöntemine göre anlamlıdır.
- Veri seti sürümleri farklı örnek uzunluklarına, sınıf listelerine ve kanal modellerine sahiptir; sonuçlar doğrudan karşılaştırılamaz.
- Yakın veya aynı üretim akışından gelen örneklerin rastgele bölünmesi veri sızıntısına yol açabilir. Varsa `group_id`/`sequence_id` temelinde bölme yapılmalıdır.
- RadioML açık veri setlerinin CC BY-NC-SA 4.0 koşulları ticari ürün kullanımını ve dağıtımını sınırlar.
- RadioML 2016 pickle biçimi güvenilmeyen dosyalarda kod çalıştırma riski taşır.
- Bu karar bir araştırma prototipinin adını tanımlar; operasyonel güvenilirlik, güvenlik-kritik kullanım veya ticari ürün uygunluğu iddiası oluşturmaz.

## Sonuçlar

- Model çıktıları “modülasyon tahmini” veya “modülasyon skoru” olarak gösterilir.
- Başarı metrikleri modülasyon sınıfı ve SNR kırılımında raporlanır.
- Arayüzde veya API'de çıktı alanı `target_class` olarak adlandırılamaz; `modulation_class` kullanılmalıdır.
- RadioML ile elde edilen sonuçlar hedef sınıflandırma doğruluğu başlığı altında yayımlanamaz.
- Fiziksel radar hedef verisi için geliştirilecek okuyucu ve model hattı bu görevle aynı deney serisine sessizce eklenemez.

## Yeniden değerlendirme koşulları

“Gerçek radar hedef sınıflandırması” görevine geçiş ancak aşağıdaki koşulların tamamı sağlandığında değerlendirmeye alınır:

1. Gerçek radar ölçümünden oluşan veri seti resmen seçilmiş olmalı.
1. Etiketler fiziksel hedef sınıflarını temsil etmeli ve sınıf ontolojisi yazılı olmalı.
1. Veri lisansı; amaçlanan araştırma/ticari kullanıma, türetilmiş çıktılara ve gerekli yeniden dağıtıma açıkça izin vermeli.
1. `radariq data inspect` ile shape, dtype, etiket, SNR ve grup/sequence alanları doğrulanmalı; inceleme JSON'u sürümlenmeli.
1. Hedef veya sekans kimliği üzerinden eğitim/doğrulama/test ayrımı yapılarak veri sızıntısı kontrol edilmeli.
1. Sensör, saha, hava, mesafe, bakış açısı, SNR ve sınıf dengesi bakımından temsil sınırları belgelenmeli.
1. Kabul metrikleri, bağımsız test yöntemi ve yanlış sınıflandırmanın ürün etkisi onaylanmalı.
1. [Ürün çerçevesi](../product-charter.md) yeni kanıtlarla güncellenmeli.

Koşullar sağlanırsa ADR-001'in anlamı geriye dönük değiştirilmez. Yeni bir ADR hazırlanır, ADR-001 “yerine geçildi” durumuna alınır ve yeni teknik görev kimliği `radar_target_classification` olarak ayrıca tanımlanır.

## Reddedilen alternatif

### Görevi şimdiden “gerçek radar hedef sınıflandırması” olarak adlandırmak

Reddedildi. Mevcut veri kanıtı fiziksel hedef semantiğini ve gerçek saha doğrulamasını sağlamıyor. Bu ad, model yeteneğini olduğundan geniş gösterir ve ürün çerçevesiyle çelişir.
