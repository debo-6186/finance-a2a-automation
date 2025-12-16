FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project files
COPY stockreport_analyser_agent/pyproject.toml ./
COPY stockreport_analyser_agent/__init__.py ./
COPY stockreport_analyser_agent/__main__.py ./
COPY stockreport_analyser_agent/agent.py ./
COPY stockreport_analyser_agent/agent_executor.py ./
COPY stockreport_analyser_agent/limited_context_session_service.py ./

# Install dependencies using uv
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt

# Expose the default A2A port
EXPOSE 10003

# Start the agent
CMD ["python", "__main__.py"]
