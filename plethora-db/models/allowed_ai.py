# plethora-db/models/allowed_ai.py
from sqlalchemy import Column, String, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base

class AllowedAI(Base):
    __tablename__ = 'allowed_ai_models'
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    agent_slug_id = Column(UUID(as_uuid=True), ForeignKey('agent_slugs.id', ondelete='CASCADE'), nullable=False)
    ai_name = Column(String, nullable=False)             # e.g., 'Claude Code', 'Codex'
    custom_agent_url = Column(String, nullable=True)     # Optional