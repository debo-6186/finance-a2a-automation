#!/bin/bash

# Startup script for the Finance A2A Automation System
# This script starts the PostgreSQL database and the Host Agent

echo "🚀 Starting Finance A2A Automation System..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first:"
    echo "   https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        echo "⚠️  Port $port is already in use"
        return 1
    fi
    return 0
}

# Check if required ports are available
echo "🔍 Checking port availability..."
if ! check_port 5432; then
    echo "   Port 5432 (PostgreSQL) is already in use"
    echo "   Please stop any existing PostgreSQL service"
    exit 1
fi

if ! check_port 10001; then
    echo "   Port 10001 (Host Agent) is already in use"
    echo "   Please stop any existing service on port 10001"
    exit 1
fi

# Start PostgreSQL database
echo "🐘 Starting PostgreSQL database..."
cd "$(dirname "$0")/.."
docker compose up -d postgres

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
max_attempts=30
attempt=1
while [ $attempt -le $max_attempts ]; do
    if docker compose exec -T postgres pg_isready -U postgres -d finance_a2a >/dev/null 2>&1; then
        echo "✅ PostgreSQL is ready!"
        break
    fi
    echo "   Attempt $attempt/$max_attempts - PostgreSQL not ready yet..."
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -gt $max_attempts ]; then
    echo "❌ PostgreSQL failed to start within expected time"
    echo "   Check Docker logs: docker compose logs postgres"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
cd host_agent
uv sync

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cat > .env << EOF
# Database Configuration
DATABASE_URL=postgresql://postgres:password@localhost:5432/finance_a2a

# Google API Configuration
GOOGLE_API_KEY=AIzaSyAZgykw2rIFWiF8Db_jjlZiWeHPpUJ5H0Y
GOOGLE_GENAI_USE_VERTEXAI=FALSE

# Host Agent Configuration
HOST_AGENT_PORT=10001
STOCK_ANALYSER_AGENT_URL=http://localhost:10002
STOCK_REPORT_ANALYSER_AGENT_URL=http://localhost:10003
EOF
    echo "   Created .env file. Please update GOOGLE_API_KEY with your actual API key."
fi

# Start the Host Agent
echo "🤖 Starting Host Agent..."
echo "   The system will be available at: http://localhost:10001"
echo "   Press Ctrl+C to stop the system"
echo ""

# Start the Host Agent using the working command
echo "   Starting with uv run --active ."
uv run --active .
