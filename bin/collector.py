#!/usr/bin/env python3
"""Unified Modular Agent Usage Collector for Omarchy (nertwork.agents).

Supports two operating modes out of the box (strictly on localhost):
1. Out-of-the-Box Public Default (`splitProfiles: false`):
   - Emits `agy.json` (aggregating all local Antigravity profiles) and
     `claude.json` (aggregating all local Claude Code profiles).
2. Modular Multi-Profile Mode (`splitProfiles: true`, enabled via
   `~/.local/state/omarchy/settings/nertwork.agents.json` or
   `~/.config/omarchy/agents/profiles.json`):
   - Emits separate non-overlapping provider files:
     * `agy.json` (primary AGY profile)
     * `agy-sandbox.json` (secondary/sandbox AGY profile)
     * `claude-work.json` (secondary/work Claude profile)
     * `claude.json` (primary/personal Claude profile)
   - Also emits `_summary.json` with family-level (`agy`, `claude`) and
     cross-provider (`grandTotal`) rollups, and embeds `aggregation` and
     `groupTotals` metadata into each provider JSON file.
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
import socket
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
os.umask(0o077)


def get_usage_dir() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    agents_state_dir = state_home / "omarchy" / "agents"
    usage_dir = agents_state_dir / "usage"
    usage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        agents_state_dir.chmod(0o700)
        usage_dir.chmod(0o700)
    except OSError:
        pass
    return usage_dir


def get_legacy_usage_dir() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    legacy_dir = state_home / "omarchy" / "agent-usage"
    legacy_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        legacy_dir.chmod(0o700)
    except OSError:
        pass
    return legacy_dir


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
        tmp.chmod(0o600)
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    # Mirror to legacy `~/.local/state/omarchy/agent-usage/` directory
    try:
        legacy_dir = get_legacy_usage_dir()
        shutil.copy2(target, legacy_dir / target.name)
    except Exception:
        pass

    return target


def remove_state_file(agent_id: str) -> None:
    for d in (get_usage_dir(), get_legacy_usage_dir()):
        p = d / f"{agent_id}.json"
        p.unlink(missing_ok=True)


_SETTINGS_CACHE: dict | None = None


def load_settings() -> dict:
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is not None:
        return _SETTINGS_CACHE
    state_home = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    settings_path = state_home / "omarchy" / "settings" / "nertwork.agents.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _SETTINGS_CACHE = data
                return data
        except Exception:
            pass
    _SETTINGS_CACHE = {}
    return _SETTINGS_CACHE


def is_provider_enabled(provider_id: str, default: bool = False) -> bool:
    settings = load_settings()
    providers = settings.get("providers")
    if isinstance(providers, dict):
        p = providers.get(provider_id)
        if isinstance(p, dict) and "enabled" in p:
            return bool(p["enabled"])
    enabled_list = settings.get("enabledProviders")
    if isinstance(enabled_list, list):
        return provider_id in enabled_list
    return default


def limit_window_entry(window: dict | None) -> dict | None:
    if not isinstance(window, dict):
        return None
    label = window.get("label") or window.get("name") or window.get("window") or "Limit"
    pct = window.get("percent")
    if pct is None:
        used = window.get("used")
        limit = window.get("limit") or window.get("max")
        if isinstance(used, (int, float)) and isinstance(limit, (int, float)) and limit > 0:
            pct = float(used) / float(limit)
    if pct is None:
        return None
    resets_at = window.get("resetsAt") or window.get("resetAt") or ""
    return {
        "label": str(label),
        "percent": round(max(0.0, min(1.0, float(pct))), 4),
        "resetsAt": str(resets_at),
    }


def _normalize_family_sum(fsum: dict) -> dict:
    out = dict(fsum)
    out["todayTokens"] = int(out.get("todayTokens", out.get("tokensToday", 0)))
    out["tokensToday"] = out["todayTokens"]
    out["sevenDayTokens"] = int(out.get("sevenDayTokens", out.get("tokens7d", 0)))
    out["tokens7d"] = out["sevenDayTokens"]
    out["thirtyDayTokens"] = int(out.get("thirtyDayTokens", out.get("tokens30d", 0)))
    out["tokens30d"] = out["thirtyDayTokens"]
    out["allTimeTokens"] = int(out.get("allTimeTokens", 0))
    out["todayCostUsd"] = round(float(out.get("todayCostUsd", out.get("costUsdToday", 0.0))), 2)
    out["costUsdToday"] = out["todayCostUsd"]
    out["sevenDayCostUsd"] = round(float(out.get("sevenDayCostUsd", out.get("costUsd7d", 0.0))), 2)
    out["costUsd7d"] = out["sevenDayCostUsd"]
    out["thirtyDayCostUsd"] = round(float(out.get("thirtyDayCostUsd", out.get("costUsd30d", 0.0))), 2)
    out["costUsd30d"] = out["thirtyDayCostUsd"]
    out["allTimeCostUsd"] = round(float(out.get("allTimeCostUsd", 0.0)), 2)
    out["todayPrompts"] = int(out.get("todayPrompts", out.get("promptsToday", 0)))
    out["promptsToday"] = out["todayPrompts"]
    out["thirtyDayPrompts"] = int(out.get("thirtyDayPrompts", out.get("prompts30d", 0)))
    out["prompts30d"] = out["thirtyDayPrompts"]
    out["todaySessions"] = int(out.get("todaySessions", out.get("sessionsToday", 0)))
    out["sessionsToday"] = out["todaySessions"]
    out["thirtyDaySessions"] = int(out.get("thirtyDaySessions", out.get("sessions30d", 0)))
    out["sessions30d"] = out["thirtyDaySessions"]
    return out


def _build_grand_summary(agy_sum: dict, claude_sum: dict, agy_split: bool, claude_split: bool) -> dict:
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    agy_sum = _normalize_family_sum(agy_sum)
    claude_sum = _normalize_family_sum(claude_sum)
    grand_total = _normalize_family_sum({
        "todayTokens": agy_sum["todayTokens"] + claude_sum["todayTokens"],
        "sevenDayTokens": agy_sum["sevenDayTokens"] + claude_sum["sevenDayTokens"],
        "thirtyDayTokens": agy_sum["thirtyDayTokens"] + claude_sum["thirtyDayTokens"],
        "allTimeTokens": agy_sum["allTimeTokens"] + claude_sum["allTimeTokens"],
        "todayCostUsd": round(agy_sum["todayCostUsd"] + claude_sum["todayCostUsd"], 2),
        "sevenDayCostUsd": round(agy_sum["sevenDayCostUsd"] + claude_sum["sevenDayCostUsd"], 2),
        "thirtyDayCostUsd": round(agy_sum["thirtyDayCostUsd"] + claude_sum["thirtyDayCostUsd"], 2),
        "allTimeCostUsd": round(agy_sum["allTimeCostUsd"] + claude_sum["allTimeCostUsd"], 2),
        "todayPrompts": agy_sum["todayPrompts"] + claude_sum["todayPrompts"],
        "thirtyDayPrompts": agy_sum["thirtyDayPrompts"] + claude_sum["thirtyDayPrompts"],
        "todaySessions": agy_sum["todaySessions"] + claude_sum["todaySessions"],
        "thirtyDaySessions": agy_sum["thirtyDaySessions"] + claude_sum["thirtyDaySessions"],
    })
    profiles_list = list(agy_sum.get("profiles", [])) + list(claude_sum.get("profiles", []))
    work_c_prof = next((p for p in claude_sum.get("profiles", []) if p.get("id") == "claude-work"), {})
    pers_c_prof = next((p for p in claude_sum.get("profiles", []) if p.get("id") == "claude"), {})
    work_30d = round(float(agy_sum.get("workCostUsd30d", 0.0)) + float(work_c_prof.get("costUsd30d", 0.0)), 2)
    work_7d = round(float(agy_sum.get("workCostUsd7d", 0.0)) + float(work_c_prof.get("costUsd7d", 0.0)), 2)
    work_today = round(float(agy_sum.get("workCostUsdToday", 0.0)) + float(work_c_prof.get("costUsdToday", 0.0)), 2)
    pers_30d = round(float(agy_sum.get("personalCostUsd30d", 0.0)) + float(pers_c_prof.get("costUsd30d", 0.0)), 2)
    pers_7d = round(float(agy_sum.get("personalCostUsd7d", 0.0)) + float(pers_c_prof.get("costUsd7d", 0.0)), 2)
    pers_today = round(float(agy_sum.get("personalCostUsdToday", 0.0)) + float(pers_c_prof.get("costUsdToday", 0.0)), 2)
    org_30d = round(float(agy_sum.get("orgCostUsd30d", 0.0)), 2)
    org_7d = round(float(agy_sum.get("orgCostUsd7d", 0.0)), 2)
    org_today = round(float(agy_sum.get("orgCostUsdToday", 0.0)), 2)

    settings_dict = load_settings()
    localhost_only = bool(settings_dict.get("localhostOnly", False))
    try:
        daily_quota_usd = float(settings_dict.get("dailyQuotaUsd", 50.0))
    except (TypeError, ValueError):
        daily_quota_usd = 50.0
    over_daily_quota = bool(daily_quota_usd > 0 and grand_total["todayCostUsd"] >= daily_quota_usd)
    grand_total["dailyQuotaUsd"] = daily_quota_usd
    grand_total["overDailyQuota"] = over_daily_quota
    return {
        "schemaVersion": 2,
        "updatedAt": now_iso,
        "executionScope": "localhost" if localhost_only else "multi-host",
        "localhostOnly": localhost_only,
        "dailyQuotaUsd": daily_quota_usd,
        "overDailyQuota": over_daily_quota,
        "splitProfiles": bool(agy_split or claude_split),
        "agySplitProfiles": bool(agy_split),
        "claudeSplitProfiles": bool(claude_split),
        "barCostWindow": "today",
        "todayCostUsd": round(grand_total.get("todayCostUsd", 0.0), 2),
        "sevenDayCostUsd": round(grand_total.get("sevenDayCostUsd", 0.0), 2),
        "thirtyDayCostUsd": round(grand_total.get("thirtyDayCostUsd", 0.0), 2),
        "grandTotal": grand_total,
        "workVsPersonal": {
            "workCostUsd30d": work_30d,
            "workCostUsd7d": work_7d,
            "workCostUsdToday": work_today,
            "personalCostUsd30d": pers_30d,
            "personalCostUsd7d": pers_7d,
            "personalCostUsdToday": pers_today,
            "orgCostUsd30d": org_30d,
            "orgCostUsd7d": org_7d,
            "orgCostUsdToday": org_today,
        },
        "groups": {
            "agy": agy_sum,
            "claude": claude_sum,
        },
        "agy": agy_sum,
        "claude": claude_sum,
        "profiles": profiles_list,
    }


def _enrich_record_with_summary(record: dict, family_sum: dict, grand_summary: dict) -> dict:
    enriched = dict(record)
    agg = dict(enriched.get("aggregation") or family_sum)
    agg["grandTotal"] = grand_summary["grandTotal"]
    agg["groups"] = grand_summary["groups"]
    enriched["aggregation"] = agg
    enriched["groupTotals"] = family_sum
    enriched["grandTotals"] = grand_summary["grandTotal"]
    return enriched


def collect_agy_and_claude(
    want_agy: bool = True,
    want_agy_sandbox: bool | None = None,
    want_claude: bool = True,
    want_claude_work: bool | None = None,
    force: bool = False,
    split_override: bool | None = None,
) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import agy_core
    import claude_core

    agy_split = split_override if split_override is not None else agy_core.is_agy_split_enabled()
    claude_split = split_override if split_override is not None else claude_core.is_claude_split_enabled()
    if want_agy_sandbox is True:
        agy_split = True
    if want_claude_work is True:
        claude_split = True

    agy_profiles = agy_core.collect_agy_profiles(force=force, split_profiles=agy_split)
    claude_profiles = claude_core.collect_claude_profiles(force=force, split_profiles=claude_split)

    agy_sum = agy_profiles["summary"]
    claude_sum = claude_profiles["summary"]
    grand_summary = _build_grand_summary(agy_sum, claude_sum, agy_split, claude_split)

    local_host = socket.gethostname().split(".")[0] or "localhost"
    allowed_agy_profiles = set(
        agy_core.HOST_ALLOWED_PROFILES.get(
            local_host, ("agy-personal", "agy-org", "agy", "agy-sandbox")
        )
    )

    if want_agy or want_agy_sandbox:
        if agy_split:
            if want_agy:
                for pid in ("agy", "agy-personal", "agy-org"):
                    if pid in allowed_agy_profiles:
                        rec_p = _enrich_record_with_summary(agy_profiles[pid], agy_sum, grand_summary)
                        write_state_file(pid, rec_p)
                    else:
                        remove_state_file(pid)
            if want_agy_sandbox is not False and "agy-sandbox" in allowed_agy_profiles:
                rec_sb = _enrich_record_with_summary(agy_profiles["agy-sandbox"], agy_sum, grand_summary)
                write_state_file("agy-sandbox", rec_sb)
            elif "agy-sandbox" not in allowed_agy_profiles:
                remove_state_file("agy-sandbox")
        else:
            rec_all_agy = _enrich_record_with_summary(agy_profiles["all"], agy_sum, grand_summary)
            write_state_file("agy", rec_all_agy)
            if want_agy_sandbox and "agy-sandbox" in allowed_agy_profiles:
                rec_sb = _enrich_record_with_summary(agy_profiles["agy-sandbox"], agy_sum, grand_summary)
                write_state_file("agy-sandbox", rec_sb)
            else:
                remove_state_file("agy-sandbox")
                remove_state_file("agy-personal")
                remove_state_file("agy-org")

    if want_claude or want_claude_work:
        if claude_split:
            if want_claude_work is not False:
                rec_claude_work = _enrich_record_with_summary(claude_profiles["claude-work"], claude_sum, grand_summary)
                write_state_file("claude-work", rec_claude_work)
            if want_claude:
                rec_personal = _enrich_record_with_summary(claude_profiles["claude-personal"], claude_sum, grand_summary)
                write_state_file("claude", rec_personal)
        else:
            rec_all_claude = _enrich_record_with_summary(claude_profiles["all"], claude_sum, grand_summary)
            write_state_file("claude", rec_all_claude)
            if want_claude_work:
                rec_claude_work = _enrich_record_with_summary(claude_profiles["claude-work"], claude_sum, grand_summary)
                write_state_file("claude-work", rec_claude_work)
            else:
                remove_state_file("claude-work")

    write_state_file("_summary", grand_summary)
    return grand_summary


# =============================================================================
# OpenAI Codex
# =============================================================================

def collect_codex(force: bool = False):
    if not is_provider_enabled("codex", default=False):
        return

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
        result["usageStatusText"] = "Local + remote session history"
        result["authHelpText"] = "codex CLI not installed on this host; showing synced session stats."
    elif is_provider_enabled("codex", default=False) or force:
        proc = None
        try:
            proc = subprocess.Popen(
                [codex_cmd, "-s", "read-only", "-a", "on-request", "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            fcntl.fcntl(proc.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)

            def rpc(req_id: int, method: str, params: dict | None = None, timeout: float = 2.5) -> dict:
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

            rpc(1, "initialize", {"clientInfo": {"name": "omarchy-agent-usage", "version": "1"}}, timeout=2.5)
            proc.stdin.write(b'{"method": "initialized", "params": {}}\n')
            proc.stdin.flush()
            account_msg = rpc(2, "account/read", timeout=2.0)
            limits_msg = rpc(3, "account/rateLimits/read", timeout=2.0)

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
                    proc.wait(timeout=0.5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    stats = {}
    upstream_bin = Path("/usr/share/omarchy/bin/omarchy-agent-usage-codex")
    if upstream_bin.is_file():
        try:
            codex_mod = SourceFileLoader("codex_collector", str(upstream_bin)).load_module()
            stats = codex_mod.cached_local_stats(20)
        except Exception:
            pass

    # Scan local + synced remote .codex/sessions/*.jsonl for full all-time token & cost telemetry
    codex_files = {}
    codex_roots = [Path.home() / ".codex/sessions"]
    if not bool(load_settings().get("localhostOnly", True)):
        codex_roots.append(Path.home() / ".cache/omarchy/remote-sessions/codex")
    for root in codex_roots:
        if root.is_dir():
            for jf in root.rglob("*.jsonl"):
                codex_files.setdefault(jf.name, jf)
    all_time_tok = all_time_in = all_time_cache = all_time_out = all_time_prompts = 0
    for jf in codex_files.values():
        max_tot = 0
        last_u = None
        try:
            for ln in jf.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not ln.strip():
                    continue
                o = json.loads(ln)
                if o.get("type") == "event_msg":
                    p = o.get("payload") or {}
                    if p.get("type") == "user_message":
                        all_time_prompts += 1
                    elif p.get("type") == "token_count":
                        tot_u = (p.get("info") or {}).get("total_token_usage") or {}
                        t = int(tot_u.get("total_tokens", 0) or 0)
                        if t >= max_tot:
                            max_tot = t
                            last_u = tot_u
        except Exception:
            pass
        if last_u:
            it = int(last_u.get("input_tokens", 0) or 0)
            ct = int(last_u.get("cached_input_tokens", 0) or 0)
            ot = int(last_u.get("output_tokens", 0) or 0)
            all_time_in += max(0, it - ct)
            all_time_cache += ct
            all_time_out += ot
            all_time_tok += (it + ot)
    # GPT-5-Codex / o3 API pricing: $1.50/1M uncached input, $0.375/1M cached input, $6.00/1M output
    all_time_cost = round((all_time_in * 1.50 + all_time_cache * 0.375 + all_time_out * 6.00) / 1e6, 2)

    record = {
        "schemaVersion": 1,
        "id": "codex",
        "name": "Codex",
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ready": bool(codex_cmd) or len(codex_files) > 0,
        "hasLocalStats": len(codex_files) > 0 or bool(stats.get("totalSessions", 0) > 0),
        "allTimeTokens": all_time_tok,
        "allTimeCostUsd": all_time_cost,
        "allTimeSessions": len(codex_files),
        "allTimePrompts": all_time_prompts,
    }
    record.update(stats)
    record.update(result)
    record["allTimeTokens"] = all_time_tok
    record["allTimeCostUsd"] = all_time_cost
    record["allTimeSessions"] = len(codex_files)
    record["allTimePrompts"] = all_time_prompts
    write_state_file("codex", record)


# =============================================================================
# Grok CLI
# =============================================================================

def collect_grok():
    if not is_provider_enabled("grok", default=False):
        return
    today = dt.datetime.now().date()
    today_str = local_date_str(today)
    recent_dates = recent_date_strings()
    recent = {day: {"date": day, "messageCount": 0} for day in recent_dates}

    grok_session_dirs = [
        Path.home() / ".grok" / "sessions",
        Path.home() / ".cache/omarchy/remote-sessions/grok",
        Path.home() / "migration-staging/.grok/sessions",
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
                            sender = obj.get("sender")
                            ts = obj.get("timestamp")
                            entry_date_str = session_date_str
                            if ts:
                                try:
                                    if isinstance(ts, (int, float)):
                                        entry_date_str = local_date_str(dt.datetime.fromtimestamp(ts / 1000.0 if ts > 1e11 else ts).date())
                                    elif isinstance(ts, str):
                                        entry_date_str = local_date_str(dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).date())
                                except Exception:
                                    pass

                            if sender == "user":
                                total_prompts += 1
                                active_days.add(entry_date_str)
                                if entry_date_str == today_str:
                                    today_prompts += 1
                                    today_sessions.add(session_id)
                            elif sender == "assistant":
                                msg = obj.get("message", "")
                                est_tokens = max(1, len(msg) // 4)
                                model = obj.get("model") or "grok-4.6"
                                b = model_usage.setdefault(model, {
                                    "inputTokens": 0,
                                    "outputTokens": 0,
                                    "cacheReadInputTokens": 0,
                                    "cacheCreationInputTokens": 0,
                                })
                                b["outputTokens"] += est_tokens
                                if entry_date_str in recent:
                                    recent[entry_date_str]["messageCount"] += est_tokens
                                if entry_date_str == today_str:
                                    today_tokens += est_tokens
                                    today_tokens_by_model[model] = today_tokens_by_model.get(model, 0) + est_tokens
                                active_days.add(entry_date_str)
                        except Exception:
                            continue
            except Exception:
                continue

    grok_auth_check = Path.home() / ".grok" / "user-settings.json"
    is_ready = grok_auth_check.is_file()

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
    if not is_provider_enabled("copilot", default=False):
        return
    today = dt.datetime.now().date()
    today_str = local_date_str(today)
    recent_dates = recent_date_strings()
    recent = {day: {"date": day, "messageCount": 0} for day in recent_dates}

    copilot_dirs = [
        Path.home() / ".copilot" / "session-state",
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
        help="Specific agent(s) to collect (agy, agy-sandbox, claude, claude-work, codex, grok, copilot). If omitted, collects all.",
    )
    parser.add_argument("--force", action="store_true", help="Force rescan")
    parser.add_argument("--limits-only", action="store_true", help="Only refresh limits")
    parser.add_argument("--split-profiles", action="store_true", help="Force split-profile emission")
    parser.add_argument("--no-split-profiles", action="store_true", help="Force aggregated single-profile emission")
    args, _ = parser.parse_known_args()

    split_override: bool | None = None
    if args.split_profiles:
        split_override = True
    elif args.no_split_profiles:
        split_override = False

    targets = [a.lower() for a in args.agents] if args.agents else ["agy", "claude", "codex", "grok", "copilot"]

    want_agy = any(t in ("agy", "agy-personal", "agy-org", "all") for t in targets)
    want_agy_sb = True if "agy-sandbox" in targets else (None if want_agy else False)
    want_claude = any(t in ("claude", "all") for t in targets)
    want_claude_work = True if "claude-work" in targets else (None if want_claude else False)

    if want_agy or want_agy_sb or want_claude or want_claude_work:
        collect_agy_and_claude(
            want_agy=want_agy,
            want_agy_sandbox=want_agy_sb,
            want_claude=want_claude,
            want_claude_work=want_claude_work,
            force=args.force,
            split_override=split_override,
        )

    for target in targets:
        if target in ("agy", "agy-personal", "agy-org", "agy-sandbox", "claude", "claude-work", "all"):
            continue
        elif target == "codex":
            collect_codex(force=args.force and ("codex" in args.agents))
        elif target == "grok":
            collect_grok()
        elif target == "copilot":
            collect_copilot()
        else:
            print(f"Unknown agent: {target}", file=sys.stderr)


if __name__ == "__main__":
    main()
