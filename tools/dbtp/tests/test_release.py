"""dbtp.release: tag rule, artifact contents, write-once registry logic (fake registry)."""

from __future__ import annotations

import io
import subprocess
import tarfile

import pytest

from dbtp import release
from dbtp.devenv import SetupError


@pytest.mark.parametrize("tag", ["v1.0.0", "1.2.3", "v1.2.3-rc.1", "2026.11.04-1", "v1.0.0+build_7"])
def test_valid_release_tags(tag):
    assert release.tag_problem(tag) is None


@pytest.mark.parametrize("tag", ["", "release/1.0", "v1 0", "..", "v1.0/", "vé1"])
def test_invalid_release_tags(tag):
    assert release.tag_problem(tag) is not None


def names(archive: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        return tar.getnames()


def test_artifact_includes_installed_packages_and_is_reproducible(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "dbt_project.yml").write_text("name: p\n")
    (tmp_path / "Makefile").write_text("all:\n")
    (tmp_path / "dbt_packages" / "pkg" / "macros").mkdir(parents=True)
    (tmp_path / "dbt_packages" / "pkg" / "macros" / "m.sql").write_text("{% macro m() %}{% endmacro %}")
    subprocess.run(["git", "add", "dbt_project.yml", "Makefile"], cwd=tmp_path, check=True)

    files = release.tracked_files(tmp_path) + release.installed_files(tmp_path)
    assert files == ["dbt_project.yml", "dbt_packages/pkg/macros/m.sql"]
    first = release.build_archive(tmp_path, "p", "v1", files, "abc")
    assert first == release.build_archive(tmp_path, "p", "v1", files, "abc")
    assert names(first) == ["RELEASE.json", "dbt_project.yml", "dbt_packages/pkg/macros/m.sql"]

    release.unpack(first, tmp_path / "out")
    assert (tmp_path / "out" / "dbt_packages" / "pkg" / "macros" / "m.sql").exists()
    assert '"version": "v1"' in (tmp_path / "out" / "RELEASE.json").read_text()


class FakeRegistry:
    def __init__(self, stored: dict | None = None):
        self.stored = dict(stored or {})
        self.uploads = 0

    def get(self, product, version):
        return self.stored.get((product, version))

    def put(self, product, version, archive):
        self.uploads += 1
        self.stored[(product, version)] = archive


def test_publish_builds_and_uploads_once(monkeypatch):
    builds = []
    monkeypatch.setattr(release, "build", lambda root, p, v: builds.append(v) or b"archive-" + v.encode())
    registry = FakeRegistry()
    assert release.publish(registry, None, "p", "v1", out=lambda _: None) == (b"archive-v1", True)
    # A re-run of the pipeline reuses the stored archive and never rebuilds.
    assert release.publish(registry, None, "p", "v1", out=lambda _: None) == (b"archive-v1", False)
    assert builds == ["v1"] and registry.uploads == 1


def test_fetch_never_builds():
    with pytest.raises(SetupError, match="release-artifact"):
        release.fetch(FakeRegistry(), "p", "v9")
    assert release.fetch(FakeRegistry({("p", "v1"): b"x"}), "p", "v1") == b"x"


def test_registry_url():
    registry = release.Registry("https://gitlab.example.com/api/v4/", "group/proj", "token")
    assert registry.url("sample_product", "v1.0.0+b") == (
        "https://gitlab.example.com/api/v4/projects/group%2Fproj/packages/generic/"
        "sample_product/v1.0.0%2Bb/sample_product-v1.0.0%2Bb.tar.gz"
    )


def test_commit_on_branch(tmp_path):
    def git(*args, cwd=tmp_path):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

    origin, clone = tmp_path / "origin", tmp_path / "clone"
    origin.mkdir()
    git("init", "-q", "-b", "main", cwd=origin)
    git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "one", cwd=origin)
    git("clone", "-q", str(origin), str(clone))
    on_main = git("rev-parse", "HEAD", cwd=clone)
    git("checkout", "-q", "-b", "hotfix", cwd=clone)
    git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "fix", cwd=clone)
    off_main = git("rev-parse", "HEAD", cwd=clone)
    assert release.commit_on_branch(on_main, "main", clone)
    assert not release.commit_on_branch(off_main, "main", clone)


def test_registry_against_fake_gitlab_package_api(monkeypatch):
    """The real HTTP client against a local stand-in for GitLab's generic package API."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    stored, seen_tokens = {}, []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen_tokens.append(self.headers.get("JOB-TOKEN"))
            body = stored.get(self.path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            self.wfile.write(body or b'{"message":"404 Not Found"}')

        def do_PUT(self):
            seen_tokens.append(self.headers.get("JOB-TOKEN"))
            stored[self.path] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(201)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        registry = release.Registry(f"http://127.0.0.1:{server.server_address[1]}/api/v4", "42", "job-tok")
        monkeypatch.setattr(release, "build", lambda root, p, v: b"tarball")
        assert release.publish(registry, None, "p", "v1", out=lambda _: None) == (b"tarball", True)
        assert list(stored) == ["/api/v4/projects/42/packages/generic/p/v1/p-v1.tar.gz"]
        assert release.publish(registry, None, "p", "v1", out=lambda _: None) == (b"tarball", False)
        assert release.fetch(registry, "p", "v1") == b"tarball"
        assert set(seen_tokens) == {"job-tok"}
    finally:
        server.shutdown()
        server.server_close()
