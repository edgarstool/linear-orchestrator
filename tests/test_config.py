"""Tests for per-model context length config + resolution (EDG-148)."""
from __future__ import annotations

import pytest

from linear_orchestrator.config import (
    Config,
    _parse_model_context_lengths,
    _parse_positive_int,
)
from linear_orchestrator.runner import HERMES_CONTEXT_LENGTH_FLAG, _build_hermes_args


def _cfg(default_model="", default_context_length=None, model_context_lengths=None) -> Config:
    """Build a Config directly, bypassing env, for resolver tests."""
    return Config(
        linear_api_key="k",
        linear_webhook_secrets=["s"],
        hermes_path="hermes",
        host="127.0.0.1",
        port=8645,
        hermes_timeout_sec=180,
        default_model=default_model,
        agent_linear_user_id="",
        default_context_length=default_context_length,
        model_context_lengths=model_context_lengths or {},
    )


# --- _parse_positive_int -------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("8000", 8000),
    ("  32000  ", 32000),
    (16000, 16000),
    ("", None),
    (None, None),
    ("0", None),
    ("-5", None),
    ("abc", None),
    ("12.5", None),
    (True, None),   # bool must not slip through as 1
    (False, None),
])
def test_parse_positive_int(raw, expected):
    assert _parse_positive_int(raw) == expected


# --- _parse_model_context_lengths ---------------------------------------

def test_parse_pairs_form():
    assert _parse_model_context_lengths("model-a=8000,model-b=32000") == {
        "model-a": 8000,
        "model-b": 32000,
    }


def test_parse_pairs_semicolon_and_spaces():
    assert _parse_model_context_lengths(" model-a = 8000 ; model-b=32000 ") == {
        "model-a": 8000,
        "model-b": 32000,
    }


def test_parse_json_form():
    assert _parse_model_context_lengths('{"model-a": 8000, "model-b": 32000}') == {
        "model-a": 8000,
        "model-b": 32000,
    }


def test_parse_drops_invalid_entries():
    parsed = _parse_model_context_lengths("good=8000,bad=abc,zero=0,neg=-1,=500,noeq")
    assert parsed == {"good": 8000}


def test_parse_empty_and_garbage():
    assert _parse_model_context_lengths("") == {}
    assert _parse_model_context_lengths("   ") == {}
    assert _parse_model_context_lengths("{not valid json") == {}


# --- Config.context_length_for ------------------------------------------

def test_model_override_wins_over_global():
    cfg = _cfg(default_context_length=8000, model_context_lengths={"big": 128000})
    assert cfg.context_length_for("big") == 128000


def test_fallback_to_global_when_no_override():
    cfg = _cfg(default_context_length=8000, model_context_lengths={"big": 128000})
    assert cfg.context_length_for("small") == 8000


def test_none_when_nothing_configured():
    # Backward compat: existing configs with no context length behave as before.
    cfg = _cfg()
    assert cfg.context_length_for("any") is None
    assert cfg.context_length_for("") is None


def test_empty_model_uses_global():
    cfg = _cfg(default_context_length=8000)
    assert cfg.context_length_for("") == 8000


def test_model_switching_updates_active_limit():
    cfg = _cfg(
        default_context_length=8000,
        model_context_lengths={"small": 4000, "large": 200000},
    )
    # Switching the active model changes the resolved limit accordingly.
    assert cfg.context_length_for("small") == 4000
    assert cfg.context_length_for("large") == 200000
    assert cfg.context_length_for("unknown") == 8000  # falls back to global


def test_invalid_stored_values_are_ignored():
    # Even if a bad value slips into the map, resolution stays safe.
    cfg = _cfg(default_context_length=8000, model_context_lengths={"m": 0})
    assert cfg.context_length_for("m") == 8000
    cfg2 = _cfg(default_context_length=None, model_context_lengths={"m": -1})
    assert cfg2.context_length_for("m") is None


# --- Config.from_env ----------------------------------------------------

def _base_env(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_x")
    monkeypatch.setenv("LINEAR_WEBHOOK_SECRET", "wh_x")
    # Avoid loading real ~/.hermes/.env / ./.env during the test.
    monkeypatch.setattr("linear_orchestrator.config._load_envs", lambda: None)


def test_from_env_backward_compatible_without_new_vars(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.delenv("DEFAULT_CONTEXT_LENGTH", raising=False)
    monkeypatch.delenv("MODEL_CONTEXT_LENGTHS", raising=False)
    cfg = Config.from_env()
    assert cfg.default_context_length is None
    assert cfg.model_context_lengths == {}
    assert cfg.context_length_for("whatever") is None


def test_from_env_parses_new_vars(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("DEFAULT_CONTEXT_LENGTH", "8000")
    monkeypatch.setenv("MODEL_CONTEXT_LENGTHS", "big=128000,small=4000")
    cfg = Config.from_env()
    assert cfg.default_context_length == 8000
    assert cfg.context_length_for("big") == 128000
    assert cfg.context_length_for("small") == 4000
    assert cfg.context_length_for("other") == 8000


# --- runner._build_hermes_args ------------------------------------------

def test_build_args_omits_flag_when_no_context_length():
    args = _build_hermes_args("hermes", "prompt", "sess", default_model="m")
    assert HERMES_CONTEXT_LENGTH_FLAG not in args


def test_build_args_includes_flag_when_context_length_set():
    args = _build_hermes_args("hermes", "prompt", "sess", default_model="m", context_length=8000)
    assert HERMES_CONTEXT_LENGTH_FLAG in args
    idx = args.index(HERMES_CONTEXT_LENGTH_FLAG)
    assert args[idx + 1] == "8000"


def test_build_args_omits_flag_for_nonpositive_context_length():
    for bad in (0, None, -5):
        args = _build_hermes_args("hermes", "prompt", "sess", default_model="m", context_length=bad)
        assert HERMES_CONTEXT_LENGTH_FLAG not in args
