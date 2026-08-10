# Altyapı

Yerel API image'ı, eğitim sonunda oluşan modeli salt okunur bağlayarak çalıştırır:

```powershell
docker build -f infra/Dockerfile -t radariq-api .
docker run --rm -p 8000:8000 -v "${PWD}/artifacts:/models:ro" radariq-api
```

Kubernetes ve registry tanımları, yerel eğitim/değerlendirme/API akışı doğrulandıktan sonra eklenecektir.
