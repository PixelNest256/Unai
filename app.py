#!/usr/bin/env python3
"""Unai Web UI - Flask server"""

from flask import Flask, request, jsonify, render_template, Response, stream_with_context
import os, uuid, json
from datetime import datetime

from unai_core import (
    process, process_streamed,
    load_priority, save_priority,
    get_all_skills,
    load_sessions, save_sessions,
    make_branch, get_active_path, migrate_session,
    NO_SKILL_MESSAGE,
    warm_skill_cache, invalidate_skill_cache,
    UNAI_DIR,
)

app = Flask(__name__)

SETTINGS_FILE = os.path.join(UNAI_DIR, "settings.json")

# ─── settings.json helpers ───────────────────────────────────────

def load_settings() -> dict:
    defaults = {"preload_skills": True}
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**defaults, **data}
    except Exception:
        return defaults

def save_settings(data: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── process のラッパー（Web UI 向け） ───────────────────────────

def _process_for_web(user_input: str) -> dict:
    """
    unai_core.process() を呼び、response=None のときは
    NO_SKILL_MESSAGE に差し替えて返す。
    """
    result = process(user_input)
    if result["response"] is None:
        result["response"] = NO_SKILL_MESSAGE
    return result

# ─── SSE: chat with progress ────────────────────────────────────

@app.route("/api/chat/sse", methods=["POST"])
def chat_sse():
    """
    Server-Sent Events エンドポイント。
    Skill マッチング・レスポンス生成の進捗を逐次 SSE で返す。
    Body: { message, session_id }
    """
    data       = request.get_json()
    user_input = data.get("message", "").strip()
    session_id = data.get("session_id", "").strip()

    if not user_input:
        return jsonify({"error": "empty"}), 400

    def generate():
        final_result = None
        for event in process_streamed(user_input):
            if event["phase"] == "done":
                final_result = {k: v for k, v in event.items() if k != "phase"}
                if final_result.get("response") is None:
                    final_result["response"] = NO_SKILL_MESSAGE
            elif event["phase"] == "no_match":
                # どの Skill にもマッチしなかった場合もセッションに保存するため result を作る
                final_result = {
                    "response":   NO_SKILL_MESSAGE,
                    "skill":      None,
                    "tokens":     0,
                    "elapsed_ms": 0,
                    "tps":        0,
                }
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

        # セッション保存
        if final_result and session_id:
            now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            sessions = load_sessions()
            sess = next((s for s in sessions["sessions"] if s["id"] == session_id), None)
            if sess:
                if "messages" in sess and "turns" not in sess:
                    sess = migrate_session(sess)
                branch   = make_branch(user_input, final_result, now)
                new_turn = {
                    "id":            __import__("uuid").uuid4().__str__(),
                    "active_branch": 0,
                    "branches":      [branch],
                }
                sess.setdefault("turns", []).append(new_turn)
                sess["updated_at"] = now
                if sess.get("title") in ("New Chat", "新しいチャット", "") and len(sess["turns"]) == 1:
                    first = user_input[:30] + ("…" if len(user_input) > 30 else "")
                    sess["title"] = first
                for i, s in enumerate(sessions["sessions"]):
                    if s["id"] == session_id:
                        sessions["sessions"][i] = sess
                        break
                save_sessions(sessions)

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ─── Routes: pages ───────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/skills")
def skills_page():
    return render_template("skills.html")

# ─── Routes: app settings ────────────────────────────────────────

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(load_settings())

@app.route("/api/settings", methods=["POST"])
def update_settings():
    data     = request.get_json()
    settings = load_settings()
    settings.update(data)
    save_settings(settings)
    if settings.get("preload_skills"):
        warm_skill_cache()
    return jsonify({"ok": True, **settings})

# ─── Routes: chat ────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    """Normal send. Appends a new turn to the session.
    Body: { message, session_id }
    """
    data       = request.get_json()
    user_input = data.get("message", "").strip()
    session_id = data.get("session_id", "").strip()

    if not user_input:
        return jsonify({"error": "empty"}), 400

    result = _process_for_web(user_input)
    now    = datetime.now().isoformat(timespec="seconds")

    if session_id:
        sessions = load_sessions()
        sess = next((s for s in sessions["sessions"] if s["id"] == session_id), None)
        if sess:
            if "messages" in sess and "turns" not in sess:
                sess = migrate_session(sess)

            branch   = make_branch(user_input, result, now)
            new_turn = {
                "id":            str(uuid.uuid4()),
                "active_branch": 0,
                "branches":      [branch],
            }
            sess.setdefault("turns", []).append(new_turn)
            sess["updated_at"] = now

            # Auto-title from first user message
            if sess.get("title") in ("New Chat", "新しいチャット", "") and len(sess["turns"]) == 1:
                first = user_input[:30] + ("…" if len(user_input) > 30 else "")
                sess["title"] = first

            for i, s in enumerate(sessions["sessions"]):
                if s["id"] == session_id:
                    sessions["sessions"][i] = sess
                    break
            save_sessions(sessions)

    return jsonify(result)


@app.route("/api/chat/regenerate", methods=["POST"])
def regenerate():
    """Re-run the bot on the same user message for a given turn.
    Body: { session_id, turn_id }
    """
    data       = request.get_json()
    session_id = data.get("session_id", "").strip()
    turn_id    = data.get("turn_id", "").strip()

    sessions = load_sessions()
    sess = next((s for s in sessions["sessions"] if s["id"] == session_id), None)
    if not sess:
        return jsonify({"error": "session not found"}), 404

    if "messages" in sess and "turns" not in sess:
        sess = migrate_session(sess)

    turn = next((t for t in sess.get("turns", []) if t["id"] == turn_id), None)
    if not turn:
        return jsonify({"error": "turn not found"}), 404

    active_b   = turn["branches"][turn.get("active_branch", 0)]
    user_input = active_b["user"]["content"]

    result = _process_for_web(user_input)
    now    = datetime.now().isoformat(timespec="seconds")
    branch = make_branch(user_input, result, now)

    turn["branches"].append(branch)
    turn["active_branch"] = len(turn["branches"]) - 1
    sess["updated_at"] = now

    for i, s in enumerate(sessions["sessions"]):
        if s["id"] == session_id:
            sessions["sessions"][i] = sess
            break
    save_sessions(sessions)

    return jsonify({
        **result,
        "branch_index": turn["active_branch"],
        "branch_count": len(turn["branches"]),
        "branch_id":    branch["id"],
    })


@app.route("/api/chat/edit", methods=["POST"])
def edit_message():
    """Re-send with edited user text for a given turn.
    Body: { session_id, turn_id, message }
    """
    data       = request.get_json()
    session_id = data.get("session_id", "").strip()
    turn_id    = data.get("turn_id", "").strip()
    user_input = data.get("message", "").strip()

    if not user_input:
        return jsonify({"error": "empty"}), 400

    sessions = load_sessions()
    sess = next((s for s in sessions["sessions"] if s["id"] == session_id), None)
    if not sess:
        return jsonify({"error": "session not found"}), 404

    if "messages" in sess and "turns" not in sess:
        sess = migrate_session(sess)

    turns    = sess.get("turns", [])
    turn_idx = next((i for i, t in enumerate(turns) if t["id"] == turn_id), None)
    if turn_idx is None:
        return jsonify({"error": "turn not found"}), 404

    result = _process_for_web(user_input)
    now    = datetime.now().isoformat(timespec="seconds")
    branch = make_branch(user_input, result, now)

    turn = turns[turn_idx]
    turn["branches"].append(branch)
    turn["active_branch"] = len(turn["branches"]) - 1

    sess["turns"]      = turns[:turn_idx + 1]
    sess["updated_at"] = now

    for i, s in enumerate(sessions["sessions"]):
        if s["id"] == session_id:
            sessions["sessions"][i] = sess
            break
    save_sessions(sessions)

    return jsonify({
        **result,
        "branch_index":    turn["active_branch"],
        "branch_count":    len(turn["branches"]),
        "branch_id":       branch["id"],
        "truncated_after": turn_id,
    })


@app.route("/api/chat/switch_branch", methods=["POST"])
def switch_branch():
    """Switch the active branch of a turn.
    Body: { session_id, turn_id, branch_index }
    """
    data         = request.get_json()
    session_id   = data.get("session_id", "").strip()
    turn_id      = data.get("turn_id", "").strip()
    branch_index = int(data.get("branch_index", 0))

    sessions = load_sessions()
    sess = next((s for s in sessions["sessions"] if s["id"] == session_id), None)
    if not sess:
        return jsonify({"error": "session not found"}), 404

    turn = next((t for t in sess.get("turns", []) if t["id"] == turn_id), None)
    if not turn:
        return jsonify({"error": "turn not found"}), 404

    branch_index          = max(0, min(branch_index, len(turn["branches"]) - 1))
    turn["active_branch"] = branch_index

    for i, s in enumerate(sessions["sessions"]):
        if s["id"] == session_id:
            sessions["sessions"][i] = sess
            break
    save_sessions(sessions)

    branch = turn["branches"][branch_index]
    return jsonify({
        "branch_index": branch_index,
        "branch_count": len(turn["branches"]),
        "user_content": branch["user"]["content"],
        "bot":          branch["bot"],
    })

# ─── Routes: sessions ────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    sessions = load_sessions()
    result = [
        {
            "id":         s["id"],
            "title":      s.get("title", "New Chat"),
            "created_at": s.get("created_at"),
            "updated_at": s.get("updated_at"),
        }
        for s in sessions["sessions"]
    ]
    result.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return jsonify(result)


@app.route("/api/sessions", methods=["POST"])
def create_session():
    now = datetime.now().isoformat(timespec="seconds")
    new_session = {
        "id":         str(uuid.uuid4()),
        "title":      "New Chat",
        "created_at": now,
        "updated_at": now,
        "turns":      [],
    }
    sessions = load_sessions()
    sessions["sessions"].append(new_session)
    save_sessions(sessions)
    return jsonify({"id": new_session["id"], "title": new_session["title"]})


@app.route("/api/sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    sessions = load_sessions()
    sess = next((s for s in sessions["sessions"] if s["id"] == session_id), None)
    if not sess:
        return jsonify({"error": "not found"}), 404

    if "messages" in sess and "turns" not in sess:
        sess = migrate_session(sess)

    active_path = get_active_path(sess)
    return jsonify({
        "id":         sess["id"],
        "title":      sess.get("title", "New Chat"),
        "updated_at": sess.get("updated_at"),
        "turns":      active_path,
    })


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    sessions = load_sessions()
    sessions["sessions"] = [s for s in sessions["sessions"] if s["id"] != session_id]
    save_sessions(sessions)
    return jsonify({"ok": True})


@app.route("/api/sessions/<session_id>/rename", methods=["POST"])
def rename_session(session_id):
    data  = request.get_json()
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "empty title"}), 400
    sessions = load_sessions()
    sess = next((s for s in sessions["sessions"] if s["id"] == session_id), None)
    if not sess:
        return jsonify({"error": "not found"}), 404
    sess["title"] = title
    save_sessions(sessions)
    return jsonify({"ok": True, "title": title})

# ─── Routes: skills ──────────────────────────────────────────────

@app.route("/api/skills", methods=["GET"])
def skills_list():
    priority   = load_priority()
    all_skills = get_all_skills()
    disabled   = priority.get("disabled", [])
    order      = priority.get("order", [])
    for s in all_skills:
        if s["id"] not in order:
            order.append(s["id"])
    result = []
    for sid in order:
        meta = next((s for s in all_skills if s["id"] == sid), None)
        if meta:
            meta["enabled"] = sid not in disabled
            result.append(meta)
    return jsonify(result)


@app.route("/api/skills/toggle", methods=["POST"])
def toggle_skill():
    data     = request.get_json()
    skill_id = data.get("id")
    priority = load_priority()
    disabled = priority.get("disabled", [])
    if skill_id in disabled:
        disabled.remove(skill_id)
    else:
        disabled.append(skill_id)
    priority["disabled"] = disabled
    save_priority(priority)
    invalidate_skill_cache(skill_id)  # 有効/無効が変わったので再ロードさせる
    warm_skill_cache()                # 有効な Skill を即座に再キャッシュ
    return jsonify({"ok": True, "disabled": disabled})


@app.route("/api/skills/reorder", methods=["POST"])
def reorder_skills():
    data      = request.get_json()
    new_order = data.get("order", [])
    priority  = load_priority()
    priority["order"] = new_order
    save_priority(priority)
    warm_skill_cache()  # 優先順位変更後もキャッシュは有効なので再温めだけ
    return jsonify({"ok": True})

# ─── Entry point ─────────────────────────────────────────────────

if __name__ == "__main__":
    settings = load_settings()
    if settings.get("preload_skills", True):
        loaded = warm_skill_cache()
        print(f"Unai Web UI starting at http://localhost:5000")
        print(f"  Preloaded {len(loaded)} skill(s): {', '.join(loaded)}")
    else:
        print("Unai Web UI starting at http://localhost:5000")
        print("  Skill preloading disabled")
    app.run(debug=False, port=5000)
