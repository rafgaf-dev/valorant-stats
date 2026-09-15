.PHONY: help install dev api frontend build check clean

PYTHON ?= python3
NPM ?= corepack npm
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
FRONTEND_HOST ?= 127.0.0.1
FRONTEND_PORT ?= 5173

help:
	@printf '%s\n' \
		'make install   Install frontend dependencies' \
		'make dev       Run the local API and React app' \
		'make api       Run only the local API' \
		'make frontend  Run only the Vite frontend' \
		'make build     Create a production frontend build' \
		'make check     Run syntax and formatting checks'

install:
	$(NPM) --prefix frontend install

api:
	API_HOST=$(API_HOST) API_PORT=$(API_PORT) $(PYTHON) lambda/api/local_server.py

frontend:
	VITE_API_BASE_URL=http://$(API_HOST):$(API_PORT) $(NPM) --prefix frontend run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT)

dev: install
	@set -e; \
	API_HOST=$(API_HOST) API_PORT=$(API_PORT) $(PYTHON) lambda/api/local_server.py & api_pid=$$!; \
	trap 'kill $$api_pid 2>/dev/null || true' EXIT INT TERM; \
	VITE_API_BASE_URL=http://$(API_HOST):$(API_PORT) $(NPM) --prefix frontend run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT)

build:
	$(NPM) --prefix frontend run build

check:
	git diff --check
	$(PYTHON) -m compileall -q lambda

clean:
	rm -rf frontend/dist frontend/.vite