FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project files
COPY host_agent/pyproject.toml ./
COPY host_agent/__init__.py ./
COPY host_agent/__main__.py ./
COPY host_agent/database.py ./
COPY host_agent/config.py ./
COPY host_agent/user_api.py ./
COPY host_agent/host/ ./host/
COPY host_agent/migrations/ ./migrations/

# Install dependencies using uv
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt

# Expose the port
EXPOSE 10001

# Start the server
# Note: Migrations are run separately via ECS task before deployment
CMD ["python", "__main__.py"]
