from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from logging import getLogger

from schemas.tasks import (
    CheckSubscriptionResponse,
    InitiateTaskRequest, InitiateTaskResponse,
    ApproveTaskRequest, ApproveTaskResponse,
    RollbackRequest, RollbackResponse,
)
from schemas.user import UserInDB
from services.task_service import (
    check_active_subscription,
    initiate_task,
    approve_and_move_on,
    rollback_phase,
)
from config_api.session import get_db
from config_api.dependencies import get_current_user

logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


# ---------------------------------------------------------------------------
# GET /api/v1/tasks/check-subscription/{agent_slug}
# Hidden call — Swift fires this before showing the task creation form.
# Returns the user's active subscription for the given agent, if one exists.
# ---------------------------------------------------------------------------

@router.get("/check-subscription/{agent_slug}", response_model=CheckSubscriptionResponse)
def check_subscription(
    agent_slug: str,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user),
) -> CheckSubscriptionResponse:
    subscription = check_active_subscription(db, str(current_user.id), agent_slug)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active subscription found for agent '{agent_slug}'",
        )
    return CheckSubscriptionResponse(
        subscription_id=subscription.id,
        agent_slug=agent_slug,
        success=True,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/tasks/initiate/{agent_slug}
# Creates a task and kicks off Phase 1.
# Returns the Phase 1 prompt for Swift to pass to the AI app.
# ---------------------------------------------------------------------------

@router.post("/initiate/{agent_slug}", response_model=InitiateTaskResponse)
def initiate(
    agent_slug: str,
    body: InitiateTaskRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user),
) -> InitiateTaskResponse:
    try:
        task, phase, prompt = initiate_task(
            db,
            user_id=str(current_user.id),
            subscription_id=str(body.subscription_id),
            task_slug=body.task_slug,
            task_name=body.task_name,
            task_description=body.task_description,
        )
        return InitiateTaskResponse(
            task_id=task.id,
            phase_number=phase.phase_number,
            phase_name=phase.phase_name,
            prompt=prompt,
            success=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"initiate_task error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initiate task")


# ---------------------------------------------------------------------------
# POST /api/v1/tasks/approve
# Approves the current phase, opens a session for the next phase.
# Returns the next phase prompt, or completed=True if no more phases.
# ---------------------------------------------------------------------------

@router.post("/approve", response_model=ApproveTaskResponse)
def approve(
    body: ApproveTaskRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user),
) -> ApproveTaskResponse:
    try:
        task, next_phase, prompt = approve_and_move_on(db, str(current_user.id), str(body.task_id))
        if next_phase is None:
            return ApproveTaskResponse(
                task_id=task.id,
                phase_number=-1,
                phase_name="",
                prompt="",
                completed=True,
                success=True,
            )
        return ApproveTaskResponse(
            task_id=task.id,
            phase_number=next_phase.phase_number,
            phase_name=next_phase.phase_name,
            prompt=prompt,
            completed=False,
            success=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"approve_and_move_on error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to approve phase")


# ---------------------------------------------------------------------------
# PATCH /api/v1/tasks/rollback
# Halts the current phase, revives the previous phase's session.
# Returns the previous phase info + chat_session_id to re-open in the app.
# ---------------------------------------------------------------------------

@router.patch("/rollback", response_model=RollbackResponse)
def rollback(
    body: RollbackRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user),
) -> RollbackResponse:
    try:
        task, prev_phase, chat_session_id = rollback_phase(db, str(current_user.id), str(body.task_id))
        return RollbackResponse(
            task_id=task.id,
            phase_number=prev_phase.phase_number,
            phase_name=prev_phase.phase_name,
            chat_session_id=chat_session_id,
            success=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"rollback_phase error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to roll back phase")
