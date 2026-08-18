# Tekrarlanabilir geliştirici komutları

Tüm yerel geliştirme ve daha sonra eklenecek CI işleri aynı Poe görevlerini çağırır. Uzun komutlar README veya workflow dosyalarında yeniden yazılmaz.

| Görev | Komut | Amaç |
|---|---|---|
| Kurulum | `uv run poe setup` | Kilitli core, serve ve dev ortamını kurar |
| DVC durum | `uv run poe dvc-status` | Pointer dosyalarını varsayılan DVC remote ile karşılaştırır |
| DVC indir | `uv run poe dvc-pull` | Yerel remote profilinden veri ve büyük artifact'ları indirir |
| DVC yükle | `uv run poe dvc-push` | Yerel remote profiline veri ve büyük artifact'ları yükler |
| Full-run DVC indir | `uv run poe dvc-pull-full` | Çalışma anında yapılandırılmış `full-run` remote'undan indirir |
| Veri edinimi | `uv run radariq data acquire --config configs/acquire.yaml` | HTTP, yerel dosya veya kullanıcı arşivini atomik olarak raw hedefe alır |
| Veri kaydı | `uv run radariq data register --config configs/register.yaml` | Raw kaynağı SHA-256, lisans, atıf ve sürümlü manifest ile doğrular |
| Raw ingestion | `uv run radariq data ingest --config configs/ingest.yaml` | Doğrulanmış arşivi deterministik kimliklerle değişmez raw stage'e açar |
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
| Secret taraması | `uv run poe security-secrets` | Git tarafından takip edilen bütün dosyalarda yeni secret arar |
| Güvenlik politikası | `uv run poe security-policy` | Lisans, zafiyet eşiği ve süreli istisna kayıtlarını doğrular |
| Bağımlılık güvenliği | `uv run poe security-dependencies` | Lock zafiyetlerini ve dağıtılan bağımlılık lisanslarını denetler |
| Bütün güvenlik kontrolleri | `uv run poe security` | Secret, politika, zafiyet ve lisans kontrollerini birlikte çalıştırır |
| PR politikası | `uv run poe pr-policy` | PR checklist'ini ve süreli politika istisnalarını doğrular |
| Compose doğrulama | `uv run poe compose-config` | Compose dosyasını parse edip doğrular |
| Stack başlatma | `uv run poe compose-up` | Lokal API container'ını build edip başlatır |
| Hızlı kontrol | `uv run poe check` | Lint, typecheck, test, integration ve smoke görevlerini sırayla çağırır |
| Hook kurulumu | `uv run poe install-hooks` | Git pre-commit hook'unu yerel repoya kurar |
| Pre-commit | `uv run poe precommit` | Tüm hook'ları bütün takip edilen dosyalarda çalıştırır |

Remote kurulumu, DVC'ye dosya ekleme ve CI secret sözleşmesi [DVC remote profilleri](dvc-remotes.md) belgesindedir.

`compose-up` uzun süre çalışan etkileşimli bir görevdir; kullanıcı `Ctrl+C` ile durdurur. Nihai model henüz üretilmediği için `/ready` endpoint'inin `false` dönmesi beklenir.

## Ayrı Colab komut sözleşmesi

Colab eğitimi repo ile senkronize edilmez. Google Drive'daki eğitim notebook'unda giriş aşamaları aşağıdaki sabit adları ve sırayı kullanır:

1. `data`: Kaggle indirme, HDF5 doğrulama, pilot örnekleme ve split.
1. `model-test`: Tek batch forward/backward ve overfit smoke testi.
1. `train`: Checkpoint'li gerçek eğitim.
1. `evaluate`: Test, Macro-F1, sınıf recall, SNR ve kalibrasyon raporu.
1. `export`: Model artifact'ı, sınıf sırası, normalizasyon ve manifest dışa aktarımı.

Her aşama kendinden önceki aşamanın Drive artifact'ını doğrulamadan başlamaz. Notebook ve model kodu, nihai model seçilene kadar bu repoya eklenmez.
