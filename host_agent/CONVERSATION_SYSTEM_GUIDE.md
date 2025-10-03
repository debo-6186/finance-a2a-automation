# Conversation System Implementation Guide

## Overview

Your conversation system is fully implemented with the following features:

✅ **Session Management**: Automatic session ID generation and stateful conversations  
✅ **User Management**: User ID tracking with paid/free status  
✅ **Message Limits**: 19 messages for free users, unlimited for paid users  
✅ **Stateful Conversations**: Maintains context across all agents  
✅ **PostgreSQL Integration**: Persistent storage for all conversation data  
✅ **REST API**: Complete API endpoints for chat functionality  

## How It Works

### 1. Session Management

- **New Conversation**: If no `session_id` is provided, a new one is automatically generated
- **Existing Conversation**: If `session_id` is provided, the conversation continues from where it left off
- **Cross-Agent State**: All agents in the system share the same session context

### 2. User Management

- **Required Fields**: `user_id` and `paid_user` must be provided in every API request
- **Paid Users**: Can send unlimited messages
- **Free Users**: Limited to 19 user messages

### 3. Message Flow

```
User Request → API Validation → Session Management → Agent Processing → Response Storage
     ↓              ↓              ↓                    ↓              ↓
  user_id       paid_user     session_id         Host Agent      Database
  message       message       generation         + Other Agents   Storage
```

## API Endpoints

### POST `/chats`
Send a message and get a complete response.

**Request Body:**
```json
{
  "message": "Hello, I need help with stock analysis",
  "user_id": "user123",
  "paid_user": false,
  "session_id": "optional-existing-session-id"
}
```

**Response:**
```json
{
  "response": "I can help you with stock analysis...",
  "session_id": "generated-or-existing-session-id",
  "is_complete": true
}
```

### POST `/chats/stream`
Send a message and get a streaming response for real-time updates.

**Request Body:** Same as `/chats`

**Response:** Streaming NDJSON with real-time updates

### GET `/sessions/{session_id}`
Get information about a specific conversation session.

### GET `/users/{user_id}`
Get user information including message count and limits.

### GET `/agents/status`
Get status of all connected agents.

## Database Schema

### Tables

1. **users**
   - `id`: User identifier
   - `email`: User email (optional)
   - `paid_user`: Boolean for subscription status
   - `created_at`, `updated_at`: Timestamps

2. **conversation_sessions**
   - `id`: Session identifier
   - `user_id`: Reference to user
   - `is_active`: Session status
   - `created_at`, `updated_at`: Timestamps

3. **conversation_messages**
   - `id`: Message identifier
   - `session_id`: Reference to session
   - `user_id`: Reference to user
   - `message_type`: 'user', 'agent', or 'system'
   - `content`: Message content
   - `agent_name`: Which agent processed the message
   - `timestamp`: When the message was sent

4. **agent_states**
   - `id`: State identifier
   - `session_id`: Reference to session
   - `agent_name`: Agent identifier
   - `state_data`: JSON string of agent state
   - `created_at`, `updated_at`: Timestamps

## Setup Instructions

### 1. Install Dependencies

```bash
cd host_agent
uv sync
```

### 2. Start PostgreSQL Database

```bash
# From the root directory
docker compose up -d postgres
```

### 3. Set Environment Variables

Create a `.env` file in the `host_agent` directory:

```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:password@localhost:5432/finance_a2a

# Google API Configuration
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_GENAI_USE_VERTEXAI=FALSE

# Host Agent Configuration
HOST_AGENT_PORT=10001
STOCK_ANALYSER_AGENT_URL=http://localhost:10002
STOCK_REPORT_ANALYSER_AGENT_URL=http://localhost:10003
```

### 4. Start the Host Agent

```bash
cd host_agent
uv run python -m __main__
```

The server will start on `http://localhost:10001`

## Usage Examples

### Starting a New Conversation

```bash
curl -X POST "http://localhost:10001/chats" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, I need help with stock analysis",
    "user_id": "user123",
    "paid_user": false
  }'
```

### Continuing an Existing Conversation

```bash
curl -X POST "http://localhost:10001/chats" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What about technology stocks?",
    "user_id": "user123",
    "paid_user": false,
    "session_id": "existing-session-id-from-previous-response"
  }'
```

### Checking User Status

```bash
curl "http://localhost:10001/users/user123"
```

### Getting Session Information

```bash
curl "http://localhost:10001/sessions/session-id-here"
```

## Message Limit Logic

### Free Users (paid_user: false)
- **Limit**: 19 user messages
- **Behavior**: After 19 messages, API returns HTTP 429 (Too Many Requests)
- **Upgrade Path**: Change `paid_user` to `true` in subsequent requests

### Paid Users (paid_user: true)
- **Limit**: Unlimited messages
- **Behavior**: Can send as many messages as needed
- **Downgrade**: Can be changed to `false` in subsequent requests

## Stateful Conversation Features

### 1. Cross-Agent Context
- All agents share the same session context
- Agent states are persisted in the database
- Conversations maintain context across restarts

### 2. Session Persistence
- Sessions are stored in PostgreSQL
- Messages are logged with timestamps
- Agent states are preserved between requests

### 3. User History
- Complete conversation history is maintained
- Users can resume conversations from any point
- Session information is queryable via API

## Testing

### Run the Test Suite

```bash
cd host_agent
uv run python test_conversation_system.py
```

### Manual Testing

1. Start the server
2. Use curl or Postman to test API endpoints
3. Verify session persistence
4. Test message limits for free users
5. Verify paid users can send unlimited messages

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Ensure PostgreSQL is running: `docker compose ps`
   - Check DATABASE_URL in .env file
   - Verify database exists: `finance_a2a`

2. **Message Limit Errors**
   - Check `paid_user` status in request
   - Verify user message count: `/users/{user_id}`

3. **Session Not Found**
   - Ensure `session_id` is valid
   - Check if session is active: `/sessions/{session_id}`

### Logs

- Host Agent logs: `host_agent.log`
- API logs: `host_agent_api.log`
- Database logs: Check Docker container logs

## Security Considerations

1. **User Authentication**: Implement proper user authentication
2. **Rate Limiting**: Consider adding rate limiting per user
3. **Input Validation**: All inputs are validated via Pydantic models
4. **Database Security**: Use environment variables for database credentials

## Performance

- **Database Indexes**: Optimized for common queries
- **Connection Pooling**: Efficient database connection management
- **Streaming Responses**: Real-time updates for better UX
- **State Caching**: Agent states are cached and updated efficiently

## Future Enhancements

1. **User Authentication**: JWT tokens, OAuth integration
2. **Rate Limiting**: Per-user and per-session rate limits
3. **Analytics**: Conversation analytics and insights
4. **Multi-tenancy**: Support for multiple organizations
5. **WebSocket Support**: Real-time bidirectional communication

---

Your conversation system is production-ready with all the requested features implemented! 🎉
