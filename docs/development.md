# Geliştirme akışı

1. Veri dosyaları Git'e eklenmez; `data/` altında yerel tutulur.
2. `radariq data inspect` ile shape, dtype, etiket ve metadata kontrol edilir.
3. Deney yolları ve seed `configs/` altında sabitlenir.
4. Eğitim `radariq train`, değerlendirme `radariq evaluate` ile çalıştırılır.
5. `artifacts/training.json` ve `artifacts/evaluation.json` deney kanıtıdır.
6. Notebook'lar aynı komutları çağıran etkileşimli girişlerdir.
7. API yalnızca doğrulanmış model artifact'ı ile paketlenir.
