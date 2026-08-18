# Pull request ve release politikası

## Pull request politikası

- `.github/pull_request_template.md` içindeki beş zorunlu kontrol işaretlenir.
- Draft PR merge edilemez.
- Bütün required status check'ler yeşil olmalıdır.
- Tartışmalar çözümlenmeden merge yapılmaz.
- Solo geliştirme döneminde zorunlu onay sayısı sıfırdır; ikinci maintainer eklendiğinde bir CODEOWNER onayı zorunlu yapılır.

## Ana dal koruması

`main` için doğrudan push, force-push ve silme kapalı tutulur. Değişiklikler PR ve squash merge ile alınır. Zorunlu check adları:

- `pr-fast-quality`
- `pr-colab-evidence`
- `pr-security-policy`
- `pr-dependency-security`
- `pr-policy`

## Sürüm ve changelog

Proje Semantic Versioning kullanır:

- `fix` veya geriye uyumlu küçük bakım: **patch** (`0.1.0` → `0.1.1`)
- `feat`: **minor** (`0.1.0` → `0.2.0`)
- `!` veya `BREAKING CHANGE`: **major** (`0.1.0` → `1.0.0`)
- `docs`, `test`, `ci`, `chore`: tek başına sürüm yükseltmez.

Kullanıcıya görünen değişiklikler önce `CHANGELOG.md` dosyasının `Unreleased` bölümüne yazılır. Release sırasında bu bölüm sürüm ve tarihe dönüştürülür; temiz required check sonucu olmayan commit veya artifact yayınlanmaz.

## Süreli politika istisnası

Zorunlu bir kontrol geçici olarak uygulanamıyorsa `policy/exceptions.json` içinde PR numarası, atlanan kontroller, sorumlu, gerekçe, onay ve bitiş tarihi kaydedilir. İstisna en fazla 30 gündür; süresi dolmuş veya eksik kayıt CI'ı başarısız yapar.
