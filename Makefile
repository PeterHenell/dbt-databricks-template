# Daily developer commands. Every recipe runs dbt or forwards to the `dbtp` tooling
# (tools/dbtp, installed by `uv sync`); no logic lives here. `make help` lists them.
#
# Not here on purpose: CI-only steps (release, MR build, deploy) are called as
# `uv run dbtp …` straight from .gitlab-ci.yml, and rarely used commands (hand deploy,
# rendering the diagrams) are in the docs (docs/ci-cd.md, docs/workflows.md).

# Interactive targets (setup, clean-dev) must not run in parallel, even with `make -j`.
.NOTPARALLEL:
.DEFAULT_GOAL := help
SHELL := bash

UV   ?= uv
DBT  := $(UV) run dbt
DBTP := $(UV) run dbtp

# Options for the dbt targets below:
#   SELECT="customers+"   dbt --select
#   SOURCE_MODE=prod      read prod sources instead of your clones (dev_source_mode)
#   ARGS="--full-refresh" anything else, passed on to dbt
DBT_OPTS = $(if $(SELECT),--select $(SELECT)) \
           $(if $(SOURCE_MODE),--vars '{dev_source_mode: $(SOURCE_MODE)}') $(ARGS)

.PHONY: help
help: ## List the targets
	@awk 'BEGIN {FS = ":.*## "} \
		/^##@ / {printf "\n%s\n", substr($$0, 5)} \
		/^[a-zA-Z_-]+:.*## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "dbt targets take SELECT=..., SOURCE_MODE=prod and ARGS=\"...\", e.g. make build SELECT=+customers"

##@ Setup

.PHONY: setup
setup: ## Install pinned tools, check the Databricks login, write your personal profiles.yml
	$(UV) sync --locked
	$(DBTP) setup

# The dbt targets need the profile `make setup` writes.
profiles.yml:
	@echo "No profiles.yml yet: run \`make setup\` first." >&2; exit 1

##@ dbt in your personal environment on Databricks (<product>__<alias>__*)

.PHONY: build run test compile docs debug
build: profiles.yml ## dbt build: models, tests, seeds and snapshots
	$(DBT) build $(DBT_OPTS)
run: profiles.yml ## dbt run: models only
	$(DBT) run $(DBT_OPTS)
test: profiles.yml ## dbt test: data and unit tests
	$(DBT) test $(DBT_OPTS)
compile: profiles.yml ## dbt compile: write the compiled SQL to target/compiled/
	$(DBT) compile $(DBT_OPTS)
docs: profiles.yml ## dbt docs generate, then serve the site on http://localhost:8080
	$(DBT) docs generate $(DBT_OPTS)
	$(DBT) docs serve --port 8080
debug: profiles.yml ## dbt debug: check your profile and the connection to the SQL warehouse
	$(DBT) debug

.PHONY: build-changed clone-sources clean-dev
build-changed: profiles.yml ## Build only what you changed, deferring the rest to product dev
	$(DBTP) build-changed -- $(ARGS)
clone-sources: profiles.yml ## (Re)create your shallow clones of every source (also after a prod VACUUM)
	$(DBTP) clone-sources
clean-dev: profiles.yml ## Drop your whole personal environment, after confirmation
	$(DBTP) clean-dev

##@ Checks (the MR pipeline runs these too)

.PHONY: lint parse test-tooling
lint: ## Lint SQL (sqlfluff) and YAML (yamllint)
	$(UV) run sqlfluff lint models
	$(UV) run yamllint -s .
parse: ## Offline `dbt parse` with the deployment profile (no connection, no login)
	$(DBTP) parse
test-tooling: ## Tests of the tooling (tools/dbtp) and of the macros, bundle and CI config
	$(UV) run pytest

##@ Local engine: Spark + Delta in containers, no Databricks (run on the host)

# COMPOSE_CMD="podman compose" overrides the compose command
# (default: podman-compose if installed, else docker compose).
export COMPOSE_CMD

.PHONY: local-up local-sources local-dbt local-sql local-down local-clean
local-up: ## Build the image and start the Postgres metastore
	$(DBTP) local up
local-sources: ## Create the local stand-in source tables (local/sources.sql)
	$(DBTP) local sources
local-dbt: ## Run dbt locally (default `build`; e.g. ARGS="build --select customers")
	$(DBTP) local dbt $(ARGS)
local-sql: ## Open a Spark SQL shell on the local catalog
	$(DBTP) local sql
local-down: ## Stop the containers (keeps the data)
	$(DBTP) local down
local-clean: ## Stop and delete all local tables and the catalog
	$(DBTP) local clean
