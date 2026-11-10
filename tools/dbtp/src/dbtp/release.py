"""Release artifact: build it, check the release tag, store it once, fetch it (ADR 0008).

The artifact is one archive with everything the bundle deploys and nothing
environment-specific: the bundle (`databricks.yml`, `resources/`), the dbt project,
the installed `dbt_packages/`, `deploy/profiles.yml` and the job's helper script.
It is deployed unchanged to product dev and prod; the bundle target supplies hosts,
catalogs, warehouses and identities.

Commands (`dbtp release …`; the Makefile and .gitlab-ci.yml call them):

  build --version V   `dbt deps`, then build target/release/<product>-<V>.tar.gz and unpack it into
                      target/release/bundle/ (what `make bundle-deploy` deploys)
  check-tag           CI, release pipeline: the tag is a valid GitLab package version
                      and its commit is on the default branch
  publish             CI: reuse the archive in the GitLab generic package registry if
                      it is there, otherwise `dbt deps`, build and upload it; then unpack it
  fetch               CI: download the archive from the registry (never build); unpack
"""

from __future__ import annotations

import gzip
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from dbtp import devenv
from dbtp.devenv import Project, SetupError

# The job's helper script ships inside the artifact; the bundle points at this path.
JOB_SCRIPT = "tools/dbtp/src/dbtp/jobs/publish_dbt_artifacts.py"


def release_dir(project: Project) -> Path:
    return project.target_dir / "release"


def bundle_dir(project: Project) -> Path:
    """Where the unpacked artifact goes; `dbtp bundle deploy|run` deploy from here."""
    return release_dir(project) / "bundle"

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
    JOB_SCRIPT,
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


# Run output inside an installed package's own directory (e.g. a `local:` package
# someone ran dbt in) is not package content.
PACKAGE_RUN_OUTPUT = {"target", "logs", "dbt_packages"}


def installed_files(root: Path) -> list[str]:
    """Files under `dbt_packages/`. `dbt deps` installs a `local:` package as a symlink
    (an absolute one), so links are followed and the artifact gets real copies."""
    files = []
    for top in INSTALLED:
        base = root / top
        for dirpath, dirnames, filenames in os.walk(base, followlinks=True):
            here = Path(dirpath)
            if here.parent == base:  # a package's own directory
                dirnames[:] = [d for d in dirnames if d not in PACKAGE_RUN_OUTPUT]
            files += [(here / name).relative_to(root).as_posix() for name in filenames]
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
    """`dbt deps` (the artifact ships the installed packages), then the archive."""
    subprocess.run(["dbt", "deps"], cwd=root, check=True)
    files = tracked_files(root) + installed_files(root)
    return build_archive(root, product, version, files, git_commit(root))


def save_and_unpack(archive: bytes, product: str, version: str, project: Project) -> Path:
    release_dir(project).mkdir(parents=True, exist_ok=True)
    path = release_dir(project) / archive_name(product, version)
    path.write_bytes(archive)
    unpack(archive, bundle_dir(project))
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


def commit_on_branch(sha: str, branch: str, root: Path) -> bool:
    subprocess.run(["git", "fetch", "--quiet", "origin", branch], cwd=root, check=True)
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, f"origin/{branch}"],
                          cwd=root, check=False).returncode == 0


def ci_tag() -> str:
    return os.environ.get("CI_COMMIT_TAG", "")


def main(project: Project, command: str, version: str = "local") -> int:
    root = project.root
    rel = lambda path: path.relative_to(root)  # noqa: E731
    try:
        product = project.product()
        if command == "build":
            if problem := tag_problem(version):
                raise SetupError(problem.replace("Release tag", "Version"))
            path = save_and_unpack(build(root, product, version), product, version, project)
            print(f"Built {rel(path)}; unpacked into {rel(bundle_dir(project))}/.")
        elif command == "check-tag":
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
        elif command in ("publish", "fetch"):
            tag = ci_tag()
            if problem := tag_problem(tag):
                raise SetupError(problem)
            registry = Registry.from_ci_env()
            archive = (publish(registry, root, product, tag)[0] if command == "publish"
                       else fetch(registry, product, tag))
            save_and_unpack(archive, product, tag, project)
            print(f"Unpacked {archive_name(product, tag)} into {rel(bundle_dir(project))}/.")
        else:
            raise SetupError(f"Unknown release command '{command}'.")
    except subprocess.CalledProcessError as error:
        raise SetupError(
            f"{' '.join(map(str, error.cmd))} failed with exit code {error.returncode}.") from None
    return 0
