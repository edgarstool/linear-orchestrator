"""Normalise Linear webhook payload to a dict the rest of the pipeline understands."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    raw: dict
    type: str = ""             # Issue | Comment | AppUserNotification | AgentSessionEvent | ...
    action: str = ""           # create | update | remove | ...
    actor_id: str = ""
    actor_name: str = ""
    issue_id: str = ""
    issue_identifier: str = "" # e.g. WHO-210
    issue_title: str = ""
    issue_url: str = ""
    comment_body: str = ""
    body_text: str = ""        # generic text content (comment body, notification body)
    mentions_agent: bool = False
    agent_session_id: str = ""
    notes: list = field(default_factory=list)

    @property
    def session_key(self) -> str:
        """Pick a stable session id for hermes."""
        if self.agent_session_id:
            return f"linear-as-{self.agent_session_id}"
        if self.issue_identifier:
            return f"linear-issue-{self.issue_identifier}"
        if self.issue_id:
            return f"linear-issue-id-{self.issue_id}"
        return f"linear-{self.type or 'event'}"


def _g(d: dict, *keys, default=None):
    """Safe nested get."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


def parse(payload: dict, agent_user_id: str = "") -> Event:
    ev = Event(raw=payload)
    ev.type = str(payload.get("type", "")).strip()
    ev.action = str(payload.get("action", "")).strip()
    data = payload.get("data") or {}

    # actor
    actor = payload.get("actor") or data.get("actor") or {}
    ev.actor_id = str(actor.get("id", "") if isinstance(actor, dict) else "")
    ev.actor_name = str(actor.get("name", "") if isinstance(actor, dict) else "")

    # AgentSessionEvent — Linear's official agent protocol
    if ev.type == "AgentSessionEvent":
        # Linear sends `agentSession` at top level (not inside data) in newer payloads;
        # older shape had data.agentSession. Try both.
        agent_session = (payload.get("agentSession")
                         or data.get("agentSession")
                         or _g(data, "session")
                         or {})
        ev.agent_session_id = str(
            agent_session.get("id")
            or payload.get("agentSessionId")
            or data.get("agentSessionId")
            or ""
        )
        issue = (agent_session.get("issue") or
                 payload.get("issue") or
                 data.get("issue") or {})
        ev.issue_id = str(issue.get("id") or
                          agent_session.get("issueId") or
                          data.get("issueId") or
                          payload.get("issueId") or "")
        ev.issue_identifier = str(issue.get("identifier") or "")
        ev.issue_title = str(issue.get("title") or "")
        ev.issue_url = str(issue.get("url") or "")
        ev.body_text = str(
            agent_session.get("title")
            or payload.get("prompt")
            or data.get("prompt")
            or _g(payload, "comment", "body")
            or ""
        )
        ev.mentions_agent = True
        return ev

    # Issue events
    if ev.type == "Issue":
        ev.issue_id = str(data.get("id") or "")
        ev.issue_identifier = str(data.get("identifier") or "")
        ev.issue_title = str(data.get("title") or "")
        ev.issue_url = str(data.get("url") or "")
        ev.body_text = str(data.get("description") or "")
        assignee_id = str(_g(data, "assignee", "id") or data.get("assigneeId") or "")
        if agent_user_id and assignee_id == agent_user_id:
            ev.mentions_agent = True
            ev.notes.append("assigned to agent")
        return ev

    # Comment events
    if ev.type == "Comment":
        ev.issue_id = str(data.get("issueId") or _g(data, "issue", "id") or "")
        ev.issue_identifier = str(_g(data, "issue", "identifier") or "")
        ev.issue_title = str(_g(data, "issue", "title") or "")
        ev.issue_url = str(_g(data, "issue", "url") or "")
        ev.comment_body = str(data.get("body") or "")
        ev.body_text = ev.comment_body
        if agent_user_id and agent_user_id in ev.comment_body:
            ev.mentions_agent = True
            ev.notes.append("mentioned via id in body")
        for tag in ("@hermes", "@Hermes", "@HermesAgent", "@Hermes Agent"):
            if tag in ev.comment_body:
                ev.mentions_agent = True
                ev.notes.append(f"mentioned via {tag}")
                break
        return ev

    # AppUserNotification — Linear's real shape puts everything under top-level `notification`,
    # NOT under `data`. The wider Linear webhook envelope uses `data` only for some types.
    if ev.type == "AppUserNotification":
        notif = payload.get("notification") or data.get("notification") or data or {}
        ntype = str(notif.get("type") or data.get("type") or payload.get("action") or ev.action).strip()
        ev.actor_id = str(_g(notif, "actor", "id") or notif.get("actorId") or ev.actor_id)
        ev.actor_name = str(_g(notif, "actor", "name") or ev.actor_name)
        issue = notif.get("issue") or data.get("issue") or {}
        ev.issue_id = str(issue.get("id") or notif.get("issueId") or data.get("issueId") or "")
        ev.issue_identifier = str(issue.get("identifier") or "")
        ev.issue_title = str(issue.get("title") or "")
        ev.issue_url = str(issue.get("url") or "")
        ev.body_text = str(notif.get("commentBody") or notif.get("title")
                           or data.get("commentBody") or data.get("title") or "")
        ev.mentions_agent = ntype in {
            "issueMention", "issueAssignedToYou", "issueCommentMention",
            "issueNewComment", "issueDelegate", "issueAgentReady",
            "issueEmoji", "issueNewMention",
        }
        ev.notes.append(f"notification:{ntype}")
        return ev

    return ev


def should_act(ev: Event) -> tuple[bool, str]:
    """Decide whether to invoke hermes for this event."""
    if ev.type == "AgentSessionEvent":
        return True, "agent session"
    if ev.mentions_agent and ev.issue_id:
        return True, "mentioned + issue context"
    if ev.type == "Issue" and "assigned to agent" in ev.notes:
        return True, "issue assigned to agent"
    return False, f"skip: type={ev.type} action={ev.action} mentions={ev.mentions_agent}"
