"""Tests for the aiohttp server health endpoint."""
from __future__ import annotations

import asyncio

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from linear_orchestrator import __version__
from linear_orchestrator.server import _healthz


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
