"""Operator CLI for linear-orchestrator runtime state.

    linear-orchestrator-state inspect
    linear-orchestrator-state backup [--keep N]
    linear-orchestrator-state restore <snapshot> [--force]
    linear-orchestrator-state verify [--from <db>]
    linear-orchestrator-state import-legacy [--delete-source]
    linear-orchestrator-state prune [--days 7]
    linear-orchestrator-state pending [--reset]

Everything operates on the state root resolved by ``linear_orchestrator.state``
(``LINEAR_ORCHESTRATOR_STATE_DIR`` wins). ``restore`` refuses to overwrite a
live database unless ``--force`` is given, so the safe order is:
stop the service → restore → start the service.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from . import state as state_paths
from .session import SessionStore

BACKUP_PREFIX = "sessions-"


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _snapshot_name() -> str:
    return f"{BACKUP_PREFIX}{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.db"


def _list_backups() -> list[Path]:
    d = state_paths.backup_dir(create=False)
    if not d.exists():
        return []
    return sorted(d.glob(f"{BACKUP_PREFIX}*.db"))


def cmd_inspect(args: argparse.Namespace) -> int:
    info = state_paths.describe()
    db = Path(info["db_path"])
    if db.exists():
        store = SessionStore(db)
        try:
            info["counts"] = store.counts()
            info["pending_deliveries"] = store.list_pending()[:20]
            info["integrity"] = store.integrity_check()
        finally:
            store.close()
    info["backups"] = [{"path": str(p), "bytes": p.stat().st_size} for p in _list_backups()]
    _out(info)
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    db = state_paths.db_path()
    if not db.exists():
        print(f"no state database at {db}", file=sys.stderr)
        return 1
    store = SessionStore(db)
    try:
        dest = state_paths.backup_dir() / _snapshot_name()
        store.backup(dest)
    finally:
        store.close()
    keep = args.keep
    removed = []
    if keep > 0:
        for p in _list_backups()[:-keep]:
            try:
                p.unlink()
                removed.append(str(p))
            except OSError:
                pass
    _out({"backup": str(dest), "bytes": dest.stat().st_size,
          "kept": keep, "removed": removed})
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    src = Path(args.snapshot).expanduser()
    if not src.exists():
        print(f"snapshot not found: {src}", file=sys.stderr)
        return 1
    # Fail fast on a corrupt snapshot rather than half-restoring.
    probe = SessionStore(src)
    try:
        integrity = probe.integrity_check()
        counts = probe.counts()
    finally:
        probe.close()
    if integrity != "ok":
        print(f"snapshot failed integrity check: {integrity}", file=sys.stderr)
        return 2

    db = state_paths.db_path()
    if db.exists() and not args.force:
        print(f"{db} already exists; stop the service and re-run with --force",
              file=sys.stderr)
        return 3

    rescued = None
    if db.exists():
        rescued = db.with_name(f"{db.name}.pre-restore-{int(time.time())}")
        shutil.copy2(db, rescued)
    for suffix in ("-wal", "-shm"):
        stale = db.with_name(db.name + suffix)
        if stale.exists():
            stale.unlink()
    shutil.copy2(src, db)
    _out({"restored_from": str(src), "db": str(db),
          "previous_db_saved_as": str(rescued) if rescued else None,
          "counts": counts, "integrity": integrity,
          "next": "start the service; startup recovery replays interrupted deliveries"})
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    db = Path(args.source).expanduser() if args.source else state_paths.db_path()
    if not db.exists():
        print(f"no database at {db}", file=sys.stderr)
        return 1
    store = SessionStore(db)
    try:
        result = {"db": str(db), "integrity": store.integrity_check(),
                  "counts": store.counts()}
    finally:
        store.close()
    _out(result)
    return 0 if result["integrity"] == "ok" else 2


def cmd_import_legacy(args: argparse.Namespace) -> int:
    store = SessionStore(state_paths.db_path())
    try:
        imported = store.import_legacy_payloads(delete_after=args.delete_source)
        counts = store.counts()
    finally:
        store.close()
    _out({"imported": imported, "counts": counts,
          "sources": [str(p) for p in state_paths.legacy_payload_dirs() if p.exists()]})
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    store = SessionStore(state_paths.db_path())
    try:
        removed = store.prune_payloads(args.days)
        counts = store.counts()
    finally:
        store.close()
    _out({"pruned_payloads": removed, "older_than_days": args.days, "counts": counts})
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    store = SessionStore(state_paths.db_path())
    try:
        if args.reset:
            pending = store.mark_interrupted("marked interrupted by operator CLI")
            result = {"marked_interrupted": [p["delivery_id"] for p in pending]}
        else:
            result = {"pending": store.list_pending()}
    finally:
        store.close()
    _out(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="linear-orchestrator-state",
                                description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("inspect", help="show state locations, counts, integrity").set_defaults(
        func=cmd_inspect)

    b = sub.add_parser("backup", help="write an online snapshot and rotate old ones")
    b.add_argument("--keep", type=int, default=7, help="snapshots to keep (0 = keep all)")
    b.set_defaults(func=cmd_backup)

    r = sub.add_parser("restore", help="restore the state db from a snapshot")
    r.add_argument("snapshot")
    r.add_argument("--force", action="store_true",
                   help="overwrite an existing db (service must be stopped)")
    r.set_defaults(func=cmd_restore)

    v = sub.add_parser("verify", help="integrity-check a db or snapshot")
    v.add_argument("--from", dest="source", default="")
    v.set_defaults(func=cmd_verify)

    i = sub.add_parser("import-legacy", help="import pre-EDG-86 payload JSON files")
    i.add_argument("--delete-source", action="store_true")
    i.set_defaults(func=cmd_import_legacy)

    pr = sub.add_parser("prune", help="drop stored payloads older than N days")
    pr.add_argument("--days", type=int, default=7)
    pr.set_defaults(func=cmd_prune)

    pe = sub.add_parser("pending", help="list deliveries stuck in-flight")
    pe.add_argument("--reset", action="store_true",
                    help="mark them interrupted so the next start replays them")
    pe.set_defaults(func=cmd_pending)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
