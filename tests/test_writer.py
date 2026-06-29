"""Tests for Linear agent session writeback helpers."""
from __future__ import annotations
from unittest.mock import AsyncMock, patch

import pytest

from linear_orchestrator.parser import parse
from linear_orchestrator.writer import emit_thought_ack


@pytest.mark.asyncio
async def test_emit_thought_ack_uses_thought_type_for_created():
    ev = parse({
        "type": "AgentSessionEvent",
        "action": "created",
        "agentSession": {
            "id": "as-123",
            "issue": {"id": "i1", "identifier": "EDG-1"},
        },
    })
    with patch(
        "linear_orchestrator.writer._post_agent_activity",
        new_callable=AsyncMock,
        return_value=(True, "agentActivity type=thought ok=True id=a1"),
    ) as mock_post:
        ok, detail = await emit_thought_ack(ev)
    assert ok is True
    mock_post.assert_awaited_once()
    args = mock_post.await_args[0]
    assert args[1] == "as-123"
    assert args[2] == "thought"
    assert "收到委派" in args[3]


@pytest.mark.asyncio
async def test_emit_thought_ack_no_session():
    ev = parse({"type": "Comment", "action": "create", "data": {"body": "hi"}})
    ok, detail = await emit_thought_ack(ev)
    assert ok is False
    assert "no agent_session_id" in detail
