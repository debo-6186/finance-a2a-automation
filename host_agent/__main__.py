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
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from fastapi.responses import StreamingResponse
import requests
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

from host.agent import HostAgent
from database import (
    get_db, get_or_create_user, create_session, get_session, 
    add_message, can_user_send_message, get_user_message_count,
    User, ConversationSession, ConversationMessage
)
from user_api import (
    get_user_profile, update_user_profile, get_user_statistics,
    delete_user_account, get_user_sessions_summary, upgrade_user_to_paid,
    downgrade_user_to_free, UserProfile, UserUpdate, UserStats
)

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
    user_id: str
    paid_user: bool = False


class ChatResponse(BaseModel):
    """Response model for chat messages."""
    response: str
    session_id: str
    is_complete: bool
    is_file_uploaded: bool = False
    end_session: bool = False


class ChatStreamResponse(BaseModel):
    """Response model for streaming chat messages."""
    content: Optional[str] = None
    updates: Optional[str] = None
    is_task_complete: bool
    session_id: str
    is_file_uploaded: bool = False
    end_session: bool = False


class LoginRequest(BaseModel):
    """Request model for login with Firebase ID token."""
    id_token: str
    
    
class LoginResponse(BaseModel):
    """Response model for login that matches frontend User interface."""
    id: str  # Firebase UID
    email: str
    name: str
    contactNumber: str = ""
    countryCode: str = "+1" 
    uploadFile: bool = False
    createdAt: str




# Global variable to store the host agent instance
host_agent_instance: Optional[HostAgent] = None

# Agent URLs configuration
AGENT_URLS = [
    "http://localhost:10002",  # Stock Analyser Agent
    "http://localhost:10003",  # Stock Report Analyser Agent
]


# Firebase Admin SDK initialization
def init_firebase():
    """Initialize Firebase Admin SDK."""
    try:
        # Check if Firebase is already initialized
        if firebase_admin._apps:
            logger.info("Firebase Admin SDK already initialized")
            return
        
        # Get Firebase project ID from environment
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if not project_id or project_id == "your-firebase-project-id":
            logger.warning("FIREBASE_PROJECT_ID not set in environment variables")
            logger.warning("Please set FIREBASE_PROJECT_ID in your .env file")
            # For development, we'll skip Firebase initialization
            return
        
        # Try to use service account file if available
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
        if service_account_path and os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred, {'projectId': project_id})
            logger.info(f"Firebase Admin SDK initialized with service account for project: {project_id}")
        else:
            # Use default credentials with project ID
            firebase_admin.initialize_app(options={'projectId': project_id})
            logger.info(f"Firebase Admin SDK initialized with default credentials for project: {project_id}")
            
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        logger.warning("Firebase authentication will not work properly")


def validate_firebase_token(id_token: str) -> dict:
    """
    Validate Firebase ID token using Firebase Admin SDK and return user info.
    Falls back to development mode if Firebase is not properly configured.
    """
    logger.info(f"[TOKEN] validate_firebase_token called with token length: {len(id_token)}")
    
    try:
        # Check if Firebase is initialized
        logger.info(f"[TOKEN] Firebase apps initialized: {len(firebase_admin._apps) > 0}")
        
        if not firebase_admin._apps:
            logger.warning("[TOKEN] Firebase not initialized, using development mode")
            return _dev_validate_token(id_token)
        
        logger.info("[TOKEN] Attempting Firebase token verification...")
        # Verify the Firebase ID token
        decoded_token = firebase_auth.verify_id_token(id_token)
        logger.info(f"[TOKEN] Firebase token verification successful for UID: {decoded_token.get('uid', 'unknown')}")
        
        result = {
            'uid': decoded_token['uid'],
            'email': decoded_token.get('email', 'user@example.com'),
            'email_verified': decoded_token.get('email_verified', False),
            'name': decoded_token.get('name', 'User'),
            'picture': decoded_token.get('picture')
        }
        logger.info(f"[TOKEN] Returning user info: uid={result['uid']}, email={result['email']}")
        return result
            
    except Exception as e:
        logger.error(f"[TOKEN] Error validating Firebase token: {e}")
        logger.warning("[TOKEN] Falling back to development mode")
        return _dev_validate_token(id_token)


def _dev_validate_token(id_token: str) -> dict:
    """
    Development mode token validation - DO NOT USE IN PRODUCTION.
    This is for testing when Firebase is not configured.
    """
    logger.info(f"[DEV_TOKEN] _dev_validate_token called with token length: {len(id_token)}")
    
    try:
        # Basic validation - check if token looks valid
        if not id_token or len(id_token) < 10:
            raise ValueError("Invalid token format")
        
        # Try to decode JWT payload for development
        import json
        import base64
        
        parts = id_token.split('.')
        if len(parts) != 3:
            # Create a mock user for development
            return {
                'uid': f'dev_user_{hash(id_token) % 10000}',
                'email': 'dev-user@example.com',
                'email_verified': True,
                'name': 'Development User',
                'picture': None
            }
        
        # Decode payload (add padding if needed)
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded_payload = base64.b64decode(payload)
        user_info = json.loads(decoded_payload)
        
        return {
            'uid': user_info.get('user_id', user_info.get('sub', f'dev_user_{hash(id_token) % 10000}')),
            'email': user_info.get('email', 'dev-user@example.com'),
            'email_verified': user_info.get('email_verified', True),
            'name': user_info.get('name', 'Development User'),
            'picture': user_info.get('picture')
        }
        
    except Exception as e:
        logger.error(f"Error in development token validation: {e}")
        raise HTTPException(status_code=401, detail="Invalid token format")


def get_current_user(authorization: str = Header(None)) -> dict:
    """
    Dependency to extract and validate Firebase token from Authorization header.
    """
    logger.info(f"[AUTH] get_current_user called")
    logger.info(f"[AUTH] Authorization header present: {authorization is not None}")
    
    if authorization:
        logger.info(f"[AUTH] Authorization header: {authorization[:50]}..." if len(authorization) > 50 else f"[AUTH] Authorization header: {authorization}")
    
    if not authorization:
        logger.error("[AUTH] Missing authorization header")
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    if not authorization.startswith("Bearer "):
        logger.error(f"[AUTH] Invalid authorization header format. Header: {authorization[:20]}...")
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    token = authorization.split("Bearer ")[1]
    logger.info(f"[AUTH] Extracted token length: {len(token)}")
    logger.info(f"[AUTH] Token preview: {token[:20]}...")
    
    try:
        result = validate_firebase_token(token)
        logger.info(f"[AUTH] Token validation successful for user: {result.get('uid', 'unknown')}")
        return result
    except Exception as e:
        logger.error(f"[AUTH] Token validation failed: {e}")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to initialize and cleanup the host agent."""
    global host_agent_instance
    
    try:
        logger.info("Initializing Host Agent...")
        
        # Initialize Firebase Admin SDK
        init_firebase()
        
        # Initialize database
        from database import init_db
        try:
            init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            logger.warning("Continuing without database initialization")
        
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


@app.post("/api/login", response_model=LoginResponse)
def login(login_request: LoginRequest):
    """
    Handle Firebase authentication and user creation/login.
    """
    try:
        logger.info(f"Processing login request with token: {login_request.id_token[:20]}...")
        
        # Validate Firebase token
        firebase_user = validate_firebase_token(login_request.id_token)
        user_id = firebase_user['uid']
        email = firebase_user.get('email', '')
        name = firebase_user.get('name', '')
        
        logger.info(f"Firebase token validated for user: {user_id}")
        
        # Get database session
        db = next(get_db())
        
        # Get or create user in database
        user = get_or_create_user(db, user_id, email=email, name=name, paid_user=False)
        
        logger.info(f"User {'created' if user else 'found'} in database: {user_id}")
        
        return LoginResponse(
            id=user_id,
            email=email,
            name=name,
            contactNumber="",  # Will be updated by user later
            countryCode="+1",  # Default country code
            uploadFile=user.paid_user if user else False,  # Map paid_user to uploadFile
            createdAt=user.created_at.isoformat() if user else ""
        )
        
    except HTTPException as e:
        logger.error(f"HTTP error during login: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


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
async def chat(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Send a message to the host agent and get a complete response.
    This endpoint waits for the full response before returning.
    
    Supports two input formats:
    1. JSON payload with Content-Type: application/json
    2. Form data with Content-Type: multipart/form-data (for file uploads)
    """
    logger.info(f"[CHAT] /chats endpoint called successfully")
    logger.info(f"[CHAT] Authenticated user: {current_user.get('uid', 'unknown')} ({current_user.get('email', 'no-email')})")
    
    # Handle both JSON and form data inputs based on content type
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        # JSON input
        try:
            json_data = await request.json()
            chat_message = ChatMessage(**json_data)
            final_message = chat_message.message
            final_user_id = chat_message.user_id
            final_session_id = chat_message.session_id
            final_paid_user = chat_message.paid_user
            uploaded_file = None
            logger.info(f"[CHAT] Using JSON input format")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    elif "multipart/form-data" in content_type:
        # Form data input
        try:
            form = await request.form()
            message = form.get("message")
            user_id = form.get("user_id")
            paid_user = form.get("paid_user")
            session_id = form.get("session_id")
            uploaded_file = form.get("file")
            
            if not message or not user_id:
                raise HTTPException(status_code=400, detail="message and user_id are required")
            
            final_message = message
            final_user_id = user_id
            final_session_id = session_id
            final_paid_user = paid_user == "true" if paid_user is not None else False
            logger.info(f"[CHAT] Using form data input format")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid form data: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Content-Type must be application/json or multipart/form-data")
    
    try:
        logger.info(f"[CHAT] Message: {final_message[:100]}...")
        logger.info(f"[CHAT] User ID: {final_user_id}")
        logger.info(f"[CHAT] Session ID: {final_session_id}")
        logger.info(f"[CHAT] Paid user: {final_paid_user}")
        logger.info(f"[CHAT] File uploaded: {uploaded_file is not None}")
    except Exception as e:
        logger.error(f"[CHAT] Error accessing message fields: {e}")
        raise
    
    global host_agent_instance
    
    if host_agent_instance is None:
        raise HTTPException(status_code=503, detail="Host Agent not initialized")
    
    # Generate session ID if not provided
    session_id = final_session_id or str(uuid.uuid4())
    logger.info(f"[CHAT] Final session ID: {session_id}")
    
    try:
        logger.info(f"Processing chat message in session {session_id} for user {final_user_id}: {final_message[:100]}...")
        
        # Get database session
        db = next(get_db())
        
        # Get or create user
        get_or_create_user(db, final_user_id, paid_user=final_paid_user)
        
        # Check if user can send more messages
        if not can_user_send_message(db, final_user_id):
            message_count = get_user_message_count(db, final_user_id)
            raise HTTPException(
                status_code=429, 
                detail=f"Message limit reached. Free users are limited to 30 messages. You have sent {message_count} messages. Upgrade to paid to continue."
            )
        
        # Get or create session
        session = get_session(db, session_id)
        if not session:
            session = create_session(db, session_id, final_user_id)
        
        # Handle file upload if present
        file_uploaded = False
        if uploaded_file and hasattr(uploaded_file, 'filename') and uploaded_file.filename:
            try:
                # Validate file type (should be PDF)
                if not uploaded_file.filename.lower().endswith('.pdf'):
                    raise HTTPException(status_code=400, detail="Only PDF files are allowed")
                
                # Create a temporary file path
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    # Read and write file content
                    if hasattr(uploaded_file, 'read'):
                        content = await uploaded_file.read()
                    else:
                        content = uploaded_file.file.read()
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                
                try:
                    # Update host agent's current session ID for consistency
                    host_agent_instance.current_session_id = {"id": session_id, "is_file_uploaded": False}
                    
                    # Use the existing store_portfolio_file method with explicit session_id
                    result = host_agent_instance.store_portfolio_file(final_user_id, temp_file_path, session_id)
                    
                    # Check if upload was successful
                    if "successfully" in result:
                        # Set file uploaded flag to True
                        host_agent_instance.current_session_id["is_file_uploaded"] = True
                        file_uploaded = True
                        
                        logger.info(f"Portfolio file uploaded successfully for user {final_user_id}, session {session_id}")
                    else:
                        logger.error(f"Portfolio file upload failed: {result}")
                        
                finally:
                    # Clean up temporary file
                    import os
                    try:
                        os.unlink(temp_file_path)
                    except:
                        pass  # Ignore cleanup errors
                        
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error processing uploaded file: {e}")
                raise HTTPException(status_code=500, detail=f"Error processing uploaded file: {str(e)}")
        
        # Add user message to database
        add_message(db, session_id, final_user_id, "user", final_message)
        
        # Test log to verify code insertion
        logger.info(f"Test log: Starting to process message for session {session_id}, user {final_user_id}")
        # Collect all streaming responses
        full_response = ""
        is_complete = False
        end_session = False
        response_count = 0
        max_responses = 100  # Prevent infinite loops
        
        async for response_chunk in host_agent_instance.stream(
            query=final_message,
            session_id=session_id
        ):
            response_count += 1
            logger.info(f"Received response chunk {response_count}: {response_chunk}")
            
            if response_chunk.get("is_task_complete", False):
                content = response_chunk.get("content", "")
                # Check if content is a JSON string with message and end_session
                try:
                    import json
                    if isinstance(content, str) and content.strip().startswith('{') and content.strip().endswith('}'):
                        parsed_content = json.loads(content.strip())
                        if isinstance(parsed_content, dict) and "message" in parsed_content:
                            full_response = parsed_content["message"]
                            end_session = parsed_content.get("end_session", False)
                            logger.info(f"Parsed JSON response - End session flag: {end_session}")
                        else:
                            full_response = content
                    else:
                        full_response = content
                except (json.JSONDecodeError, ValueError):
                    # If parsing fails, treat as regular string
                    full_response = content
                
                is_complete = True
                logger.info(f"Task completed with response length: {len(full_response)}")
                break
            elif response_count >= max_responses:
                logger.warning(f"Breaking from stream after {max_responses} responses to prevent infinite loop")
                full_response = "Task processing exceeded maximum iterations. Please try again."
                is_complete = True
                break
            # For intermediate updates, we just continue collecting
        
        # Add agent response to database
        if full_response:
            add_message(db, session_id, final_user_id, "agent", full_response, "host_agent")
        
        logger.info(f"Chat response completed for session {session_id}")
        
        # Check if file has been uploaded for this session (either in current request or previously)
        session_has_file_uploaded = file_uploaded  # Current request upload
        if not session_has_file_uploaded:
            # Check database for previous uploads in this session
            session_obj = get_session(db, session_id)
            if session_obj and session_obj.portfolio_statement_uploaded:
                session_has_file_uploaded = True
        
        return ChatResponse(
            response=full_response,
            session_id=session_id,
            is_complete=is_complete,
            is_file_uploaded=session_has_file_uploaded,
            end_session=end_session
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error processing chat message in session {session_id}: {e}")

        # Check if it's a Google AI API error
        if any(code in error_message for code in ["500 INTERNAL", "503 UNAVAILABLE"]):
            logger.error(f"Google AI API error: {error_message}")
            raise HTTPException(
                status_code=503,
                detail="The AI service is temporarily unavailable. Please try again in a moment."
            )
        else:
            raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@app.post("/chats/stream")
async def chat_stream(request: Request):
    """
    Send a message to the host agent and stream the response.
    This endpoint returns a streaming response for real-time updates.
    
    Supports two input formats:
    1. JSON payload with Content-Type: application/json
    2. Form data with Content-Type: multipart/form-data (for file uploads)
    """
    global host_agent_instance
    
    if host_agent_instance is None:
        raise HTTPException(status_code=503, detail="Host Agent not initialized")
    
    # Handle both JSON and form data inputs based on content type
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        # JSON input
        try:
            json_data = await request.json()
            chat_message = ChatMessage(**json_data)
            final_message = chat_message.message
            final_user_id = chat_message.user_id
            final_session_id = chat_message.session_id
            final_paid_user = chat_message.paid_user
            uploaded_file = None
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    elif "multipart/form-data" in content_type:
        # Form data input
        try:
            form = await request.form()
            message = form.get("message")
            user_id = form.get("user_id")
            paid_user = form.get("paid_user")
            session_id = form.get("session_id")
            uploaded_file = form.get("file")
            
            if not message or not user_id:
                raise HTTPException(status_code=400, detail="message and user_id are required")
            
            final_message = message
            final_user_id = user_id
            final_session_id = session_id
            final_paid_user = paid_user == "true" if paid_user is not None else False
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid form data: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Content-Type must be application/json or multipart/form-data")
    
    # Generate session ID if not provided
    session_id = final_session_id or str(uuid.uuid4())
    
    try:
        logger.info(f"Processing streaming chat message in session {session_id} for user {final_user_id}: {final_message[:100]}...")
        
        # Get database session
        db = next(get_db())
        
        # Get or create user
        get_or_create_user(db, final_user_id, paid_user=final_paid_user)
        
        # Check if user can send more messages
        if not can_user_send_message(db, final_user_id):
            message_count = get_user_message_count(db, final_user_id)
            raise HTTPException(
                status_code=429, 
                detail=f"Message limit reached. Free users are limited to 19 messages. You have sent {message_count} messages. Upgrade to paid to continue."
            )
        
        # Get or create session
        session = get_session(db, session_id)
        if not session:
            session = create_session(db, session_id, final_user_id)
        
        # Handle file upload if present
        file_uploaded = False
        if uploaded_file and hasattr(uploaded_file, 'filename') and uploaded_file.filename:
            try:
                # Validate file type (should be PDF)
                if not uploaded_file.filename.lower().endswith('.pdf'):
                    raise HTTPException(status_code=400, detail="Only PDF files are allowed")
                
                # Create a temporary file path
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    # Read and write file content
                    if hasattr(uploaded_file, 'read'):
                        content = await uploaded_file.read()
                    else:
                        content = uploaded_file.file.read()
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                
                try:
                    # Update host agent's current session ID for consistency
                    host_agent_instance.current_session_id = {"id": session_id, "is_file_uploaded": False}
                    
                    # Use the existing store_portfolio_file method with explicit session_id
                    result = host_agent_instance.store_portfolio_file(final_user_id, temp_file_path, session_id)
                    
                    # Check if upload was successful
                    if "successfully" in result:
                        # Set file uploaded flag to True
                        host_agent_instance.current_session_id["is_file_uploaded"] = True
                        file_uploaded = True
                        
                        logger.info(f"Portfolio file uploaded successfully for user {final_user_id}, session {session_id}")
                    else:
                        logger.error(f"Portfolio file upload failed: {result}")
                        
                finally:
                    # Clean up temporary file
                    import os
                    try:
                        os.unlink(temp_file_path)
                    except:
                        pass  # Ignore cleanup errors
                        
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error processing uploaded file: {e}")
                raise HTTPException(status_code=500, detail=f"Error processing uploaded file: {str(e)}")
        
        # Add user message to database
        add_message(db, session_id, final_user_id, "user", final_message)
        
        async def generate_response():
            full_response = ""
            end_session = False
            async for response_chunk in host_agent_instance.stream(
                query=final_message,
                session_id=session_id
            ):
                content = response_chunk.get("content", "")
                if response_chunk.get("is_task_complete", False):
                    # Check if content is a JSON string with message and end_session
                    try:
                        import json
                        if isinstance(content, str) and content.strip().startswith('{') and content.strip().endswith('}'):
                            parsed_content = json.loads(content.strip())
                            if isinstance(parsed_content, dict) and "message" in parsed_content:
                                full_response = parsed_content["message"]
                                end_session = parsed_content.get("end_session", False)
                                final_content = parsed_content["message"]
                            else:
                                full_response = content
                                final_content = content
                        else:
                            full_response = content
                            final_content = content
                    except (json.JSONDecodeError, ValueError):
                        # If parsing fails, treat as regular string
                        full_response = content
                        final_content = content
                    
                    # Add agent response to database
                    if full_response:
                        add_message(db, session_id, final_user_id, "agent", full_response, "host_agent")
                else:
                    final_content = content
                
                # Check if file has been uploaded for this session (either in current request or previously)
                session_has_file_uploaded = file_uploaded  # Current request upload
                if not session_has_file_uploaded:
                    # Check database for previous uploads in this session
                    session_obj = get_session(db, session_id)
                    if session_obj and session_obj.portfolio_statement_uploaded:
                        session_has_file_uploaded = True
                
                yield ChatStreamResponse(
                    content=final_content,
                    updates=response_chunk.get("updates"),
                    is_task_complete=response_chunk.get("is_task_complete", False),
                    session_id=session_id,
                    is_file_uploaded=session_has_file_uploaded,
                    end_session=end_session
                ).model_dump_json() + "\n"
        
        return StreamingResponse(
            generate_response(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error processing streaming chat message in session {session_id}: {e}")

        # Check if it's a Google AI API error
        if any(code in error_message for code in ["500 INTERNAL", "503 UNAVAILABLE"]):
            logger.error(f"Google AI API error in streaming: {error_message}")
            raise HTTPException(
                status_code=503,
                detail="The AI service is temporarily unavailable. Please try again in a moment."
            )
        else:
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


@app.get("/sessions/{session_id}")
async def get_session_info(session_id: str):
    """Get information about a specific session."""
    try:
        db = next(get_db())
        session = get_session(db, session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get session messages
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session_id
        ).order_by(ConversationMessage.timestamp).all()
        
        # Get user info
        user = db.query(User).filter(User.id == session.user_id).first()
        
        return {
            "session_id": session_id,
            "user_id": session.user_id,
            "user_email": user.email if user else None,
            "paid_user": user.paid_user if user else False,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "is_active": session.is_active,
            "message_count": len(messages),
            "user_message_count": len([m for m in messages if m.message_type == "user"]),
            "agent_message_count": len([m for m in messages if m.message_type == "agent"])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session info for {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting session info: {str(e)}")


@app.get("/users/{user_id}")
async def get_user_info(user_id: str):
    """Get information about a specific user."""
    try:
        db = next(get_db())
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get user's sessions
        sessions = db.query(ConversationSession).filter(
            ConversationSession.user_id == user_id
        ).all()
        
        # Get total message count
        message_count = get_user_message_count(db, user_id)
        
        return {
            "user_id": user_id,
            "email": user.email,
            "paid_user": user.paid_user,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat(),
            "total_sessions": len(sessions),
            "total_messages": message_count,
            "can_send_messages": can_user_send_message(db, user_id),
            "message_limit": "unlimited" if user.paid_user else "19 messages"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user info for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting user info: {str(e)}")


@app.get("/users/{user_id}/sessions")
async def get_user_sessions(user_id: str):
    """Get all sessions for a specific user."""
    try:
        db = next(get_db())
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        sessions = db.query(ConversationSession).filter(
            ConversationSession.user_id == user_id
        ).order_by(ConversationSession.updated_at.desc()).all()
        
        session_list = []
        for session in sessions:
            # Get message count for each session
            message_count = db.query(ConversationMessage).filter(
                ConversationMessage.session_id == session.id
            ).count()
            
            session_list.append({
                "session_id": session.id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "is_active": session.is_active,
                "message_count": message_count
            })
        
        return {
            "user_id": user_id,
            "total_sessions": len(sessions),
            "sessions": session_list
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user sessions for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting user sessions: {str(e)}")


# User-level API endpoints
@app.get("/api/users/{user_id}/profile", response_model=UserProfile)
def get_user_profile_endpoint(user_id: str):
    """Get complete user profile information."""
    return get_user_profile(user_id)


@app.put("/api/users/{user_id}/profile", response_model=UserProfile)
def update_user_profile_endpoint(user_id: str, update_data: UserUpdate, current_user: dict = Depends(get_current_user)):
    """Update user profile information."""
    # Ensure user can only update their own profile
    if current_user['uid'] != user_id:
        raise HTTPException(status_code=403, detail="You can only update your own profile")
    
    return update_user_profile(user_id, update_data)


@app.get("/api/users/{user_id}/statistics", response_model=UserStats)
def get_user_statistics_endpoint(user_id: str):
    """Get detailed user statistics."""
    return get_user_statistics(user_id)


@app.delete("/api/users/{user_id}")
def delete_user_account_endpoint(user_id: str):
    """Delete user account and all associated data."""
    return delete_user_account(user_id)


@app.get("/api/users/{user_id}/sessions/summary")
def get_user_sessions_summary_endpoint(user_id: str, limit: int = 10):
    """Get summary of user's recent sessions."""
    return get_user_sessions_summary(user_id, limit)


@app.post("/api/users/{user_id}/upgrade", response_model=UserProfile)
def upgrade_user_to_paid_endpoint(user_id: str):
    """Upgrade user to paid status."""
    return upgrade_user_to_paid(user_id)


@app.post("/api/users/{user_id}/downgrade", response_model=UserProfile)
def downgrade_user_to_free_endpoint(user_id: str):
    """Downgrade user to free status."""
    return downgrade_user_to_free(user_id)




@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 50, offset: int = 0):
    """Get messages for a specific session with pagination."""
    try:
        db = next(get_db())
        session = get_session(db, session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get messages with pagination
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session_id
        ).order_by(ConversationMessage.timestamp.desc()).offset(offset).limit(limit).all()
        
        message_list = []
        for message in messages:
            message_list.append({
                "id": message.id,
                "message_type": message.message_type,
                "content": message.content,
                "agent_name": message.agent_name,
                "timestamp": message.timestamp.isoformat()
            })
        
        # Get total count
        total_count = db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session_id
        ).count()
        
        return {
            "session_id": session_id,
            "messages": message_list,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session messages for {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting session messages: {str(e)}")


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
        logger.info("  POST /api/login - Firebase authentication and user login")
        logger.info("  POST /chats - Send a chat message and get complete response")
        logger.info("  POST /chats/stream - Send a chat message and get streaming response")
        logger.info("  GET /agents/status - Get status of connected agents")
        logger.info("  POST /agents/{agent_name}/test - Test agent connection")
        logger.info("  GET /health - Health check")
        logger.info("  GET /sessions/{session_id} - Get session information")
        logger.info("  GET /sessions/{session_id}/messages - Get session messages")
        logger.info("  GET /users/{user_id} - Get user information")
        logger.info("  GET /users/{user_id}/sessions - Get user sessions")
        logger.info("  GET /users/{user_id}/profile - Get complete user profile")
        logger.info("  PUT /users/{user_id}/profile - Update user profile")
        logger.info("  GET /users/{user_id}/statistics - Get user statistics")
        logger.info("  DELETE /users/{user_id} - Delete user account")
        logger.info("  GET /users/{user_id}/sessions/summary - Get user sessions summary")
        logger.info("  POST /users/{user_id}/upgrade - Upgrade user to paid")
        logger.info("  POST /users/{user_id}/downgrade - Downgrade user to free")
        
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