# Train-fitted I/Q preprocessing

024 aşaması DC offset ve amplitude/power normalizasyonunu yalnız train split üzerinde fit eder.
Validation, test ve serving aynı immutable `preprocessor.json` değerlerini kullanır; bu
split'lerde yeniden fit veya batch istatistiği hesaplanmaz.

```powershell
uv run radariq data preprocess --config configs/preprocess.example.yaml
```

Girdi canonical NPZ içindeki `samples` alanıdır. Diğer NPZ alanları değiştirilmeden
`processed_iq.npz` dosyasına taşınır. `train_indices_path`, 025 tarafından üretilecek tek
boyutlu, benzersiz ve artan sıralı integer indeks dosyasıdır. Fit lineage; kaynak revision, input SHA-256,
train indeks dosyası SHA-256 ve train örnek sayısını artifact'a bağlar.

## Politika

- `remove_dc_offset`: train genelindeki I/Q ortalamalarını çıkarır.
- `normalization`: `none`, `train_rms_power` veya `train_peak_amplitude` olabilir.
- `zero_power_epsilon`: sıfıra yakın güç/scale için fail-closed sınırıdır.
- `max_input_amplitude`: aşırı amplitude girdisinin fit/transform'u bozmasını engeller.
- `reject_zero_power`: anlamsız sıfır güçlü örnekleri reddeder.

NaN/Inf, canonical olmayan shape/dtype, boş veya tekrarlı train indeksleri, validation/test
etiketiyle fit ve artifact olmadan dönüşüm kabul edilmez. `inverse_transform`, training-serving
parite ve matematiksel kararlılık testleri için aynı affine dönüşümü geri alır.

Çıktı dizini immutable kabul edilir:

- `preprocessor.json`: fit edilen DC ve scale ile tam lineage;
- `processed_iq.npz`: bütün örneklere aynı train-fitted dönüşümün uygulanmış hali;
- `preprocessing_artifacts.json`: dosya ve preprocessor SHA-256 manifesti.

Aynı girdiler tekrar çalıştırıldığında aynı byte artifact'lar doğrulanıp `reused` döner. Aynı
dizinde farklı içerik varsa yerinde overwrite edilmez; yeni bir sürümlü output yolu gerekir.
