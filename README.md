# Finance A2A Automation

A comprehensive financial analysis and automation system with multiple specialized agents for stock analysis, portfolio management, and report analysis.

## 🏗️ Project Structure

```
finance-a2a-automation/
├── host_agent/                 # Main host agent for coordination
├── stockanalyser_agent/        # Stock analysis and allocation management
├── stockreport_analyser_agent/ # Portfolio report analysis
└── README.md                   # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12.9 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- macOS/Linux environment

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

4. **Set up Stock Report Analyser Agent:**
   ```bash
   cd ../stockreport_analyser_agent
   uv venv
   source .venv/bin/activate
   uv run --active .
   ```

## 📋 Detailed Setup Instructions

### Step 1: Host Agent Setup

```bash
# Navigate to host agent directory
cd host_agent

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate

# Run the host agent
uv run --active .
```

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

### Step 3: Stock Report Analyser Agent Setup

```bash
# Navigate to stock report analyser agent directory
cd stockreport_analyser_agent

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate

# Run the stock report analyser agent
uv run --active .
```

## 🤖 Agent Descriptions

### Host Agent
- **Purpose**: Main coordination agent for the A2A automation system
- **Port**: Default A2A port
- **Features**: 
  - Coordinates between different agents
  - Manages agent communication
  - Handles routing and task distribution

### Stock Analyser Agent
- **Purpose**: Comprehensive stock analysis and allocation management
- **Port**: Default A2A port
- **Features**:
  - Technical stock analysis with indicators (RSI, MACD, Bollinger Bands)
  - Stock suggestions by country and sector
  - Allocation list management
  - Portfolio-level insights
  - Real-time stock data analysis

### Stock Report Analyser Agent
- **Purpose**: Portfolio report and financial document analysis
- **Port**: Default A2A port
- **Features**:
  - PDF portfolio statement analysis
  - Financial metrics evaluation
  - Earnings report analysis
  - Investment recommendations
  - Risk assessment

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

1. **Start all agents** using the setup instructions above
2. **Connect to host agent** for coordination
3. **Use stock analyser** for individual stock analysis and allocation management
4. **Use stock report analyser** for portfolio and document analysis
5. **Coordinate through host agent** for complex multi-agent tasks

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
├── pyproject.toml
└── uv.lock
```

### Stock Report Analyser Agent
```
stockreport_analyser_agent/
├── __init__.py
├── __main__.py
├── agent.py
├── agent_executor.py
├── portfolio_statement.pdf  # Sample portfolio document
├── pyproject.toml
└── uv.lock
```

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