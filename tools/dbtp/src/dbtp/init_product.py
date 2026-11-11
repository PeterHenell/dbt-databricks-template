"""`dbtp init`: turn a fresh copy of the template into one data product's repository.

Run once, right after creating the repository from the template:

1. Renames the data product: the current dbt project name (the template ships a
   working sample name) is replaced in every file that must repeat it.
2. Writes the team's dev settings into `config/dev-environment.toml`.
3. Fills the `dev` target of `databricks.yml` with the same dev workspace host and
   product dev catalog, if it still has the template's placeholders.

It can be run again, e.g. to rename the product: it always starts from the name that
is in `dbt_project.yml` now. Values not given are asked for; with `--yes`, values not
given are left as they are.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dbtp import devenv
from dbtp.devenv import Project, SetupError

# Files that must repeat the data product name (relative to the repository root).
# Missing files are skipped, so a product that drops e.g. the local engine still works.
PRODUCT_NAME_FILES = (
    "dbt_project.yml",       # name, profile, the `models:` block
    "deploy/profiles.yml",   # profile name, the `mr` target's schema `<product>__mr`
    "databricks.yml",        # bundle.name
    "local/profiles.yml",    # profile name, local schema prefix
)

DEV_CONFIG_KEYS = {  # setting -> key in config/dev-environment.toml
    "host": "host",
    "warehouse_id": "warehouse_id",
    "team_catalog": "team",
    "product_dev_catalog": "product_dev",
}

# Placeholders in the `dev` target of databricks.yml that the dev settings answer.
BUNDLE_DEV_PLACEHOLDERS = {
    "host": "https://<dev-workspace-host>",
    "product_dev_catalog": "<product_dev_catalog>",
}


@dataclass
class Settings:
    product: str
    host: str | None = None
    warehouse_id: str | None = None
    team_catalog: str | None = None
    product_dev_catalog: str | None = None


def rename_in_text(text: str, old: str, new: str) -> str:
    """Replace the product name `old` where it is a whole name or a schema prefix (`old__…`)."""
    pattern = re.compile(rf"(?<![a-z0-9_]){re.escape(old)}(?=__|[^a-z0-9_]|$)")
    return pattern.sub(new, text)


def set_toml_value(text: str, key: str, value: str) -> str:
    """Set `key = "…"` in place, keeping the file's comments and layout."""
    pattern = re.compile(rf'^({re.escape(key)}\s*=\s*)"[^"\n]*"', re.MULTILINE)
    if not pattern.search(text):
        raise SetupError(f"config/dev-environment.toml has no `{key}` setting to fill in.")
    return pattern.sub(lambda m: f'{m.group(1)}"{value}"', text, count=1)


def validate(settings: Settings) -> None:
    if not devenv.NAME_PATTERN.match(settings.product):
        raise SetupError(
            f"Product name '{settings.product}' must be lowercase letters and digits joined "
            "by single underscores, e.g. customer_orders."
        )
    if settings.host is not None:
        if not settings.host.startswith("https://"):
            raise SetupError(f"Host '{settings.host}' must start with https://")
        settings.host = settings.host.rstrip("/")
    for name in ("warehouse_id", "team_catalog", "product_dev_catalog"):
        value = getattr(settings, name)
        if value is not None and (not value or "<" in value or '"' in value):
            raise SetupError(f"'{value}' is not a valid {name.replace('_', ' ')}.")


def apply(project: Project, settings: Settings) -> list[str]:
    """Write the settings into the repository. Returns the files changed."""
    validate(settings)
    changed: list[str] = []

    def update(relative: str, transform) -> None:
        path = project.root / relative
        if not path.is_file():
            return
        before = path.read_text()
        after = transform(before)
        if after != before:
            path.write_text(after)
            if relative not in changed:
                changed.append(relative)

    old = devenv.read_product(project.dbt_project)
    if settings.product != old:
        for relative in PRODUCT_NAME_FILES:
            update(relative, lambda text: rename_in_text(text, old, settings.product))

    def fill_config(text: str) -> str:
        for name, key in DEV_CONFIG_KEYS.items():
            if (value := getattr(settings, name)) is not None:
                text = set_toml_value(text, key, value)
        return text

    update("config/dev-environment.toml", fill_config)

    def fill_bundle(text: str) -> str:
        if settings.host is not None:
            text = text.replace(BUNDLE_DEV_PLACEHOLDERS["host"], settings.host)
        if settings.product_dev_catalog is not None:
            text = text.replace(BUNDLE_DEV_PLACEHOLDERS["product_dev_catalog"],
                                settings.product_dev_catalog)
        return text

    update("databricks.yml", fill_bundle)
    return changed


def current_dev_values(project: Project) -> dict[str, str]:
    """The settings in config/dev-environment.toml that are already filled in."""
    try:
        text = project.dev_config.read_text()
    except FileNotFoundError:
        return {}
    values = {}
    for name, key in DEV_CONFIG_KEYS.items():
        match = re.search(rf'^{re.escape(key)}\s*=\s*"([^"\n]*)"', text, re.MULTILINE)
        if match and "<" not in match.group(1):
            values[name] = match.group(1)
    return values


QUESTIONS = (
    ("host", "Dev workspace URL (https://…)"),
    ("warehouse_id", "ID of the team's shared SQL warehouse in the dev workspace"),
    ("team_catalog", "Team catalog (personal environments and MR builds go here)"),
    ("product_dev_catalog", "Product dev catalog (Enter to leave it for later)"),
)


def ask(question: str, default: str | None) -> str | None:
    shown = f" [{default}]" if default else ""
    answer = input(f"{question}{shown}: ").strip()
    return answer or default


def main(project: Project, given: dict[str, str | None], assume_yes: bool) -> int:
    current = devenv.read_product(project.dbt_project)
    existing = current_dev_values(project)
    values = dict(given)
    if values.get("product") is None and not assume_yes:
        values["product"] = ask("Data product name (lowercase, words joined by _)", current)
    values["product"] = values.get("product") or current
    for name, question in QUESTIONS:
        if values.get(name) is None and not assume_yes:
            values[name] = ask(question, existing.get(name))
    settings = Settings(**{key: values.get(key) for key in Settings.__dataclass_fields__})

    changed = apply(project, settings)
    print(f"Data product: {settings.product}")
    print("Changed: " + (", ".join(changed) if changed else "nothing (already set)"))
    print(
        "\nNext:\n"
        "  make setup          log in check, your personal profiles.yml, dbt deps\n"
        "  make build          build and test the sample models in your personal environment\n"
        "Deployment settings (the prod target in databricks.yml, GitLab variables) are\n"
        "described in README.md, \"Turn the template into your data product\"."
    )
    return 0
