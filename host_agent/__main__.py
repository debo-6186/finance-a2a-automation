#!/usr/bin/env python3
"""
Main entry point for the Host Agent with /chats API endpoint.
This replaces the adk web UI with a REST API for user conversations.
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from fastapi.responses import StreamingResponse

from host.agent import HostAgent

load_dotenv()

# Set up logging
logger = logging.getLogger("host_agent_api")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler("host_agent_api.log", maxBytes=5*1024*1024, backupCount=3)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Console handler for immediate feedback
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


class ChatMessage(BaseModel):
    """Request model for chat messages."""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat messages."""
    response: str
    session_id: str
    is_complete: bool


class ChatStreamResponse(BaseModel):
    """Response model for streaming chat messages."""
    content: Optional[str] = None
    updates: Optional[str] = None
    is_task_complete: bool
    session_id: str


# Global variable to store the host agent instance
host_agent_instance: Optional[HostAgent] = None

# Configure remote agent URLs here
AGENT_URLS: list[str] = [
    "http://localhost:10002",  # Stock Analyser Agent
    "http://localhost:10003",  # Stock Report Analyser Agent
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to initialize and cleanup the host agent."""
    global host_agent_instance
    
    try:
        logger.info("Initializing Host Agent...")
        
        # Create and initialize the host agent
        host_agent_instance = await HostAgent.create(remote_agent_addresses=AGENT_URLS)
        logger.info("Host Agent initialized successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize Host Agent: {e}")
        raise
    finally:
        logger.info("Shutting down Host Agent...")
        # Cleanup if needed
        host_agent_instance = None


# Create FastAPI app with lifespan events
app = FastAPI(
    title="Host Agent API",
    description="REST API for the Host Agent to handle user conversations and coordinate with other agents",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware to allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    global host_agent_instance
    
    if host_agent_instance is None:
        raise HTTPException(status_code=503, detail="Host Agent not initialized")
    
    return {
        "status": "healthy",
        "message": "Host Agent is running",
        "connected_agents": list(host_agent_instance.remote_agent_connections.keys())
    }


@app.post("/chats", response_model=ChatResponse)
async def chat(chat_message: ChatMessage):
    """
    Send a message to the host agent and get a complete response.
    This endpoint waits for the full response before returning.
    """
    global host_agent_instance
    
    if host_agent_instance is None:
        raise HTTPException(status_code=503, detail="Host Agent not initialized")
    
    # Generate session ID if not provided
    session_id = chat_message.session_id or str(uuid.uuid4())
    
    try:
        logger.info(f"Processing chat message in session {session_id}: {chat_message.message[:100]}...")
        
        # Collect all streaming responses
        full_response = ""
        is_complete = False
        
        async for response_chunk in host_agent_instance.stream(
            query=chat_message.message,
            session_id=session_id
        ):
            if response_chunk.get("is_task_complete", False):
                full_response = response_chunk.get("content", "")
                is_complete = True
                break
            # For intermediate updates, we just continue collecting
        
        logger.info(f"Chat response completed for session {session_id}")
        
        return ChatResponse(
            response=full_response,
            session_id=session_id,
            is_complete=is_complete
        )
        
    except Exception as e:
        logger.error(f"Error processing chat message in session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@app.post("/chats/stream")
async def chat_stream(chat_message: ChatMessage):
    """
    Send a message to the host agent and stream the response.
    This endpoint returns a streaming response for real-time updates.
    """
    global host_agent_instance
    
    if host_agent_instance is None:
        raise HTTPException(status_code=503, detail="Host Agent not initialized")
    
    # Generate session ID if not provided
    session_id = chat_message.session_id or str(uuid.uuid4())
    
    try:
        logger.info(f"Processing streaming chat message in session {session_id}: {chat_message.message[:100]}...")
        
        async def generate_response():
            async for response_chunk in host_agent_instance.stream(
                query=chat_message.message,
                session_id=session_id
            ):
                yield ChatStreamResponse(
                    content=response_chunk.get("content"),
                    updates=response_chunk.get("updates"),
                    is_task_complete=response_chunk.get("is_task_complete", False),
                    session_id=session_id
                ).model_dump_json() + "\n"
        
        return StreamingResponse(
            generate_response(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache"}
        )
        
    except Exception as e:
        logger.error(f"Error processing streaming chat message in session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@app.get("/agents/status")
async def get_agents_status():
    """Get the status of all connected agents."""
    global host_agent_instance
    
    if host_agent_instance is None:
        raise HTTPException(status_code=503, detail="Host Agent not initialized")
    
    try:
        # Use the existing get_agent_status method from HostAgent
        status_text = host_agent_instance.get_agent_status()
        
        # Also return structured data
        agents_info = {}
        for agent_name, connection in host_agent_instance.remote_agent_connections.items():
            agents_info[agent_name] = {
                "name": agent_name,
                "url": connection.agent_url,
                "description": connection.agent_card.description,
                "skills": [skill.name for skill in connection.agent_card.skills],
                "version": connection.agent_card.version,
                "status": "connected"
            }
        
        return {
            "status_text": status_text,
            "agents": agents_info,
            "total_connected": len(host_agent_instance.remote_agent_connections)
        }
        
    except Exception as e:
        logger.error(f"Error getting agents status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting agents status: {str(e)}")


@app.post("/agents/refresh")
async def refresh_agents():
    """Attempt to (re)connect to remote agents without restarting the server."""
    global host_agent_instance
    if host_agent_instance is None:
        raise HTTPException(status_code=503, detail="Host Agent not initialized")

    try:
        # Recreate and reinitialize HostAgent to re-resolve cards and connections
        logger.info("Refreshing remote agent connections...")
        new_instance = await HostAgent.create(remote_agent_addresses=AGENT_URLS)

        # Swap instances atomically
        host_agent_instance.remote_agent_connections = new_instance.remote_agent_connections
        host_agent_instance.cards = new_instance.cards
        host_agent_instance.agents = new_instance.agents

        logger.info(f"Refresh complete. Connected agents: {list(host_agent_instance.remote_agent_connections.keys())}")
        return {
            "message": "Agents refreshed",
            "connected_agents": list(host_agent_instance.remote_agent_connections.keys()),
            "total_connected": len(host_agent_instance.remote_agent_connections)
        }
    except Exception as e:
        logger.error(f"Error refreshing agents: {e}")
        raise HTTPException(status_code=500, detail=f"Error refreshing agents: {str(e)}")


@app.post("/agents/{agent_name}/test")
async def test_agent_connection(agent_name: str):
    """Test connection to a specific agent."""
    global host_agent_instance
    
    if host_agent_instance is None:
        raise HTTPException(status_code=503, detail="Host Agent not initialized")
    
    try:
        # Use the existing test_agent_connection method from HostAgent
        test_result = host_agent_instance.test_agent_connection(agent_name)
        
        return {
            "agent_name": agent_name,
            "test_result": test_result,
            "timestamp": str(asyncio.get_event_loop().time())
        }
        
    except Exception as e:
        logger.error(f"Error testing agent connection for {agent_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Error testing agent connection: {str(e)}")


def main():
    """Start the Host Agent API server."""
    try:
        # Check for required environment variables
        if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            logger.error("GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE.")
            exit(1)
        
        host = "localhost"
        port = 10001  # Different port from other agents
        
        logger.info(f"Starting Host Agent API server on {host}:{port}")
        logger.info("Available endpoints:")
        logger.info("  POST /chats - Send a chat message and get complete response")
        logger.info("  POST /chats/stream - Send a chat message and get streaming response")
        logger.info("  GET /agents/status - Get status of connected agents")
        logger.info("  POST /agents/{agent_name}/test - Test agent connection")
        logger.info("  GET /health - Health check")
        
        # Run using the in-memory app object to avoid module import path issues
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=False,  # Set to True for development
            log_level="info"
        )
        
    except Exception as e:
        logger.error(f"Error starting Host Agent API server: {e}")
        exit(1)


if __name__ == "__main__":
    main()