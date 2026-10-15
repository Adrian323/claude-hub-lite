"""Startup entry and restart, called by the .cmd files with the venv's python.

  python -m claudetray.install on        add the Startup shortcut
  python -m claudetray.install off       remove it
  python -m claudetray.install restart   stop any running tray from this folder, start a fresh one
  python -m claudetray.install stop      stop the tray and usage panel

Startup is a plain .lnk in the user's Startup folder pointing at pythonw in this folder's venv.
On purpose, because Bitdefender quarantined the alternatives on the machine this came from:
no script file (.js/.vbs/.bat) in the Startup folder, no Run registry key, no scheduled task,
no -EncodedCommand or -ExecutionPolicy Bypass. A .lnk is inert data, and the code it starts
lives in this folder.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psutil

from .sessions import NO_WINDOW, ROOT

LNK = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/Claude Hub Lite.lnk"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")


def startup_on() -> None:
    from .icons import make_icon
    ico = ROOT / "claudetray.ico"
    make_icon("green").save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    q = lambda p: str(p).replace("'", "''")  # PowerShell single-quote escape
    # WScript.Shell COM is the stock way to write a .lnk; no Add-Type, no P/Invoke.
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(LNK)}');"
                    f"$s.TargetPath='{q(PYTHONW)}';$s.Arguments='-m claudetray';"
                    f"$s.WorkingDirectory='{q(ROOT)}';$s.IconLocation='{q(ico)}';"
                    f"$s.Description='Claude Hub Lite tray';$s.Save()"],
                   check=True, creationflags=NO_WINDOW)
    print("Claude Hub Lite starts with Windows." if LNK.exists() else f"Could not create {LNK}")


def startup_off() -> None:
    LNK.unlink(missing_ok=True)
    print("Claude Hub Lite no longer starts with Windows.")


def ours(p: psutil.Process) -> bool:
    """A tray or usage panel started from this folder, or an AgTop window (cmd /k agtop + its node)."""
    try:
        cmd = p.cmdline()
        if any("agtop" in a.lower() for a in cmd):
            return True
        return "-m" in cmd and any(a.startswith("claudetray") for a in cmd) and Path(p.cwd()) == ROOT
    except (psutil.Error, OSError):
        return False


def stop_others() -> None:
    """Kill every tray / usage panel started from this folder, except this process and its parents
    (the venv's python.exe is a launcher that waits on the real interpreter)."""
    me = psutil.Process()
    keep = {me.pid} | {a.pid for a in me.parents()}
    for p in psutil.process_iter():
        if p.pid not in keep and ours(p):
            try:
                p.kill()
            except psutil.Error:
                pass


def restart() -> None:
    stop_others()
    subprocess.Popen([str(PYTHONW), "-m", "claudetray"], cwd=ROOT, close_fds=True,
                     creationflags=0x00000008 | NO_WINDOW)  # DETACHED_PROCESS
    print("Claude Hub Lite is running: look for its icon in the notification area.")


if __name__ == "__main__":
    {"on": startup_on, "off": startup_off, "restart": restart, "stop": stop_others}[sys.argv[1] if len(sys.argv) > 1 else "on"]()
