"""Publish a successful job run's dbt artifacts to the catalog volume (ADR 0006).

Runs as the job's second task (resources/dbt_job.yml), only after the dbt task
succeeded. It fetches the dbt task's archived output (`dbt_output.artifacts_link` of
the task run) and writes `manifest.json` and `run_results.json` to

    <volume>/runs/<job_run_id>/   and then   <volume>/latest/

`runs/` is written first, so `latest/` only ever changes to a complete, successful run.

Why a follow-up task, not `dbt --target-path <volume>`: dbt writes `run_results.json`
(and a manifest) even when the build fails, so writing straight to the volume would
break "a failed run publishes nothing".

Needs only databricks-sdk; on Databricks it authenticates as the job's run-as identity.
"""

from __future__ import annotations

import argparse
import io
import shutil
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Callable

ARTIFACTS = ("manifest.json", "run_results.json")


class PublishError(Exception):
    pass


def dbt_task_run_id(client, job_run_id: int, dbt_task_key: str) -> int:
    run = client.jobs.get_run(job_run_id)
    for task in run.tasks or []:
        if task.task_key == dbt_task_key:
            return task.run_id
    raise PublishError(f"Job run {job_run_id} has no task '{dbt_task_key}'.")


def download_artifacts_archive(client, task_run_id: int,
                               fetch: Callable[[str, dict], bytes] | None = None) -> bytes:
    output = client.jobs.get_run_output(task_run_id)
    dbt_output = output.dbt_output
    if dbt_output is None or not dbt_output.artifacts_link:
        raise PublishError(f"Task run {task_run_id} has no dbt artifacts (dbt_output.artifacts_link).")
    return (fetch or _http_get)(dbt_output.artifacts_link, dict(dbt_output.artifacts_headers or {}))


def _http_get(url: str, headers: dict) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=300) as response:
        return response.read()


def extract_artifacts(archive: bytes) -> dict[str, bytes]:
    """manifest.json and run_results.json from dbt's `target/` in the archive.

    The archive layout is not documented, so take the files from the `target`
    directory nearest the archive root.
    """
    found: dict[str, tuple[int, bytes]] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if not member.isfile() or path.name not in ARTIFACTS or path.parent.name != "target":
                continue
            depth = len(path.parts)
            if path.name not in found or depth < found[path.name][0]:
                found[path.name] = (depth, tar.extractfile(member).read())
    missing = [name for name in ARTIFACTS if name not in found]
    if missing:
        raise PublishError(f"dbt artifacts archive has no target/{', target/'.join(missing)}.")
    return {name: content for name, (_, content) in found.items()}


def publish(artifacts: dict[str, bytes], volume: Path, job_run_id: int) -> None:
    run_dir = volume / "runs" / str(job_run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items():
        (run_dir / name).write_bytes(content)
    latest = volume / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for name in ARTIFACTS:
        shutil.copyfile(run_dir / name, latest / name)


def main(argv: list[str] | None = None, client=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--job-run-id", type=int, required=True)
    parser.add_argument("--dbt-task-key", required=True)
    parser.add_argument("--volume", type=Path, required=True, help="/Volumes/<catalog>/<schema>/<volume>")
    args = parser.parse_args(argv)

    if client is None:
        from databricks.sdk import WorkspaceClient

        client = WorkspaceClient()
    task_run_id = dbt_task_run_id(client, args.job_run_id, args.dbt_task_key)
    artifacts = extract_artifacts(download_artifacts_archive(client, task_run_id))
    publish(artifacts, args.volume, args.job_run_id)
    print(f"Published {', '.join(ARTIFACTS)} of run {args.job_run_id} to "
          f"{args.volume}/runs/{args.job_run_id}/ and {args.volume}/latest/.")


if __name__ == "__main__":
    main()
