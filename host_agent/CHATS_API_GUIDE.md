# Host Agent /chats API Guide

This guide explains how to use the new `/chats` API endpoint that replaces the adk web UI for user conversations.

## Overview

The Host Agent now provides a REST API for all user interactions. Instead of using the adk web UI, all conversations now go through HTTP endpoints.

## Key Changes

1. **No more adk web UI**: All user interactions are now via REST API
2. **New endpoint**: `POST /chats` for sending messages
3. **Streaming support**: `POST /chats/stream` for real-time responses
4. **Session management**: Automatic session handling for conversation continuity
5. **Health monitoring**: Status endpoints for system monitoring

## Starting the Host Agent

```bash
cd host_agent
python __main__.py
```

The server will start on `http://localhost:10001` and display available endpoints.

## API Endpoints

### Core Chat Endpoints

#### POST /chats
Send a message and get a complete response.

**Example:**
```bash
curl -X POST http://localhost:10001/chats \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I want to analyze my stock portfolio",
    "session_id": "my-session-123"
  }'
```

**Response:**
```json
{
  "response": "I'll help you analyze your portfolio statement. This will take about a minute...",
  "session_id": "my-session-123",
  "is_complete": true
}
```

#### POST /chats/stream
Send a message and get streaming responses for real-time updates.

**Example:**
```bash
curl -X POST http://localhost:10001/chats/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What agents are available?"}' \
  --no-buffer
```

**Response (NDJSON stream):**
```json
{"content": null, "updates": "The host agent is thinking...", "is_task_complete": false, "session_id": "abc123"}
{"content": "I have access to these agents: Stock Analyser Agent, Stock Report Analyser Agent...", "updates": null, "is_task_complete": true, "session_id": "abc123"}
```

### Monitoring Endpoints

#### GET /health
Check if the API is running and which agents are connected.

```bash
curl http://localhost:10001/health
```

#### GET /agents/status
Get detailed information about all connected agents.

```bash
curl http://localhost:10001/agents/status
```

#### POST /agents/{agent_name}/test
Test connection to a specific agent.

```bash
curl -X POST http://localhost:10001/agents/stock_analyser_agent/test
```

### Session Management

#### GET /chats/sessions/{session_id}
Get information about a specific chat session.

```bash
curl http://localhost:10001/chats/sessions/my-session-123
```

## Python Client Example

Here's how to use the API from Python:

```python
import asyncio
import httpx

class HostAgentClient:
    def __init__(self, base_url="http://localhost:10001"):
        self.base_url = base_url
        self.session_id = None
    
    async def chat(self, message: str):
        payload = {
            "message": message,
            "session_id": self.session_id
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(f"{self.base_url}/chats", json=payload)
            result = response.json()
            
            # Store session ID for future messages
            self.session_id = result["session_id"]
            return result["response"]

async def main():
    client = HostAgentClient()
    
    # Start a conversation
    response = await client.chat("Hello, I need help with stock analysis")
    print(f"Agent: {response}")
    
    # Continue the conversation in the same session
    response = await client.chat("I want to invest $10,000")
    print(f"Agent: {response}")

# Run the example
asyncio.run(main())
```

## Workflow Examples

### Stock Portfolio Analysis

1. **Upload portfolio statement**:
```json
{
  "message": "I want to analyze my portfolio statement for stock allocation recommendations",
  "session_id": "portfolio-analysis-001"
}
```

2. **Provide investment amount**:
```json
{
  "message": "$15,000",
  "session_id": "portfolio-analysis-001"
}
```

3. **Select additional stocks**:
```json
{
  "message": "I want to invest in USA technology stocks",
  "session_id": "portfolio-analysis-001"
}
```

### Stock Analysis

1. **Request specific stock analysis**:
```json
{
  "message": "Analyze AAPL stock",
  "session_id": "stock-analysis-001"
}
```

2. **Ask for recommendations**:
```json
{
  "message": "Should I buy, sell, or hold?",
  "session_id": "stock-analysis-001"
}
```

## Error Handling

The API returns standard HTTP status codes:

- **200**: Success
- **400**: Bad request (invalid JSON, missing fields)
- **404**: Session not found
- **500**: Internal server error
- **503**: Service unavailable (agents not connected)

Example error response:
```json
{
  "detail": "Host Agent not initialized"
}
```

## Migration from adk Web UI

If you were previously using the adk web UI:

1. **Replace web UI calls** with HTTP requests to `/chats`
2. **Handle sessions** by passing `session_id` to maintain conversation context
3. **Use streaming** for real-time updates instead of polling
4. **Monitor health** via `/health` endpoint instead of UI status

## Testing

Use the provided test script to validate all endpoints:

```bash
cd host_agent
python test_chats_api.py
```

This will test all major endpoints and show example usage patterns.

## Production Considerations

1. **CORS**: Configure appropriate origins in production
2. **Authentication**: Add authentication middleware if needed
3. **Rate limiting**: Consider adding rate limiting for API endpoints
4. **Logging**: Monitor logs in `host_agent_api.log`
5. **Health checks**: Use `/health` endpoint for load balancer health checks
6. **Timeouts**: Adjust timeout values based on your agent response times

## Troubleshooting

### Common Issues

1. **Connection refused**: Make sure the host agent is running on port 10001
2. **503 Service unavailable**: Ensure stock analyser and stock report analyser agents are running
3. **Timeout errors**: Increase timeout values for long-running agent operations
4. **Session not found**: Session IDs expire; create new sessions as needed

### Debug Commands

```bash
# Check if host agent is running
curl http://localhost:10001/health

# Check agent connections
curl http://localhost:10001/agents/status

# Test specific agent
curl -X POST http://localhost:10001/agents/Stock\ Analyser\ Agent/test
```