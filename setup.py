from __future__ import annotations

import ctypes
import itertools
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
APP_PY = BASE_DIR / "app.py"
REQ_TXT = BASE_DIR / "requirements.txt"
VENV_DIR = BASE_DIR / ".venv"
VENV_PY = VENV_DIR / "Scripts" / "python.exe"
MARK_FILE = VENV_DIR / ".setup_complete"


def enable_virtual_terminal() -> None:
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def term_width() -> int:
    return shutil.get_terminal_size((100, 24)).columns


def hr(char: str = "─") -> str:
    return char * max(40, min(term_width() - 2, 110))


def print_panel(title: str, lines: list[str]) -> None:
    width = max(60, min(term_width(), 110))
    inner = width - 4

    def wrap_line(s: str) -> list[str]:
        wrapped = textwrap.wrap(s, width=inner) if s else [""]
        return wrapped or [""]

    title_text = f" {title} "
    if len(title_text) > width - 2:
        title_text = title_text[: width - 5] + "… "
    pad = width - 2 - len(title_text)
    left = pad // 2
    right = pad - left

    print(f"┌{'─' * (width - 2)}┐")
    print(f"│{' ' * left}{title_text}{' ' * right}│")
    print(f"├{'─' * (width - 2)}┤")
    for line in lines:
        for part in wrap_line(line):
            print(f"│ {part.ljust(inner)} │")
    print(f"└{'─' * (width - 2)}┘")


def status_line(label: str, message: str) -> None:
    print(f"  [{label}] {message}")


def select_bootstrap_python() -> Path:
    pyenv_python = Path(os.environ.get("USERPROFILE", "")) / ".pyenv" / "pyenv-win" / "versions" / "3.12.0" / "python.exe"
    if pyenv_python.exists():
        return pyenv_python
    return Path(sys.executable)


def tail_lines(text: list[str], limit: int = 40) -> list[str]:
    return text[-limit:] if len(text) > limit else text


def run_command(title: str, cmd: list[str], cwd: Path | None = None) -> tuple[int, list[str]]:
    width = term_width()
    spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
    output: list[str] = []
    stop_event = threading.Event()

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    def reader() -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            output.append(line.rstrip("\n"))

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    try:
        while proc.poll() is None:
            frame = next(spinner)
            msg = f"{frame} {title}"
            pad = max(0, width - len(msg) - 1)
            sys.stdout.write("\r" + msg + " " * pad)
            sys.stdout.flush()
            time.sleep(0.08)
    finally:
        stop_event.set()

    t.join(timeout=1.0)
    sys.stdout.write("\r" + " " * max(0, width - 1) + "\r")
    sys.stdout.flush()

    return proc.returncode or 0, output


def ensure_paths() -> None:
    if not APP_PY.exists():
        raise FileNotFoundError(f"app.py が見つかりません: {APP_PY}")
    if not REQ_TXT.exists():
        raise FileNotFoundError(f"requirements.txt が見つかりません: {REQ_TXT}")


def create_venv(python: Path) -> None:
    if VENV_PY.exists():
        status_line("OK", "Virtual environment already exists.")
        return

    status_line("INFO", "Creating virtual environment...")
    code, output = run_command("Creating .venv", [str(python), "-m", "venv", str(VENV_DIR)], cwd=BASE_DIR)
    if code != 0:
        print_panel("ERROR", ["Virtual environment creation failed."] + tail_lines(output))
        raise SystemExit(code)
    status_line("OK", "Virtual environment created.")


def upgrade_pip() -> None:
    status_line("INFO", "Upgrading pip...")
    code, output = run_command("Upgrading pip", [str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"], cwd=BASE_DIR)
    if code != 0:
        print_panel("ERROR", ["pip upgrade failed."] + tail_lines(output))
        raise SystemExit(code)
    status_line("OK", "pip upgraded.")


def install_requirements() -> None:
    status_line("INFO", "Installing dependencies...")
    code, output = run_command(
        "Installing requirements",
        [str(VENV_PY), "-m", "pip", "install", "-r", str(REQ_TXT)],
        cwd=BASE_DIR,
    )
    if code != 0:
        print_panel("ERROR", ["Dependency installation failed."] + tail_lines(output))
        raise SystemExit(code)
    status_line("OK", "Dependencies installed.")


def write_marker() -> None:
    MARK_FILE.write_text("setup complete\n", encoding="utf-8")
    status_line("OK", "Setup completion marker written.")


def launch_app() -> None:
    print()
    print_panel(
        "Launching Application",
        [
            f"Python  : {VENV_PY}",
            f"App     : {APP_PY.name}",
            "Status  : starting...",
        ],
    )
    print()

    code = subprocess.call([str(VENV_PY), str(APP_PY)], cwd=str(BASE_DIR))
    raise SystemExit(code)


def main() -> None:
    enable_virtual_terminal()
    clear_screen()

    bootstrap_python = select_bootstrap_python()

    print_panel(
        "Unai Application Launcher",
        [
            f"Project : {BASE_DIR}",
            f"Python  : {bootstrap_python}",
            f"Venv    : {VENV_DIR}",
            f"Marker  : {MARK_FILE.name}",
        ],
    )
    print()

    try:
        ensure_paths()
    except FileNotFoundError as e:
        print_panel("ERROR", [str(e)])
        raise SystemExit(1)

    if VENV_PY.exists() and MARK_FILE.exists():
        status_line("INFO", "Setup already completed. Skipping installation.")
        launch_app()

    status_line("INFO", "Setup required or incomplete. Starting setup...")
    print(hr())
    create_venv(bootstrap_python)
    upgrade_pip()
    install_requirements()
    write_marker()
    print(hr())
    status_line("OK", "Setup complete.")
    print()
    launch_app()


if __name__ == "__main__":
    main()