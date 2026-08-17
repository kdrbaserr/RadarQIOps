from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


ROOT = Path(r"C:\Users\kadir\RadarIQops")
OUTPUT = ROOT / "output" / "pdf" / "01kadircv.pdf"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf"))

NAVY = colors.HexColor("#12263F")
TEAL = colors.HexColor("#008C9E")
MUTED = colors.HexColor("#506784")
RULE = colors.HexColor("#B8C8D5")

doc = SimpleDocTemplate(
    str(OUTPUT),
    pagesize=A4,
    leftMargin=18 * mm,
    rightMargin=18 * mm,
    topMargin=13 * mm,
    bottomMargin=12 * mm,
    title="Kadir Başer - Özgeçmiş",
    author="Kadir Başer",
)

styles = {
    "name": ParagraphStyle(
        "name", fontName="Arial-Bold", fontSize=27, leading=28,
        textColor=NAVY, spaceAfter=0,
    ),
    "tagline": ParagraphStyle(
        "tagline", fontName="Arial-Bold", fontSize=12.3, leading=14,
        textColor=TEAL, spaceAfter=7,
    ),
    "contact": ParagraphStyle(
        "contact", fontName="Arial", fontSize=8.7, leading=11,
        textColor=MUTED, spaceAfter=0,
    ),
    "section": ParagraphStyle(
        "section", fontName="Arial-Bold", fontSize=11.8, leading=13,
        textColor=TEAL, spaceBefore=6, spaceAfter=1,
    ),
    "body": ParagraphStyle(
        "body", fontName="Arial", fontSize=9, leading=11.1,
        textColor=NAVY, alignment=TA_LEFT, spaceAfter=0,
    ),
    "role": ParagraphStyle(
        "role", fontName="Arial", fontSize=9.5, leading=11.5,
        textColor=NAVY, spaceBefore=3.5, spaceAfter=0.5,
    ),
    "tech": ParagraphStyle(
        "tech", fontName="Arial", fontSize=8.5, leading=10.2,
        textColor=MUTED, spaceAfter=0.5,
    ),
    "bullet": ParagraphStyle(
        "bullet", fontName="Arial", fontSize=8.7, leading=10.5,
        textColor=NAVY, leftIndent=10, firstLineIndent=-7,
        bulletIndent=0, spaceAfter=0.25,
    ),
}


def p(text, style="body"):
    return Paragraph(text, styles[style])


def section(title):
    return [
        p(title, "section"),
        HRFlowable(width="100%", thickness=0.45, color=RULE, spaceBefore=0, spaceAfter=4),
    ]


def bullet(text):
    return Paragraph(text, styles["bullet"], bulletText="•")


story = [
    p("KADİR BAŞER", "name"),
    p("YAZILIM MÜHENDİSLİĞİ ÖĞRENCİSİ | YAPAY ZEKÂ VE MLOPS", "tagline"),
    p(
        "Malatya, Türkiye | +90 537 370 95 22 | baserkdr44@gmail.com<br/>"
        '<link href="https://kadirbaser.com" color="#008C9E">kadirbaser.com</link> | '
        '<link href="https://github.com/kdrbaserr" color="#008C9E">github.com/kdrbaserr</link> | '
        '<link href="https://linkedin.com/in/kadir-baser-623725294" color="#008C9E">linkedin.com/in/kadir-baser-623725294</link>',
        "contact",
    ),
]

story += section("PROFİL")
story += [
    p(
        "Makine öğrenmesi, arka uç geliştirme ve biyomedikal sinyal işleme alanlarında projeler geliştiren "
        "üçüncü sınıf Yazılım Mühendisliği öğrencisi. Tekrarlanabilir ML iş akışları, model değerlendirme ve "
        "üretime alma süreçlerine odaklanıyor. Sağlık teknolojileri ve sensör verilerine yönelik uçtan uca "
        "yapay zekâ sistemleri geliştiriyor."
    )
]

story += section("DENEYİM")
story += [
    p("<b>Başaran İleri Teknoloji</b> | <font color='#506784'>Yazılım Geliştirme Stajyeri | Yaz 2026</font>", "role"),
    bullet("Mühendislerin rehberliğinde küçük özellikler geliştirdi; hataları araştırdı ve değişiklikleri test ederek günlük yazılım geliştirme süreçlerine katkı sağladı."),
    bullet("Git tabanlı iş akışlarını kullandı ve görevleri belgeledi; kod incelemelerine, günlük toplantılara ve teknik görüşmelere katıldı."),
]

story += section("SEÇİLMİŞ PROJELER")
story += [
    KeepTogether([
        p("<b>RadarIQOps - Radar/Sensör MLOps Platformu</b> | <font color='#506784'>Kurucu ve Geliştirici | Tem 2026 - Günümüz</font>", "role"),
        p('<link href="https://github.com/kdrbaserr/RadarQIOps" color="#008C9E">github.com/kdrbaserr/RadarQIOps</link> | Python, NumPy, FastAPI, Docker Compose, pytest, GitHub Actions', "tech"),
        bullet("Radar ve sensör ML deneyleri için veri kümesi inceleme, temel model eğitimi/değerlendirmesi ve FastAPI tabanlı çıkarım servisi sunan bir Python platformu geliştiriyor."),
        bullet("Birim, sözleşme, entegrasyon ve API katmanlarında toplam 37 otomatik test oluşturdu; CI süreçlerine kalite ve güvenlik kontrolleri ekledi."),
        bullet("Veri kümesi lisanslarını ve model kökenini belgeledi; sürümlenmiş deneyler ve tekrarlanabilir çalıştırmalar için DVC ve MLflow entegrasyonu üzerinde çalışıyor."),
    ]),
    KeepTogether([
        p("<b>drAI - Biyomedikal Sinyal Yapay Zekâ Platformu</b> | <font color='#506784'>Geliştirici | Mar - Haz 2026</font>", "role"),
        p("PyTorch, PEFT, MNE-Python, NeuroKit2, ONNX, FastAPI, Docker, AWS, React Native", "tech"),
        bullet("MOMENT zaman serisi modelini MIT-BIH, PTB-XL ve PhysioNet verileriyle LoRA/QLoRA kullanarak ince ayarladı; ROC-AUC &gt; 0,88 elde etti."),
        bullet(".edf biçimindeki tıbbi sinyalleri MNE-Python ve NeuroKit2 ile işledi; filtreleme ve ICA tabanlı artefakt giderme uyguladı."),
        bullet("ONNX modellerini dışa aktardı, FastAPI ve Docker ile servis etti; .edf yükleme, tahmin ve raporlama akışları için React Native arayüzleri geliştirdi."),
    ]),
    KeepTogether([
        p("<b>Kone Dijital Asistan - Çevrimdışı Uç Yapay Zekâ Asistanı</b> | <font color='#506784'>Geliştirici | Ağu 2026</font>", "role"),
        p("Kotlin, Jetpack Compose, AudioRecord, Vosk, whisper.cpp, Room", "tech"),
        bullet("VAD, Türkçe konuşma tanıma, güvenli niyet algılama ve eylem yönlendirme mekanizmaları içeren çevrimdışı bir Android sesli asistan geliştirdi."),
        bullet("Vosk ve nicemlenmiş whisper.cpp modellerini 50'den fazla ses kaydı üzerinde; p50/p95 gecikme, bellek kullanımı ve model boyutu bakımından karşılaştırdı."),
        bullet("Tekrarlanabilir cihaz değerlendirmesi için yerel telemetri, kişisel veri maskeleme ve 120 komutluk saha testi matrisi ekledi."),
    ]),
]

story += section("TEKNİK YETKİNLİKLER")
story += [
    p("<b>Yapay Zekâ ve Sinyal:</b> Python, PyTorch, Hugging Face Transformers, PEFT (LoRA/QLoRA), ONNX Runtime, NumPy, MNE-Python, NeuroKit2, SHAP, Grad-CAM"),
    p("<b>MLOps ve Arka Uç:</b> FastAPI, Docker/Compose, MLflow, DVC, pytest, GitHub Actions, AWS (ECS, ECR, RDS), PostgreSQL"),
    p("<b>Yazılım ve Araçlar:</b> TypeScript, Node.js, React/React Native, Kotlin, Jetpack Compose, Git/GitHub, Linux (Pop!_OS), REST API'leri"),
]

story += section("EĞİTİM VE DİLLER")
story += [
    p("<b>Fırat Üniversitesi - Yazılım Mühendisliği Lisans Programı</b> | 2023 - Beklenen Mezuniyet: Haz 2027 | 3. sınıf"),
    p("<b>Diller:</b> Türkçe (Ana dil) | İngilizce (A2 - Temel)"),
]

doc.build(story)
print(OUTPUT)
