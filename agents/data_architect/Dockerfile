FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies.
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies.
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache rtk adam azure-devops azure-identity azure-mgmt-fabric azure-purview-scanning requests pytest

# Copy agent-specific files
COPY . .

# Entrypoint script to configure tools if their values are provided
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "app.py"]
