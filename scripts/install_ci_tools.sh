#!/usr/bin/env bash
# `make ci-tools`: install uv and the Databricks CLI in a standard Python CI image, at
# the versions pinned in .devcontainer/Dockerfile (one place for both). Binaries go
# to $CI_TOOLS_DIR (cached between pipelines); Python packages come from uv.lock.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
dockerfile="$root/.devcontainer/Dockerfile"
pin() { sed -n "s/^ARG $1=//p" "$dockerfile"; }
uv_version="$(pin UV_VERSION)"
cli_version="$(pin DATABRICKS_CLI_VERSION)"
[[ -n "$uv_version" && -n "$cli_version" ]] || { echo "No version pins in $dockerfile" >&2; exit 1; }

dir="${CI_TOOLS_DIR:-$root/.cache/tools}"
mkdir -p "$dir"

if [[ "$("$dir/uv" --version 2>/dev/null)" != "uv $uv_version"* ]]; then
    python3 -m pip install --quiet --disable-pip-version-check --target "$dir/uv-pkg" "uv==$uv_version"
    ln -sf "$dir/uv-pkg/bin/uv" "$dir/uv"
fi

if [[ "$("$dir/databricks" --version 2>/dev/null)" != "Databricks CLI v$cli_version" ]]; then
    case "$(uname -m)" in x86_64) arch=amd64 ;; aarch64 | arm64) arch=arm64 ;; *) arch="$(uname -m)" ;; esac
    url="https://github.com/databricks/cli/releases/download/v${cli_version}/databricks_cli_${cli_version}_linux_${arch}.zip"
    curl -fsSL -o "$dir/databricks.zip" "$url"
    python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extract("databricks", sys.argv[2])' "$dir/databricks.zip" "$dir"
    chmod +x "$dir/databricks"
    rm "$dir/databricks.zip"
fi

"$dir/uv" --version
"$dir/databricks" --version
