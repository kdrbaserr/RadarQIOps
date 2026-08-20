# DVC veri hattı ve Colab kanıtı

026 aşaması güvenli gerçek çalışma sırasını tek komuta bağlar:

```text
validate → split → preprocess → report
```

Split, preprocessing'den önce çalışır; çünkü DC/scale değerleri yalnız train indeksleriyle fit
edilebilir. `dvc.yaml` kod, parametre ve önceki aşama çıktısı değişmedikçe tamamlanmış aşamayı
yeniden çalıştırmaz. `dvc.lock`, fixture çalışmasının gerçek bağımlılık ve çıktı kimliklerini
kaydeder.

## Lokal fixture

Repository içindeki küçük ve modelsiz fixture için:

```powershell
uv run poe dvc-repro
uv run poe data-pipeline-export
```

İlk komut validation raporu, split indeksleri, preprocessing artifact'ı ve export manifesti
üretir. İkinci komut yalnız küçük `pipeline_export_manifest.json` dosyasını okur; NPZ veya model
verisini açmaz.

## Temiz Colab çalışması

Gerçek veri Colab/Drive DVC remote'undan çekildikten sonra çalışma parametreleri experiment
override ile verilir. Secret veya Drive kimlik bilgisi `params.yaml` içine yazılmaz.

```bash
uv sync --locked --all-extras
uv run dvc remote add --local --force full-run "$DVC_REMOTE_URL"
uv run dvc pull -r full-run
uv run dvc exp run \
  -S pipeline.raw_input=data/raw/validated_iq.npz \
  -S pipeline.validation_output=data/validation/colab-v1 \
  -S pipeline.split_output=data/interim/splits/colab-v1 \
  -S pipeline.preprocessing_output=data/processed/colab-v1 \
  -S pipeline.report_output=artifacts/data-pipeline/colab-v1 \
  -S pipeline.source_revision=dvc:GERCEK_REVISION \
  -S pipeline.execution_profile=colab \
  -S pipeline.dvc_remote=full-run \
  -S pipeline.dvc_pull_status=verified \
  -S pipeline.dvc_pull_log_sha256=GERCEK_64_KARAKTER_SHA256 \
  -S pipeline.runtime_manifest_sha256=GERCEK_64_KARAKTER_SHA256
```

`dvc_pull_log_sha256`, başarılı pull komutunun saklanan log dosyasının parmak izidir.
`runtime_manifest_sha256`, Python/Colab runtime bilgisini taşıyan küçük JSON dosyasının parmak
izidir. Colab profili bu iki alan olmadan rapor üretmez.

Colab'den indirilen export manifesti lokal ortamda şu şekilde doğrulanır:

```powershell
uv run python tools/check_data_pipeline_export.py `
  --manifest path/to/pipeline_export_manifest.json `
  --expected-split-sha256 ONAYLANMIS_SPLIT_SHA256
```

Doğrulayıcı; manifestin kendi hash'ini, aşama sırasını, DVC pull/runtime kanıtını, test kilidini
ve preprocessing'in split ile aynı train indeks hash'ini kullandığını kontrol eder. Büyük veri
veya model dosyası indirmez ya da işlemez.
