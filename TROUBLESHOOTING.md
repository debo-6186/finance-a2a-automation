# Host Agent Troubleshooting Guide

## 🚨 Common Host Agent Connection Issues

### **Error: HTTP 503 Service Unavailable / ReadTimeout**

This error occurs when the host agent cannot connect to the remote agents.

## 🔧 **Step-by-Step Solutions**

### **1. Verify Agent Startup Order**

**CRITICAL**: Start agents in this exact order:

```bash
# Step 1: Start Stock Analyser Agent
cd stockanalyser_agent
source .venv/bin/activate
uv run --active .
# Wait for: "INFO - uvicorn.server - Uvicorn running on http://localhost:10002"

# Step 2: Start Stock Report Analyser Agent  
cd stockreport_analyser_agent
source .venv/bin/activate
uv run --active .
# Wait for: "INFO - uvicorn.server - Uvicorn running on http://localhost:10003"

# Step 3: Start Host Agent (ONLY after above two are running)
cd host_agent
source .venv/bin/activate
uv run --active .
```

### **2. Check Agent Status**

Verify each agent is running and accessible:

```bash
# Check Stock Analyser Agent
curl http://localhost:10002/
# Should return: {"message": "Stock Analyser Agent is running"}

# Check Stock Report Analyser Agent
curl http://localhost:10003/
# Should return: {"message": "Stock Report Analyser Agent is running"}
```

### **3. Port Conflicts**

If ports are already in use:

```bash
# Check what's using the ports
lsof -i :10002
lsof -i :10003

# Kill processes if needed
kill -9 <PID>
```

### **4. Environment Variables**

Ensure required environment variables are set:

```bash
# Check if GOOGLE_API_KEY is set
echo $GOOGLE_API_KEY

# If not set, add to your shell profile
export GOOGLE_API_KEY="your-api-key-here"
```

### **5. Network Issues**

Check localhost connectivity:

```bash
# Test localhost
ping localhost

# Check if ports are listening
netstat -an | grep 10002
netstat -an | grep 10003
```

### **6. Timeout Configuration**

If agents are slow to respond, increase timeout in host agent:

```python
# In host_agent/host/agent.py, line 67
async with httpx.AsyncClient(timeout=60) as client:  # Increase from 30 to 60
```

## 🐛 **Debugging Steps**

### **1. Check Host Agent Logs**

```bash
cd host_agent
tail -f host_agent.log
```

Look for:
- Connection errors
- Timeout messages
- Agent card resolution failures

### **2. Check Individual Agent Logs**

```bash
# Stock Analyser Agent logs
cd stockanalyser_agent
# Check console output for errors

# Stock Report Analyser Agent logs  
cd stockreport_analyser_agent
# Check console output for errors
```

### **3. Test Agent Communication**

```bash
# Test direct communication to agents
curl -X POST http://localhost:10002/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'

curl -X POST http://localhost:10003/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

## 🔄 **Quick Fix Commands**

### **Restart All Agents (Recommended)**

```bash
# Kill all existing processes
pkill -f "uv run"
pkill -f "uvicorn"

# Start fresh in order
cd stockanalyser_agent && source .venv/bin/activate && uv run --active . &
sleep 10

cd stockreport_analyser_agent && source .venv/bin/activate && uv run --active . &
sleep 10

cd host_agent && source .venv/bin/activate && uv run --active .
```

### **Check Dependencies**

```bash
# Reinstall dependencies for each agent
cd stockanalyser_agent && uv sync
cd stockreport_analyser_agent && uv sync  
cd host_agent && uv sync
```

## 📋 **Verification Checklist**

- [ ] Stock Analyser Agent running on port 10002
- [ ] Stock Report Analyser Agent running on port 10003
- [ ] Both agents responding to curl requests
- [ ] GOOGLE_API_KEY environment variable set
- [ ] No port conflicts
- [ ] Host agent started after other agents
- [ ] All virtual environments activated

## 🆘 **If Still Not Working**

1. **Check system resources**: `top` or `htop`
2. **Check firewall settings**: Ensure localhost is not blocked
3. **Try different ports**: Modify port numbers in agent configurations
4. **Restart your terminal/IDE**: Sometimes environment issues persist
5. **Check Python version**: Ensure all agents use the same Python version

## 📞 **Getting Help**

If the issue persists:
1. Check the logs in each agent directory
2. Verify all environment variables are set correctly
3. Ensure no other services are using the required ports
4. Try running agents in separate terminal windows for better debugging 