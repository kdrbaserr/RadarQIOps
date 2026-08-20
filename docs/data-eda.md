# Tekrarlanabilir EDA artifact'ları

023 aşaması canonical I/Q verisinin sayısal keşif özetini notebook'tan bağımsız üretir:

```powershell
uv run radariq data eda --config configs/eda.example.yaml
```

Girdi, pickle içermeyen bir NPZ dosyasıdır. Zorunlu alanlar `samples`, `labels` ve `snr_db`;
isteğe bağlı `sample_ids` alanıdır. `snr_db` içinde `NaN`, eksik SNR değerini temsil eder.
`samples`, config'teki gösterime göre `[N, 2, L]` channels-first veya `[N, L]` kompleks
dizidir. EDA yalnız 020 doğrulamasından geçmiş canonical veride çalıştırılmalıdır.

Çıktı dizininde dört artifact oluşur:

- `eda_summary.json`: sınıf/SNR/uzunluk dağılımı, I/Q mean-std ve power özeti;
- `eda_plot_data.json`: grafiklerin kullandığı deterministik veri ve örnek spektrumlar;
- `eda_report.html`: ek kütüphane gerektirmeyen, self-contained SVG raporu;
- `eda_artifacts.json`: input lineage, run kimliği ve artifact SHA-256 değerleri.

Run kimliği input SHA-256 ile semantik config SHA-256 değerlerinden türetilir. Zaman damgası ve
mutlak makine yolu artifact içeriğine alınmaz; aynı byte girdisi ve aynı parametreler aynı run
kimliğini ve aynı çıktıları üretir. Örnek spektrumlar `sample_id` sırasından seçilir. HTML'deki
her grafik, kullandığı `eda_plot_data.json` JSON pointer'ını görünür biçimde taşır.
