# Dev container: the one environment the Makefile and scripts are written for, on
# macOS, Linux and Windows alike. Python packages are NOT installed here; they come
# from uv.lock (`uv sync --locked` runs when the container is created).
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ARG UV_VERSION=0.11.25
ARG DATABRICKS_CLI_VERSION=1.19.0
ARG TARGETARCH

# The base image already has make, git, curl and unzip.

# uv, pinned.
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /usr/local/bin/

# Databricks CLI, pinned (release zip for this CPU architecture).
RUN arch="${TARGETARCH:-$(dpkg --print-architecture)}" \
    && curl -fsSL -o /tmp/databricks.zip \
       "https://github.com/databricks/cli/releases/download/v${DATABRICKS_CLI_VERSION}/databricks_cli_${DATABRICKS_CLI_VERSION}_linux_${arch}.zip" \
    && unzip -q /tmp/databricks.zip databricks -d /usr/local/bin \
    && rm /tmp/databricks.zip \
    && databricks --version

# Directories that devcontainer.json mounts named volumes on. Creating them here,
# owned by the container user, gives new volumes the right owner.
USER vscode
RUN mkdir -p /home/vscode/.databricks /home/vscode/.config/databricks-sdk-py \
             /home/vscode/.cache/uv /home/vscode/venv
