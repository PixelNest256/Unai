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
import time
import uuid
import tiktoken
from datetime import datetime

# ─── Path constants ────────────────────────────────────────────────────

UNAI_DIR      = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR    = os.path.join(UNAI_DIR, "skills")
PRIORITY_FILE = os.path.join(UNAI_DIR, "priority.json")
SESSIONS_FILE = os.path.join(UNAI_DIR, "sessions.json")

# Fallback message when no Skill matches
NO_SKILL_MESSAGE = "Sorry, there is no corresponding Skill for that question."

# ─── priority.json ───────────────────────────────────────────────

def load_priority() -> dict:
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

# ─── sessions.json ────────────────────────────────────────────────

def load_sessions() -> dict:
    if not os.path.exists(SESSIONS_FILE):
        return {"sessions": []}
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_sessions(data: dict):
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Session structure helpers ───────────────────────────────────────

def make_branch(user_content: str, bot_result: dict, now: str) -> dict:
    """Generate and return one branch object."""
    return {
        "id":         str(uuid.uuid4()),
        "created_at": now,
        "user": {
            "content": user_content,
            "ts":      now,
        },
        "bot": {
            "content":    bot_result["response"],
            "skill":      bot_result.get("skill"),
            "tokens":     bot_result.get("tokens"),
            "elapsed_ms": bot_result.get("elapsed_ms"),
            "tps":        bot_result.get("tps"),
            "ts":         now,
        },
    }

def get_active_path(sess: dict) -> list:
    """Return path of active branch in session."""
    path = []
    for turn in sess.get("turns", []):
        bi       = turn.get("active_branch", 0)
        branches = turn.get("branches", [])
        if branches:
            bi = max(0, min(bi, len(branches) - 1))
            path.append({
                "turn_id":      turn["id"],
                "branch":       branches[bi],
                "branch_index": bi,
                "branch_count": len(branches),
            })
    return path

def migrate_session(sess: dict) -> dict:
    """Convert old format (flat messages list) to turns/branches structure."""
    messages = sess.get("messages", [])
    turns = []
    i = 0
    while i < len(messages):
        u = messages[i]     if i     < len(messages) else None
        b = messages[i + 1] if i + 1 < len(messages) else None
        if u and u.get("role") == "user":
            now = u.get("ts", datetime.now().isoformat(timespec="seconds"))
            bot_result = {
                "response":   b["content"]        if b else "",
                "skill":      b.get("skill")       if b else None,
                "tokens":     b.get("tokens")      if b else 0,
                "elapsed_ms": b.get("elapsed_ms")  if b else 0,
                "tps":        b.get("tps")         if b else 0,
            }
            branch = make_branch(u["content"], bot_result, now)
            turns.append({
                "id":            str(uuid.uuid4()),
                "active_branch": 0,
                "branches":      [branch],
            })
        i += 2
    sess["turns"] = turns
    del sess["messages"]
    return sess
