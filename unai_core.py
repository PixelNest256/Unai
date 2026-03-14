#!/usr/bin/env python3
"""
unai_core.py — Unai の中核ロジック

app.py (Web UI) と main.py (CLI) の両方から import して使う。
Skill のロード・実行、priority.json の読み書き、セッション管理、
トークン計算など UI に依存しない共通処理をすべてここに集約する。
"""

import json
import importlib.util
import os
import time
import uuid
import tiktoken
from datetime import datetime

# ─── パス定数 ────────────────────────────────────────────────────

UNAI_DIR      = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR    = os.path.join(UNAI_DIR, "skills")
PRIORITY_FILE = os.path.join(UNAI_DIR, "priority.json")
SESSIONS_FILE = os.path.join(UNAI_DIR, "sessions.json")

# どの Skill にもマッチしなかったときのフォールバックメッセージ
NO_SKILL_MESSAGE = "Sorry, there is no corresponding Skill for that question."

# ─── priority.json ───────────────────────────────────────────────

def load_priority() -> dict:
    with open(PRIORITY_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def save_priority(data: dict):
    with open(PRIORITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Skill ロード ────────────────────────────────────────────────

# モジュールキャッシュ: { skill_name -> module }
# 同一プロセス内では importlib によるファイル読み込みを一度だけ行う。
_skill_cache: dict[str, object] = {}

def load_skill(skill_name: str):
    """skill.py をインポートしてモジュールを返す。キャッシュ済みならそれを返す。"""
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
    priority.json の有効な Skill を全て先読みしてキャッシュに格納する。
    起動時に一度だけ呼ぶことで、最初のリクエストの遅延をなくす。
    ロードできた Skill 名のリストを返す。
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
    キャッシュを無効化する。
    skill_name を指定した場合はその Skill のみ、None の場合は全件削除。
    toggle や reorder 後に呼んで再ロードを促す。
    """
    if skill_name is None:
        _skill_cache.clear()
    else:
        _skill_cache.pop(skill_name, None)

def load_meta(skill_name: str) -> dict:
    """meta.json を読んで辞書を返す。存在しなければデフォルト値。"""
    meta_path = os.path.join(SKILLS_DIR, skill_name, "meta.json")
    if not os.path.exists(meta_path):
        return {"name": skill_name, "description": "", "author": "unknown", "version": "1.0"}
    with open(meta_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def get_all_skills() -> list[dict]:
    """skills/ 以下のすべての Skill のメタ情報リストを返す。"""
    skills = []
    for name in os.listdir(SKILLS_DIR):
        if os.path.isdir(os.path.join(SKILLS_DIR, name)):
            meta = load_meta(name)
            meta["id"] = name
            skills.append(meta)
    return skills

def load_active_skills() -> list[tuple[str, object]]:
    """
    priority.json に従い、有効な Skill を優先順に (name, module) のリストで返す。
    CLI の起動時など、Skill を事前にロードしておきたい場合に使う。
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

# ─── トークン計算 ─────────────────────────────────────────────────

_enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_enc.encode(text))

# ─── 結果辞書の生成 ───────────────────────────────────────────────

def make_result(response: str, skill: str | None, elapsed: float) -> dict:
    """
    process 系関数が返す統一フォーマットの辞書を生成する。

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

# ─── スラッシュコマンド ───────────────────────────────────────────

def process_slash_command(user_input: str) -> dict | None:
    """
    /help などのスラッシュコマンドを処理する。
    マッチした場合は make_result() と同形式の辞書を返す。
    スラッシュコマンドでなければ None を返す。
    """
    if not user_input.startswith("/"):
        return None

    parts   = user_input[1:].strip().split()
    command = parts[0].lower()

    if command == "help":
        start = time.perf_counter()

        if len(parts) == 1:
            # /help — 有効な Skill 一覧を表示
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
            # /help <skill_name> — Skill 個別ヘルプ
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

# ─── メイン処理ループ ─────────────────────────────────────────────

def process(user_input: str) -> dict:
    """
    ユーザー入力を受け取り、マッチした Skill の応答を返す。
    スラッシュコマンドを優先チェックし、次に priority 順で Skill を試す。
    どれもマッチしなかった場合は response=None の辞書を返す。

    戻り値は常に make_result() と同形式の辞書:
    {
        "response":   str | None,
        "skill":      str | None,
        "tokens":     int,
        "elapsed_ms": float,
        "tps":        float,
    }
    """
    # 1. スラッシュコマンド
    slash = process_slash_command(user_input)
    if slash:
        return slash

    # 2. priority 順で Skill を試す
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

    # 3. どれもマッチしなかった
    return {"response": None, "skill": None, "tokens": 0, "elapsed_ms": 0, "tps": 0}

# ─── 進捗付きジェネレーター ──────────────────────────────────────

def process_streamed(user_input: str):
    """
    Skill のマッチング・実行過程をジェネレーターで逐次 yield する。
    各 yield は辞書:
      {"phase": "matching", "skill": name}          # match() 判定中
      {"phase": "responding", "skill": name}        # respond() 呼び出し中
      {"phase": "done", **make_result(...)}           # 完了（通常の結果辞書）
      {"phase": "no_match"}                          # どれもマッチしなかった
    """
    # スラッシュコマンドは進捗なしで即返す
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

# ─── セッション構造ヘルパー ───────────────────────────────────────

def make_branch(user_content: str, bot_result: dict, now: str) -> dict:
    """1 つのブランチオブジェクトを生成して返す。"""
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
    """セッションのアクティブブランチのパスを返す。"""
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
    """旧フォーマット（flat messages リスト）を turns/branches 構造へ変換する。"""
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
