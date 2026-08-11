# Tekrarlanabilir geliştirici komutları

Tüm yerel geliştirme ve daha sonra eklenecek CI işleri aynı Poe görevlerini çağırır. Uzun komutlar README veya workflow dosyalarında yeniden yazılmaz.

| Görev | Komut | Amaç |
|---|---|---|
| Kurulum | `uv run poe setup` | Kilitli core, serve ve dev ortamını kurar |
| Lint | `uv run poe lint` | Python lint ve import sırası kontrolünü salt-kontrol modunda çalıştırır |
| Otomatik format | `uv run poe format` | Güvenli Ruff düzeltmelerini ve Python/Markdown formatını yerelde uygular |
| Format kontrolü | `uv run poe format-check` | Python formatını dosya değiştirmeden kontrol eder |
| Markdown | `uv run poe markdown-check` | README ve docs Markdown formatını kontrol eder |
| YAML | `uv run poe yaml-check` | Config, Compose ve pre-commit YAML dosyalarını kontrol eder |
| Tip kontrolü | `uv run poe typecheck` | `src/` üzerinde mypy çalıştırır |
| Lokal test | `uv run poe test` | Colab ve entegrasyon marker'larını toplamadan hızlı lokal testleri çalıştırır |
| Entegrasyon | `uv run poe integration-test` | Yalnız lokal API/artifact/pipeline entegrasyon testlerini çalıştırır |
| Bütün lokal testler | `uv run poe test-all-local` | `colab` marker'ı dışındaki bütün testleri çalıştırır |
| API smoke | `uv run poe api-smoke` | Model yokken health/readiness davranışını doğrular |
| Colab kanıtı | `uv run poe colab-evidence` | Son commit model hassas dosyaları değiştirdiyse eşleşen Colab manifestini doğrular |
| Compose doğrulama | `uv run poe compose-config` | Compose dosyasını parse edip doğrular |
| Stack başlatma | `uv run poe compose-up` | Lokal API container'ını build edip başlatır |
| Hızlı kontrol | `uv run poe check` | Lint, typecheck, test, integration ve smoke görevlerini sırayla çağırır |
| Hook kurulumu | `uv run poe install-hooks` | Git pre-commit hook'unu yerel repoya kurar |
| Pre-commit | `uv run poe precommit` | Tüm hook'ları bütün takip edilen dosyalarda çalıştırır |

`compose-up` uzun süre çalışan etkileşimli bir görevdir; kullanıcı `Ctrl+C` ile durdurur. Nihai model henüz üretilmediği için `/ready` endpoint'inin `false` dönmesi beklenir.

## Ayrı Colab komut sözleşmesi

Colab eğitimi repo ile senkronize edilmez. Google Drive'daki eğitim notebook'unda giriş aşamaları aşağıdaki sabit adları ve sırayı kullanır:

1. `data`: Kaggle indirme, HDF5 doğrulama, pilot örnekleme ve split.
1. `model-test`: Tek batch forward/backward ve overfit smoke testi.
1. `train`: Checkpoint'li gerçek eğitim.
1. `evaluate`: Test, Macro-F1, sınıf recall, SNR ve kalibrasyon raporu.
1. `export`: Model artifact'ı, sınıf sırası, normalizasyon ve manifest dışa aktarımı.

Her aşama kendinden önceki aşamanın Drive artifact'ını doğrulamadan başlamaz. Notebook ve model kodu, nihai model seçilene kadar bu repoya eklenmez.
