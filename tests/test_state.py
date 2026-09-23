"""Tests for durable runtime state: paths, payloads, recovery, backup/restore."""
from __future__ import annotations

import json

import pytest

from linear_orchestrator import state as state_paths
from linear_orchestrator import state_cli
from linear_orchestrator.session import SessionStore


@pytest.fixture
def state_root(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setenv(state_paths.ENV_STATE_DIR, str(root))
    monkeypatch.delenv(state_paths.ENV_BACKUP_DIR, raising=False)
    return root


def test_state_dir_follows_env(state_root):
    assert state_paths.state_dir() == state_root
    assert state_paths.db_path() == state_root / "sessions.db"
    assert state_paths.backup_dir() == state_root / "backups"


def test_state_dir_falls_back_to_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv(state_paths.ENV_STATE_DIR, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert state_paths.state_dir() == tmp_path / "xdg" / "linear-orchestrator"


def test_store_uses_wal_and_survives_reopen(state_root):
    store = SessionStore()
    assert store.path == state_root / "sessions.db"
    mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    store.upsert("linear-issue-EDG-86", issue_iden="EDG-86")
    store.save_payload("d-1", "linear-issue-EDG-86", {"type": "Comment"})
    store.close()

    reopened = SessionStore()
    assert reopened.load_payload("d-1") == {"type": "Comment"}
    assert reopened.counts()["sessions"] == 1
    assert reopened.integrity_check() == "ok"
    reopened.close()


def test_pending_deliveries_are_marked_interrupted(state_root):
    store = SessionStore()
    store.record_delivery("d-live", "s1", "queued", "accepted")
    store.record_delivery("d-done", "s1", "written", "ok")
    assert [p["delivery_id"] for p in store.list_pending()] == ["d-live"]

    interrupted = store.mark_interrupted()
    assert [i["delivery_id"] for i in interrupted] == ["d-live"]
    assert store.list_pending() == []
    status = store._conn.execute(
        "SELECT status FROM deliveries WHERE delivery_id='d-live'"
    ).fetchone()[0]
    assert status == "interrupted"
    store.close()


def test_import_legacy_payloads_is_idempotent(state_root):
    legacy = state_root / "payloads"
    legacy.mkdir(parents=True)
    (legacy / "d-old.json").write_text(json.dumps({"type": "Issue"}), encoding="utf-8")
    (legacy / "broken.json").write_text("{not json", encoding="utf-8")

    store = SessionStore()
    assert store.import_legacy_payloads() == 1
    assert store.import_legacy_payloads() == 0
    assert store.load_payload("d-old") == {"type": "Issue"}
    assert store.load_payload("broken") is None
    store.close()


def test_prune_payloads_respects_retention(state_root):
    store = SessionStore()
    store.save_payload("fresh", "s1", {"a": 1})
    store._conn.execute("UPDATE payloads SET ts='2000-01-01T00:00:00+00:00' "
                        "WHERE delivery_id='fresh'")
    store._conn.commit()
    store.save_payload("recent", "s1", {"a": 2})

    assert store.prune_payloads(days=7) == 1
    assert store.load_payload("fresh") is None
    assert store.load_payload("recent") == {"a": 2}
    store.close()


def test_backup_and_restore_roundtrip(state_root, capsys):
    store = SessionStore()
    store.upsert("linear-issue-EDG-86", issue_iden="EDG-86")
    store.save_payload("d-1", "linear-issue-EDG-86", {"type": "Comment"})
    store.close()

    assert state_cli.main(["backup", "--keep", "2"]) == 0
    snapshot = json.loads(capsys.readouterr().out)["backup"]

    # Simulate losing the live database (crash / bad deploy / wiped volume).
    state_paths.db_path().unlink()
    assert state_cli.main(["restore", snapshot]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["integrity"] == "ok"
    assert restored["counts"]["payloads"] == 1

    store = SessionStore()
    assert store.load_payload("d-1") == {"type": "Comment"}
    store.close()


def test_restore_refuses_to_clobber_live_db_without_force(state_root, capsys):
    store = SessionStore()
    store.save_payload("d-1", "s1", {"a": 1})
    store.close()
    assert state_cli.main(["backup"]) == 0
    snapshot = json.loads(capsys.readouterr().out)["backup"]

    assert state_cli.main(["restore", snapshot]) == 3
    assert state_cli.main(["restore", snapshot, "--force"]) == 0
    # the pre-restore copy is kept so nothing is silently destroyed
    assert list(state_root.glob("sessions.db.pre-restore-*"))


def test_verify_reports_counts(state_root, capsys):
    store = SessionStore()
    store.record_delivery("d-1", "s1", "written", "ok")
    store.close()
    assert state_cli.main(["verify"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["integrity"] == "ok"
    assert out["counts"]["deliveries"] == 1


def test_inspect_reports_state_location(state_root, capsys):
    SessionStore().close()
    assert state_cli.main(["inspect"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state_dir"] == str(state_root)
    assert out["state_dir_source"] == "env"
    assert out["db_exists"] is True
