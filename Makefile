COMPOSE_DEV := docker compose -f docker-compose.dev.yml

export SEED_EMAIL
export SEED_PASSWORD

.DEFAULT_GOAL := help

# All targets are phony (no output files)
.PHONY: help \
        up-dev build-dev rebuild-dev restart-dev stop-dev down-dev \
        logs-dev urls-dev \
        migrate-up-dev migrate-down-dev migrate-status-dev migrate-history-dev \
        seed-super-admin-dev \
        test-backend-unit test-backend-integration-dev test-backend-e2e-dev \
        test-backend-all-dev test-frontend test-all-dev

# Services available in docker-compose.dev.yml
SERVICES := backend frontend worker mongo postgres redis rabbitmq flower loki promtail grafana
# Services that have a Dockerfile and can be built
BUILDABLE := backend frontend

# The awk parser matches two patterns:
#   ##@ Section     → prints a bold section header
#   target: ## desc → prints the target + description
help:
	@echo ""
	@echo "  DopaCRM"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} \
		/^##@ / { printf "\n  \033[1;33m%s\033[0m\n", substr($$0, 5) } \
		/^[a-zA-Z_%-]+:.*?## / { printf "    \033[36m%-25s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# ==============================================================================
#  DEVELOPMENT
# ==============================================================================

##@ Development

##@ Stack

up-dev:  ## Start the dev stack (detached)
	$(COMPOSE_DEV) up -d --remove-orphans

build-dev:  ## Build images (uses cache)
	$(COMPOSE_DEV) build

rebuild-dev:  ## Build images from scratch (--no-cache)
	$(COMPOSE_DEV) build --no-cache

restart-dev:  ## Restart running services
	$(COMPOSE_DEV) restart

stop-dev:  ## Stop services (containers preserved)
	$(COMPOSE_DEV) stop

down-dev:  ## Stop and remove containers (volumes preserved)
	$(COMPOSE_DEV) down

##@ Per-service (make <action>-<service>-dev)

# Pattern rules — works for any service in the compose file.
# Usage:
#   make restart-backend-dev      restart just the backend
#   make stop-postgres-dev        stop just postgres
#   make up-redis-dev             start just redis
#   make build-backend-dev        build just the backend image
#   make rebuild-frontend-dev     build frontend from scratch (--no-cache)
#   make logs-worker-dev          tail worker logs

restart-%-dev:  ## Restart one service (e.g. restart-backend-dev)
	$(COMPOSE_DEV) restart $*

stop-%-dev:  ## Stop one service (e.g. stop-postgres-dev)
	$(COMPOSE_DEV) stop $*

up-%-dev:  ## Start one service (e.g. up-redis-dev)
	$(COMPOSE_DEV) up -d $*

build-%-dev:  ## Build one service image (e.g. build-backend-dev)
	$(COMPOSE_DEV) build $*

rebuild-%-dev:  ## Build one service from scratch (e.g. rebuild-frontend-dev)
	$(COMPOSE_DEV) build --no-cache $*

##@ Database

migrate-up-dev:  ## Apply all pending Alembic migrations
	$(COMPOSE_DEV) exec backend alembic upgrade head

migrate-down-dev:  ## Roll back the most recent Alembic migration
	$(COMPOSE_DEV) exec backend alembic downgrade -1

migrate-status-dev:  ## Show current Alembic revision
	$(COMPOSE_DEV) exec backend alembic current

migrate-history-dev:  ## Show Alembic migration history
	$(COMPOSE_DEV) exec backend alembic history

seed-super-admin-dev:  ## Create platform super_admin (SEED_EMAIL=... SEED_PASSWORD=...)
	@if [ -z "$$SEED_EMAIL" ] || [ -z "$$SEED_PASSWORD" ]; then \
		echo "Error: SEED_EMAIL and SEED_PASSWORD must be set."; \
		echo "Example: make seed-super-admin-dev SEED_EMAIL=admin@example.com SEED_PASSWORD=secret"; \
		exit 1; \
	fi
	@$(COMPOSE_DEV) exec -e SEED_EMAIL -e SEED_PASSWORD backend python -m scripts.create_super_admin

seed-test-gym-dev:  ## Create a test gym + owner/staff/sales users (SLUG=<slug>)
	@if [ -z "$$SLUG" ]; then \
		echo "Error: SLUG must be set."; \
		echo "Example: make seed-test-gym-dev SLUG=dopamineo"; \
		echo ""; \
		echo "Creates tenant \"<slug>\" + three users:"; \
		echo "  owner@<slug>.test   (role: owner)"; \
		echo "  staff@<slug>.test   (role: staff)"; \
		echo "  sales@<slug>.test   (role: sales)"; \
		echo "All with password: TestPass1!"; \
		exit 1; \
	fi
	@$(COMPOSE_DEV) exec -e SLUG backend python -m scripts.seed_test_gym

list-tables-dev:  ## List all tables in the dev database
	@$(COMPOSE_DEV) exec postgres psql -U dopacrm -d dopacrm -c "\dt"

clean-database-dev:  ## Truncate tables (TABLE=<name> or TABLE=all — preserves saas_plans + alembic)
	@if [ -z "$$TABLE" ]; then \
		echo "Error: TABLE must be set."; \
		echo "Examples:"; \
		echo "  make clean-database-dev TABLE=users    # truncate one table"; \
		echo "  make clean-database-dev TABLE=all      # truncate ALL user data"; \
		echo "                                         # (preserves saas_plans + alembic_version)"; \
		echo ""; \
		echo "To see available tables: make list-tables-dev"; \
		exit 1; \
	fi
	@if [ "$$TABLE" = "all" ]; then \
		echo "Truncating all user tables (preserving saas_plans + alembic_version)..."; \
		$(COMPOSE_DEV) exec postgres psql -U dopacrm -d dopacrm -c "\
			DO \$$\$$ \
			DECLARE r RECORD; \
			BEGIN \
				FOR r IN SELECT tablename FROM pg_tables \
					WHERE schemaname = 'public' \
					AND tablename NOT IN ('saas_plans', 'alembic_version') \
				LOOP \
					EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE'; \
					RAISE NOTICE 'truncated %', r.tablename; \
				END LOOP; \
			END \$$\$$;"; \
	else \
		echo "Truncating table: $$TABLE"; \
		$(COMPOSE_DEV) exec postgres psql -U dopacrm -d dopacrm -c "TRUNCATE TABLE $$TABLE CASCADE;"; \
	fi

##@ Logs

logs-dev:  ## Tail logs from all services
	$(COMPOSE_DEV) logs -f

# Per-service logs use the pattern rule above: make logs-backend-dev, logs-postgres-dev, etc.

##@ API types (frontend codegen from backend OpenAPI)

gen-api-types:  ## Regenerate frontend TypeScript types from backend OpenAPI spec
	@echo "Exporting OpenAPI spec from backend..."
	@uv run python -m scripts.export_openapi > /tmp/openapi.json
	@echo "Generating TypeScript types..."
	@cd frontend && npm run gen:api-types
	@echo "✅ frontend/src/lib/api-schema.ts is up to date"

check-api-types:  ## Verify frontend TypeScript types match the live backend OpenAPI
	@uv run python -m scripts.export_openapi > /tmp/openapi.json
	@cd frontend && npm run check:api-types

##@ Testing

test-backend-unit:  ## Backend unit tests (no DB needed)
	uv run pytest backend/tests/unit/ backend/tests/test_health.py -v

test-backend-integration-dev:  ## Backend integration tests (needs Postgres)
	uv run pytest backend/tests/integration/ -v

test-backend-e2e-dev:  ## Backend E2E tests (needs Postgres + Redis)
	uv run pytest backend/tests/e2e/ -v

test-backend-all-dev:  ## All backend tests (needs Postgres + Redis)
	uv run pytest backend/tests/ -v

test-frontend:  ## Frontend tests (Vitest)
	cd frontend && npx vitest run

test-all-dev:  ## ALL tests — backend + frontend
	@echo "── Backend ──"
	@uv run pytest backend/tests/ -v
	@echo ""
	@echo "── Frontend ──"
	@cd frontend && npx vitest run

##@ Load Testing

load-test-auth:  ## Load test auth endpoints (Locust → http://localhost:8089)
	uv run locust -f loadtests/test_auth_load.py --host=http://localhost:8000

load-test-users:  ## Load test users CRUD (Locust → http://localhost:8089)
	uv run locust -f loadtests/test_users_load.py --host=http://localhost:8000

load-test-tenants:  ## Load test tenants CRUD (Locust → http://localhost:8089)
	uv run locust -f loadtests/test_tenants_load.py --host=http://localhost:8000

##@ Info

list-services-dev:  ## List all services and available per-service commands
	@echo ""
	@echo "  Services:"
	@echo ""
	@for svc in $(SERVICES); do \
		printf "    \033[36m%-15s\033[0m" "$$svc"; \
		echo ""; \
	done
	@echo ""
	@echo "  Per-service commands (replace <svc> with a service name above):"
	@echo ""
	@echo "    make up-<svc>-dev          Start one service"
	@echo "    make stop-<svc>-dev        Stop one service"
	@echo "    make restart-<svc>-dev     Restart one service"
	@echo "    make build-<svc>-dev       Build one service image"
	@echo "    make rebuild-<svc>-dev     Build from scratch (--no-cache)"
	@echo "    make logs-<svc>-dev        Tail logs for one service"
	@echo ""
	@echo "  Examples:"
	@echo "    make restart-backend-dev"
	@echo "    make logs-frontend-dev"
	@echo "    make stop-postgres-dev"
	@echo ""

status-dev:  ## Show running containers and their status
	$(COMPOSE_DEV) ps

urls-dev:  ## Show URLs for all dev services
	@echo "DopaCRM — dev service URLs:"
	@echo ""
	@echo "  Frontend (React+Vite)  http://localhost:5173"
	@echo ""
	@echo "  Backend (FastAPI)      http://localhost:8000"
	@echo "  Backend health         http://localhost:8000/health"
	@echo "  Backend docs (Swagger) http://localhost:8000/docs"
	@echo "  Backend redoc          http://localhost:8000/redoc"
	@echo ""
	@echo "  Mongo Express          http://localhost:8081"
	@echo "  RabbitMQ Management    http://localhost:15672  (guest / guest)"
	@echo "  Flower (Celery UI)     http://localhost:5555"
	@echo "  Grafana                http://localhost:3000   (anonymous Admin)"
	@echo "  Loki API               http://localhost:3100"
	@echo ""
	@echo "  MongoDB                localhost:27017  (root / root)"
	@echo "  Postgres               localhost:5432   (dopacrm / dopacrm)"
	@echo "  Redis                  localhost:6379"
	@echo "  RabbitMQ AMQP          localhost:5672   (guest / guest)"
	@echo ""

# ==============================================================================
#  PRODUCTION (future — CI/CD handles deploys, not Make)
# ==============================================================================
