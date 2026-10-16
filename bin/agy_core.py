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
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request

MODEL_MAP = {
    "MODEL_GOOGLE_GEMINI_PRO_3_1": "gemini-3.1-pro-high",
    "MODEL_GOOGLE_GEMINI_PRO_3_1_LOW": "gemini-3.1-pro-low",
    "MODEL_GOOGLE_GEMINI_PRO_3": "gemini-3-pro",
    "MODEL_GOOGLE_GEMINI_FLASH_3": "gemini-3-flash",
    "MODEL_GOOGLE_GEMINI_FLASH_LITE_3": "gemini-3-flash-lite",
    "MODEL_CLAUDE_4_6_OPUS": "claude-opus-4-6",
    "MODEL_CLAUDE_4_6_SONNET": "claude-sonnet-4-6",
    "MODEL_CLAUDE_4_5_SONNET_THINKING": "claude-sonnet-4-5",
    "MODEL_CLAUDE_4_5_OPUS_THINKING": "claude-opus-4-5",
    "MODEL_CLAUDE_4_5_SONNET": "claude-sonnet-4-5",
}

# Official Vertex AI pricing per 1M tokens: (uncached_input, output, cache_read)
COST_PER_M = {
    "gemini-4-argon": (1.25, 10.0, 0.125),
    "gemini-3.1-pro-high": (1.25, 10.0, 0.125),
    "gemini-3.1-pro-low": (1.25, 10.0, 0.125),
    "gemini-3.1-pro-preview": (1.25, 10.0, 0.125),
    "gemini-3-pro": (1.25, 10.0, 0.125),
    "gemini-2.5-pro": (1.25, 10.0, 0.125),
    "gemini-3.8-flash": (0.15, 0.60, 0.015),
    "gemini-3.7-flash": (0.15, 0.60, 0.015),
    "gemini-3.6-flash": (0.15, 0.60, 0.015),
    "gemini-3.5-flash": (0.15, 0.60, 0.015),
    "gemini-3-flash": (0.15, 0.60, 0.015),
    "gemini-2.5-flash": (0.15, 0.60, 0.015),
    "gemini-3-flash-lite": (0.075, 0.30, 0.0075),
    "gemini-2.5-flash-lite": (0.075, 0.30, 0.0075),
    "claude-opus-4-6": (5.0, 25.0, 0.50),
    "claude-opus-4-5": (5.0, 25.0, 0.50),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-sonnet-4-5": (3.0, 15.0, 0.30),
    "claude-haiku-4-5": (0.80, 4.0, 0.08),
}

# Match only Vertex AI / Google Cloud resource paths (`projects/<id>/locations/...`)
# so local filesystem paths like `/home/user/projects/foo/` are never misattributed.
PROJ_RE = re.compile(r"projects/([a-zA-Z0-9_-]+)/locations/")
PARENT_RE = re.compile(r'parent"?[,\s]+id:\s*"?([0-9a-f-]{36})')


_COST_CACHE: dict[str, tuple[float, float, float]] = {}
_DAY_CACHE: dict[int, str] = {}


def _ts_to_day(ts: int) -> str:
    b = ts // 900
    d = _DAY_CACHE.get(b)
    if d is None:
        d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        _DAY_CACHE[b] = d
    return d


def _cost_rates(model_id: str) -> tuple[float, float, float]:
    cached = _COST_CACHE.get(model_id)
    if cached is not None:
        return cached
    m = (model_id or "").lower()
    if m in COST_PER_M:
        res = COST_PER_M[m]
    elif "flash-lite" in m or "lite" in m:
        res = (0.075, 0.30, 0.0075)
    elif "flash" in m:
        res = (0.15, 0.60, 0.015)
    elif "haiku" in m:
        res = (0.80, 4.0, 0.08)
    elif "sonnet" in m:
        res = (3.0, 15.0, 0.30)
    elif "opus" in m:
        res = (5.0, 25.0, 0.50)
    else:
        res = (1.25, 10.0, 0.125)
    _COST_CACHE[model_id] = res
    return res


def _cost_rates_unused(model_id: str) -> tuple[float, float, float]:
    m = (model_id or "").lower()
    if m in COST_PER_M:
        return COST_PER_M[m]
    if "flash-lite" in m or "lite" in m:
        return (0.075, 0.30, 0.0075)
    if "flash" in m:
        return (0.15, 0.60, 0.015)
    if "haiku" in m:
        return (0.80, 4.0, 0.08)
    if "sonnet" in m:
        return (3.0, 15.0, 0.30)
    if "opus" in m:
        return (5.0, 25.0, 0.50)
    return (1.25, 10.0, 0.125)


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


def load_modular_settings() -> dict:
    """Load modular plugin settings from profiles.json, state settings, or manifest defaults."""
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


def is_agy_split_enabled(settings: dict | None = None) -> bool:
    if settings is None:
        settings = load_modular_settings()
    provs = settings.get("providers") or {}
    if isinstance(provs, dict) and "agy-sandbox" in provs:
        return bool(provs["agy-sandbox"].get("enabled", False))
    enabled_list = settings.get("enabledAgents") or settings.get("enabledProviders") or []
    if isinstance(enabled_list, list) and "agy-sandbox" in enabled_list:
        return True
    return False


def resolve_agy_meta(settings: dict | None = None) -> dict:
    if settings is None:
        settings = load_modular_settings()
    provs = settings.get("providers") or {}
    profs = settings.get("profiles") or {}
    agy_p = {**(profs.get("agy") or {}), **(provs.get("agy") or {})}
    sb_p = {**(profs.get("agy-sandbox") or {}), **(provs.get("agy-sandbox") or {})}

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
        pri_proj = _read_dir_proj(Path.home() / ".gemini/antigravity-cli") or "agy-primary"

    sb_proj = str(sb_p.get("gcpProject") or (sb_p.get("projects") or [""])[0] or sb_p.get("profile") or "").strip()
    if sb_proj in ("", "default", "sandbox", "all"):
        sb_proj = _read_dir_proj(Path.home() / ".gemini/antigravity-cli-sandbox") or "agy-sandbox"

    return {
        "primary_proj": pri_proj,
        "sandbox_proj": sb_proj,
        "primary_label": str(agy_p.get("label") or "AGY"),
        "primary_short": str(agy_p.get("shortLabel") or "AGY"),
        "primary_display": str(agy_p.get("displayName") or "Antigravity (Primary)"),
        "primary_badge": str(agy_p.get("badge") or pri_proj),
        "sandbox_label": str(sb_p.get("label") or "AGY Sandbox"),
        "sandbox_short": str(sb_p.get("shortLabel") or "AGY · Sandbox"),
        "sandbox_display": str(sb_p.get("displayName") or "Antigravity (Sandbox)"),
        "sandbox_badge": str(sb_p.get("badge") or sb_proj),
    }


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
        if not d.exists():
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
        try:
            conn = sqlite3.connect(f"file:{db_p}?mode=ro", uri=True, timeout=2.0)
            row = conn.execute("SELECT data FROM trajectory_metadata_blob LIMIT 1").fetchone()
            if row and row[0]:
                m = _pb(row[0])
                if 5 in m:
                    res["parent"] = _s(m[5][0]).strip()
                if 7 in m:
                    u = _pb(m[7][0])
                    if 1 in u:
                        res["ws"] = Path(urllib.parse.unquote(_s(u[1][0])).replace("file://", "")).name or "global"
            for st, meta, gm in conn.execute("SELECT s.step_type, s.metadata, g.data FROM steps s LEFT JOIN gen_metadata g ON s.idx = g.idx"):
                res["steps"] += 1
                ts = 0
                if meta:
                    mp = _pb(meta)
                    if 1 in mp:
                        tp = _pb(mp[1][0])
                        if 1 in tp and isinstance(tp[1][0], int):
                            ts = tp[1][0]
                if ts > res["ts"]:
                    res["ts"] = ts
                if st == 14:
                    res["prompts"] += 1
                    res["events"].append([ts, "p", "", 0, 0, 0])
                elif st not in (14, 15, 17, 23, 101):
                    res["tools"] += 1
                    res["events"].append([ts, "t", "", 0, 0, 0])
                if gm:
                    gp = _pb(gm)
                    if 1 in gp:
                        s1 = _pb(gp[1][0])
                        if 17 in s1:
                            err_s = _s(s1[17][0])
                            pm = PROJ_RE.search(err_s)
                            if pm and pm.group(1) != "default-cli-project":
                                res["proj"] = pm.group(1)
                                res["explicit_proj"] = True
                        raw_m = _s(s1[19][0]) if 19 in s1 else "MODEL_GOOGLE_GEMINI_PRO_3_1"
                        mod = MODEL_MAP.get(raw_m, raw_m.lower().replace("model_", "").replace("_", "-"))
                        if 4 in s1:
                            u = _pb(s1[4][0])
                            it = u[2][0] if 2 in u and isinstance(u[2][0], int) else 0
                            ot = u[3][0] if 3 in u and isinstance(u[3][0], int) else 0
                            ct = u[5][0] if 5 in u and isinstance(u[5][0], int) else 0
                            if it or ot or ct:
                                res["events"].append([ts, "u", mod, it, ot, ct])
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
                        res["events"].append([ts, "p", "", 0, 0, 0])
                    for tc in obj.get("tool_calls", []):
                        res["tools"] += 1
                        res["events"].append([ts, "t", "", 0, 0, 0])
                        if tc.get("name") == "invoke_subagent":
                            res["events"].append([ts, "sub", "", 0, 0, 0])
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
    tok = _gcloud_token()
    if not tok:
        return json.loads(cp.read_text(encoding="utf-8")).get("projects", {}) if cp.exists() else {}
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
            # Spawn non-blocking background refresh so local telemetry collection never stalls on gcloud
            try:
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


def _scan_all_local_sessions(dirs: list[tuple[Path, str, bool]], rebuild_cache: bool = False) -> dict[str, dict]:
    sc_p = Path.home() / ".cache/omarchy/agy-scan-cache.json"
    sc_p.parent.mkdir(parents=True, exist_ok=True)
    sc = {}
    if not rebuild_cache and sc_p.exists():
        try:
            raw_sc = json.loads(sc_p.read_text(encoding="utf-8"))
            if raw_sc.get("__schema__") == 3:
                sc = raw_sc.get("sessions", {})
        except Exception:
            sc = {}

    cids: dict[str, dict] = {}
    for d, dir_proj, is_dedicated in dirs:
        conv_d, brain_d = d / "conversations", d / "brain"
        if conv_d.exists():
            for f in conv_d.glob("*.db"):
                cid = f.stem
                try:
                    st = f.stat()
                except OSError:
                    continue
                if cid not in cids or st.st_size > cids[cid]["db_sz"]:
                    cids.setdefault(
                        cid,
                        {
                            "db": None,
                            "db_sz": 0,
                            "db_mt": 0,
                            "tr": None,
                            "tr_sz": 0,
                            "tr_mt": 0,
                            "proj": dir_proj,
                            "dedicated": is_dedicated,
                        },
                    )
                    cids[cid].update(
                        {
                            "db": f,
                            "db_sz": st.st_size,
                            "db_mt": int(st.st_mtime),
                            "proj": dir_proj,
                            "dedicated": is_dedicated,
                        }
                    )
        if brain_d.exists():
            for b in brain_d.iterdir():
                if not b.is_dir():
                    continue
                cid = b.name
                tr = b / ".system_generated/logs/transcript.jsonl"
                if tr.exists():
                    try:
                        st = tr.stat()
                    except OSError:
                        continue
                    cids.setdefault(
                        cid,
                        {
                            "db": None,
                            "db_sz": 0,
                            "db_mt": 0,
                            "tr": None,
                            "tr_sz": 0,
                            "tr_mt": 0,
                            "proj": dir_proj,
                            "dedicated": is_dedicated,
                        },
                    )
                    if st.st_size > cids[cid]["tr_sz"]:
                        cids[cid].update({"tr": tr, "tr_sz": st.st_size, "tr_mt": int(st.st_mtime)})

    new_sc: dict[str, dict] = {}
    dirty = False
    for cid, info in cids.items():
        sig = f"{info['db_sz']}:{info['db_mt']}:{info['tr_sz']}:{info['tr_mt']}:{info['proj']}:{int(info['dedicated'])}"
        if cid in sc and sc[cid].get("sig") == sig:
            new_sc[cid] = sc[cid]
        else:
            new_sc[cid] = {
                "sig": sig,
                "data": _parse_session(cid, info["db"], info["tr"], info["proj"], info["dedicated"], sandbox_proj=resolve_agy_meta()["sandbox_proj"]),
            }
            dirty = True

    # Propagate explicit project attribution across parent-child subagent conversation trees
    parent_map: dict[str, str] = {}
    for cid, entry in new_sc.items():
        par = entry["data"].get("parent")
        if par:
            parent_map[cid] = par

    def get_root(c: str) -> str:
        seen = set()
        curr = c
        while curr in parent_map and parent_map[curr] not in seen:
            seen.add(curr)
            curr = parent_map[curr]
        return curr

    tree_proj: dict[str, str] = {}
    for cid, entry in new_sc.items():
        d = entry["data"]
        if d.get("explicit_proj") and d.get("proj"):
            r = get_root(cid)
            if d["proj"] == resolve_agy_meta()["sandbox_proj"] or r not in tree_proj:
                tree_proj[r] = d["proj"]

    for cid, entry in new_sc.items():
        d = entry["data"]
        r = get_root(cid)
        if not d.get("explicit_proj") and r in tree_proj:
            if d.get("proj") != tree_proj[r]:
                d["proj"] = tree_proj[r]
                dirty = True

    if dirty or len(new_sc) != len(sc):
        try:
            sc_p.write_text(json.dumps({"__schema__": 3, "sessions": new_sc}), encoding="utf-8")
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
    ws_stats: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "prompts": 0, "sessions": set(), "last": ""})
    tok_5h = 0
    all_time_tokens = 0
    all_time_cost = 0.0
    recent_convs = []
    sessions_7d: set[str] = set()

    for cid, entry in sessions_map.items():
        d = entry["data"]
        c_proj = d.get("proj") or resolve_agy_meta()["primary_proj"]
        if target_projects is not None and c_proj not in target_projects:
            continue

        is_sub = bool(d.get("parent"))
        if is_sub:
            sub_convs += 1
        else:
            root_convs += 1
        total_steps += d.get("steps", 0)
        total_tools += d.get("tools", 0)
        ws = d.get("ws") or "global"
        c_tok = 0
        c_cost = 0.0
        c_mod = "gemini-3.1-pro-high"
        c_in_30d = False

        for ev in d.get("events", []):
            ts, et, mod, it, ot, ct = ev
            if not ts:
                continue
            day = _ts_to_day(ts)
            if et == "p":
                prompts_all += 1
                if day >= cut_30d:
                    c_in_30d = True
                    prompts_by_day[day] += 1
                    prompts_30d += 1
                    ws_stats[ws]["prompts"] += 1
                    sessions_by_day[day].add(cid)
                    ws_stats[ws]["sessions"].add(cid)
                    if day > ws_stats[ws]["last"]:
                        ws_stats[ws]["last"] = day
                    if day >= cut_7d:
                        prompts_7d += 1
                        sessions_7d.add(cid)
                    if day == today_s:
                        today_prompts += 1
            elif et == "sub" and day == today_s:
                today_sub_calls += 1
            elif et == "u":
                tot = it + ot + ct
                ci, co, cc = _cost_rates(mod)
                ev_cost = (it * ci + ot * co + ct * cc) / 1e6
                c_tok += tot
                c_cost += ev_cost
                all_time_tokens += tot
                all_time_cost += ev_cost
                c_mod = mod
                if day >= cut_30d:
                    c_in_30d = True
                    sessions_by_day[day].add(cid)
                    ws_stats[ws]["sessions"].add(cid)
                    if day > ws_stats[ws]["last"]:
                        ws_stats[ws]["last"] = day
                    local_day_mod[day][mod][0] += it
                    local_day_mod[day][mod][1] += ot
                    local_day_mod[day][mod][2] += ct
                    ws_stats[ws]["tokens"] += tot
                    if day >= cut_7d:
                        sessions_7d.add(cid)
                    if ts >= cut_5h:
                        tok_5h += tot
                    if is_sub and day == today_s:
                        today_sub_tokens += tot

        if c_in_30d:
            if is_sub:
                sub_convs_30d += 1
            else:
                root_convs_30d += 1
        if not is_sub and c_tok > 0:
            recent_convs.append(
                {
                    "id": cid,
                    "title": f"{ws} ({cid[:8]})",
                    "prompts": d.get("prompts", 0),
                    "model": c_mod,
                    "tokens": c_tok,
                    "costUsd": round(c_cost, 2),
                    "project": c_proj,
                    "ts": d.get("ts", 0),
                }
            )
        if is_sub and d.get("ts", 0) > 0 and datetime.fromtimestamp(d["ts"]).strftime("%Y-%m-%d") == today_s:
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
    for m, (it, ot, ct, mcost) in sorted(personal_mod.items(), key=lambda x: -(x[1][0] + x[1][1] + x[1][2])):
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

    # When aggregated across multiple projects, provide a single combined entry in projectsBreakdown
    # so Main.qml does not trigger fallback split-synthesis on an intentionally aggregated record.
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
            "tokens": v["tokens"],
            "prompts": v["prompts"],
            "sessions": len(v["sessions"]),
            "lastActive": v["last"],
        }
        for k, v in sorted(ws_stats.items(), key=lambda x: -x[1]["tokens"])[:12]
    ]

    st_p = (
        Path.home() / ".gemini/antigravity-cli-sandbox/settings.json"
        if record_id == "agy-sandbox"
        else Path.home() / ".gemini/antigravity-cli/settings.json"
    )
    st_cfg = json.loads(st_p.read_text(encoding="utf-8")) if st_p.exists() else {}
    act_mod = st_cfg.get("model", "gemini-3.1-pro-high")
    if model_quotas:
        act_mod = model_quotas[0]["model"]
    pri_proj = scoped_projs[0] if scoped_projs else resolve_agy_meta()["primary_proj"]
    loc = st_cfg.get("gcp", {}).get("location", "global")
    peak_rpm = max((pb["peakRpm"] for pb in scoped_breakdown), default=0)
    quota_rpm = max((pb["quotaLimitRpm"] for pb in scoped_breakdown), default=30000)

    five_limit = 500_000_000
    seven_limit = 10_000_000_000
    five_pct = min(100.0, round(tok_5h * 100.0 / five_limit, 1))
    seven_pct = min(100.0, round(tok_7d * 100.0 / seven_limit, 1))
    rpm_pct = min(100.0, round(peak_rpm * 100.0 / max(1, quota_rpm), 1))

    now_iso = datetime.now(timezone.utc).isoformat()

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
        "executionScope": "localhost",
        "localhostOnly": True,
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
        "authMode": "Vertex AI + Cloud Monitoring",
        "tierLabel": f"Vertex AI ({badge}) · Today ${today_cost:,.2f} · 7d ${cost_7d:,.2f} · 30d ${total_cost_30d:,.2f}",
        "usageStatusText": "",
        "authHelpText": "Personal usage from local AGY sessions on localhost; GCP project telemetry shows shared org-wide quota.",
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
        "recentConversations": recent_convs[:10],
        "projectsBreakdown": projects_breakdown_field,
        "allProjectsBreakdown": all_proj_breakdown,
        "profilesSummary": all_proj_breakdown,
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
    """Scan local AGY sessions once and build both split (`agy`, `agy-sandbox`) and combined (`all`) records."""
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

    local_proj_stats: dict[str, dict] = defaultdict(
        lambda: {
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
    )

    for cid, entry in sessions_map.items():
        d = entry["data"]
        c_proj = d.get("proj") or resolve_agy_meta()["primary_proj"]
        lp = local_proj_stats[c_proj]
        for ev in d.get("events", []):
            ts, et, mod, it, ot, ct = ev
            if not ts:
                continue
            day = _ts_to_day(ts)
            if et == "p":
                if day >= cut_30d:
                    lp["prompts30d"] += 1
                    lp["sessions30d"].add(cid)
                    if day == today_s:
                        lp["promptsToday"] += 1
                        lp["sessionsToday"].add(cid)
            elif et == "u":
                tot = it + ot + ct
                ci, co, cc = _cost_rates(mod)
                ev_cost = (it * ci + ot * co + ct * cc) / 1e6
                lp["allTimeTokens"] += tot
                lp["allTimeCost"] += ev_cost
                if day >= cut_30d:
                    lp["tokens30d"] += tot
                    lp["cost30d"] += ev_cost
                    lp["sessions30d"].add(cid)
                    if day >= cut_7d:
                        lp["tokens7d"] += tot
                        lp["cost7d"] += ev_cost
                    if day == today_s:
                        lp["tokensToday"] += tot
                        lp["costToday"] += ev_cost
                        lp["sessionsToday"].add(cid)

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

    family_summary = {
        "family": "agy",
        "executionScope": "localhost",
        "splitProfiles": bool(split_profiles),
        "tokens30d": sum(pb["localTokens30d"] for pb in all_proj_breakdown),
        "tokens7d": sum(pb["localTokens7d"] for pb in all_proj_breakdown),
        "tokensToday": sum(pb["localTokensToday"] for pb in all_proj_breakdown),
        "allTimeTokens": sum(pb["localAllTimeTokens"] for pb in all_proj_breakdown),
        "costUsd30d": round(sum(pb["localCostUsd30d"] for pb in all_proj_breakdown), 2),
        "costUsd7d": round(sum(pb["localCostUsd7d"] for pb in all_proj_breakdown), 2),
        "costUsdToday": round(sum(pb["localCostUsdToday"] for pb in all_proj_breakdown), 2),
        "allTimeCostUsd": round(sum(pb["localAllTimeCostUsd"] for pb in all_proj_breakdown), 2),
        "prompts30d": sum(pb["localPrompts30d"] for pb in all_proj_breakdown),
        "promptsToday": sum(pb["localPromptsToday"] for pb in all_proj_breakdown),
        "sessions30d": sum(pb["localSessions30d"] for pb in all_proj_breakdown),
        "sessionsToday": sum(pb["localSessionsToday"] for pb in all_proj_breakdown),
        "sharedOrgTokens30d": c_tok_30d_all,
        "profiles": [
            {
                "id": pb["profileId"],
                "project": pb["project"],
                "tokens30d": pb["localTokens30d"],
                "tokens7d": pb["localTokens7d"],
                "tokensToday": pb["localTokensToday"],
                "costUsd30d": pb["localCostUsd30d"],
                "costUsd7d": pb["localCostUsd7d"],
                "costUsdToday": pb["localCostUsdToday"],
                "prompts30d": pb["localPrompts30d"],
                "sessions30d": pb["localSessions30d"],
            }
            for pb in all_proj_breakdown
        ],
    }

    sb_proj = meta["sandbox_proj"]
    pri_proj = meta["primary_proj"]
    corp_projects = {p for p in projects if p != sb_proj} or {pri_proj}
    sandbox_projects = {sb_proj}

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
    )
    rec_all = _build_agy_record(
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
    )

    return {
        "agy": rec_corp if split_profiles else rec_all,
        "agy-corp": rec_corp,
        "agy-sandbox": rec_sandbox,
        "all": rec_all,
        "summary": family_summary,
    }


def collect_agy_data(force: bool = False, profile: str | None = None, split_profiles: bool | None = None) -> dict:
    meta = resolve_agy_meta()
    profiles = collect_agy_profiles(force=force, split_profiles=split_profiles)
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
    parser.add_argument("--rebuild-cache", action="store_true", help="Rebuild SQLite session scan cache")
    parser.add_argument("--refresh-cloud-only", action="store_true", help="Refresh Cloud Monitoring cache and exit")
    parser.add_argument("--profile", default=None, help="Profile to emit (agy, agy-sandbox, all)")
    parser.add_argument("--project", default=None, help="GCP project filter")
    parser.add_argument("--split-profiles", action="store_true", help="Force split-profile mode")
    args, _ = parser.parse_known_args()

    if args.refresh_cloud_only:
        _, projs = discover_agy_config()
        get_cloud_metrics(projs, force=True, refresh_cloud_sync=True)
        sys.exit(0)

    meta = resolve_agy_meta()
    target_prof = args.profile or args.project
    split = True if (args.split_profiles or target_prof in ("agy-sandbox", meta["sandbox_proj"], meta["primary_proj"], "sandbox", "primary")) else None
    profs = collect_agy_profiles(force=args.force, split_profiles=split, rebuild_cache=args.rebuild_cache)
    if target_prof in ("agy-sandbox", meta["sandbox_proj"], "sandbox"):
        out = profs["agy-sandbox"]
    elif target_prof in ("agy-corp", meta["primary_proj"], "primary", "corp"):
        out = profs["agy-corp"]
    elif target_prof == "all":
        out = profs["all"]
    else:
        out = profs["agy"]
    print(json.dumps(out, indent=2))
