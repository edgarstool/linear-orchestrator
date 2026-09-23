"""Tests for crash / failed-deploy recovery at startup."""
from __future__ import annotations

import asyncio

import pytest
from aiohttp import web

from linear_orchestrator import server, state as state_paths
from linear_orchestrator.broadcast import Broadcaster
from linear_orchestrator.config import Config
from linear_orchestrator.session import SessionStore

PAYLOAD = {
    "type": "Comment",
    "action": "create",
    "data": {"body": "@hermes ping", "issue": {"id": "i1", "identifier": "EDG-86"}},
}


def _cfg() -> Config:
    return Config(
        linear_api_key="k",
        linear_webhook_secrets=["s"],
        hermes_path="/bin/true",
        host="127.0.0.1",
        port=8645,
        hermes_timeout_sec=5,
        default_model="",
        agent_linear_user_id="",
    )


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv(state_paths.ENV_STATE_DIR, str(tmp_path / "state"))
    monkeypatch.delenv(state_paths.ENV_BACKUP_DIR, raising=False)
    application = web.Application()
    application["cfg"] = _cfg()
    application["store"] = SessionStore()
    application["bcast"] = Broadcaster()
    application["_pending"] = set()
    yield application
    application["store"].close()


@pytest.fixture
def processed(monkeypatch):
    """Capture replays instead of actually invoking hermes."""
    seen: list[str] = []

    async def _fake_process(cfg, store, ev, delivery_id, broadcaster):
        seen.append(delivery_id)

    monkeypatch.setattr(server, "_process", _fake_process)
    return seen


def test_recovery_replays_interrupted_delivery(app, processed):
    store: SessionStore = app["store"]
    store.save_payload("d-1", "linear-issue-EDG-86", PAYLOAD)
    store.record_delivery("d-1", "linear-issue-EDG-86", "queued", "accepted")

    async def _run():
        summary = server.recover_state(app)
        await asyncio.gather(*app["_pending"])
        return summary

    summary = asyncio.run(_run())
    assert summary["interrupted"] == ["d-1"]
    assert summary["resumed"] == ["d-1"]
    assert len(processed) == 1 and processed[0].startswith("resume-d-1-")
    # the original delivery is closed out, not left dangling; only the fresh
    # replay (still in flight in this test) remains pending
    assert store._conn.execute(
        "SELECT status FROM deliveries WHERE delivery_id='d-1'"
    ).fetchone()[0] == "interrupted"
    assert [p["delivery_id"] for p in store.list_pending()] == [processed[0]]


def test_recovery_skips_stale_deliveries(app, processed, monkeypatch):
    monkeypatch.setenv("STATE_RESUME_MAX_AGE_SEC", "60")
    store: SessionStore = app["store"]
    store.save_payload("d-old", "s1", PAYLOAD)
    store.record_delivery("d-old", "s1", "queued", "accepted")
    store._conn.execute("UPDATE deliveries SET ts='2000-01-01T00:00:00+00:00' "
                        "WHERE delivery_id='d-old'")
    store._conn.commit()

    summary = asyncio.run(_recover(app))
    assert summary["resumed"] == []
    assert summary["skipped"] == ["d-old"]
    assert processed == []


def test_recovery_can_be_disabled(app, processed, monkeypatch):
    monkeypatch.setenv("STATE_AUTO_RESUME", "0")
    store: SessionStore = app["store"]
    store.save_payload("d-1", "s1", PAYLOAD)
    store.record_delivery("d-1", "s1", "running", "processing started")

    summary = asyncio.run(_recover(app))
    assert summary["auto_resume"] is False
    assert summary["resumed"] == []
    assert summary["skipped"] == ["d-1"]
    assert processed == []


def test_recovery_imports_legacy_payload_files(app, processed, tmp_path):
    legacy = state_paths.state_dir() / "payloads"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "d-legacy.json").write_text('{"type": "Issue"}', encoding="utf-8")

    summary = asyncio.run(_recover(app))
    assert summary["legacy_payloads_imported"] == 1
    assert app["store"].load_payload("d-legacy") == {"type": "Issue"}


async def _recover(app):
    summary = server.recover_state(app)
    if app["_pending"]:
        await asyncio.gather(*app["_pending"])
    return summary
