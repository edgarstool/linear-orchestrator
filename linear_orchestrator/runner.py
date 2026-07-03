"""Invoke hermes CLI to process a parsed Linear event with session continuity."""
from __future__ import annotations
import asyncio
import json
import logging
from .parser import Event

log = logging.getLogger("orch.runner")

# hermes top-level flag used to cap the model context window (tokens).
HERMES_CONTEXT_LENGTH_FLAG = "--context-length"


def _build_prompt(ev: Event) -> str:
    parts = [
        "你收到一個來自 Linear 的事件，請根據上下文做最小、最有用的回應。",
        "",
        f"事件類型：{ev.type}（{ev.action}）",
    ]
    if ev.issue_identifier:
        parts.append(f"Issue：{ev.issue_identifier} - {ev.issue_title}")
    if ev.issue_url:
        parts.append(f"URL：{ev.issue_url}")
    if ev.actor_name:
        parts.append(f"觸發者：{ev.actor_name}")
    if ev.body_text:
        parts.append("")
        parts.append("內容/留言：")
        parts.append(ev.body_text[:4000])
    parts.append("")
    parts.append("規則：")
    parts.append("- 你已被 linear skill 載入，可用 linear MCP 工具讀 issue 上下文")
    parts.append("- 結尾請只回一段「要寫回 Linear 的訊息」（≤500 字、繁體中文、不需要 markdown 標題）")
    parts.append("- 如果不該回應就回「__SKIP__」")
    parts.append("")
    parts.append("Linear 原始 payload（JSON）：")
    parts.append(json.dumps(ev.raw, ensure_ascii=False)[:6000])
    return "\n".join(parts)


def _build_hermes_args(hermes_path: str, prompt: str, session_key: str,
                       default_model: str = "", context_length: int | None = None) -> list:
    """Assemble the hermes argv. Context length is only added when configured,
    so existing setups (no context length) invoke hermes exactly as before."""
    # hermes top-level options come BEFORE any subcommand; -z = non-interactive prompt mode
    args = [hermes_path, "-z", prompt, "--cli", "--continue", session_key, "--skills", "linear", "--ignore-user-config"]
    if default_model:
        args.extend(["-m", default_model])
    if context_length and context_length > 0:
        args.extend([HERMES_CONTEXT_LENGTH_FLAG, str(context_length)])
    return args


async def run_hermes(ev: Event, hermes_path: str, timeout_sec: int,
                     session_key: str, default_model: str = "",
                     context_length: int | None = None) -> tuple[bool, str]:
    """Returns (ok, response_text). response_text is the agent's final reply."""
    prompt = _build_prompt(ev)
    args = _build_hermes_args(hermes_path, prompt, session_key, default_model, context_length)
    log.info("hermes invoke session=%s model=%s ctx_len=%s args_len=%d prompt_len=%d",
             session_key, default_model or "(default)", context_length or "(unset)", len(args), len(prompt))
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # detach from controlling tty
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            proc.kill()
            return False, f"hermes timeout >{timeout_sec}s"

        out_text = (out or b"").decode("utf-8", errors="replace").strip()
        err_text = (err or b"").decode("utf-8", errors="replace").strip()
        reply = _extract_final_reply(out_text)
        # Hermes ≥ 0.16 sometimes SIGABRT(-6 / 134) during shutdown after producing
        # a valid reply on stdout. Treat any captured reply as success.
        if reply and reply != "__SKIP__":
            if proc.returncode not in (0, -6, 134):
                log.warning("hermes rc=%s but stdout has reply, accepting; stderr=%s",
                            proc.returncode, err_text[:200])
            return True, reply
        if reply == "__SKIP__":
            return True, ""
        if proc.returncode != 0:
            log.warning("hermes rc=%s no reply; stderr=%s", proc.returncode, err_text[:500])
            return False, f"hermes exit={proc.returncode}: {err_text[:300] or out_text[:300]}"
        return True, ""
    except FileNotFoundError:
        return False, f"hermes not found at {hermes_path}"


def _extract_final_reply(stdout: str) -> str:
    """Strip ANSI + take the last block of text the agent produced."""
    import re
    no_ansi = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", stdout)
    no_ansi = no_ansi.strip()
    if not no_ansi:
        return ""
    # heuristic: last 60 lines, drop tool-call traces
    lines = [ln for ln in no_ansi.splitlines() if ln.strip()]
    tail = "\n".join(lines[-60:])
    return tail.strip()
