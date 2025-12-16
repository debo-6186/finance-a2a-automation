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
COPY stockanalyser_agent/pyproject.toml ./
COPY stockanalyser_agent/__init__.py ./
COPY stockanalyser_agent/__main__.py ./
COPY stockanalyser_agent/agent.py ./
COPY stockanalyser_agent/agent_executor.py ./
COPY stockanalyser_agent/fetch_technical_indicators.py ./
COPY stockanalyser_agent/integration_example.py ./
COPY stockanalyser_agent/section_extractor.py ./
COPY stockanalyser_agent/logger.py ./
COPY stockanalyser_agent/limited_context_session_service.py ./
COPY stockanalyser_agent/.env.example ./.env.example

# Copy database.py from host_agent (resolving symlink)
COPY host_agent/database.py ./database.py

# Install dependencies using uv
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt

# Expose the default A2A port
EXPOSE 10002

# Start the agent
CMD ["python", "__main__.py"]
