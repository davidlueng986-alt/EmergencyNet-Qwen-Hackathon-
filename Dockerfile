# EmergencyNet Field + Base (same image, different CMD)
# Python 3.11 slim — Gradio UIs on 7860 / 7861
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Gradio defaults (overridable in compose)
    FIELD_GRADIO_HOST=0.0.0.0 \
    FIELD_GRADIO_PORT=7860 \
    BASE_GRADIO_HOST=0.0.0.0 \
    BASE_GRADIO_PORT=7861

WORKDIR /app

# System dependencies for serial access and health checks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer cache)
COPY requirements*.txt /app/
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

# Application code + static data tables
COPY emergencynet/ /app/emergencynet/
COPY data/ /app/data/

# Default: field UI (compose overrides for base)
EXPOSE 7860 7861
CMD ["python", "-m", "emergencynet.gradio_app"]
