# Dev container

Developers may be on macOS, Linux or Windows. The toolkit (`make`, the `dbtp` tooling in `tools/dbtp/`, dbt, the Databricks CLI) is written for one environment only: the Linux dev container in `.devcontainer/`. Use it rather than installing the tools yourself.

## What you need

- Docker Desktop, or Podman (with `podman machine` on macOS/Windows).
- VS Code with the Dev Containers extension, or any tool that reads `devcontainer.json` (the `devcontainer` CLI, JetBrains Gateway).

## Start

1. Clone the repository and open it in VS Code.
2. Run **Dev Containers: Reopen in Container**. The first build takes a few minutes; it then runs `uv sync --locked`.
3. In the container's terminal: `databricks auth login --host <dev-workspace-host>`, `uv run dbtp init`, then `make build` (`make help` lists the commands).

## What's in it

- Python 3.12, `uv` and the Databricks CLI, at the versions pinned in `.devcontainer/Dockerfile`. Python packages come from `uv.lock`.
- The virtual environment is at `/home/vscode/venv`, outside the workspace, so it never clashes with a `.venv` made on your host.
- Login tokens (`~/.databricks`, `~/.config/databricks-sdk-py`) are on named Docker volumes: they survive rebuilds and are never written to the workspace or the image.
- Port 8020 is forwarded: it's where `databricks auth login` and dbt-databricks receive the OAuth callback. VS Code opens the sign-in page in your host browser.
- Port 8080 is forwarded for the dbt docs site (`make docs`).
- `.gitattributes` keeps LF line endings in Windows checkouts, which the Makefile needs.

## Upgrading tools

Change `UV_VERSION`/`DATABRICKS_CLI_VERSION` (and the `uv` image tag) in `.devcontainer/Dockerfile`, then **Dev Containers: Rebuild Container**. Python packages are upgraded in `pyproject.toml` / `uv.lock` as usual.

## Not in the dev container

The local Spark engine (`make local-*`, `local/`) starts containers of its own. Run those targets on the host, where Podman or Docker is. The targets run `uv run dbtp local …`, so the host also needs [uv](https://docs.astral.sh/uv/) (it brings its own Python).
