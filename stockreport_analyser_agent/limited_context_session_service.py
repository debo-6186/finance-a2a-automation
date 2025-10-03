"""
Limited Context Session Service to prevent conversation history overflow.
"""
import asyncio
from typing import Dict, Any, Optional
from google.adk.sessions import InMemorySessionService, Session
from google.genai import types
import time
import logging

logger = logging.getLogger(__name__)


class LimitedContextSessionService(InMemorySessionService):
    """
    Session service that limits conversation history to prevent context overflow.
    Keeps only the last N messages to avoid the 'Contents' field growing too large.
    """

    def _get_session_attr(self, session, attr_name):
        """Safely get an attribute from a session object or dict."""
        if hasattr(session, attr_name):
            return getattr(session, attr_name)
        elif isinstance(session, dict):
            return session.get(attr_name)
        else:
            return None
    
    def __init__(self, max_messages: int = 6):
        """
        Initialize with maximum number of messages to keep in history.
        
        Args:
            max_messages: Maximum number of messages to retain (default: 6)
                         This keeps 3 user messages + 3 model responses
        """
        super().__init__()
        self.max_messages = max_messages
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # Clean up every 5 minutes
        logger.info(f"LimitedContextSessionService initialized with max_messages={max_messages}")
    
    async def get_session(self, app_name: str, user_id: str, session_id: str) -> Optional[Session]:
        """Get session and optionally clean up old messages."""
        session = await super().get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        
        if session:
            # Trim conversation history if needed
            session = self._trim_session_history(session)
            
            # Periodic cleanup of old sessions
            current_time = time.time()
            if current_time - self.last_cleanup > self.cleanup_interval:
                await self._cleanup_old_sessions()
                self.last_cleanup = current_time
        
        return session
    
    def _trim_session_history(self, session: Session) -> Session:
        """
        Trim the session's conversation history to keep only recent messages.
        
        Args:
            session: The session to trim
            
        Returns:
            Session with trimmed history
        """
        state = self._get_session_attr(session, 'state')
        if not state or not state.get("conversation_history"):
            return session

        history = state["conversation_history"]
        if isinstance(history, list) and len(history) > self.max_messages:
            # Keep only the most recent messages
            trimmed_history = history[-self.max_messages:]
            
            logger.info(f"Trimmed session {self._get_session_attr(session, 'session_id')} history from {len(history)} to {len(trimmed_history)} messages")
            
            # Create a new session with trimmed history
            new_state = state.copy()
            new_state["conversation_history"] = trimmed_history
            
            session = Session(
                session_id=self._get_session_attr(session, 'session_id'),
                app_name=self._get_session_attr(session, 'app_name'),
                user_id=self._get_session_attr(session, 'user_id'),
                state=new_state,
                created_at=self._get_session_attr(session, 'created_at'),
                updated_at=self._get_session_attr(session, 'updated_at')
            )
        
        return session
    
    async def _cleanup_old_sessions(self):
        """Clean up very old sessions to free memory."""
        current_time = time.time()
        sessions_to_remove = []
        
        # Find sessions older than 1 hour
        for key, session in self.sessions.items():
            updated_at = self._get_session_attr(session, 'updated_at')
            if updated_at and current_time - updated_at.timestamp() > 3600:  # 1 hour
                sessions_to_remove.append(key)

        # Remove old sessions
        for key in sessions_to_remove:
            del self.sessions[key]
            
        if sessions_to_remove:
            logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions")
    
    async def update_session(self, session: Session) -> Session:
        """Update session with automatic history trimming."""
        # Trim history before updating
        trimmed_session = self._trim_session_history(session)
        return await super().update_session(trimmed_session)