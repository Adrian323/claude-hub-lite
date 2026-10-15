"""Floating usage panel for whoever is logged in to Claude Code on this Windows account.

Reads the OAuth token Claude Code keeps in ~/.claude/.credentials.json and asks the same
endpoint Claude Code's /usage screen uses. It never refreshes the token itself (that would
race Claude Code's own refresh); an expired token just says so until Claude Code renews it.
The endpoint is rate-limited, so it is polled every 3 minutes, countdowns tick locally.

Run: pythonw -m claudetray.usage     Drag to move, X to close.
"""
from __future__ import annotations

import json
import os
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime

from .sessions import CLAUDE_DIR, DATA

URL = "https://api.anthropic.com/api/oauth/usage"
POLL_S = 180
PID_FILE = DATA / "usage.pid"
POS_FILE = DATA / "usage.json"
BG, TEXT, DIM, TRACK = "#1b1d23", "#e8eaed", "#9aa0a6", "#2e323d"


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
    """(limits, error). limits: [{label, pct, resets}] in the API's order."""
    try:
        oauth = json.loads((CLAUDE_DIR / ".credentials.json").read_text(encoding="utf-8"))["claudeAiOauth"]
    except (OSError, ValueError, KeyError):
        return None, "Not logged in: run claude and /login"
    if oauth.get("expiresAt", 0) / 1000 < time.time():
        return None, "Login expired: open Claude Code to renew it"
    req = urllib.request.Request(URL, headers={"Authorization": "Bearer " + oauth["accessToken"],
                                               "anthropic-beta": "oauth-2025-04-20", "User-Agent": "claude-tray"})
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


def left(iso: str | None) -> str:
    if not iso:
        return ""
    s = (datetime.fromisoformat(iso.replace("Z", "+00:00")) - datetime.now().astimezone()).total_seconds()
    h = s / 3600
    return f"{round(h / 24)}d" if h > 36 else f"{round(h)}h" if h >= 1 else f"{max(0, int(s // 60))}m"


def bar_color(pct: float) -> str:
    return "#4cc2ff" if pct < 40 else "#f2b84b" if pct < 80 else "#ef5b5b"


class Panel:
    W, ROW = 260, 26

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0, width=self.W, height=60)
        self.canvas.pack()
        self.limits: list[dict] = []
        self.error = "Loading..."
        self.email = account()
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

    def _poll(self) -> None:
        def work():
            limits, err = fetch()
            self.root.after(0, self._got, limits, err)
        threading.Thread(target=work, daemon=True).start()
        self.root.after(POLL_S * 1000, self._poll)

    def _got(self, limits, err) -> None:
        if limits is not None:
            self.limits = limits
        self.error = err
        self.email = account()
        self.draw()

    def _draw_loop(self) -> None:
        self.draw()
        self.root.after(30_000, self._draw_loop)

    def draw(self) -> None:
        c, W = self.canvas, self.W
        c.delete("all")
        c.create_text(10, 13, text=self.email, fill=DIM, anchor="w", font=("Segoe UI", 9))
        c.create_text(W - 12, 12, text="✕", fill=DIM, font=("Segoe UI", 10))
        y = 32
        for lim in self.limits:
            pct = min(lim["pct"], 100)
            c.create_text(10, y, text=lim["label"], fill=TEXT, anchor="w", font=("Segoe UI", 9, "bold"))
            c.create_rectangle(70, y - 6, 190, y + 6, fill=TRACK, width=0)
            c.create_rectangle(70, y - 6, 70 + 120 * pct / 100, y + 6, fill=bar_color(pct), width=0)
            c.create_text(196, y, text=f"{round(pct)}%", fill=TEXT, anchor="w", font=("Segoe UI", 9))
            c.create_text(W - 10, y, text=left(lim["resets"]), fill=DIM, anchor="e", font=("Segoe UI", 9))
            y += self.ROW
        if self.error:
            c.create_text(10, y, text=self.error, fill="#f2b84b", anchor="w", font=("Segoe UI", 8))
            y += self.ROW - 6
        c.configure(height=y - 6)

    def _press(self, e) -> None:
        if e.x > self.W - 24 and e.y < 24:  # the X
            self.root.destroy()
            return
        self._grab = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag(self, e) -> None:
        if getattr(self, "_grab", None):
            self.root.geometry(f"+{e.x_root - self._grab[0]}+{e.y_root - self._grab[1]}")

    def _release(self, _e) -> None:
        if getattr(self, "_grab", None):
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
        assert left("2099-01-01T00:00:00Z").endswith("d") and left(None) == ""
        assert bar_color(10) != bar_color(90)
        print("usage self-check ok;", account(), fetch()[1] or "fetch ok")
    else:
        main()
