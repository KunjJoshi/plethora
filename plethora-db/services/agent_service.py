from sqlalchemy.orm import Session
from models.agent_slug import AgentSlug
from models.allowed_ai import AllowedAI
from models.pipeline_phases import PipelinePhase
from schemas.agents import AllowedAISchema, MarketplaceAgentSchema


def get_marketplace_agents(db: Session) -> list[MarketplaceAgentSchema]:
    agents = db.query(AgentSlug).all()
    result = []
    for agent in agents:
        allowed_ai = (
            db.query(AllowedAI)
            .filter(AllowedAI.agent_slug_id == agent.id)
            .all()
        )
        phase_count = (
            db.query(PipelinePhase)
            .filter(PipelinePhase.agent_slug_id == agent.id)
            .count()
        )
        result.append(
            MarketplaceAgentSchema(
                id=agent.id,
                slug_name=agent.slug_name,
                agent_type=agent.agent_type,
                allowed_ai=[AllowedAISchema.model_validate(ai) for ai in allowed_ai],
                phase_count=phase_count,
            )
        )
    return result
