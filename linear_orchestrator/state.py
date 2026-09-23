"""Durable runtime-state locations for linear-orchestrator.

Every *mutable* file the runtime owns lives under a single state root so it can
be pointed at persistent storage, snapshotted, and restored as one unit.

Resolution order for the state root:

1. ``LINEAR_ORCHESTRATOR_STATE_DIR`` (explicit, recommended for deployments)
2. ``$XDG_DATA_HOME/linear-orchestrator``
3. ``~/.local/share/linear-orchestrator`` (legacy default, kept for upgrades)

Backups default to ``<state root>/backups`` and can be redirected with
``LINEAR_ORCHESTRATOR_BACKUP_DIR`` so snapshots can live on a different volume
than the live database.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_STATE_DIR = "LINEAR_ORCHESTRATOR_STATE_DIR"
ENV_BACKUP_DIR = "LINEAR_ORCHESTRATOR_BACKUP_DIR"

DB_FILENAME = "sessions.db"
PAYLOAD_DIRNAME = "payloads"
BACKUP_DIRNAME = "backups"

#: Where releases before EDG-86 unconditionally wrote runtime state.
LEGACY_DEFAULT_DIR = Path.home() / ".local" / "share" / "linear-orchestrator"


def _expand(raw: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(raw)))


def state_dir(create: bool = True) -> Path:
    """Return the runtime state root, creating it on demand."""
    raw = os.environ.get(ENV_STATE_DIR, "").strip()
    if raw:
        path = _expand(raw)
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "").strip()
        path = (_expand(xdg) / "linear-orchestrator") if xdg else LEGACY_DEFAULT_DIR
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def db_path(create_parent: bool = True) -> Path:
    """Path of the SQLite database holding all critical runtime state."""
    return state_dir(create=create_parent) / DB_FILENAME


def backup_dir(create: bool = True) -> Path:
    """Directory that receives SQLite snapshots."""
    raw = os.environ.get(ENV_BACKUP_DIR, "").strip()
    path = _expand(raw) if raw else state_dir(create=create) / BACKUP_DIRNAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_payload_dirs() -> list[Path]:
    """Directories that may still hold pre-EDG-86 webhook payload JSON dumps.

    These are read-only inputs for the one-shot import performed at startup;
    the SQLite database is the source of truth afterwards.
    """
    candidates = [state_dir(create=False) / PAYLOAD_DIRNAME,
                  LEGACY_DEFAULT_DIR / PAYLOAD_DIRNAME]
    seen: list[Path] = []
    for c in candidates:
        if c not in seen:
            seen.append(c)
    return seen


def describe() -> dict:
    """Human/ops-facing summary of where mutable state currently lives."""
    root = state_dir(create=False)
    db = root / DB_FILENAME
    return {
        "state_dir": str(root),
        "state_dir_exists": root.exists(),
        "state_dir_source": ("env" if os.environ.get(ENV_STATE_DIR, "").strip()
                             else ("xdg" if os.environ.get("XDG_DATA_HOME", "").strip()
                                   else "default")),
        "db_path": str(db),
        "db_exists": db.exists(),
        "db_bytes": db.stat().st_size if db.exists() else 0,
        "backup_dir": str(_expand(os.environ.get(ENV_BACKUP_DIR, "").strip())
                          if os.environ.get(ENV_BACKUP_DIR, "").strip()
                          else root / BACKUP_DIRNAME),
        "legacy_payload_dirs": [str(p) for p in legacy_payload_dirs() if p.exists()],
    }
