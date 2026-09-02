import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from logging import getLogger
from dotenv import load_dotenv

from schemas.subscriptions import (
    SubscribeRequest, SubscribeResponse,
    GitHubCallbackRequest,
    AIAppAuthRequest, AIAppAuthResponse,
)
from schemas.agents import AllowedAISchema, AllowedAppsResponse
from schemas.user import UserInDB
from services.subscription_service import (
    create_subscription,
    build_github_oauth_url,
    get_subscription_by_state,
    store_github_auth,
    get_allowed_apps,
    store_ai_app_auth,
)
from config_api.session import get_db
from config_api.dependencies import get_current_user

load_dotenv()

logger = getLogger(__name__)
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "plethora://github/callback")

router = APIRouter(prefix="/api/v1", tags=["Third Party"])


# ---------------------------------------------------------------------------
# POST /api/v1/third-party/subscribe
# Creates a subscription and returns the GitHub OAuth URL in one call.
# ---------------------------------------------------------------------------

@router.post("/third-party/subscribe", response_model=SubscribeResponse)
def subscribe(
    body: SubscribeRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user),
) -> SubscribeResponse:
    try:
        subscription = create_subscription(db, str(current_user.id), body.agent_slug)
        oauth_url = build_github_oauth_url(subscription.oauth_state)
        return SubscribeResponse(
            subscription_id=subscription.id,
            oauth_url=oauth_url,
            success=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"subscribe error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create subscription")


# ---------------------------------------------------------------------------
# POST /api/v1/auth/third-party/github/callback
# Swift app sends the code + state after GitHub redirects.
# Backend exchanges code for token, fetches GitHub profile, stores in DB.
# ---------------------------------------------------------------------------

@router.post("/auth/third-party/github/callback")
async def github_callback(
    body: GitHubCallbackRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user),
) -> dict:
    # Verify state matches a subscription owned by this user
    try:
        get_subscription_by_state(db, body.state, str(current_user.id))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": body.code,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
        )

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=token_data.get("error_description", "GitHub did not return an access token"),
        )

    # Fetch GitHub user profile
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    github_user = user_resp.json()

    try:
        store_github_auth(
            db,
            user_id=str(current_user.id),
            access_token=access_token,
            scope=token_data.get("scope", ""),
            provider_user_id=str(github_user.get("id", "")),
            provider_username=github_user.get("login", ""),
        )
    except Exception as e:
        logger.error(f"github auth storage error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to store GitHub auth")

    return {"success": True, "github_username": github_user.get("login")}


# ---------------------------------------------------------------------------
# GET /api/v1/allowed-apps?agent_slug=github
# Returns the allowed AI apps for a given agent.
# ---------------------------------------------------------------------------

@router.get("/allowed-apps", response_model=AllowedAppsResponse)
def allowed_apps(
    agent_slug: str,
    db: Session = Depends(get_db),
    _: UserInDB = Depends(get_current_user),
) -> AllowedAppsResponse:
    try:
        apps = get_allowed_apps(db, agent_slug)
        return AllowedAppsResponse(
            apps=[AllowedAISchema.model_validate(a) for a in apps],
            success=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/v1/auth/ai-apps
# Stores an encrypted API key for an AI app (Claude Code, Codex, etc.).
# ---------------------------------------------------------------------------

@router.post("/auth/ai-apps", response_model=AIAppAuthResponse)
def store_ai_auth(
    body: AIAppAuthRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user),
) -> AIAppAuthResponse:
    try:
        store_ai_app_auth(
            db,
            user_id=str(current_user.id),
            ai_name=body.ai_name,
            auth_type=body.auth_type,
            access_token=body.access_token,
        )
        return AIAppAuthResponse(ai_name=body.ai_name, auth_type=body.auth_type, success=True)
    except Exception as e:
        logger.error(f"ai app auth error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to store AI app auth")
