# =============================================================================
# DocuMind — Makefile
# Convenience commands for development
# =============================================================================

.PHONY: help up down build logs restart clean db-shell redis-shell test lint

# Default target
help: ## Show this help message
	@echo "DocuMind — Development Commands"
	@echo "================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ─── Docker Commands ─────────────────────────────────────────────────────────
up: ## Start all services (detached)
	docker-compose up -d --build

up-logs: ## Start all services with logs
	docker-compose up --build

down: ## Stop all services
	docker-compose down

build: ## Build all containers
	docker-compose build --no-cache

logs: ## Follow all service logs
	docker-compose logs -f

logs-backend: ## Follow backend logs
	docker-compose logs -f backend

restart: ## Restart all services
	docker-compose restart

restart-backend: ## Restart only the backend
	docker-compose restart backend

# ─── Database ────────────────────────────────────────────────────────────────
db-shell: ## Open PostgreSQL shell
	docker-compose exec postgres psql -U documind -d documind

db-reset: ## Reset database (WARNING: destroys all data)
	docker-compose down -v
	docker-compose up -d postgres
	@echo "Database reset. Run 'make up' to start all services."

# ─── Redis ───────────────────────────────────────────────────────────────────
redis-shell: ## Open Redis CLI
	docker-compose exec redis redis-cli

# ─── Cleanup ─────────────────────────────────────────────────────────────────
clean: ## Remove all containers, volumes, and orphans
	docker-compose down -v --remove-orphans
	docker system prune -f

# ─── Development ─────────────────────────────────────────────────────────────
dev: ## Run backend locally (outside Docker)
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend: ## Run Flask frontend locally (outside Docker)
	cd frontend && python app.py

# ─── Health Check ────────────────────────────────────────────────────────────
health: ## Check service health
	@echo "Backend:" && curl -s http://localhost:8000/health | python -m json.tool
