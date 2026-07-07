"""Tests for workspace/session cleanup: hermes process-group teardown and the
background-task set that tracks in-flight work.

These cover EDG-149:
- dead hermes worker sessions (process groups) are killed, active ones untouched;
- completed *and* failed background tasks leave no residue in ``_pending``;
- cleanup is best-effort and idempotent.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from linear_orchestrator.runner import _terminate_process_group
from linear_orchestrator.server import _track_pending


async def _spawn_sleeper(code: str = "import time; time.sleep(30)"):
    return await asyncio.create_subprocess_exec(
        sys.executable, "-c", code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )


@pytest.mark.asyncio
async def test_terminate_process_group_kills_running_process():
    proc = await _spawn_sleeper()
    assert proc.returncode is None
    await _terminate_process_group(proc)
    assert proc.returncode is not None  # reaped


@pytest.mark.asyncio
async def test_terminate_process_group_is_idempotent():
    proc = await _spawn_sleeper()
    await _terminate_process_group(proc)
    rc = proc.returncode
    # Calling again on an already-dead process must be a safe no-op.
    await _terminate_process_group(proc)
    assert proc.returncode == rc


@pytest.mark.asyncio
async def test_terminate_process_group_noop_on_finished_process():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "pass",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    await proc.wait()
    await _terminate_process_group(proc)  # must not raise
    assert proc.returncode is not None


def _terminated(pid: int) -> bool:
    """True if pid is gone or a zombie (i.e. no longer a live worker)."""
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("State:"):
                    return line.split()[1] == "Z"
    except FileNotFoundError:
        return True
    return False


@pytest.mark.skipif(sys.platform != "linux", reason="uses /proc + process groups")
@pytest.mark.asyncio
async def test_terminate_kills_whole_process_group():
    # Parent spawns a grandchild in the same session, prints its pid, then waits.
    code = (
        "import subprocess, sys, time;"
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']);"
        "print(c.pid, flush=True);"
        "time.sleep(30)"
    )
    proc = await _spawn_sleeper(code)
    line = await asyncio.wait_for(proc.stdout.readline(), timeout=10)
    grandchild = int(line.strip())

    await _terminate_process_group(proc)

    for _ in range(40):  # up to ~2s for the OS to tear the group down
        if _terminated(grandchild):
            break
        await asyncio.sleep(0.05)
    assert _terminated(grandchild), "grandchild worker survived group termination"


@pytest.mark.asyncio
async def test_track_pending_discards_completed_task():
    app = {"_pending": set()}

    async def _work():
        return 42

    task = _track_pending(app, _work())
    assert task in app["_pending"]
    await task
    await asyncio.sleep(0)  # let the done-callback run
    assert app["_pending"] == set()


@pytest.mark.asyncio
async def test_track_pending_discards_failed_task():
    app = {"_pending": set()}

    async def _boom():
        raise RuntimeError("boom")

    task = _track_pending(app, _boom())
    with pytest.raises(RuntimeError):
        await task
    await asyncio.sleep(0)
    assert app["_pending"] == set()


@pytest.mark.asyncio
async def test_track_pending_discards_cancelled_task():
    app = {"_pending": set()}

    async def _long():
        await asyncio.sleep(30)

    task = _track_pending(app, _long())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
    assert app["_pending"] == set()
