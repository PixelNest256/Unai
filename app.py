#!/usr/bin/env python3
"""Unai Web UI - Flask server"""

from flask import Flask, request, jsonify, render_template, Response, stream_with_context
import os, uuid, json
from datetime import datetime

from unai_core import (
    process, process_streamed,
    load_priority, save_priority,
    get_all_skills,
    make_branch,
    NO_SKILL_MESSAGE,
    warm_skill_cache, invalidate_skill_cache,
    UNAI_DIR,
    init_db,
    db_list_sessions, db_create_session, db_get_session, db_delete_session, db_rename_session,
    db_append_turn, db_add_branch, db_set_active_branch, db_truncate_turns_after, db_auto_title,
)

app = Flask(__name__)

# Initialize database
init_db()

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
            now = datetime.now().isoformat(timespec="seconds")
            sess = db_get_session(session_id)
            if sess:
                turn_result = db_append_turn(session_id, user_input, final_result, now)
                # Auto-title from first user message
                if sess.get("title") == "New Chat" and len(sess.get("turns", [])) == 0:
                    db_auto_title(session_id, user_input, now)

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
        sess = db_get_session(session_id)
        if sess:
            turn_result = db_append_turn(session_id, user_input, result, now)
            # Auto-title from first user message
            if sess.get("title") == "New Chat" and len(sess.get("turns", [])) == 0:
                db_auto_title(session_id, user_input, now)

    return jsonify(result)


@app.route("/api/chat/regenerate", methods=["POST"])
def regenerate():
    """Re-run the bot on the same user message for a given turn.
    Body: { session_id, turn_id }
    """
    data       = request.get_json()
    session_id = data.get("session_id", "").strip()
    turn_id    = data.get("turn_id", "").strip()

    sess = db_get_session(session_id)
    if not sess:
        return jsonify({"error": "session not found"}), 404

    turn = next((t for t in sess.get("turns", []) if t["turn_id"] == turn_id), None)
    if not turn:
        return jsonify({"error": "turn not found"}), 404

    user_input = turn["branch"]["user"]["content"]

    result = _process_for_web(user_input)
    now    = datetime.now().isoformat(timespec="seconds")
    
    branch_result = db_add_branch(session_id, turn_id, user_input, result, now)

    return jsonify({
        **result,
        "branch_index": branch_result["branch_index"],
        "branch_count": branch_result["branch_count"],
        "branch_id":    branch_result["branch_id"],
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

    sess = db_get_session(session_id)
    if not sess:
        return jsonify({"error": "session not found"}), 404

    turns    = sess.get("turns", [])
    turn_idx = next((i for i, t in enumerate(turns) if t["turn_id"] == turn_id), None)
    if turn_idx is None:
        return jsonify({"error": "turn not found"}), 404

    result = _process_for_web(user_input)
    now    = datetime.now().isoformat(timespec="seconds")
    
    # Truncate turns after this one and add new branch
    db_truncate_turns_after(session_id, turn_id)
    branch_result = db_add_branch(session_id, turn_id, user_input, result, now)

    return jsonify({
        **result,
        "branch_index":    branch_result["branch_index"],
        "branch_count":    branch_result["branch_count"],
        "branch_id":       branch_result["branch_id"],
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

    sess = db_get_session(session_id)
    if not sess:
        return jsonify({"error": "session not found"}), 404

    turn = next((t for t in sess.get("turns", []) if t["turn_id"] == turn_id), None)
    if not turn:
        return jsonify({"error": "turn not found"}), 404

    branch_index = max(0, min(branch_index, turn["branch_count"] - 1))
    branch_result = db_set_active_branch(session_id, turn_id, branch_index)

    return jsonify({
        "branch_index": branch_result["branch_index"],
        "branch_count": branch_result["branch_count"],
        "user_content": branch_result["branch"]["user"]["content"],
        "bot":          branch_result["branch"]["bot"],
    })
# ─── Routes: sessions ────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    return jsonify(db_list_sessions())


@app.route("/api/sessions", methods=["POST"])
def create_session():
    now = datetime.now().isoformat(timespec="seconds")
    sid = str(uuid.uuid4())
    db_create_session(sid, "New Chat", now)
    return jsonify({"id": sid, "title": "New Chat"})


@app.route("/api/sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    sess = db_get_session(session_id)
    if not sess:
        return jsonify({"error": "not found"}), 404
    return jsonify(sess)


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    db_delete_session(session_id)
    return jsonify({"ok": True})


@app.route("/api/sessions/<session_id>/rename", methods=["POST"])
def rename_session(session_id):
    data  = request.get_json()
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "empty title"}), 400
    ok = db_rename_session(session_id, title)
    if not ok:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True, "title": title})

# ─── Routes: skills ────────────────────────────────────────────── ──────────────────────────────────────────────

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
    invalidate_skill_cache(skill_id)  # Reload since enabled/disabled status changed
    warm_skill_cache()                # Immediately re-cache enabled Skills
    return jsonify({"ok": True, "disabled": disabled})


@app.route("/api/skills/reorder", methods=["POST"])
def reorder_skills():
    data      = request.get_json()
    new_order = data.get("order", [])
    priority  = load_priority()
    priority["order"] = new_order
    save_priority(priority)
    warm_skill_cache()  # Cache remains valid after priority change, just re-warm
    return jsonify({"ok": True})

# ─── Routes: skill import / export / delete ──────────────────────

@app.route("/api/skills/<skill_id>/export", methods=["GET"])
def export_skill(skill_id):
    """Export a skill as a ZIP file (excludes __pycache__)."""
    import zipfile, io
    from flask import send_file
    from unai_core import SKILLS_DIR

    skill_dir = os.path.join(SKILLS_DIR, skill_id)
    if not os.path.isdir(skill_dir):
        return jsonify({"error": "skill not found"}), 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(skill_dir):
            # Skip __pycache__
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in files:
                if fname.endswith(".pyc"):
                    continue
                abs_path = os.path.join(root, fname)
                # Arc name: skill_id/relative_path
                rel_path = os.path.relpath(abs_path, os.path.dirname(skill_dir))
                zf.write(abs_path, rel_path)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{skill_id}.zip",
    )


@app.route("/api/skills/import", methods=["POST"])
def import_skill():
    """
    Import a skill from a ZIP upload.
    Expects multipart/form-data with field 'file'.
    The ZIP must contain a top-level directory whose name becomes the skill_id.
    """
    import zipfile, io
    from unai_core import SKILLS_DIR

    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400

    f = request.files["file"]
    if not f.filename.endswith(".zip"):
        return jsonify({"error": "must be a .zip file"}), 400

    try:
        zf = zipfile.ZipFile(io.BytesIO(f.read()))
    except zipfile.BadZipFile:
        return jsonify({"error": "invalid ZIP"}), 400

    names = zf.namelist()
    if not names:
        return jsonify({"error": "empty ZIP"}), 400

    # Derive skill_id from the top-level directory in the ZIP
    top_dirs = {n.split("/")[0] for n in names if n.split("/")[0]}
    if len(top_dirs) != 1:
        return jsonify({"error": "ZIP must contain exactly one top-level folder"}), 400

    skill_id = top_dirs.pop()

    # Validate: must contain skill.py and meta.json at the root level
    required = {f"{skill_id}/skill.py", f"{skill_id}/meta.json"}
    present  = set(names)
    missing  = required - present
    if missing:
        return jsonify({"error": f"ZIP is missing required files: {', '.join(missing)}"}), 400

    # Security: reject path traversal
    for name in names:
        if ".." in name or name.startswith("/"):
            return jsonify({"error": "unsafe path in ZIP"}), 400

    dest_dir = os.path.join(SKILLS_DIR, skill_id)
    already_exists = os.path.isdir(dest_dir)

    zf.extractall(SKILLS_DIR)

    # Refresh skill cache
    invalidate_skill_cache(skill_id)
    priority = load_priority()
    if skill_id not in priority.get("order", []):
        priority.setdefault("order", []).append(skill_id)
        save_priority(priority)
    warm_skill_cache()

    return jsonify({"ok": True, "skill_id": skill_id, "updated": already_exists})


@app.route("/api/skills/<skill_id>", methods=["DELETE"])
def delete_skill(skill_id):
    """Permanently delete a skill directory."""
    import shutil
    from unai_core import SKILLS_DIR

    skill_dir = os.path.join(SKILLS_DIR, skill_id)
    if not os.path.isdir(skill_dir):
        return jsonify({"error": "skill not found"}), 404

    shutil.rmtree(skill_dir)

    # Remove from priority
    priority = load_priority()
    priority["order"]    = [x for x in priority.get("order",    []) if x != skill_id]
    priority["disabled"] = [x for x in priority.get("disabled", []) if x != skill_id]
    save_priority(priority)

    invalidate_skill_cache(skill_id)

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
