# I/Q veri kalite doğrulaması

020 validation aşaması, raw dataset adaptörünün ürettiği örnekleri değiştirmeden kalite
politikasına göre değerlendirir. Yapısal sözleşme ile veri setine özgü kabul sınırlarını ayırır:
`IQBatch` güvenilir canonical veriyi temsil ederken `SampleCandidate` henüz güvenilmeyen raw
örneği temsil eder.

## Politika

[`configs/validate.example.yaml`](../configs/validate.example.yaml) aşağıdaki sınırları sürümler:

- `representation`: örnek başına `[2, L] float32` veya `[L] complex64`;
- `signal_length`: beklenen sabit `L`;
- `allowed_labels`: veri seti sürümüne ait kapalı label kümesi;
- `snr_min_db` ve `snr_max_db`: SNR kabul aralığı;
- `max_amplitude`: örnek içindeki en yüksek kompleks genlik;
- `min_power` ve `max_power`: ortalama `I² + Q²` güç sınırları;
- `constant_tolerance`: sabit sinyal karşılaştırma toleransı.

SNR kaynakta yoksa `null` korunur ve tek başına ret nedeni olmaz. NaN/Inf SNR ise eksik bilgi
değil bozuk değer kabul edilir.

## Hata kodları

| Kod | Anlamı |
|---|---|
| `signal.not_ndarray` | Sinyal NumPy dizisi değil |
| `signal.invalid_shape` | Gösterime uymayan eksen yapısı |
| `signal.invalid_length` | Beklenmeyen sinyal uzunluğu |
| `signal.empty` | Boş sinyal kaydı |
| `signal.invalid_dtype` | `float32`/`complex64` sözleşmesine aykırı dtype |
| `signal.non_finite` | NaN veya Inf sinyal değeri |
| `signal.constant` | Tolerans içinde sabit sinyal |
| `signal.amplitude_out_of_range` | Maksimum kompleks genlik sınırı aşılmış |
| `signal.power_out_of_range` | Ortalama güç kabul aralığı dışında |
| `label.not_allowed` | Label izin verilen kümede değil |
| `snr.invalid_type` | SNR sayısal veya null değil |
| `snr.non_finite` | SNR NaN veya Inf |
| `snr.out_of_range` | SNR kabul aralığı dışında |

Validation tek örnekte güvenle gözlenebilen bütün ihlalleri korur. `ValidationReport`; toplam,
kabul ve ret sayılarını, geçerli/geçersiz `sample_id` listelerini, hata kodu dağılımını ve her
ihlalin alanını içerir. 022 aşaması aynı raporu quarantine manifesti ve insan okunur rapora
dönüştürecektir.
