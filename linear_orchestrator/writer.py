"""Write agent reply back to Linear (comment or agent session activity)."""
from __future__ import annotations
import logging
import os
import time
import aiohttp
from .parser import Event

log = logging.getLogger("orch.writer")
LINEAR_GQL = "https://api.linear.app/graphql"
LINEAR_OAUTH = "https://api.linear.app/oauth/token"

# Module-level cached OAuth token (client_credentials grant). agentActivityCreate
# REJECTS personal API keys — only OAuth-app tokens may post agent activity.
_app_token: dict = {"token": "", "expires_at": 0.0}


async def _get_app_token(session: aiohttp.ClientSession) -> str:
    """Fetch + cache an OAuth app token using client_credentials grant."""
    if _app_token["token"] and _app_token["expires_at"] > time.time() + 60:
        return _app_token["token"]
    client_id = os.environ.get("LINEAR_OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("LINEAR_OAUTH_CLIENT_SECRET", "")
    if not (client_id and client_secret):
        return ""
    try:
        async with session.post(
            LINEAR_OAUTH,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "read,write,app:assignable,app:mentionable",
            },
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            d = await r.json(content_type=None)
            tok = d.get("access_token") or ""
            ttl = int(d.get("expires_in") or 0)
            if tok:
                _app_token["token"] = tok
                _app_token["expires_at"] = time.time() + ttl
                log.info("OAuth app token refreshed, ttl=%ds", ttl)
            else:
                log.warning("OAuth client_credentials failed: %s", str(d)[:200])
            return tok
    except Exception as e:
        log.warning("OAuth token fetch error: %s", e)
        return ""


async def _gql(session: aiohttp.ClientSession, auth: str, query: str, variables: dict) -> dict:
    """auth is a full Authorization header value: either 'lin_api_...' or 'Bearer <oauth>'."""
    async with session.post(
        LINEAR_GQL,
        json={"query": query, "variables": variables},
        headers={"Authorization": auth, "Content-Type": "application/json"},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as r:
        text = await r.text()
        if r.status >= 400:
            log.warning("linear gql %d: %s", r.status, text[:300])
            return {"error": text[:300]}
        try:
            return await r.json(content_type=None) if not text else __import__("json").loads(text)
        except Exception:
            return {"raw": text[:300]}


COMMENT_MUTATION = """
mutation CommentCreate($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment { id url }
  }
}
"""


AGENT_ACTIVITY_MUTATION = """
mutation AgentActivityCreate($input: AgentActivityCreateInput!) {
  agentActivityCreate(input: $input) {
    success
    agentActivity { id }
  }
}
"""


def _dig(d, *keys, default=None):
    """Null-safe nested get — treats both missing keys AND None values as 'not present'."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


async def write_back(ev: Event, reply: str, api_key: str) -> tuple[bool, str]:
    """Returns (ok, detail)."""
    if not reply.strip():
        return True, "no reply (skip)"

    async with aiohttp.ClientSession() as session:
        if ev.agent_session_id:
            # agentActivityCreate requires an OAuth app token (client_credentials grant).
            # Personal API keys are explicitly rejected by Linear with FORBIDDEN.
            oauth = await _get_app_token(session)
            if not oauth:
                return False, "no OAuth app token; set LINEAR_OAUTH_CLIENT_ID/SECRET"
            data = await _gql(session, f"Bearer {oauth}", AGENT_ACTIVITY_MUTATION, {
                "input": {
                    "agentSessionId": ev.agent_session_id,
                    "content": {"type": "response", "body": reply},
                }
            })
            ok = bool(_dig(data, "data", "agentActivityCreate", "success", default=False))
            act_id = _dig(data, "data", "agentActivityCreate", "agentActivity", "id", default="")
            errors = data.get("errors") if isinstance(data, dict) else None
            detail = f"agentActivity ok={ok} id={act_id}"
            if errors:
                detail += f" errors={str(errors)[:250]}"
            return ok, detail

        if not ev.issue_id:
            return False, "no issue_id and no agent_session_id; nowhere to write"

        data = await _gql(session, api_key, COMMENT_MUTATION, {
            "issueId": ev.issue_id,
            "body": reply,
        })
        ok = bool(_dig(data, "data", "commentCreate", "success", default=False))
        url = _dig(data, "data", "commentCreate", "comment", "url", default="")
        errors = data.get("errors") if isinstance(data, dict) else None
        detail = f"comment ok={ok} url={url}"
        if errors:
            detail += f" errors={str(errors)[:250]}"
        return ok, detail
