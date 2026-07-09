"""Tests for aiohttp server endpoints and webhook orchestration."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from linear_orchestrator import __version__
from linear_orchestrator.config import Config
from linear_orchestrator.server import _healthz, make_app


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


def _make_cfg() -> Config:
    return Config(
        linear_api_key="lin_api_test",
        linear_webhook_secrets=["test-secret"],
        hermes_path="/tmp/hermes",
        host="127.0.0.1",
        port=8645,
        hermes_timeout_sec=30,
        default_model="",
        agent_linear_user_id="agent-user-1",
    )


def _signed_headers(secret: str, body: bytes, delivery_id: str) -> dict[str, str]:
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "Linear-Signature": sig,
        "Linear-Timestamp": ts,
        "Linear-Delivery": delivery_id,
    }


def test_linear_webhook_comment_event_runs_background_pipeline():
    async def _run():
        with TemporaryDirectory() as tmpdir, patch.dict(os.environ, {"HOME": tmpdir}, clear=False):
            cfg = _make_cfg()
            payload = {
                "type": "Comment",
                "action": "create",
                "data": {
                    "id": "c-1",
                    "body": "@hermes 幫我確認 smoke test",
                    "issueId": "issue-1",
                    "issue": {
                        "id": "issue-1",
                        "identifier": "EDG-63",
                        "title": "orchestrator e2e test",
                    },
                },
            }
            body = json.dumps(payload).encode("utf-8")
            headers = _signed_headers(cfg.linear_webhook_secrets[0], body, "delivery-comment-1")

            with patch(
                "linear_orchestrator.server.run_hermes",
                new_callable=AsyncMock,
                return_value=(True, "Hermes smoke test ack"),
            ) as mock_run, patch(
                "linear_orchestrator.server.write_back",
                new_callable=AsyncMock,
                return_value=(True, "comment ok=True url=https://linear.example/comment/1"),
            ) as mock_write:
                app = make_app(cfg)
                async with TestClient(TestServer(app)) as client:
                    resp = await client.post("/webhooks/linear", data=body, headers=headers)
                    assert resp.status == 202
                    data = await resp.json()
                    assert data["status"] == "queued"
                    assert data["session"] == "linear-issue-EDG-63"
                    await asyncio.gather(*tuple(app["_pending"]))

                mock_run.assert_awaited_once()
                mock_write.assert_awaited_once()
                delivery = app["store"]._conn.execute(
                    "SELECT status, detail, latency_ms FROM deliveries WHERE delivery_id=?",
                    ("delivery-comment-1",),
                ).fetchone()
                session = app["store"]._conn.execute(
                    "SELECT issue_id, issue_iden, events_count FROM sessions WHERE session_key=?",
                    ("linear-issue-EDG-63",),
                ).fetchone()
                payload_dump = (
                    Path(tmpdir)
                    / ".local"
                    / "share"
                    / "linear-orchestrator"
                    / "payloads"
                    / "delivery-comment-1.json"
                )

                assert delivery is not None
                assert delivery[0] == "written"
                assert "comment ok=True" in delivery[1]
                assert delivery[2] >= 0
                assert session == ("issue-1", "EDG-63", 1)
                assert payload_dump.exists()
                dumped_payload = json.loads(payload_dump.read_text(encoding="utf-8"))
                assert dumped_payload["data"]["body"] == "@hermes 幫我確認 smoke test"

    asyncio.run(_run())


def test_linear_webhook_agent_session_event_emits_thought_before_response():
    async def _run():
        with TemporaryDirectory() as tmpdir, patch.dict(os.environ, {"HOME": tmpdir}, clear=False):
            cfg = _make_cfg()
            payload = {
                "type": "AgentSessionEvent",
                "action": "created",
                "agentSession": {
                    "id": "as-63",
                    "issue": {
                        "id": "issue-63",
                        "identifier": "EDG-63",
                        "title": "orchestrator e2e test",
                    },
                },
            }
            body = json.dumps(payload).encode("utf-8")
            headers = _signed_headers(cfg.linear_webhook_secrets[0], body, "delivery-agent-1")
            call_order: list[str] = []

            async def _emit(ev):
                call_order.append(f"thought:{ev.agent_session_id}")
                return True, "agentActivity type=thought ok=True id=a1"

            async def _run_hermes(*args, **kwargs):
                call_order.append("hermes")
                return True, "Hermes agent session response"

            async def _write_back(*args, **kwargs):
                call_order.append("write_back")
                return True, "agentActivity type=response ok=True id=a2"

            with patch("linear_orchestrator.server.emit_thought_ack", side_effect=_emit), patch(
                "linear_orchestrator.server.run_hermes",
                side_effect=_run_hermes,
            ), patch(
                "linear_orchestrator.server.write_back",
                side_effect=_write_back,
            ):
                app = make_app(cfg)
                async with TestClient(TestServer(app)) as client:
                    resp = await client.post("/webhooks/linear", data=body, headers=headers)
                    assert resp.status == 202
                    data = await resp.json()
                    assert data["session"] == "linear-as-as-63"
                    await asyncio.gather(*tuple(app["_pending"]))

                delivery = app["store"]._conn.execute(
                    "SELECT status, detail FROM deliveries WHERE delivery_id=?",
                    ("delivery-agent-1",),
                ).fetchone()
                assert delivery == ("written", "agentActivity type=response ok=True id=a2")
                assert call_order == ["thought:as-63", "hermes", "write_back"]

    asyncio.run(_run())
