#!/usr/bin/env python3
"""Export lightweight per-host AI session attribution manifest (~10-50 KB).

Writes /home/jfarr/.gemini/antigravity-cli/conversations/.host_manifest_<host>.json
containing host-local AGY presence locks, brain transcripts, history.jsonl IDs,
subagent parent_map from conversation_summaries.db, and host-local Claude sessions.
"""

import json
import os
import re
import socket
import sqlite3
import sys
import time
from pathlib import Path

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def scan_agy(home: Path) -> dict:
    presence: dict[str, int] = {}
    transcripts: dict[str, int] = {}
    history_set: set[str] = set()
    parent_map: dict[str, str] = {}

    for agy_dir in sorted(home.glob(".gemini/antigravity-cli*")):
        if not agy_dir.is_dir():
            continue

        # 1. Active or recent presence locks (not synced by Mutagen)
        pdir = agy_dir / "presence"
        if pdir.is_dir():
            try:
                for lock in pdir.iterdir():
                    if lock.suffix == ".lock" and UUID_RE.match(lock.stem):
                        try:
                            mtime = int(lock.stat().st_mtime)
                            if mtime > presence.get(lock.stem, 0):
                                presence[lock.stem] = mtime
                        except OSError:
                            pass
            except OSError:
                pass

        # 2. Brain .system_generated/logs/transcript.jsonl (excluded from Mutagen agy-brain)
        bdir = agy_dir / "brain"
        if bdir.is_dir():
            try:
                for cid_dir in bdir.iterdir():
                    if not UUID_RE.match(cid_dir.name):
                        continue
                    tfile = cid_dir / ".system_generated" / "logs" / "transcript.jsonl"
                    try:
                        if tfile.exists():
                            mtime = int(tfile.stat().st_mtime)
                            if mtime > transcripts.get(cid_dir.name, 0):
                                transcripts[cid_dir.name] = mtime
                    except OSError:
                        pass
            except OSError:
                pass

        # 3. Host-local history.jsonl
        hfile = agy_dir / "history.jsonl"
        if hfile.is_file():
            try:
                with hfile.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            cid = (
                                obj.get("conversationId")
                                or obj.get("conversation_id")
                                or obj.get("sessionId")
                                or obj.get("id")
                            )
                            if isinstance(cid, str) and UUID_RE.match(cid):
                                history_set.add(cid)
                        except Exception:
                            pass
            except OSError:
                pass

        # 4. Parent-child subagent mapping from host-local conversation_summaries.db
        sfile = agy_dir / "conversation_summaries.db"
        if sfile.is_file():
            conn = None
            try:
                conn = sqlite3.connect(f"file:{sfile}?mode=ro", uri=True, timeout=2.0)
                cur = conn.cursor()
                cur.execute(
                    "SELECT conversation_id, parent_conversation_id "
                    "FROM conversation_summaries "
                    "WHERE parent_conversation_id IS NOT NULL AND parent_conversation_id != ''"
                )
                for cid, pid in cur.fetchall():
                    if (
                        isinstance(cid, str)
                        and isinstance(pid, str)
                        and UUID_RE.match(cid)
                        and UUID_RE.match(pid)
                    ):
                        parent_map[cid] = pid
            except Exception:
                pass
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

    return {
        "presence": presence,
        "transcripts": transcripts,
        "history": sorted(history_set),
        "parent_map": parent_map,
    }


def scan_claude(home: Path) -> dict:
    sessions: dict[str, dict] = {}

    def record(sid: str, mtime: int, dir_name: str) -> None:
        if not UUID_RE.match(sid):
            return
        cur = sessions.get(sid)
        if cur is None or mtime >= cur.get("mtime", 0):
            sessions[sid] = {"mtime": int(mtime), "dir": dir_name}

    claude_dirs = sorted(home.glob(".claude*"))
    work_fiserv = home / "Work" / "fiserv-claude" / ".claude"
    if work_fiserv.is_dir() and not work_fiserv.is_symlink():
        claude_dirs.append(work_fiserv)

    for cdir in claude_dirs:
        if not cdir.is_dir():
            continue
        dir_name = cdir.name

        # 1. Host-local history.jsonl
        hfile = cdir / "history.jsonl"
        if hfile.is_file():
            try:
                fallback_mtime = int(hfile.stat().st_mtime)
                with hfile.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            sid = obj.get("sessionId") or obj.get("conversationId") or obj.get("id")
                            if isinstance(sid, str) and UUID_RE.match(sid):
                                raw_ts = obj.get("timestamp")
                                if isinstance(raw_ts, (int, float)) and raw_ts > 1e11:
                                    mtime = int(raw_ts / 1000)
                                elif isinstance(raw_ts, (int, float)) and raw_ts > 0:
                                    mtime = int(raw_ts)
                                else:
                                    mtime = fallback_mtime
                                record(sid, mtime, dir_name)
                        except Exception:
                            pass
            except OSError:
                pass

        # 2. Host-local session-env and file-history directories (not synced by Mutagen)
        for subdir_name in ("session-env", "file-history", "tasks"):
            sdir = cdir / subdir_name
            if sdir.is_dir():
                try:
                    for entry in sdir.iterdir():
                        if UUID_RE.match(entry.name):
                            try:
                                record(entry.name, int(entry.stat().st_mtime), dir_name)
                            except OSError:
                                pass
                except OSError:
                    pass

        # 3. For non-Mutagen profile directories (.claude-work, .claude-fiserv, .claude-census),
        # all project JSONLs are strictly local to this host.
        pdir = cdir / "projects"
        if dir_name != ".claude" and pdir.is_dir():
            try:
                for jfile in pdir.rglob("*.jsonl"):
                    if "subagents" in jfile.parts:
                        continue
                    if UUID_RE.match(jfile.stem):
                        try:
                            record(jfile.stem, int(jfile.stat().st_mtime), dir_name)
                        except OSError:
                            pass
            except OSError:
                pass
        elif dir_name == ".claude" and pdir.is_dir() and sessions:
            # Refresh mtimes from project JSONL files for sessions already known to be local
            try:
                for jfile in pdir.rglob("*.jsonl"):
                    if "subagents" in jfile.parts:
                        continue
                    if jfile.stem in sessions:
                        try:
                            record(jfile.stem, int(jfile.stat().st_mtime), dir_name)
                        except OSError:
                            pass
            except OSError:
                pass

    return {"sessions": sessions}


def main() -> int:
    home = Path.home()
    host = socket.gethostname().split(".")[0]
    manifest = {
        "host": host,
        "ts": int(time.time()),
        "agy": scan_agy(home),
        "claude": scan_claude(home),
    }

    out_dir = home / ".gemini" / "antigravity-cli" / "conversations"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f".host_manifest_{host}.json"
    tmp_file = out_dir / f".host_manifest_{host}.json.tmp.{os.getpid()}"

    payload = json.dumps(manifest, separators=(",", ":"), sort_keys=True)
    tmp_file.write_text(payload + "\n", encoding="utf-8")
    tmp_file.replace(out_file)

    if "--stdout" in sys.argv:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
