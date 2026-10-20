# --------------------------------------------------------------------------
# KONE ELEVATE - backend image
# --------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build tools needed by psycopg2/scientific wheels on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# requirements.lock (not requirements.txt) is installed so the image gets the
# exact scikit-learn/joblib versions the shipped model was trained with - see
# app.ml.model_registry's version assertion, which refuses to load a bundle
# pickled by a different version instead of silently unpickling it.
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

# The trained models and datasets are committed and copied in above, so the
# image uses them as-is. Retrain only if they are missing or were pickled by
# different scikit-learn/joblib versions than requirements.lock installed -
# and then train BOTH models (the forecast model too, not just the classifier).
RUN python scripts/check_models.py \
    || (python scripts/train_model.py && python scripts/train_forecast.py)

# Run as a non-root user.
RUN useradd --create-home --uid 1000 elevate \
    && chown -R elevate:elevate /app
USER elevate

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
