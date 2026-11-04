# 06: Dev container for macOS, Linux and Windows

**What to build:** Developers may be on macOS, Linux or Windows. Instead of each of them installing make, uv, Python and the Databricks CLI (and the Makefile and scripts having to cope with three shells), the repository ships a Docker-based dev container in which `make setup`, `uv run dbt build` and every other `make` target work the same everywhere.

**Blocked by:** 01 (Minimal end-to-end skeleton)

**Status:** done (VS Code and OAuth in the container not yet tried)

- [ ] `.devcontainer/` (Dockerfile + `devcontainer.json`) opens in VS Code "Reopen in Container" and with the `devcontainer` CLI; it works with Docker Desktop and Podman
- [x] The image pins the tool versions: Python 3.12, `uv`, the Databricks CLI, `make`, `git`. Python packages still come from `uv.lock` (`uv sync --locked` after the container is created)
- [x] The container's virtual environment lives outside the workspace, so a host `.venv` (other OS) and the container's never clash
- [ ] OAuth user-to-machine login works from inside the container: `databricks auth login` and dbt-databricks' browser login complete through the forwarded `localhost:8020` callback, and the browser opens on the host
- [x] Logins survive rebuilding the container (token caches on named volumes); no credentials are written into the workspace or the image
- [x] Files keep LF line endings on Windows checkouts (`.gitattributes`), so the Makefile and shell recipes run in the container
- [x] Files created in the container are owned by the developer on the host (non-root container user, UID matched)
- [x] CLAUDE.md and the docs say the dev container is the supported way to run the toolkit; running on the host stays possible

**Out of scope:** the local Spark engine (`make local-*`) starts containers of its own and stays a host command for now; running it from inside the dev container would need Docker-outside-of-Docker and host path mapping.

## Comments

**2026-11-04 (implementation):**
- `.devcontainer/Dockerfile` (base `mcr.microsoft.com/devcontainers/python:1-3.12-bookworm`, user `vscode`; pinned uv 0.11.25 and Databricks CLI 1.19.0) and `.devcontainer/devcontainer.json` (venv at `/home/vscode/venv` via `UV_PROJECT_ENVIRONMENT`, named volumes for `~/.databricks`, `~/.config/databricks-sdk-py`, the uv cache and the venv; port 8020 forwarded; `postCreateCommand: uv sync --locked`). `.gitattributes` forces LF. Docs: `docs/dev-container.md`.
- The base image's yarn apt repository has an expired key, so the Dockerfile doesn't run apt at all (make, git, curl, unzip are already in the image).
- `make local-*` refuses to run inside the dev container (`DBT_DEVCONTAINER=1`), with a message to run it on the host.
- Verified with Podman, by running the image with the same env, volumes and UID mapping as `devcontainer.json`: tool versions, `uv sync --locked`, `make help`, `make test-tooling` (36 passed), `make setup` error path, host `.venv` untouched, files created in the container owned by the host user.
- **Not verified:** opening it with VS Code or the `devcontainer` CLI (not available in this session), Docker Desktop on macOS/Windows, and the OAuth browser login through the forwarded port.

**2026-11-04 (pending decision, dev-environment#07):** dev-environment#07 proposes moving the image (`.devcontainer/Dockerfile`) to the platform repo as `…/dbt-platform:1`, also used as the CI image, with `dbtp` preinstalled. `devcontainer.json` (mounts, forwarded port 8020) stays in the product repo and switches from `build` to `image`.
