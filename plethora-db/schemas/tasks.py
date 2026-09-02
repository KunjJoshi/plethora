from pydantic import BaseModel, ConfigDict
from uuid import UUID


class CheckSubscriptionResponse(BaseModel):
    subscription_id: UUID
    agent_slug: str
    success: bool


class InitiateTaskRequest(BaseModel):
    subscription_id: UUID
    task_slug: str        # user-defined identifier, used as directory name
    task_name: str        # human-readable name
    task_description: str


class InitiateTaskResponse(BaseModel):
    task_id: UUID
    phase_number: int
    phase_name: str
    prompt: str
    success: bool


class ApproveTaskRequest(BaseModel):
    task_id: UUID


class ApproveTaskResponse(BaseModel):
    task_id: UUID
    phase_number: int
    phase_name: str
    prompt: str
    completed: bool  # True when no more phases exist
    success: bool


class RollbackRequest(BaseModel):
    task_id: UUID


class RollbackResponse(BaseModel):
    task_id: UUID
    phase_number: int
    phase_name: str
    chat_session_id: str | None  # so Swift can re-open the existing session
    success: bool
