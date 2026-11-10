import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def dbt_packages():
    """Install the project's dbt packages (the platform macros, a `local:` package, so
    no network), as `make setup` does; the dbt runs in these tests need them."""
    subprocess.run(["dbt", "-q", "deps"], cwd=REPO_ROOT, check=True, timeout=180)
