"""Durable, project-scoped scientific job controller."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .command_registry import command_spec
from .execution_policy import command_allowed_via_mcp, sanitized_environment
from .project_state import load_project


JOB_DB = ".draftpaper/jobs.sqlite3"
MAX_CAPTURE_BYTES = 64 * 1024
TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled", "timed_out", "orphaned"})


def _db(project: str | Path, *, create: bool = True) -> tuple[Path, Path]:
    state = load_project(project)
    path = state.path / JOB_DB
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    return state.path, path


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY, project_path TEXT NOT NULL, command TEXT NOT NULL,
            arguments_json TEXT NOT NULL, idempotency_key TEXT, status TEXT NOT NULL,
            process_status TEXT NOT NULL, command_status TEXT, scientific_decision TEXT,
            transaction_status TEXT, failure_class TEXT, worker_pid INTEGER,
            submitted_at REAL NOT NULL, started_at REAL, completed_at REAL,
            timeout_seconds INTEGER NOT NULL, attempt INTEGER NOT NULL DEFAULT 1,
            stdout_tail TEXT, stderr_tail TEXT, result_json TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS jobs_idempotency ON jobs(idempotency_key) WHERE idempotency_key IS NOT NULL;
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
            created_at REAL NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    return connection


def _job_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    payload["arguments"] = json.loads(payload.pop("arguments_json") or "{}")
    payload["result"] = json.loads(payload.pop("result_json") or "null")
    return payload


def submit_job(
    project: str | Path,
    job_command: str,
    arguments_json: str | None = None,
    idempotency_key: str | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    root, db_path = _db(project)
    spec = command_spec(job_command)
    if spec is None:
        raise ValueError(f"Unknown Draftpaper command: {job_command}")
    if job_command in {"submit-job", "job-status", "job-cancel", "job-notifications", "recover-jobs"}:
        raise ValueError("Job-controller commands cannot recursively submit themselves.")
    allowed, reason = command_allowed_via_mcp(spec)
    if not allowed:
        raise ValueError(f"The command is not eligible for unattended execution: {reason}")
    arguments = json.loads(arguments_json or "{}")
    if not isinstance(arguments, dict):
        raise ValueError("--arguments-json must contain one JSON object.")
    supplied_project = arguments.get("project")
    if supplied_project and Path(str(supplied_project)).resolve() != root.resolve():
        raise ValueError("A job cannot target a different project root.")
    arguments["project"] = str(root)
    timeout = int(timeout_seconds or spec.timeout_seconds)
    if timeout <= 0 or timeout > 7 * 24 * 3600:
        raise ValueError("Job timeout must be between 1 second and 7 days.")
    job_id = uuid.uuid4().hex
    submitted = time.time()
    with _connect(db_path) as connection:
        if idempotency_key:
            existing = connection.execute("SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing:
                return {"status": "existing", "job": _job_row(existing)}
        connection.execute(
            "INSERT INTO jobs (job_id, project_path, command, arguments_json, idempotency_key, status, process_status, submitted_at, timeout_seconds) VALUES (?, ?, ?, ?, ?, 'submitted', 'pending', ?, ?)",
            (job_id, str(root), job_command, json.dumps(arguments, ensure_ascii=False), idempotency_key, submitted, timeout),
        )
    worker = [sys.executable, "-m", "draftpaper_cli.job_worker", "--database", str(db_path), "--job-id", job_id]
    worker_env = sanitized_environment()
    package_root = str(Path(__file__).resolve().parent.parent)
    worker_env["PYTHONPATH"] = package_root + (os.pathsep + worker_env["PYTHONPATH"] if worker_env.get("PYTHONPATH") else "")
    kwargs: dict[str, Any] = {"cwd": str(root), "env": worker_env, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(worker, **kwargs)
    with _connect(db_path) as connection:
        connection.execute("UPDATE jobs SET worker_pid = ?, status = 'running', process_status = 'running', started_at = ? WHERE job_id = ?", (process.pid, time.time(), job_id))
    return {"status": "submitted", "job_id": job_id, "worker_pid": process.pid, "database": JOB_DB, "timeout_seconds": timeout}


def job_status(project: str | Path, job_id: str) -> dict[str, Any]:
    _, db_path = _db(project, create=False)
    if not db_path.is_file():
        return {"status": "not_found", "job_id": job_id}
    with _connect(db_path) as connection:
        row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return {"status": "not_found", "job_id": job_id}
    return {"status": "found", "job": _job_row(row)}


def wait_for_job(
    project: str | Path,
    job_id: str,
    *,
    timeout_seconds: float = 60.0,
    poll_interval: float = 0.1,
) -> dict[str, Any]:
    """Wait for one job without confusing a polling deadline with job failure."""
    if timeout_seconds < 0:
        raise ValueError("Wait timeout must be non-negative.")
    if poll_interval <= 0:
        raise ValueError("Poll interval must be positive.")
    deadline = time.monotonic() + timeout_seconds
    while True:
        result = job_status(project, job_id)
        job = result.get("job") or {}
        if result.get("status") == "not_found":
            return {**result, "wait_status": "not_found"}
        if job.get("status") in TERMINAL_JOB_STATUSES:
            return {**result, "wait_status": "terminal"}
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {**result, "wait_status": "deadline_exceeded"}
        time.sleep(min(poll_interval, remaining))


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def job_cancel(project: str | Path, job_id: str) -> dict[str, Any]:
    _, db_path = _db(project)
    with _connect(db_path) as connection:
        row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return {"status": "not_found", "job_id": job_id}
        pid = row["worker_pid"]
        if row["status"] in TERMINAL_JOB_STATUSES:
            return {"status": "already_terminal", "job": _job_row(row)}
        if _pid_alive(pid):
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)
            else:
                os.killpg(int(pid), signal.SIGTERM)
        connection.execute("UPDATE jobs SET status = 'cancelled', process_status = 'cancelled', completed_at = ?, failure_class = 'user_cancelled' WHERE job_id = ?", (time.time(), job_id))
        connection.execute("INSERT INTO notifications (job_id, created_at, level, message) VALUES (?, ?, 'info', 'Job cancelled by user.')", (job_id, time.time()))
    return {"status": "cancelled", "job_id": job_id}


def job_notifications(project: str | Path, job_id: str | None = None) -> dict[str, Any]:
    _, db_path = _db(project, create=False)
    if not db_path.is_file():
        return {"status": "listed", "notifications": []}
    with _connect(db_path) as connection:
        if job_id:
            rows = connection.execute("SELECT * FROM notifications WHERE job_id = ? ORDER BY notification_id", (job_id,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM notifications ORDER BY notification_id DESC LIMIT 100").fetchall()
    return {"status": "listed", "notifications": [dict(row) for row in rows]}


def recover_jobs(project: str | Path) -> dict[str, Any]:
    _, db_path = _db(project)
    recovered = []
    with _connect(db_path) as connection:
        rows = connection.execute("SELECT * FROM jobs WHERE status IN ('submitted', 'running')").fetchall()
        for row in rows:
            if _pid_alive(row["worker_pid"]):
                recovered.append({"job_id": row["job_id"], "status": "running"})
                continue
            connection.execute("UPDATE jobs SET status = 'orphaned', process_status = 'orphaned', completed_at = ?, failure_class = 'worker_process_lost' WHERE job_id = ?", (time.time(), row["job_id"]))
            connection.execute("INSERT INTO notifications (job_id, created_at, level, message) VALUES (?, ?, 'error', 'Worker process was lost; the job is orphaned and was not scientifically retried.')", (row["job_id"], time.time()))
            recovered.append({"job_id": row["job_id"], "status": "orphaned"})
    return {"status": "recovered", "jobs": recovered, "scientific_failures_retried": False}


def _argv(command: str, arguments: dict[str, Any]) -> list[str]:
    result = [command]
    for key, value in arguments.items():
        option = "--" + str(key).replace("_", "-")
        if isinstance(value, bool):
            if value:
                result.append(option)
        elif isinstance(value, list):
            for item in value:
                result.extend([option, str(item)])
        elif value is not None:
            result.extend([option, str(value)])
    return result


def run_job_worker(database: str | Path, job_id: str) -> int:
    db_path = Path(database).resolve()
    with _connect(db_path) as connection:
        row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return 2
        arguments = json.loads(row["arguments_json"])
        command = str(row["command"])
        timeout = int(row["timeout_seconds"])
        project_path = str(row["project_path"])
        connection.execute("UPDATE jobs SET status = 'running', process_status = 'running', worker_pid = ?, started_at = COALESCE(started_at, ?) WHERE job_id = ?", (os.getpid(), time.time(), job_id))
    try:
        child_env = sanitized_environment()
        package_root = str(Path(__file__).resolve().parent.parent)
        child_env["PYTHONPATH"] = package_root + (os.pathsep + child_env["PYTHONPATH"] if child_env.get("PYTHONPATH") else "")
        completed = subprocess.run([sys.executable, "-m", "draftpaper_cli.cli", *_argv(command, arguments)], cwd=project_path, env=child_env, capture_output=True, text=True, timeout=timeout)
        process_status = "completed"
        status = "completed" if completed.returncode == 0 else "failed"
        failure_class = None if completed.returncode == 0 else "scientific_or_command_nonzero"
    except subprocess.TimeoutExpired as exc:
        completed = None
        process_status = "timed_out"; status = "timed_out"; failure_class = "infrastructure_timeout"
        stdout = str(exc.stdout or ""); stderr = str(exc.stderr or "")
    else:
        stdout = completed.stdout; stderr = completed.stderr
    stdout = stdout[-MAX_CAPTURE_BYTES:]; stderr = stderr[-MAX_CAPTURE_BYTES:]
    result = None
    for line in reversed(stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            result = candidate; break
    command_status = str((result or {}).get("status") or status)
    scientific = str((result or {}).get("decision") or (result or {}).get("scientific_decision") or ("pass" if completed and completed.returncode == 0 else "non_passing"))
    transaction = "committed" if process_status == "completed" else "not_committed"
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE jobs SET status=?, process_status=?, command_status=?, scientific_decision=?, transaction_status=?, failure_class=?, completed_at=?, stdout_tail=?, stderr_tail=?, result_json=? WHERE job_id=?",
            (status, process_status, command_status, scientific, transaction, failure_class, time.time(), stdout, stderr, json.dumps(result, ensure_ascii=False) if result else None, job_id),
        )
        level = "info" if status == "completed" else "error"
        connection.execute("INSERT INTO notifications (job_id, created_at, level, message) VALUES (?, ?, ?, ?)", (job_id, time.time(), level, f"Job {status}; scientific decision: {scientific}."))
    return 0 if status == "completed" else 1
