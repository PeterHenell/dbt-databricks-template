"""`dbtp init`: set up the repository and the developer's personal environment.

Every developer runs it once per clone. It has two parts:

Repository settings (committed; the first developer fills them in, right after creating
the repository from the template):

1. Renames the data product: the current dbt project name (the template ships a
   working sample name) is replaced in every file that must repeat it.
2. Writes the team's dev settings into `config/dev-environment.toml`.
3. Writes every deployment value into `databricks.yml`: the `dev` target (the same dev
   workspace and product dev catalog as the dev settings, plus its SQL warehouse and
   identity), the whole `prod` target and the prod schedule.

Once the team's dev settings are filled in, a later run shows them and asks whether
to change them (default: no), so a developer who clones the repository just presses
Enter. Options that set a value skip that question.

Personal environment (`setup_dev`, skipped with `--no-profile`): checks the Databricks
CLI login, asks for the developer alias, writes the gitignored `profiles.yml` and runs
`dbt deps`. It needs the team's dev settings, so it waits until they are filled in.

Workspaces and SQL warehouses are asked for as the Databricks UI shows them (server
hostname, SQL warehouse ID) and accept what people paste from there: a bare hostname
or a browser URL, a warehouse ID, HTTP path or warehouse page URL. `normalize_host`
and `normalize_warehouse_id` reduce them to the stored form.

Values are written by their key (`yaml_edit`, `set_toml_value`), not by replacing
placeholder text, so it can be run again to change any of them; the questions then
show the current values. It always starts from the product name that is in
`dbt_project.yml` now. Values not given are asked for. With `--yes`, nothing is asked:
values not given keep what they have, except that a placeholder with a default (prod
workspace = dev workspace, product dev warehouse = team warehouse, prod warehouse =
product dev warehouse) gets that default. Answers left for later keep their
placeholders, and the end of the run lists every placeholder still left.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, fields

import yaml

from dbtp import bundle, devenv, setup_dev, yaml_edit
from dbtp.devenv import Project, SetupError

# Files that must repeat the data product name (relative to the repository root).
# Missing files are skipped, so a product that drops e.g. the local engine still works.
PRODUCT_NAME_FILES = (
    "dbt_project.yml",       # name, profile, the `models:` block
    "deploy/profiles.yml",   # profile name, the `mr` target's schema `<product>__mr`
    "databricks.yml",        # bundle.name
    "local/profiles.yml",    # profile name, local schema prefix
)

DEV_CONFIG = "config/dev-environment.toml"
BUNDLE = "databricks.yml"


@dataclass
class Settings:
    product: str
    host: str | None = None
    warehouse_id: str | None = None
    team_catalog: str | None = None
    product_dev_catalog: str | None = None
    product_dev_warehouse_id: str | None = None
    product_dev_identity: str | None = None
    prod_host: str | None = None
    product_prod_catalog: str | None = None
    product_prod_warehouse_id: str | None = None
    product_prod_identity: str | None = None
    schedule: str | None = None


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


# Where each value is in the Databricks UI; used in the questions and in error messages,
# and repeated in the comments of config/dev-environment.toml.
HOST_WHERE = "SQL Warehouses → your warehouse → Connection details"
HOST_EXAMPLE = "dbc-1234abcd-5678.cloud.databricks.com"
HOST_HINT = f"{HOST_WHERE}, e.g. {HOST_EXAMPLE}"
WAREHOUSE_HINT = ("SQL Warehouses → the warehouse: the ID is shown next to its name; "
                  "or paste the HTTP path from Connection details")

HOSTNAME_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")
WAREHOUSE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


def normalize_host(value: str) -> str:
    """A workspace as `https://<hostname>`, from a server hostname or a pasted URL.

    Accepts `dbc-….cloud.databricks.com`, the same with `https://` or `http://`, and a
    browser URL with a path or query. Raises SetupError if no hostname is left.
    """
    host = re.sub(r"^[a-z]+://", "", value.strip(), flags=re.IGNORECASE)
    host = re.split(r"[/?#]", host, maxsplit=1)[0].lower()
    if not HOSTNAME_PATTERN.match(host):
        raise SetupError(
            f"'{value}' is not a server hostname. Expected something like {HOST_EXAMPLE} "
            f"({HOST_WHERE}).")
    return f"https://{host}"


def bare_host(host: str) -> str:
    """The server hostname of a stored `https://<hostname>`, as the UI shows it."""
    return re.sub(r"^https?://", "", host).rstrip("/")


def normalize_warehouse_id(value: str) -> str:
    """A SQL warehouse ID, from the ID itself, the HTTP path or a warehouse page URL.

    Accepts `9f61…`, `/sql/1.0/warehouses/9f61…` and `https://…/sql/warehouses/9f61…?o=1`.
    Raises SetupError if that doesn't leave a plain ID (letters and digits).
    """
    warehouse = value.strip()
    if "/warehouses/" in warehouse:
        warehouse = warehouse.split("/warehouses/", 1)[1]
        warehouse = re.split(r"[/?#]", warehouse, maxsplit=1)[0]
    if not WAREHOUSE_ID_PATTERN.match(warehouse):
        raise SetupError(
            f"'{value}' is not a SQL warehouse ID (letters and digits). Find it in "
            f"{WAREHOUSE_HINT}.")
    return warehouse


@dataclass(frozen=True)
class Field:
    """One setting: its CLI option, question, where it is written, and how it's checked."""

    name: str                               # attribute of Settings
    option: str                             # CLI option
    question: str
    kind: str                               # host | warehouse | name | schedule
    toml_key: str | None = None             # key in config/dev-environment.toml
    bundle_key: tuple[str, ...] | None = None  # key path in databricks.yml
    default_from: str | None = None         # setting whose value is the default
    aliases: tuple[str, ...] = ()


LATER = " (Enter to leave it for later)"

FIELDS = (
    Field("host", "--server-hostname",
          f"Server hostname of the dev workspace ({HOST_HINT})", "host",
          toml_key="host", bundle_key=("targets", "dev", "workspace", "host"),
          aliases=("--host",)),
    Field("warehouse_id", "--warehouse-id",
          f"SQL warehouse ID of the team's shared warehouse ({WAREHOUSE_HINT})", "warehouse",
          toml_key="warehouse_id"),
    Field("team_catalog", "--team-catalog",
          "Team catalog (personal environments and MR builds go here)", "name",
          toml_key="team"),
    Field("product_dev_catalog", "--product-dev-catalog", "Product dev catalog" + LATER, "name",
          toml_key="product_dev", bundle_key=("targets", "dev", "variables", "catalog")),
    Field("product_dev_warehouse_id", "--product-dev-warehouse-id",
          "SQL warehouse ID for the product dev job", "warehouse",
          bundle_key=("targets", "dev", "variables", "warehouse_id"),
          default_from="warehouse_id"),
    Field("product_dev_identity", "--product-dev-service-principal",
          "Product dev identity: service principal application ID" + LATER, "name",
          bundle_key=("targets", "dev", "variables", "service_principal")),
    Field("prod_host", "--prod-server-hostname",
          "Server hostname of the prod workspace (the same as dev if one workspace has "
          "everything: environments are picked by catalog)", "host",
          bundle_key=("targets", "prod", "workspace", "host"), default_from="host"),
    Field("product_prod_catalog", "--product-prod-catalog", "Product prod catalog" + LATER,
          "name", bundle_key=("targets", "prod", "variables", "catalog")),
    Field("product_prod_warehouse_id", "--product-prod-warehouse-id",
          "SQL warehouse ID for the product prod job", "warehouse",
          bundle_key=("targets", "prod", "variables", "warehouse_id"),
          default_from="product_dev_warehouse_id"),
    Field("product_prod_identity", "--product-prod-service-principal",
          "Product prod identity: service principal application ID" + LATER, "name",
          bundle_key=("targets", "prod", "variables", "service_principal")),
    Field("schedule", "--prod-schedule",
          "Prod schedule (Quartz cron: seconds minutes hours day-of-month month day-of-week)",
          "schedule", bundle_key=("variables", "schedule", "default")),
)
FIELD = {field.name: field for field in FIELDS}


def normalize_name(value: str) -> str:
    """A catalog or identity: non-empty, no placeholder, nothing that breaks the quoting."""
    value = value.strip()
    if not value or "<" in value or '"' in value:
        raise SetupError(f"'{value}' is not a valid value here.")
    return value


def normalize_schedule(value: str) -> str:
    """A Quartz cron expression: 6 or 7 fields (seconds first)."""
    value = " ".join(value.split())
    if not 6 <= len(value.split(" ")) <= 7 or '"' in value or "<" in value:
        raise SetupError(
            f"'{value}' is not a Quartz cron expression (6 or 7 fields, seconds first), "
            "e.g. 0 0 5 * * ?")
    return value


NORMALIZERS: dict[str, Callable[[str], str]] = {
    "host": normalize_host,
    "warehouse": normalize_warehouse_id,
    "name": normalize_name,
    "schedule": normalize_schedule,
}


def normalizer(name: str) -> Callable[[str], str]:
    return NORMALIZERS[FIELD[name].kind]


def validate(settings: Settings) -> None:
    if not devenv.NAME_PATTERN.match(settings.product):
        raise SetupError(
            f"Product name '{settings.product}' must be lowercase letters and digits joined "
            "by single underscores, e.g. customer_orders."
        )
    for field in FIELDS:
        if (value := getattr(settings, field.name)) is not None:
            try:
                setattr(settings, field.name, normalizer(field.name)(value))
            except SetupError as error:
                raise SetupError(f"{field.option}: {error}") from None


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

    def fill(text: str, key_of: Callable[[Field], object], setter) -> str:
        for field in FIELDS:
            key = key_of(field)
            if key is not None and (value := getattr(settings, field.name)) is not None:
                text = setter(text, key, value)
        return text

    update(DEV_CONFIG, lambda text: fill(text, lambda f: f.toml_key, set_toml_value))

    def set_bundle_value(text: str, key: tuple[str, ...], value: str) -> str:
        try:
            return yaml_edit.set_value(text, key, value)
        except SetupError as error:
            raise SetupError(f"{BUNDLE}: {error}") from None

    update(BUNDLE, lambda text: fill(text, lambda f: f.bundle_key, set_bundle_value))
    return changed


def _get(data, path: tuple[str, ...]):
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _read(project: Project) -> tuple[dict, dict]:
    """(config/dev-environment.toml, databricks.yml) parsed; empty if missing."""
    toml_path, bundle_path = project.root / DEV_CONFIG, project.root / BUNDLE
    config = tomllib.loads(toml_path.read_text()) if toml_path.is_file() else {}
    flat = {key: value for table in config.values() if isinstance(table, dict)
            for key, value in table.items()}
    data = (yaml.safe_load(bundle_path.read_text()) or {}) if bundle_path.is_file() else {}
    return flat, data


def current_values(project: Project) -> dict[str, str]:
    """The settings that are already filled in (no placeholder), in the form asked for.

    Hosts are returned as bare server hostnames, the form the questions ask for.
    """
    config, data = _read(project)
    values = {}
    for field in FIELDS:
        value = (config.get(field.toml_key) if field.toml_key
                 else _get(data, field.bundle_key))
        if isinstance(value, str) and value and not bundle.PLACEHOLDER.search(value):
            values[field.name] = bare_host(value) if field.kind == "host" else value
    return values


def current_dev_values(project: Project) -> dict[str, str]:
    """The settings in config/dev-environment.toml that are already filled in."""
    return {name: value for name, value in current_values(project).items()
            if FIELD[name].toml_key}


def placeholders_left(project: Project) -> list[tuple[str, str, str, str | None]]:
    """(file, key, placeholder, option that fills it) for every placeholder still left."""
    config_path = project.root / DEV_CONFIG
    left: list[tuple[str, str, str, str | None]] = []
    if config_path.is_file():
        options = {field.toml_key: field.option for field in FIELDS if field.toml_key}
        for path, value in bundle.find_placeholders(tomllib.loads(config_path.read_text())):
            left.append((DEV_CONFIG, ".".join(path), value, options.get(path[-1])))
    _, data = _read(project)
    options = {field.bundle_key: field.option for field in FIELDS if field.bundle_key}
    for path, value in bundle.find_placeholders(data):
        left.append((BUNDLE, ".".join(path), value, options.get(path)))
    return left


def ask(question: str, default: str | None, normalize=None) -> str | None:
    """Ask until the answer passes `normalize` (if given); Enter keeps the default."""
    shown = f" [{default}]" if default else ""
    while True:
        answer = input(f"{question}{shown}: ").strip() or default
        if answer is None or normalize is None:
            return answer
        try:
            normalize(answer)
        except SetupError as error:
            print(error)
            continue
        return answer


def _shown(name: str, value: str | None) -> str | None:
    """A value as the question for `name` shows it (hosts without https://)."""
    if value is None:
        return None
    value = normalizer(name)(value)
    return bare_host(value) if FIELD[name].kind == "host" else value


def dev_settings_complete(project: Project) -> bool:
    """Whether the dev settings a personal profile needs have no placeholders left."""
    try:
        devenv.read_dev_config(project.dev_config)
    except SetupError:
        return False
    return True


def print_placeholders_left(project: Project) -> None:
    left = placeholders_left(project)
    if left:
        print("\nStill to fill in (run `uv run dbtp init` again, or pass the option):")
        for file, key, value, option in left:
            print(f"  {file}: {key} = {value}" + (f"  ({option})" if option else ""))


def keep_repository_settings(project: Project) -> bool:
    """Show the filled-in settings and ask whether to change them (default: keep)."""
    existing = current_values(project)
    print(f"Data product: {devenv.read_product(project.dbt_project)}")
    for field in FIELDS:
        if field.name in existing:
            print(f"  {field.question.split(' (')[0]}: {existing[field.name]}")
    answer = input("Change the repository settings? [y/N]: ").strip().lower()
    return answer not in ("y", "yes")


def run(project: Project, given: dict[str, str | None], alias: str | None,
        assume_yes: bool, profile: bool = True) -> int:
    """`dbtp init`: the repository settings, then the personal environment."""
    if (not assume_yes and all(value is None for value in given.values())
            and dev_settings_complete(project) and keep_repository_settings(project)):
        print_placeholders_left(project)
    elif code := main(project, given, assume_yes):
        return code
    if not profile:
        return 0
    if not dev_settings_complete(project):
        print("\nYour personal profiles.yml comes once the team's dev settings (server "
              "hostname, SQL warehouse ID, team catalog) are filled in: run `uv run dbtp "
              "init` again then.")
        return 0
    print()
    return setup_dev.main(project, alias, assume_yes)


def main(project: Project, given: dict[str, str | None], assume_yes: bool) -> int:
    """The repository settings: product name, dev settings, databricks.yml."""
    current = devenv.read_product(project.dbt_project)
    existing = current_values(project)
    values = dict(given)
    if values.get("product") is None and not assume_yes:
        values["product"] = ask("Data product name (lowercase, words joined by _)", current)
    values["product"] = values.get("product") or current

    def known(name: str) -> str | None:
        """The value `name` will have after this run (given/answered, else current)."""
        return values.get(name) or existing.get(name)

    for field in FIELDS:
        if values.get(field.name) is not None:
            continue
        derived = _shown(field.default_from, known(field.default_from)) if field.default_from else None
        if assume_yes:
            if field.name not in existing:
                values[field.name] = derived
        else:
            values[field.name] = ask(field.question, existing.get(field.name) or derived,
                                     normalizer(field.name))
    settings = Settings(**{f.name: values.get(f.name) for f in fields(Settings)})

    changed = apply(project, settings)
    print(f"Data product: {settings.product}")
    print("Changed: " + (", ".join(changed) if changed else "nothing (already set)"))
    print_placeholders_left(project)
    if changed:
        print("Commit the changed files. Service principals and GitLab settings: README.md, "
              "\"Turn the template into your data product\".")
    return 0
