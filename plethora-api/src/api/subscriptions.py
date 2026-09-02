from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from logging import getLogger

from schemas.subscriptions import (
    InitializeRequest, InitializeResponse,
    ActivateRequest, ActivateResponse,
)
from schemas.user import UserInDB
from services.subscription_service import initialize_subscription, activate_subscription
from config_api.session import get_db
from config_api.dependencies import get_current_user

logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/subscriptions", tags=["Subscriptions"])


# ---------------------------------------------------------------------------
# PUT /api/v1/subscriptions/initialize
# Sets subscription → INITIALIZING, creates init task + Stage 0 session,
# returns Phase 0 prompt for the Swift app to pass to the AI.
# ---------------------------------------------------------------------------

@router.put("/initialize", response_model=InitializeResponse)
def initialize(
    body: InitializeRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user),
) -> InitializeResponse:
    try:
        prompt = initialize_subscription(
            db,
            subscription_id=str(body.subscription_id),
            ai_name=body.ai_name,
            user_id=str(current_user.id),
        )
        return InitializeResponse(
            subscription_id=body.subscription_id,
            prompt=prompt,
            success=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"initialize error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initialize subscription")


# ---------------------------------------------------------------------------
# PUT /api/v1/subscriptions/activate
# Closes the init session and sets subscription → ACTIVE.
# Called by Swift app once Phase 0 background task completes.
# ---------------------------------------------------------------------------

@router.put("/activate", response_model=ActivateResponse)
def activate(
    body: ActivateRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user),
) -> ActivateResponse:
    try:
        activate_subscription(db, str(body.subscription_id), str(current_user.id))
        return ActivateResponse(success=True, message="Subscription is now active")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"activate error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to activate subscription")
