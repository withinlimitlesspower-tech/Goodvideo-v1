"""
Database models and setup for AI Video Generator chat history.
Uses SQLAlchemy with SQLite for persistent storage of conversations.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    JSON,
    Float,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    relationship,
    scoped_session,
    Session,
)
from sqlalchemy.exc import SQLAlchemyError, OperationalError

# Configure logging
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(DATABASE_DIR, 'chat_history.db')}",
)

# Ensure database directory exists
os.makedirs(DATABASE_DIR, exist_ok=True)

# Create SQLAlchemy engine with connection pooling for SQLite
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,  # Set to True for SQL debugging
)

# Session factory
session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
SessionLocal = scoped_session(session_factory)

# Declarative base
Base = declarative_base()


class ChatSession(Base):
    """
    Represents a chat conversation session.
    Each session contains multiple messages and associated media.
    """

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(255), default="New Conversation")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, nullable=True)  # Flexible metadata storage

    # Relationships
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, session_id='{self.session_id}', title='{self.title}')>"

    def to_dict(self) -> dict:
        """Convert session to dictionary for API responses."""
        return {
            "id": self.session_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active,
            "message_count": self.messages.count() if self.messages else 0,
        }


class ChatMessage(Base):
    """
    Represents a single message in a chat conversation.
    Can be either user input or AI response with associated media.
    """

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_edited = Column(Boolean, default=False, nullable=False)
    token_count = Column(Integer, nullable=True)  # For tracking usage

    # Media generation details
    video_url = Column(Text, nullable=True)  # URL to generated video
    thumbnail_url = Column(Text, nullable=True)  # URL to video thumbnail
    audio_url = Column(Text, nullable=True)  # URL to generated audio
    media_metadata = Column(JSON, nullable=True)  # Flexible media metadata

    # Processing status
    processing_status = Column(
        String(20), default="pending", nullable=False
    )  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)  # Error details if failed
    processing_time_ms = Column(Float, nullable=True)  # Processing duration

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role='{self.role}', session='{self.session_id}')>"

    def to_dict(self) -> dict:
        """Convert message to dictionary for API responses."""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_edited": self.is_edited,
            "video_url": self.video_url,
            "thumbnail_url": self.thumbnail_url,
            "audio_url": self.audio_url,
            "media_metadata": self.media_metadata,
            "processing_status": self.processing_status,
            "error_message": self.error_message,
            "token_count": self.token_count,
            "processing_time_ms": self.processing_time_ms,
        }


class MediaAsset(Base):
    """
    Tracks individual media assets used in video generation.
    Useful for caching and reuse of fetched media.
    """

    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(
        Integer,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_type = Column(String(20), nullable=False)  # 'video', 'image', 'audio'
    source = Column(String(50), nullable=False)  # 'pixabay', 'elevenlabs', etc.
    source_url = Column(Text, nullable=False)  # Original URL from source
    local_path = Column(Text, nullable=True)  # Local cached file path
    metadata_json = Column(JSON, nullable=True)  # Source-specific metadata
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    file_size_bytes = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<MediaAsset(id={self.id}, type='{self.asset_type}', source='{self.source}')>"


def init_database() -> None:
    """
    Initialize the database by creating all tables.
    Should be called once at application startup.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except SQLAlchemyError as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def get_session() -> Session:
    """
    Get a new database session.
    Use as a context manager or call close() when done.

    Returns:
        Session: SQLAlchemy session object
    """
    try:
        session = SessionLocal()
        return session
    except SQLAlchemyError as e:
        logger.error(f"Failed to create database session: {e}")
        raise


def close_session(session: Session) -> None:
    """
    Close a database session safely.

    Args:
        session: SQLAlchemy session to close
    """
    try:
        session.close()
    except SQLAlchemyError as e:
        logger.error(f"Error closing database session: {e}")


def get_or_create_session(session_id: str, title: str = "New Conversation") -> ChatSession:
    """
    Get an existing session or create a new one.

    Args:
        session_id: Unique identifier for the session
        title: Optional title for new sessions

    Returns:
        ChatSession: The existing or newly created session
    """
    db = get_session()
    try:
        chat_session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .first()
        )

        if not chat_session:
            chat_session = ChatSession(
                session_id=session_id,
                title=title,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(chat_session)
            db.commit()
            db.refresh(chat_session)
            logger.info(f"Created new chat session: {session_id}")

        return chat_session
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error getting/creating session {session_id}: {e}")
        raise
    finally:
        close_session(db)


def add_message(
    session_id: str,
    role: str,
    content: str,
    video_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    audio_url: Optional[str] = None,
    media_metadata: Optional[dict] = None,
    token_count: Optional[int] = None,
) -> ChatMessage:
    """
    Add a new message to a chat session.

    Args:
        session_id: Session identifier
        role: 'user' or 'assistant'
        content: Message text content
        video_url: Optional URL to generated video
        thumbnail_url: Optional URL to video thumbnail
        audio_url: Optional URL to generated audio
        media_metadata: Optional metadata dictionary
        token_count: Optional token count for usage tracking

    Returns:
        ChatMessage: The newly created message
    """
    db = get_session()
    try:
        # Ensure session exists
        chat_session = get_or_create_session(session_id)

        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            video_url=video_url,
            thumbnail_url=thumbnail_url,
            audio_url=audio_url,
            media_metadata=media_metadata,
            token_count=token_count,
            created_at=datetime.now(timezone.utc),
        )

        db.add(message)

        # Update session timestamp
        chat_session.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(message)
        logger.info(f"Added {role} message to session {session_id}")

        return message
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error adding message to session {session_id}: {e}")
        raise
    finally:
        close_session(db)


def get_session_messages(
    session_id: str, limit: int = 50, offset: int = 0
) -> List[ChatMessage]:
    """
    Retrieve messages for a given session with pagination.

    Args:
        session_id: Session identifier
        limit: Maximum number of messages to return
        offset: Number of messages to skip

    Returns:
        List[ChatMessage]: List of messages in chronological order
    """
    db = get_session()
    try:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return messages
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving messages for session {session_id}: {e}")
        raise
    finally:
        close_session(db)


def get_all_sessions(limit: int = 100, offset: int = 0) -> List[ChatSession]:
    """
    Retrieve all chat sessions with pagination.

    Args:
        limit: Maximum number of sessions to return
        offset: Number of sessions to skip

    Returns:
        List[ChatSession]: List of sessions ordered by update time
    """
    db = get_session()
    try:
        sessions = (
            db.query(ChatSession)
            .order_by(ChatSession.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return sessions
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving sessions: {e}")
        raise
    finally:
        close_session(db)


def delete_session(session_id: str) -> bool:
    """
    Delete a chat session and all its messages.

    Args:
        session_id: Session identifier to delete

    Returns:
        bool: True if deleted, False if not found
    """
    db = get_session()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .first()
        )

        if session:
            db.delete(session)
            db.commit()
            logger.info(f"Deleted session {session_id}")
            return True

        logger.warning(f"Session {session_id} not found for deletion")
        return False
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error deleting session {session_id}: {e}")
        raise
    finally:
        close_session(db)


def update_message_status(
    message_id: int,
    status: str,
    error_message: Optional[str] = None,
    processing_time_ms: Optional[float] = None,
) -> bool:
    """
    Update the processing status of a message.

    Args:
        message_id: Message identifier
        status: New processing status
        error_message: Optional error details
        processing_time_ms: Optional processing duration

    Returns:
        bool: True if updated, False if not found
    """
    db = get_session()
    try:
        message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()

        if message:
            message.processing_status = status
            if error_message:
                message.error_message = error_message
            if processing_time_ms is not None:
                message.processing_time_ms = processing_time_ms
            db.commit()
            logger.info(f"Updated message {message_id} status to {status}")
            return True

        logger.warning(f"Message {message_id} not found for status update")
        return False
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating message {message_id} status: {e}")
        raise
    finally:
        close_session(db)


# Initialize database when module is imported
try:
    init_database()
except Exception as e:
    logger.warning(f"Database initialization deferred: {e}")