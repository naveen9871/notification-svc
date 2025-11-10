# ======================
# Stage 1: Builder
# ======================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Copy requirements and install globally (NOT with --user)
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ======================
# Stage 2: Runtime
# ======================
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy Python site-packages from builder (this ensures Django, gunicorn, etc. are present)
COPY --from=builder /usr/local /usr/local

# Copy app source
COPY . .

# Create logs directory and appuser
RUN mkdir -p logs && useradd -m -u 1000 appuser && chown -R appuser:appuser /app

USER appuser

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8005/api/v1/notifications/health/ || exit 1

# Run migrations and start gunicorn
CMD ["bash", "-c", "python manage.py migrate && exec gunicorn notification_service.wsgi:application --bind 0.0.0.0:8005 --workers 2 --timeout 120 --access-logfile - --error-logfile -"]
