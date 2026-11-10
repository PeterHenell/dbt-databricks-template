# Entry points for developers and CI. Every recipe forwards to the `dbtp` tooling
# (tools/dbtp, installed by `uv sync`) or calls one tool directly; no logic lives here.
# Run `make help` for the list, `uv run dbtp --help` for the tooling's own options.

# Interactive targets (setup, clean-dev) must not run in parallel, even with `make -j`.
.NOTPARALLEL:
.DEFAULT_GOAL := help
SHELL := bash

UV   ?= uv
DBT  := $(UV) run dbt
DBTP := $(UV) run dbtp

# CI_TOOLS_DIR is where `ci-tools` puts uv and the Databricks CLI.
ifdef CI_TOOLS_DIR
export PATH := $(CI_TOOLS_DIR):$(PATH)
endif

.PHONY: help
help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- Personal development environment ----

.PHONY: setup
setup: ## Install pinned tools, check the Databricks login, write your personal profiles.yml
	$(UV) sync --locked
	$(DBTP) setup

.PHONY: clone-sources
clone-sources: ## (Re)create your shallow clones of every source (also fixes clones broken by prod VACUUM)
	$(DBTP) clone-sources

.PHONY: build-changed
build-changed: ## Build only what you changed, deferring the rest to product dev (ARGS="..." for dbt)
	$(DBTP) build-changed -- $(ARGS)

.PHONY: clean-dev
clean-dev: ## Drop your whole personal environment (<product>__<alias>__*), after confirmation
	$(DBTP) clean-dev

# ---- Local engine: Apache Spark + Postgres metastore in containers (local/compose.yml) ----
# Run on the host, not in the dev container. COMPOSE_CMD="podman compose" overrides the
# compose command (default: podman-compose if installed, else docker compose).
export COMPOSE_CMD

.PHONY: local-up local-sources local-dbt local-sql local-down local-clean
local-up: ## Local engine: build the image and start the Postgres metastore
	$(DBTP) local up
local-sources: ## Local engine: create the small stand-in `tpch` source tables
	$(DBTP) local sources
local-dbt: ## Local engine: run dbt (default `build`; e.g. ARGS="build --select customers")
	$(DBTP) local dbt $(ARGS)
local-sql: ## Local engine: open a Spark SQL shell on the local catalog
	$(DBTP) local sql
local-down: ## Local engine: stop the containers (keeps the data)
	$(DBTP) local down
local-clean: ## Local engine: stop and delete all local tables and the catalog
	$(DBTP) local clean

# ---- Checks (MR and main pipelines; also fine to run locally) ----

.PHONY: test-tooling
test-tooling: ## Run the tests of the tooling (tools/dbtp) and of the project's macros, bundle and CI config
	$(UV) run pytest

.PHONY: lint
lint: ## Lint SQL (sqlfluff) and YAML (yamllint)
	$(UV) run sqlfluff lint models
	$(UV) run yamllint -s .

.PHONY: parse
parse: ## Offline `dbt parse` with the deployment profile (no connection, no login)
	$(DBTP) parse

.PHONY: security-scan
security-scan: ## Placeholder for scanners GitLab doesn't provide (GitLab SAST and secret detection run as their own jobs)
	@echo "No extra security scanners configured. GitLab SAST and secret detection run from .gitlab-ci.yml."

# ---- Deployment: Databricks Asset Bundle (databricks.yml, resources/) ----
# TARGET is a bundle target: dev (product dev catalog) or prod (product prod catalog).
# Deploys always go from the unpacked release artifact in target/release/bundle/, so
# a hand deploy ships exactly what a release would: `make artifact bundle-deploy`.
TARGET ?= dev

.PHONY: artifact
artifact: ## Build the release artifact (VERSION=local) and unpack it into target/release/bundle
	$(DBTP) release build --version $(or $(VERSION),local)

.PHONY: bundle-validate
bundle-validate: ## Validate the bundle for TARGET (BUNDLE_DIR=target/release/bundle for the artifact)
	$(DBTP) bundle validate -t $(TARGET) $(if $(BUNDLE_DIR),--dir $(BUNDLE_DIR))

.PHONY: bundle-deploy
bundle-deploy: ## Deploy the unpacked artifact to TARGET (run `make artifact` first)
	$(DBTP) bundle deploy -t $(TARGET)

.PHONY: bundle-run
bundle-run: ## Start the job in TARGET, wait for it; fails if the run fails
	$(DBTP) bundle run -t $(TARGET)

# ---- CI only (.gitlab-ci.yml calls these) ----

.PHONY: ci-tools
ci-tools: ## CI: install the pinned uv and Databricks CLI, then the locked Python packages
	python3 tools/dbtp/src/dbtp/ci_tools.py
	$(UV) sync --locked

.PHONY: ci-mr-build
ci-mr-build: ## CI: drop <product>__mr__*, then a full dbt build into it (team identity)
	$(DBTP) mr-build -- $(ARGS)

.PHONY: ci-release-check
ci-release-check: ## CI: refuse a release tag that isn't a valid package version or not on main
	$(DBTP) release check-tag

.PHONY: ci-release-artifact
ci-release-artifact: ## CI: build and upload the release artifact once (re-runs reuse it), unpack it
	$(DBTP) release publish

.PHONY: ci-release-fetch
ci-release-fetch: ## CI: download this release's artifact from the package registry and unpack it
	$(DBTP) release fetch

# ---- Docs: PlantUML diagrams (docs/diagrams/*.puml -> *.svg, both committed) ----
# Template documentation, not product tooling. GitHub and many GitLab instances don't
# render PlantUML in Markdown, so the docs embed the SVGs. Re-run after editing a .puml
# file. Needs Podman or Docker (run on the host).
CONTAINER      ?= $(shell command -v podman >/dev/null 2>&1 && echo podman || echo docker)
PLANTUML_IMAGE ?= docker.io/plantuml/plantuml:1.2025.4
CONTAINER_USER  = $(if $(findstring podman,$(CONTAINER)),--userns=keep-id,--user $(shell id -u):$(shell id -g))

.PHONY: diagrams
diagrams: ## Render docs/diagrams/*.puml to SVG (Podman or Docker, on the host)
	$(CONTAINER) run --rm $(CONTAINER_USER) -e JAVA_TOOL_OPTIONS=-Duser.home=/tmp -v "$(CURDIR)/docs/diagrams:/data:Z" \
		$(PLANTUML_IMAGE) -tsvg -charset UTF-8 "/data/*.puml"
