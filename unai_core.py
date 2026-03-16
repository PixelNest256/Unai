#!/usr/bin/env python3
"""
unai_core.py — Core logic of Unai

Imported and used by both app.py (Web UI) and main.py (CLI).
All common processing independent of UI is aggregated here:
Skill loading/execution, priority.json read/write, session management,
token calculation, etc.
"""

import json
import importlib.util
import os
import sqlite3
import time
import uuid
import tiktoken
from contextlib import contextmanager
from datetime import datetime

# ─── Path constants ────────────────────────────────────────────────────

UNAI_DIR      = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR    = os.path.join(UNAI_DIR, "skills")
PRIORITY_FILE = os.path.join(SKILLS_DIR, "priority.json")
DB_FILE = os.path.join(UNAI_DIR, "sessions.db")

# Fallback message when no Skill matches
NO_SKILL_MESSAGE = "Sorry, there is no corresponding Skill for that question."

# ─── priority.json ───────────────────────────────────────────────

def _create_default_priority() -> dict:
    """Generate a default priority.json from skill directories found in SKILLS_DIR."""
    order = sorted([
        name for name in os.listdir(SKILLS_DIR)
        if os.path.isdir(os.path.join(SKILLS_DIR, name))
    ])
    data = {"order": order, "disabled": []}
    with open(PRIORITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def load_priority() -> dict:
    if not os.path.exists(PRIORITY_FILE):
        return _create_default_priority()
    with open(PRIORITY_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def save_priority(data: dict):
    with open(PRIORITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Skill loading ────────────────────────────────────────────────

# Module cache: { skill_name -> module }
# File reading by importlib is performed only once within the same process.
_skill_cache: dict[str, object] = {}

def load_skill(skill_name: str):
    """Import skill.py and return the module. Return cached version if already loaded."""
    if skill_name in _skill_cache:
        return _skill_cache[skill_name]
    skill_path = os.path.join(SKILLS_DIR, skill_name, "skill.py")
    if not os.path.exists(skill_path):
        return None
    spec = importlib.util.spec_from_file_location(skill_name, skill_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _skill_cache[skill_name] = mod
    return mod

def warm_skill_cache() -> list[str]:
    """
    Preload all valid Skills from priority.json and store them in cache.
    Called once at startup to eliminate delay for the first request.
    Returns list of loaded Skill names.
    """
    priority = load_priority()
    loaded = []
    for name in priority["order"]:
        if name in priority.get("disabled", []):
            continue
        if load_skill(name) is not None:
            loaded.append(name)
    return loaded

def invalidate_skill_cache(skill_name: str | None = None):
    """
    Invalidate cache.
    If skill_name is specified, only that Skill; if None, delete all.
    Called after toggle or reorder to prompt reloading.
    """
    if skill_name is None:
        _skill_cache.clear()
    else:
        _skill_cache.pop(skill_name, None)

def load_meta(skill_name: str) -> dict:
    """Read meta.json and return dict. Return default values if not exist."""
    meta_path = os.path.join(SKILLS_DIR, skill_name, "meta.json")
    if not os.path.exists(meta_path):
        return {"name": skill_name, "description": "", "author": "unknown", "version": "1.0"}
    with open(meta_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def get_all_skills() -> list[dict]:
    """Return meta information list of all Skills under skills/."""
    skills = []
    for name in os.listdir(SKILLS_DIR):
        if os.path.isdir(os.path.join(SKILLS_DIR, name)):
            meta = load_meta(name)
            meta["id"] = name
            skills.append(meta)
    return skills

def load_active_skills() -> list[tuple[str, object]]:
    """
    Return list of enabled Skills in priority order as (name, module) according to priority.json.
    Used when Skills need to be preloaded, such as CLI startup.
    """
    priority = load_priority()
    skills = []
    for name in priority["order"]:
        if name in priority.get("disabled", []):
            continue
        mod = load_skill(name)
        if mod:
            skills.append((name, mod))
    return skills

# ─── Token calculation ─────────────────────────────────────────────────

_enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_enc.encode(text))

# ─── Result dictionary generation ───────────────────────────────────────────────

def make_result(response: str, skill: str | None, elapsed: float) -> dict:
    """
    Generate unified format dictionary returned by process functions.

    {
        "response":   str,
        "skill":      str | None,
        "tokens":     int,
        "elapsed_ms": float,
        "tps":        float,
    }
    """
    tokens = count_tokens(response)
    tps    = tokens / elapsed if elapsed > 0 else 0.0
    return {
        "response":   response,
        "skill":      skill,
        "tokens":     tokens,
        "elapsed_ms": round(elapsed * 1000, 1),
        "tps":        round(tps, 1),
    }

# ─── Slash commands ───────────────────────────────────────────

def process_slash_command(user_input: str) -> dict | None:
    """
    Process slash commands like /help.
    Return dictionary in same format as make_result() if matched.
    Return None if not a slash command.
    """
    if not user_input.startswith("/"):
        return None

    parts   = user_input[1:].strip().split()
    command = parts[0].lower()

    if command == "help":
        start = time.perf_counter()

        if len(parts) == 1:
            # /help — Show list of enabled Skills
            priority    = load_priority()
            skills_list = []
            for name in priority["order"]:
                if name in priority.get("disabled", []):
                    continue
                meta_file = os.path.join(SKILLS_DIR, name, "meta.json")
                try:
                    with open(meta_file, "r", encoding="utf-8-sig") as f:
                        meta = json.load(f)
                        skills_list.append(
                            f"  {meta.get('name', name):<12} - {meta.get('author', 'unknown')} v{meta.get('version', '?.?.?')}"
                        )
                except Exception:
                    skills_list.append(f"  {name:<12} - unknown v?.?.?")

            skills_text = "\n".join(skills_list)
            response = (
                "Unai is a community-powered non-AI assistant.\n\n"
                "Available Skills:\n"
                f"{skills_text}\n\n"
                "Slash Commands:\n"
                "  /help              - Show this help message\n"
                "  /help {skill_name} - Show detailed help for a specific skill\n\n"
                "You can change skill priorities in priority.json."
            )
            skill_name = "help"

        else:
            # /help <skill_name> — Individual Skill help
            skill_name     = parts[1]
            help_file_path = os.path.join(SKILLS_DIR, skill_name, "help.txt")

            if os.path.exists(help_file_path):
                try:
                    with open(help_file_path, "r", encoding="utf-8-sig") as f:
                        response = f.read().strip() or f"No help information available for skill '{skill_name}'."
                except Exception:
                    response = f"Error reading help file for skill '{skill_name}'."
            else:
                skill_dir = os.path.join(SKILLS_DIR, skill_name)
                response = (
                    f"No help.txt file found for skill '{skill_name}'."
                    if os.path.exists(skill_dir)
                    else f"Skill '{skill_name}' not found."
                )

        elapsed = time.perf_counter() - start
        return make_result(response, skill_name, elapsed)

    return None

# ─── Main processing loop ─────────────────────────────────────────────

def process(user_input: str) -> dict:
    """
    Accept user input and return response from matching Skill.
    Check slash commands first, then try Skills in priority order.
    If nothing matches, return dictionary with response=None.

    Return value is always dictionary in same format as make_result():
    {
        "response":   str | None,
        "skill":      str | None,
        "tokens":     int,
        "elapsed_ms": float,
        "tps":        float,
    }
    """
    # 1. Slash commands
    slash = process_slash_command(user_input)
    if slash:
        return slash

    # 2. Try Skills in priority order
    priority = load_priority()
    for name in priority["order"]:
        if name in priority.get("disabled", []):
            continue
        mod = load_skill(name)
        if mod is None:
            continue
        try:
            if not mod.match(user_input):
                continue
            start    = time.perf_counter()
            response = mod.respond(user_input)
            elapsed  = time.perf_counter() - start
            if response is None:
                continue
            return make_result(response, name, elapsed)
        except Exception:
            continue

    # 3. Nothing matched
    return {"response": None, "skill": None, "tokens": 0, "elapsed_ms": 0, "tps": 0}

# ─── Progress generator ──────────────────────────────────────

def process_streamed(user_input: str):
    """
    Sequentially yield Skill matching/execution process via generator.
    Each yield is a dictionary:
      {"phase": "matching", "skill": name}          # During match() judgment
      {"phase": "responding", "skill": name}        # During respond() call
      {"phase": "done", **make_result(...)}           # Complete (normal result dictionary)
      {"phase": "no_match"}                          # Nothing matched
    """
    # Return slash commands immediately without progress
    slash = process_slash_command(user_input)
    if slash:
        yield {"phase": "done", **slash}
        return

    priority = load_priority()
    for name in priority["order"]:
        if name in priority.get("disabled", []):
            continue
        mod = load_skill(name)
        if mod is None:
            continue
        try:
            yield {"phase": "matching", "skill": name}
            if not mod.match(user_input):
                continue
            yield {"phase": "responding", "skill": name}
            start    = time.perf_counter()
            response = mod.respond(user_input)
            elapsed  = time.perf_counter() - start
            if response is None:
                continue
            yield {"phase": "done", **make_result(response, name, elapsed)}
            return
        except Exception:
            continue

    yield {"phase": "no_match"}

# ─── SQLite: DB init ──────────────────────────────────────────────

def _db_conn() -> sqlite3.Connection:
    """Open (and auto-create) the sessions DB with WAL mode."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def db():
    """Context manager: yields a connection, commits on success, rolls back on error."""
    conn = _db_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Create tables if they do not yet exist. Called once at startup."""
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'New Chat',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS turns (
                id             TEXT PRIMARY KEY,
                session_id     TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                position       INTEGER NOT NULL,
                active_branch  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS branches (
                id            TEXT PRIMARY KEY,
                turn_id       TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
                position      INTEGER NOT NULL,
                created_at    TEXT NOT NULL,
                user_content  TEXT NOT NULL,
                user_ts       TEXT NOT NULL,
                bot_content   TEXT NOT NULL,
                bot_skill     TEXT,
                bot_tokens    INTEGER,
                bot_elapsed   REAL,
                bot_tps       REAL,
                bot_ts        TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_turns_session  ON turns(session_id, position);
            CREATE INDEX IF NOT EXISTS idx_branches_turn  ON branches(turn_id, position);
        """)

# ─── Session structure helper ─────────────────────────────────────

def make_branch(user_content: str, bot_result: dict, now: str) -> dict:
    """In-memory branch dict (used by app.py before/after DB writes)."""
    return {
        "id":         str(uuid.uuid4()),
        "created_at": now,
        "user": {"content": user_content, "ts": now},
        "bot": {
            "content":    bot_result["response"],
            "skill":      bot_result.get("skill"),
            "tokens":     bot_result.get("tokens"),
            "elapsed_ms": bot_result.get("elapsed_ms"),
            "tps":        bot_result.get("tps"),
            "ts":         now,
        },
    }

def _branch_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id":         row["id"],
        "created_at": row["created_at"],
        "user": {"content": row["user_content"], "ts": row["user_ts"]},
        "bot": {
            "content":    row["bot_content"],
            "skill":      row["bot_skill"],
            "tokens":     row["bot_tokens"],
            "elapsed_ms": row["bot_elapsed"],
            "tps":        row["bot_tps"],
            "ts":         row["bot_ts"],
        },
    }

# ─── DB-backed session CRUD ───────────────────────────────────────

def db_list_sessions() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def db_create_session(session_id: str, title: str, now: str):
    with db() as conn:
        conn.execute(
            "INSERT INTO sessions(id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (session_id, title, now, now),
        )

def db_get_session(session_id: str) -> dict | None:
    """Return session + active-path turns, or None."""
    with db() as conn:
        sess_row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if not sess_row:
            return None

        turn_rows = conn.execute(
            "SELECT id, position, active_branch FROM turns WHERE session_id=? ORDER BY position",
            (session_id,),
        ).fetchall()

        active_path = []
        for tr in turn_rows:
            branch_rows = conn.execute(
                "SELECT * FROM branches WHERE turn_id=? ORDER BY position",
                (tr["id"],),
            ).fetchall()
            if not branch_rows:
                continue
            bi = max(0, min(tr["active_branch"], len(branch_rows) - 1))
            active_path.append({
                "turn_id":      tr["id"],
                "branch":       _branch_row_to_dict(branch_rows[bi]),
                "branch_index": bi,
                "branch_count": len(branch_rows),
            })

    return {
        "id":         sess_row["id"],
        "title":      sess_row["title"],
        "created_at": sess_row["created_at"],
        "updated_at": sess_row["updated_at"],
        "turns":      active_path,
    }

def db_delete_session(session_id: str):
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))

def db_rename_session(session_id: str, title: str) -> bool:
    with db() as conn:
        cur = conn.execute(
            "UPDATE sessions SET title=? WHERE id=?", (title, session_id)
        )
    return cur.rowcount > 0

def db_append_turn(session_id: str, user_input: str,
                   bot_result: dict, now: str) -> dict:
    """Append a new turn (one branch) to a session. Returns active-path turn dict."""
    with db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS mx FROM turns WHERE session_id=?",
            (session_id,),
        ).fetchone()
        pos       = row["mx"] + 1
        turn_id   = str(uuid.uuid4())
        branch_id = str(uuid.uuid4())
        bot       = bot_result

        conn.execute(
            "INSERT INTO turns(id, session_id, position, active_branch) VALUES (?,?,?,0)",
            (turn_id, session_id, pos),
        )
        conn.execute(
            """INSERT INTO branches
               (id, turn_id, position, created_at,
                user_content, user_ts,
                bot_content, bot_skill, bot_tokens, bot_elapsed, bot_tps, bot_ts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (branch_id, turn_id, 0, now,
             user_input, now,
             bot.get("response", ""), bot.get("skill"),
             bot.get("tokens"), bot.get("elapsed_ms"), bot.get("tps"), now),
        )
        conn.execute(
            "UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id)
        )

    return {
        "turn_id":      turn_id,
        "branch":       {
            "id": branch_id, "created_at": now,
            "user": {"content": user_input, "ts": now},
            "bot": {
                "content":    bot.get("response", ""),
                "skill":      bot.get("skill"),
                "tokens":     bot.get("tokens"),
                "elapsed_ms": bot.get("elapsed_ms"),
                "tps":        bot.get("tps"),
                "ts":         now,
            },
        },
        "branch_index": 0,
        "branch_count": 1,
    }

def db_add_branch(session_id: str, turn_id: str, user_input: str,
                  bot_result: dict, now: str) -> dict:
    """Append a new branch to an existing turn (regenerate / edit). Returns updated info."""
    with db() as conn:
        agg = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS mx, COUNT(*) AS cnt FROM branches WHERE turn_id=?",
            (turn_id,),
        ).fetchone()
        new_pos   = agg["mx"] + 1
        new_count = agg["cnt"] + 1
        branch_id = str(uuid.uuid4())
        bot       = bot_result

        conn.execute(
            """INSERT INTO branches
               (id, turn_id, position, created_at,
                user_content, user_ts,
                bot_content, bot_skill, bot_tokens, bot_elapsed, bot_tps, bot_ts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (branch_id, turn_id, new_pos, now,
             user_input, now,
             bot.get("response", ""), bot.get("skill"),
             bot.get("tokens"), bot.get("elapsed_ms"), bot.get("tps"), now),
        )
        conn.execute(
            "UPDATE turns SET active_branch=? WHERE id=?", (new_pos, turn_id)
        )
        conn.execute(
            "UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id)
        )

    return {
        "branch_index": new_pos,
        "branch_count": new_count,
        "branch_id":    branch_id,
        "branch": {
            "id": branch_id, "created_at": now,
            "user": {"content": user_input, "ts": now},
            "bot": {
                "content":    bot.get("response", ""),
                "skill":      bot.get("skill"),
                "tokens":     bot.get("tokens"),
                "elapsed_ms": bot.get("elapsed_ms"),
                "tps":        bot.get("tps"),
                "ts":         now,
            },
        },
    }

def db_set_active_branch(session_id: str, turn_id: str, branch_index: int) -> dict | None:
    """Switch active branch of a turn. Returns branch dict or None if invalid."""
    with db() as conn:
        branches = conn.execute(
            "SELECT * FROM branches WHERE turn_id=? ORDER BY position",
            (turn_id,),
        ).fetchall()
        if not branches:
            return None
        bi = max(0, min(branch_index, len(branches) - 1))
        conn.execute("UPDATE turns SET active_branch=? WHERE id=?", (bi, turn_id))

    return {
        "branch_index": bi,
        "branch_count": len(branches),
        "branch":       _branch_row_to_dict(branches[bi]),
    }

def db_truncate_turns_after(session_id: str, turn_id: str):
    """Delete all turns that come positionally after the given turn."""
    with db() as conn:
        pos_row = conn.execute(
            "SELECT position FROM turns WHERE id=? AND session_id=?",
            (turn_id, session_id),
        ).fetchone()
        if pos_row:
            conn.execute(
                "DELETE FROM turns WHERE session_id=? AND position > ?",
                (session_id, pos_row["position"]),
            )

def db_get_turn_active_branch(session_id: str, turn_id: str) -> dict | None:
    """Return the active branch dict of a specific turn."""
    with db() as conn:
        tr = conn.execute(
            "SELECT active_branch FROM turns WHERE id=? AND session_id=?",
            (turn_id, session_id),
        ).fetchone()
        if not tr:
            return None
        branches = conn.execute(
            "SELECT * FROM branches WHERE turn_id=? ORDER BY position",
            (turn_id,),
        ).fetchall()
        if not branches:
            return None
        bi = max(0, min(tr["active_branch"], len(branches) - 1))
        return _branch_row_to_dict(branches[bi])

def db_auto_title(session_id: str, text: str, now: str):
    """Set title from first user message if still 'New Chat'."""
    title = text[:30] + ("..." if len(text) > 30 else "")
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET title=?, updated_at=? WHERE id=? AND title='New Chat'",
            (title, now, session_id),
        )
