"""Live Claude Code consoles, read straight from Claude Code's own files.

Claude Code writes one record per running process to ~/.claude/sessions/<pid>.json:
  {pid, sessionId, cwd, procStart, kind, entrypoint, name, status, ...}
A record whose process is gone, or whose pid now belongs to some other process, is stale.

  open    kind "interactive" + entrypoint "cli": a console window you typed `claude` in
  hidden  any other live record, e.g. a headless `claude -p` another app started
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

import psutil

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SAVED_FILE = DATA / "saved-consoles.json"
NO_WINDOW = 0x08000000
FILETIME_EPOCH = 11644473600  # seconds from 1601-01-01 to 1970-01-01


def _same_process(pid: int, proc_start: str | None) -> bool:
    """The pid is alive, is claude, and (when the record says) started when the record says."""
    try:
        p = psutil.Process(pid)
        if not p.name().lower().startswith("claude"):
            return False
        if proc_start:  # Windows FILETIME of process creation, 100 ns units
            return abs((p.create_time() + FILETIME_EPOCH) - int(proc_start) / 1e7) < 2
        return True
    except (psutil.Error, ValueError):
        return False


def scan() -> list[dict]:
    out = []
    for f in (CLAUDE_DIR / "sessions").glob("*.json"):
        try:
            e = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(e, dict) or not e.get("sessionId") or not e.get("pid"):
            continue
        if _same_process(int(e["pid"]), e.get("procStart")):
            e["open"] = e.get("kind") == "interactive" and e.get("entrypoint") == "cli"
            out.append(e)
    return sorted(out, key=lambda e: (str(e.get("name") or "")).lower())


def label(e: dict) -> str:
    name = _titles(e)[0] if _titles(e) else e["sessionId"][:8]
    project = Path(e.get("cwd") or "").name
    squash = lambda t: "".join(c for c in t.lower() if c.isalnum())
    return f"{name}  ·  {project}" if project and squash(project) not in squash(name) else name


# -- focus -------------------------------------------------------------------

_seen: dict[str, list] = {}  # sessionId -> [bytes read, custom title, ai title]


def _titles(e: dict) -> list[str]:
    """Title candidates, best first: /rename title and Claude's AI title (from the transcript, which
    is also what the terminal window shows), then the record's name. Transcripts are append-only,
    so each poll reads only the bytes added since the last one."""
    st = _seen.setdefault(e["sessionId"], [0, "", ""])
    for f in (CLAUDE_DIR / "projects").glob(f"*/{e['sessionId']}.jsonl"):
        try:
            with open(f, "rb") as fh:
                fh.seek(st[0])
                for raw in fh:
                    if not raw.endswith(b"\n"):
                        break  # half-written line: read it next time
                    st[0] += len(raw)
                    if b'"custom-title"' in raw or b'"ai-title"' in raw:
                        try:
                            r = json.loads(raw)
                        except ValueError:
                            continue
                        st[1] = r.get("customTitle") or st[1]
                        st[2] = r.get("aiTitle") or st[2]
        except OSError:
            pass
    user = e.get("name") if e.get("nameSource") == "user" else ""
    return list(dict.fromkeys(t for t in (st[1], user, st[2], e.get("name")) if t))


def windows() -> list[tuple[int, int, str]]:
    """(hwnd, pid, title) of every visible titled top-level window."""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append((hwnd, pid.value, buf.value))
        return True

    user32.EnumWindows(each, 0)
    return found


def raise_window(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.keybd_event(0x12, 0, 0, 0)  # tap Alt: Windows only lets the last-input process steal focus
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)


def pick(wins: list[tuple[int, int, str]], titles: list[str], pids: set[int]) -> int | None:
    """Claude keeps the terminal title = "<glyph> <session title>", so match the suffix first;
    else a window owned by the process tree (a plain conhost console)."""
    for t in titles:
        for hwnd, _pid, title in wins:
            if title.endswith(t):
                return hwnd
    return next((hwnd for hwnd, pid, _ in wins if pid in pids), None)


def _tree(pid: int) -> list[psutil.Process]:
    """The process and its ancestors up to (not including) explorer, nearest first."""
    try:
        p = psutil.Process(pid)
        return [p] + [a for a in p.parents() if a.name().lower() != "explorer.exe"]
    except psutil.Error:
        return []


def focus(e: dict) -> bool:
    tree = _tree(int(e["pid"]))
    pids = {p.pid for p in tree}
    for p in tree:  # a console window belongs to conhost, a child of the shell
        try:
            pids |= {c.pid for c in p.children()}
        except psutil.Error:
            pass
    hwnd = pick(windows(), _titles(e), pids)
    if hwnd:
        raise_window(hwnd)
    return bool(hwnd)


def owner_text(e: dict) -> str:
    """Who runs a hidden (windowless) session, for an info box."""
    lines = [f"{label(e)} has no console window.", "",
             f"Project: {e.get('cwd') or '?'}", f"Session: {e['sessionId']}", f"claude PID {e['pid']}"]
    for p in _tree(int(e["pid"]))[1:5]:
        try:
            lines.append(f"  started by {p.name()} PID {p.pid}: {' '.join(p.cmdline())[:160]}")
        except psutil.Error:
            pass
    return "\n".join(lines)


# -- save / restore ------------------------------------------------------------

def save(live: list[dict], file: Path = SAVED_FILE) -> int:
    """Snapshot the open consoles. Returns how many; 0 leaves the previous snapshot alone,
    because an empty save would wipe exactly what Restore needs after a reboot."""
    rows = [{"sessionId": e["sessionId"], "cwd": e.get("cwd"), "name": e.get("name")}
            for e in live if e.get("open")]
    if rows:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.with_suffix(".tmp").write_text(json.dumps({"savedAt": time.time(), "sessions": rows}, indent=2),
                                            encoding="utf-8")
        os.replace(file.with_suffix(".tmp"), file)
    return len(rows)


def to_restore(live: list[dict], file: Path = SAVED_FILE) -> tuple[int, list[dict]]:
    """(saved count, saved sessions no live process holds). --resume keeps the session id,
    so a second Restore sees the reopened ones as held and skips them."""
    try:
        saved = json.loads(file.read_text(encoding="utf-8")).get("sessions") or []
    except (OSError, ValueError):
        saved = []
    held = {e["sessionId"] for e in live}
    return len(saved), [s for s in saved if s.get("sessionId") and s["sessionId"] not in held]


# A console opened from inside a Claude session inherits its markers and then thinks it is a
# subagent (and saves no transcript). Hand it a clean environment.
_SESSION_ENV = {"CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH",
                "CLAUDE_CODE_SESSION_ID", "CLAUDE_EFFORT", "AI_AGENT"}


def resume(s: dict) -> None:
    cwd = s.get("cwd") if s.get("cwd") and os.path.isdir(s["cwd"]) else str(Path.home())
    title = "".join(c for c in f"Claude {s.get('name') or s['sessionId'][:8]}" if c.isalnum() or c in " .:()[]-_")
    env = {k: v for k, v in os.environ.items() if k.upper() not in _SESSION_ENV}
    subprocess.Popen(f'cmd.exe /d /c start "{title[:60]}" /D "{cwd}" cmd /k claude --resume {s["sessionId"]}',
                     env=env, cwd=Path.home(), creationflags=NO_WINDOW, stdin=subprocess.DEVNULL, close_fds=True)


if __name__ == "__main__":
    import tempfile
    f = Path(tempfile.mkdtemp()) / "s.json"
    assert to_restore([], f) == (0, [])
    assert save([{"sessionId": "a", "open": False}], f) == 0 and not f.exists(), "empty save must not write"
    assert save([{"sessionId": "a", "cwd": "C:\\x", "name": "A", "open": True},
                 {"sessionId": "b", "open": True}, {"sessionId": "c", "open": False}], f) == 2
    n, todo = to_restore([{"sessionId": "a"}], f)
    assert n == 2 and [s["sessionId"] for s in todo] == ["b"]
    wins = [(1, 50, "✳ Fix the bug"), (2, 60, "Notepad")]
    assert pick(wins, ["Fix the bug"], set()) == 1
    assert pick(wins, ["nope"], {60}) == 2
    assert pick(wins, ["nope"], set()) is None
    assert not _same_process(os.getpid(), None), "python is not claude"
    assert label({"sessionId": "x", "name": "odin-13", "cwd": "C:\\Projects\\Odin"}) == "odin-13"
    print("sessions self-check ok;", len(scan()), "live sessions")
