from pydantic import BaseModel
from uuid import UUID


class SubscribeRequest(BaseModel):
    agent_slug: str


class SubscribeResponse(BaseModel):
    subscription_id: UUID
    oauth_url: str
    success: bool
    message: str | None = None


class GitHubCallbackRequest(BaseModel):
    code: str
    state: str  # equals subscription_id — verified server-side


class AIAppAuthRequest(BaseModel):
    ai_name: str       # 'claude_code', 'openai_codex'
    auth_type: str     # 'api_key' or 'oauth'
    access_token: str  # raw key — encrypted before storage


class AIAppAuthResponse(BaseModel):
    ai_name: str
    auth_type: str
    success: bool
    message: str | None = None


class InitializeRequest(BaseModel):
    subscription_id: UUID
    ai_name: str


class InitializeResponse(BaseModel):
    subscription_id: UUID
    prompt: str
    success: bool
    message: str | None = None


class ActivateRequest(BaseModel):
    subscription_id: UUID


class ActivateResponse(BaseModel):
    success: bool
    message: str | None = None
