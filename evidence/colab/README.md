# Colab kanıt manifestleri

Bu dizin notebook veya model artifact'ı saklamaz. Yalnız model hassas kaynak ağacıyla kriptografik olarak eşleşen küçük JSON kanıt manifestleri sürümlenir.

`pr-colab-evidence` kontrolü aşağıdaki dosyalarda PR değişikliği varsa eşleşen manifest ister:

- `src/radariq/models/**/*.py`
- `src/radariq/training/**/*.py`
- `src/radariq/evaluation/**/*.py`
- `configs/model.yaml`
- `configs/train.yaml`
- `configs/evaluate.yaml`

Manifestin `source_tree_sha256` alanı `uv run poe colab-evidence` tarafından hesaplanan güncel hassas kaynak ağacı hash'iyle eşleşmelidir. Ayrıca veri, runtime, notebook, beş Colab test grubu, evaluation raporu ve export artifact hash'leri zorunludur.

Notebook Google Drive'da kalır. Repo yalnız notebook dosyasının SHA-256 değerini ve test/export kanıtlarını taşır.
