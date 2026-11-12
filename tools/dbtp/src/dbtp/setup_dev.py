"""`dbtp setup` (`make setup`): create the developer's personal dev profile.

1. Checks for a Databricks CLI OAuth (user-to-machine) login to the dev workspace.
2. Suggests a developer alias from the logged-in user's name and lets the developer
   accept or change it.
3. Writes the gitignored `profiles.yml` at the repo root (ADR 0002).
4. Installs the dbt packages (`dbt deps`).

Python dependencies (dbtp itself among them) are installed by `uv sync` before this runs.
"""

from __future__ import annotations

import configparser
import json
import os
import subprocess
import urllib.request
from pathlib import Path

from dbtp import devenv
from dbtp.devenv import Project, SetupError


def cli_config_path() -> Path:
    """The Databricks CLI config file: `$DATABRICKS_CONFIG_FILE`, else `~/.databrickscfg`."""
    configured = os.environ.get("DATABRICKS_CONFIG_FILE")
    return Path(configured).expanduser() if configured else Path.home() / ".databrickscfg"


def _normalize_host(host: str) -> str:
    return host.strip().rstrip("/").lower()


def cli_profile(host: str) -> str | None:
    """The Databricks CLI profile that logs in to `host`, or None to fall back to `--host`.

    Only profiles whose `host` is the dev host count, so a default profile for another
    workspace is never used. Several matches (e.g. `databricks auth login` run twice)
    are not an error: `[__settings__] default_profile` wins if it is one of them,
    otherwise the first one in the file.
    """
    parser = configparser.ConfigParser(interpolation=None, default_section="__no_defaults__")
    try:
        parser.read(cli_config_path())
    except configparser.Error:
        return None
    wanted = _normalize_host(host)
    matches = [
        name for name in parser.sections()
        if name != "__settings__" and _normalize_host(parser[name].get("host", "")) == wanted
    ]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    default = parser.get("__settings__", "default_profile", fallback=None)
    chosen = default if default in matches else matches[0]
    others = ", ".join(name for name in matches if name != chosen)
    print(f"Note: using Databricks CLI profile '{chosen}' for {host} (also matching: {others}).")
    return chosen


def cli_target_args(host: str, profile: str | None) -> list[str]:
    """CLI arguments that select the developer's login: `--profile` if one matched, else `--host`."""
    return ["--profile", profile] if profile else ["--host", host]


def cli_access_token(host: str, profile: str | None) -> str:
    """Access token from the Databricks CLI's U2M login for `host` (via `profile` if set)."""
    login_help = (
        "No valid Databricks CLI login for the dev workspace.\n"
        f"  Log in with:  databricks auth login --host {host}\n"
        "  (a browser opens; sign in with your own account), then run `make setup` again."
    )
    try:
        result = subprocess.run(
            ["databricks", "auth", "token", *cli_target_args(host, profile), "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise SetupError(
            "The Databricks CLI is not installed. See "
            "https://docs.databricks.com/dev-tools/cli/install.html"
        ) from None
    if result.stderr.strip():
        login_help = f"{login_help}\n  The Databricks CLI said:\n    {result.stderr.strip()}"
    try:
        token = json.loads(result.stdout)["access_token"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise SetupError(login_help) from None
    if result.returncode != 0 or not token:
        raise SetupError(login_help)
    return token


def current_user_names(host: str, token: str) -> tuple[str, str]:
    """(first, last) name of the logged-in user, from the workspace SCIM API."""
    request = urllib.request.Request(
        f"{host}/api/2.0/preview/scim/v2/Me",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            me = json.load(response)
    except OSError:
        return "", ""
    name = me.get("name") or {}
    first, last = name.get("givenName") or "", name.get("familyName") or ""
    if first and last:
        return first, last
    return devenv.split_display_name(me.get("displayName") or "")


def git_user_names() -> tuple[str, str]:
    result = subprocess.run(
        ["git", "config", "user.name"], capture_output=True, text=True, check=False
    )
    return devenv.split_display_name(result.stdout.strip())


def ask(question: str, default: str) -> str:
    answer = input(f"{question} [{default}]: ").strip()
    return answer or default


def choose_alias(suggested: str, existing: str | None, preset: str | None, assume_yes: bool) -> str:
    if preset is not None:
        error = devenv.validate_alias(preset)
        if error:
            raise SetupError(f"alias '{preset}': {error}")
        return preset

    if existing:
        print(f"Your profiles.yml already uses the alias '{existing}'.")
        if existing != suggested and suggested:
            print(f"(The suggested alias from your name would be '{suggested}'.)")
        default = existing
    else:
        if suggested:
            print(f"Suggested developer alias: '{suggested}' (first 2 letters of first + last name).")
        default = suggested

    while True:
        alias = default if assume_yes else ask("Developer alias", default)
        error = devenv.validate_alias(alias)
        if not error:
            return alias
        if assume_yes:
            raise SetupError(f"alias '{alias}': {error} Pass --alias.")
        print(f"  {error}")
        default = ""


def write_profile(path, content: str, assume_yes: bool) -> bool:
    if path.exists() and path.read_text() != content:
        print(f"\n{path.name} exists and will be replaced. Current content:\n")
        print(path.read_text())
        if not assume_yes and ask("Replace it?", "y/N").lower() not in ("y", "yes"):
            print("Kept the existing profiles.yml.")
            return False
    path.write_text(content)
    return True


def main(project: Project, alias: str | None = None, assume_yes: bool = False) -> int:
    product = project.product()
    config = devenv.read_dev_config(project.dev_config)

    profile = cli_profile(config.host)
    token = cli_access_token(config.host, profile)
    login = f" (profile '{profile}')" if profile else ""
    print(f"Databricks CLI login OK for {config.host}{login}")

    first, last = current_user_names(config.host, token)
    if not (first and last):
        first, last = git_user_names()
    suggested = devenv.suggest_alias(first, last)
    existing = devenv.alias_from_profile(product, project.dev_profile)

    chosen = choose_alias(suggested, existing, alias, assume_yes)
    prefix = devenv.personal_prefix(product, chosen)

    if write_profile(project.dev_profile, devenv.render_profile(product, chosen, config), assume_yes):
        print(
            f"\nWrote profiles.yml: catalog '{config.team_catalog}', "
            f"personal environment '{prefix}__<layer>'."
        )
    if code := devenv.run(["dbt", "deps"], project):
        return code
    print(
        "\nNext: `uv run dbt build` (the first dbt run opens a browser to sign in to dbt-databricks)."
    )
    return 0
