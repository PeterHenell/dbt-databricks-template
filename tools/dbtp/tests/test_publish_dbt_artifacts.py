"""dbtp/jobs/publish_dbt_artifacts.py (the job task) with a fake Databricks SDK client."""

from __future__ import annotations

import io
import tarfile
from types import SimpleNamespace

import pytest

from dbtp.jobs import publish_dbt_artifacts as publish


def tar_gz(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class FakeJobs:
    def __init__(self, archive_link="https://example/dbt-output.tar.gz"):
        self.link = archive_link

    def get_run(self, run_id):
        return SimpleNamespace(tasks=[SimpleNamespace(task_key="dbt_build", run_id=run_id + 1),
                                      SimpleNamespace(task_key="publish_dbt_artifacts", run_id=run_id + 2)])

    def get_run_output(self, task_run_id):
        dbt_output = SimpleNamespace(artifacts_link=self.link, artifacts_headers={"x-ms": "1"}) if self.link else None
        return SimpleNamespace(dbt_output=dbt_output)


def test_extract_takes_target_nearest_the_root():
    archive = tar_gz({
        "dbt-output/target/manifest.json": b"M",
        "dbt-output/target/run_results.json": b"R",
        "dbt-output/dbt_packages/x/target/manifest.json": b"wrong",
        "dbt-output/logs/dbt.log": b"log",
    })
    assert publish.extract_artifacts(archive) == {"manifest.json": b"M", "run_results.json": b"R"}


def test_extract_fails_without_artifacts():
    with pytest.raises(publish.PublishError, match="run_results.json"):
        publish.extract_artifacts(tar_gz({"target/manifest.json": b"M"}))


def test_publish_writes_run_then_latest(tmp_path):
    publish.publish({"manifest.json": b"M2", "run_results.json": b"R2"}, tmp_path, 42)
    assert (tmp_path / "runs" / "42" / "manifest.json").read_bytes() == b"M2"
    assert (tmp_path / "latest" / "run_results.json").read_bytes() == b"R2"


def test_main_end_to_end_with_fake_client(tmp_path, monkeypatch):
    archive = tar_gz({"target/manifest.json": b"M", "target/run_results.json": b"R"})
    fetched = {}

    def fake_get(url, headers):
        fetched.update(url=url, headers=headers)
        return archive

    monkeypatch.setattr(publish, "_http_get", fake_get)
    client = SimpleNamespace(jobs=FakeJobs())
    publish.main(["--job-run-id", "100", "--dbt-task-key", "dbt_build", "--volume", str(tmp_path)], client=client)
    assert fetched == {"url": "https://example/dbt-output.tar.gz", "headers": {"x-ms": "1"}}
    assert (tmp_path / "runs" / "100" / "manifest.json").read_bytes() == b"M"
    assert (tmp_path / "latest" / "manifest.json").read_bytes() == b"M"


def test_no_dbt_output_publishes_nothing(tmp_path):
    client = SimpleNamespace(jobs=FakeJobs(archive_link=None))
    with pytest.raises(publish.PublishError):
        publish.main(["--job-run-id", "1", "--dbt-task-key", "dbt_build", "--volume", str(tmp_path)], client=client)
    assert list(tmp_path.iterdir()) == []


def test_unknown_task_key():
    with pytest.raises(publish.PublishError, match="no task 'nope'"):
        publish.dbt_task_run_id(SimpleNamespace(jobs=FakeJobs()), 1, "nope")
