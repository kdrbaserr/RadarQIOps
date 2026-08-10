from pathlib import Path


SOURCE = Path(
    r"C:\Users\kadir\Documents\Codex\2026-08-06\bu\work\build_radariqops_roadmap.py"
)


REPLACEMENTS = {
    'PDF_PATH = OUTPUT_DIR / "RadarIQOps_Commit_Odakli_Yol_Haritasi.pdf"':
        'PDF_PATH = OUTPUT_DIR / "RadarIQOps_Colab_Egitim_Odakli_Yol_Haritasi.pdf"',
    'MD_PATH = OUTPUT_DIR / "RadarIQOps_Commit_Odakli_Yol_Haritasi.md"':
        'MD_PATH = OUTPUT_DIR / "RadarIQOps_Colab_Egitim_Odakli_Yol_Haritasi.md"',
    'OUTPUT_DIR = ROOT / "outputs"': 'OUTPUT_DIR = ROOT / "output" / "pdf"',
    'Commit Odaklı Uygulama ve CI/CD Yol Haritası':
        'Colab Eğitim Odaklı Uygulama ve CI/CD Yol Haritası',
    '72 commitlik bağımlılık ve kalite kapısı odaklı proje yol haritası':
        '72 commitlik Colab GPU eğitim ve lokal entegrasyon odaklı proje yol haritası',
    'Dört haftalık takvim kaldırıldı. İlerleme; bağımlılık, test kanıtı, kalite kapısı ve geri alınabilir release üzerinden ölçülür.':
        'Model geliştirme, model testleri, tam eğitim ve değerlendirme Colab GPU ortamında; lokal çalışma yalnız entegrasyon ve servis doğrulamasında yürütülür. İlerleme test kanıtı, kalite kapısı ve geri alınabilir release üzerinden ölçülür.',
    'RadioML/DeepSig kullanılıyorsa ürün modülasyon sınıflandırmasıdır. Gerçek radar hedef etiketli veri olmadan drone/kuş/araç iddiası yapılamaz. Commit 001-006 bitmeden model sınıfları ve API sözleşmesi dondurulmaz.':
        'RadioML/DeepSig kullanılıyorsa ürün modülasyon sınıflandırmasıdır. Gerçek radar hedef etiketli veri olmadan drone/kuş/araç iddiası yapılamaz. Model kodu, model testleri, kısa ve tam eğitim ile değerlendirme Colab GPU üzerinde yürütülür; lokal ortam yalnız immutable model artifact entegrasyonunu yapar.',
    '("Plan tipi", "Takvimsiz, bağımlılık ve kalite kapısı odaklı")':
        '("Plan tipi", "Takvimsiz, Colab GPU eğitim + lokal entegrasyon ve kalite kapısı odaklı")',
    '("CI başlangıcı", "Commit 012; model ve servis gelmeden önce kalite kapıları aktiftir")':
        '("CI başlangıcı", "Commit 012; lokal CI statik/API kontrollerini, Colab model kapısı ise tüm model testlerini yürütür")',
    '"Veri + lisans", "DVC + doğrulama", "Eğitim + MLflow", "Registry gate", "FastAPI + OCI", "K8s + gözlem", "Drift + retrain"':
        '"Veri + lisans", "DVC + Drive", "Colab GPU", "MLflow gate", "Lokal FastAPI", "OCI + K8s", "Drift + Colab retrain"',
    'Uygulama kodu OCI image digest, model ise MLflow registry version olarak ayrı terfi eder. Production release manifesti ikisini bağlar. Mutable model alias deployment anında immutable version\'a çözülür; pod restart\'ında sessiz model değişikliği olmaz.':
        'Model geliştirme, model testleri, eğitim ve değerlendirme Colab GPU üzerinde tamamlanır. Checkpoint ve raporlar Google Drive üzerinde kalıcılaştırılır; kabul edilen model checksum\'lı immutable MLflow registry version olarak dışa aktarılır. Lokal ortam modeli eğitmez, yalnız sabit sürümü API/OCI/Kubernetes ile entegre eder. Production release manifesti image digest ile model version\'ı bağlar.',
    'configs/{data,features,training,serving,drift}/':
        'configs/{data,features,training,colab,serving,drift}/',
    'tests/{unit,integration,contract,smoke,fixtures}/':
        'tests/{model_colab,integration,contract,smoke,fixtures}/',
    'infra/{docker,k8s,monitoring}/':
        'notebooks/colab/              # veri, test, train, evaluate ve export girişleri\ninfra/{docker,k8s,monitoring}/',
    '.github/workflows/            # CI, image, staging, production, retraining':
        '.github/workflows/            # lokal integration CI, image, staging ve production',
    '("PR-fast", "Her PR", "Lock, lint, format, typecheck, unit, secret/license/dependency", "Dakikalar içinde geri bildirim; gerekli kontrol")':
        '("PR-fast", "Her PR", "Lock, lint, format, typecheck, model-dışı unit/integration, secret/license/dependency", "Model testleri burada koşmaz; Colab kanıtı ayrı kapıdır")',
    '("PR-model", "Training/model değişince", "One-batch overfit, kısa CPU train, lineage/artifact test", "Tam eğitim PR\'da çalışmaz")':
        '("Colab-model", "Training/model değişince manuel dispatch", "Feature/model testleri, one-batch overfit, kısa GPU run, lineage ve artifact", "Model kapısı Colab kanıtı olmadan geçmez")',
    '("PR-api", "API/inference değişince", "Golden parity, OpenAPI contract, HTTP integration, latency smoke", "Training-serving skew merge\'i engeller")':
        '("Local-integration", "API/inference değişince", "Export bundle doğrulama, golden parity, OpenAPI, HTTP ve latency smoke", "Lokal ortam eğitim yapmaz; skew merge\'i engeller")',
    '("Full-training", "Manuel/zamanlı/tetikli", "Gerçek DVC veri, train, evaluate, registry candidate", "Production terfisi ayrı onay kapısı")':
        '("Colab-full-training", "Manuel Colab GPU", "Gerçek DVC veri, tüm model testleri, train, evaluate, immutable candidate export", "Notebook run kanıtı ve production terfisi ayrı kapı")',
    'Python sürümü, pyproject.toml, lock dosyası ve core/train/serve/dev bağımlılık grupları sabitlenir. CPU varsayılan, GPU ayrı profil olur.':
        'Python sürümü ve bağımlılıklar sabitlenir. Lokal core/serve/dev profili model eğitmez; Colab için GPU uyumlu train lock dosyası ve kurulum hücresi ayrı tutulur.',
    'src/radariqops altına data, features, training, evaluation, tracking, inference, monitoring ve retraining paketleri; services/api, tests, configs, infra ve docs dizinleri açılır.':
        'src/radariqops altına ana paketler; services/api, tests, configs, infra ve docs dizinleri açılır. notebooks/colab altında 00_bootstrap, 10_model_tests, 20_train ve 30_evaluate_export giriş notebook\'ları oluşturulur.',
    'Paket import smoke testi ve repo ağacı kontrolü; notebook üretim bağımlılığı olamaz.':
        'Paket import smoke testi ve repo ağacı kontrolü; notebook yalnız orkestrasyon girişidir, model mantığı src paketlerinde kalır ve lokal ortam notebook çalıştırmaz.',
    'Temiz sanal ortam kurulumu; lock dosyasından çözüm ve temel import testi.':
        'Temiz lokal serve kurulumu ve temiz Colab GPU runtime kurulumu; iki ortamda ortak inference import testi.',
    'Makefile veya eşdeğer task runner ile setup, lint, typecheck, test, data-smoke, train-smoke, api-smoke ve compose-up komutları eklenir.':
        'Makefile veya eşdeğer task runner ile lokal setup, lint, typecheck, integration-test, api-smoke ve compose-up komutları; Colab notebook girişleri için data, model-test, train, evaluate ve export komutları eklenir.',
    'Unit, integration, contract, smoke ve slow marker\'ları; deterministik seed fixture\'ları; geçici artifact alanı ve kapsama raporu kurulumu eklenir.':
        'Model testleri Colab marker/grubuna; API, contract, artifact yükleme ve smoke testleri lokal integration grubuna ayrılır. Deterministik seed fixture\'ları ve kanıt manifesti eklenir.',
    'Boş/örnek test paketi paralel koşabilir; slow testler varsayılan PR akışından ayrıdır.':
        'Lokal test komutu model testlerini toplamaz; Colab test komutu feature, gradient, overfit, reproducibility ve evaluation testlerinin tamamını toplar.',
    'Pull request için lock doğrulama, lint, format, typecheck ve unit test işleri; path filtresi, concurrency cancel ve dependency cache eklenir.':
        'Pull request için lock doğrulama, lint, format, typecheck ve lokal integration testleri eklenir. Model kodu değişirse Colab run manifesti ve notebook kanıtı zorunlu kontrol olur.',
    'dvc.yaml ve params.yaml raw -> validate -> preprocess -> split -> report zincirini, bağımlılıkları ve çıktıları bağlar. PR\'da küçük fixture ile çalışır.':
        'dvc.yaml ve params.yaml raw -> validate -> preprocess -> split -> report zincirini bağlar. Gerçek veri ve veri/model testleri Colab\'de; lokal ortam yalnız indirilen artifact manifestini doğrular.',
    'dvc repro ikinci koşuda no-op; data-smoke işi cache\'siz temiz ortamda geçer. v0.1.0-data etiketi için G2 hazırdır.':
        'Temiz Colab runtime\'ında DVC pull/repro kanıtı ve aynı split hash\'i üretilir; lokal ortam model verisini işlemeden export manifestini doğrular.',
    '"name": "Faz 3 - Feature, baseline ve tekrarlanabilir eğitim çekirdeği"':
        '"name": "Faz 3 - Colab feature, model testleri ve GPU eğitim çekirdeği"',
    '"goal": "Model deneyini notebook\'tan çıkarıp deterministik, testli ve karşılaştırılabilir komutlara dönüştürmek."':
        '"goal": "Tüm feature/model testlerini ve eğitimi Colab GPU üzerinde deterministik, yeniden başlatılabilir ve karşılaştırılabilir hale getirmek."',
    '"gate": "G3: Baseline ve 1D CNN aynı split\'te koşuyor; one-batch overfit, resume ve tekrarlanabilirlik testleri geçiyor."':
        '"gate": "G3: Temiz Colab GPU runtime\'ında tüm model testleri, baseline ve 1D CNN aynı split\'te koşuyor; one-batch overfit, resume ve tekrarlanabilirlik kanıtları Drive\'a yazılıyor."',
    '"gate": "G1: Temiz klonda kurulum, statik kontroller, unit test ve güvenlik kontrolleri yeşil."':
        '"gate": "G1: Temiz lokal klonda kurulum, statik kontroller, model-dışı unit/integration ve güvenlik kontrolleri yeşil; model testleri Colab kapısındadır."',
    'Train/validation döngüsü, gradient yönetimi, mixed precision opsiyonu, metrik toplama ve cihaz seçimi eklenir. CPU her zaman desteklenir.':
        'Colab GPU train/validation döngüsü, gradient yönetimi, mixed precision, metrik toplama ve cihaz doğrulaması eklenir. Eğitim GPU yoksa başlamaz; lokal CPU eğitim yolu kapsam dışıdır.',
    'feat(training): implement CPU GPU training loop':
        'feat(training): implement Colab GPU training loop',
    'Küçük fixture bir epoch CPU\'da biter; GPU yokken sessiz davranış değişikliği yerine açık fallback kaydı oluşur.':
        'Temiz Colab GPU runtime\'ında küçük fixture bir epoch biter; GPU bağlı değilse eğitim açık hatayla durur ve CPU fallback yapılmaz.',
    'Latest/best checkpoint, optimizer/scheduler state, epoch ve RNG state kaydedilir. Early stopping validation metriğine bağlıdır.':
        'Latest/best checkpoint, optimizer/scheduler state, epoch ve RNG state her epoch Google Drive\'a atomik kaydedilir. Colab oturum kopmasına karşı resume zorunludur.',
    'Overfit testi slow marker altında düzenli çalışır; gradient kopması merge\'i engeller.':
        'Overfit ve gradient testleri Colab model-test hücresinde çalışır; başarılı test raporu ve runtime kimliği olmadan model kapısı geçmez.',
    'Metrikler tanımlı toleransta; performans raporu CI artifact\'ı. Tam GPU eğitimi PR\'da değil manuel/zamanlanmış pipeline\'dadır.':
        'İki temiz Colab GPU run metrikleri tolerans içinde eşleşir; süre, VRAM ve throughput raporu Drive artifact\'ıdır. Lokal makinede hiçbir model testi veya eğitim çalıştırılmaz.',
    'MLflow URI, experiment/run adlandırma, yerel dosya backend\'i ve ortam değişkenleri config\'e alınır. mlruns Git\'e girmez; erişim hatası açıkça raporlanır.':
        'Colab\'den erişilebilen kalıcı MLflow tracking URI ve artifact store yapılandırılır. Kimlik bilgileri Colab Secrets\'tan alınır; notebook veya Git\'e yazılmaz.',
    'Yerel MLflow ile run aç/kapat integration testi; başarısız run status\'u doğru işaretlenir.':
        'Temiz Colab runtime\'ında run aç/kapat ve artifact upload testi; oturum kopması veya upload hatası doğru status ile kaydedilir.',
    'Git SHA, dirty flag, DVC/data revision, split hash, config hash, seed, Python/bağımlılık ve donanım bilgisi her run\'a yazılır.':
        'Git SHA, DVC/data revision, split/config hash, seed, Colab runtime kimliği, Python/bağımlılık, GPU modeli ve CUDA bilgisi her run\'a yazılır.',
    'Epoch metrikleri, checkpoint, confusion matrix, classification report, çözümlenmiş config ve log özeti MLflow artifact\'ı olur.':
        'Epoch metrikleri, checkpoint, test raporları, confusion matrix, classification report, config ve log özeti Colab\'den kalıcı MLflow/Drive artifact alanına yüklenir.',
    'Hedef CPU profilinde warmup sonrası tekli/batch p50-p95-p99, throughput, model boyutu ve peak memory ölçülür.':
        'Colab GPU\'da eğitim throughput, epoch süresi, peak VRAM ve model boyutu ölçülür. Gerçek servis p50-p95-p99 ölçümü lokal integration fazında yapılır.',
    'Model signature, input example, label map ve preprocessing contract ile registry kaydı oluşturulur. Candidate etiketi immutable model version\'a çözülür.':
        'Colab\'de geçen model signature, input example, label map, preprocessing contract ve golden outputs ile checksum\'lı export bundle oluşturulur; immutable registry version kaydedilir.',
    '"name": "Faz 5 - Eğitim-serving eşitliği ve API"':
        '"name": "Faz 5 - Lokal model entegrasyonu ve API"',
    '"goal": "Aynı model ve preprocessing sözleşmesini güvenli, gözlenebilir bir HTTP servisine dönüştürmek."':
        '"goal": "Colab\'den çıkan immutable model paketini lokal ortamda yeniden eğitim yapmadan güvenli ve gözlenebilir bir HTTP servisine entegre etmek."',
    'Serving, eğitimdeki aynı transform paketini ve version\'lı label map\'i kullanır. Ayrı kopya preprocessing kodu yasaklanır.':
        'Lokal serving, Colab export bundle içindeki aynı transform sözleşmesini ve version\'lı label map\'i kullanır. Ayrı preprocessing kopyası ve lokal eğitim yasaklanır.',
    'Model alias\'ı deployment anında immutable version\'a çözülür; pod restart\'ında sessiz model değişimi olmaz. Cache ve checksum doğrulaması eklenir.':
        'Colab\'den terfi eden model alias\'ı lokal entegrasyonda immutable version\'a çözülür; bundle indirilir, checksum ve schema doğrulanır. Pod restart\'ında sessiz değişim olmaz.',
    'Sabit IQ örnekleri için preprocessing hash\'i, logits toleransı, sınıf ve confidence regression snapshot\'ları eklenir.':
        'Colab export bundle içindeki sabit IQ, preprocessing hash, logits, sınıf ve confidence değerleri lokal serving sonucuyla karşılaştırılır; bu bir entegrasyon testidir, model testi değildir.',
    'PR API işi OpenAPI artifact\'ı üretir; hata oranı sıfır ve gevşek başlangıç p95 bütçesi içinde olmalı. v0.3.0-api hazırdır.':
        'Lokal API işi OpenAPI artifact\'ı üretir; Colab model bundle\'ı ile hata oranı sıfır ve başlangıç p95 bütçesi içinde olmalıdır. v0.3.0-api hazırdır.',
    'Compose profilleri API, MLflow ve monitoring geliştirme bileşenlerini kalıcı volume ve health dependency\'leriyle kurar. Model version açık config\'tir.':
        'Compose profilleri lokal API ve monitoring bileşenlerini kurar; yalnız Colab\'den terfi etmiş immutable model version kullanılır. Lokal training servisi bulunmaz.',
    'Tetik validate -> preprocess -> train -> evaluate -> registry candidate zincirini başlatır; data/code/config/model kimlikleri audit kaydına yazılır. Drift tek başına production promotion yapmaz.':
        'Drift tetikleyicisi otomatik production eğitimi yapmaz; onaylı Colab retraining runbook\'unu ve sabit config\'i hazırlar. Colab validate -> model-tests -> train -> evaluate -> registry candidate zinciri manuel başlatılır ve audit kaydı tutulur.',
    'Yetersiz örnek, cooldown, validation hatası ve training hatası senaryoları güvenli sonlanır; champion değişmez.':
        'Yetersiz örnek, cooldown, Colab GPU yokluğu, oturum kopması, validation/test/training ve artifact upload hataları güvenli sonlanır; champion değişmez.',
    'Aynı config ile kısa training run başlat; MLflow\'da Git SHA, data rev, metrik ve artifact\'ı aç.':
        'Temiz Colab GPU runtime\'ında model testlerini ve training run\'ı başlat; Drive checkpoint\'ini, MLflow Git SHA/data rev/GPU/metrik/artifact kaydını göster.',
    'API performans eşiği hedef donanım belirtilmeden sabitlenmez. Commit 044 ve staging ölçümü ilk gerçek p95 bütçesini üretir.':
        'Colab commit 044 eğitim throughput/VRAM bütçesini; lokal API ve staging ölçümleri ise gerçek serving p95 bütçesini üretir. Eğitim ve serving performansları birbirine karıştırılmaz.',
}


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS.items():
        if old not in source:
            raise RuntimeError(f"Beklenen kaynak metni bulunamadı: {old[:100]}")
        source = source.replace(old, new)

    runtime_file = Path(__file__).resolve()
    namespace = {"__name__": "__main__", "__file__": str(runtime_file)}
    exec(compile(source, str(SOURCE), "exec"), namespace)


if __name__ == "__main__":
    main()
