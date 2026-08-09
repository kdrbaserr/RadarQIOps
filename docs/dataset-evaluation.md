# Radar Hedef Veri Seti Değerlendirmesi

Son doğrulama tarihi: 9 Ağustos 2026

## Amaç ve karar kuralı

Bu belge, RadioML/DeepSig veri setlerini ve fiziksel radar hedeflerini temsil eden alternatifleri; lisans, erişim, sınıf anlamı, SNR, örnek şekli, boyut ve yeniden dağıtım hakkı bakımından karşılaştırır.

Bir veri setinin toplam puanı tek başına “radar hedef sınıflandırmasına uygundur” anlamına gelmez. **Sınıf etiketleri fiziksel hedef kimliğini veya türünü temsil etmiyorsa veri seti hedef sınıflandırma için elenir.** Bu nedenle RadioML veri setleri yüksek SNR ve veri biçimi puanı alsa bile yalnızca sinyal/modülasyon analizi için kullanılabilir.

Lisans değerlendirmesi teknik bir ön elemedir; hukuki görüş değildir. Ürüne veri veya türetilmiş veri dahil edilmeden önce lisans sahibi ve güncel lisans metni ayrıca doğrulanmalıdır.

## Puanlama yöntemi

Her ölçüt 0–2 arasında puanlanır; en yüksek toplam 14'tür.

| Ölçüt | 0 puan | 1 puan | 2 puan |
|---|---|---|---|
| Lisans | Belirsiz veya yayımlanmamış | Açık fakat ticari olmayan/kısıtlı | Açık ve ticari kullanıma elverişli |
| Erişim | Pratikte erişilemiyor | Hesap, başvuru, kırık ayna veya fiziksel aktarım gerektiriyor | Kararlı ve doğrudan indirme |
| Sınıf anlamı | Fiziksel hedef değil | Fiziksel fakat dar, kaba veya ürün hedefiyle kısmi uyumlu | Açık fiziksel hedef sınıfları |
| SNR | Yok/belirtilmemiş | RCS, güç veya kalite vekili var; açık SNR etiketi yok | Örnek bazında açık SNR etiketi |
| Örnek şekli | Belirsiz | Değişken uzunlukta veya işlem hattına bağlı | Açık, sabit ve makinece okunabilir |
| Boyut / pilot kolaylığı | 250 GB üstü veya doğrulanmamış | 20–250 GB | 20 GB veya altı |
| Yeniden dağıtım | Belirsiz veya yasak | Koşullu; NC/SA/ND yükümlülükleri var | Açıkça izinli, ticari yeniden kullanım mümkün |

Boyut puanı veri kalitesini değil, ilk pilotu indirme, saklama ve tekrarlama kolaylığını ölçer.

## Özet puan tablosu

| Veri seti | Lisans | Erişim | Sınıf | SNR | Şekil | Boyut | Dağıtım | Toplam | Hedef sınıflandırma kararı |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| RadioML 2016.10A | 1 | 2 | 0 | 2 | 2 | 2 | 1 | **10/14** | Elendi — modülasyon sınıfları |
| RadioML 2018.01A | 1 | 2 | 0 | 2 | 2 | 2 | 1 | **10/14** | Elendi — modülasyon sınıfları |
| RadarScenes | 1 | 2 | 2 | 1 | 1 | 2 | 1 | **10/14** | Araştırma pilotuna uygun |
| CARRADA | 1 | 2 | 2 | 0 | 2 | 1 | 1 | **9/14** | Tensor/segmentasyon pilotuna uygun |
| RADDet | 2 | 1 | 2 | 0 | 2 | 0 | 2 | **9/14** | Erişim doğrulanırsa güçlü aday |
| K-Radar | 1 | 1 | 2 | 0 | 2 | 0 | 1 | **7/14** | İleri araştırma; MVP için uygun değil |
| MSTAR | 0 | 1 | 2 | 0 | 0 | 0 | 0 | **3/14** | Lisans ve biçim teyidi olmadan kullanma |

## Ayrıntılı değerlendirme

### RadioML 2016.10A

- **Kaynak ve lisans:** DeepSig, açık veri setlerinin CC BY-NC-SA 4.0 ile lisanslandığını ve bunların desteklenmeyen tarihsel akademik veri setleri olduğunu belirtiyor. Ticari ürün kullanımı için alternatif lisans gerekiyor. [DeepSig veri setleri](https://www.deepsig.ai/datasets/)
- **Sınıf anlamı:** 8 dijital ve 3 analog olmak üzere 11 haberleşme modülasyonu. Etiketler araç, uçak, gemi veya başka bir fiziksel hedef değildir.
- **SNR:** Yaygın sürümde −20 dB ile +18 dB arasında 2 dB adımlar bulunur.
- **Örnek:** Her örnek `2 × 128` I/Q değeridir; pickle sözlüğü modülasyon ve SNR anahtarlarıyla düzenlenir.
- **Boyut:** 220.000 örnek. Yalnızca float32 I/Q yükü yaklaşık 225 MB'dir; gerçek pickle/arşiv boyutu serileştirme ek yüküne göre değişir.
- **Dağıtım:** Atıf, ticari olmama ve aynı lisansla paylaşma koşullarıyla yeniden dağıtılabilir. Ürün paketine ticari biçimde eklenemez.
- **Karar:** Veri yükleme, I/Q model prototipi ve SNR'ye göre dayanıklılık deneyi için kullanılabilir; hedef sınıflandırma eğitimi veya doğrulaması için kullanılamaz.

### RadioML 2018.01A

- **Kaynak ve lisans:** CC BY-NC-SA 4.0; DeepSig bunu da desteklenmeyen tarihsel araştırma verisi olarak tanımlar. [DeepSig veri setleri](https://www.deepsig.ai/datasets/)
- **Sınıf anlamı:** 24 analog/dijital modülasyon türü; fiziksel radar hedef sınıfı yoktur.
- **SNR:** Yaygın sürüm −20 dB ile +30 dB arasında 2 dB adımlar içerir.
- **Örnek:** HDF5 içinde örnek başına 1.024 karmaşık I/Q örneği (`1024 × 2` gerçek gösterim), sınıf ve SNR etiketleri.
- **Boyut:** Sağlayıcı yaklaşık 2 milyon örnek bildirir. Float32 I/Q yükü tek başına yaklaşık 16 GB olduğundan pilot için hâlâ yönetilebilir, fakat 2016.10A'dan belirgin biçimde büyüktür.
- **Dağıtım:** CC BY-NC-SA koşulları geçerlidir; ticari yeniden dağıtım yoktur.
- **Karar:** Daha uzun I/Q pencereli sinyal sınıflandırma ve kontrollü SNR deneyi için kullanılabilir; hedef sınıflandırma kanıtı değildir.

### RadarScenes

- **Kaynak ve lisans:** Zenodo üzerinden doğrudan indirilebilir, 11,1 GB ve CC BY-NC-SA 4.0 lisanslıdır. Ticari kullanım yasaktır. [RadarScenes Zenodo kaydı](https://zenodo.org/records/4559821)
- **Sınıf anlamı:** Otomobil, büyük araç, kamyon, otobüs, tren, bisiklet, motorlu iki tekerli, yaya, yaya grubu, hayvan, diğer dinamik nesne ve statik çevre olmak üzere 12 nokta etiketi vardır.
- **SNR:** Örnek başına SNR etiketi yoktur. `rcs` (dBsm) alanı vardır, ancak RCS doğrudan SNR değildir.
- **Örnek:** Bir sahne, değişken sayıda radar tespit satırından oluşur. Her satır zaman, sensör, menzil, azimut, RCS, radyal hız, konum, iz ve sınıf alanları taşır. Sabit tensör isteyen modeller padding/voxelization gibi bir ön işlem gerektirir.
- **Boyut:** 158 sekans, dört saatten fazla sürüş, 7.500'den fazla benzersiz nesne ve 11,1 GB arşiv.
- **Dağıtım:** Atıf + ticari olmama + aynı lisans koşullarıyla paylaşım mümkündür; ticari ürün paketine eklenemez.
- **Karar:** En düşük operasyonel maliyetli gerçek radar hedef pilotudur. Yalnızca hareketli yol kullanıcılarının etiketlendiği ve sağlayıcının ürün kullanımı için anotasyon kalitesi garantisi vermediği dikkate alınmalıdır. [RadarScenes etiketleme açıklaması](https://radar-scenes.com/dataset/labeling/)

### CARRADA

- **Kaynak ve lisans:** Veri CC BY-NC-SA 4.0, kod GPL-3.0'dır. Veri doğrudan proje sayfasından indirilebilir. [CARRADA resmi deposu](https://github.com/valeoai/carrada_dataset)
- **Sınıf anlamı:** Yaya, bisikletli ve araç sınıfları; arka planla birlikte semantik segmentasyon ve nesne örnek anotasyonları.
- **SNR:** Açık örnek-bazlı SNR etiketi yayımlanmamıştır.
- **Örnek:** Range–azimuth–Doppler tensörleri ile range–Doppler, range–angle ve angle–Doppler görünümleri; yaygın RAD tensör şekli `256 × 256 × 64` olarak belgelenmiştir.
- **Boyut:** Ana arşiv 23 GB sıkıştırılmış ve yaklaşık 90 GB açılmıştır. Ayrı RAD tensör arşivi 176 GB sıkıştırılmış, yaklaşık 198 GB açılmıştır.
- **Dağıtım:** Yalnızca CC BY-NC-SA koşullarıyla; ticari ürün dağıtımı yoktur.
- **Karar:** Radar tensörü, nesne segmentasyonu ve kontrollü otomotiv senaryosu prototipi için güçlü adaydır. Sınıf çeşitliliği az ve depolama maliyeti RadarScenes'ten yüksektir.

### RADDet

- **Kaynak ve lisans:** Veri CC BY 4.0 lisanslıdır. Resmi depo, eski Google Drive bağlantısının kapandığını ve bazı verilerin OneDrive/Baidu üzerinden sağlandığını bildiriyor; erişim pilot öncesi fiilen test edilmelidir. [RADDet resmi deposu](https://github.com/ZhangAoCanada/RADDet)
- **Sınıf anlamı:** `person`, `bicycle`, `car`, `motorcycle`, `bus`, `truck` olmak üzere altı fiziksel yol kullanıcısı sınıfı.
- **SNR:** Örnek bazında SNR etiketi yoktur.
- **Örnek:** Sabit `256 × 256 × 64` range–azimuth–Doppler tensörü; kutu ve sınıf yer gerçeği ayrıca verilir.
- **Boyut:** 10.158 etiketli çerçeve. Resmi depo bazı yer gerçeği/ADC türevlerinin yaklaşık 1 TB'a ulaşabildiğini belirttiği için kullanılacak alt paketin gerçek boyutu indirmeden önce doğrulanmalıdır.
- **Dağıtım:** CC BY 4.0 atıf koşuluyla ticari yeniden kullanım ve dağıtıma en elverişli adaydır.
- **Karar:** Lisans açısından en iyi fiziksel hedef adayıdır. Ancak kararsız indirme bağlantıları ve paket boyutu nedeniyle erişim kanıtı alınmadan ana veri seti seçilmemelidir.

### K-Radar

- **Kaynak ve lisans:** Veri CC BY-NC-ND, kod Apache-2.0'dır. Tam veri yaklaşık 15 TB; yerel sunucu veya fiziksel disk aktarımı, yalnızca bir bölüm için Google Drive sunulur. [K-Radar resmi deposu](https://github.com/kaist-avelab/K-Radar)
- **Sınıf anlamı:** Yol nesneleri için 3B kutular ve fiziksel nesne algılama görevi vardır. Kullanılacak sürümün kesin sınıf eşlemesi veri yapılandırmasından ayrıca dondurulmalıdır.
- **SNR:** Açık örnek-bazlı SNR etiketi yoktur; kötü hava koşulları ayrı deney ekseni sağlar fakat SNR'nin yerini tutmaz.
- **Örnek:** Menzil–azimut–elevasyon–Doppler güç ölçümlerini içeren tam 4B radar tensörü.
- **Boyut:** Yaklaşık 35.000 kare ve toplam 15 TB.
- **Dağıtım:** NC ticari kullanımı, ND ise değiştirilmiş/türetilmiş veri dağıtımını sınırlar. Ticari kullanım için sağlayıcıyla ayrıca görüşülmelidir.
- **Karar:** 4B radar ve kötü hava araştırması için değerli; MVP indirme, depolama ve lisans koşulları bakımından uygun değildir.

### MSTAR

- **Kaynak ve erişim:** AFRL/SDMS, MSTAR'ı kamu veri seti olarak listeler; indirme için ücretsiz SDMS hesabı gerekir. [MSTAR resmi sayfası](https://www.sdms.afrl.af.mil/index.php?collection=mstar)
- **Sınıf anlamı:** X-band SAR görüntülerinde tank, piyade savaş aracı ve zırhlı personel taşıyıcı gibi gerçek askerî kara hedefleri bulunur. Resmi hedef sayfası T-72, BMP-2 ve BTR-70 örneklerini, farklı depresyon açılarını ve tam bakış açısı kapsamını açıklar. [MSTAR hedef açıklaması](https://www.sdms.afrl.af.mil/index.php?collection=mstar&page=targets)
- **SNR:** Dağıtım sayfasında standart örnek-bazlı SNR etiketi belirtilmemiştir.
- **Örnek:** SAR görüntü çipi ve sensör/çekim üstverisi kullanılır; resmi genel sayfada tek ve sabit bir tensör şekli taahhüt edilmemiştir. İndirilen koleksiyonun dosya başlıklarıyla doğrulanmalıdır.
- **Boyut:** Resmi genel sayfada toplam indirilebilir boyut açıkça belirtilmemiştir.
- **Dağıtım:** İncelenen resmi sayfalarda açık bir standart veri lisansı veya yeniden dağıtım izni bulunmadı. “Public dataset” ifadesi yeniden paketleyip dağıtma hakkı olarak yorumlanmamalıdır.
- **Karar:** Fiziksel askerî hedef anlamı bakımından en doğrudan adaydır; fakat yazılı kullanım/yeniden dağıtım koşulu, örnek biçimi ve koleksiyon boyutu doğrulanmadan üründe veya eğitim hattında kullanılmamalıdır.

## Ürün kararı

1. **RadioML yalnızca altyapı veri setidir.** I/Q içe aktarma, model deneyi ve SNR kırılımı için kullanılabilir; ürün hedef sınıflandırıcı olarak sunulamaz.
2. **İlk gerçek radar pilotu RadarScenes ile yapılmalıdır.** İndirme kararlı, boyut yönetilebilir ve fiziksel sınıflar açıktır. Sonuç “otomotiv radar nokta sınıflandırma araştırması” olarak adlandırılmalıdır; ticari kullanım için ek lisans gerekir.
3. **Sabit radar tensörü gerekiyorsa CARRADA ikinci seçimdir.** Daha yüksek depolama maliyeti kabul edilerek üç sınıflı kontrollü deney yapılabilir.
4. **Ticari lisans yolu için RADDet öncelikli doğrulama adayıdır.** Önce indirme bağlantısı, seçilen paket boyutu ve CC BY 4.0 lisans dosyasının veriyle birlikte geldiği doğrulanmalıdır.
5. **MSTAR ayrı bir hukuki/teknik keşif işidir.** Askerî hedef iddiası ancak resmi verinin kullanım hakkı, yeniden dağıtım koşulu, veri şeması ve ölçüm kapsamı yazılı biçimde doğrulandıktan sonra değerlendirilebilir.
6. **Hiçbir aday tek başına operasyonel ürün doğrulaması sağlamaz.** Eğitim/test ayrımı, veri sızıntısı kontrolü, sınıf dengesi, sensör alan kayması ve bağımsız gerçek-saha doğrulaması ayrıca yapılmalıdır.

## İndirme öncesi kabul kontrolü

Bir veri seti projeye alınmadan aşağıdaki kanıtlar kaydedilmelidir:

- Lisans metninin yerel kopyası, kaynak URL'si ve erişim tarihi.
- Dosya listesi, toplam byte boyutu ve SHA-256 sağlama toplamları.
- Bir örneğin gerçek `dtype`, `shape`, birim ve eksen sırası.
- Sınıf kimliği–sınıf adı eşleme tablosu ve anotasyon yöntemi.
- SNR alanının gerçek ölçüm mü, sentetik ayar mı, yoksa hiç bulunmayan bir özellik mi olduğu.
- Eğitim, doğrulama ve test bölmelerinin sekans/hedef kimliği düzeyinde ayrıldığına ilişkin kontrol.
- Ham veriyi, dönüştürülmüş örnekleri ve model ağırlıklarını yeniden dağıtma haklarının birbirinden ayrı değerlendirilmesi.

Bu kontroller tamamlanmadan veri seti yalnızca “aday” statüsünde tutulur ve ürün iddiasında kullanılamaz.
