# RadarIQops Ürün Çerçevesi

## Amaç

RadarIQops; radar benzeri gözlem ve senaryo verilerini incelemeyi, karşılaştırmayı ve sonuçları anlaşılır biçimde sunmayı amaçlayan bir analiz ve karar destek ürünüdür. Ürün, doğrulanmış gerçek radar hedef verisi ve buna dayalı ölçülmüş model başarımı bulunmadığı sürece bir **hedef sınıflandırıcı** değildir ve bu şekilde tanıtılmaz.

## Hedef kullanıcı

Birincil kullanıcılar:

- Sentetik, simüle edilmiş veya izinli test verilerini inceleyen radar/sensör analistleri ve mühendisler.
- Senaryoları karşılaştıran, veri kalitesini değerlendiren ve bulguları raporlayan Ar-Ge ekipleri.

İkincil kullanıcılar:

- Analiz sonuçlarını ürün, test veya operasyon planlamasında girdi olarak kullanan teknik karar vericiler.

Ürün, eğitimli bir operatörün veya yetkili karar vericinin yerini almaz.

## Kullanıcı ihtiyacı ve karar çıktısı

Kullanıcının temel ihtiyacı, farklı veri veya senaryolardaki ölçümleri tek bir akışta incelemek, tutarsızlıkları görmek ve sonuçları karşılaştırılabilir bir biçimde kaydetmektir.

Ürünün karar çıktısı şunlarla sınırlıdır:

- Verinin analiz için yeterli, eksik veya şüpheli olduğuna ilişkin kalite göstergeleri.
- Tanımlı ölçütlere göre senaryo veya gözlem karşılaştırmaları.
- Kullanıcının daha ayrıntılı inceleme, yeniden veri toplama ya da senaryoyu reddetme kararını destekleyen özetler ve raporlar.

Ürün, bir hedefin kimliğini veya sınıfını kesin olarak belirleyen operasyonel karar üretmez. Üretilen skor, etiket, benzerlik veya örüntü çıktıları varsa bunlar yalnızca analiz bulgusudur; doğrulanmış hedef sınıfı değildir.

## Online ve offline kullanım

### Offline kullanım

- Temel veri içe aktarma, analiz ve raporlama işlevleri internet bağlantısı olmadan çalışabilmelidir.
- Kullanıcı verisi, açık bir aktarım işlemi yapılmadıkça yerel çalışma ortamından çıkmamalıdır.
- Offline kullanımda harici servis gerektiren güncelleme, paylaşım veya uzaktan eşitleme işlevleri kullanılamaz.

### Online kullanım

- İnternet bağlantısı; ürün güncellemeleri, isteğe bağlı ekip paylaşımı, uzaktan depolama veya entegrasyonlar için kullanılabilir.
- Her çevrimiçi aktarım kullanıcıya görünür olmalı ve açık yetkilendirme gerektirmelidir.
- Online servislerin kullanılamaması, temel yerel analiz akışını engellememelidir.

## Veri girdileri

Ürün şu veri kaynaklarıyla çalışacak şekilde sınırlandırılır:

- Sentetik veya simüle edilmiş radar/sensör gözlemleri.
- Kullanım izni ve kaynağı belgelenmiş test verileri.
- Senaryo parametreleri, sensör yapılandırması ve analiz için gerekli açıklayıcı üstveri.
- Kullanıcının girdiği eşik, filtre ve karşılaştırma ölçütleri.

Girdiler için asgari olarak veri kaynağı, üretim/toplama yöntemi, zaman bilgisi, ölçüm birimleri ve bilinen kalite kısıtları kaydedilmelidir. Dosya biçimleri, zorunlu alanlar ve doğrulama kuralları teknik veri sözleşmesinde ayrıca tanımlanacaktır.

Kaynağı belirsiz, kullanım izni bulunmayan veya gerekli üstverisi eksik veri; doğrulanmış sonuç üretmek için kullanılamaz. Böyle bir durumda ürün kullanıcıyı açıkça uyarmalı ve çıktıyı deneysel/inceleme amaçlı olarak işaretlemelidir.

## Gerçek radar hedef verisi ve ürün iddiası

Gerçek radar hedef verisi bulunmadığı sürece:

- Ürün “hedef sınıflandırıcı”, “otomatik hedef tanıma sistemi” veya eşdeğer bir ifadeyle sunulmaz.
- Başarı, doğruluk, hassasiyet ya da operasyonel güvenilirlik iddiasında bulunulmaz.
- Sentetik veriden üretilen etiket veya skorlar gerçek hedef teşhisi olarak gösterilmez.
- Tanıtım, arayüz ve dokümantasyonda “simülasyon”, “deneysel analiz” veya “karar desteği” ifadeleri kullanılır.

Bu konumlandırmanın değişebilmesi için temsil gücü gösterilmiş, etiketleri doğrulanmış ve kullanımı yetkilendirilmiş gerçek radar hedef verisi; tanımlı bir değerlendirme yöntemi; kabul ölçütleri ve bağımsız doğrulama sonuçları birlikte bulunmalıdır.

## Kapsam dışı

İlk ürün kapsamına şunlar dahil değildir:

- Operasyonel hedef teşhisi veya otomatik hedef sınıflandırma.
- Silah, angajman ya da ateş kontrol kararı üretme.
- İnsan denetimi olmadan gerçek zamanlı operasyonel karar alma.
- Kanıtlanmamış verilerle güvenlik-kritik kullanım veya performans garantisi verme.
- Kaynağı ve kullanım yetkisi belirsiz veriyi toplama, işleme ya da paylaşma.
- İnternet bağlantısını temel analiz için zorunlu kılma.

## Başarı ölçütleri

Ürünün ilk aşamadaki başarısı sınıflandırma doğruluğuyla değil, aşağıdaki ölçütlerle değerlendirilir:

- Desteklenen verinin hatasız içe aktarılması ve doğrulama sorunlarının görünür kılınması.
- Aynı girdilerle tekrar üretilebilir analiz sonuçları.
- Kullanıcının veri kalitesi ve senaryo karşılaştırma kararını izlenebilir biçimde verebilmesi.
- Offline temel akışın çevrimiçi servislere bağımlı olmadan tamamlanabilmesi.
- Deneysel sonuçlarla doğrulanmış gerçek veri sonuçlarının arayüz ve raporlarda açıkça ayrılması.

## Değişiklik ilkesi

Hedef kullanıcı, karar çıktısı, veri kaynağı veya ürün iddiasındaki önemli bir değişiklik bu belge güncellenmeden ürün kapsamına alınmaz. “Hedef sınıflandırıcı” konumlandırmasına geçiş, gerçek veri ve doğrulama koşulları sağlanmadan yalnızca pazarlama kararıyla yapılamaz.
