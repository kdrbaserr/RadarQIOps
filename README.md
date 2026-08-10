# RadarIQops

Radar/sensör verilerini incelemek, tekrarlanabilir deneyler yürütmek ve sonuçları kontrollü bir API üzerinden sunmak için başlangıç projesi.

## Yerel başlangıç

```powershell
uv sync --locked --all-extras
uv run poe install-hooks
uv run poe check
```

API stack'inin tanımını doğrulamak ve servisi başlatmak için:

```powershell
uv run poe compose-config
uv run poe compose-up
```

Nihai model henüz üretilmediği için API health kontrolü geçer, readiness kontrolü `false` döner. Colab eğitimi Google Drive'da bağımsız yürütülür ve model seçilene kadar bu repo ile senkronize edilmez. Komut ayrıntıları [geliştirici komutları](docs/developer-commands.md) belgesindedir.

Yerelde güvenli otomatik düzeltmeleri uygulamak için `uv run poe format`; commit öncesi tüm kontrolleri çalıştırmak için `uv run poe precommit` kullanılır. Otomasyon ortamları yalnız salt-kontrol görevlerini çağırır ve dosya değiştirmez.
