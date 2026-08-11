# PR hızlı kalite workflow'u

`.github/workflows/pr-fast-quality.yaml`, `main` dalını hedefleyen her pull request'te iki benzersiz job çalıştırır.

## `pr-fast-quality`

Python 3.11.15 ve uv 0.11.14 ile temiz Ubuntu ortamı kurar. Sırasıyla lock doğrulama, kilitli kurulum, Ruff lint/import, format, Markdown/YAML, mypy, bütün lokal testler ve API smoke kontrolünü çalıştırır. Görevler dosya değiştirmeyen check modundadır.

## `pr-colab-evidence`

PR diff'inde model, training, evaluation veya ilgili config değişikliği yoksa başarılı olur. Hassas değişiklik varsa `evidence/colab/*.json` altında güncel source-tree hash'iyle eşleşen ve bütün Colab kanıt alanlarını taşıyan manifest zorunludur.

Notebook ve büyük artifact'lar Git'e eklenmez; yalnız hash ve test/export manifestleri sürümlenir.

## Merge kapıları

Branch protection'a yazılacak bütün required check adları `docs/repository-policy.md` içinde tanımlıdır. Bu workflow'un sağladığı adlar:

- `pr-fast-quality`
- `pr-colab-evidence`

Workflow yalnız `contents: read` izni kullanır. Aynı PR'a yeni commit gelirse önceki çalışma concurrency kuralıyla iptal edilir ve son commit doğrulanır.
