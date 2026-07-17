from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from database import Base


class AIAppAuth(Base):
    __tablename__ = 'ai_app_auths'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    ai_name = Column(String, nullable=False)    # 'claude_code', 'openai_codex' — matches allowed_ai_models.ai_name
    auth_type = Column(String, nullable=False)  # 'api_key' or 'oauth'
    access_token = Column(Text, nullable=False) # encrypted at app layer
    refresh_token = Column(Text, nullable=True) # encrypted at app layer
    expires_at = Column(DateTime, nullable=True)
    meta = Column(JSONB, nullable=True)         # e.g. {"org_id": "..."} for OpenAI
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'ai_name', name='uq_ai_app_auths_user_ai_name'),
    )
