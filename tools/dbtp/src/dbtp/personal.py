"""The developer's personal environment: `dbtp clone-sources` and `dbtp clean-dev`.

The work itself is done by the project's dbt macros (`clone_sources`,
`drop_personal_environment`); these commands run them and ask before dropping.
"""

from __future__ import annotations

import subprocess
from typing import Callable

from dbtp import devenv
from dbtp.devenv import Project


def clone_sources(project: Project) -> int:
    """(Re)create the developer's shallow clones of every source (dev-environment#04)."""
    return devenv.run(["dbt", "-q", "run-operation", "clone_sources"], project)


def drop_command(dry_run: bool) -> list[str]:
    return ["dbt", "-q", "run-operation", "drop_personal_environment",
            "--args", f"{{dry_run: {'true' if dry_run else 'false'}}}"]


def clean_dev(project: Project, ask: Callable[[str], str] = input) -> int:
    """Show what would be dropped, then drop it only after the developer types `yes`."""
    preview = subprocess.run(drop_command(dry_run=True), cwd=project.root,
                             stdout=subprocess.PIPE, text=True, check=False)
    output = preview.stdout.rstrip("\n")
    print(output)
    if preview.returncode != 0:
        return preview.returncode
    if output.startswith("Nothing to drop"):
        return 0
    if ask("Type 'yes' to drop them: ").strip() != "yes":
        print("Nothing dropped.")
        return 0
    return subprocess.call(drop_command(dry_run=False), cwd=project.root)
