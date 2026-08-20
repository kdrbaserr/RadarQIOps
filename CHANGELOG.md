# Changelog

Bu projedeki kullanıcıya görünen önemli değişiklikler bu dosyada belgelenir. Sürüm numaraları Semantic Versioning kurallarını izler.

## Unreleased

### Added

- Configurable crop/padding policy, validity mask and audit metadata for canonical PyTorch I/Q tensors.
- Validation, group-aware split, train-fitted preprocessing ve export raporunu bağlayan DVC hattı.
- Grup sızıntısını engelleyen deterministik train/validation/test indeksleri ve kilitli test manifesti.
- Train-only fit lineage ile DC offset ve amplitude/power normalizasyon artifact'ları.
- Notebook bağımsız CLI ile yeniden üretilebilir sınıf/SNR, I/Q, power ve spektrum EDA artifact'ları.
- Başlangıç repository, kalite, test, PR ve güvenlik otomasyonu.
- Ham veri ve büyük model artifact'ları için DVC sürümleme altyapısı ile yerel ve CI/full-run remote sözleşmesi.
- DVC'nin düzeltmesi bulunmayan geçişli DiskCache zafiyeti için izole cache zorunluluğu ve süreli güvenlik istisnası.
