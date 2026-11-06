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

# ---- Docs: PlantUML diagrams (docs/diagrams/*.puml -> *.svg, both committed) ----
# GitHub and many GitLab instances don't render PlantUML in Markdown, so the docs embed
# the SVGs. Re-run after editing a .puml file. Needs Podman or Docker (run on the host).
CONTAINER      ?= $(shell command -v podman >/dev/null 2>&1 && echo podman || echo docker)
PLANTUML_IMAGE ?= docker.io/plantuml/plantuml:1.2025.4
CONTAINER_USER  = $(if $(findstring podman,$(CONTAINER)),--userns=keep-id,--user $(shell id -u):$(shell id -g))

.PHONY: diagrams
diagrams: ## Render docs/diagrams/*.puml to SVG (Podman or Docker, on the host)
	$(CONTAINER) run --rm $(CONTAINER_USER) -e JAVA_TOOL_OPTIONS=-Duser.home=/tmp -v "$(CURDIR)/docs/diagrams:/data:Z" \
		$(PLANTUML_IMAGE) -tsvg -charset UTF-8 "/data/*.puml"

.PHONY: test-tooling
test-tooling: ## Run the unit tests for the developer tooling in scripts/
	$(UV) run pytest

# ---- Static checks (MR and main pipelines; also fine to run locally) ----

.PHONY: lint
lint: ## Lint SQL (sqlfluff) and YAML (yamllint)
	$(UV) run sqlfluff lint models
	$(UV) run yamllint -s .

.PHONY: parse
parse: ## Offline `dbt parse` with the deployment profile (no connection, no login)
	DBT_HOST=parse.invalid DBT_ACCESS_TOKEN=unused $(DBT) parse --profiles-dir deploy --target mr \
		--vars '{deploy_catalog: parse, deploy_warehouse_id: parse}'

.PHONY: security-scan
security-scan: ## Placeholder for scanners GitLab doesn't provide (GitLab SAST and secret detection run as their own jobs)
	@echo "No extra security scanners configured. GitLab SAST and secret detection run from .gitlab-ci.yml."

# ---- Deployment: Databricks Asset Bundle (databricks.yml, resources/) ----
# TARGET is a bundle target: dev (product dev catalog) or prod (product prod catalog).
# Deploys always go from the unpacked release artifact in target/release/bundle/, so
# a hand deploy ships exactly what a release would: `make artifact bundle-deploy`.
TARGET         ?= dev
DATABRICKS     ?= databricks
RELEASE_BUNDLE := target/release/bundle

.PHONY: artifact
artifact: ## Build the release artifact (VERSION=local) and unpack it into target/release/bundle
	$(DBT) deps
	$(UV) run python scripts/release.py build --version $(or $(VERSION),local)

.PHONY: bundle-validate
bundle-validate: ## Validate the bundle for TARGET (BUNDLE_DIR=target/release/bundle for the artifact)
	cd $(or $(BUNDLE_DIR),.) && $(DATABRICKS) bundle validate -t $(TARGET)

.PHONY: bundle-deploy
bundle-deploy: ## Deploy the unpacked artifact to TARGET (run `make artifact` first)
	@test -f $(RELEASE_BUNDLE)/databricks.yml \
		|| { echo "No unpacked artifact in $(RELEASE_BUNDLE): run make artifact first." >&2; exit 1; }
	cd $(RELEASE_BUNDLE) && $(DATABRICKS) bundle deploy -t $(TARGET)

.PHONY: bundle-run
bundle-run: ## Start the job in TARGET, wait for it; fails if the run fails
	cd $(RELEASE_BUNDLE) && $(DATABRICKS) bundle run -t $(TARGET) dbt_build

# ---- CI only (.gitlab-ci.yml calls these; all pipeline logic lives here and in scripts/) ----
# CI_TOOLS_DIR is where `ci-tools` puts uv and the Databricks CLI.
ifdef CI_TOOLS_DIR
export PATH := $(CI_TOOLS_DIR):$(PATH)
endif

.PHONY: ci-tools
ci-tools: ## CI: install the pinned uv and Databricks CLI, then the locked Python packages
	bash scripts/install_ci_tools.sh
	$(UV) sync --locked

.PHONY: ci-mr-build
ci-mr-build: ## CI: drop <product>__mr__*, then a full dbt build into it (team identity)
	$(UV) run python scripts/mr_build.py $(ARGS)

.PHONY: ci-release-check
ci-release-check: ## CI: refuse a release tag that isn't a valid package version or not on main
	$(UV) run python scripts/release.py check-tag

.PHONY: ci-release-artifact
ci-release-artifact: ## CI: build and upload the release artifact once (re-runs reuse it), unpack it
	$(DBT) deps
	$(UV) run python scripts/release.py publish

.PHONY: ci-release-fetch
ci-release-fetch: ## CI: download this release's artifact from the package registry and unpack it
	$(UV) run python scripts/release.py fetch
