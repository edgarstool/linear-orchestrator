#!/usr/bin/env python3
"""daily-standup: 彙整 Linear 任務進度 + Git commit log + mem0 歷史記憶。

輸出結構化 standup 報告（昨日完成 / 今日計畫 / Blockers）。

設計原則
--------
- 零額外依賴：只用 Python 標準庫（urllib / subprocess / argparse）。
- 優雅降級：任一資料來源缺 token 或失敗，該區塊標註略過，不讓整份報告崩潰。
- 純函式可測：資料抓取與報告組裝拆開，方便 unit test。

環境變數
--------
- LINEAR_API_KEY         Linear personal API key（lin_api_...），抓 assignedIssues 用。
- MEM0_API_KEY           mem0 platform API key（可選）。
- MEM0_USER_ID           mem0 查詢的 user/peer id（可選，預設 "edgar"）。
- MEM0_BASE_URL          mem0 API base（可選，預設 https://api.mem0.ai）。

用法
----
    python standup.py                        # 預設 24h 窗口，markdown 輸出
    python standup.py --window-hours 72      # 拉長窗口
    python standup.py --format json          # 機器可讀
    python standup.py --no-mem0 --author 德德 # 關掉 mem0、只算某作者的 commit
    python standup.py --post-to-issue <id>   # 把報告貼回某 Linear issue（需 LINEAR_API_KEY）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

LINEAR_GQL = "https://api.linear.app/graphql"

# Linear workflow state types → 我們的分類語意。
DONE_STATE_TYPES = {"completed", "canceled"}
ACTIVE_STATE_TYPES = {"started", "unstarted"}


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #
@dataclass
class Commit:
    sha: str
    author: str
    date: str
    subject: str

    @property
    def short(self) -> str:
        return self.sha[:7]


@dataclass
class LinearIssue:
    identifier: str
    title: str
    url: str
    state_name: str
    state_type: str
    updated_at: str
    completed_at: str = ""
    labels: list = field(default_factory=list)
    blocked_by: list = field(default_factory=list)  # identifiers of blocking issues


@dataclass
class Memory:
    text: str
    score: float = 0.0


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(timezone.utc)


def since_cutoff(window_hours: int) -> datetime:
    return _now() - timedelta(hours=window_hours)


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        # Linear returns e.g. 2026-07-01T09:30:00.000Z
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _within(value: str, cutoff: datetime) -> bool:
    dt = _parse_iso(value)
    return dt is not None and dt >= cutoff


# --------------------------------------------------------------------------- #
# HTTP helper (stdlib only)
# --------------------------------------------------------------------------- #
def _http_json(url: str, payload: dict, headers: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted URLs)
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


# --------------------------------------------------------------------------- #
# Git collection
# --------------------------------------------------------------------------- #
_GIT_SEP = "\x1f"
_GIT_FMT = _GIT_SEP.join(["%H", "%an", "%ad", "%s"])


def parse_git_log(raw: str) -> list[Commit]:
    """Parse `git log` output produced with _GIT_FMT (unit-separator delimited)."""
    commits: list[Commit] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(_GIT_SEP)
        if len(parts) != 4:
            continue
        sha, author, date, subject = parts
        commits.append(Commit(sha=sha, author=author, date=date, subject=subject))
    return commits


def collect_git_commits(repo: str, cutoff: datetime, author: str | None) -> tuple[list[Commit], str]:
    """Return (commits, note). note is non-empty when the source was skipped/failed."""
    cmd = [
        "git", "-C", repo, "log",
        f"--since={cutoff.isoformat()}",
        f"--pretty=format:{_GIT_FMT}",
        "--date=iso",
        "--no-merges",
    ]
    if author:
        cmd.append(f"--author={author}")
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return [], f"git 無法執行：{e}"
    if out.returncode != 0:
        err = (out.stderr or "").strip()[:200]
        return [], f"git log 失敗（可能非 git repo）：{err}"
    return parse_git_log(out.stdout), ""


# --------------------------------------------------------------------------- #
# Linear collection
# --------------------------------------------------------------------------- #
STANDUP_QUERY = """
query Standup {
  viewer {
    name
    assignedIssues(first: 100, orderBy: updatedAt) {
      nodes {
        identifier
        title
        url
        updatedAt
        completedAt
        state { name type }
        labels { nodes { name } }
        inverseRelations {
          nodes { type relatedIssue { identifier state { type } } }
        }
      }
    }
  }
}
"""


def _issue_from_node(node: dict) -> LinearIssue:
    state = node.get("state") or {}
    labels = [n.get("name", "") for n in (node.get("labels", {}) or {}).get("nodes", [])]
    blocked_by = []
    for rel in ((node.get("inverseRelations", {}) or {}).get("nodes", []) or []):
        # inverseRelations of type "blocks" means: relatedIssue blocks THIS issue.
        if rel.get("type") == "blocks":
            related = rel.get("relatedIssue") or {}
            rel_state = (related.get("state") or {}).get("type", "")
            if rel_state not in DONE_STATE_TYPES:  # only unresolved blockers count
                blocked_by.append(related.get("identifier", "?"))
    return LinearIssue(
        identifier=node.get("identifier", "?"),
        title=node.get("title", ""),
        url=node.get("url", ""),
        state_name=state.get("name", ""),
        state_type=state.get("type", ""),
        updated_at=node.get("updatedAt", ""),
        completed_at=node.get("completedAt", "") or "",
        labels=labels,
        blocked_by=blocked_by,
    )


def collect_linear_issues(api_key: str) -> tuple[list[LinearIssue], str, str]:
    """Return (issues, viewer_name, note)."""
    if not api_key:
        return [], "", "未設定 LINEAR_API_KEY，略過 Linear。"
    try:
        data = _http_json(
            LINEAR_GQL,
            {"query": STANDUP_QUERY},
            {"Authorization": api_key, "Content-Type": "application/json"},
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return [], "", f"Linear 查詢失敗：{e}"
    if data.get("errors"):
        return [], "", f"Linear GraphQL 錯誤：{str(data['errors'])[:200]}"
    viewer = ((data.get("data") or {}).get("viewer") or {})
    nodes = ((viewer.get("assignedIssues") or {}).get("nodes") or [])
    return [_issue_from_node(n) for n in nodes], viewer.get("name", ""), ""


def classify_issues(
    issues: list[LinearIssue], cutoff: datetime
) -> tuple[list[LinearIssue], list[LinearIssue], list[LinearIssue]]:
    """Split issues into (done_recently, planned_today, blockers)."""
    done, planned, blockers = [], [], []
    for iss in issues:
        is_blocked = bool(iss.blocked_by) or any("block" in l.lower() for l in iss.labels)
        if iss.state_type in DONE_STATE_TYPES:
            if _within(iss.completed_at or iss.updated_at, cutoff):
                done.append(iss)
        elif iss.state_type in ACTIVE_STATE_TYPES:
            if is_blocked:
                blockers.append(iss)
            else:
                planned.append(iss)
    # started 排在 unstarted 前面，讓「進行中」優先呈現。
    planned.sort(key=lambda i: 0 if i.state_type == "started" else 1)
    return done, planned, blockers


# --------------------------------------------------------------------------- #
# mem0 collection
# --------------------------------------------------------------------------- #
def collect_memories(
    api_key: str, user_id: str, base_url: str, query: str, limit: int = 5
) -> tuple[list[Memory], str]:
    if not api_key:
        return [], "未設定 MEM0_API_KEY，略過 mem0。"
    url = f"{base_url.rstrip('/')}/v1/memories/search/"
    try:
        data = _http_json(
            url,
            {"query": query, "user_id": user_id, "limit": limit},
            {"Authorization": f"Token {api_key}", "Content-Type": "application/json"},
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return [], f"mem0 查詢失敗：{e}"
    # mem0 platform 可能回傳 list 或 {"results": [...]}
    rows = data.get("results", data) if isinstance(data, dict) else data
    memories: list[Memory] = []
    for row in (rows or [])[:limit]:
        if not isinstance(row, dict):
            continue
        text = row.get("memory") or row.get("text") or row.get("content") or ""
        if text:
            memories.append(Memory(text=text, score=float(row.get("score", 0) or 0)))
    return memories, ""


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #
@dataclass
class StandupData:
    since: datetime
    now: datetime
    viewer: str
    commits: list[Commit]
    done: list[LinearIssue]
    planned: list[LinearIssue]
    blockers: list[LinearIssue]
    memories: list[Memory]
    notes: list[str] = field(default_factory=list)


def _issue_line(iss: LinearIssue) -> str:
    suffix = f" — 被 {', '.join(iss.blocked_by)} 卡住" if iss.blocked_by else ""
    link = f"（{iss.url}）" if iss.url else ""
    return f"- `{iss.identifier}` {iss.title} [{iss.state_name}]{suffix}{link}"


def render_markdown(d: StandupData) -> str:
    date_str = d.now.astimezone().strftime("%Y-%m-%d")
    win = (
        f"{d.since.astimezone().strftime('%Y-%m-%d %H:%M')}"
        f" → {d.now.astimezone().strftime('%Y-%m-%d %H:%M')}"
    )
    who = d.viewer or "（unknown）"
    lines: list[str] = [
        f"# 📋 Daily Standup — {date_str}",
        f"_窗口：{win} · 產生者：{who}_",
        "",
        "## ✅ 昨日完成",
    ]
    if d.done:
        lines += [_issue_line(i) for i in d.done]
    else:
        lines.append("- （此窗口內無標記完成的 Linear 任務）")

    lines += ["", "## 🎯 今日計畫"]
    if d.planned:
        lines += [_issue_line(i) for i in d.planned]
    else:
        lines.append("- （無進行中/待辦的指派任務）")

    lines += ["", "## 🚧 Blockers"]
    if d.blockers:
        lines += [_issue_line(i) for i in d.blockers]
    else:
        lines.append("- 無 🎉")

    lines += ["", f"## 🧠 記憶脈絡（mem0，{len(d.memories)}）"]
    if d.memories:
        lines += [f"- {m.text}" for m in d.memories]
    else:
        lines.append("- （無相關歷史記憶）")

    lines += ["", f"## 🔨 Git commits（{len(d.commits)}）"]
    if d.commits:
        lines += [f"- `{c.short}` {c.subject} — {c.author}" for c in d.commits]
    else:
        lines.append("- （此窗口內無 commit）")

    if d.notes:
        lines += ["", "---", "### ⚠️ 資料來源備註"]
        lines += [f"- {n}" for n in d.notes]

    return "\n".join(lines) + "\n"


def render_json(d: StandupData) -> str:
    def issues(seq: list[LinearIssue]) -> list[dict]:
        return [
            {
                "identifier": i.identifier,
                "title": i.title,
                "url": i.url,
                "state": i.state_name,
                "state_type": i.state_type,
                "blocked_by": i.blocked_by,
            }
            for i in seq
        ]

    payload = {
        "date": d.now.astimezone().strftime("%Y-%m-%d"),
        "window": {"since": d.since.isoformat(), "now": d.now.isoformat()},
        "viewer": d.viewer,
        "yesterday_done": issues(d.done),
        "today_plan": issues(d.planned),
        "blockers": issues(d.blockers),
        "memories": [{"text": m.text, "score": m.score} for m in d.memories],
        "commits": [
            {"sha": c.sha, "author": c.author, "date": c.date, "subject": c.subject}
            for c in d.commits
        ],
        "notes": d.notes,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Optional: post back to Linear as a comment
# --------------------------------------------------------------------------- #
COMMENT_MUTATION = """
mutation CommentCreate($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment { url }
  }
}
"""


def post_comment(api_key: str, issue_id: str, body: str) -> tuple[bool, str]:
    if not api_key:
        return False, "未設定 LINEAR_API_KEY，無法貼回。"
    try:
        data = _http_json(
            LINEAR_GQL,
            {"query": COMMENT_MUTATION, "variables": {"issueId": issue_id, "body": body}},
            {"Authorization": api_key, "Content-Type": "application/json"},
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return False, f"貼回失敗：{e}"
    created = (((data.get("data") or {}).get("commentCreate") or {}))
    ok = bool(created.get("success"))
    url = (created.get("comment") or {}).get("url", "")
    if data.get("errors"):
        return False, f"GraphQL 錯誤：{str(data['errors'])[:200]}"
    return ok, url


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def build_standup(args: argparse.Namespace) -> StandupData:
    now = _now()
    cutoff = since_cutoff(args.window_hours)
    notes: list[str] = []

    commits: list[Commit] = []
    if args.git:
        commits, note = collect_git_commits(args.repo, cutoff, args.author)
        if note:
            notes.append(note)

    done: list[LinearIssue] = []
    planned: list[LinearIssue] = []
    blockers: list[LinearIssue] = []
    viewer = ""
    if args.linear:
        issues, viewer, note = collect_linear_issues(os.environ.get("LINEAR_API_KEY", ""))
        if note:
            notes.append(note)
        done, planned, blockers = classify_issues(issues, cutoff)

    memories: list[Memory] = []
    if args.mem0:
        memories, note = collect_memories(
            os.environ.get("MEM0_API_KEY", ""),
            os.environ.get("MEM0_USER_ID", "edgar"),
            os.environ.get("MEM0_BASE_URL", "https://api.mem0.ai"),
            query=args.mem0_query,
        )
        if note:
            notes.append(note)

    return StandupData(
        since=cutoff, now=now, viewer=viewer,
        commits=commits, done=done, planned=planned,
        blockers=blockers, memories=memories, notes=notes,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="每日 standup 報告產生器")
    p.add_argument("--window-hours", type=int, default=24, help="回溯窗口小時數（預設 24）")
    p.add_argument("--repo", default=".", help="git repo 路徑（預設當前目錄）")
    p.add_argument("--author", default=None, help="只計算此作者的 git commit")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.add_argument("--output", default=None, help="輸出檔案路徑（預設 stdout）")
    p.add_argument(
        "--mem0-query",
        default="最近的優先事項、進行中任務與 blockers",
        help="mem0 語意搜尋 query",
    )
    p.add_argument("--no-git", dest="git", action="store_false", help="關閉 git 來源")
    p.add_argument("--no-linear", dest="linear", action="store_false", help="關閉 Linear 來源")
    p.add_argument("--no-mem0", dest="mem0", action="store_false", help="關閉 mem0 來源")
    p.add_argument("--post-to-issue", default=None, help="把報告貼回指定 Linear issue id")
    p.set_defaults(git=True, linear=True, mem0=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    data = build_standup(args)

    rendered = render_json(data) if args.format == "json" else render_markdown(data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"已寫入 {args.output}", file=sys.stderr)
    else:
        print(rendered)

    if args.post_to_issue:
        # 貼回時一律用 markdown，comment 才好讀。
        body = rendered if args.format == "markdown" else render_markdown(data)
        ok, detail = post_comment(
            os.environ.get("LINEAR_API_KEY", ""), args.post_to_issue, body
        )
        print(f"[post-to-issue] ok={ok} {detail}", file=sys.stderr)
        if not ok:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
