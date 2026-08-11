# Pytest stratejisi

Testler lokal servis doğrulaması ile Colab GPU model doğrulamasını bilinçli olarak ayırır. Lokal komutlar model eğitmez ve `colab` marker'lı testleri toplamaz.

## Lokal gruplar

| Marker | Kapsam |
|---|---|
| `unit` | Dış kaynaksız küçük davranışlar |
| `contract` | Veri, API ve artifact şemaları |
| `integration` | Lokal dosya/API/pipeline birleşimleri |
| `api` | Inference API endpoint davranışı |
| `artifact` | Model artifact kaydetme/yükleme |
| `smoke` | En kısa temel çalışma kontrolleri |

`uv run poe test` hızlı grubu, `uv run poe integration-test` lokal entegrasyon grubunu, `uv run poe test-all-local` ise `colab` dışındaki bütün grupları çalıştırır.

## Colab grupları

Colab testleri Google Drive'da kalır ve nihai model seçilene kadar repoya eklenmez. Her model testi `colab` ile birlikte aşağıdaki marker'lardan birini taşır:

- `model_feature`: giriş shape/dtype ve logit/probability sözleşmesi.
- `gradient`: finite loss, backward ve finite/non-zero gradient.
- `overfit`: küçük sabit batch üzerinde kaybı düşürme.
- `reproducibility`: aynı seed ile aynı başlangıç ve kısa koşu sonucu.
- `evaluation`: Macro-F1, sınıf recall, SNR dilimleri ve rapor şeması.

Colab collection kapısı tüm beş grubun en az bir test topladığını kanıtlamalıdır. Lokal komutlar bu testleri toplamaz.

## Determinizm ve kanıt

Lokal varsayılan seed `20260811` değeridir ve her test öncesi Python/NumPy RNG'leri sıfırlanır. Colab ayrıca PyTorch CPU/CUDA seed'lerini ve deterministik algoritma ayarını uygular.

Sürümlü `tests/evidence-manifest.json`; ortam, veri checksum'u, split hash'leri, seed ve test raporunu zorunlu kanıt alanları olarak tanımlar.
