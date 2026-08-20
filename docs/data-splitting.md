# Deterministik group-aware veri bölme

025 aşaması canonical metadata'yı train, validation ve test olarak böler. Aynı `group_id`
değerindeki örnekler parçalanmaz; böylece aynı kayıt, sekans veya özne farklı split'lere sızmaz.

```powershell
uv run radariq data split --config configs/split.example.yaml
```

Girdi NPZ dosyasında eşit uzunlukta `sample_ids`, `labels`, `snr_db` ve `group_ids` alanları
zorunludur. Eksik/boş grup kimliğiyle sahte grup üretilmez; işlem durur. En az üç bağımsız grup
gerekir. `snr_bin_edges`, SNR değerlerini dengelenebilir aralıklara ayırır; bilinmeyen SNR
`unknown` olarak korunur.

Algoritma grupları bölmeden hedef split büyüklüğü ile ortak label/SNR dağılımı arasındaki farkı
azaltır. Seed yalnız SHA-256 tabanlı deterministik sıralama ve eşitlik bozma için kullanılır.
Aynı input, config ve seed aynı artan sıralı `int64` indeks dosyalarını üretir.

## Artifact'lar

- `train_indices.npy`, `validation_indices.npy`, `test_indices.npy`: ayrık indeksler;
- `split_manifest.json`: kaynak, seed, strateji, grup sayıları, sınıf/SNR dengesi ve indeks hash'leri;
- `development_splits.json`: yalnız train/validation referansları; test dosya yolunu içermez;
- `test_lock.json`: evaluation için test indeks checksum'u ve split kimliği.

Model geliştirme kodu `load_development_splits` ile yalnız train/validation indekslerini alır.
Nihai değerlendirme, `load_locked_test_indices` çağrısına onaylı test-lock SHA-256 değerini
vermeden test indekslerini açamaz. Test dosyası veya kilit değişirse doğrulama başarısız olur.

Artifact dizini immutable'dır. Aynı çalışma `reused` döner; farklı split aynı dizinin üzerine
yazılamaz. 024 preprocessing yalnız bu aşamanın ürettiği `train_indices.npy` ile fit edilir.
