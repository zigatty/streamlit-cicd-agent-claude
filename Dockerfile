# =============================================================================
# Dockerfile — Streamlit Dashboard
# App    : streamlit-dashboard
# Python : 3.12-slim (multi-stage)
# Port   : 8501 (Streamlit default; Cloud Run overrides via $PORT)
# User   : appuser (UID 1001, non-root)
# =============================================================================

# ---- Stage 1: build deps ----------------------------------------------------
# Installs packages into /install so the runtime stage gets no build tools
FROM python:3.12-slim AS builder

WORKDIR /build

# gcc is needed for compiled wheels (numpy, pandas C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
  && rm -rf /var/lib/apt/lists/*

# Copy manifest first — pip layer only rebuilds when requirements.txt changes
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt

# ---- Stage 2: runtime image -------------------------------------------------
FROM python:3.12-slim AS runtime

ARG BUILD_DATE
ARG VCS_REF
LABEL org.opencontainers.image.title="streamlit-dashboard" \
      org.opencontainers.image.description="Streamlit analytics dashboard" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://bitbucket.org/YOUR_WORKSPACE/streamlit-dashboard"

# Copy only the installed packages — no gcc, no apt cache, lean image
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source (see .dockerignore for exclusions)
COPY . .

# Non-root user — satisfies Trivy/Snyk high-severity rule for root containers
RUN useradd --uid 1001 --no-create-home --shell /bin/false appuser
USER appuser

# Cloud Run injects PORT at runtime (default 8080 unless you set --port 8501)
# We default to 8501 for local docker run compatibility
ENV PORT=8501
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Streamlit telemetry off in production
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true

EXPOSE 8501

# Health check for local docker run / docker-compose
# Cloud Run uses HTTP checks at /_stcore/health natively
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" \
    || exit 1

# Cloud Run injects $PORT — Streamlit must bind to it
CMD ["sh", "-c", \
     "streamlit run streamlit_app.py \
        --server.port=${PORT} \
        --server.address=0.0.0.0 \
        --server.headless=true \
        --server.enableCORS=false \
        --server.enableXsrfProtection=true"]
