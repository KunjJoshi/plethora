from pydantic import BaseModel, ConfigDict
from uuid import UUID


class AllowedAISchema(BaseModel):
    id: UUID
    ai_name: str
    custom_agent_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MarketplaceAgentSchema(BaseModel):
    id: UUID
    slug_name: str
    agent_type: str
    allowed_ai: list[AllowedAISchema]
    phase_count: int


class MarketplaceResponse(BaseModel):
    agents: list[MarketplaceAgentSchema]
    success: bool
