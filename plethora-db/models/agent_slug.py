# plethora-db/models/agent_slug.py
from sqlalchemy import Column, String, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base

class AgentSlug(Base):
    __tablename__ = 'agent_slugs'
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    slug_name = Column(String, unique=True, nullable=False)  # e.g., 'github'
    agent_type = Column(String, nullable=False)              # e.g., 'Coding Agent'