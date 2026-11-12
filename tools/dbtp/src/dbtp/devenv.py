"""The data product repository dbtp works on, and its settings.

dbtp is installed into a product repository's environment and finds the repository
from the working directory: the nearest directory upwards that has `dbt_project.yml`,
or `$DBTP_PROJECT_DIR` when set. Everything here reads that repository's files: the
data product name (`dbt_project.yml`), the team's dev settings
(`config/dev-environment.toml`) and the developer's generated `profiles.yml`.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_DIR_ENV = "DBTP_PROJECT_DIR"

# Lowercase ASCII words joined by single underscores: never `__`, which separates
# product, alias and layer in schema names (ADR 0001).
NAME_PATTERN = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")

# Aliases that would collide with schemas the template itself uses.
RESERVED_ALIASES = {"mr"}  # `<product>__mr__*` holds the shared MR builds (ADR 0009).

# Letters that Unicode decomposition does not reduce to ASCII.
_EXTRA_ASCII = str.maketrans(
    {"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss",
     "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "þ": "th", "Þ": "TH", "ð": "d", "Ð": "D"}
)


class SetupError(Exception):
    """A problem the developer has to fix; printed without a traceback."""


@dataclass(frozen=True)
class Project:
    """A data product repository: the dbt project plus the files dbtp reads in it."""

    root: Path

    @classmethod
    def at(cls, root: Path) -> "Project":
        root = Path(root).resolve()
        if not (root / "dbt_project.yml").is_file():
            raise SetupError(f"{root} has no dbt_project.yml: not a data product repository.")
        return cls(root)

    @classmethod
    def find(cls, start: Path | None = None) -> "Project":
        """`$DBTP_PROJECT_DIR`, else the nearest directory from `start` (cwd) up with dbt_project.yml."""
        if configured := os.environ.get(PROJECT_DIR_ENV):
            return cls.at(Path(configured))
        here = (start or Path.cwd()).resolve()
        for candidate in (here, *here.parents):
            if (candidate / "dbt_project.yml").is_file():
                return cls(candidate)
        raise SetupError(
            f"No dbt_project.yml in {here} or any parent directory. Run dbtp inside a data "
            f"product repository, or set {PROJECT_DIR_ENV}."
        )

    @property
    def dbt_project(self) -> Path:
        return self.root / "dbt_project.yml"

    @property
    def dev_config(self) -> Path:
        return self.root / "config" / "dev-environment.toml"

    @property
    def dev_profile(self) -> Path:
        """The developer's own profile, written by `dbtp init` (gitignored, ADR 0002)."""
        return self.root / "profiles.yml"

    @property
    def target_dir(self) -> Path:
        return self.root / "target"

    def product(self) -> str:
        return read_product(self.dbt_project)


def to_ascii_letters(text: str) -> str:
    """Lowercase ASCII letters and digits of `text` (`Öberg` -> `oberg`)."""
    decomposed = unicodedata.normalize("NFKD", text.translate(_EXTRA_ASCII))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def suggest_alias(first_name: str, last_name: str) -> str:
    """First two letters of the first name plus the first two of the last name."""
    return to_ascii_letters(first_name)[:2] + to_ascii_letters(last_name)[:2]


def split_display_name(display_name: str) -> tuple[str, str]:
    """`Peter Henell` -> (`Peter`, `Henell`); last word is the last name."""
    parts = display_name.split()
    if len(parts) < 2:
        return (parts[0] if parts else "", "")
    return parts[0], parts[-1]


def validate_alias(alias: str) -> str | None:
    """Return an error message, or None if the alias is usable."""
    if not alias:
        return "The alias can't be empty."
    if not NAME_PATTERN.match(alias):
        return (
            "Use lowercase letters and digits, optionally joined by single underscores "
            "(no '__', no leading or trailing '_')."
        )
    if alias in RESERVED_ALIASES:
        return f"'{alias}' is reserved by the template."
    return None


def read_product(path: Path) -> str:
    """The data product name: the dbt project name (must equal the profile name)."""
    project = yaml.safe_load(path.read_text()) or {}
    name, profile = project.get("name"), project.get("profile")
    if name != profile:
        raise SetupError(
            f"dbt_project.yml: `name` ({name}) and `profile` ({profile}) must both be the "
            "data product name."
        )
    if not NAME_PATTERN.match(name or ""):
        raise SetupError(
            f"dbt_project.yml: product name '{name}' must be lowercase letters and digits "
            "joined by single underscores."
        )
    return name


@dataclass(frozen=True)
class DevConfig:
    host: str  # with scheme, e.g. https://adb-123.azuredatabricks.net
    warehouse_id: str
    team_catalog: str

    @property
    def hostname(self) -> str:
        return re.sub(r"^https?://", "", self.host).rstrip("/")

    @property
    def http_path(self) -> str:
        return f"/sql/1.0/warehouses/{self.warehouse_id}"


def _read_toml(path: Path) -> dict:
    if not path.is_file():
        raise SetupError(f"{path} is missing: it holds the team's dev workspace settings.")
    return tomllib.loads(path.read_text())


def read_dev_config(path: Path) -> DevConfig:
    data = _read_toml(path)
    try:
        config = DevConfig(
            host=data["databricks"]["host"].rstrip("/"),
            warehouse_id=data["databricks"]["warehouse_id"],
            team_catalog=data["catalogs"]["team"],
        )
    except KeyError as missing:
        raise SetupError(f"{path.name}: missing setting {missing}") from None
    for value in (config.host, config.warehouse_id, config.team_catalog):
        if "<" in value:
            raise SetupError(
                f"{path.name} still has template placeholders ({value}). "
                "Fill in the team's dev workspace settings first."
            )
    if not config.host.startswith("https://"):
        raise SetupError(f"{path.name}: host must start with https://")
    return config


def read_product_dev_catalog(path: Path) -> str:
    catalog = _read_toml(path).get("catalogs", {}).get("product_dev", "")
    if not catalog or "<" in catalog:
        raise SetupError(f"{path.name}: set [catalogs] product_dev to the product dev catalog.")
    return catalog


def artifacts_volume_path(catalog: str) -> str:
    """Where job runs publish dbt artifacts in a product catalog (ADR 0006)."""
    return f"/Volumes/{catalog}/_dbt_artifacts/state"


def personal_prefix(product: str, alias: str) -> str:
    """Schema prefix of one developer's personal environment, without the layer."""
    return f"{product}__{alias}"


def alias_from_profile(product: str, path: Path) -> str | None:
    """The alias in an existing dev profile (`schema: <product>__<alias>`), if any."""
    if not path.exists():
        return None
    try:
        profile = yaml.safe_load(path.read_text()) or {}
        schema = profile[product]["outputs"]["dev"]["schema"]
    except (yaml.YAMLError, KeyError, TypeError):
        return None
    prefix = f"{product}__"
    if not isinstance(schema, str) or not schema.startswith(prefix):
        return None
    return schema[len(prefix):] or None


def render_profile(product: str, alias: str, config: DevConfig) -> str:
    profile = {
        product: {
            "target": "dev",
            "outputs": {
                "dev": {
                    "type": "databricks",
                    "host": config.hostname,
                    "http_path": config.http_path,
                    "catalog": config.team_catalog,
                    "schema": personal_prefix(product, alias),
                    "auth_type": "oauth",
                    "threads": 8,
                }
            },
        }
    }
    header = (
        "# Personal dev profile, generated by `uv run dbtp init`. Gitignored; not shared (ADR 0002).\n"
        "# Your developer alias is the part of `schema` after `<product>__`.\n"
        "# To change it, run `make clean-dev` (drops the old schemas), then edit `schema` here.\n"
    )
    return header + yaml.safe_dump(profile, sort_keys=False)


def run(command: list[str], project: Project, env: dict[str, str] | None = None) -> int:
    """Run `command` in the project root, echoing it first; returns the exit code."""
    print("+ " + shlex.join(command), flush=True)
    return subprocess.call(command, cwd=project.root, env=env)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)
