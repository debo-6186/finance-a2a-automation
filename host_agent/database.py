"""
Database models and configuration for the Host Agent.
Handles session management, user tracking, and conversation state.
"""

import os
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import logging

# Import configuration
from config import current_config

# Set up logging
logger = logging.getLogger(__name__)

# Set up logging with absolute path
logger = logging.getLogger("host_agent_api")
logger.setLevel(logging.INFO)

# Database configuration from environment-based config
DATABASE_URL = current_config.DATABASE_URL
FREE_USER_MESSAGE_LIMIT = current_config.FREE_USER_MESSAGE_LIMIT

logger.info(f"Database configuration loaded for {current_config.ENVIRONMENT} environment")
logger.info(f"Database URL: {DATABASE_URL.split('@')[0]}@***")  # Log without exposing credentials

# Create SQLAlchemy engine with SSL support for RDS (production only)
connect_args = {}
if current_config.is_production() and "rds.amazonaws.com" in DATABASE_URL:
    connect_args = {"sslmode": "require"}
    logger.info("Using SSL connection for RDS")

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


class User(Base):
    """User model for tracking user information and subscription status."""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=True)
    contact_number = Column(String, nullable=True)
    country_code = Column(String, nullable=True, default='+1')
    paid_user = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    sessions = relationship("ConversationSession", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("ConversationMessage", back_populates="user", cascade="all, delete-orphan")


class ConversationSession(Base):
    """Session model for tracking conversation state across agents."""
    __tablename__ = "conversation_sessions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    portfolio_statement_uploaded = Column(Boolean, default=False, nullable=False)
    input_format = Column(String, nullable=True)  # 'pdf', 'image', 'text', or None

    # Relationships
    user = relationship("User", back_populates="sessions")
    messages = relationship("ConversationMessage", back_populates="session", cascade="all, delete-orphan")
    agent_states = relationship("AgentState", back_populates="session", cascade="all, delete-orphan")


class ConversationMessage(Base):
    """Message model for tracking all conversation messages."""
    __tablename__ = "conversation_messages"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    message_type = Column(String, nullable=False)  # 'user', 'agent', 'system'
    content = Column(Text, nullable=False)
    agent_name = Column(String, nullable=True)  # Which agent processed this message
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    session = relationship("ConversationSession", back_populates="messages")
    user = relationship("User", back_populates="messages")


class AgentState(Base):
    """State model for tracking agent-specific conversation state."""
    __tablename__ = "agent_states"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    agent_name = Column(String, nullable=False, index=True)
    state_data = Column(Text, nullable=False)  # JSON string of agent state
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("ConversationSession", back_populates="agent_states")


class StockRecommendation(Base):
    """Model for storing stock analysis recommendations."""
    __tablename__ = "stock_recommendations"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    recommendation = Column(JSON, nullable=False)  # JSON object containing the recommendation data
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("ConversationSession")
    user = relationship("User")


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except SQLAlchemyError as e:
        logger.error(f"Error creating database tables: {e}")
        raise


def create_user(db: Session, user_id: str, email: Optional[str] = None, name: Optional[str] = None, 
                contact_number: Optional[str] = None, country_code: Optional[str] = '+1', 
                paid_user: bool = False) -> User:
    """Create a new user."""
    try:
        user = User(
            id=user_id,
            email=email,
            name=name,
            contact_number=contact_number,
            country_code=country_code,
            paid_user=paid_user
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created user: {user_id} (paid: {paid_user})")
        return user
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating user {user_id}: {e}")
        raise


def get_or_create_user(db: Session, user_id: str, email: Optional[str] = None, name: Optional[str] = None,
                      contact_number: Optional[str] = None, country_code: Optional[str] = '+1',
                      paid_user: bool = False) -> User:
    """Get existing user or create new one."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            # Update fields if they changed
            updated = False
            if user.paid_user != paid_user:
                user.paid_user = paid_user
                updated = True
            if email and user.email != email:
                user.email = email
                updated = True
            if name and user.name != name:
                user.name = name
                updated = True

            if updated:
                db.commit()
                logger.info(f"Updated user {user_id}")
            return user
        else:
            return create_user(db, user_id, email, name, contact_number, country_code, paid_user)
    except IntegrityError as e:
        # Handle duplicate email constraint violation
        db.rollback()
        logger.warning(f"IntegrityError for user {user_id}: {e}. Attempting to find existing user by email.")

        # Try to find user by email if provided
        if email:
            existing_user = db.query(User).filter(User.email == email).first()
            if existing_user:
                # Check if it's a different user_id
                if existing_user.id != user_id:
                    logger.warning(f"Found user with email {email} but different ID. Updating ID from {existing_user.id} to {user_id}")
                    # Update the user's ID to match the Firebase UID
                    existing_user.id = user_id
                    existing_user.paid_user = paid_user
                    if name:
                        existing_user.name = name
                    try:
                        db.commit()
                        db.refresh(existing_user)
                        logger.info(f"Updated user ID to {user_id}")
                        return existing_user
                    except Exception as update_error:
                        db.rollback()
                        logger.error(f"Failed to update user ID: {update_error}")
                        raise
                else:
                    logger.info(f"Found existing user with email {email} and matching ID {existing_user.id}")
                    return existing_user

        # If we still can't find the user, try by ID one more time
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user

        logger.error(f"Could not create or find user {user_id} with email {email}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error getting/creating user {user_id}: {e}")
        raise


def create_session(db: Session, session_id: str, user_id: str) -> ConversationSession:
    """Create a new conversation session."""
    try:
        session = ConversationSession(
            id=session_id,
            user_id=user_id
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info(f"Created session: {session_id} for user: {user_id}")
        return session
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating session {session_id}: {e}")
        raise


def get_session(db: Session, session_id: str) -> Optional[ConversationSession]:
    """Get existing session by ID."""
    try:
        return db.query(ConversationSession).filter(
            ConversationSession.id == session_id,
            ConversationSession.is_active == True
        ).first()
    except SQLAlchemyError as e:
        logger.error(f"Error getting session {session_id}: {e}")
        return None


def add_message(db: Session, session_id: str, user_id: str, message_type: str, content: str, agent_name: Optional[str] = None) -> ConversationMessage:
    """Add a new message to the conversation."""
    try:
        message = ConversationMessage(
            id=f"{session_id}_{datetime.utcnow().timestamp()}",
            session_id=session_id,
            user_id=user_id,
            message_type=message_type,
            content=content,
            agent_name=agent_name
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        logger.info(f"Added {message_type} message to session {session_id}")
        return message
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error adding message to session {session_id}: {e}")
        raise


def get_conversation_history(db: Session, session_id: str, limit: int = 50):
    """Get conversation history for a session in chronological order."""
    try:
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session_id
        ).order_by(ConversationMessage.timestamp.asc()).limit(limit).all()
        return messages
    except SQLAlchemyError as e:
        logger.error(f"Error getting conversation history for session {session_id}: {e}")
        return []


def get_user_message_count(db: Session, user_id: str) -> int:
    """Get the total number of user messages for a user."""
    try:
        return db.query(ConversationMessage).filter(
            ConversationMessage.user_id == user_id,
            ConversationMessage.message_type == 'user'
        ).count()
    except SQLAlchemyError as e:
        logger.error(f"Error getting message count for user {user_id}: {e}")
        return 0


def can_user_send_message(db: Session, user_id: str) -> bool:
    """Check if user can send more messages based on paid status and message count."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        if user.paid_user:
            return True  # Paid users have unlimited messages
        
        # Free users limited by environment variable
        message_count = get_user_message_count(db, user_id)
        logger.info(f"Number of messages: {message_count}")
        return message_count < FREE_USER_MESSAGE_LIMIT
    except SQLAlchemyError as e:
        logger.error(f"Error checking user message limit for {user_id}: {e}")
        return False


def update_agent_state(db: Session, session_id: str, agent_name: str, state_data: str) -> AgentState:
    """Update or create agent state for a session."""
    try:
        # Try to find existing state
        existing_state = db.query(AgentState).filter(
            AgentState.session_id == session_id,
            AgentState.agent_name == agent_name
        ).first()
        
        if existing_state:
            existing_state.state_data = state_data
            existing_state.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_state)
            logger.info(f"Updated agent state for {agent_name} in session {session_id}")
            return existing_state
        else:
            # Create new state
            new_state = AgentState(
                id=f"{session_id}_{agent_name}_{datetime.utcnow().timestamp()}",
                session_id=session_id,
                agent_name=agent_name,
                state_data=state_data
            )
            db.add(new_state)
            db.commit()
            db.refresh(new_state)
            logger.info(f"Created agent state for {agent_name} in session {session_id}")
            return new_state
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating agent state for {agent_name} in session {session_id}: {e}")
        raise


def get_agent_state(db: Session, session_id: str, agent_name: str) -> Optional[AgentState]:
    """Get agent state for a session."""
    try:
        return db.query(AgentState).filter(
            AgentState.session_id == session_id,
            AgentState.agent_name == agent_name
        ).first()
    except SQLAlchemyError as e:
        logger.error(f"Error getting agent state for {agent_name} in session {session_id}: {e}")
        return None


def mark_portfolio_statement_uploaded(db: Session, session_id: str, input_format: str = 'pdf') -> bool:
    """Mark portfolio statement as uploaded for a session.

    Args:
        db: Database session
        session_id: Session ID
        input_format: Format of input - 'pdf', 'image', or 'text'
    """
    try:
        session = db.query(ConversationSession).filter(
            ConversationSession.id == session_id,
            ConversationSession.is_active == True
        ).first()

        if session:
            session.portfolio_statement_uploaded = True
            session.input_format = input_format
            session.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(session)
            logger.info(f"Marked portfolio statement as uploaded ({input_format}) for session {session_id}")
            return True
        else:
            logger.warning(f"Session {session_id} not found or inactive")
            return False
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error marking portfolio statement as uploaded for session {session_id}: {e}")
        return False


def save_stock_recommendation(db: Session, session_id: str, user_id: str, recommendation: dict) -> Optional[StockRecommendation]:
    """Save stock recommendation to database."""
    try:
        # Ensure user exists before saving recommendation
        user = get_or_create_user(db, user_id)
        if not user:
            logger.error(f"Failed to create/get user {user_id} for stock recommendation")
            return None

        stock_recommendation = StockRecommendation(
            id=f"{session_id}_{user_id}_{datetime.utcnow().timestamp()}",
            session_id=session_id,
            user_id=user_id,
            recommendation=recommendation
        )
        db.add(stock_recommendation)
        db.commit()
        db.refresh(stock_recommendation)
        logger.info(f"Saved stock recommendation for session {session_id}, user {user_id}")
        return stock_recommendation
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving stock recommendation for session {session_id}: {e}")
        return None


def get_stock_recommendation(db: Session, session_id: str) -> Optional[StockRecommendation]:
    """Get stock recommendation for a session."""
    try:
        return db.query(StockRecommendation).filter(
            StockRecommendation.session_id == session_id
        ).order_by(StockRecommendation.created_at.desc()).first()
    except SQLAlchemyError as e:
        logger.error(f"Error getting stock recommendation for session {session_id}: {e}")
        return None


def get_user_stock_recommendations(db: Session, user_id: str) -> list:
    """Get all stock recommendations for a user."""
    try:
        return db.query(StockRecommendation).filter(
            StockRecommendation.user_id == user_id
        ).order_by(StockRecommendation.created_at.desc()).all()
    except SQLAlchemyError as e:
        logger.error(f"Error getting stock recommendations for user {user_id}: {e}")
        return []
