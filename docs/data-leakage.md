# Duplicate, group ve split leakage denetimi

021 kırmızı kalite kapısıdır: aynı veya neredeyse aynı sinyalin farklı split'lere girmesi test
başarısını yapay biçimde yükseltebilir. Bu modül model eğitmez ve lokal ortamda gerçek büyük veri
taramaz. Repoda sürümlenen denetim kodu küçük sentetik fixture'larla test edilir; gerçek veri
üzerindeki çalışma 026 ile Colab/DVC hattından çağrılır.

## Exact ve near duplicate

Exact fingerprint; representation, shape, dtype ve canonical C-order sinyal byte'larının SHA-256
değeridir. Aynı fingerprint küme olarak raporlanır. Aynı sinyal farklı label taşıyorsa
`duplicate.label_conflict` ayrıca üretilir.

Near duplicate taraması bütün veri üzerinde karesel karşılaştırma yapmaz. Sinyal isteğe bağlı DC
giderme, güç normalizasyonu ve global faz sabitleme sonrasında üç deterministik kuantizasyon
kovasına yerleştirilir. Yalnız aynı kovayı paylaşan adaylar normalized complex correlation ile
doğrulanır. Eşik ve kuantizasyon [`configs/leakage.example.yaml`](../configs/leakage.example.yaml)
içinde sürümlenir. Yöntem yaklaşık aday bulucudur; correlation skoru nihai kanıttır.

## Dataset'e özgü grup kuralı

Grup kimliği dosya adından tahmin edilmez. `GroupIdAdapter` protokolü kural adı ve sürümüyle
birlikte kullanılır:

- `ExplicitGroupIdAdapter`: kaynağın sağladığı capture/subject/group kimliğini kullanır.
- `SourceSequenceGroupAdapter`: kaynak kimliği, kaynak sürümü ve sequence kimliğinden özel,
  deterministik bir grup hash'i üretir.

Kaynağa özgü yeni adaptör aynı protokolü uygular. Gerekli metadata yoksa `group.unresolved`
üretilir ve `split_ready=false` olur; rastgele veya örnek başına grup uydurulmaz.

## Split denetimi

021 split üretmez. Verilmiş aday atamaları aşağıdaki kodlarla denetler; 025 aynı fonksiyonu
ürettiği indekslerin kabul kapısı olarak kullanacaktır:

| Kod | Anlamı |
|---|---|
| `duplicate.exact` | Canonical byte içeriği aynı örnek kümesi |
| `duplicate.near` | Correlation eşiğini geçen yaklaşık kopya |
| `duplicate.label_conflict` | Aynı sinyalde çelişkili label |
| `group.unresolved` | Güvenilir group kimliği üretilemedi |
| `split.assignment_missing` | Örneğin split ataması yok |
| `split.assignment_invalid` | İzin verilmeyen split adı |
| `leakage.group_cross_split` | Aynı grup birden fazla split'te |
| `leakage.exact_cross_split` | Exact duplicate'lar farklı split'lerde |
| `leakage.near_cross_split` | Near duplicate'lar farklı split'lerde |

`DuplicateLeakageReport`; örnek/grup eşlemelerini, duplicate kümelerini, near çiftlerini,
similarity kanıtlarını, split adlarını ve sürümlü grup kuralını deterministik sırada taşır. Aynı
input sırasından bağımsız aynı rapor SHA-256 değerini üretir. Her duplicate veya çözülmemiş grup,
quarantine/gruplama kararı verilene kadar split hazırlığını kapalı tutar.
