import os
import secrets
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy.orm import Session
from dotenv import load_dotenv

from models.agent_slug import AgentSlug
from models.allowed_ai import AllowedAI
from models.pipeline_phases import PipelinePhase
from models.agent_subscriptions import AgentSubscription, SubscriptionStatus
from models.agent_tasks import AgentTask
from models.ai_app_sessions import AIAppSession, SessionStatus
from models.third_party_auths import ThirdPartyAuth
from models.ai_app_auths import AIAppAuth
from auth.encryption import encrypt_token

load_dotenv()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "plethora://github/callback")


# ---------------------------------------------------------------------------
# Subscribe
# ---------------------------------------------------------------------------

def create_subscription(db: Session, user_id: str, agent_slug_name: str) -> AgentSubscription:
    agent = db.query(AgentSlug).filter(AgentSlug.slug_name == agent_slug_name).first()
    if not agent:
        raise ValueError(f"Agent '{agent_slug_name}' not found")

    state = secrets.token_urlsafe(32)

    subscription = AgentSubscription(
        user_id=user_id,
        agent_slug_id=agent.id,
        status=SubscriptionStatus.PRE_INIT,
        oauth_state=state,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def build_github_oauth_url(state: str) -> str:
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "scope": "repo read:user",
        "state": state,
        "redirect_uri": GITHUB_REDIRECT_URI,
    }
    return "https://github.com/login/oauth/authorize?" + urlencode(params)


# ---------------------------------------------------------------------------
# GitHub OAuth callback
# ---------------------------------------------------------------------------

def get_subscription_by_state(db: Session, state: str, user_id: str) -> AgentSubscription:
    subscription = db.query(AgentSubscription).filter(
        AgentSubscription.oauth_state == state,
        AgentSubscription.user_id == user_id,
    ).first()
    if not subscription:
        raise ValueError("Invalid or expired OAuth state")
    return subscription


def store_github_auth(
    db: Session,
    user_id: str,
    access_token: str,
    scope: str,
    provider_user_id: str,
    provider_username: str,
) -> ThirdPartyAuth:
    encrypted = encrypt_token(access_token)

    existing = db.query(ThirdPartyAuth).filter(
        ThirdPartyAuth.user_id == user_id,
        ThirdPartyAuth.provider == "github",
    ).first()

    if existing:
        existing.access_token = encrypted
        existing.scope = scope
        existing.provider_user_id = provider_user_id
        existing.provider_username = provider_username
        db.commit()
        db.refresh(existing)
        return existing

    auth = ThirdPartyAuth(
        user_id=user_id,
        provider="github",
        access_token=encrypted,
        scope=scope,
        provider_user_id=provider_user_id,
        provider_username=provider_username,
    )
    db.add(auth)
    db.commit()
    db.refresh(auth)
    return auth


# ---------------------------------------------------------------------------
# Allowed AI apps
# ---------------------------------------------------------------------------

def get_allowed_apps(db: Session, agent_slug_name: str) -> list[AllowedAI]:
    agent = db.query(AgentSlug).filter(AgentSlug.slug_name == agent_slug_name).first()
    if not agent:
        raise ValueError(f"Agent '{agent_slug_name}' not found")
    return db.query(AllowedAI).filter(AllowedAI.agent_slug_id == agent.id).all()


# ---------------------------------------------------------------------------
# AI app auth
# ---------------------------------------------------------------------------

def store_ai_app_auth(
    db: Session,
    user_id: str,
    ai_name: str,
    auth_type: str,
    access_token: str,
) -> AIAppAuth:
    encrypted = encrypt_token(access_token)

    existing = db.query(AIAppAuth).filter(
        AIAppAuth.user_id == user_id,
        AIAppAuth.ai_name == ai_name,
    ).first()

    if existing:
        existing.access_token = encrypted
        existing.auth_type = auth_type
        db.commit()
        db.refresh(existing)
        return existing

    auth = AIAppAuth(
        user_id=user_id,
        ai_name=ai_name,
        auth_type=auth_type,
        access_token=encrypted,
    )
    db.add(auth)
    db.commit()
    db.refresh(auth)
    return auth


# ---------------------------------------------------------------------------
# Initialize subscription (status → INITIALIZING, create init task + session)
# ---------------------------------------------------------------------------

def initialize_subscription(
    db: Session,
    subscription_id: str,
    ai_name: str,
    user_id: str,
) -> str:
    subscription = db.query(AgentSubscription).filter(
        AgentSubscription.id == subscription_id,
        AgentSubscription.user_id == user_id,
    ).first()
    if not subscription:
        raise ValueError("Subscription not found")
    if subscription.status != SubscriptionStatus.PRE_INIT:
        raise ValueError(f"Subscription is already in '{subscription.status.value}' state")

    phase = (
        db.query(PipelinePhase)
        .filter(
            PipelinePhase.agent_slug_id == subscription.agent_slug_id,
            PipelinePhase.phase_number == 0,
        )
        .first()
    )
    if not phase:
        raise ValueError("No Phase 0 defined for this agent")

    ai_auth = db.query(AIAppAuth).filter(
        AIAppAuth.user_id == user_id,
        AIAppAuth.ai_name == ai_name,
    ).first()

    # Create virtual init task
    init_task = AgentTask(
        agent_subscription_id=subscription.id,
        task_slug="init",
        current_phase_id=phase.id,
    )
    db.add(init_task)
    db.flush()

    # Create Stage 0 session
    session = AIAppSession(
        task_id=init_task.id,
        ai_app_auth_id=ai_auth.id if ai_auth else None,
        stage=0,
        status=SessionStatus.ACTIVE,
    )
    db.add(session)
    db.flush()

    init_task.current_active_session_id = session.id
    subscription.status = SubscriptionStatus.INITIALIZING
    db.commit()

    return phase.prompt


# ---------------------------------------------------------------------------
# Activate subscription (status → ACTIVE, close init session)
# ---------------------------------------------------------------------------

def activate_subscription(db: Session, subscription_id: str, user_id: str) -> None:
    subscription = db.query(AgentSubscription).filter(
        AgentSubscription.id == subscription_id,
        AgentSubscription.user_id == user_id,
    ).first()
    if not subscription:
        raise ValueError("Subscription not found")
    if subscription.status != SubscriptionStatus.INITIALIZING:
        raise ValueError(f"Subscription is in '{subscription.status.value}' state, expected INITIALIZING")

    # Close the init session
    init_task = db.query(AgentTask).filter(
        AgentTask.agent_subscription_id == subscription.id,
        AgentTask.task_slug == "init",
    ).first()
    if init_task and init_task.current_active_session_id:
        session = db.query(AIAppSession).filter(
            AIAppSession.id == init_task.current_active_session_id
        ).first()
        if session:
            session.status = SessionStatus.CLOSED

    subscription.status = SubscriptionStatus.ACTIVE
    db.commit()
