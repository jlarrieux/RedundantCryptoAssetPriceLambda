# --- Stage 1: The "Builder" ---
# Use a full python image that includes build tools
FROM public.ecr.aws/docker/library/python:3.10-bookworm as builder

# Set build-time argument for the Git PAT. This will NOT be in the final image.
ARG GIT_PAT

# Install git and configure it to use the PAT for private repos
RUN apt-get update && apt-get install -y git && apt-get clean && \
    git config --global url."https://${GIT_PAT}@github.com/".insteadOf "https://github.com/"

WORKDIR /app

# Copy your local application code and requirements into the builder
COPY . .

# Install python packages with cleanup to reduce size
RUN pip install --no-cache-dir -r requirements.txt && \
    # Clean up Python bytecode and cache files
    find /usr/local/lib -type d -name "__pycache__" -exec rm -rf {} + && \
    find /usr/local/lib -type f -name "*.pyc" -delete && \
    # Remove pip cache
    pip cache purge


# --- Stage 2: The "Final" Image ---
# Start from a clean, slim base image for a small final size
FROM public.ecr.aws/docker/library/python:3.10-slim

WORKDIR /app

# Define ARGs for AWS credentials that will be passed during the build
ARG AWS_LIGHTSAIL_ACCESS_KEY_ID
ARG AWS_LIGHTSAIL_SECRET_ACCESS_KEY

# Set ENV variables in the final image so your application can use them at runtime
# Set PYTHONPATH to ensure Python can find your local modules.
ENV AWS_ACCESS_KEY_ID=${AWS_LIGHTSAIL_ACCESS_KEY_ID}
ENV AWS_SECRET_ACCESS_KEY=${AWS_LIGHTSAIL_SECRET_ACCESS_KEY}
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
ENV PYTHONPATH /app

# Install only RUNTIME dependencies. No git, gcc, or build-essential.
RUN apt-get update && apt-get install -y \
    curl \
    supervisor \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire prepared application from the builder stage
COPY --from=builder /app /app

# Copy the installed python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

# Copy essential Python binaries from builder
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy supervisor config to standard location
COPY supervisord.conf /etc/supervisord.conf
RUN mkdir -p /var/log/supervisor /tmp/prometheus_multiproc && \
    chmod -R 777 /var/log/supervisor /tmp/prometheus_multiproc

# Healthcheck remains the same
HEALTHCHECK --interval=50s --timeout=3s \
  CMD curl -f http://localhost:${NOMAD_PORT_http}/ || exit 1

# Expose ports using the same variable names as HCL
EXPOSE ${NOMAD_PORT} ${PROMETHEUS_METRICS_PORT}

# Run Uvicorn with your Quart app
CMD ["supervisord", "-c", "/etc/supervisord.conf", "-n"]