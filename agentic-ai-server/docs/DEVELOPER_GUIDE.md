# Developer Guide

Internal reference for building and extending **agentic-ai-server**.

## Quick start

```bash
cd agentic-ai-server
cp .env.example .env
make install
make dev          # API at http://localhost:8080
make check        # lint + typecheck + tests
```

## Creating a new agent

### Option A — Scaffold command (recommended)

```bash
# Single ADK agent (stateless)
uv run agentic-scaffold my_agent \
  --name "My Agent" \
  --description "Does something useful." \
  --template simple

# Multi-agent chat system (session-aware)
uv run agentic-scaffold support_bot \
  --name "Support Bot" \
  --description "Customer support with routing." \
  --template chat-system \
  --conversational

# Multi-agent workflow (stateless task pipeline)
uv run agentic-scaffold intake_flow \
  --name "Intake Flow" \
  --description "Sequential workflow with retry." \
  --template workflow-system
```

Or via Make:

```bash
make scaffold AGENT_ID=my_agent NAME="My Agent" DESC="Does something useful." TEMPLATE=simple
```

This generates:

```
agents/<id>/
  handler.py          # create_agent_handler factory
  agent.py            # (simple only) ADK root_agent
  manifest.yaml       # (systems only) declarative graph
tests/agents/test_<id>.py
agents/registry.yaml  # auto-appended entry
```

### Option B — Copy an example

| Copy from | When to use |
|-----------|-------------|
| `agents/echo/` | Single ADK agent, stateless `POST /run` |
| `agents/chat_assistant/` | Conversational multi-agent system with sessions |
| `agents/claim_workflow/` | Stateless workflow (sequential, parallel, retry) |

Examples are the canonical patterns — prefer copying them over reading docs alone.

## Agent types

| Type | `interaction_mode` | API pattern | Example |
|------|-------------------|-------------|---------|
| **Simple ADK** | `stateless` (default) | `POST /agents/{id}/run` | `echo` |
| **Chat system** | `conversational` | Session REST + `/run` | `chat_assistant` |
| **Workflow system** | `stateless` | `POST /agents/{id}/run` | `claim_workflow` |

### When to use each

- **Simple** — one LLM agent, no internal routing, quick endpoints.
- **Chat system** — multi-turn dialogue, orchestrator + specialists, durable sessions.
- **Workflow system** — deterministic pipelines, parallel steps, retries, merge stages.

## Session & memory behavior

Applies to agents with `interaction_mode: conversational`.

1. Client creates session: `POST /agents/{id}/sessions`
2. Client sends messages: `POST /agents/{id}/sessions/{sid}/messages`
3. Framework injects **rolling summary + recent turns** — not full transcript replay
4. On close: `DELETE /agents/{id}/sessions/{sid}` triggers memory checkpoint hooks

Configure per agent in registry:

```yaml
conversation:
  summarize_every_n_turns: 2
  recent_turns_window: 2
  max_summary_chars: 1500
  persist_to_long_term_memory: true
```

Stateless agents skip all session logic automatically.

## Telemetry

Every agent is wrapped with `InstrumentedAgentHandler` at load time — no agent code required.

| What | Where |
|------|-------|
| Traces (HTTP, tools, model calls) | Cloud Trace / OTLP / console |
| Execution rows (latency, tokens, tools) | `TELEMETRY_DATABASE_URL` |
| Business events | Telemetry + optional analytics DB |

Privacy defaults: message content **not** captured in spans or logs unless explicitly enabled.

## Official extension points

These are supported extension surfaces. Avoid bypassing them.

| Extension | Location | Purpose |
|-----------|----------|---------|
| Agent factory | `agents/*/handler.py` → `create_agent_handler` | Wire agent into framework |
| Registry entry | `agents/registry.yaml` | Mount agent + config |
| System manifest | `agents/*/manifest.yaml` | Declarative sub-agent graph |
| Sub-agent handlers | `FunctionSubAgent` overrides in handler | Deterministic/testable nodes |
| ADK root agent | `agents/*/agent.py` | LLM logic for simple agents |
| Summarization policy | registry `conversation:` block | Per-agent session compression |
| Session hooks | `core/conversation/hooks.py` | Auto memory persistence |
| Business events | `TelemetryRecorder.record_business_event()` | Auditing from agent code |

**Not extension points** (framework-owned): loader, instrumentation wrapper, session wrapper, API routing.

## Testing strategy

```bash
make test-unit          # shared abstractions, registry, redaction
make test-orchestration # multi-agent composition flows
make test-api           # HTTP contract tests
make test-session       # session/memory integration
make test-smoke         # startup + optional container smoke
make test               # everything
```

Markers are auto-assigned by directory; override with `@pytest.mark.unit` etc.

## Local container (production-identical)

```bash
make docker-build
make docker-up
curl http://localhost:8080/health
make invoke-echo
make docker-down
```

## CI/CD

| Asset | Purpose |
|-------|---------|
| `.github/workflows/ci.yml` | Lint, typecheck, tests, Docker build smoke |
| `.github/workflows/deploy-cloudrun.yml` | Build, push, deploy with secret refs |
| `infra/cloudbuild.yaml` | GCP-native build + deploy alternative |

Deploy workflow expects GitHub secrets (not hardcoded values):

- `GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`
- `CLOUD_RUN_SERVICE_ACCOUNT`, `GOOGLE_API_KEY` (Secret Manager reference)

## Invoke sample agents

```bash
make invoke-echo
make invoke-chat
# or
./scripts/invoke_agent.sh chat_assistant "Hello!"
```

## Checklist for a new agent PR

- [ ] Scaffolded or copied from an example
- [ ] Registry entry with correct `interaction_mode`
- [ ] Generated/custom tests pass (`tests/agents/test_<id>.py`)
- [ ] `make check` green
- [ ] Documented in PR which agent type and why
