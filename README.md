# Finance A2A Automation

A comprehensive financial analysis and automation system with multiple specialized agents for stock analysis, portfolio management, and report analysis.

## 🏗️ Project Structure

```
finance-a2a-automation/
├── host_agent/                 # Main host agent for coordination (includes PDF analysis sub-agent)
├── stockanalyser_agent/        # Stock analysis and allocation management
├── stockreport_analyser_agent/ # [DEPRECATED] Portfolio report analysis (now integrated into host_agent)
└── README.md                   # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12.9 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- macOS/Linux environment

### Environment Variables

Before starting the agents, you need to set up the required API keys:

1. **Google API Key** (required for all agents):
   ```bash
   export GOOGLE_API_KEY="your_google_api_key_here"
   ```
   Get your key from: https://makersuite.google.com/app/apikey

2. **Apify API Token** (optional, for enhanced stock data):
   ```bash
   export APIFY_API_TOKEN="your_apify_api_token_here"
   ```
   Get your token from: https://console.apify.com/account/integrations

3. **Create .env files** (optional, for easier setup):
   ```bash
   # Copy the example file
   cp stockanalyser_agent/env.example stockanalyser_agent/.env
   
   # Edit the .env file with your actual keys
   nano stockanalyser_agent/.env
   ```

### Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd finance-a2a-automation
   ```

2. **Set up Host Agent:**
   ```bash
   cd host_agent
   uv venv
   source .venv/bin/activate
   uv run --active .
   ```

3. **Set up Stock Analyser Agent:**
   ```bash
   cd ../stockanalyser_agent
   uv venv
   source .venv/bin/activate
   uv run --active .
   ```

**Note:** The Stock Report Analyser Agent has been integrated into the Host Agent as a sub-agent for better performance. You no longer need to run it separately.

## 📋 Detailed Setup Instructions

### Step 1: Host Agent Setup

```bash
# Navigate to host agent directory
cd host_agent

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
uv sync

# Run the host agent API server
python __main__.py

# Or alternatively:
uv run --active .
```

The Host Agent will start a REST API server on `http://localhost:10001` with the `/chats` endpoint.

### Step 2: Stock Analyser Agent Setup

```bash
# Navigate to stock analyser agent directory
cd stockanalyser_agent

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate

# Run the stock analyser agent
uv run --active .
```

**Note:** The Stock Report Analyser Agent has been integrated into the Host Agent as a sub-agent and no longer needs to be run separately.

## 🤖 Agent Descriptions

### Host Agent
- **Purpose**: Main coordination agent for the A2A automation system
- **Port**: 10001 (HTTP REST API)
- **Features**:
  - REST API with `/chats` endpoint for user conversations
  - Coordinates between different agents
  - Manages agent communication
  - Handles routing and task distribution
  - Streaming and non-streaming chat responses
  - Session management for conversations
  - **Integrated PDF Analysis Sub-Agent** for portfolio statement processing (local, no network overhead)

### Stock Analyser Agent
- **Purpose**: Comprehensive stock analysis and allocation management
- **Port**: 10002 (A2A protocol)
- **Features**:
  - Technical stock analysis with indicators (RSI, MACD, Bollinger Bands)
  - Stock suggestions by country and sector
  - Allocation list management
  - Portfolio-level insights
  - Real-time stock data analysis

### Stock Report Analyser Agent (DEPRECATED)
- **Status**: Now integrated into Host Agent as a sub-agent
- **Migration**: PDF analysis functionality moved to Host Agent for:
  - Reduced network latency (no HTTP calls)
  - Simpler deployment (2 services instead of 3)
  - Better performance for lightweight PDF parsing
  - Maintained isolation for heavy compute tasks (Stock Analyser remains separate)

## 🔧 Configuration

### Environment Variables

Each agent may require specific environment variables. Check the individual agent directories for `.env` files or configuration requirements.

### Dependencies

Each agent uses `uv` for dependency management with its own `pyproject.toml` and `uv.lock` files.

## 📊 Features

### Stock Analysis
- Real-time stock price analysis
- Technical indicators (RSI, MACD, Bollinger Bands)
- Stock news and sentiment analysis
- Buy/Sell/Hold recommendations
- Risk assessment and price targets

### Allocation Management
- Stock suggestions by country (USA, India)
- Sector-based recommendations (Technology, Financial, Automobile)
- Allocation list management
- Portfolio diversification insights
- Systematic stock analysis workflow

### Report Analysis
- PDF portfolio statement processing
- Financial metrics analysis
- Earnings report evaluation
- Investment insights and recommendations

## 🎯 Usage Examples

### Stock Analysis
```
User: "Analyze AAPL"
Agent: Provides comprehensive technical analysis including price, indicators, news, and recommendations
```

### Stock Suggestions
```
User: "Suggest USA technology stocks"
Agent: Shows top tech stocks and offers to add to allocation
```

### Allocation Management
```
User: "Add AAPL, MSFT to allocation"
Agent: Adds stocks and suggests analysis
```

### Portfolio Analysis
```
User: "Analyze my portfolio"
Agent: Processes portfolio statement and provides investment insights
```

## 🔄 Workflow

1. **Start required agents**:
   - Host Agent (port 10001) - includes integrated PDF analysis sub-agent
   - Stock Analyser Agent (port 10002) - for comprehensive stock analysis
2. **Use the Host Agent REST API** at `http://localhost:10001` for user conversations
3. **Send messages via `/chats` endpoint** to interact with the coordination system
4. **Portfolio analysis** is now handled locally within Host Agent (no separate service needed)
5. **Stock analysis** is delegated to Stock Analyser Agent via A2A protocol
6. **All communication** goes through the `/chats` API

## ☁️ AWS Deployment

The application can be deployed to AWS using ECS Fargate with automated database migrations.

### Prerequisites

- AWS CLI configured with appropriate credentials
- Docker installed and running
- AWS account with ECS, ECR, RDS, and Secrets Manager access

### Deployment Steps

#### 1. Run Complete Deployment

Deploy everything (build images, run migrations, update services):

```bash
./deploy.sh
```

This script will:
1. Create ECR repositories (if needed)
2. Build and push Docker images to ECR
3. Create/verify ECS cluster
4. Create CloudWatch log groups
5. **Run database migrations via ECS Fargate task**
6. Update ECS services with new images

#### 2. Run Migrations Only

To run database migrations without full deployment:

```bash
./run_migrations_task.sh
```

This is useful for:
- Running migrations after manual code changes
- Testing new migration scripts
- Emergency database updates

### Database Migrations

#### Migration Architecture

The system uses **ECS/Fargate tasks** for database migrations - the production-standard approach:

- Migrations run as **one-off Fargate tasks** before application deployment
- Automatic execution during deployment
- Clear separation from application runtime
- Full CloudWatch logging at `/ecs/finance-a2a-migration`
- Deployment **fails automatically** if migrations fail (safety mechanism)

#### Migration Files

All SQL migrations are stored in `host_agent/migrations/`:
```
host_agent/migrations/
├── 000_add_portfolio_statement_uploaded_field.sql
├── 001_add_stock_recommendations_table.sql
├── 002_add_input_format_column.sql
├── 003_add_portfolio_analysis_table.sql
├── 004_add_user_whitelist_table.sql
└── run_migrations.py
```

Migrations are executed in **alphabetical order**.

#### Adding New Migrations

1. Create a new SQL file with the next number:
   ```bash
   touch host_agent/migrations/005_your_migration_name.sql
   ```

2. Write your SQL migration:
   ```sql
   -- 005_your_migration_name.sql
   ALTER TABLE users ADD COLUMN phone_verified BOOLEAN DEFAULT FALSE;
   CREATE INDEX idx_users_phone_verified ON users(phone_verified);
   ```

3. Test locally:
   ```bash
   cd host_agent
   python migrations/run_migrations.py
   ```

4. Deploy to AWS:
   ```bash
   ./deploy.sh
   ```

The migration will run automatically before the application is deployed.

### Monitoring Deployments

#### View Migration Logs
```bash
# Real-time logs
aws logs tail /ecs/finance-a2a-migration --follow --region us-east-1

# Recent logs
aws logs tail /ecs/finance-a2a-migration --since 10m --region us-east-1
```

#### View Service Logs
```bash
# Host Agent logs
aws logs tail /ecs/finance-a2a-host-agent --follow --region us-east-1

# Stock Analyser Agent logs
aws logs tail /ecs/finance-a2a-stockanalyser-agent --follow --region us-east-1
```

#### Check Service Status
```bash
aws ecs describe-services \
  --cluster finance-a2a-cluster \
  --services host-agent stockanalyser-agent \
  --region us-east-1
```

### Deployment Files

- **`deploy.sh`** - Main deployment script
- **`run_migrations_task.sh`** - Standalone migration runner
- **`task-definition-migration.json`** - ECS task definition for migrations
- **`host_agent/Dockerfile`** - Host agent container definition
- **`stockanalyser_agent/Dockerfile`** - Stock analyser container definition

### Rollback Strategy

If a deployment fails:

1. **Check migration logs** to identify the issue:
   ```bash
   aws logs tail /ecs/finance-a2a-migration --region us-east-1
   ```

2. **Fix the migration file** locally

3. **Re-run deployment**:
   ```bash
   ./deploy.sh
   ```

4. **For urgent rollbacks**, use AWS Console to:
   - Roll back ECS service to previous task definition
   - Manually revert database changes if needed

### Infrastructure

The deployment uses:
- **ECS Fargate** for serverless container orchestration
- **ECR** for Docker image storage
- **RDS PostgreSQL** for database
- **CloudWatch Logs** for logging
- **VPC** with private subnets for security
- **IAM roles** for task permissions

## 📡 Host Agent API Documentation

The Host Agent now provides a REST API for user conversations, replacing the previous ADK web UI.

### Base URL
```
http://localhost:10001
```

### Available Endpoints

#### POST /chats
Send a chat message and receive a complete response.

**Request Body:**
```json
{
  "message": "Hello, I need help with stock analysis",
  "session_id": "optional-session-id"
}
```

**Response:**
```json
{
  "response": "I'll help you with stock analysis...",
  "session_id": "generated-or-provided-session-id",
  "is_complete": true
}
```

#### POST /chats/stream
Send a chat message and receive streaming responses for real-time updates.

**Request Body:** Same as `/chats`

**Response:** NDJSON stream of:
```json
{
  "content": "Final response content",
  "updates": "Intermediate update message",
  "is_task_complete": false,
  "session_id": "session-id"
}
```

#### GET /health
Check if the Host Agent API is healthy.

**Response:**
```json
{
  "status": "healthy",
  "message": "Host Agent is running",
  "connected_agents": ["Stock Analyser Agent"]
}
```

#### GET /agents/status
Get detailed status of all connected agents.

#### GET /chats/sessions/{session_id}
Get information about a specific chat session.

#### POST /agents/{agent_name}/test
Test connection to a specific agent.

### Usage Examples

#### Using curl:
```bash
# Health check
curl http://localhost:10001/health

# Send a chat message
curl -X POST http://localhost:10001/chats \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze AAPL stock"}'

# Stream a chat message
curl -X POST http://localhost:10001/chats/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What agents are available?"}' \
  --no-buffer
```

#### Using Python:
```python
import httpx
import asyncio

async def chat_with_host_agent():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:10001/chats",
            json={"message": "Hello, I need help with stock analysis"}
        )
        result = response.json()
        print(f"Response: {result['response']}")

asyncio.run(chat_with_host_agent())
```

#### Testing with the provided test script:
```bash
# Run the test script to validate all endpoints
cd host_agent
python test_chats_api.py
```

## 🛠️ Troubleshooting

### Common Issues

1. **Virtual Environment Issues:**
   ```bash
   # If activation fails, recreate the environment
   rm -rf .venv
   uv venv
   source .venv/bin/activate
   ```

2. **Port Conflicts:**
   - Check if ports are already in use
   - Modify port configurations in agent files if needed

3. **Dependency Issues:**
   ```bash
   # Reinstall dependencies
   uv sync
   ```

4. **API Key Issues:**
   ```bash
   # Check if environment variables are set
   echo $GOOGLE_API_KEY
   echo $APIFY_API_TOKEN
   
   # Set them if missing
   export GOOGLE_API_KEY="your_key_here"
   export APIFY_API_TOKEN="your_token_here"
   ```

### Logs and Debugging

- Check agent logs for error messages
- Verify environment variables are set correctly
- Ensure all required files (like `portfolio_statement.pdf`) are present

## 📁 File Structure Details

### Host Agent
```
host_agent/
├── __init__.py
├── host/
│   ├── __init__.py
│   ├── agent.py
│   ├── pdf_analyzer.py           # Integrated PDF analysis sub-agent
│   └── remote_agent_connection.py
├── pyproject.toml
└── uv.lock
```

### Stock Analyser Agent
```
stockanalyser_agent/
├── __init__.py
├── __main__.py
├── agent.py
├── agent_executor.py
├── stock_data.json          # Stock categories and tickers
├── allocation.json          # User allocation list
├── env.example             # Environment variables example
├── pyproject.toml
└── uv.lock
```

### Stock Report Analyser Agent (DEPRECATED - functionality moved to Host Agent)
```
stockreport_analyser_agent/
├── __init__.py
├── __main__.py
├── agent.py                 # Deprecated - see host_agent/host/pdf_analyzer.py
├── agent_executor.py        # Deprecated
├── portfolio_statement.pdf  # Still used by integrated PDF analyzer
├── pyproject.toml
└── uv.lock
```

**Note:** This agent is no longer run as a separate service. Its PDF analysis functionality has been integrated into the Host Agent for better performance.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

[Add your license information here]

## 📞 Support

For issues and questions:
- Check the troubleshooting section
- Review agent-specific documentation
- Create an issue in the repository

---

**Note**: Make sure to have all required API keys and environment variables configured before running the agents. 