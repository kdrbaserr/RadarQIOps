FROM python:3.11.15-slim-bookworm
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[serve]"
ENV RADARIQ_MODEL_PATH=/models/model.npz
EXPOSE 8000
CMD ["uvicorn", "radariq.services.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
