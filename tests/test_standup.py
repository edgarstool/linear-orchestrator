"""Tests for the daily-standup skill's pure functions.

The skill script lives outside the python package (under skills/), so we load it
by path with importlib rather than a normal import.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "skills" / "daily-standup" / "scripts" / "standup.py"
)
_spec = importlib.util.spec_from_file_location("standup", _SCRIPT)
standup = importlib.util.module_from_spec(_spec)
# Register before exec so dataclass type resolution can find the module.
sys.modules["standup"] = standup
_spec.loader.exec_module(standup)


# --------------------------------------------------------------------------- #
# git parsing
# --------------------------------------------------------------------------- #
def test_parse_git_log_splits_on_unit_separator():
    sep = "\x1f"
    raw = sep.join(["abcdef1234567890", "德德", "2026-07-01 10:00:00 +0800", "feat: 加東西 | 含管線"])
    commits = standup.parse_git_log(raw)
    assert len(commits) == 1
    c = commits[0]
    assert c.short == "abcdef1"
    assert c.author == "德德"
    assert c.subject == "feat: 加東西 | 含管線"  # pipes in subject survive


def test_parse_git_log_ignores_blank_and_malformed_lines():
    sep = "\x1f"
    good = sep.join(["sha1", "a", "d", "s"])
    raw = f"\n{good}\nnot-a-real-line\n"
    commits = standup.parse_git_log(raw)
    assert len(commits) == 1
    assert commits[0].sha == "sha1"


# --------------------------------------------------------------------------- #
# Linear node parsing + classification
# --------------------------------------------------------------------------- #
def _node(identifier, state_type, *, completed_at="", labels=None, blocked_by_open=False):
    inverse = []
    if blocked_by_open:
        inverse = [{"type": "blocks",
                    "relatedIssue": {"identifier": "EDG-99", "state": {"type": "started"}}}]
    return {
        "identifier": identifier,
        "title": f"title-{identifier}",
        "url": f"https://linear.app/x/{identifier}",
        "updatedAt": "2026-07-01T10:00:00.000Z",
        "completedAt": completed_at,
        "state": {"name": state_type.title(), "type": state_type},
        "labels": {"nodes": [{"name": n} for n in (labels or [])]},
        "inverseRelations": {"nodes": inverse},
    }


def test_issue_from_node_extracts_open_blocker():
    iss = standup._issue_from_node(_node("EDG-1", "started", blocked_by_open=True))
    assert iss.blocked_by == ["EDG-99"]


def test_issue_from_node_ignores_resolved_blocker():
    node = {
        "identifier": "EDG-2", "title": "t", "url": "", "updatedAt": "", "completedAt": "",
        "state": {"name": "In Progress", "type": "started"},
        "labels": {"nodes": []},
        "inverseRelations": {"nodes": [
            {"type": "blocks", "relatedIssue": {"identifier": "EDG-3", "state": {"type": "completed"}}}
        ]},
    }
    iss = standup._issue_from_node(node)
    assert iss.blocked_by == []  # blocker already done → not a blocker


def test_classify_issues_buckets_correctly():
    now = standup._now()
    cutoff = now - timedelta(hours=24)
    recent = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    old = (now - timedelta(hours=48)).isoformat().replace("+00:00", "Z")

    nodes = [
        _node("EDG-10", "completed", completed_at=recent),   # 昨日完成
        _node("EDG-11", "completed", completed_at=old),      # 太舊，排除
        _node("EDG-12", "started"),                          # 今日計畫（進行中）
        _node("EDG-13", "unstarted"),                        # 今日計畫（待辦）
        _node("EDG-14", "started", blocked_by_open=True),    # Blocker（關係）
        _node("EDG-15", "unstarted", labels=["Blocked"]),    # Blocker（label）
        _node("EDG-16", "backlog"),                          # 不進 standup
    ]
    issues = [standup._issue_from_node(n) for n in nodes]
    done, planned, blockers = standup.classify_issues(issues, cutoff)

    assert [i.identifier for i in done] == ["EDG-10"]
    assert {i.identifier for i in planned} == {"EDG-12", "EDG-13"}
    assert {i.identifier for i in blockers} == {"EDG-14", "EDG-15"}
    # started 應排在 unstarted 前
    assert planned[0].state_type == "started"


def test_classify_issues_ignores_negated_block_labels():
    now = standup._now()
    cutoff = now - timedelta(hours=24)
    nodes = [
        _node("EDG-17", "started", labels=["Unblocked"]),
        _node("EDG-18", "unstarted", labels=["Non-blocking"]),
        _node("EDG-19", "started", labels=["Blocked"]),
    ]
    issues = [standup._issue_from_node(n) for n in nodes]
    _, planned, blockers = standup.classify_issues(issues, cutoff)

    assert {i.identifier for i in planned} == {"EDG-17", "EDG-18"}
    assert [i.identifier for i in blockers] == ["EDG-19"]


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _sample_data():
    now = standup._now()
    return standup.StandupData(
        since=now - timedelta(hours=24),
        now=now,
        viewer="德德",
        commits=[standup.Commit(sha="abcdef1234", author="德德", date="d", subject="feat: x")],
        done=[standup.LinearIssue("EDG-1", "done it", "u", "Done", "completed", "")],
        planned=[standup.LinearIssue("EDG-2", "do it", "u", "In Progress", "started", "")],
        blockers=[standup.LinearIssue("EDG-3", "stuck", "u", "Todo", "unstarted", "",
                                      blocked_by=["EDG-9"])],
        memories=[standup.Memory(text="上週決定用 stdlib")],
        notes=["未設定 MEM0_API_KEY，略過 mem0。"],
    )


def test_render_markdown_has_all_sections():
    md = standup.render_markdown(_sample_data())
    for heading in ("## ✅ 昨日完成", "## 🎯 今日計畫", "## 🚧 Blockers",
                    "🧠 記憶脈絡", "🔨 Git commits", "資料來源備註"):
        assert heading in md
    assert "`EDG-1`" in md
    assert "被 EDG-9 卡住" in md
    assert "`abcdef1`" in md  # short sha


def test_render_markdown_empty_sections_have_placeholders():
    now = standup._now()
    empty = standup.StandupData(
        since=now - timedelta(hours=24), now=now, viewer="",
        commits=[], done=[], planned=[], blockers=[], memories=[], notes=[],
    )
    md = standup.render_markdown(empty)
    assert "無 🎉" in md  # blockers empty
    assert "（unknown）" in md


def test_render_json_is_valid_and_structured():
    import json
    payload = json.loads(standup.render_json(_sample_data()))
    assert payload["yesterday_done"][0]["identifier"] == "EDG-1"
    assert payload["today_plan"][0]["state_type"] == "started"
    assert payload["blockers"][0]["blocked_by"] == ["EDG-9"]
    assert payload["commits"][0]["author"] == "德德"


def test_within_window_boundaries():
    now = standup._now()
    cutoff = now - timedelta(hours=24)
    assert standup._within((now - timedelta(hours=1)).isoformat(), cutoff) is True
    assert standup._within((now - timedelta(hours=48)).isoformat(), cutoff) is False
    assert standup._within("", cutoff) is False
    assert standup._within("garbage", cutoff) is False
