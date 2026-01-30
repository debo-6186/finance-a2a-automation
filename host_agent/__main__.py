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
import json

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
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters
from config import get_config

from sqlalchemy.orm import Session

from host.agent import HostAgent
from database import (
    get_db, get_or_create_user, create_session, get_session,
    add_message, can_user_send_message, get_user_message_count,
    update_agent_state, get_agent_state, has_session_messages,
    User, ConversationSession, ConversationMessage, FREE_USER_MESSAGE_LIMIT,
    get_stock_recommendation, get_user_stock_recommendations,
    can_user_generate_report, update_user_max_reports, add_user_credits,
    set_user_whitelist_status, get_or_create_whitelist_entry,
    can_user_send_message_credits, decrement_user_credits, can_session_upload_file
)
from user_api import (
    get_user_profile, get_user_statistics,
    delete_user_account, get_user_sessions_summary, upgrade_user_to_paid,
    downgrade_user_to_free, update_user_profile,
    UserProfile, UserStats, UserUpdateRequest
)

load_dotenv()

# Set up logging with absolute path
logger = logging.getLogger("host_agent_api")
logger.setLevel(logging.INFO)

# Setup file logging (optional - mainly for local development)
# In production, logs go to CloudWatch
formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
try:
    # Get the project root directory (one level up from host_agent/__main__.py)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(project_root, "host_agent")
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "host_agent_api.log")
    handler = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=3)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
except (FileNotFoundError, PermissionError, OSError) as e:
    # File logging not available (e.g., in Docker without mounted volumes)
    # This is fine - logs will go to stdout/CloudWatch
    logger.warning(f"File logging not available: {e}. Logging to stdout only.")

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
    paid_user: bool = False
    createdAt: str




# Global variable to store the host agent instance
host_agent_instance: Optional[HostAgent] = None

# Global variable to store the MCP tool instance
stock_mcp_tool: Optional[MCPToolset] = None

# Import configuration
from config import current_config as Config

# Agent URLs configuration - read from environment via config
AGENT_URLS = [
    Config.STOCK_ANALYSER_AGENT_URL,  # Stock Analyser Agent
    # Stock Report Analyser Agent removed - now integrated locally as a sub-agent
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

        # Get the user record from Firebase Admin SDK to retrieve displayName
        try:
            user_record = firebase_auth.get_user(decoded_token['uid'])
            display_name = user_record.display_name or decoded_token.get('name', 'User')
            logger.info(f"[TOKEN] Retrieved user record, displayName: {display_name}")
        except Exception as e:
            logger.warning(f"[TOKEN] Could not retrieve user record: {e}, using token name")
            display_name = decoded_token.get('name', 'User')

        result = {
            'uid': decoded_token['uid'],
            'email': decoded_token.get('email', 'user@example.com'),
            'email_verified': decoded_token.get('email_verified', False),
            'name': display_name,
            'picture': decoded_token.get('picture')
        }
        logger.info(f"[TOKEN] Returning user info: uid={result['uid']}, email={result['email']}, name={result['name']}")
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
    global host_agent_instance, stock_mcp_tool

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

        # Initialize MCP tool for stock data
        global stock_mcp_tool
        try:
            current_config = get_config()
            mcp_directory = current_config.MCP_DIRECTORY
            logger.info(f"Initializing MCP tool from directory: {mcp_directory}")

            mcp_env = {**os.environ}
            mcp_env["MCP_TIMEOUT"] = os.getenv("MCP_TIMEOUT", "30")

            server_script = os.path.join(mcp_directory, "server.py")

            # Use uv run to execute in the correct virtual environment
            connection_params = StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="uv",
                    args=["run", "--directory", mcp_directory, "python", server_script],
                    env=mcp_env,
                )
            )
            stock_mcp_tool = MCPToolset(
                connection_params=connection_params,
            )
            logger.info("MCP tool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP tool: {e}")
            logger.warning("Continuing without MCP tool - portfolio performance may be limited")

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
        stock_mcp_tool = None


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
    allow_origins=[
        "https://aistockrecommender.com",  # Custom domain
        "https://www.aistockrecommender.com",  # Custom domain with www
        "https://warm-rookery-461602-i8.web.app",  # Keep for backward compatibility
        "https://warm-rookery-461602-i8.firebaseapp.com",  # Keep for backward compatibility
        "http://localhost:3000",  # For local development
        "https://localhost:3000",  # For local development with HTTPS
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/login", response_model=LoginResponse)
def login(login_request: LoginRequest):
    """
    Handle Firebase authentication and user creation/login.
    """
    db = None
    try:
        logger.info(f"Processing login request with token: {login_request.id_token[:20]}...")

        # Validate Firebase token
        firebase_user = validate_firebase_token(login_request.id_token)
        user_id = firebase_user['uid']
        email = firebase_user.get('email', '')
        name = firebase_user.get('name', '')

        logger.info(f"Firebase token validated for user: {user_id}, email: {email}")

        # Get database session
        db = next(get_db())

        # Get or create user in database
        user = get_or_create_user(db, user_id, email=email, name=name, paid_user=False)

        logger.info(f"User {'created' if user else 'found'} in database: {user_id}")

        db.close()
        return LoginResponse(
            id=user_id,
            email=user.email or email,
            name=user.name or name,
            contactNumber=user.contact_number or "",
            countryCode=user.country_code or "+1",
            uploadFile=user.paid_user if user else False,  # Map paid_user to uploadFile
            createdAt=user.created_at.isoformat() if user else "",
            paid_user=user.paid_user if user else False
        )

    except ValueError as e:
        # Handle duplicate email error
        error_msg = str(e)
        logger.error(f"[LOGIN ERROR] Duplicate email detected: {error_msg}")
        logger.error(f"[LOGIN ERROR] Returning 409 Conflict to frontend")
        if db:
            try:
                db.close()
            except:
                pass
        raise HTTPException(status_code=409, detail=error_msg)
    except HTTPException as e:
        logger.error(f"[LOGIN ERROR] HTTP error during login: {e.detail}")
        if db:
            try:
                db.close()
            except:
                pass
        raise e
    except Exception as e:
        logger.error(f"[LOGIN ERROR] Unexpected error during login: {e}")
        if db:
            try:
                db.close()
            except:
                pass
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


@app.post("/api/chats/init")
async def init_chat(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Initialize a chat session and return the greeting message.
    This endpoint is called when a user starts a new chat to get the initial greeting.

    Request body (JSON):
    {
        "user_id": "user123",
        "session_id": "optional-session-id"  // If not provided, a new one will be generated
    }
    """
    try:
        # Parse request body
        json_data = await request.json()
        user_id = json_data.get("user_id")
        session_id = json_data.get("session_id") or str(uuid.uuid4())

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        logger.info(f"[INIT_CHAT] Initializing chat for user {user_id}, session {session_id}")

        # Get database session
        db = next(get_db())

        try:
            # Get or create user
            user = get_or_create_user(db, user_id)

            # Get or create session
            session = get_session(db, session_id)
            if not session:
                # Check report generation limits before creating session
                user_email = user.email if user.email else "no-email@example.com"
                can_generate, limit_message, current_count, max_reports = can_user_generate_report(db, user_email, user_id)

                if not can_generate:
                    logger.warning(f"User {user_id} ({user_email}) blocked from creating session: {limit_message}")
                    raise HTTPException(
                        status_code=403,
                        detail=limit_message
                    )

                logger.info(f"Creating new session {session_id} for user {user_id}")
                session = create_session(db, session_id, user_id)

            # Check if session has any messages - add greeting if no messages exist
            greeting_message = None
            if not has_session_messages(db, session_id):
                initial_greeting = (
                    "Hello! Welcome to the portfolio analysis service. To get started, please provide your portfolio details using any of these methods:\n\n"
                    "1. Upload a PDF portfolio statement\n"
                    "2. Upload a screenshot/snapshot of your portfolio\n"
                    "3. Type your stock holdings directly in the chat (e.g., 'AAPL 30 shares, GOOGL around 20 shares, MSFT 55 shares')\n\n"
                    "How would you like to share your portfolio?"
                )

                # Add initial greeting to database as agent message
                add_message(db, session_id, user_id, "agent", initial_greeting, "host_agent")
                greeting_message = initial_greeting
                logger.info(f"Added greeting message for session {session_id}")
            else:
                logger.info(f"Session {session_id} already has messages, skipping greeting")

            return {
                "session_id": session_id,
                "greeting": greeting_message,
                "has_messages": has_session_messages(db, session_id)
            }

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initializing chat: {e}")
        raise HTTPException(status_code=500, detail=f"Error initializing chat: {str(e)}")


@app.post("/api/chats", response_model=ChatResponse)
async def chat(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Send a message to the host agent and get a complete response.
    This endpoint waits for the full response before returning.

    Supports two input formats:
    1. JSON payload with Content-Type: application/json
    2. Form data with Content-Type: multipart/form-data (for file uploads)
    """
    logger.info("=" * 80)
    logger.info("🔔 DUMMY LOG: /api/chats endpoint has been called!")
    logger.info("=" * 80)
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
    
    # Get database session
    db = next(get_db())

    try:
        logger.info(f"Processing chat message in session {session_id} for user {final_user_id}: {final_message[:100]}...")

        # Get or create user
        user = get_or_create_user(db, final_user_id, paid_user=final_paid_user)

        # Check user credits
        can_send, error_msg = can_user_send_message_credits(db, final_user_id)
        if not can_send:
            raise HTTPException(
                status_code=429,
                detail=error_msg
            )

        # Get or create session
        session = get_session(db, session_id)
        if not session:
            # NEW SESSION: Check report generation limits before creating session
            user_email = user.email if user.email else "no-email@example.com"
            can_generate, limit_message, current_count, max_reports = can_user_generate_report(db, user_email, final_user_id)

            if not can_generate:
                logger.warning(f"User {final_user_id} ({user_email}) blocked from creating session: {limit_message}")
                raise HTTPException(
                    status_code=403,
                    detail=limit_message
                )

            logger.info(f"User {final_user_id} ({user_email}) can generate new report: {current_count}/{max_reports} reports used")
            session = create_session(db, session_id, final_user_id)

        # CRITICAL: Check if session has any messages - send greeting if no messages exist
        # This ensures the greeting is sent every time the API is called with a session that has no messages
        if not has_session_messages(db, session_id):
            initial_greeting = (
                "Hello! Welcome to the portfolio analysis service. To get started, please provide your portfolio details using any of these methods:\n\n"
                "1. Upload a PDF portfolio statement\n"
                "2. Upload a screenshot/snapshot of your portfolio\n"
                "3. Type your stock holdings directly in the chat (e.g., 'AAPL 30 shares, GOOGL around 20 shares, MSFT 55 shares')\n\n"
                "How would you like to share your portfolio?"
            )

            # Add initial greeting to database as agent message
            add_message(db, session_id, final_user_id, "agent", initial_greeting, "host_agent")
            logger.info(f"Sent initial greeting for session {session_id} (no messages found)")

        # Handle file upload if present
        file_uploaded = False
        if uploaded_file and hasattr(uploaded_file, 'filename') and uploaded_file.filename:
            # Check if session can accept file upload (1 per session limit for free users)
            can_upload, upload_error = can_session_upload_file(db, session_id, final_user_id)
            if not can_upload:
                raise HTTPException(
                    status_code=400,
                    detail=upload_error
                )

            try:
                # Validate file type (PDF or image formats)
                filename_lower = uploaded_file.filename.lower()
                allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']

                if not any(filename_lower.endswith(ext) for ext in allowed_extensions):
                    raise HTTPException(
                        status_code=400,
                        detail="Only PDF and image files (JPG, PNG, GIF, BMP, TIFF, WEBP) are allowed"
                    )

                # Get file extension
                import os
                file_ext = os.path.splitext(uploaded_file.filename)[1]

                # Create a temporary file path with appropriate extension
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
                    # Read and write file content
                    if hasattr(uploaded_file, 'read'):
                        content = await uploaded_file.read()
                    else:
                        content = uploaded_file.file.read()
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                
                try:
                    # Update host agent's current session ID for consistency
                    host_agent_instance.current_session_id = {"id": session_id, "user_id": final_user_id, "is_file_uploaded": False}
                    
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

        # Decrement user credits for free users
        logger.info(f"[CREDITS] About to call decrement_user_credits for user {final_user_id}")
        credit_result = decrement_user_credits(db, final_user_id)
        logger.info(f"[CREDITS] decrement_user_credits returned: {credit_result}")

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
            session_id=session_id,
            user_id=final_user_id
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

        # Save agent state to database after conversation turn
        # Note: State should have been saved during tool calls, but we reload and save
        # here to ensure persistence even if tools weren't called
        try:
            import json
            # Get current state from host agent (loads from DB what was saved during tool calls)
            current_state = host_agent_instance._load_state()

            # Log the state values for debugging
            logger.info(f"Current state after conversation turn for session {session_id}:")
            logger.info(f"  - investment_amount: {current_state.get('investment_amount', 0)}")
            logger.info(f"  - diversification_preference: {current_state.get('diversification_preference', 'NOT SET')[:50]}...")
            logger.info(f"  - receiver_email_id: {current_state.get('receiver_email_id', 'NOT SET')}")
            logger.info(f"  - existing_portfolio_stocks: {len(current_state.get('existing_portfolio_stocks', []))} stocks")
            logger.info(f"  - new_stocks: {len(current_state.get('new_stocks', []))} stocks")

            # Save state to database
            update_agent_state(db, session_id, "host_agent", json.dumps(current_state))
            logger.info(f"Agent state persisted to database for session {session_id}")

            # Verify the save by reading it back
            saved_state = get_agent_state(db, session_id, "host_agent")
            if saved_state:
                logger.info(f"✓ Verified: Agent state exists in database for session {session_id}")
            else:
                logger.error(f"✗ Warning: Agent state was NOT saved to database for session {session_id}")
        except Exception as e:
            logger.error(f"Error saving agent state for session {session_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

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

    except ValueError as e:
        # Handle duplicate email error
        logger.error(f"Value error during chat: {e}")
        raise HTTPException(status_code=409, detail=str(e))
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
    finally:
        # Always close the database session
        db.close()
        logger.info(f"Database session closed for session {session_id}")


@app.post("/api/chats/stream")
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

    # Get database session
    db = next(get_db())

    try:
        logger.info(f"Processing streaming chat message in session {session_id} for user {final_user_id}: {final_message[:100]}...")

        # Get or create user
        user = get_or_create_user(db, final_user_id, paid_user=final_paid_user)

        # Check user credits
        can_send, error_msg = can_user_send_message_credits(db, final_user_id)
        if not can_send:
            raise HTTPException(
                status_code=429,
                detail=error_msg
            )

        # Get or create session
        session = get_session(db, session_id)
        if not session:
            # NEW SESSION: Check report generation limits before creating session
            user_email = user.email if user.email else "no-email@example.com"
            can_generate, limit_message, current_count, max_reports = can_user_generate_report(db, user_email, final_user_id)

            if not can_generate:
                logger.warning(f"User {final_user_id} ({user_email}) blocked from creating session: {limit_message}")
                raise HTTPException(
                    status_code=403,
                    detail=limit_message
                )

            logger.info(f"User {final_user_id} ({user_email}) can generate new report: {current_count}/{max_reports} reports used")
            session = create_session(db, session_id, final_user_id)

        # CRITICAL: Check if session has any messages - send greeting if no messages exist
        # This ensures the greeting is sent every time the API is called with a session that has no messages
        if not has_session_messages(db, session_id):
            initial_greeting = (
                "Hello! Welcome to the portfolio analysis service. To get started, please provide your portfolio details using any of these methods:\n\n"
                "1. Upload a PDF portfolio statement\n"
                "2. Upload a screenshot/snapshot of your portfolio\n"
                "3. Type your stock holdings directly in the chat (e.g., 'AAPL 30 shares, GOOGL around 20 shares, MSFT 55 shares')\n\n"
                "How would you like to share your portfolio?"
            )

            # Add initial greeting to database as agent message
            add_message(db, session_id, final_user_id, "agent", initial_greeting, "host_agent")
            logger.info(f"Sent initial greeting for session {session_id} (no messages found)")

        # Handle file upload if present
        file_uploaded = False
        if uploaded_file and hasattr(uploaded_file, 'filename') and uploaded_file.filename:
            # Check if session can accept file upload (1 per session limit for free users)
            can_upload, upload_error = can_session_upload_file(db, session_id, final_user_id)
            if not can_upload:
                raise HTTPException(
                    status_code=400,
                    detail=upload_error
                )

            try:
                # Validate file type (PDF or image formats)
                filename_lower = uploaded_file.filename.lower()
                allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']

                if not any(filename_lower.endswith(ext) for ext in allowed_extensions):
                    raise HTTPException(
                        status_code=400,
                        detail="Only PDF and image files (JPG, PNG, GIF, BMP, TIFF, WEBP) are allowed"
                    )

                # Get file extension
                import os
                file_ext = os.path.splitext(uploaded_file.filename)[1]

                # Create a temporary file path with appropriate extension
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
                    # Read and write file content
                    if hasattr(uploaded_file, 'read'):
                        content = await uploaded_file.read()
                    else:
                        content = uploaded_file.file.read()
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                
                try:
                    # Update host agent's current session ID for consistency
                    host_agent_instance.current_session_id = {"id": session_id, "user_id": final_user_id, "is_file_uploaded": False}
                    
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
            try:
                full_response = ""
                end_session = False
                async for response_chunk in host_agent_instance.stream(
                    query=final_message,
                    session_id=session_id,
                    user_id=final_user_id
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

                        # Save agent state to database after conversation turn
                        # Note: State should have been saved during tool calls, but we reload and save
                        # here to ensure persistence even if tools weren't called
                        try:
                            import json
                            # Get current state from host agent (loads from DB what was saved during tool calls)
                            current_state = host_agent_instance._load_state()

                            # Log the state values for debugging
                            logger.info(f"Current state after conversation turn for session {session_id}:")
                            logger.info(f"  - investment_amount: {current_state.get('investment_amount', 0)}")
                            logger.info(f"  - diversification_preference: {current_state.get('diversification_preference', 'NOT SET')[:50]}...")
                            logger.info(f"  - receiver_email_id: {current_state.get('receiver_email_id', 'NOT SET')}")
                            logger.info(f"  - existing_portfolio_stocks: {len(current_state.get('existing_portfolio_stocks', []))} stocks")
                            logger.info(f"  - new_stocks: {len(current_state.get('new_stocks', []))} stocks")

                            # Save state to database
                            update_agent_state(db, session_id, "host_agent", json.dumps(current_state))
                            logger.info(f"Agent state persisted to database for session {session_id}")

                            # Verify the save by reading it back
                            saved_state = get_agent_state(db, session_id, "host_agent")
                            if saved_state:
                                logger.info(f"✓ Verified: Agent state exists in database for session {session_id}")
                            else:
                                logger.error(f"✗ Warning: Agent state was NOT saved to database for session {session_id}")
                        except Exception as e:
                            logger.error(f"Error saving agent state for session {session_id}: {e}")
                            import traceback
                            logger.error(f"Traceback: {traceback.format_exc()}")

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

            finally:
                # Close database session after streaming completes (or on error)
                db.close()
                logger.info(f"Database session closed for streaming session {session_id}")
        
        return StreamingResponse(
            generate_response(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache"}
        )

    except ValueError as e:
        # Handle duplicate email error
        logger.error(f"Value error during streaming chat: {e}")
        try:
            db.close()
            logger.info(f"Database session closed (ValueError) for session {session_id}")
        except:
            pass  # Already closed or doesn't exist
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        # Close db if generator hasn't started
        try:
            db.close()
            logger.info(f"Database session closed (HTTPException) for session {session_id}")
        except:
            pass  # Already closed or doesn't exist
        raise
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error processing streaming chat message in session {session_id}: {e}")

        # Close db if generator hasn't started
        try:
            db.close()
            logger.info(f"Database session closed (Exception) for session {session_id}")
        except:
            pass  # Already closed or doesn't exist

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
            "message_limit": "unlimited" if user.paid_user else f"{FREE_USER_MESSAGE_LIMIT} messages"
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
@app.get("/api/profile", response_model=UserProfile)
def get_current_user_profile(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user's profile information."""
    return get_user_profile(current_user['uid'], current_user.get('email'))


@app.get("/api/users/{user_id}/profile", response_model=UserProfile)
def get_user_profile_endpoint(user_id: str, current_user: dict = Depends(get_current_user)):
    """Get complete user profile information."""
    # Ensure user can only access their own profile
    if current_user['uid'] != user_id:
        raise HTTPException(status_code=403, detail="You can only access your own profile")

    return get_user_profile(user_id)


@app.put("/api/users/{user_id}/profile", response_model=UserProfile)
def update_user_profile_endpoint(user_id: str, update_data: UserUpdateRequest, current_user: dict = Depends(get_current_user)):
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


@app.post("/api/users/add-credits")
async def add_credits_to_user(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add message credits to the current user's account.
    For now: adds 30 credits for free.
    Later: will integrate with Stripe payment.
    """
    try:
        user_id = current_user["uid"]
        logger.info(f"User {user_id} requesting to add credits")

        # Verify user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Add credits (30 for now, will be configurable with payment later)
        success, new_total = add_user_credits(db, user_id, credits_to_add=30)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to add credits")

        logger.info(f"Added 30 credits to user {user_id}. New total: {new_total}")

        return {
            "success": True,
            "message": "Credits added successfully",
            "credits_added": 30,
            "total_credits": new_total,
            "user_id": user_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding credits to user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/payment/paypal-info")
async def get_paypal_payment_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get PayPal payment information for purchasing credits.
    Returns the PayPal checkout URL and pricing details.
    """
    try:
        config = get_config()

        return {
            "success": True,
            "payment_url": config.PAYPAL_CHECKOUT_URL,
            "credits_per_package": config.CREDITS_PER_PURCHASE,
            "price": config.PAYPAL_PRICE_PER_PACKAGE,
            "currency": config.PAYPAL_CURRENCY,
            "message": f"Pay ${config.PAYPAL_PRICE_PER_PACKAGE} {config.PAYPAL_CURRENCY} to receive {config.CREDITS_PER_PURCHASE} message credits"
        }
    except Exception as e:
        logger.error(f"Error fetching PayPal info: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch payment information")


@app.post("/api/payment/verify")
async def verify_payment(
    transaction_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify PayPal payment and add credits to user account.
    For manual verification: Admin needs to confirm the transaction.

    Args:
        transaction_id: PayPal transaction ID provided by user after payment
    """
    try:
        user_id = current_user["uid"]
        logger.info(f"User {user_id} submitted payment verification for transaction: {transaction_id}")

        # For now, return a pending status
        # In production, you would verify with PayPal API or have admin approval
        return {
            "success": True,
            "status": "pending",
            "message": "Payment verification submitted. Credits will be added after manual verification.",
            "transaction_id": transaction_id,
            "user_id": user_id
        }
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify payment")


# Admin API endpoints for managing user credits and whitelist
class AdminCreditsRequest(BaseModel):
    """
    Request model for admin user credits and settings management.

    All fields except email are optional. Provide only the fields you want to update.
    """
    email: str
    credits: Optional[int] = None  # Add credits to user (incremental)
    max_reports: Optional[int] = None  # Set max reports limit (absolute value)
    whitelist: Optional[bool] = None  # Set whitelist status


@app.post("/api/admin/credits")
def admin_credits_endpoint(request: AdminCreditsRequest):
    """
    Single admin endpoint to manage user credits, max reports, and whitelist status.

    Updates only the fields that are provided in the request.

    Example requests:

    Add 5 credits to a user:
    {
        "email": "user@example.com",
        "credits": 5
    }

    Set max reports to 10:
    {
        "email": "user@example.com",
        "max_reports": 10
    }

    Whitelist a user:
    {
        "email": "user@example.com",
        "whitelist": true
    }

    Update multiple settings at once:
    {
        "email": "user@example.com",
        "credits": 5,
        "max_reports": 10,
        "whitelist": true
    }
    """
    try:
        db = next(get_db())

        # Track what was updated
        updates = []

        # Add credits if provided
        if request.credits is not None:
            success = add_user_credits(db, request.email, request.credits)
            if success:
                updates.append(f"Added {request.credits} credits")
            else:
                raise HTTPException(status_code=500, detail="Failed to add credits")

        # Set max reports if provided
        if request.max_reports is not None:
            success = update_user_max_reports(db, request.email, request.max_reports)
            if success:
                updates.append(f"Set max_reports to {request.max_reports}")
            else:
                raise HTTPException(status_code=500, detail="Failed to update max_reports")

        # Set whitelist status if provided
        if request.whitelist is not None:
            success = set_user_whitelist_status(db, request.email, request.whitelist)
            if success:
                status = "whitelisted" if request.whitelist else "blacklisted"
                updates.append(f"User {status}")
            else:
                raise HTTPException(status_code=500, detail="Failed to update whitelist status")

        # If no fields were provided, return error
        if not updates:
            raise HTTPException(
                status_code=400,
                detail="At least one field (credits, max_reports, or whitelist) must be provided"
            )

        # Get final state of user
        whitelist_entry = get_or_create_whitelist_entry(db, request.email)

        # Find user by email to get user_id for report count
        user = db.query(User).filter(User.email == request.email).first()
        current_count = 0
        if user:
            from database import count_user_valid_recommendations
            current_count = count_user_valid_recommendations(db, user.id)

        return {
            "success": True,
            "message": "; ".join(updates),
            "email": request.email,
            "current_state": {
                "whitelisted": whitelist_entry.whitelisted if whitelist_entry else False,
                "max_reports": whitelist_entry.max_reports if whitelist_entry else 0,
                "current_report_count": current_count,
                "remaining_reports": max(0, whitelist_entry.max_reports - current_count) if (whitelist_entry and whitelist_entry.max_reports > 0) else "unlimited"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in admin_credits_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/credits/{email}")
def get_admin_credits_info(email: str):
    """
    Get user credits, max reports, and whitelist information.

    Returns the current state of user's credits and settings.
    """
    db = None
    try:
        db = next(get_db())

        # Validate email format
        if not email or '@' not in email:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Invalid email format",
                    "message": "Please provide a valid email address"
                }
            )

        # Get whitelist entry
        whitelist_entry = get_or_create_whitelist_entry(db, email)

        if not whitelist_entry:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "User not found",
                    "message": f"No user found with email: {email}"
                }
            )

        # Find user by email to get user_id
        user = db.query(User).filter(User.email == email).first()

        # Count reports if user exists
        current_count = 0
        if user:
            from database import count_user_valid_recommendations
            current_count = count_user_valid_recommendations(db, user.id)

        return {
            "success": True,
            "email": email,
            "whitelisted": whitelist_entry.whitelisted,
            "max_reports": whitelist_entry.max_reports,
            "current_report_count": current_count,
            "remaining_reports": max(0, whitelist_entry.max_reports - current_count) if whitelist_entry.max_reports > 0 else "unlimited",
            "created_at": whitelist_entry.created_at.isoformat(),
            "updated_at": whitelist_entry.updated_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting credits info for {email}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )
    finally:
        if db:
            db.close()




@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 50, offset: int = 0):
    """Get messages for a specific session with pagination."""
    try:
        db = next(get_db())
        session = get_session(db, session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get messages with pagination (ordered chronologically - oldest first)
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session_id
        ).order_by(ConversationMessage.timestamp.asc()).offset(offset).limit(limit).all()
        
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


@app.get("/api/portfolio-performance/{session_id}")
async def get_portfolio_performance(session_id: str, _current_user: dict = Depends(get_current_user)):
    """
    Get portfolio performance showing profit/loss for recommended stocks.
    Calculates based on entry price vs current price, taking into account number of shares.

    Returns:
        {
            "overall_performance": {
                "total_investment": 2100.00,
                "current_value": 2310.00,
                "profit_loss": 210.00,
                "profit_loss_percentage": 10.0,
                "status": "profit"  // or "loss"
            },
            "stocks": [
                {
                    "ticker": "AMZN",
                    "entry_price": 232.00,
                    "current_price": 245.00,
                    "investment_amount": 525.00,
                    "shares": 2.26,
                    "current_value": 554.52,
                    "profit_loss": 29.52,
                    "profit_loss_percentage": 5.62,
                    "status": "profit"
                },
                ...
            ],
            "recommendation_date": "2025-12-30T10:30:00"
        }
    """
    try:
        logger.info(f"Fetching portfolio performance for session {session_id}")

        # Get database session
        db = next(get_db())

        try:
            # Get the stock recommendation for this session
            recommendation = get_stock_recommendation(db, session_id)

            if not recommendation:
                raise HTTPException(status_code=404, detail="No stock recommendation found for this session")

            # Parse the recommendation JSON
            rec_data = recommendation.recommendation
            allocation_breakdown = rec_data.get("allocation_breakdown", [])
            entry_prices = rec_data.get("entry_prices", {})
            recommendation_date = rec_data.get("recommendation_date", recommendation.created_at.isoformat())

            # If entry_prices is missing, fetch from MCP and populate
            if not entry_prices:
                logger.info("Entry prices missing - fetching from MCP")

                if not stock_mcp_tool:
                    raise HTTPException(
                        status_code=503,
                        detail="Stock data service unavailable. Cannot fetch entry prices."
                    )

                try:
                    # Fetch stock prices from MCP
                    tickers = [stock["ticker"] for stock in allocation_breakdown]
                    entry_prices = {}

                    for ticker in tickers:
                        try:
                            logger.info(f"Fetching stock info for {ticker} from MCP")
                            session = await stock_mcp_tool._mcp_session_manager.create_session()
                            stock_data = await session.call_tool("get_stock_info", arguments={"symbol": ticker})

                            # Parse the stock data JSON
                            stock_info = json.loads(str(stock_data))

                            # Extract currentPrice from MCP data
                            stock_type = stock_info.get("stock_type", "EQUITY")
                            current_price = None

                            if stock_type == "EQUITY":
                                core_valuation = stock_info.get("core_valuation_metrics", {})
                                current_price = core_valuation.get("currentPrice")
                            else:  # ETF
                                trading_valuation = stock_info.get("trading_valuation", {})
                                current_price = trading_valuation.get("regularMarketPrice")

                            if current_price:
                                entry_prices[ticker] = float(current_price)
                                logger.info(f"Fetched entry price for {ticker}: ${current_price}")

                        except Exception as ticker_error:
                            logger.error(f"Error fetching price for {ticker}: {ticker_error}")
                            continue

                    if entry_prices:
                        # Update recommendation in database with entry prices
                        rec_data["entry_prices"] = entry_prices
                        if "recommendation_date" not in rec_data:
                            rec_data["recommendation_date"] = recommendation.created_at.isoformat()

                        # Save updated recommendation
                        from host_agent.database import StockRecommendation
                        from sqlalchemy import update

                        stmt = update(StockRecommendation).where(
                            StockRecommendation.session_id == session_id
                        ).values(recommendation=rec_data)
                        db.execute(stmt)
                        db.commit()

                        logger.info(f"Populated and saved entry prices for {len(entry_prices)} stocks")
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail="Failed to fetch entry prices from stock data service."
                        )

                except Exception as mcp_error:
                    logger.error(f"Error fetching entry prices from MCP: {mcp_error}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error fetching stock prices: {str(mcp_error)}"
                    )

            # Check if recommendation is less than 1 day old
            from datetime import datetime, timedelta
            rec_datetime = datetime.fromisoformat(recommendation_date.replace('Z', '+00:00'))
            time_since_recommendation = datetime.now(rec_datetime.tzinfo) - rec_datetime
            is_too_recent = time_since_recommendation < timedelta(days=1)

            if is_too_recent:
                logger.info(f"Recommendation is only {time_since_recommendation.total_seconds() / 3600:.1f} hours old - too recent for performance calculation")
            else:
                logger.info(f"Recommendation is {time_since_recommendation.days} days old - calculating performance")

            # If recommendation is too recent, return minimal data without performance metrics
            if is_too_recent:
                hours_old = time_since_recommendation.total_seconds() / 3600
                stock_list = []

                for stock in allocation_breakdown:
                    ticker = stock["ticker"]
                    import re
                    investment_str = stock.get("investment_amount", "$0")
                    investment_match = re.search(r'[\d.]+', investment_str)
                    investment_amount = float(investment_match.group()) if investment_match else 0.0

                    entry_price = entry_prices.get(ticker, 0.0)

                    stock_list.append({
                        "ticker": ticker,
                        "entry_price": round(entry_price, 2),
                        "investment_amount": round(investment_amount, 2),
                        "status": "too_recent"
                    })

                total_investment = sum(
                    float(re.search(r'[\d.]+', s.get("investment_amount", "$0")).group())
                    for s in allocation_breakdown
                    if re.search(r'[\d.]+', s.get("investment_amount", "$0"))
                )

                return {
                    "overall_performance": {
                        "total_investment": round(total_investment, 2),
                        "status": "too_recent",
                        "message": f"Recommendation is only {hours_old:.1f} hours old. Performance tracking will be available after 24 hours."
                    },
                    "stocks": stock_list,
                    "recommendation_date": recommendation_date,
                    "is_too_recent": True,
                    "hours_since_recommendation": round(hours_old, 1)
                }

            # Fetch current prices for all tickers (only if recommendation is old enough)
            logger.info(f"Fetching current prices for {len(allocation_breakdown)} stocks")
            current_prices = await fetch_current_stock_prices([stock["ticker"] for stock in allocation_breakdown])

            # Calculate performance for each stock
            stock_performance = []
            total_investment = 0.0
            total_current_value = 0.0

            for stock in allocation_breakdown:
                ticker = stock["ticker"]

                # Extract investment amount (remove $ and convert to float)
                import re
                investment_str = stock.get("investment_amount", "$0")
                investment_match = re.search(r'[\d.]+', investment_str)
                investment_amount = float(investment_match.group()) if investment_match else 0.0

                total_investment += investment_amount

                # Get entry and current prices
                entry_price = entry_prices.get(ticker, 0.0)
                current_price = current_prices.get(ticker, 0.0)

                if entry_price > 0 and current_price > 0:
                    # Get number of shares - prefer pre-calculated value from recommendation
                    shares_str = stock.get("number_of_shares")
                    if shares_str:
                        # Parse the shares string (format: "16.6667 shares")
                        shares_match = re.search(r'[\d.]+', shares_str)
                        shares = float(shares_match.group()) if shares_match else 0.0
                        logger.info(f"Using pre-calculated shares for {ticker}: {shares}")
                    else:
                        # Fallback: Calculate number of shares (for backward compatibility)
                        shares = investment_amount / entry_price
                        logger.info(f"Calculated shares for {ticker}: {shares} (no pre-calculated value found)")

                    # Calculate current value
                    current_value = shares * current_price

                    # Calculate profit/loss
                    profit_loss = current_value - investment_amount
                    profit_loss_percentage = (profit_loss / investment_amount) * 100 if investment_amount > 0 else 0.0

                    status = "profit" if profit_loss >= 0 else "loss"

                    stock_performance.append({
                        "ticker": ticker,
                        "entry_price": round(entry_price, 2),
                        "current_price": round(current_price, 2),
                        "investment_amount": round(investment_amount, 2),
                        "shares": round(shares, 2),
                        "current_value": round(current_value, 2),
                        "profit_loss": round(profit_loss, 2),
                        "profit_loss_percentage": round(profit_loss_percentage, 2),
                        "status": status
                    })

                    total_current_value += current_value
                else:
                    logger.warning(f"Missing price data for {ticker} (entry: {entry_price}, current: {current_price})")
                    # Add stock with error status
                    stock_performance.append({
                        "ticker": ticker,
                        "entry_price": entry_price,
                        "current_price": current_price,
                        "investment_amount": round(investment_amount, 2),
                        "shares": 0.0,
                        "current_value": 0.0,
                        "profit_loss": 0.0,
                        "profit_loss_percentage": 0.0,
                        "status": "error",
                        "error": "Price data unavailable"
                    })

            # Calculate overall performance
            overall_profit_loss = total_current_value - total_investment
            overall_profit_loss_percentage = (overall_profit_loss / total_investment) * 100 if total_investment > 0 else 0.0
            overall_status = "profit" if overall_profit_loss >= 0 else "loss"

            response = {
                "overall_performance": {
                    "total_investment": round(total_investment, 2),
                    "current_value": round(total_current_value, 2),
                    "profit_loss": round(overall_profit_loss, 2),
                    "profit_loss_percentage": round(overall_profit_loss_percentage, 2),
                    "status": overall_status
                },
                "stocks": stock_performance,
                "recommendation_date": recommendation_date,
                "is_too_recent": False,
                "days_since_recommendation": time_since_recommendation.days
            }

            logger.info(f"Portfolio performance calculated: {overall_status} of ${abs(overall_profit_loss):.2f} ({overall_profit_loss_percentage:.2f}%)")
            return response

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating portfolio performance for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error calculating portfolio performance: {str(e)}")


@app.get("/api/latest-portfolio-performance/{user_id}")
async def get_latest_portfolio_performance(user_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get portfolio performance for the user's latest stock recommendation.

    Automatically fetches the most recent recommendation and shows transparent
    profit/loss calculations with detailed price comparisons for each stock.

    Returns:
        {
            "user_id": "user123",
            "session_id": "session_abc",
            "recommendation_date": "2025-01-15T10:00:00",
            "days_since_recommendation": 5,
            "overall_performance": {
                "total_investment": 10000.00,
                "total_current_value": 10500.00,
                "total_profit_loss": 500.00,
                "total_profit_loss_percentage": 5.00,
                "status": "profit"
            },
            "stocks": [
                {
                    "ticker": "AAPL",
                    "recommendation": "BUY",
                    "conviction_level": "HIGH",
                    "entry_price": 180.00,
                    "current_price": 185.50,
                    "price_change": 5.50,
                    "price_change_percentage": 3.06,
                    "number_of_shares": 13.8889,
                    "investment_amount": 2500.00,
                    "current_value": 2576.39,
                    "profit_loss": 76.39,
                    "profit_loss_percentage": 3.06,
                    "status": "profit"
                },
                ...
            ]
        }
    """
    try:
        logger.info(f"Fetching latest portfolio performance for user {user_id}")

        # Verify the authenticated user matches the requested user_id
        if current_user.get('uid') != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized to access this user's portfolio")

        # Get database session
        db = next(get_db())

        try:
            # Get the latest recommendation for this user
            recommendations = get_user_stock_recommendations(db, user_id)

            if not recommendations:
                raise HTTPException(status_code=404, detail="No stock recommendations found for this user")

            # Get the most recent recommendation (already ordered by created_at desc)
            latest_recommendation = recommendations[0]
            session_id = latest_recommendation.session_id

            logger.info(f"Found latest recommendation for user {user_id} in session {session_id}")

            # Parse the recommendation JSON
            rec_data = latest_recommendation.recommendation
            individual_recommendations = rec_data.get("individual_stock_recommendations", [])
            entry_prices = rec_data.get("entry_prices", {})
            recommendation_date = rec_data.get("recommendation_date", latest_recommendation.created_at.isoformat())

            # Calculate time since recommendation
            from datetime import datetime
            rec_datetime = datetime.fromisoformat(recommendation_date.replace('Z', '+00:00') if 'Z' in recommendation_date else recommendation_date)
            time_since_recommendation = datetime.now() - rec_datetime

            # Check if recommendation is too recent (less than 24 hours)
            if time_since_recommendation.total_seconds() < 86400:  # 24 hours in seconds
                hours_since = time_since_recommendation.total_seconds() / 3600
                logger.info(f"Recommendation is only {hours_since:.1f} hours old, returning limited data")

                return {
                    "user_id": user_id,
                    "session_id": session_id,
                    "recommendation_date": recommendation_date,
                    "is_too_recent": True,
                    "hours_since_recommendation": round(hours_since, 1),
                    "message": f"Recommendation is only {hours_since:.1f} hours old. Performance tracking will be available after 24 hours.",
                    "overall_performance": {
                        "status": "too_recent"
                    },
                    "stocks": []
                }

            # Get BUY stocks only (those with investment amounts > 0)
            buy_stocks = [
                stock for stock in individual_recommendations
                if stock.get("recommendation") == "BUY"
            ]

            if not buy_stocks:
                raise HTTPException(status_code=404, detail="No BUY recommendations found in latest recommendation")

            # Extract tickers for current price fetching
            tickers = [stock["ticker"] for stock in buy_stocks]

            # Fetch current prices
            logger.info(f"Fetching current prices for {len(tickers)} stocks from MCP")
            current_prices = await fetch_current_prices_from_mcp(tickers)

            if not current_prices:
                raise HTTPException(status_code=500, detail="Failed to fetch current stock prices")

            # Calculate performance for each BUY stock
            stock_performance = []
            total_investment = 0.0
            total_current_value = 0.0

            import re
            for stock in buy_stocks:
                ticker = stock["ticker"]

                # Get entry price
                entry_price = entry_prices.get(ticker)
                if not entry_price:
                    # Try to extract from stock's entry_price field
                    entry_price_str = stock.get("entry_price", "$0")
                    entry_match = re.search(r'[\d.]+', entry_price_str)
                    entry_price = float(entry_match.group()) if entry_match else 0.0

                # Get current price
                current_price = current_prices.get(ticker, 0.0)

                # Get number of shares - prefer pre-calculated value
                shares_str = stock.get("number_of_shares")
                if shares_str:
                    shares_match = re.search(r'[\d.]+', shares_str)
                    shares = float(shares_match.group()) if shares_match else 0.0
                else:
                    # Fallback: calculate from investment amount
                    investment_str = stock.get("investment_amount", "$0")
                    investment_match = re.search(r'[\d.]+', investment_str)
                    investment_amount = float(investment_match.group()) if investment_match else 0.0
                    shares = investment_amount / entry_price if entry_price > 0 else 0.0

                # Get investment amount
                investment_str = stock.get("investment_amount", "$0")
                investment_match = re.search(r'[\d.]+', investment_str)
                investment_amount = float(investment_match.group()) if investment_match else 0.0

                if entry_price > 0 and current_price > 0 and shares > 0:
                    # Calculate values
                    current_value = shares * current_price
                    profit_loss = current_value - investment_amount
                    profit_loss_percentage = (profit_loss / investment_amount) * 100 if investment_amount > 0 else 0.0

                    # Calculate price change
                    price_change = current_price - entry_price
                    price_change_percentage = (price_change / entry_price) * 100 if entry_price > 0 else 0.0

                    status = "profit" if profit_loss >= 0 else "loss"

                    stock_performance.append({
                        "ticker": ticker,
                        "recommendation": "BUY",
                        "conviction_level": stock.get("conviction_level", "N/A"),
                        "entry_price": round(entry_price, 2),
                        "current_price": round(current_price, 2),
                        "price_change": round(price_change, 2),
                        "price_change_percentage": round(price_change_percentage, 2),
                        "number_of_shares": round(shares, 4),
                        "investment_amount": round(investment_amount, 2),
                        "current_value": round(current_value, 2),
                        "profit_loss": round(profit_loss, 2),
                        "profit_loss_percentage": round(profit_loss_percentage, 2),
                        "status": status
                    })

                    total_investment += investment_amount
                    total_current_value += current_value
                else:
                    logger.warning(f"Missing data for {ticker}: entry_price={entry_price}, current_price={current_price}, shares={shares}")
                    stock_performance.append({
                        "ticker": ticker,
                        "recommendation": "BUY",
                        "conviction_level": stock.get("conviction_level", "N/A"),
                        "entry_price": entry_price,
                        "current_price": current_price,
                        "price_change": 0.0,
                        "price_change_percentage": 0.0,
                        "number_of_shares": shares,
                        "investment_amount": round(investment_amount, 2),
                        "current_value": 0.0,
                        "profit_loss": 0.0,
                        "profit_loss_percentage": 0.0,
                        "status": "error",
                        "error": "Incomplete price or share data"
                    })

            # Calculate overall performance
            overall_profit_loss = total_current_value - total_investment
            overall_profit_loss_percentage = (overall_profit_loss / total_investment) * 100 if total_investment > 0 else 0.0
            overall_status = "profit" if overall_profit_loss >= 0 else "loss"

            response = {
                "user_id": user_id,
                "session_id": session_id,
                "recommendation_date": recommendation_date,
                "days_since_recommendation": time_since_recommendation.days,
                "is_too_recent": False,
                "overall_performance": {
                    "total_investment": round(total_investment, 2),
                    "total_current_value": round(total_current_value, 2),
                    "total_profit_loss": round(overall_profit_loss, 2),
                    "total_profit_loss_percentage": round(overall_profit_loss_percentage, 2),
                    "status": overall_status
                },
                "stocks": stock_performance
            }

            logger.info(f"Latest portfolio performance calculated: {overall_status} of ${abs(overall_profit_loss):.2f} ({overall_profit_loss_percentage:.2f}%)")
            return response

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating latest portfolio performance for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error calculating portfolio performance: {str(e)}")


@app.get("/api/user-recommendations/{user_id}")
async def get_user_recommendations(user_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get all stock recommendations for a user.

    Returns a list of recommendations with their session IDs, dates, and basic info.
    """
    try:
        logger.info(f"Fetching recommendations for user {user_id}")

        # Verify the authenticated user matches the requested user_id
        if current_user.get('uid') != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized to access this user's recommendations")

        # Get database session
        db = next(get_db())

        try:
            # Get all recommendations for this user
            recommendations = get_user_stock_recommendations(db, user_id)

            if not recommendations:
                return {
                    "user_id": user_id,
                    "recommendations": [],
                    "total_count": 0
                }

            # Format recommendations for response
            formatted_recommendations = []
            for rec in recommendations:
                rec_data = rec.recommendation
                allocation_breakdown = rec_data.get("allocation_breakdown", [])

                # Calculate total investment
                import re
                total_investment = sum(
                    float(re.search(r'[\d.]+', stock.get("investment_amount", "$0")).group())
                    for stock in allocation_breakdown
                    if re.search(r'[\d.]+', stock.get("investment_amount", "$0"))
                )

                formatted_recommendations.append({
                    "session_id": rec.session_id,
                    "created_at": rec.created_at.isoformat(),
                    "total_investment": round(total_investment, 2),
                    "stock_count": len(allocation_breakdown),
                    "stocks": [s.get("ticker") for s in allocation_breakdown],
                    "has_entry_prices": "entry_prices" in rec_data,
                    "recommendation_date": rec_data.get("recommendation_date", rec.created_at.isoformat())
                })

            return {
                "user_id": user_id,
                "recommendations": formatted_recommendations,
                "total_count": len(formatted_recommendations)
            }

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user recommendations for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching recommendations: {str(e)}")


async def fetch_current_stock_prices(tickers: list) -> dict:
    """
    Fetch current stock prices for a list of tickers.

    Args:
        tickers: List of stock ticker symbols

    Returns:
        Dictionary mapping ticker to current price
    """
    import json

    prices = {}

    # Use Perplexity API to fetch current prices
    try:
        from openai import OpenAI

        perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
        if not perplexity_api_key:
            logger.error("PERPLEXITY_API_KEY not found")
            return prices

        client = OpenAI(
            api_key=perplexity_api_key,
            base_url="https://api.perplexity.ai"
        )

        # Request current prices for all tickers
        ticker_list = ", ".join(tickers)

        response = client.chat.completions.create(
            model="sonar",
            messages=[
                {
                    "role": "system",
                    "content": """You are a stock price lookup assistant. Return ONLY valid JSON with no additional text.
                    Format: {"TICKER": price_as_number, ...}
                    Example: {"AAPL": 232.50, "GOOGL": 175.30}"""
                },
                {
                    "role": "user",
                    "content": f"Get the current stock prices for these tickers: {ticker_list}. Return as JSON only."
                }
            ]
        )

        # Parse the response
        if response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content.strip()

            # Remove markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            # Parse JSON
            prices = json.loads(content)
            logger.info(f"Fetched current prices for {len(prices)} stocks")

    except Exception as e:
        logger.error(f"Error fetching current stock prices: {e}")

    return prices


async def fetch_current_prices_from_mcp(tickers: list) -> dict:
    """
    Fetch current stock prices using MCP tool.

    Args:
        tickers: List of stock ticker symbols

    Returns:
        Dictionary mapping ticker to current price
    """
    prices = {}

    if not stock_mcp_tool:
        logger.error("MCP tool not available for fetching prices")
        return prices

    try:
        for ticker in tickers:
            try:
                logger.info(f"Fetching current price for {ticker} from MCP")
                session = await stock_mcp_tool._mcp_session_manager.create_session()
                stock_data_result = await session.call_tool("get_stock_info", arguments={"symbol": ticker})

                # Parse MCP result object
                stock_data = None
                if hasattr(stock_data_result, 'content'):
                    if isinstance(stock_data_result.content, list) and len(stock_data_result.content) > 0:
                        content_item = stock_data_result.content[0]
                        if hasattr(content_item, 'text'):
                            stock_data = json.loads(content_item.text)
                elif isinstance(stock_data_result, dict):
                    stock_data = stock_data_result
                elif isinstance(stock_data_result, str):
                    stock_data = json.loads(stock_data_result)

                if stock_data:
                    stock_type = stock_data.get("stock_type", "EQUITY")
                    current_price = None

                    if stock_type == "EQUITY":
                        core_valuation = stock_data.get("core_valuation_metrics", {})
                        current_price = core_valuation.get("currentPrice")
                    else:  # ETF
                        trading_valuation = stock_data.get("trading_valuation", {})
                        current_price = trading_valuation.get("regularMarketPrice")

                    if current_price:
                        prices[ticker] = float(current_price)
                        logger.info(f"Fetched current price for {ticker}: ${current_price}")
                    else:
                        logger.warning(f"No price found for {ticker}")

            except Exception as ticker_error:
                logger.error(f"Error fetching price for {ticker}: {ticker_error}")
                continue

    except Exception as e:
        logger.error(f"Error in fetch_current_prices_from_mcp: {e}")

    return prices


@app.get("/api/debug/user-recommendations/{user_id}")
async def debug_user_recommendations(user_id: str, _current_user: dict = Depends(get_current_user)):
    """
    Debug endpoint to see the raw recommendation data structure.
    """
    try:
        db = next(get_db())
        try:
            recommendations = get_user_stock_recommendations(db, user_id)
            if not recommendations or len(recommendations) == 0:
                return {"error": "No recommendations found", "user_id": user_id}

            latest = recommendations[0]
            return {
                "user_id": user_id,
                "session_id": latest.session_id,
                "created_at": latest.created_at.isoformat(),
                "recommendation_data": latest.recommendation,
                "has_individual_recommendations": bool(latest.recommendation.get("individual_stock_recommendations")),
                "has_entry_prices": bool(latest.recommendation.get("entry_prices")),
                "individual_recommendations_count": len(latest.recommendation.get("individual_stock_recommendations", [])),
                "entry_prices_count": len(latest.recommendation.get("entry_prices", {}))
            }
        finally:
            db.close()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/portfolio-performance/user/{user_id}")
async def get_user_portfolio_performance(user_id: str, _current_user: dict = Depends(get_current_user)):
    """
    Get portfolio performance for the user's LATEST stock recommendation.
    Shows profit/loss by comparing entry_price vs current MCP price.
    Only tracks BUY and SELL stocks.

    Returns:
        {
            "overall_performance": {
                "total_investment": 3000.00,
                "current_value": 3250.00,
                "profit_loss": 250.00,
                "profit_loss_percentage": 8.33,
                "status": "profit"
            },
            "stocks": [
                {
                    "ticker": "AMZN",
                    "recommendation": "BUY",
                    "entry_price": 215.30,
                    "current_price": 220.50,
                    "investment_amount": 750.00,
                    "shares": 3.48,
                    "current_value": 767.52,
                    "profit_loss": 17.52,
                    "profit_loss_percentage": 2.34,
                    "status": "profit"
                },
                ...
            ],
            "recommendation_date": "2026-01-02T10:30:00",
            "session_id": "session_123"
        }
    """
    try:
        logger.info(f"Fetching latest portfolio performance for user {user_id}")

        # Get database session
        db = next(get_db())

        try:
            # Get the LATEST stock recommendation for this user
            recommendations = get_user_stock_recommendations(db, user_id)

            if not recommendations or len(recommendations) == 0:
                raise HTTPException(status_code=404, detail="No stock recommendations found for this user")

            # Get the most recent recommendation (first in list as it's ordered by created_at desc)
            latest_recommendation = recommendations[0]
            rec_data = latest_recommendation.recommendation

            # Extract data
            individual_recommendations = rec_data.get("individual_stock_recommendations", [])
            entry_prices_dict = rec_data.get("entry_prices", {})
            recommendation_date = rec_data.get("recommendation_date", latest_recommendation.created_at.isoformat())
            session_id = latest_recommendation.session_id

            # Log what we found
            logger.info(f"Total individual recommendations: {len(individual_recommendations)}")
            for stock in individual_recommendations:
                logger.info(f"Stock {stock.get('ticker')}: recommendation={stock.get('recommendation')}, has entry_price={bool(stock.get('entry_price'))}")

            # Use ALL stocks (BUY/SELL/HOLD) for performance tracking
            all_stocks = individual_recommendations

            if not all_stocks:
                logger.warning("No stock recommendations found")
                return {
                    "overall_performance": {
                        "total_investment": 0.0,
                        "current_value": 0.0,
                        "profit_loss": 0.0,
                        "profit_loss_percentage": 0.0,
                        "status": "no_recommendations"
                    },
                    "stocks": [],
                    "recommendation_date": recommendation_date,
                    "session_id": session_id,
                    "message": "No stock recommendations found in your latest portfolio"
                }

            logger.info(f"Processing {len(all_stocks)} stocks (BUY/SELL/HOLD)")

            # Get tickers for current price lookup
            tickers = [stock["ticker"] for stock in all_stocks]

            # Fetch current prices from MCP
            logger.info(f"Fetching current prices for {len(tickers)} stocks from MCP")
            current_prices = await fetch_current_prices_from_mcp(tickers)

            # Calculate performance for each stock (BUY/SELL/HOLD)
            stock_performance = []
            total_investment = 0.0
            total_current_value = 0.0

            for stock in all_stocks:
                ticker = stock.get("ticker")
                recommendation = stock.get("recommendation", "HOLD")

                # Extract investment amount
                import re
                investment_str = stock.get("investment_amount", "$0")
                investment_match = re.search(r'[\d.]+', investment_str.replace(",", ""))
                investment_amount = float(investment_match.group()) if investment_match else 0.0

                # Get entry price from the stock recommendation (we just added this field!)
                entry_price_str = stock.get("entry_price", "")
                if entry_price_str:
                    entry_price_match = re.search(r'[\d.]+', str(entry_price_str).replace(",", ""))
                    entry_price = float(entry_price_match.group()) if entry_price_match else entry_prices_dict.get(ticker, 0.0)
                else:
                    # Fallback to entry_prices dict
                    entry_price = entry_prices_dict.get(ticker, 0.0)

                # Get current price from MCP
                current_price = current_prices.get(ticker, 0.0)

                # For HOLD stocks or stocks with investment, calculate performance
                if entry_price > 0 and current_price > 0:
                    if investment_amount > 0:
                        # Calculate shares: investment_amount / entry_price
                        shares = investment_amount / entry_price

                        # Calculate current value
                        current_value = shares * current_price

                        # Calculate profit/loss
                        profit_loss = current_value - investment_amount
                        profit_loss_percentage = (profit_loss / investment_amount) * 100

                        status = "profit" if profit_loss >= 0 else "loss"

                        stock_performance.append({
                            "ticker": ticker,
                            "recommendation": recommendation,
                            "entry_price": round(entry_price, 2),
                            "current_price": round(current_price, 2),
                            "investment_amount": round(investment_amount, 2),
                            "shares": round(shares, 4),
                            "current_value": round(current_value, 2),
                            "profit_loss": round(profit_loss, 2),
                            "profit_loss_percentage": round(profit_loss_percentage, 2),
                            "status": status
                        })

                        # Only count BUY stocks in total investment and profit/loss
                        if recommendation == "BUY":
                            total_investment += investment_amount
                            total_current_value += current_value
                    else:
                        # HOLD or SELL stock - show prices but no investment
                        stock_performance.append({
                            "ticker": ticker,
                            "recommendation": recommendation,
                            "entry_price": round(entry_price, 2),
                            "current_price": round(current_price, 2),
                            "investment_amount": 0.0,
                            "shares": 0.0,
                            "current_value": 0.0,
                            "profit_loss": 0.0,
                            "profit_loss_percentage": 0.0,
                            "status": "neutral"
                        })
                else:
                    # Missing price data
                    logger.warning(f"Missing data for {ticker}: entry={entry_price}, current={current_price}")
                    stock_performance.append({
                        "ticker": ticker,
                        "recommendation": recommendation,
                        "entry_price": entry_price if entry_price > 0 else 0.0,
                        "current_price": current_price if current_price > 0 else 0.0,
                        "investment_amount": round(investment_amount, 2),
                        "shares": 0.0,
                        "current_value": 0.0,
                        "profit_loss": 0.0,
                        "profit_loss_percentage": 0.0,
                        "status": "error",
                        "error": "Price data unavailable"
                    })

            # Calculate overall performance
            overall_profit_loss = total_current_value - total_investment
            overall_profit_loss_percentage = (overall_profit_loss / total_investment) * 100 if total_investment > 0 else 0.0
            overall_status = "profit" if overall_profit_loss >= 0 else "loss"

            return {
                "overall_performance": {
                    "total_investment": round(total_investment, 2),
                    "current_value": round(total_current_value, 2),
                    "profit_loss": round(overall_profit_loss, 2),
                    "profit_loss_percentage": round(overall_profit_loss_percentage, 2),
                    "status": overall_status
                },
                "stocks": stock_performance,
                "recommendation_date": recommendation_date,
                "session_id": session_id
            }

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio performance for user {user_id}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error calculating portfolio performance: {str(e)}")


def main():
    """Start the Host Agent API server."""
    try:
        # Check for required environment variables
        if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            logger.error("GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE.")
            exit(1)

        logger.info(f"GOOGLE_API_KEY: {os.getenv("GOOGLE_API_KEY")}")
        
        host = "0.0.0.0"  # Listen on all interfaces to accept external connections
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
        logger.info("  GET /api/portfolio-performance/{session_id} - Get portfolio profit/loss performance")
        logger.info("  GET /api/user-recommendations/{user_id} - Get all recommendations for a user")
        logger.info("  GET /users/{user_id} - Get user information")
        logger.info("  GET /users/{user_id}/sessions - Get user sessions")
        logger.info("  GET /api/profile - Get current user's profile (authenticated)")
        logger.info("  GET /users/{user_id}/profile - Get complete user profile")
        logger.info("  GET /users/{user_id}/statistics - Get user statistics")
        logger.info("  DELETE /users/{user_id} - Delete user account")
        logger.info("  GET /users/{user_id}/sessions/summary - Get user sessions summary")
        logger.info("  POST /users/{user_id}/upgrade - Upgrade user to paid")
        logger.info("  POST /users/{user_id}/downgrade - Downgrade user to free")
        logger.info("  POST /api/admin/credits - Manage user credits, max reports, and whitelist")
        logger.info("  GET /api/admin/credits/{email} - Get user credits and settings info")
        
        # Run using the in-memory app object to avoid module import path issues
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=False,  # Reload disabled for production
            log_level="info"
        )
        
    except Exception as e:
        logger.error(f"Error starting Host Agent API server: {e}")
        exit(1)


if __name__ == "__main__":
    main()