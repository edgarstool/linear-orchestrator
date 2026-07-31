"""Durable runtime state: Linear issue/agent-session ↔ hermes session mapping,
delivery bookkeeping, and the webhook payloads needed to replay work.

SQLite is the single source of truth for everything the orchestrator must
survive a crash, restart, or failed deploy with. See
``docs/STATE-PERSISTENCE.zh-TW.md`` for the backup/restore contract.
"""
from __future__ import annotations
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

from . import state as state_paths

log = logging.getLogger("orch.session")


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_key  TEXT PRIMARY KEY,
  hermes_id    TEXT,
  issue_id     TEXT,
  issue_iden   TEXT,
  agent_sess   TEXT,
  first_seen   TEXT,
  last_seen    TEXT,
  events_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS deliveries (
  delivery_id TEXT PRIMARY KEY,
  ts          TEXT,
  session_key TEXT,
  status      TEXT,
  detail      TEXT,
  latency_ms  INTEGER DEFAULT 0
);
-- Webhook payloads used by /retry and by crash recovery. These used to be
-- loose JSON files on local disk (a single point of failure); they now live
-- with the rest of the durable state.
CREATE TABLE IF NOT EXISTS payloads (
  delivery_id TEXT PRIMARY KEY,
  ts          TEXT,
  session_key TEXT,
  body        TEXT
);
CREATE INDEX IF NOT EXISTS idx_deliveries_ts ON deliveries(ts);
CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status);
CREATE INDEX IF NOT EXISTS idx_payloads_ts ON payloads(ts);
-- back-compat add column for older sqlite files (no-op if exists)
"""

#: Statuses meaning "work was accepted but never reached a conclusion".
#: Anything left in one of these after a restart was killed mid-flight.
PENDING_STATUSES = ("queued", "running")


def _maybe_add_latency_column(conn: sqlite3.Connection) -> None:
    """Old databases predate latency_ms; add it as a no-op upgrade."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(deliveries)").fetchall()}
    if "latency_ms" not in cols:
        conn.execute("ALTER TABLE deliveries ADD COLUMN latency_ms INTEGER DEFAULT 0")
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else state_paths.db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        # WAL keeps readers and the writer from blocking each other and gives
        # crash-safe commits; synchronous=FULL means an accepted webhook is on
        # disk before we answer Linear.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(SCHEMA)
        _maybe_add_latency_column(self._conn)
        self._conn.commit()

    # ---------------------------------------------------------------- sessions

    def upsert(self, session_key: str, issue_id: str = "", issue_iden: str = "",
               agent_sess: str = "") -> None:
        now = _now()
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO sessions(session_key,issue_id,issue_iden,agent_sess,first_seen,last_seen,events_count)
               VALUES(?,?,?,?,?,?,1)
               ON CONFLICT(session_key) DO UPDATE SET
                 last_seen=excluded.last_seen,
                 events_count=events_count+1""",
            (session_key, issue_id, issue_iden, agent_sess, now, now),
        )
        self._conn.commit()

    # -------------------------------------------------------------- deliveries

    def already_processed(self, delivery_id: str) -> bool:
        cur = self._conn.cursor()
        row = cur.execute("SELECT 1 FROM deliveries WHERE delivery_id=?", (delivery_id,)).fetchone()
        return row is not None

    def record_delivery(self, delivery_id: str, session_key: str, status: str,
                        detail: str = "", latency_ms: int = 0) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO deliveries(delivery_id,ts,session_key,status,detail,latency_ms) VALUES(?,?,?,?,?,?)",
            (delivery_id, _now(), session_key, status, detail[:2000], int(latency_ms or 0)),
        )
        self._conn.commit()

    def list_pending(self) -> list[dict]:
        """Deliveries accepted but never finished (crash / kill / deploy window)."""
        marks = ",".join("?" for _ in PENDING_STATUSES)
        rows = self._conn.execute(
            f"SELECT delivery_id, ts, session_key, status FROM deliveries "
            f"WHERE status IN ({marks}) ORDER BY ts ASC",
            PENDING_STATUSES,
        ).fetchall()
        return [{"delivery_id": r[0], "ts": r[1], "session_key": r[2], "status": r[3]}
                for r in rows]

    def mark_interrupted(self, detail: str = "process restarted before completion") -> list[dict]:
        """Close out in-flight deliveries left behind by a crash; return them."""
        pending = self.list_pending()
        if not pending:
            return []
        cur = self._conn.cursor()
        cur.executemany(
            "UPDATE deliveries SET status='interrupted', detail=? WHERE delivery_id=?",
            [(detail[:2000], p["delivery_id"]) for p in pending],
        )
        self._conn.commit()
        return pending

    # ---------------------------------------------------------------- payloads

    def save_payload(self, delivery_id: str, session_key: str, payload: dict) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO payloads(delivery_id,ts,session_key,body) VALUES(?,?,?,?)",
            (delivery_id, _now(), session_key, json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    def load_payload(self, delivery_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT body FROM payloads WHERE delivery_id=?", (delivery_id,)
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            log.warning("stored payload for %s is not valid JSON", delivery_id)
            return None

    def import_legacy_payloads(self, dirs: list[Path] | None = None,
                               delete_after: bool = False) -> int:
        """Pull pre-EDG-86 payload JSON files into the database (idempotent)."""
        dirs = dirs if dirs is not None else state_paths.legacy_payload_dirs()
        imported = 0
        for d in dirs:
            if not d.exists() or not d.is_dir():
                continue
            for p in sorted(d.glob("*.json")):
                delivery_id = p.stem
                if self._conn.execute(
                    "SELECT 1 FROM payloads WHERE delivery_id=?", (delivery_id,)
                ).fetchone():
                    continue
                try:
                    body = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    log.warning("skipping unreadable legacy payload %s", p)
                    continue
                self.save_payload(delivery_id, "", body)
                imported += 1
                if delete_after:
                    try:
                        p.unlink()
                    except OSError:
                        pass
        return imported

    def prune_payloads(self, days: int = 7) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._conn.cursor()
        cur.execute("DELETE FROM payloads WHERE ts < ?", (cutoff,))
        removed = cur.rowcount or 0
        self._conn.commit()
        return removed

    # ------------------------------------------------------------ ops / health

    def counts(self) -> dict:
        cur = self._conn.cursor()
        return {
            "sessions": cur.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            "deliveries": cur.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0],
            "payloads": cur.execute("SELECT COUNT(*) FROM payloads").fetchone()[0],
            "pending_deliveries": len(self.list_pending()),
        }

    def integrity_check(self) -> str:
        row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return row[0] if row else "unknown"

    def backup(self, dest: Path) -> Path:
        """Online snapshot. Safe while the service is running (WAL aware)."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        target = sqlite3.connect(str(tmp))
        try:
            with target:
                self._conn.backup(target)
        finally:
            target.close()
        tmp.replace(dest)
        return dest

    def checkpoint(self) -> None:
        """Fold the WAL back into the main db file (do this before copying files)."""
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def stats_24h(self) -> dict:
        """Aggregate stats over the last 24h for the dashboard."""
        cur = self._conn.cursor()
        rows = cur.execute(
            """SELECT status, COUNT(*) as n, COALESCE(AVG(NULLIF(latency_ms,0)),0) as avg_ms
               FROM deliveries
               WHERE ts > datetime('now','-1 day')
               GROUP BY status"""
        ).fetchall()
        total = sum(r[1] for r in rows)
        per_status = {r[0]: {"count": r[1], "avg_ms": round(r[2])} for r in rows}
        # "queued"/"running" are transient: a delivery only keeps that status if
        # it is still in flight, so they count as attempts, not successes.
        ok_states = {"written", "hermes_skip"}
        written = sum(r[1] for r in rows if r[0] in ok_states)
        ran_states = {"written", "write_fail", "hermes_fail", "hermes_skip",
                      "exception", "thought_fail", "interrupted"}
        ran = sum(r[1] for r in rows if r[0] in ran_states)
        avg_ms = round(sum(r[1] * r[2] for r in rows) / total) if total else 0
        sess_count = cur.execute(
            "SELECT COUNT(*) FROM sessions WHERE last_seen > datetime('now','-1 day')"
        ).fetchone()[0]
        return {
            "window_hours": 24,
            "total_deliveries": total,
            "active_sessions": sess_count,
            "by_status": per_status,
            "agent_runs": ran,
            "success_rate": round(written / ran, 3) if ran else None,
            "avg_processing_ms": avg_ms,
        }
