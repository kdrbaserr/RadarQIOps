# `radariq data inspect`

## Amaç

Bu komut, seçilen veri setinden tek bir küçük örnek okuyarak gerçek veri sözleşmesini JSON biçiminde gösterir. Model eğitimi başlamadan önce şekil, veri tipi, etiket, SNR ve sekans ayrımının beklenen yapıyla uyuşup uyuşmadığını kontrol etmek için kullanılır.

Komut veri setini değiştirmez ve tüm veri setini belleğe yüklemez. SNR veya grup bilgisi kaynakta yoksa değer `null` olur; eksik bilgi tahmin edilmez.

## Kurulum

```powershell
python -m pip install -e .
```

## Kullanım

```powershell
radariq data inspect `
  --dataset radarscenes `
  --path C:\datasets\RadarScenes `
  --sample-index 0
```

Desteklenen okuyucular:

- `radioml-2016.10a`: pickle içindeki `(modülasyon, SNR) -> örnekler` sözlüğü.
- `radioml-2018.01a`: `X`, `Y`, `Z` alanlarını içeren HDF5.
- `radarscenes`: `radar_data` alanını içeren HDF5.
- `carrada`, `raddet`, `k-radar`, `npy`: örnek başına bir `.npy` tensörü.

Farklı bir örnek için:

```powershell
radariq data inspect --dataset radioml-2018.01a --path C:\datasets\radioml.h5 --sample-index 42
```

Çıktıyı dosyaya yazmak için:

```powershell
radariq data inspect --dataset radarscenes --path C:\datasets\RadarScenes --output inspection.json
```

## NPY metadata yan dosyası

CARRADA, RADDet, K-Radar veya genel NPY örneğinde etiket ve grup alanları aynı isimli `.json` dosyasından okunabilir:

```text
sample_0001.npy
sample_0001.json
```

Yan dosya örneği:

```json
{
  "label": "car",
  "snr_db": null,
  "group_id": "vehicle-17",
  "sequence_id": "sequence-03"
}
```

Başka bir metadata dosyası `--metadata` ile verilebilir.

## Güvenlik

Pickle dosyası açmak keyfi kod çalıştırabilir. Bu yüzden RadioML 2016 okuyucusu varsayılan olarak kapalıdır. Dosya resmi kaynaktan indirilip checksum'u doğrulandıktan sonra açık onay verilmelidir:

```powershell
radariq data inspect `
  --dataset radioml-2016.10a `
  --path C:\datasets\RML2016.10a_dict.pkl `
  --allow-unsafe-pickle
```

## JSON sözleşmesi

Çıktı en az şu alanları içerir:

```json
{
  "schema_version": "1.0",
  "dataset": "radarscenes",
  "source": "C:\\datasets\\RadarScenes\\sequence_1\\radar_data.h5",
  "sample_index": 0,
  "shape": [],
  "dtype": {
    "kind": "structured",
    "fields": {}
  },
  "label": {
    "index": 0,
    "name": "car"
  },
  "snr_db": null,
  "group_id": "track-1",
  "sequence_id": "sequence_1",
  "statistics": {}
}
```
