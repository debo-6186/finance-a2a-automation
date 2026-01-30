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
    message_credits = Column(Integer, default=30, nullable=False)
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
    market_preference = Column(String, nullable=True)  # 'US' or 'INDIA'

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


class PortfolioAnalysis(Base):
    """Model for storing portfolio analysis data."""
    __tablename__ = "portfolio_analysis"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    portfolio_analysis = Column(Text, nullable=False)  # The raw portfolio analysis text
    investment_amount = Column(String, nullable=True)
    email_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("ConversationSession")
    user = relationship("User")


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


class UserWhitelist(Base):
    """Model for managing user access control and report generation limits."""
    __tablename__ = "user_whitelist"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    whitelisted = Column(Boolean, default=True, nullable=False)
    max_reports = Column(Integer, default=3, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


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
        # First, check if email already exists with a different user_id
        if email:
            existing_user_with_email = db.query(User).filter(User.email == email).first()
            if existing_user_with_email and existing_user_with_email.id != user_id:
                logger.error(f"User with email {email} already exists with different ID {existing_user_with_email.id}")
                raise ValueError(f"A user with email {email} already exists. Please use a different email or contact support.")

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
            if contact_number and user.contact_number != contact_number:
                user.contact_number = contact_number
                updated = True
            if country_code and user.country_code != country_code:
                user.country_code = country_code
                updated = True

            if updated:
                user.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(user)
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
                    logger.error(f"User with email {email} already exists with different ID {existing_user.id}")
                    # Raise a specific error that can be caught and returned to the frontend
                    raise ValueError(f"A user with email {email} already exists. Please use a different email or contact support.")
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


def has_session_messages(db: Session, session_id: str) -> bool:
    """Check if a session has any messages in conversation_messages table."""
    try:
        message_count = db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session_id
        ).count()
        return message_count > 0
    except SQLAlchemyError as e:
        logger.error(f"Error checking messages for session {session_id}: {e}")
        return False


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


def can_user_send_message_credits(db: Session, user_id: str) -> tuple[bool, dict|str]:
    """
    Check if user has credits remaining for free users.
    Returns (can_send: bool, error_message: dict|str)
    """
    try:
        # Get user to check if paid and check credits
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found"

        # Paid users have unlimited messages
        if user.paid_user:
            return True, ""

        # Free users: check user credits
        if user.message_credits <= 0:
            return False, {
                "message": "Maximum message limit is reached for free tier. Free users are limited to 30 messages. Add credits to continue.",
                "payment_required": True,
                "payment_url": current_config.PAYPAL_CHECKOUT_URL,
                "credits_per_package": current_config.CREDITS_PER_PURCHASE,
                "price": current_config.PAYPAL_PRICE_PER_PACKAGE,
                "currency": current_config.PAYPAL_CURRENCY
            }

        return True, ""
    except SQLAlchemyError as e:
        logger.error(f"Error checking user credits for {user_id}: {e}")
        return False, "Error checking user credits"


def decrement_user_credits(db: Session, user_id: str) -> bool:
    """
    Decrement message credits for free users.
    Returns True if successful, False otherwise.
    """
    try:
        logger.info(f"[CREDITS] decrement_user_credits called for user {user_id}")

        # Get user to check if paid
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning(f"[CREDITS] User {user_id} not found")
            return False

        logger.info(f"[CREDITS] User {user_id} - paid_user: {user.paid_user}, current credits: {user.message_credits}")

        # Skip for paid users
        if user.paid_user:
            logger.info(f"[CREDITS] User {user_id} is paid, skipping credit decrement")
            return True

        # Decrement credits for free users
        if user.message_credits > 0:
            old_credits = user.message_credits
            user.message_credits -= 1
            user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user)
            logger.info(f"[CREDITS] Successfully decremented credits for user {user_id}. Before: {old_credits}, After: {user.message_credits}")
        else:
            logger.warning(f"[CREDITS] User {user_id} has no credits remaining: {user.message_credits}")

        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[CREDITS] Error decrementing user credits for {user_id}: {e}")
        return False


def add_user_credits(db: Session, user_id: str, credits_to_add: int = 30) -> tuple[bool, int]:
    """
    Add credits to a user account.
    Returns (success: bool, new_total: int)
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return False, 0

        user.message_credits += credits_to_add
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        logger.info(f"Added {credits_to_add} credits to user {user_id}. New total: {user.message_credits}")
        return True, user.message_credits
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error adding credits to user {user_id}: {e}")
        return False, 0


def can_session_upload_file(db: Session, session_id: str, user_id: str) -> tuple[bool, str]:
    """
    Check if session can upload a file (1 per session limit for free users).
    Returns (can_upload: bool, error_message: str)
    """
    try:
        # Get user to check if paid
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found"

        # Paid users have unlimited uploads
        if user.paid_user:
            return True, ""

        # Free users: check if file already uploaded
        session = db.query(ConversationSession).filter(
            ConversationSession.id == session_id
        ).first()

        if not session:
            return False, "Session not found"

        if session.portfolio_statement_uploaded:
            return False, "Only one file upload allowed per session. Please start a new session to upload another file."

        return True, ""
    except SQLAlchemyError as e:
        logger.error(f"Error checking file upload limit for {session_id}: {e}")
        return False, "Error checking file upload limit"


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


def save_portfolio_analysis(db: Session, session_id: str, user_id: str, portfolio_analysis: str,
                            investment_amount: str = "0", email_id: str = "not_found") -> Optional[PortfolioAnalysis]:
    """Save portfolio analysis to database."""
    try:
        # Ensure user exists before saving analysis
        user = get_or_create_user(db, user_id)
        if not user:
            logger.error(f"Failed to create/get user {user_id} for portfolio analysis")
            return None

        portfolio_analysis_record = PortfolioAnalysis(
            id=f"{session_id}_{user_id}_portfolio_{datetime.utcnow().timestamp()}",
            session_id=session_id,
            user_id=user_id,
            portfolio_analysis=portfolio_analysis,
            investment_amount=investment_amount,
            email_id=email_id
        )
        db.add(portfolio_analysis_record)
        db.commit()
        db.refresh(portfolio_analysis_record)
        logger.info(f"Saved portfolio analysis for session {session_id}, user {user_id}")
        return portfolio_analysis_record
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving portfolio analysis for session {session_id}: {e}")
        return None


def get_portfolio_analysis(db: Session, session_id: str) -> Optional[PortfolioAnalysis]:
    """Get portfolio analysis for a session."""
    try:
        return db.query(PortfolioAnalysis).filter(
            PortfolioAnalysis.session_id == session_id
        ).order_by(PortfolioAnalysis.created_at.desc()).first()
    except SQLAlchemyError as e:
        logger.error(f"Error getting portfolio analysis for session {session_id}: {e}")
        return None


def get_or_create_whitelist_entry(db: Session, email: str, max_reports: int = 3, whitelisted: bool = True) -> Optional[UserWhitelist]:
    """Get or create a whitelist entry for a user."""
    try:
        # Check if whitelist entry exists
        whitelist_entry = db.query(UserWhitelist).filter(UserWhitelist.email == email).first()

        if whitelist_entry:
            logger.info(f"Found existing whitelist entry for {email}: max_reports={whitelist_entry.max_reports}, whitelisted={whitelist_entry.whitelisted}")
            return whitelist_entry
        else:
            # Create new whitelist entry with default values
            import uuid
            whitelist_entry = UserWhitelist(
                id=str(uuid.uuid4()),
                email=email,
                whitelisted=whitelisted,
                max_reports=max_reports
            )
            db.add(whitelist_entry)
            db.commit()
            db.refresh(whitelist_entry)
            logger.info(f"Created new whitelist entry for {email}: max_reports={max_reports}, whitelisted={whitelisted}")
            return whitelist_entry
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error getting/creating whitelist entry for {email}: {e}")
        return None


def count_user_valid_recommendations(db: Session, user_id: str) -> int:
    """
    Count the number of valid recommendations (with non-empty recommendation field) for a user.

    Args:
        db: Database session
        user_id: User ID to check

    Returns:
        Number of valid recommendations generated by the user
    """
    try:
        # Count stock recommendations where the recommendation JSON field is not null/empty
        # We check if the recommendation field contains actual data
        count = db.query(StockRecommendation).filter(
            StockRecommendation.user_id == user_id,
            StockRecommendation.recommendation != None
        ).count()

        logger.info(f"User {user_id} has generated {count} valid recommendations")
        return count
    except SQLAlchemyError as e:
        logger.error(f"Error counting recommendations for user {user_id}: {e}")
        return 0


def can_user_generate_report(db: Session, email: str, user_id: str) -> tuple[bool, str, int, int]:
    """
    Check if a user can generate more reports based on their whitelist status and report limit.

    Args:
        db: Database session
        email: User email address
        user_id: User ID

    Returns:
        Tuple of (can_generate, message, current_count, max_reports)
        - can_generate: Whether the user can generate a new report
        - message: Error message if limit reached, empty string otherwise
        - current_count: Number of reports already generated
        - max_reports: Maximum reports allowed for this user
    """
    try:
        # Get whitelist entry - DO NOT auto-create
        whitelist_entry = db.query(UserWhitelist).filter(UserWhitelist.email == email).first()

        # If user is not in whitelist table at all, deny access
        if not whitelist_entry:
            return False, "Your account is not authorized. Please contact support to get access.", 0, 0

        # Check if user is whitelisted
        if not whitelist_entry.whitelisted:
            return False, "Your account has been disabled. Please contact support.", 0, whitelist_entry.max_reports

        # Check if max_reports is 0 (unlimited for paid users)
        if whitelist_entry.max_reports == 0:
            logger.info(f"User {email} has unlimited reports (paid user)")
            return True, "", 0, 0

        # Count existing valid recommendations
        current_count = count_user_valid_recommendations(db, user_id)

        # Check if user has reached the limit
        if current_count >= whitelist_entry.max_reports:
            message = (
                f"You have reached the maximum number of reports ({whitelist_entry.max_reports}). "
                f"You have already generated {current_count} report(s). "
                f"Please upgrade your account or contact support for more credits."
            )
            logger.warning(f"User {email} has reached report limit: {current_count}/{whitelist_entry.max_reports}")
            return False, message, current_count, whitelist_entry.max_reports

        # User can generate more reports
        remaining = whitelist_entry.max_reports - current_count
        logger.info(f"User {email} can generate {remaining} more report(s)")
        return True, "", current_count, whitelist_entry.max_reports

    except Exception as e:
        logger.error(f"Error checking report generation limit for user {email}: {e}")
        return False, "An error occurred while checking your report limit. Please try again.", 0, 0


def update_user_max_reports(db: Session, email: str, new_max_reports: int) -> bool:
    """
    Update the maximum number of reports a user can generate.

    Args:
        db: Database session
        email: User email address
        new_max_reports: New maximum reports limit (0 = unlimited)

    Returns:
        True if successful, False otherwise
    """
    try:
        whitelist_entry = db.query(UserWhitelist).filter(UserWhitelist.email == email).first()

        if not whitelist_entry:
            # Create new entry if it doesn't exist
            import uuid
            whitelist_entry = UserWhitelist(
                id=str(uuid.uuid4()),
                email=email,
                whitelisted=True,
                max_reports=new_max_reports
            )
            db.add(whitelist_entry)
        else:
            # Update existing entry
            whitelist_entry.max_reports = new_max_reports
            whitelist_entry.updated_at = datetime.utcnow()

        db.commit()
        logger.info(f"Updated max_reports for {email} to {new_max_reports}")
        return True

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating max_reports for {email}: {e}")
        return False


def add_user_credits(db: Session, email: str, additional_credits: int) -> bool:
    """
    Add more report credits to a user's account.

    Args:
        db: Database session
        email: User email address
        additional_credits: Number of credits to add

    Returns:
        True if successful, False otherwise
    """
    try:
        whitelist_entry = get_or_create_whitelist_entry(db, email)

        if not whitelist_entry:
            logger.error(f"Failed to get/create whitelist entry for {email}")
            return False

        # Add credits to max_reports (unless it's already unlimited)
        if whitelist_entry.max_reports > 0:
            whitelist_entry.max_reports += additional_credits
            whitelist_entry.updated_at = datetime.utcnow()
            db.commit()
            logger.info(f"Added {additional_credits} credits to {email}. New max_reports: {whitelist_entry.max_reports}")
            return True
        else:
            logger.info(f"User {email} already has unlimited reports")
            return True

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error adding credits to {email}: {e}")
        return False


def set_user_whitelist_status(db: Session, email: str, whitelisted: bool) -> bool:
    """
    Update whether a user is whitelisted or not.

    Args:
        db: Database session
        email: User email address
        whitelisted: Whether to whitelist (True) or blacklist (False) the user

    Returns:
        True if successful, False otherwise
    """
    try:
        whitelist_entry = get_or_create_whitelist_entry(db, email)

        if not whitelist_entry:
            logger.error(f"Failed to get/create whitelist entry for {email}")
            return False

        whitelist_entry.whitelisted = whitelisted
        whitelist_entry.updated_at = datetime.utcnow()
        db.commit()

        status = "whitelisted" if whitelisted else "blacklisted"
        logger.info(f"User {email} is now {status}")
        return True

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating whitelist status for {email}: {e}")
        return False
