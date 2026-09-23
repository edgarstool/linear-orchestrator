"""Tests for the aiohttp server health, webhook persistence, and state endpoint."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from linear_orchestrator import __version__, server, state as state_paths
from linear_orchestrator.config import Config
from linear_orchestrator.server import _healthz, make_app

SECRET = "test-secret"


def test_healthz_returns_status_and_version():
    async def _run():
        app = web.Application()
        app.router.add_get("/healthz", _healthz)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/healthz")
            assert resp.status == 200
            assert resp.content_type == "application/json"
            return await resp.json()

    data = asyncio.run(_run())
    assert data == {"status": "ok", "version": "0.1.0"}
    assert data["version"] == __version__


def _cfg() -> Config:
    return Config(
        linear_api_key="k",
        linear_webhook_secrets=[SECRET],
        hermes_path="/bin/true",
        host="*********",
        port=8645,
        hermes_timeout_sec=5,
        default_model="",
        agent_linear_user_id="",
    )


def _signed(payload: dict) -> tuple[bytes, dict]:
    payload = {**payload, "webhookTimestamp": int(time.time() * 1000)}
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {"Content-Type": "application/json",
                  "Linear-Signature": sig,
                  "Linear-Delivery": "d-int-1"}


def test_webhook_payload_and_delivery_land_in_durable_state(tmp_path, monkeypatch):
    monkeypatch.setenv(state_paths.ENV_STATE_DIR, str(tmp_path / "state"))
    monkeypatch.delenv(state_paths.ENV_BACKUP_DIR, raising=False)
    monkeypatch.setenv("STATE_BACKUP_INTERVAL_SEC", "0")

    async def _fake_run_hermes(ev, path, timeout, session_key, model=""):
        return True, "reply"

    async def _fake_write_back(ev, reply, api_key):
        return True, "written"

    monkeypatch.setattr(server, "run_hermes", _fake_run_hermes)
    monkeypatch.setattr(server, "write_back", _fake_write_back)

    body, headers = _signed({
        "type": "Comment",
        "action": "create",
        "data": {"body": "@hermes ping", "issueId": "i1",
                 "issue": {"id": "i1", "identifier": "EDG-86"}},
    })

    async def _run():
        app = make_app(_cfg())
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/webhooks/linear", data=body, headers=headers)
            assert resp.status == 202
            await asyncio.gather(*app["_pending"])

            stored = await (await client.get("/payloads/d-int-1")).json()
            state = await (await client.get("/state")).json()
            backup = await (await client.post("/state/backup")).json()
            return stored, state, backup

    stored, state, backup = asyncio.run(_run())
    assert stored["data"]["issue"]["identifier"] == "EDG-86"
    assert state["db_path"] == str(tmp_path / "state" / "sessions.db")
    assert state["integrity"] == "ok"
    assert state["counts"]["payloads"] == 1
    assert state["counts"]["pending_deliveries"] == 0
    assert backup["status"] == "ok"
    assert backup["bytes"] > 0
