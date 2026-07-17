from sqlalchemy import Column, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class AgentTask(Base):
    __tablename__ = 'agent_tasks'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    agent_subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey('agent_subscriptions.id', ondelete='CASCADE'),
        nullable=False
    )
    task_slug = Column(String, nullable=False)
    current_phase_id = Column(
        UUID(as_uuid=True),
        ForeignKey('pipeline_phases.id', ondelete='SET NULL'),
        nullable=True
    )
    # use_alter=True breaks the circular FK with ai_app_sessions:
    # ai_app_sessions.task_id → agent_tasks, and agent_tasks.current_active_session_id → ai_app_sessions
    # Alembic emits this as ALTER TABLE after both tables are created.
    current_active_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            'ai_app_sessions.id',
            use_alter=True,
            name='fk_agent_tasks_current_active_session_id',
            ondelete='SET NULL'
        ),
        nullable=True
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
