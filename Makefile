SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

UV ?= uv
NPM ?= npm
COMPOSE ?= docker compose
WEB_DIR := apps/web
DATABASE_URL ?= postgresql://jarvis:jarvis@localhost:5432/jarvis
DATABASE_SCHEMA ?= public
TEST_DATABASE_URL ?= $(DATABASE_URL)

.PHONY: help doctor bootstrap dev stop verify verify-python verify-web \
	verify-integration migrate demo clean

help: ## List available commands.
	@awk 'BEGIN {FS = ":.*## "; printf "Jarvis commands:\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

doctor: ## Check required local tools and configuration without changing the system.
	@bash ./scripts/doctor.sh

bootstrap: doctor ## Install dependencies and start development infrastructure.
	$(UV) sync --frozen
	$(NPM) ci --prefix $(WEB_DIR)
	@bash ./scripts/install_git_hooks.sh
	$(COMPOSE) up -d --wait postgres otel-collector
	@JARVIS_TEST_DATABASE_URL="$(DATABASE_URL)" $(UV) run python scripts/check_postgres.py
	@$(MAKE) migrate

dev: ## Build and run the complete local stack.
	$(COMPOSE) up --build

stop: ## Stop the local stack without deleting database data.
	$(COMPOSE) down

verify: verify-python verify-web verify-integration ## Run deterministic pull-request gates.

verify-python: ## Run Python formatting, lint, typing, and unit tests.
	$(UV) run ruff format --check src tests
	$(UV) run ruff check src tests
	$(UV) run mypy src
	$(UV) run pytest tests/unit

verify-web: ## Run web lint, tests, and production build.
	$(NPM) run lint --prefix $(WEB_DIR)
	$(NPM) run test --prefix $(WEB_DIR)
	$(NPM) run build --prefix $(WEB_DIR)

verify-integration: ## Run the complete coverage suite against real PostgreSQL.
	JARVIS_TEST_DATABASE_URL="$(TEST_DATABASE_URL)" $(UV) run pytest tests \
		--cov=jarvis --cov-report=term-missing

migrate: ## Apply pending canonical PostgreSQL migrations.
	JARVIS_DATABASE_URL="$(DATABASE_URL)" JARVIS_DATABASE_SCHEMA="$(DATABASE_SCHEMA)" \
		$(UV) run python -m jarvis.infrastructure.migrations

demo: ## Build, run, and verify one complete disposable local stack.
	@bash ./scripts/demo.sh

clean: ## Remove generated local build and test output.
	rm -rf .coverage .mypy_cache .pytest_cache .ruff_cache htmlcov
	rm -rf $(WEB_DIR)/dist $(WEB_DIR)/coverage
