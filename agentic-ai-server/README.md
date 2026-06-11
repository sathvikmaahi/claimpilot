# agentic-ai-server

Production-ready foundation for a containerized Python service that hosts **Google ADK 2.x** multi-agent systems behind REST APIs.

## Architecture

```
agentic-ai-server/
├── app/           # Application factory and entry point
├── core/          # Config, agent contract, registry, composition framework
├── agents/        # ADK agent implementations + registry.yaml
├── api/           # FastAPI routes and middleware
├── db/            # Session service factory
├── telemetry/     # Structured logging and OpenTelemetry
├── tools/         # Agent scaffold CLI (`agentic-scaffold`)
├── docs/          # Developer guide
├── scripts/       # Local invoke helpers
├── Makefile       # Dev workflow commands
├── tests/         # Pytest suite (unit, api, orchestration, session, smoke)
├── infra/         # Docker Compose and Cloud Run env templates
└── Dockerfile     # Production container image
```

**Framework first, agents second.** Reusable runtime concerns live under `core/`; individual agents only implement ADK logic and a thin handler factory.

## Quick start

```bash
cd agentic-ai-server
cp .env.example .env   # set GOOGLE_API_KEY or Vertex AI vars

make install
make dev               # http://localhost:8080
make check             # lint + typecheck + tests
```

See **[docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)** for the full team workflow.

## Scaffold a new agent

```bash
# Single ADK agent
uv run agentic-scaffold my_agent --name "My Agent" --description "Does X." --template simple

# Chat multi-agent system (session-aware)
uv run agentic-scaffold support_bot --name "Support" --description "Support chat." \
  --template chat-system --conversational

# Workflow system
uv run agentic-scaffold intake_flow --name "Intake" --description "Intake pipeline." \
  --template workflow-system
```

## Adding an agent (manual)

1. Create `agents/my_agent/agent.py` with a `root_agent` ADK `Agent`.
2. Create `agents/my_agent/handler.py` with a `create_agent_handler(...)` factory returning `ADKAgentHandler`.
3. Register it in `agents/registry.yaml`:

```yaml
agents:
  - id: my_agent
    enabled: true
    name: My Agent
    description: Does something useful.
    handler_module: agents.my_agent.handler
    handler_class: create_agent_handler
    adk:
      model: gemini-2.0-flash
      instruction: "Your system prompt."
```

The agent is automatically mounted at `POST /agents/my_agent/run`.

## Multi-agent composition

Deployable **agent systems** compose internal **sub-agents** through `core/composition/`.

### Sub-agent role taxonomy

| Role | Purpose |
|------|---------|
| `orchestrator` | Plans and delegates across the graph |
| `conversational` | Open-ended dialogue |
| `task` | Bounded, goal-directed work |
| `tool_wrapper` | Wraps external tools/APIs |
| `router` | Selects downstream specialists |
| `memory` | Summarization and session memory |

### Orchestration primitives

- **Sequential** — run steps in order, stop on failure
- **Parallel** — run branches concurrently and merge outputs
- **Router** — dispatch based on structured output from a prior node
- **Retry** — retry a step until success or max attempts

### Declarative agent system manifest

Each multi-agent system declares its graph in `agents/<system>/manifest.yaml`:

```yaml
id: chat_assistant
name: Chat Assistant
model:
  default: gemini-2.0-flash
safety:
  max_turns: 20
nodes:
  orchestrator:
    role: orchestrator
    instruction: "Classify intent as chat or task..."
    output_key: route
  conversational:
    role: conversational
    instruction: "Respond naturally..."
graph:
  - type: sequential
    steps:
      - orchestrator
      - type: router
        source: orchestrator
        field: route
        routes:
          chat: conversational
          task: task_worker
      - session_memory
```

Register in `agents/registry.yaml` with `type: agent_system` and point to the manifest.

### Example systems

- **`chat_assistant`** — orchestrator → router → conversational/task → memory
- **`claim_workflow`** — intake → retry validate → parallel reviewers → merge → summarize

```bash
curl -X POST http://localhost:8080/agents/chat_assistant/run \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'

curl -X POST http://localhost:8080/agents/claim_workflow/run \
  -H "Content-Type: application/json" \
  -d '{"message": "claim-abc-123"}'
```

Sub-agents exchange context through `OrchestrationContext` (`shared`, `outputs`, `trace`) with normalized `SubAgentResult` payloads for deterministic, testable orchestration.

## Conversation layer (sessions, memory, summarization)

The `core/conversation/` module provides a reusable chat infrastructure:

- **`SessionSummary`** — first-class rolling summary artifact (not full transcript replay)
- **`ConversationSessionStore`** — in-memory (dev) or SQLite (production via `CONVERSATION_DATABASE_URL`)
- **`SummarizationPipeline`** — updates summaries at configurable intervals per agent
- **`FrameworkMemoryAdapter`** — ADK long-term memory integration with auto-persist hooks
- **`SessionAwareAgentWrapper`** — wraps conversational agents with durable session support

### Conversational vs stateless agents

Set `interaction_mode` in `agents/registry.yaml`:

```yaml
  - id: chat_assistant
    interaction_mode: conversational
    conversation:
      summarize_every_n_turns: 2
      recent_turns_window: 2
      max_summary_chars: 1500
      persist_to_long_term_memory: true

  - id: claim_workflow
    interaction_mode: stateless
```

### Session REST API (conversational agents only)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/agents/{id}/sessions` | Create session |
| POST | `/agents/{id}/sessions/{sid}/messages` | Continue session (summary injected) |
| GET | `/agents/{id}/sessions/{sid}` | Get session state (summary by default) |
| GET | `/agents/{id}/sessions/{sid}?include_turns=true` | Opt-in full turn history |
| DELETE | `/agents/{id}/sessions/{sid}` | Close session + memory checkpoint |

Stateless agents continue to use `POST /agents/{id}/run` without session management.

## Observability & operational persistence

Observability **transport** (traces/metrics/logs) is separate from **business telemetry** (SQL rows):

| Layer | Destination | Purpose |
|-------|-------------|---------|
| OpenTelemetry spans | Cloud Trace / OTLP / console | Distributed tracing |
| Normalized SQL rows | `TELEMETRY_DATABASE_URL` | Queryable execution metadata |
| Business events | Telemetry + optional analytics DB | Auditing and reporting |

### Automatic instrumentation

Every registered agent is wrapped with `InstrumentedAgentHandler`, which:
- Emits correlated OTel spans (`agent.execute`)
- Persists execution rows (agent, session, user, latency, tools, tokens, failures)
- Applies privacy-conscious redaction by default

ADK's `AutoTracingPlugin` is enabled on ADK runners when `OTEL_ENABLED=true`.

### Multi-database configuration

```bash
APP_DATABASE_URL=postgresql://...        # application data
TELEMETRY_DATABASE_URL=postgresql://...  # execution events
ANALYTICS_DATABASE_URL=postgresql://...  # reporting (optional)
```

### Privacy defaults

```bash
TELEMETRY_CAPTURE_MESSAGE_CONTENT=false
TELEMETRY_CAPTURE_SPAN_CONTENT=false
ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false  # set automatically
```

Readiness checks report database connectivity at `/ready` (`databases.app`, `databases.telemetry`, etc.).

```bash
# Create and continue a conversation
SESSION=$(curl -s -X POST http://localhost:8080/agents/chat_assistant/sessions \
  -H "Content-Type: application/json" -d '{"user_id":"alice"}' | jq -r .session_id)

curl -X POST http://localhost:8080/agents/chat_assistant/sessions/$SESSION/messages \
  -H "Content-Type: application/json" -d '{"message":"Hello!", "user_id":"alice"}'
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health`, `/healthz` | Liveness probe |
| GET | `/ready`, `/readyz` | Readiness probe (includes registered agents) |
| GET | `/agents` | List registered agents |
| GET | `/agents/{id}` | Agent metadata |
| POST | `/agents/{id}/run` | Run an agent |
| GET | `/agents/{id}/health` | Agent-specific health |

### Run example

```bash
curl -X POST http://localhost:8080/agents/echo/run \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, ADK!"}'
```

## Docker / Cloud Run

```bash
docker build -t agentic-ai-server .
docker run -p 8080:8080 --env-file .env agentic-ai-server
```

Cloud Run notes:
- Binds to `0.0.0.0` and reads `PORT` from the environment
- Stateless by default (`InMemorySessionService`); set `SESSION_SERVICE_URI` for persistence
- Externalize secrets (`GOOGLE_API_KEY`, etc.) via Secret Manager
- Health checks at `/health` and `/ready`

## Development

```bash
make dev              # run server
make test             # full suite
make test-unit        # unit tests only
make test-api         # API contract tests
make test-smoke       # startup smoke tests
make lint             # ruff
make typecheck        # mypy
make docker-build     # production-identical container
make invoke-echo      # sample agent call
```

Or directly:

```bash
uv run pytest
uv run ruff check .
uv run mypy app core api db telemetry agents tools
```

## Environment variables

See [`.env.example`](.env.example) for the full list. Key variables:

- `GOOGLE_API_KEY` — AI Studio API key (local dev)
- `GOOGLE_GENAI_USE_VERTEXAI` — set `true` for Vertex AI on GCP
- `CONVERSATION_DATABASE_URL` — SQLite path for durable sessions (e.g. `sqlite:///./data/conversations.db`)
- `MEMORY_ENABLED` — enable ADK long-term memory adapter
- `SESSION_SERVICE_URI` — ADK runner session backend (separate from conversation layer)
- `AGENT_REGISTRY_PATH` — path to agent manifest YAML
