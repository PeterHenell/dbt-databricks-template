# 03: GitLab pipeline with static checks and Databricks login

**What to build:** Every MR and every merge to `main` runs the static checks in GitLab, and GitLab jobs can log in to Databricks without stored secrets.

**Blocked by:** 01 (Bundle deployable to product dev by hand)

**Status:** done (not yet run in GitLab; OIDC only for the team identity, see comment)

- [x] `.gitlab-ci.yml` only calls `make` targets; all logic lives in the Makefile and scripts
- [x] CI uses a standard Python image, installs tools from the `uv` lockfile with caching, and uses a pinned Databricks CLI version
- [x] MR and `main` pipelines run lint (SQL and YAML), `dbt parse`, and bundle validation
- [x] There is a security-scan stage, using GitLab's built-in scanners where available, with a placeholder otherwise
- [x] GitLab jobs log in to Databricks with OIDC workload identity federation. It is confirmed that Databricks accepts GitLab as an issuer, and the federation policy the platform team must create is documented
- [x] The fallback (OAuth client ID and secret in masked, protected CI variables) is documented
- [x] Merging to `main` deploys nothing

## Comments

**2026-11-04 (pending decision, dev-environment#07):** dev-environment#07 proposes that pipeline jobs live in a central GitLab CI/CD component (`include: component: …@1`) running a central platform image, instead of `.gitlab-ci.yml` calling this repo's `make` targets in a standard Python image (conflicts with the first two criteria). Check the status of 07 before implementing; if 07 is still open, ask the user which to follow.

**2026-11-04 (implementation):**
- dev-environment#07 was still `needs-triage`; the user chose to build this as written, in this repo, keeping product-specific values in variables/targets so it can later become a template.
- `.gitlab-ci.yml`: every job only runs `make …`; `python:3.12-bookworm`; `make ci-tools` (`scripts/install_ci_tools.sh`) installs uv and the Databricks CLI at the versions pinned in `.devcontainer/Dockerfile` (one source of truth) into a cached `.cache/tools`; `uv sync --locked` with a cached `UV_CACHE_DIR`.
- MR and `main`: `lint` (`make lint parse`: sqlfluff with the jinja templater + dbt builtins, yamllint, offline `dbt parse` with the deploy profile), `tooling-tests`, `bundle-validate` (team identity), `security-scan` (placeholder target) plus GitLab's SAST and secret-detection templates. `main` deploys nothing (tested in `tests/test_bundle.py`).
- Ran `make ci-tools lint parse test-tooling` in `python:3.12-bookworm` under Podman: green (it caught yamllint scanning `.cache/`, fixed).
- **OIDC finding:** Databricks accepts GitLab as an issuer (docs: dev-tools/auth/provider-gitlab; `env-oidc` + `DATABRICKS_OIDC_TOKEN`; the SDK in `uv.lock` supports it). But Databricks matches the subject *exactly*, and GitLab's `sub` contains the ref. So: team identity uses OIDC with `subject_claim: project_path` (any pipeline of the project; acceptable for the team catalog). Product identities default to the documented fallback (client ID + secret in masked, protected variables, protected release tags), because no policy can express "release tags only" and `project_path` would let any MR log in as prod. Per-identity switch: `<ID>_AUTH_TYPE`. Policy JSON and reasoning: `docs/ci-cd.md`, "Logging in to Databricks". Worth raising with the platform team.
- **Not verified:** a real GitLab run; `project_path` as subject claim (Databricks docs only show `sub`).
