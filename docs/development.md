# Geliştirme akışı

1. Ham kaynaklar [atomik acquisition adapterleriyle](data-acquisition.md) alınır.
1. Kaynak checksum, lisans ve atıf bilgileri [sürümlü data manifestinde](data-manifests.md) doğrulanır.
1. Kaynak adaptörleri veriyi sürümlü [I/Q veri sözleşmesine](data-contracts.md) dönüştürür.
1. Veri dosyaları Git'e eklenmez; `data/` altında yerel tutulur.
1. `radariq data inspect` ile shape, dtype, etiket ve metadata kontrol edilir.
1. Deney yolları ve seed `configs/` altında sabitlenir.
1. Eğitim `radariq train`, değerlendirme `radariq evaluate` ile çalıştırılır.
1. `artifacts/training.json` ve `artifacts/evaluation.json` deney kanıtıdır.
1. Notebook'lar aynı komutları çağıran etkileşimli girişlerdir.
1. API yalnızca doğrulanmış model artifact'ı ile paketlenir.
