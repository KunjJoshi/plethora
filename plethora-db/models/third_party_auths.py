import enum
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from database import Base


class ThirdPartyAuth(Base):
    __tablename__ = 'third_party_auths'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    provider = Column(String, nullable=False)          # 'github', 'linkedin', 'jira'
    access_token = Column(Text, nullable=False)        # encrypted at app layer
    refresh_token = Column(Text, nullable=True)        # encrypted at app layer
    token_type = Column(String, server_default='Bearer')
    scope = Column(String, nullable=True)              # e.g. 'repo read:user'
    expires_at = Column(DateTime, nullable=True)       # NULL = non-expiring token
    provider_user_id = Column(String, nullable=True)   # user's ID on the provider
    provider_username = Column(String, nullable=True)  # e.g. 'kunjjoshi' on GitHub
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'provider', name='uq_third_party_auths_user_provider'),
    )
