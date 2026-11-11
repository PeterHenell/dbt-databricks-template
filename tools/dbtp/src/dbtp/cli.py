"""The `dbtp` command line. Run `dbtp --help`, or `dbtp <command> --help`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dbtp import (__version__, build_changed, bundle, checks, devenv, init_product, local_engine,
                  mr_build, personal, release, setup_dev)
from dbtp.devenv import Project, SetupError

PASSTHROUGH_HELP = "extra dbt arguments, after `--` (e.g. -- --exclude published)"


def dbt_args(args: list[str]) -> list[str]:
    """Arguments after `--`, without it (argparse.REMAINDER keeps the `--`)."""
    return args[1:] if args[:1] == ["--"] else args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbtp",
        description="Setup, developer-environment and deployment tooling for dbt data "
                    "products on Databricks.")
    parser.add_argument("--version", action="version", version=f"dbtp {__version__}")
    parser.add_argument("--project-dir", type=Path,
                        help="the data product repository (default: found from the working "
                             f"directory, or ${devenv.PROJECT_DIR_ENV})")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def command(name: str, help: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help, description=help)

    init = command("init", "Once, in a new repository: set the data product name and the team's "
                           "dev settings")
    init.add_argument("--product", help="data product name (lowercase, words joined by _)")
    init.add_argument("--host", help="dev workspace URL, https://…")
    init.add_argument("--warehouse-id", help="the team's shared SQL warehouse in the dev workspace")
    init.add_argument("--team-catalog", help="the team catalog (personal environments, MR builds)")
    init.add_argument("--product-dev-catalog", help="the product dev catalog")
    init.add_argument("--yes", action="store_true",
                      help="don't ask; leave values that aren't given as they are")

    setup = command("setup", "Check the Databricks login, write your personal profiles.yml, dbt deps")
    setup.add_argument("--alias", help="use this developer alias without asking")
    setup.add_argument("--yes", action="store_true", help="accept all defaults (non-interactive)")

    command("clone-sources", "(Re)create your shallow clones of every source")
    command("clean-dev", "Drop your whole personal environment (<product>__<alias>__*), after confirmation")

    changed = command("build-changed",
                      "Build only what you changed, deferring the rest to product dev")
    changed.add_argument("--manifest-dir", type=Path,
                         help="use a manifest.json already in this directory instead of downloading it")
    changed.add_argument("dbt_args", nargs=argparse.REMAINDER, help=PASSTHROUGH_HELP)

    command("parse", "Offline `dbt parse` with the deployment profile (no connection, no login)")

    local = command("local", "Local engine: Apache Spark + Postgres metastore in containers")
    local_sub = local.add_subparsers(dest="action", required=True, metavar="<action>")
    for name, help in (("up", "build the image and start the Postgres metastore"),
                       ("sources", "create the local stand-in source tables (local/sources.sql)"),
                       ("sql", "open a Spark SQL shell on the local catalog"),
                       ("down", "stop the containers (keeps the data)"),
                       ("clean", "stop and delete all local tables and the catalog")):
        local_sub.add_parser(name, help=help)
    local_dbt = local_sub.add_parser("dbt", help="run dbt in the local engine (default: build)")
    local_dbt.add_argument("dbt_args", nargs=argparse.REMAINDER,
                           help="dbt command and arguments (default: build)")

    rel = command("release", "Release artifact: build, check the tag, publish, fetch (ADR 0008)")
    rel_sub = rel.add_subparsers(dest="action", required=True, metavar="<action>")
    rel_build = rel_sub.add_parser("build", help="build and unpack the artifact by hand")
    rel_build.add_argument("--version", default="local")
    rel_sub.add_parser("check-tag", help="CI: the release tag is valid and on the default branch")
    rel_sub.add_parser("publish", help="CI: build and upload the artifact once, then unpack it")
    rel_sub.add_parser("fetch", help="CI: download the release's artifact and unpack it")

    bun = command("bundle", "Databricks Asset Bundle: validate, deploy and run")
    bun_sub = bun.add_subparsers(dest="action", required=True, metavar="<action>")
    for name, help in (("validate", "validate the bundle for a target"),
                       ("deploy", "deploy the unpacked artifact to a target"),
                       ("run", "start the job in a target and wait for it")):
        action = bun_sub.add_parser(name, help=help)
        action.add_argument("-t", "--target", default="dev", help="bundle target (default: dev)")
        if name == "validate":
            action.add_argument("--dir", type=Path,
                                help="bundle directory relative to the repository, e.g. "
                                     "target/release/bundle for the artifact")

    mr = command("mr-build", "CI: drop <product>__mr__*, then a full dbt build into it")
    mr.add_argument("dbt_args", nargs=argparse.REMAINDER, help=PASSTHROUGH_HELP)
    return parser


def dispatch(args: argparse.Namespace, project: Project) -> int:
    match args.command:
        case "init":
            given = {name: getattr(args, name) for name in
                     ("product", "host", "warehouse_id", "team_catalog", "product_dev_catalog")}
            return init_product.main(project, given, args.yes)
        case "setup":
            return setup_dev.main(project, args.alias, args.yes)
        case "clone-sources":
            return personal.clone_sources(project)
        case "clean-dev":
            return personal.clean_dev(project)
        case "build-changed":
            return build_changed.main(project, dbt_args(args.dbt_args), args.manifest_dir)
        case "parse":
            return checks.parse(project)
        case "local":
            if args.action == "dbt":
                return local_engine.dbt(project, dbt_args(args.dbt_args))
            return getattr(local_engine, args.action)(project)
        case "release":
            return release.main(project, args.action, getattr(args, "version", "local"))
        case "bundle":
            if args.action == "validate":
                return bundle.validate(project, args.target, args.dir)
            return getattr(bundle, args.action)(project, args.target)
        case "mr-build":
            return mr_build.main(project, dbt_args(args.dbt_args))
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        project = Project.at(args.project_dir) if args.project_dir else Project.find()
        return dispatch(args, project)
    except SetupError as error:
        devenv.fail(str(error))
    except FileNotFoundError as error:
        devenv.fail(f"`{error.filename}` is not installed or not on PATH.")
    except (KeyboardInterrupt, EOFError):
        devenv.fail("cancelled")
    return 1


if __name__ == "__main__":
    sys.exit(main())
