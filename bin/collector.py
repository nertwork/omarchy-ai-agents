#!/usr/bin/env python3
"""Unified Agent Usage Collector for Omarchy.

Collects usage statistics, subscriptions, and rate limits for:
- Antigravity (AGY) - Vertex AI token usage, prompt counts, and model stats
- OpenAI Codex - Non-blocking RPC rate limits (5h & 7d windows) and session stats
- Grok CLI - Session token counts, prompts, and active model stats
- GitHub Copilot - CLI session token counts and active model stats

Writes display-ready records to ~/.local/state/omarchy/agents/usage/
for the Omarchy Agents panel.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time


def get_usage_dir() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    usage_dir = state_home / "omarchy" / "agents" / "usage"
    usage_dir.mkdir(parents=True, exist_ok=True)
    return usage_dir


def local_date_str(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def recent_date_strings() -> list[str]:
    today = dt.datetime.now().date()
    return [local_date_str(today - dt.timedelta(days=offset)) for offset in range(6, -1, -1)]


def write_state_file(agent_id: str, record: dict) -> Path:
    usage_dir = get_usage_dir()
    target = usage_dir / f"{agent_id}.json"
    handle_fd, tmp_name = tempfile.mkstemp(dir=usage_dir, prefix=f".{agent_id}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
            handle.write("\n")
        tmp.chmod(0o644)
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return target


# =============================================================================
# Antigravity (AGY)
# =============================================================================

# Vertex AI / AI Studio Pricing for Gemini models (per 1M tokens)
# Promotional Pricing (effective through Dec 31, 2026):
AGY_PRICING = {
    "Gemini 3.8 Flash (High)": {
        "input": 0.75,
        "cache": 0.075,
        "output": 3.75,
    },
    "gemini-3.8-flash": {
        "input": 0.75,
        "cache": 0.075,
        "output": 3.75,
    },
    "Gemini 3.5 Flash Lite": {
        "input": 0.30,
        "cache": 0.03,
        "output": 2.50,
    },
    "gemini-3.5-flash-lite": {
        "input": 0.30,
        "cache": 0.03,
        "output": 2.50,
    },
    "Gemini 2.5 Pro": {
        "input": 1.25,
        "cache": 0.3125,
        "output": 10.00,
    },
    "gemini-2.5-pro": {
        "input": 1.25,
        "cache": 0.3125,
        "output": 10.00,
    },
}
AGY_DEFAULT_MODEL = "Gemini 3.8 Flash (High)"


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    res = 0
    shift = 0
    while True:
        b = data[offset]
        offset += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, offset


def _parse_proto(data: bytes) -> dict[int, list]:
    fields: dict[int, list] = {}
    offset = 0
    length = len(data)
    while offset < length:
        try:
            tag_wire, offset = _read_varint(data, offset)
        except Exception:
            break
        tag = tag_wire >> 3
        wire = tag_wire & 7
        if wire == 0:
            val, offset = _read_varint(data, offset)
        elif wire == 1:
            val = data[offset : offset + 8]
            offset += 8
        elif wire == 2:
            l, offset = _read_varint(data, offset)
            val = data[offset : offset + l]
            offset += l
        elif wire == 5:
            val = data[offset : offset + 4]
            offset += 4
        else:
            break
        fields.setdefault(tag, []).append(val)
    return fields


def get_conversation_model(db_path: Path) -> str:
    if not db_path.is_file():
        return AGY_DEFAULT_MODEL
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gen_metadata'")
        if not cur.fetchone():
            return AGY_DEFAULT_MODEL
        cur.execute("SELECT data FROM gen_metadata WHERE data IS NOT NULL LIMIT 10")
        for (data,) in cur.fetchall():
            if not isinstance(data, (bytes, bytearray)):
                continue
            outer = _parse_proto(data)
            for sub1 in outer.get(1, []):
                inner = _parse_proto(sub1)
                if 19 in inner:
                    raw_name = inner[19][0].decode(errors="ignore").strip()
                    if "3.8-flash" in raw_name or "3.8" in raw_name:
                        return "Gemini 3.8 Flash (High)"
                    elif "3.5-flash-lite" in raw_name:
                        return "Gemini 3.5 Flash Lite"
                    elif "2.5-pro" in raw_name:
                        return "Gemini 2.5 Pro"
                    elif raw_name:
                        return raw_name
    except Exception:
        pass
    return AGY_DEFAULT_MODEL


def collect_agy():
    today = dt.datetime.now().date()
    today_str = local_date_str(today)
    recent_dates = recent_date_strings()
    recent = {day: {"date": day, "messageCount": 0, "costUsd": 0.0} for day in recent_dates}

    gemini_cli_home = Path(os.environ.get("GEMINI_CLI_HOME") or (Path.home() / ".gemini" / "antigravity-cli"))
    brain_dir = gemini_cli_home / "brain"
    conv_db_dir = gemini_cli_home / "conversations"
    sum_db = gemini_cli_home / "conversation_summaries.db"

    # Map subagents to their root parent conversations and extract titles
    titles: dict[str, str] = {}
    parent_map: dict[str, str] = {}
    if sum_db.is_file():
        try:
            conn = sqlite3.connect(str(sum_db))
            cur = conn.cursor()
            cur.execute("SELECT conversation_id, title, parent_conversation_id FROM conversation_summaries")
            for cid, t, p in cur.fetchall():
                if t:
                    titles[cid] = t
                if p:
                    parent_map[cid] = p
            conn.close()
        except Exception:
            pass

    def get_root_id(cid: str) -> str:
        curr = cid
        visited = set()
        while curr in parent_map and curr not in visited:
            visited.add(curr)
            curr = parent_map[curr]
        return curr

    today_prompts = 0
    today_root_sessions: set[str] = set()
    today_total_tokens = 0
    today_total_cost = 0.0
    today_tokens_by_model: dict[str, int] = {}
    model_usage: dict[str, dict[str, int | float]] = {}
    active_days: set[str] = set()
    total_prompts = 0
    root_sessions: set[str] = set()
    total_cost = 0.0

    # Per-root conversation statistics (child subagents are rolled up into parent)
    conv_stats: dict[str, dict] = {}

    if brain_dir.is_dir():
        transcript_files = list(brain_dir.glob("*/.system_generated/logs/transcript.jsonl"))
        for tpath in transcript_files:
            try:
                cid = tpath.parent.parent.parent.name
                root_id = get_root_id(cid)

                mtime = tpath.stat().st_mtime
                session_dt = dt.datetime.fromtimestamp(mtime)
                session_date_str = local_date_str(session_dt.date())

                db_path = conv_db_dir / f"{cid}.db"
                session_model = get_conversation_model(db_path)

                if root_id not in conv_stats:
                    conv_stats[root_id] = {
                        "tokens": 0,
                        "inp": 0,
                        "cache": 0,
                        "out": 0,
                        "cost": 0.0,
                        "prompts": 0,
                        "mtime": mtime,
                        "model": session_model,
                    }
                else:
                    conv_stats[root_id]["mtime"] = max(conv_stats[root_id]["mtime"], mtime)

                with tpath.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            step_type = obj.get("type", "")
                            source = obj.get("source", "")
                            created = obj.get("created_at")

                            entry_date_str = session_date_str
                            if created:
                                try:
                                    entry_date_str = local_date_str(
                                        dt.datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone().date()
                                    )
                                except Exception:
                                    pass

                            # Only count explicit user prompts in root sessions
                            if step_type == "USER_INPUT" and source == "USER_EXPLICIT":
                                total_prompts += 1
                                root_sessions.add(root_id)
                                conv_stats[root_id]["prompts"] += 1
                                active_days.add(entry_date_str)
                                if entry_date_str == today_str:
                                    today_prompts += 1
                                    today_root_sessions.add(root_id)

                            if step_type == "PLANNER_RESPONSE":
                                if obj.get("input_tokens") is not None:
                                    inp = int(obj.get("input_tokens") or 0)
                                    cache_read = int(obj.get("cache_read_tokens") or 0)
                                    out = int(obj.get("output_tokens") or 0)
                                else:
                                    content = obj.get("content", "") or ""
                                    thinking = obj.get("thinking", "") or ""
                                    tc = obj.get("tool_calls") or []
                                    tc_len = len(json.dumps(tc)) if tc else 0
                                    total_chars = len(content) + len(thinking) + tc_len
                                    inp = 0
                                    cache_read = 0
                                    out = max(1, round(total_chars / 3.85)) if total_chars > 0 else 0

                                rates = AGY_PRICING.get(session_model, AGY_PRICING[AGY_DEFAULT_MODEL])
                                turn_cost = (
                                    inp * rates["input"]
                                    + cache_read * rates["cache"]
                                    + out * rates["output"]
                                ) / 1_000_000.0
                                turn_total = inp + cache_read + out

                                b = model_usage.setdefault(session_model, {
                                    "inputTokens": 0,
                                    "outputTokens": 0,
                                    "cacheReadInputTokens": 0,
                                    "cacheCreationInputTokens": 0,
                                    "costUsd": 0.0,
                                })
                                b["inputTokens"] += inp
                                b["outputTokens"] += out
                                b["cacheReadInputTokens"] += cache_read
                                b["costUsd"] += turn_cost

                                total_cost += turn_cost

                                if entry_date_str in recent:
                                    recent[entry_date_str]["messageCount"] += turn_total
                                    recent[entry_date_str]["costUsd"] += turn_cost

                                if entry_date_str == today_str:
                                    today_total_tokens += turn_total
                                    today_total_cost += turn_cost
                                    today_tokens_by_model[session_model] = (
                                        today_tokens_by_model.get(session_model, 0) + turn_total
                                    )

                                active_days.add(entry_date_str)

                                cs = conv_stats[root_id]
                                cs["tokens"] += turn_total
                                cs["inp"] += inp
                                cs["cache"] += cache_read
                                cs["out"] += out
                                cs["cost"] += turn_cost
                        except Exception:
                            continue
            except Exception:
                continue

    recent_conversations = []
    for rid, cs in sorted(conv_stats.items(), key=lambda item: item[1]["mtime"], reverse=True):
        if cs["prompts"] == 0 and cs["tokens"] == 0:
            continue
        title = titles.get(rid) or f"Session {rid[:8]}"
        recent_conversations.append({
            "id": rid,
            "title": title,
            "model": cs["model"],
            "tokens": cs["tokens"],
            "inputTokens": cs["inp"],
            "cacheReadTokens": cs["cache"],
            "outputTokens": cs["out"],
            "costUsd": round(cs["cost"], 2),
            "prompts": cs["prompts"],
            "updatedAt": dt.datetime.fromtimestamp(cs["mtime"]).isoformat(),
        })

    agy_bin = shutil.which("agy") or str(Path.home() / ".local" / "bin" / "agy")
    is_ready = os.path.exists(agy_bin) or (brain_dir.is_dir() and len(root_sessions) > 0)

    # Determine active model
    if today_tokens_by_model:
        active_model = max(today_tokens_by_model.keys(), key=lambda m: today_tokens_by_model[m])
    elif model_usage:
        active_model = max(
            model_usage.keys(),
            key=lambda m: model_usage[m]["inputTokens"]
            + model_usage[m]["cacheReadInputTokens"]
            + model_usage[m]["outputTokens"],
        )
    else:
        active_model = AGY_DEFAULT_MODEL

    serialized_model_usage = {}
    for m, data in model_usage.items():
        serialized_model_usage[m] = {
            "inputTokens": int(data["inputTokens"]),
            "outputTokens": int(data["outputTokens"]),
            "cacheReadInputTokens": int(data["cacheReadInputTokens"]),
            "cacheCreationInputTokens": int(data["cacheCreationInputTokens"]),
            "costUsd": round(float(data["costUsd"]), 2),
        }

    serialized_recent_days = [
        {
            "date": d,
            "messageCount": int(recent[d]["messageCount"]),
            "costUsd": round(float(recent[d]["costUsd"]), 2),
        }
        for d in recent_dates
    ]

    tier_label = f"Vertex AI · ${total_cost:.2f}"
    if today_total_cost > 0:
        tier_label += f" (${today_total_cost:.2f} today)"

    record = {
        "schemaVersion": 1,
        "id": "agy",
        "name": "Antigravity",
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ready": is_ready,
        "hasLocalStats": len(root_sessions) > 0,
        "hasPromptStats": True,
        "tierLabel": tier_label,
        "usageStatusText": "",
        "authHelpText": "Antigravity uses Vertex AI ADC auth.",
        "activeModel": active_model,
        "limits": [],
        "costUsd": round(total_cost, 2),
        "todayCostUsd": round(today_total_cost, 2),
        "todayPrompts": today_prompts,
        "todaySessions": len(today_root_sessions),
        "todayTotalTokens": today_total_tokens,
        "todayTokensByModel": dict(today_tokens_by_model),
        "recentDays": serialized_recent_days,
        "totalPrompts": total_prompts,
        "totalSessions": len(root_sessions),
        "activeDays": len(active_days),
        "activeDates": sorted(active_days),
        "modelUsage": serialized_model_usage,
        "recentConversations": recent_conversations[:8],
    }
    write_state_file("agy", record)


# =============================================================================
# OpenAI Codex (Robust Non-blocking RPC)
# =============================================================================

def limit_window_entry(window: dict | None) -> dict | None:
    if not isinstance(window, dict):
        return None
    used = window.get("usedPercent")
    if used is None:
        return None
    try:
        mins = int(window.get("windowDurationMins") or 0)
    except Exception:
        mins = 0
    if mins == 10080:
        label = "Weekly (7-day)"
    elif mins and mins % 60 == 0:
        label = f"{mins // 60}h window"
    elif mins:
        label = f"{mins}m window"
    else:
        label = "Limit"
    reset = window.get("resetsAt")
    reset_iso = ""
    if reset:
        try:
            reset_iso = dt.datetime.fromtimestamp(int(reset), dt.timezone.utc).isoformat()
        except Exception:
            pass
    return {
        "label": label,
        "percent": float(used) / 100.0,
        "resetsAt": reset_iso,
    }


def collect_codex():
    codex_cmd = shutil.which("codex")
    if not codex_cmd:
        candidates = [
            Path.home() / ".local" / "bin" / "codex",
            Path.home() / ".npm-global" / "bin" / "codex",
            Path.home() / ".local" / "share" / "mise" / "shims" / "codex",
        ]
        for c in candidates:
            if c.is_file():
                codex_cmd = str(c)
                break

    result = {
        "limits": [],
        "tierLabel": "",
        "usageStatusText": "",
        "authHelpText": "Run `codex login` to authenticate.",
    }

    if not codex_cmd:
        result["usageStatusText"] = "Codex unavailable"
        result["authHelpText"] = "codex not found in PATH"
        record = {
            "schemaVersion": 1,
            "id": "codex",
            "name": "Codex",
            "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "ready": False,
            "hasLocalStats": False,
        }
        record.update(result)
        write_state_file("codex", record)
        return

    # Non-blocking RPC to bypass buffered I/O starvation
    proc = None
    try:
        proc = subprocess.Popen(
            [codex_cmd, "-s", "read-only", "-a", "on-request", "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        fcntl.fcntl(proc.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)

        def rpc(req_id: int, method: str, params: dict | None = None, timeout: float = 4.0) -> dict:
            msg = json.dumps({"id": req_id, "method": method, "params": params or {}}) + "\n"
            proc.stdin.write(msg.encode())
            proc.stdin.flush()
            deadline = time.time() + timeout
            buf = b""
            while time.time() < deadline:
                try:
                    chunk = os.read(proc.stdout.fileno(), 4096)
                    if chunk:
                        buf += chunk
                except BlockingIOError:
                    pass
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        res = json.loads(line.decode())
                        if res.get("id") == req_id:
                            return res
                    except Exception:
                        pass
                time.sleep(0.01)
            raise TimeoutError(method)

        rpc(1, "initialize", {"clientInfo": {"name": "omarchy-agent-usage", "version": "1"}}, timeout=4.0)
        proc.stdin.write(b'{"method": "initialized", "params": {}}\n')
        proc.stdin.flush()
        account_msg = rpc(2, "account/read", timeout=3.0)
        limits_msg = rpc(3, "account/rateLimits/read", timeout=3.0)

        account = (account_msg.get("result") or {}).get("account") or {}
        limits = (limits_msg.get("result") or {}).get("rateLimits") or {}
        plan = limits.get("planType") or account.get("planType") or account.get("type") or ""
        result["tierLabel"] = str(plan).capitalize() if plan else ""

        for window in (limits.get("primary"), limits.get("secondary")):
            entry = limit_window_entry(window)
            if entry:
                result["limits"].append(entry)
    except Exception as exc:
        result["usageStatusText"] = "Codex limits unavailable"
        result["authHelpText"] = str(exc)
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    # Optional local stats via upstream helper if available
    stats = {}
    upstream_bin = Path("/usr/share/omarchy/bin/omarchy-agent-usage-codex")
    if upstream_bin.is_file():
        try:
            codex_mod = SourceFileLoader("codex_collector", str(upstream_bin)).load_module()
            stats = codex_mod.cached_local_stats(20)
        except Exception:
            pass

    record = {
        "schemaVersion": 1,
        "id": "codex",
        "name": "Codex",
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ready": True,
        "hasLocalStats": bool(stats.get("totalSessions", 0) > 0),
    }
    record.update(stats)
    record.update(result)
    write_state_file("codex", record)


# =============================================================================
# Grok CLI
# =============================================================================

def collect_grok():
    today = dt.datetime.now().date()
    today_str = local_date_str(today)
    recent_dates = recent_date_strings()
    recent = {day: {"date": day, "messageCount": 0} for day in recent_dates}

    grok_session_dirs = [
        Path.home() / ".grok" / "sessions",
        Path.home() / "migration-staging" / ".grok" / "sessions",
    ]

    total_prompts = 0
    today_prompts = 0
    today_tokens = 0
    today_tokens_by_model: dict[str, int] = {}
    model_usage: dict[str, dict[str, int]] = {}
    active_days: set[str] = set()
    total_sessions: set[str] = set()
    today_sessions: set[str] = set()

    for sdir in grok_session_dirs:
        if not sdir.is_dir():
            continue
        for up_path in sdir.glob("**/updates.jsonl"):
            session_id = up_path.parent.name
            total_sessions.add(session_id)
            try:
                mtime = up_path.stat().st_mtime
                session_dt = dt.datetime.fromtimestamp(mtime)
                session_date_str = local_date_str(session_dt.date())

                with up_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            ts = obj.get("timestamp")
                            entry_date_str = session_date_str
                            if ts:
                                try:
                                    entry_date_str = local_date_str(dt.datetime.fromtimestamp(ts).date())
                                except Exception:
                                    pass

                            update = obj.get("params", {}).get("update", {})
                            if update.get("sessionUpdate") == "turn_completed":
                                total_prompts += 1
                                active_days.add(entry_date_str)
                                if entry_date_str == today_str:
                                    today_prompts += 1
                                    today_sessions.add(session_id)

                                u = update.get("usage", {})
                                turn_in = u.get("inputTokens", 0)
                                turn_out = u.get("outputTokens", 0)
                                turn_total = turn_in + turn_out

                                if entry_date_str in recent:
                                    recent[entry_date_str]["messageCount"] += turn_total

                                mu = u.get("modelUsage", {})
                                if not mu:
                                    mu = {"grok-4.6": {"inputTokens": turn_in, "outputTokens": turn_out}}

                                for mname, mstats in mu.items():
                                    b = model_usage.setdefault(mname, {
                                        "inputTokens": 0,
                                        "outputTokens": 0,
                                        "cacheReadInputTokens": 0,
                                        "cacheCreationInputTokens": 0,
                                    })
                                    b["inputTokens"] += mstats.get("inputTokens", 0)
                                    b["outputTokens"] += mstats.get("outputTokens", 0)
                                    b["cacheReadInputTokens"] += mstats.get("cachedReadTokens", 0)

                                    if entry_date_str == today_str:
                                        today_tokens += turn_total
                                        today_tokens_by_model[mname] = today_tokens_by_model.get(mname, 0) + turn_total
                        except Exception:
                            continue
            except Exception:
                continue

    auth_file = Path.home() / ".grok" / "auth.json"
    is_ready = auth_file.is_file() and auth_file.stat().st_size > 5

    record = {
        "schemaVersion": 1,
        "id": "grok",
        "name": "Grok",
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ready": is_ready,
        "hasLocalStats": len(total_sessions) > 0,
        "hasPromptStats": True,
        "tierLabel": "Grok 4.6",
        "usageStatusText": "" if is_ready else "Waiting for auth",
        "authHelpText": "Run `grok login --device-auth` to authenticate.",
        "activeModel": "grok-4.6",
        "limits": [],
        "todayPrompts": today_prompts,
        "todaySessions": len(today_sessions),
        "todayTotalTokens": today_tokens,
        "todayTokensByModel": today_tokens_by_model,
        "recentDays": [recent[d] for d in recent_dates],
        "totalPrompts": total_prompts,
        "totalSessions": len(total_sessions),
        "activeDays": len(active_days),
        "activeDates": sorted(active_days),
        "modelUsage": model_usage,
    }
    write_state_file("grok", record)


# =============================================================================
# GitHub Copilot
# =============================================================================

def collect_copilot():
    today = dt.datetime.now().date()
    today_str = local_date_str(today)
    recent_dates = recent_date_strings()
    recent = {day: {"date": day, "messageCount": 0} for day in recent_dates}

    copilot_dirs = [
        Path.home() / ".copilot" / "session-state",
        Path.home() / "migration-staging" / ".copilot" / "session-state",
    ]

    total_prompts = 0
    today_prompts = 0
    today_tokens = 0
    today_tokens_by_model: dict[str, int] = {}
    model_usage: dict[str, dict[str, int]] = {}
    active_days: set[str] = set()
    total_sessions: set[str] = set()
    today_sessions: set[str] = set()

    for cdir in copilot_dirs:
        if not cdir.is_dir():
            continue
        for ev_path in cdir.glob("**/events.jsonl"):
            session_id = ev_path.parent.name
            total_sessions.add(session_id)
            try:
                mtime = ev_path.stat().st_mtime
                session_dt = dt.datetime.fromtimestamp(mtime)
                session_date_str = local_date_str(session_dt.date())

                with ev_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            ev_type = obj.get("type")
                            ts_str = obj.get("timestamp")
                            entry_date_str = session_date_str
                            if ts_str:
                                try:
                                    entry_date_str = local_date_str(dt.datetime.fromisoformat(ts_str.replace("Z", "+00:00")).date())
                                except Exception:
                                    pass

                            data = obj.get("data", {})
                            if ev_type == "user.message":
                                total_prompts += 1
                                active_days.add(entry_date_str)
                                if entry_date_str == today_str:
                                    today_prompts += 1
                                    today_sessions.add(session_id)
                            elif ev_type == "assistant.message":
                                out_tok = data.get("outputTokens", 0)
                                model = data.get("model") or "copilot"
                                b = model_usage.setdefault(model, {
                                    "inputTokens": 0,
                                    "outputTokens": 0,
                                    "cacheReadInputTokens": 0,
                                    "cacheCreationInputTokens": 0,
                                })
                                b["outputTokens"] += out_tok
                                if entry_date_str in recent:
                                    recent[entry_date_str]["messageCount"] += out_tok
                                if entry_date_str == today_str:
                                    today_tokens += out_tok
                                    today_tokens_by_model[model] = today_tokens_by_model.get(model, 0) + out_tok
                                active_days.add(entry_date_str)
                        except Exception:
                            continue
            except Exception:
                continue

    copilot_auth_check = Path.home() / ".copilot" / "config.json"
    is_ready = copilot_auth_check.is_file()

    record = {
        "schemaVersion": 1,
        "id": "copilot",
        "name": "GitHub Copilot",
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ready": is_ready,
        "hasLocalStats": len(total_sessions) > 0,
        "hasPromptStats": True,
        "tierLabel": "Copilot",
        "usageStatusText": "" if is_ready else "Waiting for auth",
        "authHelpText": "Run `copilot login --device-code` to authenticate.",
        "activeModel": "copilot",
        "limits": [],
        "todayPrompts": today_prompts,
        "todaySessions": len(today_sessions),
        "todayTotalTokens": today_tokens,
        "todayTokensByModel": today_tokens_by_model,
        "recentDays": [recent[d] for d in recent_dates],
        "totalPrompts": total_prompts,
        "totalSessions": len(total_sessions),
        "activeDays": len(active_days),
        "activeDates": sorted(active_days),
        "modelUsage": model_usage,
    }
    write_state_file("copilot", record)


def main():
    parser = argparse.ArgumentParser(description="Collect usage for AI assistants.")
    parser.add_argument(
        "agents",
        nargs="*",
        help="Specific agent(s) to collect (agy, codex, grok, copilot). If omitted, collects all.",
    )
    parser.add_argument("--force", action="store_true", help="Force rescan")
    parser.add_argument("--limits-only", action="store_true", help="Only refresh limits")
    args, _ = parser.parse_known_args()

    collectors = {
        "agy": collect_agy,
        "codex": collect_codex,
        "grok": collect_grok,
        "copilot": collect_copilot,
    }

    targets = [a.lower() for a in args.agents] if args.agents else list(collectors.keys())
    for target in targets:
        fn = collectors.get(target)
        if fn:
            fn()
        else:
            print(f"Unknown agent: {target}", file=sys.stderr)


if __name__ == "__main__":
    main()
