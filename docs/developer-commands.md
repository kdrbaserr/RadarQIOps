# Tekrarlanabilir geliştirici komutları

Tüm yerel geliştirme ve daha sonra eklenecek CI işleri aynı Poe görevlerini çağırır. Uzun komutlar README veya workflow dosyalarında yeniden yazılmaz.

| Görev | Komut | Amaç |
|---|---|---|
| Kurulum | `uv run poe setup` | Kilitli core, serve ve dev ortamını kurar |
| Lint | `uv run poe lint` | 009'da kesin Python/sözdizimi hatalarını kontrol eder; tam kural seti 010'da açılır |
| Tip kontrolü | `uv run poe typecheck` | `src/` üzerinde mypy çalıştırır |
| Lokal test | `uv run poe test` | Hızlı lokal testleri çalıştırır |
| Entegrasyon | `uv run poe integration-test` | Lokal pipeline round-trip testini çalıştırır |
| API smoke | `uv run poe api-smoke` | Model yokken health/readiness davranışını doğrular |
| Compose doğrulama | `uv run poe compose-config` | Compose dosyasını parse edip doğrular |
| Stack başlatma | `uv run poe compose-up` | Lokal API container'ını build edip başlatır |
| Hızlı kontrol | `uv run poe check` | Lint, typecheck, test, integration ve smoke görevlerini sırayla çağırır |

`compose-up` uzun süre çalışan etkileşimli bir görevdir; kullanıcı `Ctrl+C` ile durdurur. Nihai model henüz üretilmediği için `/ready` endpoint'inin `false` dönmesi beklenir.

## Ayrı Colab komut sözleşmesi

Colab eğitimi repo ile senkronize edilmez. Google Drive'daki eğitim notebook'unda giriş aşamaları aşağıdaki sabit adları ve sırayı kullanır:

1. `data`: Kaggle indirme, HDF5 doğrulama, pilot örnekleme ve split.
2. `model-test`: Tek batch forward/backward ve overfit smoke testi.
3. `train`: Checkpoint'li gerçek eğitim.
4. `evaluate`: Test, Macro-F1, sınıf recall, SNR ve kalibrasyon raporu.
5. `export`: Model artifact'ı, sınıf sırası, normalizasyon ve manifest dışa aktarımı.

Her aşama kendinden önceki aşamanın Drive artifact'ını doğrulamadan başlamaz. Notebook ve model kodu, nihai model seçilene kadar bu repoya eklenmez.
