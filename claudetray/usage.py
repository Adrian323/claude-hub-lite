"""Floating usage panel: Claude Code plan limits for this Windows user.

Two sources:
  * cswap (claude-swap, multi-account switcher), when it manages any accounts: one block per
    account, from `cswap list --json`. Click an account's name to switch to it.
  * the logged-in account, always: the OAuth token Claude Code keeps in .credentials.json,
    sent to the endpoint Claude Code's /usage screen uses. Its numbers are the freshest, so
    they replace cswap's for the active account.
The token is never refreshed here (that would race Claude Code's own refresh); an expired
token just says so until Claude Code renews it. The endpoint is rate-limited, so it is asked
every 3 minutes; cswap serves from its own cache and is read every 30 s.

Run: pythonw -m claudetray.usage     Drag to move, X to close.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from .sessions import CLAUDE_DIR, DATA, NO_WINDOW

URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_EVERY_S = 180
POLL_S = 30
PID_FILE = DATA / "usage.pid"
POS_FILE = DATA / "usage.json"
BG, TEXT, DIM, TRACK, ACTIVE = "#1b1d23", "#e8eaed", "#9aa0a6", "#2e323d", "#3ecf6e"


def account() -> str:
    for f in (CLAUDE_DIR / ".claude.json", CLAUDE_DIR.parent / ".claude.json"):
        try:
            a = json.loads(f.read_text(encoding="utf-8")).get("oauthAccount") or {}
            if a.get("emailAddress"):
                return a["emailAddress"]
        except (OSError, ValueError):
            pass
    return os.environ.get("USERNAME", "?")


def fetch() -> tuple[list[dict] | None, str]:
    """Logged-in account: (limits, error). limits: [{label, pct, resets}] in the API's order."""
    try:
        oauth = json.loads((CLAUDE_DIR / ".credentials.json").read_text(encoding="utf-8"))["claudeAiOauth"]
    except (OSError, ValueError, KeyError):
        return None, "Not logged in: run claude and /login"
    if oauth.get("expiresAt", 0) / 1000 < time.time():
        return None, "Login expired: open Claude Code to renew it"
    req = urllib.request.Request(URL, headers={"Authorization": "Bearer " + oauth["accessToken"],
                                               "anthropic-beta": "oauth-2025-04-20", "User-Agent": "claude-hub-lite"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return parse(json.loads(r.read())), ""
    except urllib.error.HTTPError as e:
        return None, {401: "Login expired: open Claude Code to renew it", 429: "Rate limited, retrying"}.get(
            e.code, f"HTTP {e.code}")
    except (OSError, ValueError) as e:
        return None, f"Offline ({type(e).__name__})"


def parse(data: dict) -> list[dict]:
    names = {"session": "5h", "weekly_all": "7d"}
    out = []
    for lim in data.get("limits") or []:
        scope = ((lim.get("scope") or {}).get("model") or {}).get("display_name")
        out.append({"label": scope or names.get(lim.get("kind"), lim.get("kind") or "?"),
                    "pct": float(lim.get("percent") or 0), "resets": lim.get("resets_at")})
    if not out:  # older response shape
        for key, lbl in (("five_hour", "5h"), ("seven_day", "7d")):
            w = data.get(key) or {}
            if w.get("utilization") is not None:
                out.append({"label": lbl, "pct": float(w["utilization"]), "resets": w.get("resets_at")})
    return out


def cswap_exe() -> str | None:
    found = shutil.which("cswap")
    local = Path.home() / ".local" / "bin" / "cswap.exe"
    return found or (str(local) if local.exists() else None)


def cswap_accounts() -> list[dict]:
    """[{email, number, active, limits}] from cswap, [] when it is absent or manages nothing."""
    exe = cswap_exe()
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "list", "--json"], capture_output=True, text=True, timeout=30,
                           creationflags=NO_WINDOW)
        return parse_cswap(json.loads(r.stdout or "{}"))
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def parse_cswap(data: dict) -> list[dict]:
    out = []
    for a in data.get("accounts") or []:
        u = a.get("usage") or {}
        limits = [{"label": lbl, "pct": float(w.get("pct") or 0), "resets": w.get("resetsAt")}
                  for lbl, w in (("5h", u.get("fiveHour")), ("7d", u.get("sevenDay"))) if w]
        limits += [{"label": s.get("name") or "scoped", "pct": float(s.get("pct") or 0), "resets": s.get("resetsAt")}
                   for s in u.get("scoped") or []]
        out.append({"email": a.get("email") or "?", "number": a.get("number"), "active": bool(a.get("active")),
                    "limits": limits})
    return out


def merge(accounts: list[dict], oauth: list[dict] | None, email: str) -> list[dict]:
    """cswap's accounts with the live numbers on the active one; just the live account without cswap."""
    if not accounts:
        return [{"email": email, "number": None, "active": True, "limits": oauth or []}]
    for a in accounts:
        if a["active"] and oauth:
            a["limits"] = oauth
    return accounts


def left(iso: str | None) -> str:
    if not iso:
        return ""
    s = (datetime.fromisoformat(iso.replace("Z", "+00:00")) - datetime.now().astimezone()).total_seconds()
    h = s / 3600
    return f"{round(h / 24)}d" if h > 36 else f"{round(h)}h" if h >= 1 else f"{max(0, int(s // 60))}m"


def bar_color(pct: float) -> str:
    return "#4cc2ff" if pct < 40 else "#f2b84b" if pct < 80 else "#ef5b5b"


class Panel:
    W, ROW = 260, 24

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0, width=self.W, height=60)
        self.canvas.pack()
        self.accounts: list[dict] = []
        self.oauth: list[dict] | None = None
        self.oauth_at = 0.0
        self.error = "Loading..."
        self.headers: list[tuple[int, int, int]] = []  # (y top, y bottom, cswap number) of clickable names
        self._grab = None
        try:
            x, y = json.loads(POS_FILE.read_text())["pos"]
            self.root.geometry(f"+{x}+{y}")
        except (OSError, ValueError, KeyError, TypeError):
            self.root.geometry(f"+{self.root.winfo_screenwidth() - self.W - 40}+60")
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self._poll()
        self._draw_loop()

    def refresh(self, force_oauth: bool = False) -> None:
        def work():
            accounts = cswap_accounts()
            if force_oauth or time.time() - self.oauth_at > OAUTH_EVERY_S:
                limits, err = fetch()
                self.oauth_at = time.time()
                if limits is not None or force_oauth:
                    self.oauth = limits
                self.error = err
            self.root.after(0, self._got, merge(accounts, self.oauth, account()))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self) -> None:
        self.refresh()
        self.root.after(POLL_S * 1000, self._poll)

    def _got(self, accounts) -> None:
        self.accounts = accounts
        self.draw()

    def _draw_loop(self) -> None:
        self.draw()
        self.root.after(30_000, self._draw_loop)

    def draw(self) -> None:
        c, W = self.canvas, self.W
        c.delete("all")
        c.create_text(W - 12, 12, text="✕", fill=DIM, font=("Segoe UI", 10))
        self.headers = []
        y = 13
        many = len(self.accounts) > 1
        for a in self.accounts:
            mark = "● " if many and a["active"] else ""
            c.create_text(10, y, text=mark + a["email"], fill=ACTIVE if mark else DIM, anchor="w",
                          font=("Segoe UI", 9))
            if many and not a["active"] and a["number"] is not None:
                self.headers.append((y - 10, y + 10, a["number"]))
            y += self.ROW - 2
            for lim in a["limits"]:
                pct = min(lim["pct"], 100)
                c.create_text(10, y, text=lim["label"], fill=TEXT, anchor="w", font=("Segoe UI", 9, "bold"))
                c.create_rectangle(70, y - 6, 190, y + 6, fill=TRACK, width=0)
                c.create_rectangle(70, y - 6, 70 + 120 * pct / 100, y + 6, fill=bar_color(pct), width=0)
                c.create_text(196, y, text=f"{round(pct)}%", fill=TEXT, anchor="w", font=("Segoe UI", 9))
                c.create_text(W - 10, y, text=left(lim["resets"]), fill=DIM, anchor="e", font=("Segoe UI", 9))
                y += self.ROW
            y += 4
        if self.error:
            c.create_text(10, y, text=self.error, fill="#f2b84b", anchor="w", font=("Segoe UI", 8))
            y += self.ROW
        c.configure(height=y - 8)

    def _press(self, e) -> None:
        if e.x > self.W - 24 and e.y < 24:  # the X
            self.root.destroy()
            return
        for top, bottom, number in self.headers:
            if top <= e.y <= bottom:
                self.error = f"Switching to account {number}..."
                self.draw()
                exe = cswap_exe()

                def switch():
                    subprocess.run([exe, "switch", str(number)], capture_output=True, timeout=60,
                                   creationflags=NO_WINDOW)
                    self.refresh(force_oauth=True)  # the live numbers now belong to the new account
                threading.Thread(target=switch, daemon=True).start()
                return
        self._grab = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag(self, e) -> None:
        if self._grab:
            self.root.geometry(f"+{e.x_root - self._grab[0]}+{e.y_root - self._grab[1]}")

    def _release(self, _e) -> None:
        if self._grab:
            DATA.mkdir(exist_ok=True)
            POS_FILE.write_text(json.dumps({"pos": [self.root.winfo_x(), self.root.winfo_y()]}))
            self._grab = None


def main() -> None:
    DATA.mkdir(exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    try:
        Panel().root.mainloop()
    finally:
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        r = parse({"limits": [{"kind": "session", "percent": 44, "resets_at": "2099-01-01T00:00:00+00:00"},
                              {"kind": "weekly_scoped", "percent": 0, "scope": {"model": {"display_name": "Fable"}}}]})
        assert [x["label"] for x in r] == ["5h", "Fable"] and r[0]["pct"] == 44.0, r
        assert parse({"five_hour": {"utilization": 10, "resets_at": None}})[0]["label"] == "5h"
        cs = parse_cswap({"accounts": [
            {"number": 2, "email": "a@x", "active": True, "usage": {"fiveHour": {"pct": 1, "resetsAt": None}}},
            {"number": 3, "email": "b@x", "active": False,
             "usage": {"sevenDay": {"pct": 9}, "scoped": [{"name": "Fable", "pct": 0}]}}]})
        assert [x["label"] for x in cs[1]["limits"]] == ["7d", "Fable"]
        m = merge(cs, r, "a@x")
        assert m[0]["limits"] is r and m[1]["limits"][0]["pct"] == 9
        assert merge([], None, "me")[0] == {"email": "me", "number": None, "active": True, "limits": []}
        assert left("2099-01-01T00:00:00Z").endswith("d") and left(None) == ""
        assert bar_color(10) != bar_color(90)
        print("usage self-check ok;", account(), fetch()[1] or "fetch ok;",
              len(cswap_accounts()), "cswap accounts")
    else:
        main()
