# DVC veri ve artifact sürümleme

## Kapsam

DVC, `data/raw` içindeki kabul edilmiş ham veriyi ve büyük model/checkpoint dosyalarını içerik hash'iyle sürümler. Gerçek dosyalar Git'e girmez; Git yalnız `.dvc` pointer dosyalarını, küçük JSON manifestlerini ve değerlendirme kanıtlarını taşır.

Repository varsayılan olarak `local` adlı dosya sistemi remote'unu kullanır:

```text
.dvc-storage
```

Bu klasör yalnız geliştirici bilgisayarında bulunur ve Git tarafından yok sayılır. Hızlı yerel deneme içindir; repository silinirse onunla birlikte kaybolacağından kalıcı ekip yedeği sayılmaz.

## Yerel geliştirme profili

Bağımlılıkları kurup mevcut DVC verisini çekmek için:

```powershell
uv sync --locked --all-extras
uv run poe dvc-pull
```

Kabul ve checksum kontrolü tamamlanmış `data/raw` klasörünü tek bir sürüm olarak eklemek için:

```powershell
uv run dvc add data/raw
git add data/raw.dvc .gitignore
uv run poe dvc-push
```

Büyük bir model artifact'ını tek başına sürümlemek için:

```powershell
uv run dvc add artifacts/model.onnx
git add artifacts/model.onnx.dvc .gitignore
uv run poe dvc-push
```

`artifacts/evaluation.json`, export manifesti ve checksum kanıtı gibi küçük metin dosyaları normal Git dosyası olarak kalır. Model ağırlığı, checkpoint, NumPy/HDF5 verisi ve arşivler DVC ile takip edilir.

Her veri veya artifact değişikliğinde gerçek dosya ile pointer aynı işlemde güncellenir:

```powershell
uv run dvc add data/raw
uv run poe dvc-push
git add data/raw.dvc
```

Remote'a `dvc push` yapılmadan pointer commit edilmez. Aksi durumda diğer ortamlar hash'i görür fakat içeriği indiremez.

## CI/full-run profili

`full-run`, merkezi ve kalıcı remote için ayrılmış addır. Remote adresi ve kimlik bilgileri repository'ye yazılmaz. CI işi bunları secret veya workload identity üzerinden çalışma anında `.dvc/config.local` dosyasına ekler:

```powershell
uv run dvc remote add --local --force full-run $env:DVC_REMOTE_URL
uv run poe dvc-pull-full
```

Linux runner karşılığı:

```bash
uv run dvc remote add --local --force full-run "$DVC_REMOTE_URL"
uv run poe dvc-pull-full
```

`DVC_REMOTE_URL`, seçilen merkezi depoya ait URL'dir. S3, Azure, Google Drive veya başka bir backend seçildiğinde ilgili DVC eklentisi ayrıca kilitli bağımlılıklara eklenir. Backend kararı verilmeden sahte bir URL veya erişim anahtarı commit edilmez.

CI/full-run erişim politikası:

- PR ve doğrulama işleri yalnız okuma yetkisi kullanır.
- Veri kabul/publish işi yazma yetkisini ayrı, korumalı bir environment üzerinden alır.
- Secret, token, parola ve servis hesabı JSON'u `.dvc/config` veya Git'e yazılmaz.
- `.dvc/cache` ve `.dvc/site-cache` güvenilmeyen branch veya harici cache arşivinden restore edilmez; CI runner'ı her full-run için izole edilir.
- Remote nesneleri içerik hash'iyle değişmez kabul edilir; üzerine yazmak yerine yeni revision üretilir.
- Full-run kaydı Git SHA, DVC pointer hash'i, config hash'i ve çıktı artifact hash'ini birlikte saklar.

Yerel veya CI'a özel ayarlar `.dvc/config.local` içindedir ve DVC tarafından Git dışında tutulur. Paylaşılan `.dvc/config` yalnız secretsız varsayılan `local` profilini içerir.

## Günlük komutlar

| Amaç | Komut |
|---|---|
| Remote ile farkı gör | `uv run poe dvc-status` |
| Yerel remote'dan indir | `uv run poe dvc-pull` |
| Yerel remote'a yükle | `uv run poe dvc-push` |
| Full-run remote'dan indir | `uv run poe dvc-pull-full` |
| Takip edilen içeriği doğrula | `uv run dvc status` |

Bir Git branch veya commit değiştirildikten sonra `uv run poe dvc-pull` çalıştırmak, çalışma alanındaki veri ve artifact'ları o Git revision'ındaki pointer'larla eşleştirir.
