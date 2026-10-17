#!/usr/bin/env python3
"""Modular Claude Code usage, cost, and quota collector for Omarchy.

Supports:
- Out-of-the-box unified `claude` collection on localhost (aggregating all local Claude profiles/dirs).
- Modular split-profile collection (`fiserv-claude` for secondary/work Claude profile + configured
  workspace globs, and `claude` for `~/.claude` primary/personal workspaces) with zero double-counting
  and combined family rollups.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys
import time

# Official Anthropic pricing per 1M tokens: (input, output, cache_read, cache_write)
CLAUDE_COSTS = {
    "claude-opus-4-6": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-5": (5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-4-5": (3.0, 15.0, 0.30, 3.75),
    "claude-haiku-4-5": (0.80, 4.0, 0.08, 1.00),
}

DEFAULT_WORK_PROJECT_PATTERNS: tuple[str, ...] = ()


def _norm_model(m: str | None) -> str:
    if not m:
        return "claude-sonnet-4-6"
    m = m.lower().split("@")[0]
    for k in CLAUDE_COSTS:
        if k in m or k.replace("-", "") in m.replace("-", ""):
            return k
    if "opus" in m:
        return "claude-opus-4-6"
    if "haiku" in m:
        return "claude-haiku-4-5"
    return "claude-sonnet-4-6"


def load_modular_settings() -> dict:
    candidates = [
        Path.home() / ".config/omarchy/agents/profiles.json",
        Path.home() / ".local/state/omarchy/settings/nertwork.agents.json",
        Path.home() / ".config/omarchy/agents.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict) and ("providers" in data or "agents" in data or "enabledAgents" in data):
                    return data
            except Exception:
                pass
    return {}


def is_claude_split_enabled(settings: dict | None = None) -> bool:
    if settings is None:
        settings = load_modular_settings()
    provs = settings.get("providers") or {}
    if isinstance(provs, dict) and "fiserv-claude" in provs:
        return bool(provs["fiserv-claude"].get("enabled", False))
    enabled_list = settings.get("enabledAgents") or settings.get("enabledProviders") or []
    if isinstance(enabled_list, list) and "fiserv-claude" in enabled_list:
        return True
    return False


def resolve_claude_meta(settings: dict | None = None) -> dict:
    if settings is None:
        settings = load_modular_settings()
    provs = settings.get("providers") or {}
    profs = settings.get("profiles") or {}
    c_cfg = (settings.get("agents") or {}).get("claude") or {}
    c_profs = c_cfg.get("profiles") or {}

    work_cfg = {
        **(c_profs.get("fiserv-claude") or {}),
        **(profs.get("fiserv-claude") or {}),
        **(provs.get("fiserv-claude") or {}),
    }
    pers_cfg = {
        **(c_profs.get("claude") or {}),
        **(profs.get("claude") or {}),
        **(provs.get("claude") or {}),
    }

    work_config_dir = str(work_cfg.get("configDir") or "~/.claude-work")
    work_dirs = list(work_cfg.get("dirs") or [work_config_dir])
    pers_dirs = list(pers_cfg.get("dirs") or ["~/.claude"])
    work_patterns = list(
        work_cfg.get("projectPatterns")
        or work_cfg.get("project_patterns")
        or DEFAULT_WORK_PROJECT_PATTERNS
    )

    return {
        "work_label": str(work_cfg.get("label") or "Claude Work"),
        "work_short_label": str(work_cfg.get("shortLabel") or work_cfg.get("label") or "Claude Work"),
        "work_display_name": str(work_cfg.get("displayName") or "Claude Code (Work)"),
        "work_badge": str(work_cfg.get("badge") or work_cfg.get("profile") or "work"),
        "work_profile_key": str(work_cfg.get("profile") or work_cfg.get("badge") or "work"),
        "work_auth_mode": str(work_cfg.get("authMode") or "AWS Bedrock / Enterprise"),
        "work_tier_prefix": str(work_cfg.get("tierPrefix") or "Enterprise"),
        "work_config_dir": work_config_dir,
        "work_auth_help": str(
            work_cfg.get("authHelpText")
            or f"Secondary Claude Code profile ({work_config_dir})."
        ),
        "work_dirs": work_dirs,
        "work_patterns": work_patterns,
        "pers_label": str(pers_cfg.get("label") or "Claude"),
        "pers_short_label": str(pers_cfg.get("shortLabel") or pers_cfg.get("label") or "Claude"),
        "pers_display_name": str(pers_cfg.get("displayName") or "Claude Code (Personal)"),
        "pers_badge": str(pers_cfg.get("badge") or pers_cfg.get("profile") or "personal"),
        "pers_profile_key": str(pers_cfg.get("profile") or pers_cfg.get("badge") or "personal"),
        "pers_dirs": pers_dirs,
    }


def discover_claude_dirs(meta: dict | None = None) -> list[tuple[str, Path]]:
    settings = load_modular_settings()
    if meta is None:
        meta = resolve_claude_meta(settings)
    c_cfg = (settings.get("agents") or {}).get("claude") or {}

    raw: list[tuple[str, Path]] = []
    for d in meta["work_dirs"]:
        raw.append(("fiserv-claude", Path(d).expanduser()))
    for d in meta["pers_dirs"]:
        raw.append(("claude", Path(d).expanduser()))

    work_dir_stem = Path(meta["work_config_dir"]).expanduser().name.lower()
    for d in c_cfg.get("dirs", []) + c_cfg.get("extra_dirs", []):
        p = Path(d).expanduser()
        is_work = (work_dir_stem and work_dir_stem in p.name.lower()) or ("work" in p.name.lower())
        raw.append(("fiserv-claude" if is_work else "claude", p))
    for d in os.environ.get("OMARCHY_CLAUDE_DIRS", "").replace(",", ":").split(":"):
        if d.strip():
            p = Path(d.strip()).expanduser()
            is_work = (work_dir_stem and work_dir_stem in p.name.lower()) or ("work" in p.name.lower())
            raw.append(("fiserv-claude" if is_work else "claude", p))

    remote_hosts_root = Path.home() / ".cache/omarchy/remote-sessions/hosts"
    if remote_hosts_root.exists():
        for host_dir in sorted(remote_hosts_root.iterdir()):
            if not host_dir.is_dir():
                continue
            hname = host_dir.name
            is_work_host = hname in ("netctl1", "netctl2")
            c_root = host_dir / "claude"
            if c_root.exists():
                for sub in sorted(c_root.iterdir()):
                    if sub.is_dir():
                        lbl = "fiserv-claude" if (is_work_host or "work" in sub.name.lower()) else "claude"
                        raw.append((lbl, sub))

    seen: set[str] = set()
    out: list[tuple[str, Path]] = []
    for lbl, p in raw:
        if not p.exists():
            continue
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            out.append((lbl, p))
    return out


def _classify_project_dir(base_label: str, proj_dir_name: str, work_patterns: list[str] | tuple[str, ...] = ()) -> str:
    if base_label == "fiserv-claude":
        return "fiserv-claude"
    lower_name = proj_dir_name.lower()
    for pat in work_patterns:
        if fnmatch.fnmatch(lower_name, pat.lower()):
            return "fiserv-claude"
    return "claude"


def _local_day_and_ts(ts_s: str | None, fallback_mtime: float) -> tuple[str, int]:
    if ts_s and isinstance(ts_s, str):
        try:
            dt = datetime.fromisoformat(ts_s.replace("Z", "+00:00")).astimezone()
            return dt.strftime("%Y-%m-%d"), int(dt.timestamp())
        except Exception:
            pass
    dt = datetime.fromtimestamp(fallback_mtime)
    return dt.strftime("%Y-%m-%d"), int(fallback_mtime)


def _parse_claude_jsonl(jf: Path, base_label: str, work_patterns: list[str] | tuple[str, ...] = ()) -> dict:
    sid = jf.stem
    parent_name = jf.parent.name
    if parent_name == "subagents" and jf.parent.parent.parent.name == "projects":
        proj_folder = jf.parent.parent.name
    else:
        proj_folder = parent_name
    prof = _classify_project_dir(base_label, proj_folder, work_patterns)
    pf_clean = proj_folder
    if pf_clean.startswith("remote-"):
        parts = pf_clean.split("--", 1)
        host_tag = parts[0].replace("remote-", "")
        rem = parts[1] if len(parts) > 1 else ""
        if rem in ("home-jfarr", "home-jfarrz", ""):
            ws_name = host_tag
        else:
            for prefix in ("home-jfarr-projects-", "home-jfarr-", "home-jfarrz-"):
                if rem.startswith(prefix):
                    rem = rem[len(prefix):]
                    break
            ws_name = f"{host_tag}:{rem}" if rem else host_tag
    else:
        rem = pf_clean.lstrip("-")
        for prefix in ("home-jfarr-projects-", "home-jfarr-", "home-jfarrz-"):
            if rem.startswith(prefix):
                rem = rem[len(prefix):]
                break
        ws_name = rem if rem else "home" 

    try:
        mtime = jf.stat().st_mtime
        lines = jf.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return {
            "sid": sid,
            "prof": prof,
            "ws": ws_name,
            "day": datetime.now().strftime("%Y-%m-%d"),
            "ts": 0,
            "tok": 0,
            "it": 0,
            "ot": 0,
            "cr": 0,
            "cw": 0,
            "prompts": 0,
            "cost": 0.0,
            "mod": "claude-sonnet-4-6",
        }

    day_str, last_ts = _local_day_and_ts(None, mtime)
    s_tok = s_it = s_ot = s_cr = s_cw = s_p = 0
    s_cost = 0.0
    s_mod = "claude-sonnet-4-6"
    last_cost_state = None
    msg_usage: dict[str, tuple[int, int, int, int, str]] = {}
    anon_idx = 0

    for ln in lines:
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        ts_s = obj.get("timestamp")
        if ts_s and isinstance(ts_s, str):
            day_str, last_ts = _local_day_and_ts(ts_s, mtime)
        t = obj.get("type")
        if t == "user":
            if not obj.get("isMeta"):
                msg = obj.get("message") or {}
                content = msg.get("content") if isinstance(msg, dict) else None
                is_tool_res = (
                    isinstance(content, list)
                    and len(content) > 0
                    and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
                )
                if not is_tool_res:
                    s_p += 1
        elif t == "assistant":
            msg = obj.get("message") or {}
            raw_m = msg.get("model")
            if raw_m and not str(raw_m).startswith("<"):
                s_mod = _norm_model(raw_m)
            u = msg.get("usage") or {}
            if u:
                it = int(u.get("input_tokens", 0) or 0)
                ot = int(u.get("output_tokens", 0) or 0)
                cr = int(u.get("cache_read_input_tokens", 0) or 0)
                cw = int(u.get("cache_creation_input_tokens", 0) or 0)
                if it or ot or cr or cw:
                    mid = msg.get("id") or obj.get("requestId")
                    if not mid:
                        anon_idx += 1
                        mid = f"anon_{anon_idx}"
                    prev = msg_usage.get(mid)
                    if prev is None or (it + ot + cr + cw) >= (prev[0] + prev[1] + prev[2] + prev[3]):
                        msg_usage[mid] = (it, ot, cr, cw, s_mod)
        elif t == "cost-state":
            last_cost_state = obj

    for it, ot, cr, cw, m_id in msg_usage.values():
        s_it += it
        s_ot += ot
        s_cr += cr
        s_cw += cw
        s_tok += it + ot + cr + cw

    if s_tok == 0 and last_cost_state:
        cs_cost = float(last_cost_state.get("totalCostUSD") or last_cost_state.get("totalCost") or 0.0)
        s_cost = cs_cost
        for raw_m, mv in (last_cost_state.get("modelUsage") or {}).items():
            s_mod = _norm_model(raw_m)
            it = int(mv.get("inputTokens", 0) or 0)
            ot = int(mv.get("outputTokens", 0) or 0)
            cr = int(mv.get("cacheReadInputTokens", 0) or 0)
            cw = int(mv.get("cacheCreationInputTokens", 0) or 0)
            s_it += it
            s_ot += ot
            s_cr += cr
            s_cw += cw
            s_tok += it + ot + cr + cw
        if s_tok == 0 and cs_cost > 0:
            s_ot = int(cs_cost * 40_000)
            s_it = int(cs_cost * 160_000)
            s_tok = s_it + s_ot
        if s_p == 0 and s_tok > 0:
            s_p = max(1, len(lines) // 2)

    if s_tok > 0:
        ci, co, ccr, ccw = CLAUDE_COSTS.get(s_mod, (3.0, 15.0, 0.30, 3.75))
        calc_cost = (s_it * ci + s_ot * co + s_cr * ccr + s_cw * ccw) / 1e6
        if calc_cost > 0:
            s_cost = calc_cost

    return {
        "sid": sid,
        "prof": prof,
        "ws": ws_name,
        "day": day_str,
        "ts": last_ts,
        "tok": s_tok,
        "it": s_it,
        "ot": s_ot,
        "cr": s_cr,
        "cw": s_cw,
        "prompts": s_p,
        "cost": s_cost,
        "mod": s_mod,
    }


def _scan_all_claude_sessions(force: bool = False, meta: dict | None = None) -> list[dict]:
    if meta is None:
        meta = resolve_claude_meta()
    work_patterns = meta.get("work_patterns") or ()
    cache_p = Path.home() / ".cache/omarchy/claude-scan-cache.json"
    cache_p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache = {}
    if cache_p.exists():
        try:
            raw = json.loads(cache_p.read_text(encoding="utf-8"))
            if raw.get("__schema__") == 3:
                cache = raw.get("files", {})
        except Exception:
            cache = {}

    new_cache: dict[str, dict] = {}
    dirty = False
    seen_sids: set[str] = set()
    sessions: list[dict] = []

    for base_label, cdir in discover_claude_dirs(meta):
        proj_d = cdir / "projects"
        if not proj_d.exists():
            continue
        jsonl_paths: list[str] = []
        for root, _, files in os.walk(str(proj_d)):
            for fn in files:
                if fn.endswith(".jsonl"):
                    jsonl_paths.append(f"{root}/{fn}")
        jsonl_paths.sort()
        for f_key in jsonl_paths:
            fn = f_key.rsplit("/", 1)[-1]
            sid = fn[:-6]
            if sid in seen_sids:
                continue
            try:
                st = os.stat(f_key)
            except OSError:
                continue
            seen_sids.add(sid)
            sig = f"{st.st_size}:{int(st.st_mtime)}:{base_label}"
            if f_key in cache and cache[f_key].get("sig") == sig:
                entry = cache[f_key]
            else:
                entry = {"sig": sig, "data": _parse_claude_jsonl(Path(f_key), base_label, work_patterns)}
                dirty = True
            new_cache[f_key] = entry
            sessions.append(entry["data"])

    if dirty or len(new_cache) != len(cache):
        try:
            cache_p.write_text(json.dumps({"__schema__": 3, "files": new_cache}), encoding="utf-8")
            cache_p.chmod(0o600)
        except Exception:
            pass

    return sessions


def _get_personal_claude_limits(force: bool = False) -> dict:
    """Read personal Claude OAuth limits from cache without blocking on network timeouts."""
    limits_cache = Path.home() / ".cache/omarchy/agent-usage/claude-limits.json"
    creds_path = Path.home() / ".claude/.credentials.json"
    tier = "Pro"
    ready = creds_path.exists() or (Path.home() / ".claude/projects").exists()
    if creds_path.exists():
        try:
            sub = ((json.loads(creds_path.read_text(encoding="utf-8")).get("claudeAiOauth") or {}).get("subscriptionType") or "pro").capitalize()
            tier = sub
        except Exception:
            pass

    limits = []
    if limits_cache.exists():
        try:
            d = json.loads(limits_cache.read_text(encoding="utf-8"))
            if isinstance(d.get("limits"), list):
                limits = d["limits"]
            age = time.time() - limits_cache.stat().st_mtime
            if (force and age > 120) or age > 600:
                bin_p = Path("/usr/share/omarchy/bin/omarchy-agent-usage-claude")
                if bin_p.exists():
                    subprocess.Popen(
                        [str(bin_p)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
        except Exception:
            pass
    return {"tier": tier, "limits": limits, "ready": ready}


def _build_claude_record(
    record_id: str,
    profile_key: str,
    profile_name: str,
    display_name: str,
    short_label: str,
    badge: str,
    target_prof: str | None,
    sessions: list[dict],
    all_prof_breakdown: list[dict],
    family_summary: dict,
    personal_limits_info: dict,
    aggregated: bool,
) -> dict:
    now = datetime.now()
    today_s = now.strftime("%Y-%m-%d")
    cut_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    cut_7d = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    cut_5h = int((now - timedelta(hours=5)).timestamp())

    day_stats: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "prompts": 0, "sessions": set(), "cost": 0.0})
    mod_stats_30d: dict[str, list] = defaultdict(lambda: [0, 0, 0, 0, 0.0])
    mod_stats_all: dict[str, list] = defaultdict(lambda: [0, 0, 0, 0, 0.0])
    ws_stats: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "cost": 0.0, "prompts": 0, "sessions": set(), "last": ""})
    ws_stats_all: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "cost": 0.0, "prompts": 0, "sessions": set(), "last": ""})

    sessions_30d: set[str] = set()
    sessions_7d: set[str] = set()
    all_sids: set[str] = set()
    all_time_tokens = 0
    all_time_cost = 0.0
    all_time_prompts = 0
    tok_5h = 0

    for s in sessions:
        if target_prof is not None and s["prof"] != target_prof:
            continue
        sid = s["sid"]
        all_sids.add(sid)
        s_tok = s["tok"]
        s_p = s["prompts"]
        s_cost = s["cost"]
        s_mod = s["mod"]
        s_it, s_ot, s_cr, s_cw = s["it"], s["ot"], s["cr"], s["cw"]
        day_str = s["day"]
        ws_name = s["ws"]

        if s_tok > 0 or s_p > 0:
            all_time_tokens += s_tok
            all_time_cost += s_cost
            all_time_prompts += s_p
            if s_tok > 0:
                mod_stats_all[s_mod][0] += s_it
                mod_stats_all[s_mod][1] += s_ot
                mod_stats_all[s_mod][2] += s_cr
                mod_stats_all[s_mod][3] += s_cw
                mod_stats_all[s_mod][4] += s_cost
            ws_stats_all[ws_name]["tokens"] += s_tok
            ws_stats_all[ws_name]["cost"] += s_cost
            ws_stats_all[ws_name]["prompts"] += s_p
            ws_stats_all[ws_name]["sessions"].add(sid)
            if day_str > ws_stats_all[ws_name]["last"]:
                ws_stats_all[ws_name]["last"] = day_str

            day_stats[day_str]["tokens"] += s_tok
            day_stats[day_str]["prompts"] += s_p
            day_stats[day_str]["sessions"].add(sid)
            day_stats[day_str]["cost"] += s_cost

            if s.get("ts", 0) >= cut_5h:
                tok_5h += s_tok

            if day_str >= cut_30d:
                sessions_30d.add(sid)
                if day_str >= cut_7d:
                    sessions_7d.add(sid)
                if s_tok > 0:
                    mod_stats_30d[s_mod][0] += s_it
                    mod_stats_30d[s_mod][1] += s_ot
                    mod_stats_30d[s_mod][2] += s_cr
                    mod_stats_30d[s_mod][3] += s_cw
                    mod_stats_30d[s_mod][4] += s_cost
                ws_stats[ws_name]["tokens"] += s_tok
                ws_stats[ws_name]["cost"] += s_cost
                ws_stats[ws_name]["prompts"] += s_p
                ws_stats[ws_name]["sessions"].add(sid)
                if day_str > ws_stats[ws_name]["last"]:
                    ws_stats[ws_name]["last"] = day_str

    tot_tokens_30d = sum(v["tokens"] for d, v in day_stats.items() if d >= cut_30d)
    tot_prompts_30d = sum(v["prompts"] for d, v in day_stats.items() if d >= cut_30d)
    tot_cost_30d = sum(v["cost"] for d, v in day_stats.items() if d >= cut_30d)
    tok_7d = sum(v["tokens"] for d, v in day_stats.items() if d >= cut_7d)
    prompts_7d = sum(v["prompts"] for d, v in day_stats.items() if d >= cut_7d)
    cost_7d = sum(v["cost"] for d, v in day_stats.items() if d >= cut_7d)
    today_tokens = day_stats[today_s]["tokens"]
    today_prompts = day_stats[today_s]["prompts"]
    today_cost = day_stats[today_s]["cost"]
    today_sessions = len(day_stats[today_s]["sessions"])

    active_dates = sorted(d for d, v in day_stats.items() if d >= cut_30d and (v["tokens"] > 0 or v["prompts"] > 0))
    last_14_days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
    recent_days = [
        {
            "date": d,
            "tokens": day_stats[d]["tokens"],
            "messageCount": day_stats[d]["tokens"],
            "prompts": day_stats[d]["prompts"],
            "sessions": len(day_stats[d]["sessions"]),
            "costUsd": round(day_stats[d]["cost"], 2),
            "costUSD": round(day_stats[d]["cost"], 2),
        }
        for d in sorted(set(last_14_days) | {d for d in day_stats.keys() if d >= cut_30d})[-14:]
    ]

    def _format_mod_map(m_stats: dict, denom_tok: int) -> dict:
        out_m = {}
        for m, (it, ot, cr, cw, cost) in sorted(m_stats.items(), key=lambda x: -(x[1][0] + x[1][1] + x[1][2] + x[1][3])):
            tot = it + ot + cr + cw
            if tot <= 0 and cost <= 0:
                continue
            out_m[m] = {
                "inputTokens": it,
                "outputTokens": ot,
                "cacheReadTokens": cr,
                "cacheReadInputTokens": cr,
                "cacheCreationInputTokens": cw,
                "totalTokens": tot,
                "costUsd": round(cost, 2),
                "costUSD": round(cost, 2),
                "sharePct": round(tot * 100.0 / denom_tok, 1) if denom_tok else 0.0,
            }
        return out_m

    model_usage = _format_mod_map(mod_stats_30d, tot_tokens_30d)
    all_time_model_usage = _format_mod_map(mod_stats_all, all_time_tokens)

    active_model = "claude-sonnet-4-6"
    if model_usage:
        active_model = next(iter(model_usage.keys()))
    elif all_time_model_usage:
        active_model = next(iter(all_time_model_usage.keys()))

    scoped_breakdown = [
        pb for pb in all_prof_breakdown if target_prof is None or pb["profileId"] == record_id
    ]
    if aggregated and len(scoped_breakdown) > 1:
        projects_breakdown_field = [
            {
                "project": "all-claude-profiles",
                "profileId": "claude",
                "scope": "claude_profile",
                "tokens30d": tot_tokens_30d,
                "tokens7d": tok_7d,
                "tokensToday": today_tokens,
                "allTimeTokens": all_time_tokens,
                "requests30d": tot_prompts_30d,
                "sessions": len(sessions_30d),
                "allTimeSessions": len(all_sids),
                "costUSD": round(tot_cost_30d, 2),
                "costUsd": round(tot_cost_30d, 2),
                "localCostUsd30d": round(tot_cost_30d, 2),
                "localCostUsd7d": round(cost_7d, 2),
                "localCostUsdToday": round(today_cost, 2),
                "allTimeCostUsd": round(all_time_cost, 2),
                "sharePct": 100.0,
            }
        ]
    else:
        projects_breakdown_field = scoped_breakdown

    if record_id == "fiserv-claude":
        meta = resolve_claude_meta()
        auth_mode = meta["work_auth_mode"]
        five_pct = min(100.0, round(tok_5h * 100.0 / 50_000_000, 1))
        seven_pct = min(100.0, round(tok_7d * 100.0 / 500_000_000, 1))
        limits = [
            {"label": "Session (5-hour)", "percent": round(five_pct / 100.0, 4), "resetsAt": ""},
            {"label": "Weekly (7-day)", "percent": round(seven_pct / 100.0, 4), "resetsAt": ""},
        ]
        tier_prefix = meta["work_tier_prefix"]
        tier_label = f"{tier_prefix} · Today ${today_cost:,.2f} · 7d ${cost_7d:,.2f} · 30d ${tot_cost_30d:,.2f}"
        work_cfg_path = Path(meta["work_config_dir"]).expanduser()
        is_ready = work_cfg_path.exists() or len(all_sids) > 0
        auth_help = meta["work_auth_help"]
    else:
        auth_mode = "Claude Pro OAuth"
        limits = personal_limits_info.get("limits", [])
        base_tier = personal_limits_info.get("tier") or "Pro"
        if tot_cost_30d > 0 or aggregated:
            tier_label = f"{base_tier} · Today ${today_cost:,.2f} · 7d ${cost_7d:,.2f} · 30d ${tot_cost_30d:,.2f}"
        elif all_time_cost > 0:
            tier_label = f"{base_tier} · 30d $0.00 · All-Time ${all_time_cost:,.2f} ({all_time_tokens / 1e6:.1f}M tok)"
        else:
            tier_label = f"{base_tier} · Today $0.00 · 30d $0.00"
        is_ready = bool(personal_limits_info.get("ready")) or len(all_sids) > 0
        auth_help = "Personal Claude Code profile (~/.claude)."

    ws_source = ws_stats if ws_stats else ws_stats_all
    ws_list = [
        {
            "workspace": k,
            "tokens": v["tokens"],
            "costUsd": round(v["cost"], 2),
            "prompts": v["prompts"],
            "sessions": len(v["sessions"]),
            "lastActive": v["last"],
        }
        for k, v in sorted(ws_source.items(), key=lambda x: -x[1]["cost"])[:10]
    ]

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "schemaVersion": 1,
        "id": record_id,
        "provider": record_id,
        "family": "claude",
        "group": "claude",
        "profile": profile_key,
        "profileId": record_id,
        "profileLabel": badge,
        "name": profile_name,
        "shortLabel": short_label,
        "displayName": display_name,
        "badge": badge,
        "executionScope": "multi-host",
        "localhostOnly": False,
        "aggregated": aggregated,
        "status": "online",
        "scope": "account",
        "updatedAt": now_iso,
        "fetchedAt": now_iso,
        "ready": is_ready,
        "hasLocalStats": len(all_sids) > 0 or is_ready,
        "hasPromptStats": True,
        "activeModel": active_model,
        "authMode": auth_mode,
        "tierLabel": tier_label,
        "usageStatusText": "",
        "authHelpText": auth_help,
        "limits": limits,
        "costUsd": round(tot_cost_30d, 2),
        "thirtyDayCostUsd": round(tot_cost_30d, 2),
        "sevenDayCostUsd": round(cost_7d, 2),
        "todayCostUsd": round(today_cost, 2),
        "allTimeCostUsd": round(all_time_cost, 2),
        "todayPrompts": today_prompts,
        "sevenDayPrompts": prompts_7d,
        "todayTokens": today_tokens,
        "todayTotalTokens": today_tokens,
        "todaySessions": today_sessions,
        "sevenDaySessions": len(sessions_7d),
        "sevenDayTokens": tok_7d,
        "thirtyDayTokens": tot_tokens_30d,
        "totalTokens30d": tot_tokens_30d,
        "totalTokens": tot_tokens_30d,
        "allTimeTokens": all_time_tokens,
        "totalPrompts30d": tot_prompts_30d,
        "totalPrompts": tot_prompts_30d,
        "allTimePrompts": all_time_prompts,
        "totalSessions30d": len(sessions_30d),
        "totalSessions": len(sessions_30d) if len(sessions_30d) > 0 else len(all_sids),
        "allTimeSessions": len(all_sids),
        "totalConversations": len(all_sids),
        "activeDays": len(active_dates),
        "activeDates": active_dates,
        "recentDays": recent_days,
        "modelUsage": model_usage,
        "allTimeModelUsage": all_time_model_usage,
        "projectsBreakdown": projects_breakdown_field,
        "allProjectsBreakdown": all_prof_breakdown,
        "profilesSummary": all_prof_breakdown,
        "aggregation": family_summary,
        "groupTotals": family_summary,
        "workspaceUsage": ws_list,
    }


def collect_claude_profiles(force: bool = False, split_profiles: bool | None = None) -> dict[str, dict]:
    """Scan all local Claude sessions once and build both split (`fiserv-claude`, `claude`) and combined (`all`) records."""
    settings = load_modular_settings()
    meta = resolve_claude_meta(settings)
    if split_profiles is None:
        split_profiles = is_claude_split_enabled(settings)

    sessions = _scan_all_claude_sessions(force=force, meta=meta)
    personal_limits_info = _get_personal_claude_limits(force=force)

    now = datetime.now()
    today_s = now.strftime("%Y-%m-%d")
    cut_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    cut_7d = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    prof_stats: dict[str, dict] = {
        "fiserv-claude": {
            "project": "fiserv-claude",
            "profileId": "fiserv-claude",
            "label": meta["work_label"],
            "tokens30d": 0,
            "tokens7d": 0,
            "tokensToday": 0,
            "allTimeTokens": 0,
            "requests30d": 0,
            "requestsToday": 0,
            "allTimeRequests": 0,
            "cost30d": 0.0,
            "cost7d": 0.0,
            "costToday": 0.0,
            "allTimeCost": 0.0,
            "sessions30d": 0,
            "sessionsToday": 0,
            "allTimeSessions": 0,
        },
        "claude": {
            "project": "personal",
            "profileId": "claude",
            "label": "Claude (Personal)",
            "tokens30d": 0,
            "tokens7d": 0,
            "tokensToday": 0,
            "allTimeTokens": 0,
            "requests30d": 0,
            "requestsToday": 0,
            "allTimeRequests": 0,
            "cost30d": 0.0,
            "cost7d": 0.0,
            "costToday": 0.0,
            "allTimeCost": 0.0,
            "sessions30d": 0,
            "sessionsToday": 0,
            "allTimeSessions": 0,
        },
    }

    for s in sessions:
        p = s["prof"] if s["prof"] in prof_stats else "claude"
        ps = prof_stats[p]
        tok = s["tok"]
        pr = s["prompts"]
        cost = s["cost"]
        day = s["day"]
        if tok > 0 or pr > 0:
            ps["allTimeTokens"] += tok
            ps["allTimeRequests"] += pr
            ps["allTimeCost"] += cost
            ps["allTimeSessions"] += 1
            if day >= cut_30d:
                ps["tokens30d"] += tok
                ps["requests30d"] += pr
                ps["cost30d"] += cost
                ps["sessions30d"] += 1
                if day >= cut_7d:
                    ps["tokens7d"] += tok
                    ps["cost7d"] += cost
                if day == today_s:
                    ps["tokensToday"] += tok
                    ps["requestsToday"] += pr
                    ps["costToday"] += cost
                    ps["sessionsToday"] += 1

    tot_30d_all = sum(v["tokens30d"] for v in prof_stats.values())
    all_prof_breakdown = []
    for k in ("fiserv-claude", "claude"):
        v = prof_stats[k]
        all_prof_breakdown.append(
            {
                "project": v["project"],
                "profileId": v["profileId"],
                "label": v["label"],
                "scope": "claude_profile",
                "tokens30d": v["tokens30d"],
                "tokens7d": v["tokens7d"],
                "tokensToday": v["tokensToday"],
                "localTokens30d": v["tokens30d"],
                "localTokens7d": v["tokens7d"],
                "localTokensToday": v["tokensToday"],
                "allTimeTokens": v["allTimeTokens"],
                "requests30d": v["requests30d"],
                "requestsToday": v["requestsToday"],
                "allTimeRequests": v["allTimeRequests"],
                "sessions": v["sessions30d"],
                "localSessions30d": v["sessions30d"],
                "sessionsToday": v["sessionsToday"],
                "allTimeSessions": v["allTimeSessions"],
                "costUSD": round(v["cost30d"], 2),
                "costUsd": round(v["cost30d"], 2),
                "localCostUsd30d": round(v["cost30d"], 2),
                "localCostUsd7d": round(v["cost7d"], 2),
                "localCostUsdToday": round(v["costToday"], 2),
                "allTimeCostUsd": round(v["allTimeCost"], 2),
                "sharePct": round(v["tokens30d"] * 100.0 / tot_30d_all, 1) if tot_30d_all else 0.0,
            }
        )

    family_summary = {
        "family": "claude",
        "executionScope": "multi-host",
        "splitProfiles": bool(split_profiles),
        "tokens30d": sum(pb["tokens30d"] for pb in all_prof_breakdown),
        "tokens7d": sum(pb["tokens7d"] for pb in all_prof_breakdown),
        "tokensToday": sum(pb["tokensToday"] for pb in all_prof_breakdown),
        "allTimeTokens": sum(pb["allTimeTokens"] for pb in all_prof_breakdown),
        "costUsd30d": round(sum(pb["localCostUsd30d"] for pb in all_prof_breakdown), 2),
        "costUsd7d": round(sum(pb["localCostUsd7d"] for pb in all_prof_breakdown), 2),
        "costUsdToday": round(sum(pb["localCostUsdToday"] for pb in all_prof_breakdown), 2),
        "allTimeCostUsd": round(sum(pb["allTimeCostUsd"] for pb in all_prof_breakdown), 2),
        "prompts30d": sum(pb["requests30d"] for pb in all_prof_breakdown),
        "promptsToday": sum(pb["requestsToday"] for pb in all_prof_breakdown),
        "allTimePrompts": sum(pb["allTimeRequests"] for pb in all_prof_breakdown),
        "sessions30d": sum(pb["localSessions30d"] for pb in all_prof_breakdown),
        "sessionsToday": sum(pb["sessionsToday"] for pb in all_prof_breakdown),
        "allTimeSessions": sum(pb["allTimeSessions"] for pb in all_prof_breakdown),
        "profiles": [
            {
                "id": pb["profileId"],
                "project": pb["project"],
                "tokens30d": pb["tokens30d"],
                "tokens7d": pb["tokens7d"],
                "tokensToday": pb["tokensToday"],
                "allTimeTokens": pb["allTimeTokens"],
                "costUsd30d": pb["localCostUsd30d"],
                "costUsd7d": pb["localCostUsd7d"],
                "costUsdToday": pb["localCostUsdToday"],
                "allTimeCostUsd": pb["allTimeCostUsd"],
                "prompts30d": pb["requests30d"],
                "sessions30d": pb["localSessions30d"],
                "allTimeSessions": pb["allTimeSessions"],
            }
            for pb in all_prof_breakdown
        ],
    }

    rec_fiserv = _build_claude_record(
        record_id="fiserv-claude",
        profile_key=meta["work_profile_key"],
        profile_name=meta["work_label"],
        display_name=meta["work_display_name"],
        short_label=meta["work_short_label"],
        badge=meta["work_badge"],
        target_prof="fiserv-claude",
        sessions=sessions,
        all_prof_breakdown=all_prof_breakdown,
        family_summary=family_summary,
        personal_limits_info=personal_limits_info,
        aggregated=False,
    )
    rec_personal = _build_claude_record(
        record_id="claude",
        profile_key=meta["pers_profile_key"],
        profile_name=meta["pers_label"],
        display_name=meta["pers_display_name"],
        short_label=meta["pers_short_label"],
        badge=meta["pers_badge"],
        target_prof="claude",
        sessions=sessions,
        all_prof_breakdown=all_prof_breakdown,
        family_summary=family_summary,
        personal_limits_info=personal_limits_info,
        aggregated=False,
    )
    rec_all = (
        rec_personal
        if split_profiles
        else _build_claude_record(
            record_id="claude",
            profile_key="all",
            profile_name="Claude Code",
            display_name="Claude Code",
            short_label="Claude",
            badge="all",
            target_prof=None,
            sessions=sessions,
            all_prof_breakdown=all_prof_breakdown,
            family_summary=family_summary,
            personal_limits_info=personal_limits_info,
            aggregated=True,
        )
    )

    return {
        "fiserv-claude": rec_fiserv,
        "claude": rec_personal if split_profiles else rec_all,
        "claude-personal": rec_personal,
        "all": rec_all,
        "summary": family_summary,
    }


def collect_claude_data(force: bool = False, profile: str | None = None, split_profiles: bool | None = None) -> dict:
    if profile == "all":
        split_profiles = False
    profiles = collect_claude_profiles(force=force, split_profiles=split_profiles)
    if profile in ("fiserv-claude", "fiserv"):
        return profiles["fiserv-claude"]
    if profile in ("claude-personal", "personal"):
        return profiles["claude-personal"]
    if profile == "all":
        return profiles["all"]
    return profiles["claude"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Claude Code usage telemetry.")
    parser.add_argument("--force", action="store_true", help="Force refresh")
    parser.add_argument("--profile", default=None, help="Profile to emit (claude, fiserv-claude, all)")
    parser.add_argument("--split-profiles", action="store_true", help="Force split-profile mode")
    args, _ = parser.parse_known_args()

    split = True if (args.split_profiles or args.profile in ("fiserv-claude", "fiserv", "personal", "claude-personal")) else None
    out = collect_claude_data(force=args.force, profile=args.profile, split_profiles=split)
    print(json.dumps(out, indent=2))
