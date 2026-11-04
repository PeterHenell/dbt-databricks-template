"""Shared helpers for the personal development environment tooling.

Reads the project's settings (data product name, team-level dev settings) and the
developer's generated `profiles.yml`. Used by `scripts/setup_dev.py` and the Makefile.
"""

from __future__ import annotations

import re
import sys
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT = REPO_ROOT / "dbt_project.yml"
DEV_CONFIG = REPO_ROOT / "config" / "dev-environment.toml"
DEV_PROFILE = REPO_ROOT / "profiles.yml"

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


def read_product() -> str:
    """The data product name: the dbt project name (must equal the profile name)."""
    project = yaml.safe_load(DBT_PROJECT.read_text())
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


def read_dev_config(path: Path = DEV_CONFIG) -> DevConfig:
    data = tomllib.loads(path.read_text())
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


def read_product_dev_catalog(path: Path = DEV_CONFIG) -> str:
    catalog = tomllib.loads(path.read_text()).get("catalogs", {}).get("product_dev", "")
    if not catalog or "<" in catalog:
        raise SetupError(f"{path.name}: set [catalogs] product_dev to the product dev catalog.")
    return catalog


def artifacts_volume_path(catalog: str) -> str:
    """Where job runs publish dbt artifacts in a product catalog (ADR 0006)."""
    return f"/Volumes/{catalog}/_dbt_artifacts/state"


def personal_prefix(product: str, alias: str) -> str:
    """Schema prefix of one developer's personal environment, without the layer."""
    return f"{product}__{alias}"


def alias_from_profile(product: str, path: Path = DEV_PROFILE) -> str | None:
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
        "# Personal dev profile, generated by `make setup`. Gitignored; not shared (ADR 0002).\n"
        "# Your developer alias is the part of `schema` after `<product>__`.\n"
        "# To change it, run `make clean-dev` (drops the old schemas), then edit `schema` here.\n"
    )
    return header + yaml.safe_dump(profile, sort_keys=False)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)
