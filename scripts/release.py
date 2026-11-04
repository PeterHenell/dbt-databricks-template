"""Release artifact: build it, check the release tag, store it once, fetch it (ADR 0008).

The artifact is one archive with everything the bundle deploys and nothing
environment-specific: the bundle (`databricks.yml`, `resources/`), the dbt project,
the installed `dbt_packages/`, `deploy/profiles.yml` and the job's helper script.
It is deployed unchanged to product dev and prod; the bundle target supplies hosts,
catalogs, warehouses and identities.

Commands (the Makefile and .gitlab-ci.yml call them):

  build --version V   build target/release/<product>-<V>.tar.gz and unpack it into
                      target/release/bundle/ (what `make bundle-deploy` deploys)
  check-tag           CI, release pipeline: the tag is a valid GitLab package version
                      and its commit is on the default branch
  publish             CI: reuse the archive in the GitLab generic package registry if
                      it is there, otherwise build and upload it; then unpack it
  fetch               CI: download the archive from the registry (never build); unpack
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import devenv
from devenv import SetupError

RELEASE_DIR = devenv.REPO_ROOT / "target" / "release"
BUNDLE_DIR = RELEASE_DIR / "bundle"

# Tracked files and directories that go into the artifact. Anything else in the
# repository (developer tooling, docs, local engine, CI config) stays out.
INCLUDE = (
    "databricks.yml",
    "resources/",
    "deploy/",
    "dbt_project.yml",
    "packages.yml",
    "dependencies.yml",
    "package-lock.yml",
    "models/",
    "macros/",
    "seeds/",
    "snapshots/",
    "analyses/",
    "tests/dbt/",
    "scripts/publish_dbt_artifacts.py",
)
# Installed by `dbt deps` (gitignored) and still part of the artifact.
INSTALLED = ("dbt_packages",)

# GitLab's rule for generic package versions (Gitlab::Regex.generic_package_version_regex):
# word characters, `+` and `-`, in dot-separated parts. No `/`, no spaces.
PACKAGE_VERSION = re.compile(r"\A(\.?[\w+-]+\.?)+\Z", re.ASCII)


def tag_problem(tag: str) -> str | None:
    """Why `tag` can't be a release tag, or None."""
    if not tag:
        return "No tag: the release pipeline only runs for tags (GitLab releases)."
    if len(tag) > 255 or not PACKAGE_VERSION.match(tag):
        return (
            f"Release tag '{tag}' is not a valid GitLab package version. Use letters, digits, "
            "'_', '+', '-' and single dots between them, e.g. v1.4.0 or 2026.11.04-1 (no '/')."
        )
    return None


def tracked_files(root: Path) -> list[str]:
    # Committed and new (not ignored) files: a hand build ships the working tree.
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         cwd=root, capture_output=True, check=True).stdout.decode()
    return sorted(path for path in out.split("\0") if path and path.startswith(INCLUDE)
                  and (root / path).is_file())


def installed_files(root: Path) -> list[str]:
    files = []
    for top in INSTALLED:
        base = root / top
        if base.is_dir():
            files += [p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file()]
    return sorted(files)


def git_commit(root: Path) -> str:
    """HEAD, with `-dirty` if the working tree has changes (only possible in hand builds)."""
    git = lambda *args: subprocess.run(["git", *args], cwd=root, capture_output=True,  # noqa: E731
                                       text=True, check=True).stdout.strip()
    return git("rev-parse", "HEAD") + ("-dirty" if git("status", "--porcelain") else "")


def build_archive(root: Path, product: str, version: str, files: list[str], commit: str) -> bytes:
    """A gzipped tar of `files` plus RELEASE.json. Same inputs give the same bytes."""
    manifest = json.dumps({"product": product, "version": version, "commit": commit},
                          indent=2).encode() + b"\n"
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            def add(name: str, data: bytes, mode: int) -> None:
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(data), mode, 0
                tar.addfile(info, io.BytesIO(data))

            add("RELEASE.json", manifest, 0o644)
            for path in files:
                source = root / path
                add(path, source.read_bytes(), 0o755 if os.access(source, os.X_OK) else 0o644)
    return buffer.getvalue()


def unpack(archive: bytes, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        tar.extractall(dest, filter="data")


def archive_name(product: str, version: str) -> str:
    return f"{product}-{version}.tar.gz"


def build(root: Path, product: str, version: str) -> bytes:
    files = tracked_files(root) + installed_files(root)
    return build_archive(root, product, version, files, git_commit(root))


def save_and_unpack(archive: bytes, product: str, version: str,
                    release_dir: Path = RELEASE_DIR) -> Path:
    release_dir.mkdir(parents=True, exist_ok=True)
    path = release_dir / archive_name(product, version)
    path.write_bytes(archive)
    unpack(archive, release_dir / "bundle")
    return path


# ---- GitLab generic package registry ----

@dataclass
class Registry:
    """`<api>/projects/<id>/packages/generic/<package>/<version>/<file>` with the job token."""
    api_url: str
    project_id: str
    token: str

    @classmethod
    def from_ci_env(cls) -> "Registry":
        missing = [v for v in ("CI_API_V4_URL", "CI_PROJECT_ID", "CI_JOB_TOKEN") if not os.environ.get(v)]
        if missing:
            raise SetupError(f"Not in a GitLab CI job (missing {', '.join(missing)}).")
        return cls(os.environ["CI_API_V4_URL"], os.environ["CI_PROJECT_ID"], os.environ["CI_JOB_TOKEN"])

    def url(self, product: str, version: str) -> str:
        quote = lambda part: urllib.parse.quote(part, safe="")  # noqa: E731
        return (f"{self.api_url.rstrip('/')}/projects/{quote(self.project_id)}/packages/generic/"
                f"{quote(product)}/{quote(version)}/{quote(archive_name(product, version))}")

    def _request(self, method: str, url: str, data: bytes | None = None):
        request = urllib.request.Request(url, data=data, method=method,
                                         headers={"JOB-TOKEN": self.token})
        return urllib.request.urlopen(request, timeout=300)

    def get(self, product: str, version: str) -> bytes | None:
        try:
            with self._request("GET", self.url(product, version)) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise SetupError(f"Package registry: GET failed with HTTP {error.code}.") from None

    def put(self, product: str, version: str, archive: bytes) -> None:
        try:
            with self._request("PUT", self.url(product, version), archive):
                pass
        except urllib.error.HTTPError as error:
            raise SetupError(f"Package registry: upload failed with HTTP {error.code}.") from None


def publish(registry, root: Path, product: str, version: str, out=print) -> tuple[bytes, bool]:
    """The release's archive, built and uploaded only if the registry doesn't have it yet.

    Returns (archive, built). Write-once: a re-run of the pipeline reuses what's stored.
    """
    existing = registry.get(product, version)
    if existing is not None:
        out(f"Reusing {archive_name(product, version)} from the package registry (written once).")
        return existing, False
    archive = build(root, product, version)
    registry.put(product, version, archive)
    out(f"Built and uploaded {archive_name(product, version)} to the package registry.")
    return archive, True


def fetch(registry, product: str, version: str) -> bytes:
    archive = registry.get(product, version)
    if archive is None:
        raise SetupError(
            f"No {archive_name(product, version)} in the package registry. The release "
            "pipeline's `release-artifact` job has to run first."
        )
    return archive


def commit_on_branch(sha: str, branch: str, root: Path = devenv.REPO_ROOT) -> bool:
    subprocess.run(["git", "fetch", "--quiet", "origin", branch], cwd=root, check=True)
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, f"origin/{branch}"],
                          cwd=root, check=False).returncode == 0


def ci_tag() -> str:
    return os.environ.get("CI_COMMIT_TAG", "")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build_cmd = sub.add_parser("build")
    build_cmd.add_argument("--version", default="local")
    sub.add_parser("check-tag")
    sub.add_parser("publish")
    sub.add_parser("fetch")
    args = parser.parse_args(argv)

    root = devenv.REPO_ROOT
    try:
        product = devenv.read_product()
        if args.command == "build":
            if problem := tag_problem(args.version):
                raise SetupError(problem.replace("Release tag", "Version"))
            path = save_and_unpack(build(root, product, args.version), product, args.version)
            print(f"Built {path.relative_to(root)}; unpacked into {BUNDLE_DIR.relative_to(root)}/.")
        elif args.command == "check-tag":
            tag, sha = ci_tag(), os.environ.get("CI_COMMIT_SHA", "")
            branch = os.environ.get("CI_DEFAULT_BRANCH", "main")
            if problem := tag_problem(tag):
                raise SetupError(problem)
            if not commit_on_branch(sha, branch, root):
                raise SetupError(
                    f"Tag {tag} points at {sha[:12]}, which is not on {branch}. Releases are "
                    f"made from {branch} only (ADR 0007; for hotfixes see that ADR)."
                )
            print(f"Release tag {tag} ({sha[:12]}) is on {branch}.")
        else:
            tag = ci_tag()
            if problem := tag_problem(tag):
                raise SetupError(problem)
            registry = Registry.from_ci_env()
            archive = (publish(registry, root, product, tag)[0] if args.command == "publish"
                       else fetch(registry, product, tag))
            save_and_unpack(archive, product, tag)
            print(f"Unpacked {archive_name(product, tag)} into {BUNDLE_DIR.relative_to(root)}/.")
    except SetupError as error:
        devenv.fail(str(error))
    except subprocess.CalledProcessError as error:
        devenv.fail(f"{' '.join(map(str, error.cmd))} failed with exit code {error.returncode}.")


if __name__ == "__main__":
    sys.exit(main())
