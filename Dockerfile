FROM python:3.11-slim

# Avoid interactive prompts and keep Python output unbuffered for clean logs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SESSIONS_ROOT=/app/.sessions

WORKDIR /app

# Install Python dependencies first to leverage Docker layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and Streamlit config.
COPY app.py ./
COPY .streamlit ./.streamlit

# Per-session working files live here (mounted as tmpfs in docker-compose so
# nothing persists on the VPS disk). Created here so it exists even without the mount.
RUN mkdir -p /app/.sessions

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8503

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8503/_stcore/health').status==200 else sys.exit(1)"

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.address=0.0.0.0", \
    "--server.port=8503", \
    "--server.headless=true"]
