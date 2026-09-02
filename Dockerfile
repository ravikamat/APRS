# Dockerfile — APRS V6 Pro Container
# Multi-stage build for minimal production image

# =============================================================================
# STAGE 1: Build dependencies
# =============================================================================
FROM python:3.11-slim AS builder

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for cache)
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# =============================================================================
# STAGE 2: Playwright + Browser dependencies
# =============================================================================
FROM python:3.11-slim AS playwright

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright and browsers
RUN pip install --no-cache-dir playwright==1.40.0
RUN playwright install --with-deps chromium

# =============================================================================
# STAGE 3: Production runtime
# =============================================================================
FROM python:3.11-slim AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    # For Ollama health checks
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r aprs && useradd -r -g aprs -d /app -s /bin/bash aprs

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/aprs/.local

# Copy Playwright browsers from playwright stage
COPY --from=playwright /root/.cache/ms-playwright /home/aprs/.cache/ms-playwright

# Copy application code
COPY --chown=aprs:aprs . .

# Create data directories
RUN mkdir -p /app/data /app/logs /app/backups && chown -R aprs:aprs /app

# Switch to non-root user
USER aprs

# Add local packages to PATH
ENV PATH="/home/aprs/.local/bin:${PATH}"
ENV PLAYWRIGHT_BROWSERS_PATH="/home/aprs/.cache/ms-playwright"

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APRS_DB_PATH=/app/data/research_engine.db \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default command
ENTRYPOINT ["python", "main.py"]
CMD ["web"]