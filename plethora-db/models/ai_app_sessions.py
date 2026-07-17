import enum
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    FAILED = "failed"


class AIAppSession(Base):
    __tablename__ = 'ai_app_sessions'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    task_id = Column(UUID(as_uuid=True), ForeignKey('agent_tasks.id', ondelete='CASCADE'), nullable=False)
    ai_app_auth_id = Column(UUID(as_uuid=True), ForeignKey('ai_app_auths.id', ondelete='SET NULL'), nullable=True)
    stage = Column(Integer, nullable=False)
    chat_session_id = Column(String, nullable=True)  # conversation ID from the AI provider
    status = Column(
        Enum(SessionStatus, name='sessionstatus'),
        nullable=False,
        default=SessionStatus.ACTIVE
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
