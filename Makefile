# --------------------------------------------------------------------------
# KONE ELEVATE - developer task runner
#
#   make help          list every target
#   make setup         install backend + frontend dependencies
#   make demo          committed models -> seed -> ready for the walkthrough
#   make retrain       regenerate the dataset and retrain both models
#   make dev           run backend and frontend together
# --------------------------------------------------------------------------

SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
# Prefer backend/.venv when it exists (recipes run from inside backend/):
# Scripts/ on Windows (Git Bash / MSYS2 make), bin/ everywhere else.
ifneq ($(wildcard $(BACKEND)/.venv/Scripts/python.exe),)
PYTHON ?= .venv/Scripts/python.exe
else ifneq ($(wildcard $(BACKEND)/.venv/bin/python),)
PYTHON ?= .venv/bin/python
else
PYTHON ?= python
endif
NPM ?= npm

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-frontend data train train-forecast models retrain check-models \
        seed reset-seed seed-users demo \
        backend frontend dev test test-backend test-frontend build lint \
        migrate migration docker-up docker-down docker-logs docker-rebuild clean

## ---------------------------------------------------------------- help
help:  ## Show this help
	@echo ""
	@echo "KONE ELEVATE - Component Passport (prototype)"
	@echo "--------------------------------------------------------------"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

## --------------------------------------------------------------- setup
setup: setup-backend setup-frontend  ## Install all dependencies

setup-backend:  ## Install the exact pinned Python dependencies (requirements.lock)
	cd $(BACKEND) && $(PYTHON) -m pip install -r requirements.lock

setup-frontend:  ## Install Node dependencies
	cd $(FRONTEND) && $(NPM) install

## ------------------------------------------------------------------ ml
data:  ## Generate the synthetic degradation dataset (10,000 records)
	cd $(BACKEND) && $(PYTHON) scripts/generate_data.py

train:  ## Train, evaluate and save the Random Forest model
	cd $(BACKEND) && $(PYTHON) scripts/train_model.py

train-forecast:  ## Train the Weibull end-of-life forecast model
	cd $(BACKEND) && $(PYTHON) scripts/train_forecast.py

check-models:  ## Check the committed models load under the installed versions
	cd $(BACKEND) && $(PYTHON) scripts/check_models.py

models:  ## Use the committed models; retrain only if missing or incompatible
	@cd $(BACKEND) && $(PYTHON) scripts/check_models.py || ( \
	    echo "Retraining (committed models missing or built with other versions)" && \
	    $(PYTHON) scripts/train_model.py && $(PYTHON) scripts/train_forecast.py )

retrain: data train train-forecast  ## Regenerate the dataset and retrain both models

## ------------------------------------------------------------ database
migrate:  ## Apply database migrations
	cd $(BACKEND) && $(PYTHON) -m alembic upgrade head

migration:  ## Create a migration: make migration m="add x"
	cd $(BACKEND) && $(PYTHON) -m alembic revision --autogenerate -m "$(m)"

seed:  ## Seed the demo portfolio (60 components)
	cd $(BACKEND) && $(PYTHON) scripts/seed_database.py

reset-seed:  ## Drop everything and reseed from scratch
	cd $(BACKEND) && $(PYTHON) scripts/seed_database.py --reset

seed-users:  ## Create the five demo sign-in accounts (one per role)
	cd $(BACKEND) && $(PYTHON) scripts/seed_users.py

demo: models reset-seed seed-users  ## Demo prep: committed models, components, accounts
	@echo ""
	@echo "Demo data ready. Start the stack with: make dev"
	@echo "Sign in at http://localhost:5173 - the five demo accounts are"
	@echo "listed on the sign-in screen. Password: elevate-demo-2026"

## ------------------------------------------------------------- running
backend:  ## Run the FastAPI server (http://localhost:8000)
	cd $(BACKEND) && $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:  ## Run the Vite dev server (http://localhost:5173)
	cd $(FRONTEND) && $(NPM) run dev

dev:  ## Run backend and frontend together
	@echo "Backend  -> http://localhost:8000/docs"
	@echo "Frontend -> http://localhost:5173"
	@( cd $(BACKEND) && $(PYTHON) -m uvicorn app.main:app --reload --port 8000 & \
	   cd $(FRONTEND) && $(NPM) run dev ; \
	   wait )

## ------------------------------------------------------------- testing
test: test-backend test-frontend  ## Run every test suite

test-backend:  ## Run the pytest suite
	cd $(BACKEND) && $(PYTHON) -m pytest -q

test-frontend:  ## Run the Vitest suite
	cd $(FRONTEND) && $(NPM) run test

build:  ## Production build of the frontend
	cd $(FRONTEND) && $(NPM) run build

lint:  ## Lint the frontend
	cd $(FRONTEND) && $(NPM) run lint

## -------------------------------------------------------------- docker
docker-up:  ## Start the whole stack with Docker Compose
	docker compose up --build

docker-down:  ## Stop the stack
	docker compose down

docker-rebuild:  ## Rebuild images from scratch and start
	docker compose build --no-cache && docker compose up

docker-logs:  ## Tail service logs
	docker compose logs -f

## --------------------------------------------------------------- clean
clean:  ## Remove caches, build output and generated artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND)/.pytest_cache $(FRONTEND)/dist $(FRONTEND)/.vite
	rm -f $(BACKEND)/kone_elevate.db
	@echo "Cleaned. Reseed the demo data with: make demo"
