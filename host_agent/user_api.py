"""
User-level API endpoints for the Host Agent.
This module provides user management and profile functionality.
"""

from typing import Optional
from datetime import datetime, timedelta
import logging

from fastapi import HTTPException
from pydantic import BaseModel

from database import (
    get_db, get_user_message_count,
    can_user_send_message, User, ConversationSession, ConversationMessage,
    get_or_create_user
)

# Set up logging
logger = logging.getLogger(__name__)


class UserProfile(BaseModel):
    """User profile model."""
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    contact_number: Optional[str] = None
    country_code: Optional[str] = None
    paid_user: bool = False
    created_at: datetime
    updated_at: datetime
    total_sessions: int
    total_messages: int
    can_send_messages: bool
    message_limit: str


class UserStats(BaseModel):
    """User statistics model."""
    user_id: str
    total_messages: int
    messages_last_24h: int
    messages_last_7d: int
    messages_last_30d: int
    total_sessions: int
    active_sessions: int
    avg_messages_per_session: float
    first_message_date: Optional[datetime]
    last_message_date: Optional[datetime]


def get_user_profile(user_id: str, email: Optional[str] = None) -> UserProfile:
    """Get complete user profile information."""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.id == user_id).first()

        # If not found by ID, try by email as fallback (for users with changed Firebase UIDs)
        if not user and email:
            user = db.query(User).filter(User.email == email).first()
            if user:
                logger.info(f"User not found by ID {user_id}, but found by email {email}. User ID in DB: {user.id}")

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get user's sessions
        sessions = db.query(ConversationSession).filter(
            ConversationSession.user_id == user_id
        ).all()

        # Get total message count
        message_count = get_user_message_count(db, user_id)

        profile = UserProfile(
            user_id=user_id,
            email=user.email,
            name=user.name,
            contact_number=user.contact_number,
            country_code=user.country_code,
            paid_user=user.paid_user,
            created_at=user.created_at,
            updated_at=user.updated_at,
            total_sessions=len(sessions),
            total_messages=message_count,
            can_send_messages=can_user_send_message(db, user_id),
            message_limit="unlimited" if user.paid_user else "19 messages"
        )

        db.close()
        return profile

    except HTTPException:
        db.close()
        raise
    except Exception as e:
        db.close()
        raise HTTPException(status_code=500, detail=f"Error getting user profile: {str(e)}")


def get_user_statistics(user_id: str) -> UserStats:
    """Get detailed user statistics."""
    try:
        db = next(get_db())
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        now = datetime.utcnow()
        
        # Get all user messages
        all_messages = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == user_id,
            ConversationMessage.message_type == "user"
        ).order_by(ConversationMessage.timestamp).all()
        
        # Calculate time-based message counts
        messages_last_24h = len([
            m for m in all_messages 
            if m.timestamp > now - timedelta(hours=24)
        ])
        
        messages_last_7d = len([
            m for m in all_messages 
            if m.timestamp > now - timedelta(days=7)
        ])
        
        messages_last_30d = len([
            m for m in all_messages 
            if m.timestamp > now - timedelta(days=30)
        ])
        
        # Get session statistics
        all_sessions = db.query(ConversationSession).filter(
            ConversationSession.user_id == user_id
        ).all()
        
        active_sessions = len([s for s in all_sessions if s.is_active])
        
        # Calculate average messages per session
        avg_messages_per_session = (
            len(all_messages) / len(all_sessions) if all_sessions else 0
        )
        
        # Get first and last message dates
        first_message_date = all_messages[0].timestamp if all_messages else None
        last_message_date = all_messages[-1].timestamp if all_messages else None
        
        return UserStats(
            user_id=user_id,
            total_messages=len(all_messages),
            messages_last_24h=messages_last_24h,
            messages_last_7d=messages_last_7d,
            messages_last_30d=messages_last_30d,
            total_sessions=len(all_sessions),
            active_sessions=active_sessions,
            avg_messages_per_session=round(avg_messages_per_session, 2),
            first_message_date=first_message_date,
            last_message_date=last_message_date
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user statistics: {str(e)}")


def delete_user_account(user_id: str) -> dict:
    """Delete user account and all associated data."""
    try:
        db = next(get_db())
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Delete user messages
        messages_deleted = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == user_id
        ).delete()
        
        # Delete user sessions
        sessions_deleted = db.query(ConversationSession).filter(
            ConversationSession.user_id == user_id
        ).delete()
        
        # Delete user
        db.delete(user)
        
        db.commit()
        
        return {
            "message": "User account deleted successfully",
            "user_id": user_id,
            "sessions_deleted": sessions_deleted,
            "messages_deleted": messages_deleted
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting user account: {str(e)}")


def get_user_sessions_summary(user_id: str, limit: int = 10) -> dict:
    """Get summary of user's recent sessions."""
    try:
        db = next(get_db())
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        sessions = db.query(ConversationSession).filter(
            ConversationSession.user_id == user_id
        ).order_by(ConversationSession.updated_at.desc()).limit(limit).all()
        
        session_summaries = []
        for session in sessions:
            # Get first and last messages for context
            messages = db.query(ConversationMessage).filter(
                ConversationMessage.session_id == session.id
            ).order_by(ConversationMessage.timestamp).all()
            
            first_user_message = next(
                (m for m in messages if m.message_type == "user"), None
            )
            last_message = messages[-1] if messages else None
            
            session_summaries.append({
                "session_id": session.id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "is_active": session.is_active,
                "message_count": len(messages),
                "first_message": first_user_message.content[:100] + "..." if first_user_message and len(first_user_message.content) > 100 else (first_user_message.content if first_user_message else None),
                "last_activity": last_message.timestamp.isoformat() if last_message else None
            })
        
        return {
            "user_id": user_id,
            "recent_sessions": session_summaries,
            "total_shown": len(session_summaries)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user sessions summary: {str(e)}")


def upgrade_user_to_paid(user_id: str) -> UserProfile:
    """Upgrade user to paid status."""
    try:
        db = next(get_db())
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if user.paid_user:
            raise HTTPException(status_code=400, detail="User is already a paid user")
        
        user.paid_user = True
        user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        return get_user_profile(user_id)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error upgrading user to paid: {str(e)}")


def downgrade_user_to_free(user_id: str) -> UserProfile:
    """Downgrade user to free status."""
    try:
        db = next(get_db())
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.paid_user:
            raise HTTPException(status_code=400, detail="User is already a free user")

        user.paid_user = False
        user.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(user)

        return get_user_profile(user_id)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error downgrading user to free: {str(e)}")


class UserUpdateRequest(BaseModel):
    """User update request model."""
    email: Optional[str] = None
    name: Optional[str] = None
    contact_number: Optional[str] = None
    country_code: Optional[str] = None
    paid_user: Optional[bool] = None


def update_user_profile(user_id: str, update_data: UserUpdateRequest) -> UserProfile:
    """Update user profile information."""
    try:
        db = next(get_db())

        # Check if user exists
        existing_user = db.query(User).filter(User.id == user_id).first()

        # If user doesn't exist and we're trying to create them, email is required
        if not existing_user and not update_data.email:
            raise HTTPException(
                status_code=400,
                detail="Email is required when creating a new user profile"
            )

        # Try to get or create user
        try:
            user = get_or_create_user(
                db,
                user_id,
                email=update_data.email,
                name=update_data.name,
                contact_number=update_data.contact_number,
                country_code=update_data.country_code,
                paid_user=update_data.paid_user if update_data.paid_user is not None else False
            )
        except ValueError as e:
            # Re-raise ValueError for duplicate email
            raise HTTPException(status_code=409, detail=str(e))

        db.close()
        return get_user_profile(user_id, update_data.email)

    except HTTPException:
        raise
    except Exception as e:
        if db:
            db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating user profile: {str(e)}")