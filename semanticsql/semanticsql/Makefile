.PHONY: help up down fetch-data index warmup eval demo test lint clean

PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

help:
	@echo "SemanticSQL — make targets"
	@echo "  fetch-data   Download Pagila + Chinook SQL dumps into databases/"
	@echo "  up           Start Postgres + MySQL via docker compose"
	@echo "  down         Stop containers"
	@echo "  install      Create backend venv and install deps"
	@echo "  index        (Re)build ChromaDB index from metadata YAML"
	@echo "  warmup       Pre-load Ollama model so first query isn't cold"
	@echo "  serve        Run FastAPI on :8000"
	@echo "  frontend     Run Vite dev server on :5173"
	@echo "  eval         Run the full eval suite (baseline + treatment)"
	@echo "  test         Run pytest"
	@echo "  demo         up + warmup + serve + frontend in parallel"
	@echo "  clean        Remove venvs, caches, ChromaDB"

# ---------------- data ----------------

fetch-data:
	@echo ">> Fetching Pagila..."
	curl -fsSL -o databases/pagila/01-schema.sql https://raw.githubusercontent.com/devrimgunduz/pagila/master/pagila-schema.sql
	curl -fsSL -o databases/pagila/02-data.sql   https://raw.githubusercontent.com/devrimgunduz/pagila/master/pagila-data.sql
	@echo ">> Fetching Chinook (MySQL)..."
	curl -fsSL -o databases/chinook/01-chinook-mysql.sql https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_MySql.sql
	@echo ">> Done."

up:
	docker compose up -d
	@echo "Waiting for databases to be healthy..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' semanticsql_pg)" = "healthy" ] && \
	       [ "$$(docker inspect -f '{{.State.Health.Status}}' semanticsql_mysql)" = "healthy" ]; do \
	    sleep 2; echo "  ...still waiting"; \
	done
	@echo "Databases are healthy."

down:
	docker compose down

# ---------------- python ----------------

install:
	cd backend && python3.11 -m venv .venv && \
	    .venv/bin/pip install -U pip wheel && \
	    .venv/bin/pip install -e .
	cd eval && ../backend/.venv/bin/pip install -e .

index:
	cd backend && .venv/bin/python scripts/index_schemas.py --metadata ../databases/metadata/pagila.yaml  --database pagila
	cd backend && .venv/bin/python scripts/index_schemas.py --metadata ../databases/metadata/chinook.yaml --database chinook

warmup:
	cd backend && .venv/bin/python scripts/warmup_ollama.py

serve:
	cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	cd backend && .venv/bin/pytest -q

# ---------------- frontend ----------------

frontend:
	cd frontend && npm install && npm run dev

# ---------------- eval ----------------

eval:
	cd eval && ../backend/.venv/bin/python run_eval.py

# ---------------- combined ----------------

demo: up warmup
	@echo "Starting backend & frontend. Open http://localhost:5173"
	(cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000) & \
	(cd frontend && npm install && npm run dev)

clean:
	rm -rf backend/.venv backend/chroma_db backend/**/__pycache__ eval/cache/* eval/results/*.csv frontend/node_modules frontend/dist
