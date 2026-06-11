.PHONY: help install dev test test-unit test-api test-orchestration test-session test-smoke lint typecheck check docker-build docker-up docker-down invoke-echo invoke-chat scaffold

help:
	@echo "agentic-ai-server developer commands"
	@echo ""
	@echo "  make install          Install dependencies (uv sync)"
	@echo "  make dev              Run API server with reload"
	@echo "  make test             Run full test suite"
	@echo "  make test-unit        Run unit tests only"
	@echo "  make test-api         Run API contract tests"
	@echo "  make test-orchestration  Run multi-agent orchestration tests"
	@echo "  make test-session     Run session/memory tests"
	@echo "  make test-smoke       Run smoke tests"
	@echo "  make lint             Run ruff"
	@echo "  make typecheck        Run mypy"
	@echo "  make check            lint + typecheck + test"
	@echo "  make docker-build     Build production container"
	@echo "  make docker-up        Start container via docker compose"
	@echo "  make docker-down      Stop container"
	@echo "  make invoke-echo      POST sample message to echo agent"
	@echo "  make invoke-chat      POST sample message to chat_assistant"
	@echo "  make scaffold         Scaffold agent (AGENT_ID=... NAME=... DESC=...)"

install:
	uv sync --all-groups

dev:
	uv run agentic-ai-server

test:
	uv run pytest -q

test-unit:
	uv run pytest -q -m unit

test-api:
	uv run pytest -q -m api

test-orchestration:
	uv run pytest -q -m orchestration

test-session:
	uv run pytest -q -m session

test-smoke:
	uv run pytest -q -m smoke

lint:
	uv run ruff check .

typecheck:
	uv run mypy app core api db telemetry agents tools

check: lint typecheck test

docker-build:
	docker build -t agentic-ai-server:local .

docker-up:
	docker compose -f infra/docker-compose.yml up --build

docker-down:
	docker compose -f infra/docker-compose.yml down

invoke-echo:
	./scripts/invoke_agent.sh echo "Hello from make"

invoke-chat:
	./scripts/invoke_agent.sh chat_assistant "Hello from make"

scaffold:
	@test -n "$(AGENT_ID)" || (echo "AGENT_ID is required" && exit 1)
	@test -n "$(NAME)" || (echo "NAME is required" && exit 1)
	uv run agentic-scaffold $(AGENT_ID) --name "$(NAME)" --description "$(DESC)" --template $(TEMPLATE)

# Defaults for scaffold target
DESC ?= Generated agent
TEMPLATE ?= simple
