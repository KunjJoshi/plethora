import enum
from sqlalchemy import Column, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class SubscriptionStatus(str, enum.Enum):
    PRE_INIT = "pre_init"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    EXPIRED = "expired"


class AgentSubscription(Base):
    __tablename__ = 'agent_subscriptions'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    agent_slug_id = Column(UUID(as_uuid=True), ForeignKey('agent_slugs.id', ondelete='CASCADE'), nullable=False)
    status = Column(
        Enum(SubscriptionStatus, name='subscriptionstatus'),
        nullable=False,
        default=SubscriptionStatus.PRE_INIT
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
