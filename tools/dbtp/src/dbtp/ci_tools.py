"""`make ci-tools`: install uv and the Databricks CLI in a standard Python CI image.

At the versions pinned in `.devcontainer/Dockerfile` (one place for both). Binaries go
to `$CI_TOOLS_DIR` (cached between pipelines); Python packages come from uv.lock.

Standard library only: this runs with the image's plain `python3` before uv, and so
before dbtp itself, is installed:

    python3 tools/dbtp/src/dbtp/ci_tools.py [--dockerfile .devcontainer/Dockerfile]
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

CLI_URL = ("https://github.com/databricks/cli/releases/download/"
           "v{version}/databricks_cli_{version}_linux_{arch}.zip")


def pins(dockerfile: Path) -> tuple[str, str]:
    """(uv version, Databricks CLI version) from the Dockerfile's ARG lines."""
    text = dockerfile.read_text()

    def pin(name: str) -> str:
        match = re.search(rf"^ARG {name}=(\S+)\s*$", text, re.MULTILINE)
        if not match:
            raise SystemExit(f"No ARG {name}=... pin in {dockerfile}")
        return match.group(1)

    return pin("UV_VERSION"), pin("DATABRICKS_CLI_VERSION")


def cli_arch(machine: str | None = None) -> str:
    machine = machine or platform.machine()
    return {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, machine)


def installed_version(binary: Path) -> str:
    try:
        return subprocess.run([str(binary), "--version"], capture_output=True, text=True,
                              check=False).stdout.strip()
    except OSError:
        return ""


def install_uv(tools: Path, version: str) -> None:
    if installed_version(tools / "uv").startswith(f"uv {version}"):
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "--target", str(tools / "uv-pkg"), f"uv=={version}"], check=True)
    link = tools / "uv"
    link.unlink(missing_ok=True)
    link.symlink_to(tools / "uv-pkg" / "bin" / "uv")


def install_databricks_cli(tools: Path, version: str) -> None:
    if installed_version(tools / "databricks") == f"Databricks CLI v{version}":
        return
    url = CLI_URL.format(version=version, arch=cli_arch())
    with tempfile.TemporaryFile() as download:
        with urllib.request.urlopen(url, timeout=300) as response:
            download.write(response.read())
        zipfile.ZipFile(download).extract("databricks", tools)
    (tools / "databricks").chmod(0o755)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dockerfile", type=Path, default=Path(".devcontainer/Dockerfile"))
    args = parser.parse_args(argv)

    uv_version, cli_version = pins(args.dockerfile)
    tools = Path(os.environ.get("CI_TOOLS_DIR") or ".cache/tools").resolve()
    tools.mkdir(parents=True, exist_ok=True)
    install_uv(tools, uv_version)
    install_databricks_cli(tools, cli_version)
    print(installed_version(tools / "uv"))
    print(installed_version(tools / "databricks"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
