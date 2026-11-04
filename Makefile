# Entry points for developers and CI. Recipes stay thin: logic lives in scripts/ and dbt macros.
# Run `make help` for the list.

# Interactive targets (setup, clean-dev) must not run in parallel, even with `make -j`.
.NOTPARALLEL:
.DEFAULT_GOAL := help
SHELL := bash

UV  ?= uv
DBT := $(UV) run dbt

.PHONY: help
help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: setup
setup: ## Install pinned tools, check the Databricks login, write your personal profiles.yml
	$(UV) sync --locked
	$(UV) run python scripts/setup_dev.py
	$(DBT) deps

.PHONY: clone-sources
clone-sources: ## (Re)create your shallow clones of every source (also fixes clones broken by prod VACUUM)
	$(DBT) -q run-operation clone_sources

.PHONY: build-changed
build-changed: ## Build only what you changed, deferring the rest to product dev (ARGS="..." for dbt)
	$(UV) run python scripts/build_changed.py -- $(ARGS)

.PHONY: clean-dev
clean-dev: ## Drop your whole personal environment (<product>__<alias>__*), after confirmation
	@out="$$($(DBT) -q run-operation drop_personal_environment --args '{dry_run: true}')" \
		|| { echo "$$out"; exit 1; }; \
	echo "$$out"; \
	if [[ "$$out" == "Nothing to drop"* ]]; then exit 0; fi; \
	read -r -p "Type 'yes' to drop them: " answer; \
	if [[ "$$answer" == yes ]]; then \
		$(DBT) -q run-operation drop_personal_environment --args '{dry_run: false}'; \
	else \
		echo "Nothing dropped."; \
	fi

# ---- Local engine: Apache Spark + Postgres metastore in containers (local/compose.yml) ----
# For trying dbt changes without Databricks. podman-compose if installed (it needs no
# podman API socket), else `docker compose`. Override with e.g. COMPOSE_CMD="podman compose".
COMPOSE_CMD ?= $(shell command -v podman-compose >/dev/null 2>&1 && echo podman-compose || echo docker compose)
COMPOSE     ?= $(COMPOSE_CMD) -f local/compose.yml

.PHONY: local-up
local-up: ## Local engine: build the image and start the Postgres metastore
	@if [[ -n "$$DBT_DEVCONTAINER" ]]; then \
		echo "The local engine starts containers of its own: run make local-* on the host, not in the dev container." >&2; exit 1; \
	fi
	$(COMPOSE) build dbt
	$(COMPOSE) up -d metastore-db
	@for i in $$(seq 60); do \
		$(COMPOSE) exec -T metastore-db pg_isready -q -U hive -d metastore 2>/dev/null && exit 0; sleep 1; \
	done; echo "metastore-db did not become ready" >&2; exit 1

.PHONY: local-sources
local-sources: local-up ## Local engine: create the small stand-in `tpch` source tables
	$(COMPOSE) run --rm spark-sql -f /project/local/tpch.sql

.PHONY: local-dbt
local-dbt: local-up ## Local engine: run dbt (default `build`; e.g. ARGS="build --select customers")
	$(COMPOSE) run --rm dbt $(or $(ARGS),build)

.PHONY: local-sql
local-sql: local-up ## Local engine: open a Spark SQL shell on the local catalog
	$(COMPOSE) run --rm spark-sql

.PHONY: local-down
local-down: ## Local engine: stop the containers (keeps the data)
	$(COMPOSE) down

.PHONY: local-clean
local-clean: ## Local engine: stop and delete all local tables and the catalog
	$(COMPOSE) down -v

.PHONY: test-tooling
test-tooling: ## Run the unit tests for the developer tooling in scripts/
	$(UV) run pytest
