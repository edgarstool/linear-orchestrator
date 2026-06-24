"""aiohttp server: receive Linear webhook → parse → run hermes → write back."""
from __future__ import annotations
import asyncio
import json
import logging
import time
from pathlib import Path
from aiohttp import web

from .config import Config
from .sig import verify as verify_sig
from .parser import parse as parse_event, should_act
from .session import SessionStore
from .runner import run_hermes
from .writer import write_back
from .broadcast import Broadcaster
from .dashboard import index as dashboard_index

log = logging.getLogger("orch.server")


async def _handle_linear(request: web.Request) -> web.Response:
    cfg: Config = request.app["cfg"]
    store: SessionStore = request.app["store"]
    body = await request.read()
    sig = request.headers.get("Linear-Signature", "")
    ts = request.headers.get("Linear-Timestamp", "")
    delivery_id = (request.headers.get("Linear-Delivery", "") or
                   request.headers.get("X-Request-ID", "") or
                   f"d-{int(time.time()*1000)}")

    ok, reason = verify_sig(body, cfg.linear_webhook_secret, sig, ts)
    if not ok:
        log.warning("sig verify failed: %s", reason)
        return web.json_response({"error": "invalid signature", "reason": reason}, status=401)

    if store.already_processed(delivery_id):
        return web.json_response({"status": "duplicate", "delivery_id": delivery_id})

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as e:
        return web.json_response({"error": f"bad json: {e}"}, status=400)

    # Debug dump of every accepted webhook payload for offline parser tuning.
    # Path is cheap to disable later; useful while we're still discovering Linear's real schemas.
    try:
        import pathlib
        dump_dir = pathlib.Path.home() / ".local" / "share" / "linear-orchestrator" / "payloads"
        dump_dir.mkdir(parents=True, exist_ok=True)
        (dump_dir / f"{int(time.time()*1000)}_{payload.get('type','unknown')}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    ev = parse_event(payload, cfg.agent_linear_user_id)
    act, why = should_act(ev)
    log.info("event type=%s action=%s issue=%s session=%s act=%s why=%s",
             ev.type, ev.action, ev.issue_identifier, ev.session_key, act, why)

    store.upsert(ev.session_key, ev.issue_id, ev.issue_identifier, ev.agent_session_id)

    if not act:
        store.record_delivery(delivery_id, ev.session_key, "skip", why)
        return web.json_response({"status": "skip", "reason": why,
                                  "session": ev.session_key,
                                  "delivery_id": delivery_id})

    # respond fast to Linear; do the heavy work in background
    request.app["_pending"].add(asyncio.create_task(
        _process(cfg, store, ev, delivery_id, request.app["bcast"])
    ))
    return web.json_response({"status": "queued", "session": ev.session_key,
                              "delivery_id": delivery_id, "act_reason": why}, status=202)


async def _process(cfg: Config, store: SessionStore, ev, delivery_id: str,
                   broadcaster: Broadcaster) -> None:
    try:
        await broadcaster.publish(ev.session_key, {
            "type": "received", "delivery_id": delivery_id,
            "event_type": ev.type, "action": ev.action,
            "issue_identifier": ev.issue_identifier,
        })
        log.info("→ run hermes for delivery=%s session=%s", delivery_id, ev.session_key)
        await broadcaster.publish(ev.session_key, {"type": "hermes.started", "delivery_id": delivery_id})
        ok, reply = await run_hermes(ev, cfg.hermes_path, cfg.hermes_timeout_sec,
                                     ev.session_key, cfg.default_model)
        if not ok:
            log.warning("hermes failed: %s", reply[:200])
            store.record_delivery(delivery_id, ev.session_key, "hermes_fail", reply[:1000])
            await broadcaster.publish(ev.session_key, {"type": "hermes.failed",
                                                        "delivery_id": delivery_id, "error": reply[:300]})
            return
        if not reply:
            store.record_delivery(delivery_id, ev.session_key, "hermes_skip", "agent returned __SKIP__")
            await broadcaster.publish(ev.session_key, {"type": "hermes.skip", "delivery_id": delivery_id})
            return
        log.info("← hermes replied %d chars; writing back", len(reply))
        await broadcaster.publish(ev.session_key, {"type": "hermes.replied",
                                                    "delivery_id": delivery_id, "chars": len(reply),
                                                    "reply_preview": reply[:300]})
        ok_w, detail = await write_back(ev, reply, cfg.linear_api_key)
        store.record_delivery(delivery_id, ev.session_key,
                              "written" if ok_w else "write_fail", detail[:1000])
        await broadcaster.publish(ev.session_key, {
            "type": "written" if ok_w else "write_fail",
            "delivery_id": delivery_id, "detail": detail[:500],
        })
    except Exception as e:
        log.exception("process error")
        store.record_delivery(delivery_id, ev.session_key, "exception", str(e)[:500])
        await broadcaster.publish(ev.session_key, {"type": "exception",
                                                    "delivery_id": delivery_id, "error": str(e)[:300]})


async def _healthz(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "ts": int(time.time())})


async def _stream(request: web.Request) -> web.StreamResponse:
    """NDJSON stream of events for a session key. Use '*' for all sessions."""
    session_key = request.match_info["session_key"]
    response = web.StreamResponse(status=200, headers={
        "Content-Type": "application/x-ndjson; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
    })
    await response.prepare(request)
    await request.app["bcast"].stream(session_key, response)
    return response


async def _list_sessions(request: web.Request) -> web.Response:
    store: SessionStore = request.app["store"]
    rows = store._conn.execute(
        "SELECT session_key, issue_iden, agent_sess, events_count, last_seen "
        "FROM sessions ORDER BY last_seen DESC LIMIT 50"
    ).fetchall()
    return web.json_response([
        {"session_key": r[0], "issue": r[1], "agent_session": r[2],
         "events": r[3], "last_seen": r[4]} for r in rows
    ])


async def _list_deliveries(request: web.Request) -> web.Response:
    store: SessionStore = request.app["store"]
    rows = store._conn.execute(
        "SELECT delivery_id, ts, session_key, status, substr(detail,1,300) "
        "FROM deliveries ORDER BY ts DESC LIMIT 30"
    ).fetchall()
    return web.json_response([
        {"delivery_id": r[0], "ts": r[1], "session_key": r[2],
         "status": r[3], "detail": r[4]} for r in rows
    ])


def make_app(cfg: Config | None = None) -> web.Application:
    cfg = cfg or Config.from_env()
    db_path = Path.home() / ".local" / "share" / "linear-orchestrator" / "sessions.db"
    store = SessionStore(db_path)
    app = web.Application()
    app["cfg"] = cfg
    app["store"] = store
    app["bcast"] = Broadcaster()
    app["_pending"] = set()
    app.router.add_post("/webhooks/linear", _handle_linear)
    app.router.add_get("/healthz", _healthz)
    app.router.add_get("/sessions", _list_sessions)
    app.router.add_get("/deliveries", _list_deliveries)
    app.router.add_get("/sessions/{session_key}/stream", _stream)
    app.router.add_get("/", dashboard_index)
    return app


def run() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = Config.from_env()
    app = make_app(cfg)
    log.info("linear-orchestrator listening on %s:%s", cfg.host, cfg.port)
    web.run_app(app, host=cfg.host, port=cfg.port, print=None, access_log=None)


if __name__ == "__main__":
    run()
