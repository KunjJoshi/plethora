import os
from sqlalchemy.orm import Session

from models.agent_slug import AgentSlug
from models.pipeline_phases import PipelinePhase
from models.agent_subscriptions import AgentSubscription, SubscriptionStatus
from models.agent_tasks import AgentTask
from models.ai_app_sessions import AIAppSession, SessionStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _workspace_path(subscription_id) -> str:
    return os.path.expanduser(f"~/.plethora/workspaces/{subscription_id}")


def _substitute_prompt(prompt: str, workspace_path: str, task_name: str, task_description: str, **kwargs) -> str:
    result = prompt.replace("{workspace_path}", workspace_path)
    result = result.replace("{task_name}", task_name)
    result = result.replace("{task_description}", task_description)
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def _get_phase(db: Session, agent_slug_id, phase_number: int) -> PipelinePhase | None:
    return db.query(PipelinePhase).filter(
        PipelinePhase.agent_slug_id == agent_slug_id,
        PipelinePhase.phase_number == phase_number,
    ).first()


def _assert_task_owned_by_user(task: AgentTask, db: Session, user_id: str) -> AgentSubscription:
    subscription = db.query(AgentSubscription).filter(
        AgentSubscription.id == task.agent_subscription_id,
        AgentSubscription.user_id == user_id,
    ).first()
    if not subscription:
        raise ValueError("Task not found or access denied")
    return subscription


# ---------------------------------------------------------------------------
# Check active subscription
# ---------------------------------------------------------------------------

def check_active_subscription(
    db: Session,
    user_id: str,
    agent_slug_name: str,
) -> AgentSubscription | None:
    agent = db.query(AgentSlug).filter(AgentSlug.slug_name == agent_slug_name).first()
    if not agent:
        return None
    return db.query(AgentSubscription).filter(
        AgentSubscription.user_id == user_id,
        AgentSubscription.agent_slug_id == agent.id,
        AgentSubscription.status == SubscriptionStatus.ACTIVE,
    ).first()


# ---------------------------------------------------------------------------
# Initiate task
# ---------------------------------------------------------------------------

def initiate_task(
    db: Session,
    user_id: str,
    subscription_id: str,
    task_slug: str,
    task_name: str,
    task_description: str,
    **kwargs,
) -> tuple[AgentTask, PipelinePhase, str]:
    subscription = db.query(AgentSubscription).filter(
        AgentSubscription.id == subscription_id,
        AgentSubscription.user_id == user_id,
        AgentSubscription.status == SubscriptionStatus.ACTIVE,
    ).first()
    if not subscription:
        raise ValueError("No active subscription found")

    phase = _get_phase(db, subscription.agent_slug_id, 1)
    if not phase:
        raise ValueError("Phase 1 not defined for this agent")

    # Reuse the AI app auth from the init session if available
    init_task = db.query(AgentTask).filter(
        AgentTask.agent_subscription_id == subscription.id,
        AgentTask.task_slug == "init",
    ).first()
    ai_app_auth_id = None
    if init_task and init_task.current_active_session_id:
        init_session = db.query(AIAppSession).filter(
            AIAppSession.id == init_task.current_active_session_id
        ).first()
        if init_session:
            ai_app_auth_id = init_session.ai_app_auth_id

    task = AgentTask(
        agent_subscription_id=subscription.id,
        task_slug=task_slug,
        task_name=task_name,
        task_description=task_description,
        current_phase_id=phase.id,
    )
    db.add(task)
    db.flush()

    session = AIAppSession(
        task_id=task.id,
        ai_app_auth_id=ai_app_auth_id,
        stage=phase.phase_number,
        status=SessionStatus.ACTIVE,
    )
    db.add(session)
    db.flush()

    task.current_active_session_id = session.id
    db.commit()

    workspace = _workspace_path(subscription.id)
    prompt = _substitute_prompt(
        phase.prompt,
        workspace_path=workspace,
        task_name=task_name,
        task_description=task_description,
        **kwargs,
    )
    return task, phase, prompt


# ---------------------------------------------------------------------------
# Approve and move to next phase
# ---------------------------------------------------------------------------

def approve_and_move_on(
    db: Session,
    user_id: str,
    task_id: str,
) -> tuple[AgentTask, PipelinePhase | None, str | None]:
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise ValueError("Task not found")

    subscription = _assert_task_owned_by_user(task, db, user_id)

    current_phase = db.query(PipelinePhase).filter(
        PipelinePhase.id == task.current_phase_id
    ).first()
    if not current_phase:
        raise ValueError("Current phase not found on task")

    # Mark current session APPROVED
    if task.current_active_session_id:
        current_session = db.query(AIAppSession).filter(
            AIAppSession.id == task.current_active_session_id
        ).first()
        if current_session:
            current_session.status = SessionStatus.APPROVED
            ai_app_auth_id = current_session.ai_app_auth_id
        else:
            ai_app_auth_id = None
    else:
        ai_app_auth_id = None

    # Find next phase
    next_phase = _get_phase(db, subscription.agent_slug_id, current_phase.phase_number + 1)

    if not next_phase:
        task.current_active_session_id = None
        db.commit()
        return task, None, None

    # Open new session for next phase
    new_session = AIAppSession(
        task_id=task.id,
        ai_app_auth_id=ai_app_auth_id,
        stage=next_phase.phase_number,
        status=SessionStatus.ACTIVE,
    )
    db.add(new_session)
    db.flush()

    task.current_phase_id = next_phase.id
    task.current_active_session_id = new_session.id
    db.commit()

    workspace = _workspace_path(subscription.id)
    prompt = _substitute_prompt(
        next_phase.prompt,
        workspace_path=workspace,
        task_name=task.task_name or task.task_slug,
        task_description=task.task_description or "",
    )
    return task, next_phase, prompt


# ---------------------------------------------------------------------------
# Rollback one phase
# ---------------------------------------------------------------------------

def rollback_phase(
    db: Session,
    user_id: str,
    task_id: str,
) -> tuple[AgentTask, PipelinePhase, str | None]:
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise ValueError("Task not found")

    subscription = _assert_task_owned_by_user(task, db, user_id)

    current_phase = db.query(PipelinePhase).filter(
        PipelinePhase.id == task.current_phase_id
    ).first()
    if not current_phase:
        raise ValueError("Current phase not found on task")
    if current_phase.phase_number <= 1:
        raise ValueError("Already at Phase 1, cannot go back further")

    # Halt current session
    if task.current_active_session_id:
        current_session = db.query(AIAppSession).filter(
            AIAppSession.id == task.current_active_session_id
        ).first()
        if current_session:
            current_session.status = SessionStatus.HALTED

    # Find the most recent APPROVED session for the previous phase
    prev_phase_number = current_phase.phase_number - 1
    prev_session = (
        db.query(AIAppSession)
        .filter(
            AIAppSession.task_id == task.id,
            AIAppSession.stage == prev_phase_number,
            AIAppSession.status == SessionStatus.APPROVED,
        )
        .order_by(AIAppSession.created_at.desc())
        .first()
    )

    if not prev_session:
        raise ValueError(f"No approved session found for Phase {prev_phase_number}")

    prev_session.status = SessionStatus.ACTIVE

    prev_phase = _get_phase(db, subscription.agent_slug_id, prev_phase_number)
    if not prev_phase:
        raise ValueError(f"Phase {prev_phase_number} definition not found")

    task.current_phase_id = prev_phase.id
    task.current_active_session_id = prev_session.id
    db.commit()

    return task, prev_phase, prev_session.chat_session_id
