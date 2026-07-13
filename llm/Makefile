.PHONY: logs

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build Docker image
	@echo "Removing previous image..."
	@docker rmi tutor 2>/dev/null || true
	@echo "Building Docker images..."
	@docker build -q -t tutor .

# ============================================================================
# Production instance
# ============================================================================

prod-up: ## Start prod instance
	@echo "Starting services..."
	@docker compose up -d
	@echo "Services started!"
	@echo "  - Application: https://$$(grep ^DOMAIN .env | cut -d '=' -f2)"
	@echo "  - Health check: https://$$(grep ^DOMAIN .env | cut -d '=' -f2)/health"

prod-down: ## Stop prod instance
	@echo "Stopping services..."
	@docker compose down

prod-restart: ## Restart prod instance
	@echo "Restarting services..."
	@docker compose restart

prod-again: ## Quick rebuild and restart prod (deploy)
	@echo "Stopping services..."
	@docker compose down
	@echo "Removing previous image..."
	@docker rmi tutor 2>/dev/null || true
	@echo "Building..."
	@docker build -q -t tutor .
	@echo "Starting services..."
	@docker compose up -d

prod-logs: ## Tail prod logs
	@docker compose logs core -f

prod-shell: ## Open shell in prod container
	@docker compose exec core /bin/bash

prod-shell-db: ## Open psql in prod DB
	@docker compose exec postgres psql -U postgres -d tutor_assistant

prod-db-init: ## Create prod DB tables
	@docker compose exec core uv run python /app/scripts/db_manager.py init

prod-db-drop: ## Drop all prod DB tables
	@docker compose exec core uv run python /app/scripts/db_manager.py drop

prod-db-stats: ## Show prod DB statistics
	@docker compose exec core uv run python /app/scripts/db_manager.py stats

prod-db-projects: ## List all prod projects
	@docker compose exec core uv run python /app/scripts/db_manager.py projects

prod-db-backup: ## Create prod DB backup
	@docker compose exec core uv run python /app/scripts/db_manager.py backup

prod-db-backup-schema: ## Create prod schema-only backup
	@docker compose exec core uv run python /app/scripts/db_manager.py backup-schema

prod-db-restore: ## Restore prod DB from backup (usage: make prod-db-restore name=<backup>)
	@docker compose exec core uv run python /app/scripts/db_manager.py restore $(name)

prod-db-backups: ## List prod DB available backups
	@docker compose exec core uv run python /app/scripts/db_manager.py list-backups

prod-db-migrate: ## Apply pending migrations on prod DB
	@docker compose exec core uv run python /app/scripts/db_manager.py migrate

prod-db-migrate-create: ## Create migration (usage: make prod-db-migrate-create msg="description")
	@docker compose exec core uv run python /app/scripts/db_manager.py migrate-create '$(msg)'

prod-db-migrate-history: ## Show prod migration history
	@docker compose exec core uv run python /app/scripts/db_manager.py migrate-history

prod-db-migrate-current: ## Show prod current migration revision
	@docker compose exec core uv run python /app/scripts/db_manager.py migrate-current

prod-seed-admin: ## Seed admin user in prod DB
	@docker compose exec core uv run python /app/scripts/seed_admin.py

prod-stats: ## Show prod tutor stats dashboard
	@docker compose exec core uv run python /app/scripts/stats.py

prod-cleanup: ## Run cleanup task on prod
	@docker compose exec core uv run python /app/scripts/cleanup_task.py

# ============================================================================
# Dev instance
# ============================================================================

dev-up: ## Start dev instance (core-dev + postgres-dev)
	@echo "Starting dev instance..."
	@docker compose up postgres-dev core-dev -d
	@echo "Dev instance running at https://dev.$$(grep ^DOMAIN .env | cut -d '=' -f2)"

dev-down: ## Stop dev instance
	@docker compose stop core-dev postgres-dev

dev-logs: ## Tail dev instance logs
	@docker compose logs core-dev -f

dev-shell: ## Open shell in dev container
	@docker compose exec core-dev /bin/bash

dev-shell-db: ## Open psql in dev DB
	@docker compose exec postgres-dev psql -U postgres -d tutor_assistant_dev

dev-db-init: ## Initialize dev DB (fresh setup: create tables + stamp migrations)
	@docker compose exec core-dev uv run python /app/scripts/db_manager.py init
	@docker compose exec -w /app core-dev uv run alembic -c /app/alembic.ini stamp head
	@echo "Dev DB initialized"

dev-db-migrate: ## Apply pending migrations on dev DB
	@docker compose exec core-dev uv run python /app/scripts/db_manager.py migrate

dev-db-migrate-create: ## Create migration (usage: make dev-db-migrate-create msg="description")
	@docker compose exec core-dev uv run python /app/scripts/db_manager.py migrate-create '$(msg)'

dev-db-migrate-history: ## Show dev migration history
	@docker compose exec core-dev uv run python /app/scripts/db_manager.py migrate-history

dev-db-migrate-current: ## Show dev current migration revision
	@docker compose exec core-dev uv run python /app/scripts/db_manager.py migrate-current

# ============================================================================
# Testing
# ============================================================================

test: ## Run tests in dev container (no LLM cost)
	@docker compose exec -w /app core-dev uv run pytest tests/ -m "not agent"

test-agent: ## Run LLM/agent tests in dev container (consumes tokens)
	@docker compose exec -w /app core-dev uv run pytest tests/ -m agent

test-cov: ## Run tests with coverage report
	@docker compose exec -w /app core-dev uv run pytest tests/ -m "not agent" --cov=src --cov-report=term-missing

# ============================================================================
# Linting & Formatting
# ============================================================================

lint: ## Check code style (ruff)
	@echo "Running ruff..."
	@uv run ruff check
	@echo "All checks passed!"

format-check: ## Check formatting (yapf)
	@echo "Running yapf..."
	@uv run yapf -dr src/ > /dev/null
	@echo "All checks passed!"

lint-fix: ## Auto-fix code style (ruff)
	@echo "Fixing with ruff..."
	@uv run ruff check --fix
	@echo "Done!"

format: ## Auto-format code (yapf)
	@echo "Formatting with yapf..."
	@uv run yapf -ir src/
	@echo "Done!"
