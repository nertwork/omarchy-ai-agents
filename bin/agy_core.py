#!/usr/bin/env python3
"""Modular AGY (Antigravity) usage, cost, and quota collector for Omarchy.

Supports:
- Out-of-the-box unified `agy` collection on localhost (aggregating all local AGY profiles/projects).
- Modular split-profile collection (`agy` for primary GCP project and `agy-sandbox` for sandbox GCP project)
  with zero double-counting, parent-child subagent tree attribution, and combined family rollups.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import sqlite3

PROFILE_ALLOWED_HOSTS: dict[str, tuple[str, ...]] = {
    "agy": ("localhost",),
    "agy-personal": ("localhost",),
    "agy-org": ("localhost",),
    "agy-sandbox": ("localhost",),
}

HOST_ALLOWED_PROFILES: dict[str, tuple[str, ...]] = {
    "localhost": ("agy-personal", "agy-org", "agy", "agy-sandbox"),
    "net-node-1": ("agy", "agy-sandbox"),
    "net-node-2": ("agy", "agy-sandbox"),
    "server-1": ("agy-personal", "agy-sandbox"),
    "gpu-node": ("agy-personal", "agy-sandbox"),
}
import subprocess
import sys
import time
import urllib.parse
import urllib.request

MODEL_MAP = {
    "MODEL_GOOGLE_GEMINI_4_ARGON": "gemini-4-argon",
    "MODEL_GOOGLE_GEMINI_PRO_3_1": "gemini-3.1-pro-high",
    "MODEL_GOOGLE_GEMINI_PRO_3_1_LOW": "gemini-3.1-pro-low",
    "MODEL_GOOGLE_GEMINI_PRO_3": "gemini-3-pro",
    "MODEL_GOOGLE_GEMINI_FLASH_3_8": "gemini-3.8-flash",
    "MODEL_GOOGLE_GEMINI_FLASH_3_7": "gemini-3.7-flash",
    "MODEL_GOOGLE_GEMINI_FLASH_3_6": "gemini-3.6-flash",
    "MODEL_GOOGLE_GEMINI_FLASH_3_5": "gemini-3.5-flash",
    "MODEL_GOOGLE_GEMINI_FLASH_3": "gemini-3-flash",
    "MODEL_GOOGLE_GEMINI_FLASH_LITE_3": "gemini-3-flash-lite",
    "MODEL_CLAUDE_4_7_OPUS": "claude-opus-4-7",
    "MODEL_CLAUDE_4_6_OPUS": "claude-opus-4-6",
    "MODEL_CLAUDE_4_6_SONNET": "claude-sonnet-4-6",
    "MODEL_CLAUDE_4_5_SONNET_THINKING": "claude-sonnet-4-5",
    "MODEL_CLAUDE_4_5_OPUS_THINKING": "claude-opus-4-5",
    "MODEL_CLAUDE_4_5_SONNET": "claude-sonnet-4-5",
    "MODEL_CLAUDE_4_5_HAIKU": "claude-haiku-4-5",
}

# Best-guess Vertex AI / Anthropic pricing per 1M tokens: (uncached_input, output, cache_read)
COST_PER_M = {
    "gemini-4-argon": (1.25, 10.0, 0.125),
    "gemini-4-argon-high": (1.25, 10.0, 0.125),
    "gemini-4-argon-medium": (1.25, 10.0, 0.125),
    "gemini-4-argon-low": (1.25, 10.0, 0.125),
    "gemini-3.1-pro": (1.25, 10.0, 0.125),
    "gemini-3.1-pro-high": (1.25, 10.0, 0.125),
    "gemini-3.1-pro-low": (1.25, 10.0, 0.125),
    "gemini-3.1-pro-preview": (1.25, 10.0, 0.125),
    "gemini-3-pro": (1.25, 10.0, 0.125),
    "gemini-3-pro-preview": (1.25, 10.0, 0.125),
    "gemini-2.5-pro": (1.25, 10.0, 0.125),
    "gemini-3.8-flash": (0.15, 0.60, 0.015),
    "gemini-3.8-flash-high": (0.15, 0.60, 0.015),
    "gemini-3.8-flash-medium": (0.15, 0.60, 0.015),
    "gemini-3.8-flash-low": (0.15, 0.60, 0.015),
    "gemini-3.7-flash": (0.15, 0.60, 0.015),
    "gemini-3.7-flash-high": (0.15, 0.60, 0.015),
    "gemini-3.7-flash-medium": (0.15, 0.60, 0.015),
    "gemini-3.7-flash-low": (0.15, 0.60, 0.015),
    "gemini-3.6-flash": (0.15, 0.60, 0.015),
    "gemini-3.6-flash-high": (0.15, 0.60, 0.015),
    "gemini-3.6-flash-medium": (0.15, 0.60, 0.015),
    "gemini-3.6-flash-low": (0.15, 0.60, 0.015),
    "gemini-3.5-flash": (0.15, 0.60, 0.015),
    "gemini-3-flash": (0.15, 0.60, 0.015),
    "gemini-3-flash-preview": (0.15, 0.60, 0.015),
    "gemini-2.5-flash": (0.15, 0.60, 0.015),
    "gemini-2.0-flash-001": (0.15, 0.60, 0.015),
    "gemini-3.5-flash-lite": (0.075, 0.30, 0.0075),
    "gemini-3.1-flash-lite": (0.075, 0.30, 0.0075),
    "gemini-3.1-flash-lite-preview": (0.075, 0.30, 0.0075),
    "gemini-3-flash-lite": (0.075, 0.30, 0.0075),
    "gemini-2.5-flash-lite": (0.075, 0.30, 0.0075),
    "claude-opus-4-7": (5.0, 25.0, 0.50),
    "claude-opus-4-6": (5.0, 25.0, 0.50),
    "claude-opus-4-5": (5.0, 25.0, 0.50),
    "claude-fable-5": (5.0, 25.0, 0.50),
    "claude-fable-5-1": (5.0, 25.0, 0.50),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-sonnet-4-5": (3.0, 15.0, 0.30),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
    "claude-3-5-haiku": (0.80, 4.0, 0.08),
}

# Match only Vertex AI / Google Cloud resource paths (`projects/<id>/locations/...`)
# so local filesystem paths like `/home/user/projects/foo/` are never misattributed.
PROJ_RE = re.compile(r"projects/([a-zA-Z0-9_-]+)/locations/")
PARENT_RE = re.compile(r'parent"?[,\s]+id:\s*"?([0-9a-f-]{36})')


import functools

_DAY_CACHE: dict[int, str] = {}


@functools.lru_cache(maxsize=8192)
def _bucket_to_day(b: int) -> str:
    return datetime.fromtimestamp(b * 900).strftime("%Y-%m-%d")


def _ts_to_day(ts: int) -> str:
    b = int(ts) // 900
    d = _DAY_CACHE.get(b)
    if d is None:
        d = _bucket_to_day(b)
        _DAY_CACHE[b] = d
    return d


@functools.lru_cache(maxsize=256)
def _cost_rates(model_id: str) -> tuple[float, float, float]:
    m = (model_id or "").lower()
    if m in COST_PER_M:
        return COST_PER_M[m]
    if "flash-lite" in m or "lite" in m:
        return (0.075, 0.30, 0.0075)
    if "flash" in m:
        return (0.15, 0.60, 0.015)
    if "haiku" in m:
        return (0.80, 4.0, 0.08) if "3-" in m or "3.5" in m else (1.0, 5.0, 0.10)
    if "sonnet" in m:
        return (3.0, 15.0, 0.30)
    if "opus" in m or "fable" in m:
        return (5.0, 25.0, 0.50)
    return (1.25, 10.0, 0.125)


def _compact_session_events(events: list, now_ts: int) -> list:
    """Drop unused tool/sub events and coalesce prompt/usage events by day (and 5-min window for recent 24h)."""
    cutoff_24h = now_ts - 86400
    p_by_day: dict[str, list] = {}
    u_buckets: dict[tuple[str, int, str], list] = {}
    for ev in events:
        if len(ev) < 6:
            continue
        ts, et, mod, it, ot, ct = ev[:6]
        if not ts:
            continue
        if et == "p":
            cnt = it if it > 0 else 1
            day = _ts_to_day(ts)
            prev = p_by_day.get(day)
            if prev is None:
                p_by_day[day] = [ts, "p", "", cnt, 0, 0]
            else:
                if ts > prev[0]:
                    prev[0] = ts
                prev[3] += cnt
        elif et == "u":
            day = _ts_to_day(ts)
            b_key = (day, 0 if ts < cutoff_24h else (int(ts) // 300), mod)
            prev = u_buckets.get(b_key)
            if prev is None:
                u_buckets[b_key] = [ts, "u", mod, it, ot, ct]
            else:
                if ts > prev[0]:
                    prev[0] = ts
                prev[3] += it
                prev[4] += ot
                prev[5] += ct
    out = list(p_by_day.values()) + list(u_buckets.values())
    out.sort(key=lambda x: x[0])
    return out


def _varint(b: bytes, p: int) -> tuple[int, int]:
    v = s = 0
    while p < len(b):
        c = b[p]
        p += 1
        v |= (c & 0x7F) << s
        if not (c & 0x80):
            return v, p
        s += 7
    return v, p


def _pb(b: bytes) -> dict[int, list]:
    if not isinstance(b, (bytes, bytearray, memoryview)):
        return defaultdict(list)
    p = 0
    out: dict[int, list] = defaultdict(list)
    while p < len(b):
        try:
            t, p = _varint(b, p)
            f, w = t >> 3, t & 7
            if f == 0:
                break
            if w == 0:
                v, p = _varint(b, p)
                out[f].append(v)
            elif w == 2:
                l, p = _varint(b, p)
                out[f].append(b[p : p + l])
                p += l
            elif w == 1:
                p += 8
            elif w == 5:
                p += 4
            else:
                break
        except Exception:
            break
    return out


def _s(b) -> str:
    return b.decode("utf-8", errors="ignore") if isinstance(b, bytes) else str(b)


_MODULAR_SETTINGS_CACHE: dict | None = None
_AGY_META_CACHE: dict | None = None


def load_modular_settings() -> dict:
    """Load modular plugin settings from config.json, profiles.json, state settings, or manifest defaults."""
    global _MODULAR_SETTINGS_CACHE
    if _MODULAR_SETTINGS_CACHE is not None:
        return _MODULAR_SETTINGS_CACHE
    candidates = [
        Path.home() / ".config/omarchy/agents.json",
        Path.home() / ".local/state/omarchy/settings/nertwork.agents.json",
        Path.home() / ".config/omarchy/agents/profiles.json",
        Path.home() / ".config/omarchy/agents/config.json",
    ]
    merged: dict = {}
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict) and isinstance(merged.get(k), dict):
                            merged[k] = {**merged[k], **v}
                        else:
                            merged[k] = v
            except Exception:
                pass
    _MODULAR_SETTINGS_CACHE = merged
    return _MODULAR_SETTINGS_CACHE


ENTERPRISE_WORKSPACES = {
    "Work",
    "work",
    "enterprise-ai-ops",
    "work-infra",
    "corp-cloud",
    "net-automation",
    "dns-tools",
    "quota-alerts",
    "net-monitor",
    "enc",
}

ORG_WORKSPACES = {
    "org-ai-ops",
    "org",
    "org-cloud",
    "team-cloud",
}


@functools.lru_cache(maxsize=256)
def _is_org_workspace(ws: str | None) -> bool:
    if not ws:
        return False
    w = ws.strip()
    cfg = load_modular_settings()
    custom_org = set(cfg.get("orgWorkspaces") or [])
    if w in ORG_WORKSPACES or w in custom_org:
        return True
    wl = w.lower()
    pats = tuple(cfg.get("orgPatterns") or ()) + ("org", "org-cloud", "team-cloud")
    return any(str(k).lower() in wl for k in pats)


@functools.lru_cache(maxsize=256)
def _is_enterprise_workspace(ws: str | None) -> bool:
    if not ws:
        return False
    w = ws.strip()
    if _is_org_workspace(w):
        return False
    cfg = load_modular_settings()
    custom_work = set(cfg.get("workWorkspaces") or [])
    if w in ENTERPRISE_WORKSPACES or w in custom_work:
        return True
    wl = w.lower()
    pats = tuple(cfg.get("workPatterns") or ()) + ("enterprise", "work", "corp", "net-node")
    return any(str(k).lower() in wl for k in pats)


def is_agy_split_enabled(settings: dict | None = None) -> bool:
    if settings is None:
        settings = load_modular_settings()
    provs = settings.get("providers") or {}
    if isinstance(provs, dict):
        if "agy-sandbox" in provs and bool(provs["agy-sandbox"].get("enabled", False)):
            return True
        if "agy-personal" in provs and bool(provs["agy-personal"].get("enabled", False)):
            return True
        if "agy-org" in provs and bool(provs["agy-org"].get("enabled", False)):
            return True
    enabled_list = settings.get("enabledAgents") or settings.get("enabledProviders") or []
    if isinstance(enabled_list, list) and any(k in enabled_list for k in ("agy-sandbox", "agy-personal", "agy-org")):
        return True
    return False


def resolve_agy_meta(settings: dict | None = None) -> dict:
    global _AGY_META_CACHE
    if settings is None and _AGY_META_CACHE is not None:
        return _AGY_META_CACHE
    if settings is None:
        settings = load_modular_settings()
    provs = settings.get("providers") or {}
    profs = settings.get("profiles") or {}
    agy_p = {**(profs.get("agy") or {}), **(provs.get("agy") or {})}
    sb_p = {**(profs.get("agy-sandbox") or {}), **(provs.get("agy-sandbox") or {})}
    pers_p = {**(profs.get("agy-personal") or {}), **(provs.get("agy-personal") or {})}
    org_p = {**(profs.get("agy-org") or {}), **(provs.get("agy-org") or {})}

    def _read_dir_proj(d: Path) -> str:
        sp = d / "settings.json"
        if sp.exists():
            try:
                return str(json.loads(sp.read_text(encoding="utf-8")).get("gcp", {}).get("project") or "").strip()
            except Exception:
                pass
        return ""

    pri_proj = str(agy_p.get("gcpProject") or (agy_p.get("projects") or [""])[0] or agy_p.get("profile") or "").strip()
    if pri_proj in ("", "default", "primary", "all"):
        pri_proj = _read_dir_proj(Path.home() / ".gemini/antigravity-cli") or "enterprise-corp-ai"

    sb_proj = str(sb_p.get("gcpProject") or (sb_p.get("projects") or [""])[0] or sb_p.get("profile") or "").strip()
    if sb_proj in ("", "default", "sandbox", "all"):
        sb_proj = _read_dir_proj(Path.home() / ".gemini/antigravity-cli-sandbox") or "enterprise-sandbox"

    pers_proj = str(pers_p.get("gcpProject") or (pers_p.get("projects") or [""])[0] or pers_p.get("profile") or "").strip()
    if pers_proj in ("", "default", "personal", "all", "personal-homelab-org"):
        pers_proj = "personal-homelab"

    org_proj = str(org_p.get("gcpProject") or (org_p.get("projects") or [""])[0] or org_p.get("profile") or "").strip()
    if org_proj in ("", "default", "org", "all"):
        org_proj = "org-ai-ops"

    _res_meta = {
        "primary_proj": pri_proj,
        "sandbox_proj": sb_proj,
        "personal_proj": pers_proj,
        "org_proj": org_proj,
        "primary_label": str(agy_p.get("label") or "AGY Corp"),
        "primary_short": str(agy_p.get("shortLabel") or "AGY · Corp"),
        "primary_display": str(agy_p.get("displayName") or "Antigravity · Enterprise"),
        "primary_badge": str(agy_p.get("badge") or pri_proj),
        "sandbox_label": str(sb_p.get("label") or "AGY Sandbox"),
        "sandbox_short": str(sb_p.get("shortLabel") or "AGY · Sandbox"),
        "sandbox_display": str(sb_p.get("displayName") or "Antigravity · Sandbox"),
        "sandbox_badge": str(sb_p.get("badge") or sb_proj),
        "personal_label": str(pers_p.get("label") or "AGY Personal"),
        "personal_short": str(pers_p.get("shortLabel") or "AGY · Personal"),
        "personal_display": str(pers_p.get("displayName") or "Antigravity · Personal"),
        "personal_badge": str(pers_p.get("badge") or "personal"),
        "org_label": str(org_p.get("label") or "AGY Org"),
        "org_short": str(org_p.get("shortLabel") or "AGY · Org"),
        "org_display": str(org_p.get("displayName") or "Antigravity · Org"),
        "org_badge": str(org_p.get("badge") or "org"),
    }
    if _AGY_META_CACHE is None:
        _AGY_META_CACHE = dict(_res_meta)
    return _res_meta


def is_localhost_only(settings: dict | None = None) -> bool:
    if settings is None:
        settings = load_modular_settings()
    val = settings.get("localhostOnly")
    if val is None:
        return False
    return bool(val)


def discover_agy_config() -> tuple[list[tuple[Path, str, bool]], list[str]]:
    """Discover local AGY directories, their default GCP project, and whether they have dedicated storage."""
    settings = load_modular_settings()
    meta = resolve_agy_meta(settings)
    pri_proj = meta["primary_proj"]
    sb_proj = meta["sandbox_proj"]
    agy_cfg = (settings.get("agents") or {}).get("agy") or {}
    provs = settings.get("providers") or {}

    raw_dirs: list[Path] = [
        Path.home() / ".gemini/antigravity-cli",
        Path.home() / ".gemini/antigravity-cli-sandbox",
        Path.home() / ".gemini/antigravity-cli-personal",
    ]
    for p_key in ("agy", "agy-sandbox"):
        p_cfg = provs.get(p_key) or {}
        for d in p_cfg.get("dirs", []):
            raw_dirs.append(Path(d).expanduser())
    for d in agy_cfg.get("dirs", []) + agy_cfg.get("extra_dirs", []):
        raw_dirs.append(Path(d).expanduser())
    for d in os.environ.get("OMARCHY_AGY_DIRS", "").replace(",", ":").split(":"):
        if d.strip():
            raw_dirs.append(Path(d.strip()).expanduser())

    main_conv = (Path.home() / ".gemini/antigravity-cli/conversations").resolve() if (Path.home() / ".gemini/antigravity-cli/conversations").exists() else None
    seen_conv_dirs: set[str] = set()
    valid_dirs: list[tuple[Path, str, bool]] = []
    projs: list[str] = []

    for p_name in os.environ.get("OMARCHY_AGY_PROJECTS", "").split(","):
        if p_name.strip() and p_name.strip() not in projs:
            projs.append(p_name.strip())
    for p_name in agy_cfg.get("projects", []):
        if p_name and p_name not in projs:
            projs.append(p_name)

    for d in raw_dirs:
        if "migration-staging" in str(d) or not d.exists():
            continue
        sp = d / "settings.json"
        dir_proj = sb_proj if "sandbox" in d.name.lower() else pri_proj
        if sp.exists():
            try:
                gp = json.loads(sp.read_text(encoding="utf-8")).get("gcp", {}).get("project")
                if gp:
                    dir_proj = gp
                    if gp not in projs:
                        projs.append(gp)
            except Exception:
                pass
        conv_d = d / "conversations"
        conv_real = str(conv_d.resolve()) if conv_d.exists() else str(d.resolve())
        if conv_real in seen_conv_dirs:
            continue
        seen_conv_dirs.add(conv_real)
        is_dedicated = bool(main_conv and conv_real != str(main_conv))
        valid_dirs.append((d, dir_proj, is_dedicated))

    for dp in (pri_proj, sb_proj):
        if dp and dp not in projs:
            projs.append(dp)
    return valid_dirs, projs


def _parse_session(cid: str, db_p: Path | None, tr_p: Path | None, default_proj: str = "agy-primary", dedicated_dir: bool = False, sandbox_proj: str = "agy-sandbox") -> dict:
    res = {
        "cid": cid,
        "parent": "",
        "ws": "global",
        "proj": default_proj,
        "explicit_proj": bool(dedicated_dir and default_proj == sandbox_proj),
        "steps": 0,
        "prompts": 0,
        "tools": 0,
        "ts": 0,
        "events": [],
    }
    if db_p and db_p.exists():
        conn = None
        try:
             fallback_ts = int(db_p.stat().st_mtime)
        except Exception:
            fallback_ts = 0
        try:
            conn = sqlite3.connect(f"file:{db_p}?mode=ro", uri=True, timeout=2.0)
            try:
                row = conn.execute("SELECT data FROM trajectory_metadata_blob LIMIT 1").fetchone()
                if row and row[0]:
                    m = _pb(row[0])
                    if 5 in m:
                        res["parent"] = _s(m[5][0]).strip()
                    if 7 in m:
                        for m7 in m[7]:
                            u = _pb(m7)
                            if 1 in u:
                                cand = Path(urllib.parse.unquote(_s(u[1][0])).replace("file://", "")).name
                                if cand:
                                    res["ws"] = cand
                                    break
                    if res["ws"] == "global" and isinstance(row[0], (bytes, bytearray)):
                        for fm in re.findall(rb"file:///[^\x00-\x1f\"<> )]+", bytes(row[0])):
                            cand_p = urllib.parse.unquote(fm.decode("utf-8", errors="ignore")).replace("file://", "").rstrip("/")
                            if "/.gemini" not in cand_p and cand_p not in ("", "/home", str(Path.home())):
                                res["ws"] = Path(cand_p).name or "global"
                                break
            except Exception:
                pass

            step_rows = []
            try:
                step_rows = conn.execute("SELECT idx, step_type, metadata FROM steps ORDER BY idx").fetchall()
            except sqlite3.DatabaseError:
                misses = 0
                for idx in range(0, 20000):
                    try:
                        r = conn.execute("SELECT idx, step_type, metadata FROM steps WHERE idx = ?", (idx,)).fetchone()
                        if r:
                            step_rows.append(r)
                            misses = 0
                        else:
                            misses += 1
                            if misses > 50:
                                break
                    except sqlite3.DatabaseError:
                        misses = 0

            step_ts: dict[int, int] = {}
            last_valid_ts = fallback_ts
            for s_idx, st, meta in step_rows:
                try:
                    res["steps"] += 1
                    ts = 0
                    if meta:
                        mp = _pb(meta)
                        if 1 in mp:
                            tp = _pb(mp[1][0])
                            if 1 in tp and isinstance(tp[1][0], int):
                                ts = tp[1][0]
                    if ts <= 0:
                        ts = last_valid_ts
                    else:
                        last_valid_ts = ts
                    if isinstance(s_idx, int):
                        step_ts[s_idx] = ts
                    if ts > res["ts"]:
                        res["ts"] = ts
                    if st == 14:
                        res["prompts"] += 1
                        res["events"].append([ts, "p", "", 1, 0, 0])
                    elif st not in (14, 15, 17, 23, 101):
                        res["tools"] += 1
                except Exception:
                    continue

            gen_rows = []
            try:
                gen_rows = conn.execute("SELECT idx, data FROM gen_metadata ORDER BY idx").fetchall()
            except sqlite3.DatabaseError:
                misses = 0
                for idx in range(0, 10000):
                    try:
                        r = conn.execute("SELECT idx, data FROM gen_metadata WHERE idx = ?", (idx,)).fetchone()
                        if r:
                            gen_rows.append(r)
                            misses = 0
                        else:
                            misses += 1
                            if misses > 50:
                                break
                    except sqlite3.DatabaseError:
                        misses = 0

            sorted_s_idxs = sorted(step_ts.keys())
            for g_idx, gm in gen_rows:
                if not gm:
                    continue
                try:
                    gp = _pb(gm)
                    if 1 not in gp:
                        continue
                    s1 = _pb(gp[1][0])
                    if 17 in s1:
                        err_s = _s(s1[17][0])
                        pm = PROJ_RE.search(err_s)
                        if pm and pm.group(1) != "default-cli-project":
                            res["proj"] = pm.group(1)
                            res["explicit_proj"] = True
                    target_step = None
                    for entry_b in s1.get(20, []):
                        kv = _pb(entry_b)
                        if 1 in kv and _s(kv[1][0]) == "last_step_index" and 2 in kv:
                            try:
                                target_step = int(_s(kv[2][0]))
                            except Exception:
                                pass
                            break
                    ts = 0
                    if target_step is not None:
                        if target_step in step_ts:
                            ts = step_ts[target_step]
                        elif sorted_s_idxs:
                            # nearest step <= target_step
                            prev_idxs = [x for x in sorted_s_idxs if x <= target_step]
                            ts = step_ts[prev_idxs[-1]] if prev_idxs else step_ts[sorted_s_idxs[0]]
                    if ts <= 0:
                        if isinstance(g_idx, int) and g_idx in step_ts:
                            ts = step_ts[g_idx]
                        else:
                            ts = res["ts"] or fallback_ts
                    raw_m = _s(s1[19][0]) if 19 in s1 else "MODEL_GOOGLE_GEMINI_PRO_3_1"
                    mod = MODEL_MAP.get(raw_m, raw_m.lower().replace("model_", "").replace("_", "-"))
                    if 4 in s1:
                        u = _pb(s1[4][0])
                        it = u[2][0] if 2 in u and isinstance(u[2][0], int) else 0
                        ot = u[3][0] if 3 in u and isinstance(u[3][0], int) else 0
                        ct = u[5][0] if 5 in u and isinstance(u[5][0], int) else 0
                        if it or ot or ct:
                            res["events"].append([ts, "u", mod, it, ot, ct])
                except Exception:
                    continue
        except Exception:
            pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if tr_p and tr_p.exists():
        try:
            if not res["parent"]:
                with tr_p.open("r", encoding="utf-8", errors="ignore") as f:
                    head = f.read(8192)
                pm = PARENT_RE.search(head)
                if pm:
                    res["parent"] = pm.group(1)
            if res["steps"] == 0:
                for line in tr_p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    res["steps"] += 1
                    ts_s = obj.get("created_at") or obj.get("timestamp") or ""
                    ts = int(datetime.fromisoformat(ts_s.replace("Z", "+00:00")).timestamp()) if ts_s else int(tr_p.stat().st_mtime)
                    if ts > res["ts"]:
                        res["ts"] = ts
                    if obj.get("type") == "USER_INPUT":
                        res["prompts"] += 1
                        res["events"].append([ts, "p", "", 1, 0, 0])
                    for _tc in obj.get("tool_calls", []):
                        res["tools"] += 1
                    u = obj.get("usage")
                    if isinstance(u, dict):
                        raw_m = u.get("model") or "gemini-3.1-pro-high"
                        mod = MODEL_MAP.get(raw_m, str(raw_m).lower().replace("model_", "").replace("_", "-"))
                        it = int(u.get("input_tokens", 0) or 0)
                        ot = int(u.get("output_tokens", 0) or 0)
                        ct = int(u.get("cache_read_input_tokens", 0) or u.get("cached_tokens", 0) or 0)
                        if it or ot or ct:
                            res["events"].append([ts, "u", mod, it, ot, ct])
        except Exception:
            pass
    if res["events"]:
        res["events"] = _compact_session_events(res["events"], int(time.time()))
    return res


def _gcloud_token() -> str:
    try:
        r = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, timeout=2.5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _api_get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=4.0) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _query_project_cloud(proj: str, tok: str, now_dt: datetime) -> dict:
    out = {
        "project": proj,
        "daily_tokens": defaultdict(lambda: defaultdict(lambda: [0, 0])),
        "daily_reqs": defaultdict(lambda: defaultdict(int)),
        "peak_rpm": 0,
        "quota_rpm": 30000,
    }
    t_end = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    t_30d = (now_dt - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
    t_24h = (now_dt - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = f"https://monitoring.googleapis.com/v3/projects/{proj}/timeSeries"
    try:
        q1 = urllib.parse.urlencode(
            {
                "filter": 'metric.type="aiplatform.googleapis.com/publisher/online_serving/token_count"',
                "interval.startTime": t_30d,
                "interval.endTime": t_end,
                "aggregation.alignmentPeriod": "86400s",
                "aggregation.perSeriesAligner": "ALIGN_SUM",
                "aggregation.crossSeriesReducer": "REDUCE_SUM",
                "aggregation.groupByFields": ["resource.label.model_user_id", "metric.label.type"],
            },
            doseq=True,
        )
        for ts in _api_get(f"{base}?{q1}", tok).get("timeSeries", []):
            m = ts.get("resource", {}).get("labels", {}).get("model_user_id", "unknown")
            tp = ts.get("metric", {}).get("labels", {}).get("type", "input")
            for pt in ts.get("points", []):
                dt = datetime.fromisoformat(pt["interval"]["endTime"].replace("Z", "+00:00")).astimezone()
                day = (dt - timedelta(seconds=1)).strftime("%Y-%m-%d")
                v = int(pt.get("value", {}).get("int64Value", 0))
                if tp == "output":
                    out["daily_tokens"][day][m][1] += v
                else:
                    out["daily_tokens"][day][m][0] += v
    except Exception:
        pass
    try:
        q2 = urllib.parse.urlencode(
            {
                "filter": 'metric.type="aiplatform.googleapis.com/publisher/online_serving/model_invocation_count"',
                "interval.startTime": t_30d,
                "interval.endTime": t_end,
                "aggregation.alignmentPeriod": "86400s",
                "aggregation.perSeriesAligner": "ALIGN_SUM",
                "aggregation.crossSeriesReducer": "REDUCE_SUM",
                "aggregation.groupByFields": ["resource.label.model_user_id"],
            },
            doseq=True,
        )
        for ts in _api_get(f"{base}?{q2}", tok).get("timeSeries", []):
            m = ts.get("resource", {}).get("labels", {}).get("model_user_id", "unknown")
            for pt in ts.get("points", []):
                dt = datetime.fromisoformat(pt["interval"]["endTime"].replace("Z", "+00:00")).astimezone()
                day = (dt - timedelta(seconds=1)).strftime("%Y-%m-%d")
                out["daily_reqs"][day][m] += int(pt.get("value", {}).get("int64Value", 0))
    except Exception:
        pass
    try:
        q3 = urllib.parse.urlencode(
            {
                "filter": 'metric.type="aiplatform.googleapis.com/publisher/online_serving/model_invocation_count"',
                "interval.startTime": t_24h,
                "interval.endTime": t_end,
                "aggregation.alignmentPeriod": "60s",
                "aggregation.perSeriesAligner": "ALIGN_SUM",
                "aggregation.crossSeriesReducer": "REDUCE_SUM",
            }
        )
        for ts in _api_get(f"{base}?{q3}", tok).get("timeSeries", []):
            for pt in ts.get("points", []):
                v = int(pt.get("value", {}).get("int64Value", 0))
                if v > out["peak_rpm"]:
                    out["peak_rpm"] = v
    except Exception:
        pass
    return {
        "project": proj,
        "daily_tokens": {d: dict(ms) for d, ms in out["daily_tokens"].items()},
        "daily_reqs": {d: dict(ms) for d, ms in out["daily_reqs"].items()},
        "peak_rpm": out["peak_rpm"],
        "quota_rpm": out["quota_rpm"],
    }


def _refresh_cloud_cache_sync(projects: list[str], cp: Path) -> dict:
    import fcntl
    lock_p = cp.with_suffix(".lock")
    lock_p.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_p, "w", encoding="utf-8") as lf:
        try:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return json.loads(cp.read_text(encoding="utf-8")).get("projects", {}) if cp.exists() else {}
        tok = _gcloud_token()
        if not tok:
            if cp.exists():
                try:
                    cp.touch()
                except Exception:
                    pass
                return json.loads(cp.read_text(encoding="utf-8")).get("projects", {})
            return {}
        now_dt = datetime.now(timezone.utc)
        with ThreadPoolExecutor(max_workers=max(1, len(projects))) as ex:
            res = {r["project"]: r for r in ex.map(lambda p: _query_project_cloud(p, tok, now_dt), projects)}
        cp.write_text(json.dumps({"ts": time.time(), "projects": res}), encoding="utf-8")
        return res


def get_cloud_metrics(projects: list[str], force: bool = False, refresh_cloud_sync: bool = False) -> dict:
    cp = Path.home() / ".cache/omarchy/agy-cloud-monitoring.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    if refresh_cloud_sync:
        return _refresh_cloud_cache_sync(projects, cp)

    cached_projects = None
    age = 999999.0
    if cp.exists():
        try:
            age = time.time() - cp.stat().st_mtime
            d = json.loads(cp.read_text(encoding="utf-8"))
            if set(d.get("projects", {}).keys()) >= set(projects):
                cached_projects = d["projects"]
        except Exception:
            cached_projects = None

    if cached_projects is not None:
        if (force and age > 120) or age > 300:
            # Touch mtime before spawning so concurrent callers do not spawn duplicate background refreshes
            try:
                cp.touch()
                subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "--refresh-cloud-only"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except Exception:
                pass
        return cached_projects

    return _refresh_cloud_cache_sync(projects, cp)


_ALL_MESH_HOSTS: tuple[str, ...] = ("localhost",)


def _load_host_attribution_map(
    local_dirs: list[tuple[Path, str, bool]],
    extra_parent_map: dict[str, str] | None = None,
    tr_hosts_by_cid: dict[str, set[str]] | None = None,
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]], dict[str, str]]:
    """Build per-conversation host attribution sets from .host_manifest_<host>.json and local state."""
    presence_by_cid: dict[str, set[str]] = defaultdict(set)
    transcripts_by_cid: dict[str, set[str]] = defaultdict(set)
    history_by_cid: dict[str, set[str]] = defaultdict(set)
    combined_parent_map: dict[str, str] = dict(extra_parent_map or {})

    if tr_hosts_by_cid:
        for cid, hset in tr_hosts_by_cid.items():
            for h in hset:
                if h in _ALL_MESH_HOSTS:
                    transcripts_by_cid[cid].add(h)

    manifest_candidates: list[tuple[str, Path]] = []
    conv_root = Path.home() / ".gemini/antigravity-cli/conversations"
    remote_hosts_root = Path.home() / ".cache/omarchy/remote-sessions/hosts"
    for h in _ALL_MESH_HOSTS:
        manifest_candidates.append((h, conv_root / f".host_manifest_{h}.json"))
        manifest_candidates.append((h, remote_hosts_root / h / "manifest.json"))

    for h, mp in manifest_candidates:
        if not mp.exists():
            continue
        try:
            raw = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            continue
        agy_m = raw.get("agy") if isinstance(raw.get("agy"), dict) else raw
        if not isinstance(agy_m, dict):
            continue
        pres = agy_m.get("presence") or agy_m.get("presence_locks") or {}
        if isinstance(pres, dict):
            for cid in pres.keys():
                presence_by_cid[str(cid)].add(h)
        elif isinstance(pres, list):
            for cid in pres:
                presence_by_cid[str(cid)].add(h)

        trs = agy_m.get("transcripts") or agy_m.get("brain_transcripts") or {}
        if isinstance(trs, dict):
            for cid in trs.keys():
                transcripts_by_cid[str(cid)].add(h)
        elif isinstance(trs, list):
            for cid in trs:
                transcripts_by_cid[str(cid)].add(h)

        hist = agy_m.get("history") or agy_m.get("history_cids") or []
        if isinstance(hist, (list, dict)):
            for cid in (hist.keys() if isinstance(hist, dict) else hist):
                history_by_cid[str(cid)].add(h)

        pmap = agy_m.get("parent_map") or {}
        if isinstance(pmap, dict):
            for k, v in pmap.items():
                if k and v and str(k) not in combined_parent_map:
                    combined_parent_map[str(k)] = str(v)

    # Live local scan on localhost so active sessions are immediately visible
    for d, _, _ in local_dirs:
        pres_d = d / "presence"
        if pres_d.is_dir():
            try:
                with os.scandir(pres_d) as it:
                    for de in it:
                        if de.name.endswith(".lock"):
                            presence_by_cid[de.name[:-5]].add("localhost")
            except OSError:
                pass
        hist_f = d / "history.jsonl"
        if hist_f.is_file():
            try:
                for ln in hist_f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if not ln.strip():
                        continue
                    obj = json.loads(ln)
                    c = obj.get("conversationId") or obj.get("id")
                    if c:
                        history_by_cid[str(c)].add("localhost")
            except Exception:
                pass

    return presence_by_cid, transcripts_by_cid, history_by_cid, combined_parent_map


def _resolve_agy_origin_host(
    cid: str,
    ws: str,
    presence_by_cid: dict[str, set[str]],
    transcripts_by_cid: dict[str, set[str]],
    history_by_cid: dict[str, set[str]],
    combined_parent_map: dict[str, str],
) -> str:
    """Resolve the single authoritative execution host for an AGY conversation."""
    chain: list[str] = []
    curr = cid
    seen: set[str] = set()
    while curr and curr not in seen and len(chain) < 16:
        seen.add(curr)
        chain.append(curr)
        curr = combined_parent_map.get(curr, "")

    for a in chain:
        th = [h for h in _ALL_MESH_HOSTS if h in transcripts_by_cid.get(a, ())]
        if len(th) == 1:
            return th[0]
        if len(th) > 1:
            ph_on_tr = [h for h in th if any(h in presence_by_cid.get(x, ()) for x in chain)]
            if len(ph_on_tr) >= 1:
                return ph_on_tr[0]
            return th[0]

        ph = [h for h in _ALL_MESH_HOSTS if h in presence_by_cid.get(a, ())]
        if len(ph) == 1:
            return ph[0]
        if len(ph) > 1:
            th_on_pr = [h for h in ph if any(h in transcripts_by_cid.get(x, ()) for x in chain)]
            if len(th_on_pr) >= 1:
                return th_on_pr[0]
            return ph[0]

    hh = [h for h in _ALL_MESH_HOSTS if any(h in history_by_cid.get(x, ()) for x in chain)]
    if len(hh) >= 1:
        return hh[0]

    ws_low = (ws or "").lower()
    if any(k in ws_low for k in ("work-infra", "enterprise-ai-ops", "corp-cloud", "net-automation", "dns-tools", "quota-alerts", "net-monitor")) and "/work" not in ws_low:
        return "net-node-1"
    if "homelab-ops" in ws_low:
        return "server-1"
    return "localhost"


def _scan_all_local_sessions(dirs: list[tuple[Path, str, bool]], rebuild_cache: bool = False) -> dict[str, dict]:
    sc_p = Path.home() / ".gemini/antigravity-cli/.sessions_cache_v3.json"
    sc: dict[str, dict] = {}
    migrated_schema = False
    now_ts = int(time.time())
    if sc_p.exists() and not rebuild_cache:
        try:
            raw_sc = json.loads(sc_p.read_text(encoding="utf-8"))
            schema_v = int(raw_sc.get("__schema__", 0) or 0)
            if schema_v in (5, 6, 7, 8, 9, 10):
                sc = raw_sc.get("sessions", {})
                if schema_v < 6:
                    for _entry in sc.values():
                        _d = _entry.get("data")
                        if isinstance(_d, dict) and "events" in _d:
                            _d["events"] = _compact_session_events(_d["events"], now_ts)
                if schema_v < 10:
                    migrated_schema = True
        except Exception:
            sc = {}

    meta = resolve_agy_meta()
    pri_p = meta["primary_proj"]
    sb_p = meta["sandbox_proj"]

    cids: dict[str, dict] = {}
    tr_hosts_by_cid: dict[str, set[str]] = defaultdict(set)

    def _register_dir(
        d: Path,
        dir_proj: str,
        is_dedicated: bool,
        host_name: str,
        is_personal_dir: bool = False,
        skip_existing_db: bool = False,
    ):
        d_str = str(d)
        for sub in (f"{d_str}/conversations", d_str):
            try:
                it = os.scandir(sub)
            except OSError:
                continue
            with it:
                for de in it:
                    name = de.name
                    if not name.endswith(".db") or name == "conversation_summaries.db":
                        continue
                    cid = name[:-3]
                    entry = cids.get(cid)
                    if skip_existing_db and entry is not None and entry["db"] is not None:
                        continue
                    try:
                        st = de.stat()
                    except OSError:
                        continue
                    if entry is None:
                        entry = {
                            "db": None,
                            "db_sz": 0,
                            "db_mt": 0,
                            "tr": None,
                            "tr_sz": 0,
                            "tr_mt": 0,
                            "proj": dir_proj,
                            "dedicated": is_dedicated,
                            "personal_dir": is_personal_dir,
                            "hosts": set(),
                        }
                        cids[cid] = entry
                    entry["hosts"].add(host_name)
                    if is_personal_dir:
                        entry["personal_dir"] = True
                    if entry["db"] is None or st.st_size > entry["db_sz"]:
                        entry["db"] = Path(de.path)
                        entry["db_sz"] = st.st_size
                        entry["db_mt"] = int(st.st_mtime)
                        entry["proj"] = dir_proj
                        entry["dedicated"] = is_dedicated
        try:
            b_it = os.scandir(f"{d_str}/brain")
        except OSError:
            b_it = None
        if b_it is not None:
            with b_it:
                for de in b_it:
                    if not de.is_dir(follow_symlinks=False):
                        continue
                    cid = de.name
                    tr_path = f"{de.path}/.system_generated/logs/transcript.jsonl"
                    try:
                        st = os.stat(tr_path)
                    except OSError:
                        continue
                    tr_hosts_by_cid[cid].add(host_name)
                    entry = cids.get(cid)
                    if entry is None:
                        entry = {
                            "db": None,
                            "db_sz": 0,
                            "db_mt": 0,
                            "tr": None,
                            "tr_sz": 0,
                            "tr_mt": 0,
                            "proj": dir_proj,
                            "dedicated": is_dedicated,
                            "personal_dir": is_personal_dir,
                            "hosts": set(),
                        }
                        cids[cid] = entry
                    entry["hosts"].add(host_name)
                    if is_personal_dir:
                        entry["personal_dir"] = True
                    if st.st_size > entry["tr_sz"]:
                        entry["tr"] = Path(tr_path)
                        entry["tr_sz"] = st.st_size
                        entry["tr_mt"] = int(st.st_mtime)

    localhost_only = is_localhost_only()
    local_host = socket.gethostname().split(".")[0] or "localhost"
    for d, dir_proj, is_dedicated in dirs:
        is_pers = "personal" in d.name.lower()
        _register_dir(d, dir_proj, is_dedicated, local_host, is_personal_dir=is_pers, skip_existing_db=False)

    if not localhost_only:
        remote_hosts_root = Path.home() / ".cache/omarchy/remote-sessions/hosts"
        if remote_hosts_root.exists():
            for host_dir in sorted(remote_hosts_root.iterdir()):
                if not host_dir.is_dir():
                    continue
                hname = host_dir.name
                agy_hdir = host_dir / "agy"
                if agy_hdir.exists():
                    _register_dir(agy_hdir, pri_p, False, hname, is_personal_dir=False, skip_existing_db=True)

        remote_agy_d = Path.home() / ".cache/omarchy/remote-sessions/agy"
        if remote_agy_d.exists():
            for f in remote_agy_d.glob("*.db"):
                cid = f.stem
                if cid in cids and cids[cid]["db"] is not None:
                    continue
                try:
                    st = f.stat()
                except OSError:
                    continue
                entry = cids.setdefault(
                    cid,
                    {
                        "db": None,
                        "db_sz": 0,
                        "db_mt": 0,
                        "tr": None,
                        "tr_sz": 0,
                        "tr_mt": 0,
                        "proj": pri_p,
                        "dedicated": False,
                        "personal_dir": False,
                        "hosts": {"remote"},
                    },
                )
                if entry["db"] is None or st.st_size > entry["db_sz"]:
                    entry.update({"db": f, "db_sz": st.st_size, "db_mt": int(st.st_mtime)})

    new_sc: dict[str, dict] = {}
    dirty = False
    for cid, info in cids.items():
        sig = f"{info['db_sz']}:{info['db_mt']}:{info['tr_sz']}:{info['tr_mt']}:{info['proj']}:{int(info['dedicated'])}:{int(info['personal_dir'])}"
        if cid in sc and sc[cid].get("sig") == sig:
            new_sc[cid] = sc[cid]
        else:
            parsed = _parse_session(cid, info["db"], info["tr"], info["proj"], info["dedicated"], sandbox_proj=sb_p)
            parsed["personal_dir"] = bool(info["personal_dir"])
            new_sc[cid] = {
                "sig": sig,
                "data": parsed,
            }
            dirty = True

    parent_map: dict[str, str] = {}
    for cid, entry in new_sc.items():
        par = entry["data"].get("parent")
        if par:
            parent_map[cid] = par

    presence_by_cid, transcripts_by_cid, history_by_cid, combined_parent_map = _load_host_attribution_map(
        dirs,
        extra_parent_map=parent_map,
        tr_hosts_by_cid=tr_hosts_by_cid,
    )

    def get_root(c: str) -> str:
        seen = set()
        curr = c
        while curr in combined_parent_map and combined_parent_map[curr] not in seen:
            seen.add(curr)
            curr = combined_parent_map[curr]
        return curr

    tree_proj: dict[str, str] = {}
    tree_ws: dict[str, str] = {}
    for cid, entry in new_sc.items():
        d = entry["data"]
        r = get_root(cid)
        if d.get("explicit_proj") and d.get("proj"):
            if d["proj"] == sb_p or r not in tree_proj:
                tree_proj[r] = d["proj"]
        ws_val = d.get("ws")
        if ws_val and ws_val != "global":
            if cid == r or r not in tree_ws:
                tree_ws[r] = ws_val

    for cid, entry in new_sc.items():
        d = entry["data"]
        r = get_root(cid)
        if not d.get("explicit_proj") and r in tree_proj:
            if d.get("proj") != tree_proj[r]:
                d["proj"] = tree_proj[r]
                dirty = True
        if (not d.get("ws") or d.get("ws") == "global") and r in tree_ws:
            if d.get("ws") != tree_ws[r]:
                d["ws"] = tree_ws[r]
                dirty = True

        c_proj = d.get("proj") or pri_p
        c_ws = d.get("ws") or "global"
        origin_host = _resolve_agy_origin_host(
            cid,
            c_ws,
            presence_by_cid,
            transcripts_by_cid,
            history_by_cid,
            combined_parent_map,
        )
        raw_hosts_list = [origin_host]
        if d.get("raw_hosts") != raw_hosts_list:
            d["raw_hosts"] = raw_hosts_list
            dirty = True

        c_hosts = {"localhost"} if localhost_only else {origin_host}
        only_netnode = bool(c_hosts) and c_hosts.issubset({"net-node-1", "net-node-2"})
        only_homelab = bool(c_hosts) and c_hosts.issubset({"server-1", "gpu-node"})
        has_localhost = ("localhost" in c_hosts) or (not c_hosts)

        is_org = has_localhost and (not only_netnode) and (not only_homelab) and _is_org_workspace(c_ws)
        is_enterprise = (not is_org) and (not only_homelab) and (_is_enterprise_workspace(c_ws) or only_netnode)

        if only_netnode:
            prof_id = "agy-sandbox" if c_proj == sb_p else "agy"
        elif only_homelab:
            prof_id = "agy-sandbox" if (c_proj == sb_p and d.get("dedicated")) else "agy-personal"
        elif is_org:
            prof_id = "agy-org"
        elif is_enterprise:
            prof_id = "agy-sandbox" if c_proj == sb_p else "agy"
        elif d.get("personal_dir"):
            prof_id = "agy-personal"
        else:
            prof_id = "agy-personal"
            if c_proj == sb_p and not d.get("dedicated"):
                d["proj"] = pri_p
                dirty = True

        allowed_for_prof = {"localhost"} if localhost_only else set(PROFILE_ALLOWED_HOSTS.get(prof_id, ("localhost",)))
        filtered_hosts = ["localhost"] if localhost_only else ([origin_host] if origin_host in allowed_for_prof else [PROFILE_ALLOWED_HOSTS.get(prof_id, ("localhost",))[0]])
        if d.get("hosts") != filtered_hosts:
            d["hosts"] = filtered_hosts
            dirty = True

        if d.get("profile_id") != prof_id:
            d["profile_id"] = prof_id
            dirty = True

    if dirty or migrated_schema or len(new_sc) != len(sc):
        try:
            sc_p.write_text(json.dumps({"__schema__": 10, "sessions": new_sc}, separators=(",", ":")), encoding="utf-8")
        except Exception:
            pass

    return new_sc


def _build_agy_record(
    record_id: str,
    profile_name: str,
    display_name: str,
    short_label: str,
    badge: str,
    target_projects: set[str] | None,
    sessions_map: dict[str, dict],
    all_projects: list[str],
    cloud: dict,
    all_proj_breakdown: list[dict],
    family_summary: dict,
    aggregated: bool,
    target_profile_ids: set[str] | None = None,
) -> dict:
    now = datetime.now()
    today_s = now.strftime("%Y-%m-%d")
    cut_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    cut_7d = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    cut_5h = int((now - timedelta(hours=5)).timestamp())

    root_convs = sub_convs = total_steps = total_tools = 0
    root_convs_30d = sub_convs_30d = 0
    today_prompts = today_sub_calls = today_sub_tokens = 0
    prompts_30d = prompts_7d = prompts_all = 0
    sessions_by_day: dict[str, set[str]] = defaultdict(set)
    prompts_by_day: dict[str, int] = defaultdict(int)
    local_day_mod: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    ws_stats: dict[str, dict] = defaultdict(
        lambda: {"tokens": 0, "costUsd": 0.0, "costUsd7d": 0.0, "costUsdToday": 0.0, "prompts": 0, "sessions": set(), "last": ""}
    )
    host_stats: dict[str, dict] = defaultdict(
        lambda: {"tokens30d": 0, "costUsd30d": 0.0, "costUsd7d": 0.0, "costUsdToday": 0.0, "prompts30d": 0, "sessions30d": set()}
    )
    tok_5h = 0
    all_time_tokens = 0
    all_time_cost = 0.0
    recent_convs = []
    sessions_7d: set[str] = set()

    meta = resolve_agy_meta()
    localhost_only = is_localhost_only()
    if localhost_only:
        allowed_hosts_tuple = ("localhost",)
    elif aggregated:
        allowed_hosts_tuple = ("localhost",)
    else:
        allowed_hosts_tuple = PROFILE_ALLOWED_HOSTS.get(
            record_id, ("localhost",)
        )
    for _ah in allowed_hosts_tuple:
        _ = host_stats[_ah]
    mesh_allowed = set(allowed_hosts_tuple)

    for cid, entry in sessions_map.items():
        d = entry["data"]
        c_proj = d.get("proj") or meta["primary_proj"]
        c_prof = d.get("profile_id") or ("agy-sandbox" if c_proj == meta["sandbox_proj"] else "agy")
        if target_profile_ids is not None:
            if c_prof not in target_profile_ids:
                continue
        elif target_projects is not None and c_proj not in target_projects:
            continue

        is_sub = bool(d.get("parent"))
        if is_sub:
            sub_convs += 1
        else:
            root_convs += 1
        total_steps += d.get("steps", 0)
        total_tools += d.get("tools", 0)
        ws = d.get("ws") or "global"
        c_hosts = d.get("hosts") or ["localhost"]
        origin_host = c_hosts[0] if c_hosts else "localhost"
        primary_host = origin_host if origin_host in mesh_allowed else allowed_hosts_tuple[0]

        c_tok = 0
        c_cost = 0.0
        c_mod = "gemini-3.1-pro-high"
        c_in_30d = False

        ws_entry = ws_stats[ws]
        host_entries = [host_stats[primary_host]]
        c_in_7d = False

        for ev in d.get("events", []):
            ts, et, mod, it, ot, ct = ev[:6]
            if not ts:
                continue
            day = _ts_to_day(ts)
            if et == "p":
                p_cnt = it if it > 0 else 1
                prompts_all += p_cnt
                if day >= cut_30d:
                    c_in_30d = True
                    prompts_by_day[day] += p_cnt
                    prompts_30d += p_cnt
                    ws_entry["prompts"] += p_cnt
                    sessions_by_day[day].add(cid)
                    for _he in host_entries:
                        _he["prompts30d"] += p_cnt
                    if day > ws_entry["last"]:
                        ws_entry["last"] = day
                    if day >= cut_7d:
                        prompts_7d += p_cnt
                        c_in_7d = True
                    if day == today_s:
                        today_prompts += p_cnt
            elif et == "u":
                tot = it + ot + ct
                ci, co, cc = _cost_rates(mod)
                ev_cost = (it * ci + ot * co + ct * cc) / 1e6
                all_time_tokens += tot
                all_time_cost += ev_cost
                c_tok += tot
                c_cost += ev_cost
                if mod:
                    c_mod = mod
                if ts >= cut_5h:
                    tok_5h += tot
                if day >= cut_30d:
                    c_in_30d = True
                    b = local_day_mod[day][c_mod]
                    b[0] += it
                    b[1] += ot
                    b[2] += ct
                    ws_entry["tokens"] += tot
                    ws_entry["costUsd"] += ev_cost
                    sessions_by_day[day].add(cid)
                    for _he in host_entries:
                        _he["tokens30d"] += tot
                        _he["costUsd30d"] += ev_cost
                    if day > ws_entry["last"]:
                        ws_entry["last"] = day
                    if day >= cut_7d:
                        c_in_7d = True
                        ws_entry["costUsd7d"] += ev_cost
                        for _he in host_entries:
                            _he["costUsd7d"] += ev_cost
                    if day == today_s:
                        ws_entry["costUsdToday"] += ev_cost
                        for _he in host_entries:
                            _he["costUsdToday"] += ev_cost
                        if is_sub:
                            today_sub_tokens += tot

        if c_in_30d:
            ws_entry["sessions"].add(cid)
            for _he in host_entries:
                _he["sessions30d"].add(cid)
            if c_in_7d:
                sessions_7d.add(cid)
            if is_sub:
                sub_convs_30d += 1
            else:
                root_convs_30d += 1

        if not is_sub and (c_tok > 0 or d.get("steps", 0) > 0):
            recent_convs.append(
                {
                    "id": cid[:8],
                    "workspace": ws,
                    "host": primary_host,
                    "profileId": c_prof,
                    "steps": d.get("steps", 0),
                    "toolCalls": d.get("tools", 0),
                    "model": c_mod,
                    "tokens": c_tok,
                    "costUsd": round(c_cost, 2),
                    "project": c_proj,
                    "ts": d.get("ts", 0),
                }
            )
        if is_sub and d.get("ts", 0) > 0 and _ts_to_day(d["ts"]) == today_s:
            today_sub_calls += 1

    recent_convs.sort(key=lambda x: -x["ts"])

    last_14_days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
    all_local_days = sorted(set(local_day_mod.keys()) | set(last_14_days) | {today_s})
    personal_mod: dict[str, list] = defaultdict(lambda: [0, 0, 0, 0.0])
    recent_days = []
    tot_30d = tok_7d = today_tokens = 0
    total_cost_30d = cost_7d = today_cost = 0.0
    today_by_mod = {}
    active_dates = []

    for day in all_local_days:
        if day < cut_30d:
            continue
        d_mods = local_day_mod.get(day, {})
        d_tot = 0
        d_cost = 0.0
        for m, (lit, lot, lct) in d_mods.items():
            tot = lit + lot + lct
            ci, co, cc = _cost_rates(m)
            mc = (lit * ci + lot * co + lct * cc) / 1e6
            d_tot += tot
            d_cost += mc
            personal_mod[m][0] += lit
            personal_mod[m][1] += lot
            personal_mod[m][2] += lct
            personal_mod[m][3] += mc
            if day == today_s and tot > 0:
                today_by_mod[m] = tot
        tot_30d += d_tot
        total_cost_30d += d_cost
        if d_tot > 0 or prompts_by_day[day] > 0:
            active_dates.append(day)
        if day >= cut_7d:
            tok_7d += d_tot
            cost_7d += d_cost
        if day == today_s:
            today_tokens = d_tot
            today_cost = d_cost
        recent_days.append(
            {
                "date": day,
                "tokens": d_tot,
                "messageCount": d_tot,
                "prompts": prompts_by_day[day],
                "sessions": len(sessions_by_day[day]),
                "costUsd": round(d_cost, 2),
                "costUSD": round(d_cost, 2),
            }
        )

    model_usage = {}
    model_quotas = []
    for m, (it, ot, ct, mcost) in sorted(personal_mod.items(), key=lambda x: (-x[1][3], -(x[1][0] + x[1][1] + x[1][2]))):
        tot = it + ot + ct
        if tot <= 0:
            continue
        cost = round(mcost, 2)
        sh = round(tot * 100.0 / tot_30d, 1) if tot_30d else 0.0
        model_usage[m] = {
            "inputTokens": it,
            "outputTokens": ot,
            "cacheReadTokens": ct,
            "cacheReadInputTokens": ct,
            "cacheCreationInputTokens": 0,
            "totalTokens": tot,
            "costUSD": cost,
            "costUsd": cost,
            "sharePct": sh,
        }
        model_quotas.append(
            {
                "model": m,
                "label": m,
                "usedPct": min(100.0, round(tot * 100.0 / 5_000_000_000, 1)),
                "tokens": tot,
                "sharePct": sh,
                "costUSD": cost,
            }
        )

    scoped_projs = [p for p in all_projects if target_projects is None or p in target_projects]
    scoped_breakdown = [pb for pb in all_proj_breakdown if target_projects is None or pb["project"] in target_projects]

    c_tok_30d = sum(pb["tokens30d"] for pb in scoped_breakdown)
    c_tok_7d = sum(pb["tokens7d"] for pb in scoped_breakdown)
    c_tok_today = sum(pb["tokensToday"] for pb in scoped_breakdown)
    c_req_30d = sum(pb["requests30d"] for pb in scoped_breakdown)
    c_req_7d = sum(pb["requests7d"] for pb in scoped_breakdown)
    c_req_today = sum(pb["requestsToday"] for pb in scoped_breakdown)

    if aggregated and len(scoped_breakdown) > 1:
        projects_breakdown_field = [
            {
                "project": "all-agy-projects",
                "scope": "shared_gcp_project",
                "tokens30d": c_tok_30d,
                "tokens7d": c_tok_7d,
                "tokensToday": c_tok_today,
                "requests30d": c_req_30d,
                "requests7d": c_req_7d,
                "requestsToday": c_req_today,
                "localTokens30d": tot_30d,
                "localTokens7d": tok_7d,
                "localTokensToday": today_tokens,
                "localCostUsd30d": round(total_cost_30d, 2),
                "localCostUsd7d": round(cost_7d, 2),
                "localCostUsdToday": round(today_cost, 2),
                "localSessions30d": root_convs_30d + sub_convs_30d,
                "peakRpm": max((pb["peakRpm"] for pb in scoped_breakdown), default=0),
                "quotaLimitRpm": max((pb["quotaLimitRpm"] for pb in scoped_breakdown), default=30000),
                "sharePct": 100.0,
            }
        ]
    else:
        projects_breakdown_field = scoped_breakdown

    ws_list = [
        {
            "workspace": k,
            "category": "org" if _is_org_workspace(k) else ("work" if _is_enterprise_workspace(k) else "personal"),
            "tokens": v["tokens"],
            "costUsd": round(v["costUsd"], 2),
            "costUsd7d": round(v["costUsd7d"], 2),
            "costUsdToday": round(v["costUsdToday"], 2),
            "prompts": v["prompts"],
            "sessions": len(v["sessions"]),
            "lastActive": v["last"],
        }
        for k, v in sorted(ws_stats.items(), key=lambda x: -x[1]["costUsd"])[:14]
    ]

    last_sync_file = Path.home() / ".cache/omarchy/remote-sessions/hosts/.last_sync"
    last_sync_iso = ""
    if last_sync_file.exists():
        try:
            last_sync_iso = datetime.fromtimestamp(int(last_sync_file.read_text().strip()), tz=timezone.utc).isoformat()
        except Exception:
            pass

    _host_order = {"localhost": 0, "server-1": 1, "gpu-node": 2, "net-node-1": 3, "net-node-2": 4}
    hosts_list = [
        {
            "host": k,
            "role": "local" if k == "localhost" else "mesh-sync",
            "status": "local" if k == "localhost" else "synced",
            "lastSyncAt": now.astimezone(timezone.utc).isoformat() if k == "localhost" else last_sync_iso,
            "tokens30d": v["tokens30d"],
            "tokens": v["tokens30d"],
            "costUsd30d": round(v["costUsd30d"], 2),
            "costUsd": round(v["costUsd30d"], 2),
            "costUsd7d": round(v["costUsd7d"], 2),
            "costUsdToday": round(v["costUsdToday"], 2),
            "prompts30d": v["prompts30d"],
            "prompts": v["prompts30d"],
            "sessions30d": len(v["sessions30d"]),
            "sessions": len(v["sessions30d"]),
        }
        for k, v in sorted(host_stats.items(), key=lambda x: (_host_order.get(x[0], 99), -x[1]["costUsd30d"]))
    ]

    st_p = (
        Path.home() / ".gemini/antigravity-cli-sandbox/settings.json"
        if record_id == "agy-sandbox"
        else (
            Path.home() / ".gemini/antigravity-cli-personal/settings.json"
            if record_id in ("agy-personal", "agy-org")
            else Path.home() / ".gemini/antigravity-cli/settings.json"
        )
    )
    st_cfg = json.loads(st_p.read_text(encoding="utf-8")) if st_p.exists() else {}
    act_mod = st_cfg.get("model", "gemini-3.1-pro-high")
    if model_quotas:
        act_mod = model_quotas[0]["model"]
    pri_proj = scoped_projs[0] if scoped_projs else meta["primary_proj"]
    loc = st_cfg.get("gcp", {}).get("location", "global")
    peak_rpm = max((pb["peakRpm"] for pb in scoped_breakdown), default=0)
    quota_rpm = max((pb["quotaLimitRpm"] for pb in scoped_breakdown), default=30000)

    five_limit = 500_000_000
    seven_limit = 10_000_000_000
    five_pct = min(100.0, round(tok_5h * 100.0 / five_limit, 1))
    seven_pct = min(100.0, round(tok_7d * 100.0 / seven_limit, 1))
    rpm_pct = min(100.0, round(peak_rpm * 100.0 / max(1, quota_rpm), 1))

    now_iso = datetime.now(timezone.utc).isoformat()

    if record_id == "agy-personal":
        tier_prefix = "Personal / Homelab"
        auth_mode_str = "Google AI / Personal Profile"
        auth_help_str = "Personal & Homelab usage across localhost, server-1, and gpu-node (`agy-personal`)."
    elif record_id == "agy-org":
        tier_prefix = "Organization / Team Cloud"
        auth_mode_str = "Org Profile (org-ai-ops)"
        auth_help_str = "Organization / Team Cloud usage on localhost (`agy-org`)."
    elif record_id == "agy-sandbox":
        tier_prefix = f"Vertex AI ({badge})"
        auth_mode_str = "Vertex AI Sandbox"
        auth_help_str = "Sandbox usage across localhost, net-node-1, net-node-2, server-1, and gpu-node (`agy-sandbox`)."
    else:
        tier_prefix = f"Vertex AI ({badge})"
        auth_mode_str = "Vertex AI Corp"
        auth_help_str = "Enterprise/Work Corporate usage across localhost, net-node-1, and net-node-2 (`agy-enterprise`)."

    return {
        "schemaVersion": 1,
        "id": record_id,
        "provider": record_id,
        "family": "agy",
        "group": "agy",
        "profile": badge,
        "profileId": record_id,
        "profileLabel": badge,
        "name": profile_name,
        "shortLabel": short_label,
        "displayName": display_name,
        "badge": badge,
        "executionScope": "localhost" if localhost_only else "multi-host",
        "localhostOnly": localhost_only,
        "aggregated": aggregated,
        "status": "online",
        "scope": "account",
        "updatedAt": now_iso,
        "fetchedAt": now_iso,
        "ready": True,
        "hasLocalStats": True,
        "hasPromptStats": True,
        "activeModel": act_mod,
        "project": pri_proj,
        "projects": scoped_projs,
        "location": loc,
        "authMode": auth_mode_str,
        "tierLabel": f"{tier_prefix} · Today ${today_cost:,.2f} · 7d ${cost_7d:,.2f} · 30d ${total_cost_30d:,.2f}",
        "usageStatusText": "",
        "authHelpText": auth_help_str,
        "limits": [
            {"label": "Session (5-hour)", "percent": round(five_pct / 100.0, 4), "resetsAt": ""},
            {"label": "Weekly (7-day)", "percent": round(seven_pct / 100.0, 4), "resetsAt": ""},
            {"label": f"Peak RPM ({peak_rpm}/{quota_rpm})", "percent": round(rpm_pct / 100.0, 4), "resetsAt": ""},
        ],
        "sevenDayPct": seven_pct,
        "fiveHourPct": five_pct,
        "costUsd": round(total_cost_30d, 2),
        "thirtyDayCostUsd": round(total_cost_30d, 2),
        "sevenDayCostUsd": round(cost_7d, 2),
        "todayCostUsd": round(today_cost, 2),
        "allTimeCostUsd": round(all_time_cost, 2),
        "todayPrompts": today_prompts,
        "sevenDayPrompts": prompts_7d,
        "todayTokens": today_tokens,
        "todayTotalTokens": today_tokens,
        "todayTokensByModel": today_by_mod,
        "todaySessions": len(sessions_by_day[today_s]),
        "sevenDaySessions": len(sessions_7d),
        "todaySubagentCalls": today_sub_calls,
        "todaySubagentTokens": today_sub_tokens,
        "sevenDayTokens": tok_7d,
        "thirtyDayTokens": tot_30d,
        "totalTokens30d": tot_30d,
        "totalTokens": tot_30d,
        "allTimeTokens": all_time_tokens,
        "totalPrompts30d": prompts_30d,
        "totalPrompts": prompts_30d,
        "allTimePrompts": prompts_all,
        "totalSessions30d": root_convs_30d + sub_convs_30d,
        "totalSessions": root_convs_30d + sub_convs_30d,
        "allTimeSessions": root_convs + sub_convs,
        "totalConversations": root_convs,
        "subagentSessions": sub_convs,
        "totalSteps": total_steps,
        "totalToolCalls": total_tools,
        "activeDays": len(active_dates),
        "activeDates": active_dates,
        "recentDays": recent_days[-14:],
        "modelUsage": model_usage,
        "modelQuotas": model_quotas,
        "workspaceUsage": ws_list,
        "hostsBreakdown": hosts_list,
        "recentConversations": recent_convs[:10],
        "projectsBreakdown": projects_breakdown_field,
        "allProjectsBreakdown": all_proj_breakdown,
        "profilesSummary": family_summary.get("profiles", all_proj_breakdown),
        "aggregation": family_summary,
        "groupTotals": family_summary,
        "cloudUsage": {
            "scope": "shared_gcp_org_projects",
            "note": "Shared GCP project totals across all users/services in the project (Cloud Monitoring has no per-user label).",
            "totalTokens30d": c_tok_30d,
            "totalTokens7d": c_tok_7d,
            "totalTokensToday": c_tok_today,
            "totalRequests30d": c_req_30d,
            "totalRequests7d": c_req_7d,
            "totalRequestsToday": c_req_today,
            "projectCount": len(scoped_projs),
            "projects": scoped_projs,
        },
        "rateLimits": {
            "rpmLimit": quota_rpm,
            "rpmPeak24h": peak_rpm,
            "fiveHourTokens": tok_5h,
            "fiveHourLimit": five_limit,
            "sevenDayTokens": tok_7d,
            "sevenDayLimit": seven_limit,
        },
    }


def collect_agy_profiles(force: bool = False, split_profiles: bool | None = None, rebuild_cache: bool = False) -> dict[str, dict]:
    """Scan local + remote AGY sessions once and build split (`agy-personal`, `agy`, `agy-sandbox`) and combined (`all`) records."""
    if split_profiles is None:
        split_profiles = is_agy_split_enabled()

    meta = resolve_agy_meta()
    dirs, projects = discover_agy_config()
    sessions_map = _scan_all_local_sessions(dirs, rebuild_cache=rebuild_cache)
    cloud = get_cloud_metrics(projects, force=force)

    now = datetime.now()
    today_s = now.strftime("%Y-%m-%d")
    cut_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    cut_7d = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    def _new_stat_bucket():
        return {
            "tokens30d": 0,
            "tokens7d": 0,
            "tokensToday": 0,
            "allTimeTokens": 0,
            "cost30d": 0.0,
            "cost7d": 0.0,
            "costToday": 0.0,
            "allTimeCost": 0.0,
            "prompts30d": 0,
            "promptsToday": 0,
            "sessions30d": set(),
            "sessionsToday": set(),
        }

    local_proj_stats: dict[str, dict] = defaultdict(_new_stat_bucket)
    prof_stats: dict[str, dict] = defaultdict(_new_stat_bucket)

    for cid, entry in sessions_map.items():
        d = entry["data"]
        c_proj = d.get("proj") or meta["primary_proj"]
        c_prof = d.get("profile_id") or ("agy-sandbox" if c_proj == meta["sandbox_proj"] else "agy")
        lp = local_proj_stats[c_proj]
        pp = prof_stats[c_prof]
        s_30d = False
        s_today = False
        for ev in d.get("events", []):
            ts, et, mod, it, ot, ct = ev[:6]
            if not ts:
                continue
            day = _ts_to_day(ts)
            if et == "p":
                p_cnt = it if it > 0 else 1
                if day >= cut_30d:
                    s_30d = True
                    lp["prompts30d"] += p_cnt
                    pp["prompts30d"] += p_cnt
                    if day == today_s:
                        s_today = True
                        lp["promptsToday"] += p_cnt
                        pp["promptsToday"] += p_cnt
            elif et == "u":
                tot = it + ot + ct
                ci, co, cc = _cost_rates(mod)
                ev_cost = (it * ci + ot * co + ct * cc) / 1e6
                lp["allTimeTokens"] += tot
                lp["allTimeCost"] += ev_cost
                pp["allTimeTokens"] += tot
                pp["allTimeCost"] += ev_cost
                if day >= cut_30d:
                    s_30d = True
                    lp["tokens30d"] += tot
                    lp["cost30d"] += ev_cost
                    pp["tokens30d"] += tot
                    pp["cost30d"] += ev_cost
                    if day >= cut_7d:
                        lp["tokens7d"] += tot
                        lp["cost7d"] += ev_cost
                        pp["tokens7d"] += tot
                        pp["cost7d"] += ev_cost
                    if day == today_s:
                        s_today = True
                        lp["tokensToday"] += tot
                        lp["costToday"] += ev_cost
                        pp["tokensToday"] += tot
                        pp["costToday"] += ev_cost
        if s_30d:
            lp["sessions30d"].add(cid)
            pp["sessions30d"].add(cid)
            if s_today:
                lp["sessionsToday"].add(cid)
                pp["sessionsToday"].add(cid)

    all_proj_breakdown = []
    c_tok_30d_all = 0
    for proj in projects:
        pdata = cloud.get(proj, {})
        dtok = pdata.get("daily_tokens", {})
        dreq = pdata.get("daily_reqs", {})
        pt30 = pt7 = ptt = pi30 = po30 = pr30 = pr7 = prt = 0
        pmods: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "inputTokens": 0, "outputTokens": 0, "requests": 0})
        for day, ms in dtok.items():
            if day < cut_30d:
                continue
            for m, (it, ot) in ms.items():
                tot = it + ot
                pt30 += tot
                pi30 += it
                po30 += ot
                if day >= cut_7d:
                    pt7 += tot
                if day == today_s:
                    ptt += tot
                pmods[m]["tokens"] += tot
                pmods[m]["inputTokens"] += it
                pmods[m]["outputTokens"] += ot
        for day, ms in dreq.items():
            if day < cut_30d:
                continue
            for m, rq in ms.items():
                pr30 += rq
                pmods[m]["requests"] += rq
                if day >= cut_7d:
                    pr7 += rq
                if day == today_s:
                    prt += rq
        c_tok_30d_all += pt30
        lp = local_proj_stats[proj]
        all_proj_breakdown.append(
            {
                "project": proj,
                "profileId": "agy-sandbox" if proj == meta["sandbox_proj"] else "agy",
                "scope": "shared_gcp_project",
                "tokens30d": pt30,
                "tokens7d": pt7,
                "tokensToday": ptt,
                "inputTokens30d": pi30,
                "outputTokens30d": po30,
                "requests30d": pr30,
                "requests7d": pr7,
                "requestsToday": prt,
                "localTokens30d": lp["tokens30d"],
                "localTokens7d": lp["tokens7d"],
                "localTokensToday": lp["tokensToday"],
                "localAllTimeTokens": lp["allTimeTokens"],
                "localCostUsd30d": round(lp["cost30d"], 2),
                "localCostUsd7d": round(lp["cost7d"], 2),
                "localCostUsdToday": round(lp["costToday"], 2),
                "localAllTimeCostUsd": round(lp["allTimeCost"], 2),
                "localPrompts30d": lp["prompts30d"],
                "localPromptsToday": lp["promptsToday"],
                "localSessions30d": len(lp["sessions30d"]),
                "localSessionsToday": len(lp["sessionsToday"]),
                "peakRpm": pdata.get("peak_rpm", 0),
                "quotaLimitRpm": pdata.get("quota_rpm", 30000),
                "sharePct": 0.0,
                "models": [{"model": k, **v} for k, v in sorted(pmods.items(), key=lambda x: -x[1]["tokens"])],
            }
        )

    tot_local_30d = sum(pb["localTokens30d"] for pb in all_proj_breakdown)
    for pb in all_proj_breakdown:
        pb["sharePct"] = round(pb["localTokens30d"] * 100.0 / tot_local_30d, 1) if tot_local_30d else 0.0

    sb_proj = meta["sandbox_proj"]
    pri_proj = meta["primary_proj"]
    pers_proj = meta["personal_proj"]
    org_proj = meta["org_proj"]

    profiles_summary_list = []
    for pid, pproj, plabel in [
        ("agy-personal", pers_proj, "Personal / Homelab"),
        ("agy-org", org_proj, "Org (org-ai-ops)"),
        ("agy", pri_proj, "Enterprise / Work Corp"),
        ("agy-sandbox", sb_proj, "Enterprise / Work Sandbox"),
    ]:
        ps = prof_stats[pid]
        profiles_summary_list.append(
            {
                "id": pid,
                "label": plabel,
                "project": pproj,
                "tokens30d": ps["tokens30d"],
                "tokens7d": ps["tokens7d"],
                "tokensToday": ps["tokensToday"],
                "costUsd30d": round(ps["cost30d"], 2),
                "costUsd7d": round(ps["cost7d"], 2),
                "costUsdToday": round(ps["costToday"], 2),
                "prompts30d": ps["prompts30d"],
                "sessions30d": len(ps["sessions30d"]),
            }
        )

    work_cost_30d = round(prof_stats["agy"]["cost30d"] + prof_stats["agy-sandbox"]["cost30d"], 2)
    work_cost_7d = round(prof_stats["agy"]["cost7d"] + prof_stats["agy-sandbox"]["cost7d"], 2)
    work_cost_today = round(prof_stats["agy"]["costToday"] + prof_stats["agy-sandbox"]["costToday"], 2)
    pers_cost_30d = round(prof_stats["agy-personal"]["cost30d"], 2)
    pers_cost_7d = round(prof_stats["agy-personal"]["cost7d"], 2)
    pers_cost_today = round(prof_stats["agy-personal"]["costToday"], 2)
    org_cost_30d = round(prof_stats["agy-org"]["cost30d"], 2)
    org_cost_7d = round(prof_stats["agy-org"]["cost7d"], 2)
    org_cost_today = round(prof_stats["agy-org"]["costToday"], 2)

    localhost_only = is_localhost_only()
    family_summary = {
        "family": "agy",
        "executionScope": "localhost" if localhost_only else "multi-host",
        "localhostOnly": localhost_only,
        "splitProfiles": bool(split_profiles),
        "tokens30d": sum(pb["localTokens30d"] for pb in all_proj_breakdown),
        "tokens7d": sum(pb["localTokens7d"] for pb in all_proj_breakdown),
        "tokensToday": sum(pb["localTokensToday"] for pb in all_proj_breakdown),
        "allTimeTokens": sum(pb["localAllTimeTokens"] for pb in all_proj_breakdown),
        "costUsd30d": round(sum(pb["localCostUsd30d"] for pb in all_proj_breakdown), 2),
        "costUsd7d": round(sum(pb["localCostUsd7d"] for pb in all_proj_breakdown), 2),
        "costUsdToday": round(sum(pb["localCostUsdToday"] for pb in all_proj_breakdown), 2),
        "allTimeCostUsd": round(sum(pb["localAllTimeCostUsd"] for pb in all_proj_breakdown), 2),
        "workCostUsd30d": work_cost_30d,
        "workCostUsd7d": work_cost_7d,
        "workCostUsdToday": work_cost_today,
        "personalCostUsd30d": pers_cost_30d,
        "personalCostUsd7d": pers_cost_7d,
        "personalCostUsdToday": pers_cost_today,
        "orgCostUsd30d": org_cost_30d,
        "orgCostUsd7d": org_cost_7d,
        "orgCostUsdToday": org_cost_today,
        "prompts30d": sum(pb["localPrompts30d"] for pb in all_proj_breakdown),
        "promptsToday": sum(pb["localPromptsToday"] for pb in all_proj_breakdown),
        "sessions30d": sum(pb["localSessions30d"] for pb in all_proj_breakdown),
        "sessionsToday": sum(pb["localSessionsToday"] for pb in all_proj_breakdown),
        "sharedOrgTokens30d": c_tok_30d_all,
        "profiles": profiles_summary_list,
    }

    corp_projects = {p for p in projects if p != sb_proj} or {pri_proj}
    sandbox_projects = {sb_proj}

    rec_personal = _build_agy_record(
        record_id="agy-personal",
        profile_name=meta["personal_label"],
        display_name=meta["personal_display"],
        short_label=meta["personal_short"],
        badge=meta["personal_badge"],
        target_projects=corp_projects,
        sessions_map=sessions_map,
        all_projects=projects,
        cloud=cloud,
        all_proj_breakdown=all_proj_breakdown,
        family_summary=family_summary,
        aggregated=False,
        target_profile_ids={"agy-personal"},
    )
    rec_org = _build_agy_record(
        record_id="agy-org",
        profile_name=meta["org_label"],
        display_name=meta["org_display"],
        short_label=meta["org_short"],
        badge=meta["org_badge"],
        target_projects=corp_projects,
        sessions_map=sessions_map,
        all_projects=projects,
        cloud=cloud,
        all_proj_breakdown=all_proj_breakdown,
        family_summary=family_summary,
        aggregated=False,
        target_profile_ids={"agy-org"},
    )
    rec_corp = _build_agy_record(
        record_id="agy",
        profile_name=meta["primary_label"],
        display_name=meta["primary_display"],
        short_label=meta["primary_short"],
        badge=meta["primary_badge"],
        target_projects=corp_projects,
        sessions_map=sessions_map,
        all_projects=projects,
        cloud=cloud,
        all_proj_breakdown=all_proj_breakdown,
        family_summary=family_summary,
        aggregated=False,
        target_profile_ids={"agy"},
    )
    rec_sandbox = _build_agy_record(
        record_id="agy-sandbox",
        profile_name=meta["sandbox_label"],
        display_name=meta["sandbox_display"],
        short_label=meta["sandbox_short"],
        badge=meta["sandbox_badge"],
        target_projects=sandbox_projects,
        sessions_map=sessions_map,
        all_projects=projects,
        cloud=cloud,
        all_proj_breakdown=all_proj_breakdown,
        family_summary=family_summary,
        aggregated=False,
        target_profile_ids={"agy-sandbox"},
    )
    rec_all = (
        rec_corp
        if split_profiles
        else _build_agy_record(
            record_id="agy",
            profile_name="Antigravity",
            display_name="AGY (Antigravity)",
            short_label="AGY",
            badge="all",
            target_projects=None,
            sessions_map=sessions_map,
            all_projects=projects,
            cloud=cloud,
            all_proj_breakdown=all_proj_breakdown,
            family_summary=family_summary,
            aggregated=True,
            target_profile_ids=None,
        )
    )

    return {
        "agy": rec_corp if split_profiles else rec_all,
        "agy-corp": rec_corp,
        "agy-sandbox": rec_sandbox,
        "agy-personal": rec_personal,
        "agy-org": rec_org,
        "all": rec_all,
        "summary": family_summary,
    }


def collect_agy_data(force: bool = False, profile: str | None = None, split_profiles: bool | None = None) -> dict:
    meta = resolve_agy_meta()
    if profile == "all":
        split_profiles = False
    profiles = collect_agy_profiles(force=force, split_profiles=split_profiles)
    if profile in ("agy-personal", meta["personal_proj"], "personal"):
        return profiles["agy-personal"]
    if profile in ("agy-org", meta["org_proj"], "org"):
        return profiles["agy-org"]
    if profile in ("agy-sandbox", meta["sandbox_proj"], "sandbox"):
        return profiles["agy-sandbox"]
    if profile in ("agy-corp", meta["primary_proj"], "primary", "corp"):
        return profiles["agy-corp"]
    if profile == "all":
        return profiles["all"]
    return profiles["agy"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect AGY usage telemetry.")
    parser.add_argument("--force", action="store_true", help="Force refresh")
    parser.add_argument("--refresh-cloud-only", action="store_true", help="Refresh cloud monitoring cache only and exit")
    parser.add_argument("--rebuild-cache", action="store_true", help="Rebuild local session cache")
    parser.add_argument("--profile", type=str, default=None, help="Target profile (agy, agy-personal, agy-sandbox, all)")
    parser.add_argument("--split-profiles", action="store_true", help="Force split-profile mode")
    parser.add_argument("--no-split-profiles", action="store_true", help="Force aggregated single-profile mode")
    args, _ = parser.parse_known_args()
    if args.refresh_cloud_only:
        _, projs = discover_agy_config()
        get_cloud_metrics(projs, refresh_cloud_sync=True)
        sys.exit(0)
    split_mode = True if args.split_profiles else (False if args.no_split_profiles else None)
    data = collect_agy_data(force=args.force, profile=args.profile, split_profiles=split_mode)
    print(json.dumps(data, indent=2))
