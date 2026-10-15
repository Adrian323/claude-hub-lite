"""Claude Hub Lite: system-tray icon over this user's running Claude Code consoles.

Right-click menu:
  N consoles, H hidden      (status line)
  N consoles  >             click one to bring its window to the front
  H hidden    >             click one to see what runs it
  Usage App                 toggles the floating usage panel
  AgTop                     htop for Claude sessions (npm i -g @ldegio/agtop)
  Save CLI                  remember the open consoles
  Restore CLI               reopen the saved ones that are not open (claude --resume)
  Source                    this project on GitHub
  Quit Tray

Icon: green while any console is busy, gray otherwise. Rescans every 5 s.
"""
from __future__ import annotations

import ctypes
import logging
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import psutil
import pystray

from . import sessions, usage
from .icons import make_icon
from .sessions import DATA, NO_WINDOW, ROOT

log = logging.getLogger("claudetray")
POLL_S = 5
SOURCE = "https://github.com/Adrian323/claude-hub-lite"
DETACHED = 0x00000008


def message(text: str, title: str = "Claude Hub Lite", flags: int = 0x40) -> int:
    """Native message box (MB_ICONINFORMATION by default), topmost. Blocks the calling thread."""
    return ctypes.windll.user32.MessageBoxW(None, text, title, flags | 0x10000 | 0x40000)


def guarded(fn):
    """One failing click is logged, never kills the tray. Runs off the menu thread."""
    def wrapper(_icon=None, _item=None):  # pystray checks the arity: at most (icon, item)
        def run():
            try:
                fn()
            except Exception:  # noqa: BLE001
                log.exception("%s failed", fn.__name__)
                message(f"{fn.__name__} failed, see {DATA / 'tray.log'}", flags=0x30)
        threading.Thread(target=run, daemon=True).start()
    return wrapper


class Tray:
    def __init__(self) -> None:
        self.live: list[dict] = []
        self.icons = {c: make_icon(c) for c in ("green", "gray")}
        self.stop = threading.Event()
        self.icon = pystray.Icon("ClaudeHubLite", self.icons["gray"], "Claude Hub Lite", menu=self.menu())

    def split(self) -> tuple[list[dict], list[dict]]:
        return [e for e in self.live if e["open"]], [e for e in self.live if not e["open"]]

    def status(self) -> str:
        o, h = self.split()
        return f"{len(o)} consoles, {len(h)} hidden"

    def menu(self) -> pystray.Menu:
        o, h = (sorted(x, key=lambda e: sessions.label(e).lower()) for x in self.split())
        item = pystray.MenuItem
        return pystray.Menu(
            item(self.status(), None, enabled=False),
            item(f"{len(o)} consoles", pystray.Menu(*[item(sessions.label(e), self.on_focus(e)) for e in o]),
                 enabled=bool(o)),
            item(f"{len(h)} hidden", pystray.Menu(*[item(sessions.label(e), self.on_hidden(e)) for e in h]),
                 enabled=bool(h)),
            pystray.Menu.SEPARATOR,
            item("Usage App", guarded(self.on_usage), checked=lambda _: self.usage_pid() is not None),
            item("AgTop", guarded(self.on_agtop)),
            item("Save CLI", guarded(self.on_save)),
            item("Restore CLI", guarded(self.on_restore)),
            pystray.Menu.SEPARATOR,
            item("Source", lambda: webbrowser.open(SOURCE)),
            item("Quit Tray", self.on_quit),
        )

    def poll(self) -> None:
        while not self.stop.is_set():
            try:
                self.live = sessions.scan()
                busy = any(e.get("status") == "busy" for e in self.live if e["open"])
                self.icon.icon = self.icons["green" if busy else "gray"]
                self.icon.title = "Claude Hub Lite: " + self.status()
                self.icon.menu = self.menu()
                self.icon.update_menu()
            except Exception:  # noqa: BLE001
                log.exception("poll failed")
            self.stop.wait(POLL_S)

    # -- consoles ----------------------------------------------------------

    def on_focus(self, e: dict):
        @guarded
        def focus_console():
            if not sessions.focus(e):
                message(f"{sessions.label(e)} is running (PID {e['pid']}) but no window carries its title.")
        return focus_console

    def on_hidden(self, e: dict):
        @guarded
        def hidden_console():
            message(sessions.owner_text(e), "Hidden Claude session")
        return hidden_console

    # -- tools -------------------------------------------------------------

    @staticmethod
    def usage_pid() -> int | None:
        try:
            pid = int(usage.PID_FILE.read_text())
            return pid if psutil.pid_exists(pid) and "python" in psutil.Process(pid).name().lower() else None
        except (OSError, ValueError, psutil.Error):
            return None

    def on_usage(self) -> None:
        pid = self.usage_pid()
        if pid:
            psutil.Process(pid).kill()
            usage.PID_FILE.unlink(missing_ok=True)
        else:
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            subprocess.Popen([str(pythonw if pythonw.exists() else sys.executable), "-m", "claudetray.usage"],
                             cwd=ROOT, creationflags=DETACHED | NO_WINDOW, close_fds=True)

    def on_agtop(self) -> None:
        if not shutil.which("agtop"):
            message("AgTop is not installed. It needs Node.js (https://nodejs.org), then:\n\n"
                    "    npm i -g @ldegio/agtop", flags=0x30)
            return
        subprocess.Popen(["cmd", "/c", "start", "AgTop", "cmd", "/k", "agtop"], creationflags=NO_WINDOW,
                         close_fds=True)

    def on_save(self) -> None:
        n = sessions.save(sessions.scan())
        self.icon.notify(f"Saved {n} open console(s)." if n else "No open consoles to save. "
                         "The previous save is kept.", "Claude Hub Lite")

    def on_restore(self) -> None:
        saved, todo = sessions.to_restore(sessions.scan())
        if not saved:
            message("Nothing saved yet. Click Save CLI first.")
            return
        if not todo:
            message(f"All {saved} saved console(s) are already open.")
            return
        names = "\n".join("  " + (s.get("name") or s["sessionId"][:8]) for s in todo)
        if message(f"Reopen {len(todo)} of {saved} saved console(s)?\n\n{names}", flags=0x24) != 6:  # IDYES
            return
        for s in todo:
            sessions.resume(s)

    def on_quit(self, *_args) -> None:
        self.stop.set()
        self.icon.stop()

    def run(self) -> None:
        threading.Thread(target=self.poll, daemon=True).start()
        self.icon.run()


def main() -> int:
    DATA.mkdir(exist_ok=True)
    logging.basicConfig(filename=DATA / "tray.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    # One tray per user: a named mutex dies with the process, so a crash never leaves it stuck.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, "Local\\ClaudeTray")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return 0
    log.info("start")
    Tray().run()
    return 0
