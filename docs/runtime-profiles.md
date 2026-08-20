# Çalışma zamanı profilleri

Bu proje yerel servis geliştirmesi ile Colab GPU eğitimini ayrı ortamlar olarak yönetir. Eğitim ortamı yerel paketin bağımlılığı değildir.

## Yerel profiller

Yerel Python `.python-version` ve servis image'ında Python 3.11.15'e sabitlenir. `pyproject.toml` yalnızca 3.11 hattını kabul eder; geçişli bağımlılıkların kesin sürümleri `uv.lock` içinde tutulur.

| Profil | Kurulum | Amaç | Model eğitir mi? |
|---|---|---|---|
| `core` | `uv sync --no-dev` | Veri/artifact okuma ve CLI | Hayır |
| `model` | `uv sync --no-dev --extra model` | PyTorch feature ve model kodu | Hayır |
| `serve` | `uv sync --no-dev --extra serve` | Inference API | Hayır |
| `dev` | `uv sync` | Core + yerel test araçları | Hayır |

Yerel kurulumlara PyTorch, CUDA, Jupyter veya Colab bağımlılıkları eklenmez.

## Colab eğitim profili

Colab eğitimi Google Drive'daki notebook ve manifestlerle bağımsız yürütülür. Repo ile notebook senkronizasyonu nihai model seçilene kadar yapılmaz.

Her temiz Colab oturumu eğitim başlamadan önce en az şu alanları kaydetmelidir:

- Python, PyTorch, CUDA, cuDNN, NumPy, h5py ve scikit-learn sürümleri.
- GPU adı ve GPU bellek miktarı.
- RadioML HDF5 dosya yolu, byte boyutu ve SHA-256 değeri.
- Seed, sınıf sırası ve train/validation/test indeks manifestlerinin hash'leri.

## Ortak inference sınırı

İki ortam kaynak kodu veya sanal ortam paylaşmaz. Birleştirme sınırı daha sonra üretilecek sürümlü model paketi olacaktır. Paket en az şunları taşımalıdır:

- Model artifact'ı (`.onnx` tercih edilen taşınabilir aday; nihai karar eğitim sonunda verilir).
- Giriş shape/dtype ve I/Q eksen sırası.
- Normalizasyon parametreleri.
- Sıralı `class_id -> modulation_class` eşlemesi.
- Model ve değerlendirme manifestleri ile dosya SHA-256 değerleri.

Yerel servise entegrasyon, bu sözleşme Colab tarafında dondurulmadan başlamaz.
