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

def collect_agy():
    today = dt.datetime.now().date()
    today_str = local_date_str(today)
    recent_dates = recent_date_strings()
    recent = {day: {"date": day, "messageCount": 0} for day in recent_dates}

    gemini_cli_home = Path(os.environ.get("GEMINI_CLI_HOME") or (Path.home() / ".gemini" / "antigravity-cli"))
    brain_dir = gemini_cli_home / "brain"

    today_prompts = 0
    today_sessions = set()
    today_total_tokens = 0
    today_tokens_by_model: dict[str, int] = {}
    model_usage: dict[str, dict[str, int]] = {}
    active_days: set[str] = set()
    total_prompts = 0
    total_sessions = set()

    if brain_dir.is_dir():
        transcript_files = list(brain_dir.glob("*/.system_generated/logs/transcript.jsonl"))
        for tpath in transcript_files:
            try:
                conv_id = tpath.parent.parent.parent.name
                total_sessions.add(conv_id)

                mtime = tpath.stat().st_mtime
                session_dt = dt.datetime.fromtimestamp(mtime)
                session_date_str = local_date_str(session_dt.date())

                session_model = "Gemini 3.7 Flash"
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
                                    entry_date_str = local_date_str(dt.datetime.fromisoformat(created.replace("Z", "+00:00")).date())
                                except Exception:
                                    pass

                            if step_type == "USER_INPUT" or (step_type == "TASK" and source == "USER_EXPLICIT"):
                                total_prompts += 1
                                active_days.add(entry_date_str)
                                if entry_date_str == today_str:
                                    today_prompts += 1
                                    today_sessions.add(conv_id)

                            if step_type == "PLANNER_RESPONSE":
                                calls = obj.get("tool_calls", [])
                                for c in calls:
                                    subagents = c.get("arguments", {}).get("Subagents", [])
                                    for sub in subagents:
                                        m = sub.get("Model")
                                        if m and m != "inherit":
                                            session_model = f"Gemini ({m})"

                                content = obj.get("content", "")
                                thinking = obj.get("thinking", "")
                                total_chars = len(content) + len(thinking)
                                est_tokens = max(1, round(total_chars / 3.85)) if total_chars > 0 else 0

                                b = model_usage.setdefault(session_model, {
                                    "inputTokens": 0,
                                    "outputTokens": 0,
                                    "cacheReadInputTokens": 0,
                                    "cacheCreationInputTokens": 0,
                                })
                                b["outputTokens"] += est_tokens
                                if entry_date_str in recent:
                                    recent[entry_date_str]["messageCount"] += est_tokens
                                if entry_date_str == today_str:
                                    today_total_tokens += est_tokens
                                    today_tokens_by_model[session_model] = today_tokens_by_model.get(session_model, 0) + est_tokens
                                active_days.add(entry_date_str)
                        except Exception:
                            continue
            except Exception:
                continue

    agy_bin = shutil.which("agy") or str(Path.home() / ".local" / "bin" / "agy")
    is_ready = os.path.exists(agy_bin) or (brain_dir.is_dir() and len(total_sessions) > 0)

    record = {
        "schemaVersion": 1,
        "id": "agy",
        "name": "Antigravity",
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ready": is_ready,
        "hasLocalStats": len(total_sessions) > 0,
        "hasPromptStats": True,
        "tierLabel": "Vertex AI",
        "usageStatusText": "",
        "authHelpText": "Antigravity uses Vertex AI ADC auth.",
        "activeModel": "Gemini 3.7 Flash",
        "limits": [],
        "todayPrompts": today_prompts,
        "todaySessions": len(today_sessions),
        "todayTotalTokens": today_total_tokens,
        "todayTokensByModel": today_tokens_by_model,
        "recentDays": [recent[d] for d in recent_dates],
        "totalPrompts": total_prompts,
        "totalSessions": len(total_sessions),
        "activeDays": len(active_days),
        "activeDates": sorted(active_days),
        "modelUsage": model_usage,
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
    parser.add_argument("--force", action="store_true", help="Force rescan")
    parser.add_argument("--limits-only", action="store_true", help="Only refresh limits")
    args, _ = parser.parse_known_args()

    collect_agy()
    collect_codex()
    collect_grok()
    collect_copilot()


if __name__ == "__main__":
    main()
