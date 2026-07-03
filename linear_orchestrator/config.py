"""Runtime config loaded from env + optional .env files."""
from __future__ import annotations
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


def _parse_positive_int(raw) -> int | None:
    """Return a positive int, or None for missing / invalid / non-positive input."""
    if isinstance(raw, bool):  # bool is a subclass of int; reject True/False
        return None
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _parse_model_context_lengths(raw: str) -> dict:
    """Parse per-model context lengths from env.

    Two accepted formats:
      * pairs:  ``model-a=8000,model-b=32000`` (``;`` also works as separator)
      * JSON:   ``{"model-a": 8000, "model-b": 32000}``

    Entries with an empty name or a non-positive / invalid length are dropped so
    a bad value can never shrink the effective limit — callers fall back safely.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    result: dict = {}
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if isinstance(data, dict):
            for key, value in data.items():
                name = str(key).strip()
                val = _parse_positive_int(value)
                if name and val is not None:
                    result[name] = val
        return result
    for chunk in raw.replace(";", ",").split(","):
        name, sep, value = chunk.partition("=")
        if not sep:
            continue
        name = name.strip()
        val = _parse_positive_int(value)
        if name and val is not None:
            result[name] = val
    return result


def _default_hermes_path() -> str:
    found = shutil.which("hermes")
    if found:
        return found
    if sys.platform == "win32":
        for candidate in (
            Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent" / "venv" / "Scripts" / "hermes.exe",
            Path.home() / ".local" / "bin" / "hermes.exe",
        ):
            if candidate.exists():
                return str(candidate)
    return "/home/edgar/.local/bin/hermes"


def _load_envs() -> None:
    # Order: ~/.hermes/.env first, then ./.env override
    for p in (Path.home() / ".hermes" / ".env", Path.cwd() / ".env"):
        if p.exists():
            load_dotenv(p, override=False)


@dataclass
class Config:
    linear_api_key: str
    linear_webhook_secrets: list  # may contain workspace + oauth-app secrets
    hermes_path: str
    host: str
    port: int
    hermes_timeout_sec: int
    default_model: str
    agent_linear_user_id: str
    # Global fallback context length (tokens). None = unset / not enforced.
    default_context_length: int | None
    # Per-model overrides: {model_name: context_length}. Overrides the global default.
    model_context_lengths: dict

    # Back-compat alias for old `cfg.linear_webhook_secret` access.
    @property
    def linear_webhook_secret(self) -> list:
        return self.linear_webhook_secrets

    def context_length_for(self, model: str) -> int | None:
        """Resolve the effective context length for ``model``.

        Precedence: the model's own override wins; otherwise the global default;
        otherwise ``None`` (no limit configured). Invalid / non-positive values
        were already dropped at parse time, so switching to a model without an
        override cleanly falls back to the global default.
        """
        if model:
            override = self.model_context_lengths.get(model)
            if isinstance(override, int) and not isinstance(override, bool) and override > 0:
                return override
        default = self.default_context_length
        if isinstance(default, int) and not isinstance(default, bool) and default > 0:
            return default
        return None

    @classmethod
    def from_env(cls) -> "Config":
        _load_envs()
        missing = []
        def need(name: str) -> str:
            v = os.environ.get(name, "")
            if not v:
                missing.append(name)
            return v

        # Build webhook secret candidates: primary required, additional optional.
        primary = need("LINEAR_WEBHOOK_SECRET")
        secrets: list = []
        if primary:
            secrets.append(primary)
        for extra_key in ("LINEAR_OAUTH_WEBHOOK_SECRET", "LINEAR_WEBHOOK_SECRET_2", "LINEAR_WEBHOOK_SECRET_3"):
            v = os.environ.get(extra_key, "")
            if v and v not in secrets:
                secrets.append(v)

        cfg = cls(
            linear_api_key=need("LINEAR_API_KEY"),
            linear_webhook_secrets=secrets,
            hermes_path=os.environ.get("HERMES_PATH", _default_hermes_path()),
            host=os.environ.get("ORCHESTRATOR_HOST", "0.0.0.0"),
            port=int(os.environ.get("ORCHESTRATOR_PORT", "8645")),
            hermes_timeout_sec=int(os.environ.get("HERMES_TIMEOUT_SEC", "180")),
            default_model=os.environ.get("DEFAULT_MODEL", ""),
            agent_linear_user_id=os.environ.get("AGENT_LINEAR_USER_ID", ""),
            default_context_length=_parse_positive_int(os.environ.get("DEFAULT_CONTEXT_LENGTH", "")),
            model_context_lengths=_parse_model_context_lengths(os.environ.get("MODEL_CONTEXT_LENGTHS", "")),
        )
        if missing:
            raise SystemExit(f"[orchestrator] missing required env: {', '.join(missing)}")
        return cfg
