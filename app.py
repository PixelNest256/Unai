#!/usr/bin/env python3
"""Unai Web UI - Flask server"""

from flask import Flask, request, jsonify, render_template, Response, stream_with_context
import os, uuid, json
from datetime import datetime

from unai_core import (
    process, process_streamed,
    load_priority, save_priority,
    get_all_skills,
    NO_SKILL_MESSAGE,
    warm_skill_cache, invalidate_skill_cache,
    UNAI_DIR, SKILLS_DIR,
    init_db,
    db_list_sessions, db_create_session, db_get_session, db_delete_session, db_rename_session,
    db_append_turn, db_add_branch, db_set_active_branch, db_truncate_turns_after, db_auto_title,
    get_valve_definitions, load_valves, save_valves, load_help,
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
    Server-Sent Events endpoint.
    Streams Skill matching/responding progress, then emits all candidate results.
    The client picks one candidate; the chosen result is committed via /api/chat/commit.
    Body: { message, session_id }
    """
    data       = request.get_json()
    user_input = data.get("message", "").strip()
    session_id = data.get("session_id", "").strip()

    if not user_input:
        return jsonify({"error": "empty"}), 400

    def generate():
        candidates = []  # accumulated in arrival order

        for event in process_streamed(user_input):
            phase = event["phase"]

            if phase == "matched_skills":
                # Forward immediately so the UI can render placeholder cards
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

            elif phase == "candidate":
                candidate = {k: v for k, v in event.items() if k != "phase"}
                if candidate.get("response") is None:
                    candidate["response"] = NO_SKILL_MESSAGE
                candidates.append(candidate)
                # Forward each candidate as it arrives so the UI can fill cards progressively
                yield "data: " + json.dumps({"phase": "candidate", **candidate}, ensure_ascii=False) + "\n\n"

            elif phase == "no_match":
                no_match_result = {
                    "response":   NO_SKILL_MESSAGE,
                    "skill":      None,
                    "tokens":     0,
                    "elapsed_ms": 0,
                    "tps":        0,
                }
                if session_id:
                    now  = datetime.now().isoformat(timespec="seconds")
                    sess = db_get_session(session_id)
                    if sess:
                        db_append_turn(session_id, user_input, no_match_result, now)
                        if sess.get("title") == "New Chat" and len(sess.get("turns", [])) == 0:
                            db_auto_title(session_id, user_input, now)
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                return

            elif phase == "done":
                # All candidates have arrived — decide how to finalise
                if len(candidates) == 1:
                    # Single match: auto-commit, no user selection needed
                    result = candidates[0]
                    if session_id:
                        now  = datetime.now().isoformat(timespec="seconds")
                        sess = db_get_session(session_id)
                        if sess:
                            db_append_turn(session_id, user_input, result, now)
                            if sess.get("title") == "New Chat" and len(sess.get("turns", [])) == 0:
                                db_auto_title(session_id, user_input, now)
                    yield "data: " + json.dumps({"phase": "committed", **result}, ensure_ascii=False) + "\n\n"
                elif len(candidates) > 1:
                    # Multiple matches: client picks one, then calls /api/chat/commit
                    yield "data: " + json.dumps({"phase": "pick"}, ensure_ascii=False) + "\n\n"

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


@app.route("/api/chat/commit", methods=["POST"])
def chat_commit():
    """
    Commit a user-selected candidate result to the session.
    Called by the client after the user picks a response from the multi-candidate picker.
    Body: { session_id, message, result: { response, skill, tokens, elapsed_ms, tps } }
    """
    data       = request.get_json()
    session_id = data.get("session_id", "").strip()
    user_input = data.get("message", "").strip()
    result     = data.get("result", {})

    if not user_input or not session_id or not result:
        return jsonify({"error": "missing fields"}), 400

    sess = db_get_session(session_id)
    if not sess:
        return jsonify({"error": "session not found"}), 404

    now = datetime.now().isoformat(timespec="seconds")
    turn_result = db_append_turn(session_id, user_input, result, now)
    if sess.get("title") == "New Chat" and len(sess.get("turns", [])) == 0:
        db_auto_title(session_id, user_input, now)

    return jsonify({"ok": True, "turn": turn_result})


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


def _install_zip_bytes(zip_bytes: bytes) -> dict:
    """
    ZIP バイト列を受け取り、Skill としてインストールする共通ヘルパー。
    戻り値: {"ok": True, "skill_id": ..., "updated": bool, "pip": ...}
            または {"ok": False, "error": str}
    """
    import zipfile, io, subprocess, sys

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return {"ok": False, "error": "invalid ZIP"}

    names = zf.namelist()
    if not names:
        return {"ok": False, "error": "empty ZIP"}

    # トップレベルディレクトリ名が skill_id になる
    top_dirs = {n.split("/")[0] for n in names if n.split("/")[0]}
    if len(top_dirs) != 1:
        return {"ok": False, "error": "ZIP must contain exactly one top-level folder"}

    skill_id = top_dirs.pop()

    # skill.py と meta.json の存在確認
    required = {f"{skill_id}/skill.py", f"{skill_id}/meta.json"}
    present  = set(names)
    missing  = required - present
    if missing:
        return {"ok": False, "error": f"ZIP is missing required files: {', '.join(missing)}"}

    # パストラバーサル対策
    for name in names:
        if ".." in name or name.startswith("/"):
            return {"ok": False, "error": "unsafe path in ZIP"}

    dest_dir       = os.path.join(SKILLS_DIR, skill_id)
    already_exists = os.path.isdir(dest_dir)

    zf.extractall(SKILLS_DIR)

    # requirements.txt があれば pip install
    req_key    = f"{skill_id}/requirements.txt"
    pip_result = None
    if req_key in present:
        req_path = os.path.join(SKILLS_DIR, skill_id, "requirements.txt")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_path,
                 "--break-system-packages"],
                capture_output=True, text=True, timeout=120
            )
            if proc.returncode == 0:
                pip_result = {"ok": True,  "output": proc.stdout.strip()}
            else:
                pip_result = {"ok": False, "output": (proc.stderr or proc.stdout).strip()}
        except subprocess.TimeoutExpired:
            pip_result = {"ok": False, "output": "pip install timed out (120s)"}
        except Exception as e:
            pip_result = {"ok": False, "output": str(e)}

    # スキルキャッシュを更新
    invalidate_skill_cache(skill_id)
    priority = load_priority()
    if skill_id not in priority.get("order", []):
        priority.setdefault("order", []).append(skill_id)
        save_priority(priority)
    warm_skill_cache()

    return {
        "ok":       True,
        "skill_id": skill_id,
        "updated":  already_exists,
        "pip":      pip_result,
    }


@app.route("/api/skills/import", methods=["POST"])
def import_skill():
    """
    Import a skill from a ZIP upload.
    Expects multipart/form-data with field 'file'.
    The ZIP must contain a top-level directory whose name becomes the skill_id.
    """
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400

    f = request.files["file"]
    if not f.filename.endswith(".zip"):
        return jsonify({"error": "must be a .zip file"}), 400

    result = _install_zip_bytes(f.read())
    if not result["ok"]:
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/skills/install-from-url", methods=["POST", "OPTIONS"])
def install_skill_from_url():
    """
    公式サイトの「Install」ボタンから呼び出されるエンドポイント。
    Body: { "url": "<Skill ZIP の直リンク URL>" }

    公式サイト（外部ドメイン）からの fetch() に対応するため CORS ヘッダーを付与する。
    許可するオリジンは app.config["ALLOWED_INSTALL_ORIGIN"] で制御する（デフォルト: "*"）。
    本番では "https://your-official-site.example" のように具体的なオリジンを設定すること。
    """
    import urllib.request as _urlreq

    # ── CORS ヘッダーを付与するヘルパー ──
    def _cors(response):
        origin  = request.headers.get("Origin", "")
        allowed = app.config.get("ALLOWED_INSTALL_ORIGIN", "*")
        if allowed == "*" or origin == allowed:
            response.headers["Access-Control-Allow-Origin"]  = allowed if allowed != "*" else "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Vary"] = "Origin"
        return response

    # Preflight（OPTIONS）リクエストへの応答
    if request.method == "OPTIONS":
        return _cors(app.make_response(("", 204)))

    data = request.get_json(silent=True) or {}
    url  = (data.get("url") or "").strip()

    if not url:
        return _cors(jsonify({"ok": False, "error": "url is required"})), 400

    # https / http のみ許可（file:// などを弾く）
    if not url.startswith(("https://", "http://")):
        return _cors(jsonify({"ok": False, "error": "url must start with https:// or http://"})), 400

    # ZIP をダウンロード（タイムアウト 30 秒、最大 50 MB）
    MAX_BYTES = 50 * 1024 * 1024
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "Unai-Client/1.0"})
        with _urlreq.urlopen(req, timeout=30) as resp:
            zip_bytes = resp.read(MAX_BYTES + 1)
    except Exception as e:
        return _cors(jsonify({"ok": False, "error": f"download failed: {e}"})), 502

    if len(zip_bytes) > MAX_BYTES:
        return _cors(jsonify({"ok": False, "error": "ZIP exceeds 50 MB limit"})), 413

    result = _install_zip_bytes(zip_bytes)
    status = 200 if result["ok"] else 400
    return _cors(jsonify(result)), status


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


# ─── Routes: valves ──────────────────────────────────────────────

@app.route("/api/skills/<skill_id>/valves", methods=["GET"])
def get_valves(skill_id):
    """Return valve definitions and current values for a skill."""
    skill_dir = os.path.join(SKILLS_DIR, skill_id)
    if not os.path.isdir(skill_dir):
        return jsonify({"error": "skill not found"}), 404
    defs   = get_valve_definitions(skill_id)
    values = load_valves(skill_id)
    return jsonify({"definitions": defs, "values": values})


@app.route("/api/skills/<skill_id>/valves", methods=["POST"])
def update_valves(skill_id):
    """Save valve values for a skill."""
    skill_dir = os.path.join(SKILLS_DIR, skill_id)
    if not os.path.isdir(skill_dir):
        return jsonify({"error": "skill not found"}), 404
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({"error": "invalid body"}), 400
    # Only store keys that are defined in the valve definitions
    defs        = get_valve_definitions(skill_id)
    valid_keys  = {v["key"] for v in defs}
    filtered    = {k: v for k, v in data.items() if k in valid_keys}
    save_valves(skill_id, filtered)
    return jsonify({"ok": True, "values": filtered})


@app.route("/api/skills/<skill_id>/help", methods=["GET"])
def get_skill_help(skill_id):
    """Return the help.txt content for a skill."""
    skill_dir = os.path.join(SKILLS_DIR, skill_id)
    if not os.path.isdir(skill_dir):
        return jsonify({"error": "skill not found"}), 404
    return jsonify({"help": load_help(skill_id)})

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
    app.run(debug=False, port=5000, use_reloader=False, use_debugger=False)
