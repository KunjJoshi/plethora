from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from logging import getLogger

from schemas.agents import MarketplaceResponse
from schemas.user import UserInDB
from services.agent_service import get_marketplace_agents
from config_api.session import get_db
from config_api.dependencies import get_current_user

logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["Agents"])


@router.get("/marketplace", response_model=MarketplaceResponse)
def get_marketplace(
    db: Session = Depends(get_db),
    _: UserInDB = Depends(get_current_user),
) -> MarketplaceResponse:
    try:
        agents = get_marketplace_agents(db)
        return MarketplaceResponse(agents=agents, success=True)
    except Exception as e:
        logger.error(f"marketplace error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load marketplace",
        )
