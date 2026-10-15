"""Adds (or with --uninstall removes) the "Claude Hub Lite" shortcut in the user's Startup folder.
Called by install.cmd / uninstall.cmd with the venv's python."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .sessions import NO_WINDOW, ROOT

LNK = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/Claude Hub Lite.lnk"


def main() -> None:
    if "--uninstall" in sys.argv:
        LNK.unlink(missing_ok=True)
        print("Removed", LNK)
        return
    from .icons import make_icon
    ico = ROOT / "claudetray.ico"
    make_icon("green").save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    q = lambda p: str(p).replace("'", "''")  # PowerShell single-quote escape
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(LNK)}');"
                    f"$s.TargetPath='{q(pythonw)}';$s.Arguments='-m claudetray';"
                    f"$s.WorkingDirectory='{q(ROOT)}';$s.IconLocation='{q(ico)}';$s.Save()"],
                   check=True, creationflags=NO_WINDOW)
    print("Starts with Windows:", LNK)


if __name__ == "__main__":
    main()
