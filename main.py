#!/usr/bin/env python3
"""Unai CLI - The community-powered non-AI assistant"""

import sys
import os

from unai_core import load_active_skills, process, SKILLS_DIR

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
GRAY   = "\033[90m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def main():
    print(f"{BOLD}{CYAN}")
    print("  _   _             _  ")
    print(" | | | |_ __   __ _(_) ")
    print(" | | | | '_ \\ / _` | |")
    print(" | |_| | | | | (_| | |")
    print("  \\___/|_| |_|\\__,_|_|")
    print(f"{RESET}")
    print(f"{GRAY}  The community-powered non-AI assistant{RESET}")
    print(f"{GRAY}  un-AI / unai  |  type 'exit' to quit{RESET}\n")

    skills = load_active_skills()

    missing = []
    for name, mod in skills:
        if mod is None:
            missing.append(name)
    for name in missing:
        print(f"{YELLOW}[warn] skill '{name}' not found, skipping{RESET}")

    print(f"{GRAY}Loaded {len(skills)} skill(s): {', '.join(n for n, _ in skills)}{RESET}\n")

    while True:
        try:
            user_input = input(f"{GREEN}You > {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{GRAY}Bye!{RESET}")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print(f"{GRAY}Bye!{RESET}")
            break

        result = process(user_input)

        if result["response"] is None:
            print(f"{CYAN}Unai > {RESET}Sorry, there is no corresponding Skill for that question.\n")
        else:
            print(f"{CYAN}Unai > {RESET}{result['response']}")
            print(
                f"{GRAY}       [{result['skill']}] {result['tokens']} tokens"
                f" | {result['elapsed_ms']:.1f}ms"
                f" | {result['tps']:.1f} t/s{RESET}\n"
            )


if __name__ == "__main__":
    main()
