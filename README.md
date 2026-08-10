# RadarIQops

Radar/sensör verilerini incelemek, tekrarlanabilir deneyler yürütmek ve sonuçları kontrollü bir API üzerinden sunmak için başlangıç projesi.

## Yerel başlangıç

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,api,notebooks]"
python -m pytest
```

`configs/data.yaml` içindeki veri yollarını hazırladıktan sonra:

```powershell
radariq train --config configs/train.yaml
radariq evaluate --config configs/evaluate.yaml
uvicorn radariq.services.api.app:app --reload
```

Colab girişleri `notebooks/colab/` altındadır. Eğitim ve değerlendirme mantığı notebook'larda tekrarlanmaz; `src/radariq/` paketinden çağrılır.
