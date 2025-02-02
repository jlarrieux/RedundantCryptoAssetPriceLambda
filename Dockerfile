# Use the official docker Python 3.10 base image
FROM public.ecr.aws/docker/library/python:3.10-slim

# Set working directory
WORKDIR /app

# Argument for Personal Access Token (only available at build time)
ARG GIT_PAT
# Set the Personal Access Token as an environment variable
ENV GIT_PAT=$GIT_PAT

# Environment variables to optimize Python
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:${NOMAD_PORT_http}/ || exit 1

 # Install git and basic configurations
RUN apt-get update -y && apt-get install -y \
    git \
    curl \
    supervisor \
    gcc \
    build-essential \
    libffi-dev \
    libssl-dev \
    && apt-get clean \
    && git config --global url."https://${GIT_PAT}@github.com/".insteadOf "https://github.com/"

# Copy the application code to the container's /var/task/ directory
COPY . /app/

# Install additional dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Add this to your Dockerfile
RUN mkdir -p /tmp/prometheus_multiproc && \
    chmod 777 /tmp/prometheus_multiproc


# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose port for Uvicorn
EXPOSE ${NOMAD_PORT_http} ${NOMAD_PORT_metrics}

# Run Uvicorn with your Quart app
CMD ["supervisord", "-n"]