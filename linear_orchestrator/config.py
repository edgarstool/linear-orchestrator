"""Runtime config loaded from env + optional .env files."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


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

    # Back-compat alias for old `cfg.linear_webhook_secret` access.
    @property
    def linear_webhook_secret(self) -> list:
        return self.linear_webhook_secrets

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
            hermes_path=os.environ.get("HERMES_PATH", "/home/edgar/.local/bin/hermes"),
            host=os.environ.get("ORCHESTRATOR_HOST", "0.0.0.0"),
            port=int(os.environ.get("ORCHESTRATOR_PORT", "8645")),
            hermes_timeout_sec=int(os.environ.get("HERMES_TIMEOUT_SEC", "180")),
            default_model=os.environ.get("DEFAULT_MODEL", ""),
            agent_linear_user_id=os.environ.get("AGENT_LINEAR_USER_ID", ""),
        )
        if missing:
            raise SystemExit(f"[orchestrator] missing required env: {', '.join(missing)}")
        return cfg
