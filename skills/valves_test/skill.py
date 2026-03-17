"""valves_test — Displays the Valve values currently saved for this Skill."""

import re
import os
import sys

# Allow importing unai_core regardless of working directory
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_UNAI_DIR  = os.path.dirname(os.path.dirname(_SKILL_DIR))
if _UNAI_DIR not in sys.path:
    sys.path.insert(0, _UNAI_DIR)

from unai_core import load_valves, get_valve_definitions

_TRIGGER = re.compile(r'valves[\s\-_]?test', re.IGNORECASE)

SKILL_ID = "valves_test"


def match(text: str) -> bool:
    return bool(_TRIGGER.search(text))


def respond(text: str) -> str:
    defs   = get_valve_definitions(SKILL_ID)
    values = load_valves(SKILL_ID)

    if not defs:
        return "No Valves are defined for this Skill."

    lines = ["Valves Test — current saved values:\n"]
    for d in defs:
        key   = d["key"]
        label = d.get("label", key)
        vtype = d.get("type", "text")
        val   = values.get(key, "")

        # Mask password values
        if vtype == "password":
            display = ("*" * len(val)) if val else "(not set)"
        else:
            display = repr(val) if val != "" else "(not set)"

        lines.append(f"  {label} [{key}]  ({vtype})")
        lines.append(f"    → {display}")

    return "\n".join(lines)
