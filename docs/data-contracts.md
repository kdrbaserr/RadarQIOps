# I/Q veri sözleşmesi

Bu sözleşme, veri kaynağından bağımsız olarak RadarIQops veri hattındaki her örneğin
ortak yapısını tanımlar. Acquisition adaptörleri kaynak biçimini bu sözleşmeye dönüştürür;
doğrulama, preprocessing ve split aşamaları yalnız bu sözleşmeyi kabul eder.

## Şema sürümü 1.0

Bir batch aşağıdaki iki gösterimden tam olarak birini kullanır:

| Gösterim | NumPy dtype | Shape | Eksenler |
|---|---|---|---|
| `channels_first` | `float32` | `[N, 2, L]` | batch, I/Q kanalı, zaman |
| `complex` | `complex64` | `[N, L]` | batch, kompleks zaman örneği |

`N` batch içindeki örnek sayısı, `L` ise her örneğin sabit sinyal uzunluğudur. İki değer
de sıfırdan büyük olmalıdır. Bir batch içinde gösterim, dtype ve sinyal uzunluğu homojendir.

Her örneğin bire bir metadata kaydı vardır:

| Alan | Tip | Null olabilir mi? | Anlamı |
|---|---|---:|---|
| `sample_id` | string | Hayır | Kaynak sürümü içinde deterministik ve benzersiz örnek kimliği |
| `label` | string veya integer | Hayır | Kaynağın sınıf etiketi; SNR burada tutulmaz |
| `snr_db` | sonlu number | Evet | Kaynağın sağladığı örnek bazlı SNR; bilinmiyorsa `null` |
| `group_id` | string | Evet | Aynı yakalama/sekans/özne grubu; kaynak sağlamıyorsa `null` |
| `source_version` | string | Hayır | Örneğin geldiği veri kaynağı ve değişmez sürüm kimliği |

`group_id=null` geçerli bir temsil olsa da group-aware split için yeterli değildir. Grup üretme
kuralı 021 kapsamındaki veri setine özgü adaptörde tanımlanmadan bu örnekler split aşamasına
geçemez. Benzer şekilde `snr_db=null`, bilinmeyen SNR'yi tahmin etmek yerine açıkça korur.

## Sözleşme ve kalite doğrulaması sınırı

Bu adım yapısal kuralları doğrular: shape, dtype, zorunlu alanlar, sonlu SNR, metadata sayısı
ve batch içindeki benzersiz `sample_id`. Label kümesi, kabul edilen SNR aralığı, NaN/Inf sinyal,
sabit sinyal ve güç sınırları veri setine bağlı kalite kurallarıdır; 020 doğrulama aşamasında
uygulanacaktır.

## Geriye uyumsuz değişiklik kuralı

Şema tanımı kanonik JSON üzerinden SHA-256 ile kilitlenir. Zorunlu alan, tip, null davranışı,
dtype veya eksen düzeni değişirse mevcut parmak izi eşleşmez ve sözleşme testi başarısız olur.
Böyle bir değişiklik için yeni `schema_version`, yeni tanım ve yeni kayıtlı parmak izi birlikte
eklenmelidir. Mevcut sürümün anlamı yerinde değiştirilemez.
