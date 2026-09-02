# Plethora AI — Implementation Details

## What Is This

Plethora AI is a macOS desktop app that lets users run AI coding agents (and eventually other agent types) on their own repositories. The backend is a Python/FastAPI monorepo. The frontend is a Swift desktop app (not yet built).

The first agent is a **GitHub Coding Agent** — it connects to the user's GitHub, clones their repos, and runs Claude Code or OpenAI Codex on tasks they describe.

---

## Monorepo Structure

```
plethora-ai/
├── plethora-db/          # Shared package: models, migrations, schemas, services, auth
│   ├── auth/             # JWT verification, JWKS caching, token encryption
│   ├── models/           # SQLAlchemy models (one file per table)
│   ├── schemas/          # Pydantic request/response models
│   ├── services/         # Business logic, DB queries
│   ├── database/         # SQLAlchemy Base and engine
│   └── alembic/          # Migrations
│       └── versions/
├── plethora-api/
│   └── src/
│       ├── api/           # FastAPI routers (one file per domain)
│       ├── config_api/   # DB session, auth dependency
│       └── main.py
├── docs/
├── pyproject.toml        # uv workspace root
└── uv.lock
```

`plethora-db` is a uv workspace package depended on by `plethora-api`. All models, services, and schemas live in `plethora-db` so they can be imported anywhere.

---

## Database

**Provider:** Supabase (hosted PostgreSQL)
**Connection:** Transaction pooler at `aws-1-us-west-2.pooler.supabase.com:5432`
**Auth schema:** Managed entirely by Supabase (`auth.users`). Our `users` table FKs into it.

### Tables

#### `users`
Our application user record. `id` is the same UUID as `auth.users.id` — created after Supabase signup.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | Mirrors `auth.users.id` |
| username | String UNIQUE | |
| email | String UNIQUE | |
| name | String | |
| address | String | |
| user_type | Enum | `single-user`, `org-member`, `org-admin` |
| user_status | Enum | `active`, `suspended`, `deleted`, `account-not-created`, `account-not-verified` |
| is_active | Boolean | |
| created_at / updated_at | DateTime | |

#### `agent_slugs`
Registry of available agents shown in the marketplace.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| slug_name | String UNIQUE | e.g. `github`, `linkedin` |
| agent_type | String | e.g. `Coding Agent` |

#### `allowed_ai_models`
Which AI models can run for each agent.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| agent_slug_id | UUID FK → agent_slugs CASCADE | |
| ai_name | String | `claude_code`, `openai_codex` |
| custom_agent_url | String nullable | For custom/self-hosted models |

#### `pipeline_phases`
Ordered phases that define an agent's workflow. Each phase has a prompt that gets sent to the AI.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| agent_slug_id | UUID FK → agent_slugs CASCADE | |
| phase_name | String | e.g. `Repository Analysis` |
| phase_number | Integer | 0 = init, 1..N = task phases |
| phase_type | Enum `phasetype` | `INGESTION` (runs a function), `EXECUTION` (sends prompt to AI) |
| prompt | Text | The actual prompt text sent to the AI for this phase |

#### `third_party_auths`
OAuth tokens for external services (GitHub, LinkedIn, Jira, etc.). Tokens are **Fernet-encrypted** before storage.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users CASCADE | |
| provider | String | `github`, `linkedin`, `jira` |
| access_token | Text | Encrypted |
| refresh_token | Text nullable | Encrypted |
| token_type | String | Default `Bearer` |
| scope | String nullable | e.g. `repo read:user` |
| expires_at | DateTime nullable | NULL = non-expiring |
| provider_user_id | String nullable | User's ID on the provider |
| provider_username | String nullable | e.g. `kunjjoshi` |
| meta | JSONB nullable | Any provider-specific extras |
| UNIQUE | (user_id, provider) | One auth per provider per user |

#### `ai_app_auths`
API keys or OAuth tokens for AI apps (Claude Code, Codex, etc.). Tokens are **Fernet-encrypted**.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users CASCADE | |
| ai_name | String | `claude_code`, `openai_codex` — matches `allowed_ai_models.ai_name` |
| auth_type | String | `api_key` or `oauth` |
| access_token | Text | Encrypted |
| refresh_token | Text nullable | Encrypted |
| expires_at | DateTime nullable | |
| meta | JSONB nullable | e.g. `{"org_id": "..."}` for OpenAI |
| UNIQUE | (user_id, ai_name) | One auth per AI per user |

#### `agent_subscriptions`
A user's subscription to an agent. Created when they select an agent from the marketplace.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | Also used as the workspace directory name: `~/.plethora/workspaces/{id}/` |
| user_id | UUID FK → users CASCADE | |
| agent_slug_id | UUID FK → agent_slugs CASCADE | |
| status | Enum `subscriptionstatus` | `PRE_INIT → INITIALIZING → ACTIVE → PAUSED → EXPIRED` |
| oauth_state | String nullable | Random token for GitHub OAuth CSRF verification |
| created_at / updated_at | DateTime | |

**No `agent_subscription_repos` table.** Repos are cloned directly to `~/.plethora/workspaces/{subscription_id}/`. If that directory is deleted, the subscription is gone from disk.

#### `agent_tasks`
Individual tasks a user creates within an active subscription. Each task is a unit of work the AI handles across one or more phases.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| agent_subscription_id | UUID FK → agent_subscriptions CASCADE | |
| task_slug | String | User-defined name, e.g. `implement-auth`. `init` is reserved for the Stage 0 task |
| current_phase_id | UUID FK → pipeline_phases SET NULL | Phase the task is currently on |
| current_active_session_id | UUID FK → ai_app_sessions SET NULL | Active AI session, if any. Added via `ALTER TABLE` (circular FK) |
| created_at / updated_at | DateTime | |

#### `ai_app_sessions`
A single AI session for one phase of a task. When a user closes the AI app, the session is marked CLOSED and the task advances to the next phase.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| task_id | UUID FK → agent_tasks CASCADE | |
| ai_app_auth_id | UUID FK → ai_app_auths SET NULL | Which AI + key was used |
| stage | Integer | Phase number this session handled |
| chat_session_id | String nullable | Conversation ID from the AI provider |
| status | Enum `sessionstatus` | `ACTIVE → CLOSED / FAILED` |
| created_at / updated_at | DateTime | |

### Migration Chain

```
a43a7e72bce8  users table + auth.users FK
      ↓
fa54b90e21f9  agent_slugs, pipeline_phases, allowed_ai_models
      ↓
ede311c7098c  add phase_type enum to pipeline_phases
      ↓
e9ce85d5d731  seed: github agent + claude_code + openai_codex
      ↓
6599b1fdbbd6  third_party_auths, ai_app_auths, agent_subscriptions, agent_tasks, ai_app_sessions
      ↓
[PENDING]     rename prompt_url → prompt, add oauth_state to agent_subscriptions
      ↓
[PENDING]     seed: Phase 0 prompt for github agent
```

---

## Auth

### Supabase Auth (user identity)
All login/signup/OAuth goes through Supabase's GoTrue. We never handle passwords.

**JWT Verification — local, no network call on hot path:**
- `auth/jwks.py` fetches Supabase's public keys from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` and caches them for 1 hour.
- `auth/jwt.py` verifies tokens locally using ES256 (Supabase's current algorithm). On cache miss, auto-refreshes once to handle key rotation.
- `config_api/dependencies.py` exposes `get_current_user()` — a FastAPI dependency that extracts the bearer token, runs `verify_supabase_jwt()`, looks up the user by `sub` (UUID), and returns the `UserInDB` model.

### Token Encryption (third-party and AI app tokens)
`auth/encryption.py` wraps Fernet symmetric encryption. Requires `TOKEN_ENCRYPTION_KEY` in `.env`.

To generate a key:
```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

All `access_token` and `refresh_token` values in `third_party_auths` and `ai_app_auths` are encrypted before INSERT and decrypted after SELECT.

---

## API Endpoints

All endpoints are prefixed with `/api/v1`. The server starts with:
```bash
cd plethora-api/src && uv run uvicorn main:app --reload
```
Swagger UI: `http://localhost:8000/docs`

### Users `/api/v1/users`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/register-user` | No | Supabase signup + insert into users table |
| POST | `/login` | No | Supabase password auth, returns `access_token` + `refresh_token` |
| POST | `/refresh` | No | Exchange refresh token for new access token |
| POST | `/reset-password` | No | Send password reset email |
| POST | `/reset-password/confirm` | No | Apply new password with reset token |
| POST | `/logout` | No | Invalidate session on Supabase |
| GET | `/me` | Yes | Returns current user |
| PATCH | `/me` | Yes | Update profile |
| POST | `/oauth-callback` | No | Handle Supabase OAuth callback (Google, GitHub app login) |
| GET | `/{user_id}` | Yes | Get any user by ID |

### Agents `/api/v1/agents`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/marketplace` | Yes | All agents with allowed AIs and phase count |

### Third Party + AI Auth `/api/v1`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/third-party/subscribe` | Yes | Create subscription (status=PRE_INIT) + return GitHub OAuth URL |
| POST | `/auth/third-party/github/callback` | Yes | Exchange OAuth code for token, store encrypted in `third_party_auths` |
| GET | `/allowed-apps?agent_slug=` | Yes | List allowed AI models for an agent |
| POST | `/auth/ai-apps` | Yes | Store encrypted API key in `ai_app_auths` |

### Subscriptions `/api/v1/subscriptions`

| Method | Path | Auth | Description |
|---|---|---|---|
| PUT | `/initialize` | Yes | Status → INITIALIZING, create init task + Stage 0 session, return Phase 0 prompt |
| PUT | `/activate` | Yes | Status → ACTIVE, close init session. Called after Phase 0 background task completes |

---

## GitHub Coding Agent — Stage 0 Flow

This is the full subscription initialization flow for the GitHub agent. It spans multiple round-trips between the Swift app and backend.

```
1. User selects GitHub agent from marketplace
   Swift: GET /api/v1/agents/marketplace

2. User clicks Subscribe
   Swift: POST /api/v1/third-party/subscribe { agent_slug: "github" }
   Backend: creates AgentSubscription (PRE_INIT), generates random oauth_state
   Response: { subscription_id, oauth_url }

3. Swift opens oauth_url in system browser
   GitHub shows consent screen: "Plethora wants repo access"
   User approves → GitHub redirects to:
   plethora://github/callback?code=XXX&state=<oauth_state>

4. Swift intercepts redirect (custom URL scheme), sends code to backend
   Swift: POST /api/v1/auth/third-party/github/callback { code, state }
   Backend: verifies state matches subscription owned by user,
            exchanges code → GitHub access token,
            fetches GitHub user profile,
            stores encrypted token in third_party_auths

5. Swift calls GitHub API directly to list repos
   Swift: GET https://api.github.com/user/repos (using stored OAuth token)
   User selects which repos to use
   Swift creates: ~/.plethora/workspaces/{subscription_id}/{repo_name}/
   Swift runs: git clone https://oauth2:{token}@github.com/user/repo.git {path}

6. User selects AI app (Claude Code or Codex)
   Swift: GET /api/v1/allowed-apps?agent_slug=github
   User enters their Anthropic/OpenAI API key
   Swift: POST /api/v1/auth/ai-apps { ai_name: "claude_code", auth_type: "api_key", access_token: "sk-ant-..." }
   Backend: encrypts and stores in ai_app_auths

7. User clicks Initialize
   Swift: PUT /api/v1/subscriptions/initialize { subscription_id, ai_name: "claude_code" }
   Backend: status → INITIALIZING
            creates AgentTask (task_slug="init", phase_number=0)
            creates AIAppSession (stage=0, status=ACTIVE)
            fetches Phase 0 prompt from pipeline_phases
            substitutes {workspace_path} in prompt
   Response: { prompt, subscription_id }

8. Swift runs Phase 0 in background (no UI)
   Claude Code CLI: ANTHROPIC_API_KEY=<decrypted key> claude -p "<prompt>"
   working directory: ~/.plethora/workspaces/{subscription_id}/
   Claude reads all repos, writes current_state.json to workspace root

9. Phase 0 completes
   Swift: PUT /api/v1/subscriptions/activate { subscription_id }
   Backend: closes init AIAppSession (CLOSED)
            status → ACTIVE
   Swift: navigates to Agent page showing task history
```

### Workspace Layout

```
~/.plethora/workspaces/
  {subscription_id}/
    my-repo/                    ← cloned repository
    another-repo/               ← another cloned repository
    current_state.json          ← written by Phase 0 (repo summary)
    implement-auth/             ← created by init_new_task() for each task
      workspaces → ../my-repo  ← symlink to actual repo (git branch isolation WIP)
    add-payments/
      workspaces → ../my-repo
```

---

## What's Coming Next

### Pending migrations
- Rename `prompt_url → prompt` on `pipeline_phases`, add `oauth_state` on `agent_subscriptions`
- Seed Phase 0 prompt for GitHub agent

### Task flow (not yet built)
Once a subscription is ACTIVE, users create tasks:

```
POST /api/v1/subscriptions/{id}/tasks     { task_slug: "implement-auth" }
  → init_new_task("github") — creates symlink in workspace
  → creates AgentTask (stage 1)
  → creates AIAppSession (stage=1, ACTIVE)
  → returns session info + phase prompt

PATCH /api/v1/sessions/{id}/close
  → closes AIAppSession (CLOSED)
  → advances AgentTask.current_phase_id to next pipeline phase
  → creates new AIAppSession for next stage (if phases remain)

GET /api/v1/subscriptions/{id}/tasks      → list all tasks
GET /api/v1/tasks/{id}                    → task detail + current phase
```

### Agent page (Swift app — not yet built)
- Shows list of tasks for an active subscription
- Each task shows its current phase and session history
- "New Task" button → opens task creation flow
- Clicking a task → resumes the current AI app session

### Other agents (future)
The pipeline model is agent-agnostic. Adding a new agent means:
1. Insert a row in `agent_slugs`
2. Insert rows in `allowed_ai_models`
3. Insert rows in `pipeline_phases` with prompts
4. Add a case to `pre_init_agents(slug)` for the initialization logic
5. Add a case to `init_new_task(slug)` for the per-task setup

### Known gaps to address
- `pre_init_agents(slug)` function not yet implemented (GitHub: clone repos logic)
- `init_new_task(slug)` function not yet implemented (GitHub: symlink logic)
- No list/get endpoints for subscriptions yet (`GET /api/v1/subscriptions`, `GET /api/v1/subscriptions/{id}`)
- No `GET /api/v1/tasks/{id}` or task listing yet
- Swift app not started

---

## Required Environment Variables

```bash
# plethora-db/.env

DATABASE_URL=postgresql://postgres.{ref}:{password}@aws-1-us-west-2.pooler.supabase.com:5432/postgres
SUPABASE_URL_REST=https://{ref}.supabase.co
SUPABASE_ANON_KEY=sb_publishable_...

GITHUB_CLIENT_ID=...           # From github.com/settings/developers
GITHUB_CLIENT_SECRET=...       # Keep private — never commit
GITHUB_REDIRECT_URI=plethora://github/callback

TOKEN_ENCRYPTION_KEY=...       # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Key Design Decisions

| Decision | Why |
|---|---|
| Supabase handles auth, we handle users | We get OAuth, email confirmation, and JWT for free. Our `users` table stores app-specific data. |
| JWT verified locally via JWKS (ES256) | Calling Supabase `/auth/v1/user` on every request adds ~150ms latency. Local crypto verification is microseconds. Keys cached 1 hour. |
| `prompt` stored as text, not URL | Simpler to seed, update, and return. No S3 or CDN dependency for v1. |
| No `agent_subscription_repos` table | Can't generalize shape across agents. Filesystem is the source of truth. If `~/.plethora/` is deleted, subscription is gone from disk. |
| `oauth_state` stored on `agent_subscriptions` | Random token for CSRF protection. Ties the GitHub callback to the specific subscription that initiated the OAuth flow. |
| Circular FK handled via `ALTER TABLE` | `agent_tasks.current_active_session_id → ai_app_sessions` and `ai_app_sessions.task_id → agent_tasks`. Alembic emits the circular constraint after both tables exist. |
| Stage 0 is a virtual task (`task_slug="init"`) | Keeps `ai_app_sessions` schema clean — all sessions always FK to a task. No nullable `subscription_id` vs `task_id` split. |
| Phase 0 runs in background, no terminal UI | Repo analysis doesn't need user interaction. Swift calls Claude Code CLI with `-p` flag, waits for completion, then calls `/activate`. |
