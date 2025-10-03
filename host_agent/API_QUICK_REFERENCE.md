# API Quick Reference Card

## Base URL
```
http://localhost:10001
```

## Authentication
Currently no authentication required. All requests must include `user_id` and `paid_user` in the request body.

## Endpoints

### 🔵 Chat Endpoints

#### POST `/chats`
**Complete response endpoint**
```bash
curl -X POST "http://localhost:10001/chats" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Your message here",
    "user_id": "unique_user_id",
    "paid_user": false,
    "session_id": "optional_existing_session_id"
  }'
```

#### POST `/chats/stream`
**Streaming response endpoint**
```bash
curl -X POST "http://localhost:10001/chats/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Your message here",
    "user_id": "unique_user_id",
    "paid_user": false,
    "session_id": "optional_existing_session_id"
  }'
```

### 📊 Information Endpoints

#### GET `/health`
**System health check**
```bash
curl "http://localhost:10001/health"
```

#### GET `/agents/status`
**Agent connection status**
```bash
curl "http://localhost:10001/agents/status"
```

#### GET `/users/{user_id}`
**User information and limits**
```bash
curl "http://localhost:10001/users/your_user_id"
```

#### GET `/sessions/{session_id}`
**Session information**
```bash
curl "http://localhost:10001/sessions/your_session_id"
```

#### GET `/sessions/{session_id}/messages`
**Session messages with pagination**
```bash
curl "http://localhost:10001/sessions/your_session_id/messages?limit=50&offset=0"
```

#### GET `/users/{user_id}/sessions`
**User's session history**
```bash
curl "http://localhost:10001/users/your_user_id/sessions"
```

### 🧪 Testing Endpoints

#### POST `/agents/{agent_name}/test`
**Test agent connection**
```bash
curl -X POST "http://localhost:10001/agents/stock_analyser_agent/test"
```

## Request/Response Models

### ChatMessage (Request)
```json
{
  "message": "string (required)",
  "user_id": "string (required)",
  "paid_user": "boolean (required)",
  "session_id": "string (optional)"
}
```

### ChatResponse (Response)
```json
{
  "response": "string",
  "session_id": "string",
  "is_complete": "boolean"
}
```

### ChatStreamResponse (Streaming)
```json
{
  "content": "string (optional)",
  "updates": "string (optional)",
  "is_task_complete": "boolean",
  "session_id": "string"
}
```

## Message Limits

| User Type | Limit | Behavior |
|-----------|-------|----------|
| Free User (`paid_user: false`) | 19 messages | HTTP 429 after limit |
| Paid User (`paid_user: true`) | Unlimited | No restrictions |

## Session Management

- **No session_id**: New conversation started, new session_id generated
- **With session_id**: Continues existing conversation
- **Session persistence**: All conversations stored in PostgreSQL
- **Cross-agent state**: All agents share session context

## Error Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 400 | Bad Request | Invalid request format |
| 404 | Not Found | Session/User not found |
| 429 | Too Many Requests | Message limit reached |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | Host Agent not initialized |

## Example Workflow

### 1. Start New Conversation
```bash
curl -X POST "http://localhost:10001/chats" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, I need help with stock analysis",
    "user_id": "user123",
    "paid_user": false
  }'
```

### 2. Continue Conversation
```bash
curl -X POST "http://localhost:10001/chats" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What about technology stocks?",
    "user_id": "user123",
    "paid_user": false,
    "session_id": "session_id_from_previous_response"
  }'
```

### 3. Check User Status
```bash
curl "http://localhost:10001/users/user123"
```

### 4. View Session History
```bash
curl "http://localhost:10001/sessions/session_id_here/messages"
```

## Testing with curl

### Test Message Limits
```bash
# Send 20 messages to test limit
for i in {1..20}; do
  curl -X POST "http://localhost:10001/chats" \
    -H "Content-Type: application/json" \
    -d "{\"message\": \"Message $i\", \"user_id\": \"test_user\", \"paid_user\": false}"
  echo "Sent message $i"
done
```

### Test Paid User
```bash
curl -X POST "http://localhost:10001/chats" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I am a paid user",
    "user_id": "paid_user_123",
    "paid_user": true
  }'
```

## Environment Variables

Required in `.env` file:
```bash
DATABASE_URL=postgresql://postgres:password@localhost:5432/finance_a2a
GOOGLE_API_KEY=your_google_api_key_here
```

---

**Quick Start**: Run `./start_system.sh` to start the entire system! 🚀
