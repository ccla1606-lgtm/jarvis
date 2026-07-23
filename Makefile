SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

UV ?= uv
NPM ?= npm
COMPOSE ?= docker compose
WEB_DIR := apps/web
TEST_DATABASE_URL ?= postgresql://jarvis:jarvis@localhost:5432/jarvis_test

.PHONY: help doctor bootstrap dev stop verify verify-python verify-web \
	verify-integration demo clean

help: ## List available commands.
	@awk 'BEGIN {FS = ":.*## "; printf "Jarvis commands:\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

doctor: ## Check required local tools and configuration without changing the system.
	@bash ./scripts/doctor.sh

bootstrap: doctor ## Install dependencies and start development infrastructure.
	$(UV) sync --frozen
	$(NPM) ci --prefix $(WEB_DIR)
	$(COMPOSE) up -d --wait postgres otel-collector
	@JARVIS_TEST_DATABASE_URL="$(TEST_DATABASE_URL)" $(UV) run python scripts/check_postgres.py

dev: ## Build and run the complete local stack.
	$(COMPOSE) up --build

stop: ## Stop the local stack without deleting database data.
	$(COMPOSE) down

verify: verify-python verify-web verify-integration ## Run deterministic pull-request gates.

verify-python: ## Run Python formatting, lint, typing, and unit tests.
	$(UV) run ruff format --check src tests
	$(UV) run ruff check src tests
	$(UV) run mypy src
	$(UV) run pytest tests/unit --cov=jarvis --cov-report=term-missing

verify-web: ## Run web lint, tests, and production build.
	$(NPM) run lint --prefix $(WEB_DIR)
	$(NPM) run test --prefix $(WEB_DIR)
	$(NPM) run build --prefix $(WEB_DIR)

verify-integration: ## Run tests against real PostgreSQL.
	JARVIS_TEST_DATABASE_URL="$(TEST_DATABASE_URL)" $(UV) run pytest tests/integration -m integration

demo: ## Build, run, and verify one complete disposable local stack.
	@bash ./scripts/demo.sh

clean: ## Remove generated local build and test output.
	rm -rf .coverage .mypy_cache .pytest_cache .ruff_cache htmlcov
	rm -rf $(WEB_DIR)/dist $(WEB_DIR)/coverage
