"""valves_test — Displays the Valve values currently saved for this Skill."""

import re

_TRIGGER = re.compile(r'valves[\s\-_]?test', re.IGNORECASE)

def match(text: str) -> bool:
    return bool(_TRIGGER.search(text))

def respond(text: str) -> str:
    defs   = get_valve_definitions()
    values = load_valves()

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
