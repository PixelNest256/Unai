![Banner](banner.svg)

Unai is a chat application that builds responses from Python `Skill`s instead of using an LLM.
When a message arrives, Unai tries each Skill in the order defined by `priority.json`, calls the first Skill whose `match()` returns `True`, and then runs that Skill's `respond()` function.
If nothing matches, Unai returns a fixed fallback message.

---

## Features

- Skill-based response routing
- Flask-based web chat UI
- SQLite-backed session storage
- Branching conversation history
  - Regenerate a turn to add a new branch
  - Edit a user message to truncate later turns and create a new branch
  - Switch between branches
- SSE-based progress updates while a Skill is being selected
- Early response selection: Select skill responses as soon as they're ready, even while other skills are still generating
- Response metadata: token count, elapsed time, and tokens/sec
- Skills management page
  - Reorder Skills
  - Enable or disable Skills
  - Import and export Skills as ZIP files
  - Delete Skills
  - Edit `valves` settings
- `/help` and `/help <skill>` slash commands

---

## Screenshot

![Screenshot](screenshot.png)

---

## Requirements

- Python 3.10 or newer
- `pip`

Dependencies are listed in `requirements.txt`.

---

## Setup

### 1. Windows: use the `.bat` scripts

```bat
git clone https://github.com/PixelNest256/Unai.git
cd unai
start.bat
```

`start.bat` creates the virtual environment (if needed), installs dependencies, and starts the app in one step.

The script automatically detects pyenv Python 3.12.0 or falls back to the system Python.

> **Note:** The old `setup_venv.bat` and `run.bat` scripts are deprecated. Use `start.bat` instead.

### 2. Windows: manual setup and run

```bash
git clone https://github.com/PixelNest256/Unai.git
cd unai
python -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

If you prefer `cmd`, use:

```bat
.venv\Scripts\activate.bat
```

Then install dependencies and start the app:

```bash
pip install -r requirements.txt
python app.py
```

### 3. macOS / Linux: manual setup and run

```bash
git clone https://github.com/PixelNest256/Unai.git
cd unai
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

### 4. Open the app
Open `http://localhost:5000` in your browser.

---

## How It Works

Unai's processing flow is straightforward:

1. Check whether the input is a slash command
2. Try each Skill in `skills/priority.json` order
3. Call `respond()` on the first Skill whose `match()` returns `True`
4. Normalize the response into a shared result format and return it to the UI

In the web UI, `/api/chat/sse` streams Skill-selection progress so the frontend can show `matching` and `responding` states.
The response text can be animated token by token on the client side.

---

## Directory Structure

```text
unai/
├── app.py
├── unai_core.py
├── requirements.txt
├── sessions.db
├── settings.json
├── static/
├── templates/
└── skills/
    ├── priority.json
    ├── greeting/
    ├── calc/
    ├── wikipedia/
    ├── ddgs/
    ├── ddgs_chatbot/
    ├── joke/
    └── valves_test/
```

---

## Built-in Skills

| Skill | Purpose | Implementation notes |
|---|---|---|
| `greeting` | Greetings and small talk | Rule-based matching with Levenshtein distance for near-matches |
| `calc` | Calculation | Safe AST-based evaluation; `expand`, `factor`, and `solve` use SymPy |
| `wikipedia` | Wikipedia summaries | Uses English Wikipedia summary API |
| `ddgs` | Search summaries | Summarizes the first DuckDuckGo search result |
| `ddgs_chatbot` | Conversational search | Interactive chat-based search with DuckDuckGo |
| `joke` | Random jokes | Returns a random joke from a predefined list |
| `valves_test` | Development sample | Displays saved `valves` values for Skill |

---

## Skills Page

The `/skills` page supports:

- Searching Skills
- Drag-and-drop reordering
- Enabling and disabling Skills
- Importing Skills from ZIP files
- Exporting Skills to ZIP files
- Deleting Skills
- Editing per-Skill `valves`
- Viewing `help.txt`

### ZIP import format

The ZIP file must contain exactly one top-level folder, and that folder must include at least `skill.py` and `meta.json`.
If `requirements.txt` is present, Unai runs `pip install -r` during import.

---

## Writing a Skill

Add a new Skill under `skills/<skill_id>/`.

### Required files

```text
skills/
└── my_skill/
    ├── skill.py
    └── meta.json
```

### Optional files

| File | Purpose |
|---|---|
| `help.txt` | Help text shown by `/help <skill>` |
| `requirements.txt` | Python dependencies for the Skill |
| `valves.json` | Saved settings written from the UI |

### `skill.py`

At minimum, implement these two functions:

```python
def match(text: str) -> bool:
    return "hello" in text.lower()

def respond(text: str) -> str | None:
    return "Hi there!"
```

- `match()` decides whether the Skill should handle the input
- `respond()` returns the response text
- If `respond()` returns `None`, the Skill is skipped

### `meta.json`

`meta.json` defines the Skill's display metadata.

```json
{
  "name": "My Skill",
  "description": "What this Skill does",
  "author": "your-name",
  "version": "1.0.0"
}
```

If you add `valves`, the Skills page will show editable fields for them.

```json
{
  "name": "My Skill",
  "description": "What this Skill does",
  "author": "your-name",
  "version": "1.0.0",
  "valves": [
    {
      "key": "api_key",
      "label": "API Key",
      "type": "password",
      "description": "Optional setting shown in the UI",
      "default": ""
    }
  ]
}
```

Common `valves` fields:

| Field | Meaning |
|---|---|
| `key` | Storage key |
| `label` | UI label |
| `type` | `text`, `password`, or `number` |
| `description` | Extra help text |
| `default` | Default value |
| `placeholder` | Input placeholder |

---

## Slash Commands

- `/help`
  - Shows the list of enabled Skills and a short summary
- `/help <skill_id>`
  - Shows the target Skill's `help.txt`

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Chat UI |
| `GET` | `/skills` | Skills management page |
| `POST` | `/api/chat` | Normal send. Body: `{ message, session_id }` |
| `POST` | `/api/chat/sse` | Send with SSE progress updates |
| `POST` | `/api/chat/regenerate` | Regenerate a specific turn |
| `POST` | `/api/chat/edit` | Edit a user message and resend |
| `POST` | `/api/chat/switch_branch` | Switch the active branch for a turn |
| `GET` | `/api/sessions` | List sessions |
| `POST` | `/api/sessions` | Create a session |
| `GET` | `/api/sessions/<id>` | Get a session |
| `DELETE` | `/api/sessions/<id>` | Delete a session |
| `POST` | `/api/sessions/<id>/rename` | Rename a session |
| `GET` | `/api/skills` | List Skills |
| `GET` | `/api/skills/<id>/export` | Export a Skill as ZIP |
| `POST` | `/api/skills/import` | Import a Skill ZIP |
| `DELETE` | `/api/skills/<id>` | Delete a Skill |
| `POST` | `/api/skills/toggle` | Enable or disable a Skill |
| `POST` | `/api/skills/reorder` | Update Skill order |
| `GET` | `/api/skills/<id>/help` | Fetch `help.txt` |
| `GET` | `/api/skills/<id>/valves` | Fetch `valves` definitions and saved values |
| `POST` | `/api/skills/<id>/valves` | Update saved `valves` values |
| `GET` | `/api/settings` | Get app settings |
| `POST` | `/api/settings` | Update app settings |

---

## Configuration Files

### `skills/priority.json`

Stores Skill execution order and disabled Skills.

```json
{
  "order": ["greeting", "wikipedia", "ddgs", "ddgs_chatbot", "calc", "joke", "valves_test"],
  "disabled": []
}
```

### `settings.json`

Stores app-wide settings. The current implementation uses `preload_skills`.

```json
{
  "preload_skills": true
}
```

When `preload_skills` is `true`, Unai loads all enabled Skills at startup to reduce the delay before the first response.

---

## Development Notes

- `sessions.db` is SQLite
- `priority.json` is updated from the Skills page
- A Skill works even without `help.txt`
- If `requirements.txt` is present during ZIP import, Unai installs its dependencies
- The current implementation does not enforce external-host restrictions via `request_urls.txt`

---

## License

MIT
