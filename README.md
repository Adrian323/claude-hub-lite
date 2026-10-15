# Claude Hub Lite

A Windows tray icon for [Claude Code](https://claude.com/claude-code) consoles. It needs no server and no setup: it reads the
files Claude Code already writes for whoever is logged in.

```
12 consoles, 2 hidden
12 consoles   >   click one to bring its window to the front
2 hidden      >   click one to see which app runs it
--------------
Usage App         floating panel: your 5h / 7d / per-model limits and when they reset
AgTop             htop-style view of every Claude session
Save CLI          remember which consoles are open
Restore CLI       after a reboot, reopen them (claude --resume)
--------------
Source            opens this repo on GitHub
Quit Tray
```

The icon is green while a console is working and gray when all of them are idle.

## Install

You need **Windows**, **[Python 3.10+](https://www.python.org/downloads/)** and Claude Code. For AgTop you also need
**[Node.js](https://nodejs.org)**.

1. Clone or download this repo to any folder you like.
2. Double-click `install.cmd`.

The installer creates a private `.venv`, installs `pystray`, `pillow` and `psutil`, and installs AgTop if Node is present.
It also adds a Startup shortcut, so the tray starts with Windows, and then starts the tray. Run it again after a
`git pull` to update. Quit the tray first.

**Uninstall:** quit the tray, run `uninstall.cmd` to remove the Startup shortcut, then delete the folder.

## Notes

- **Consoles** come from `%USERPROFILE%\.claude\sessions`, or from `CLAUDE_CONFIG_DIR` if you set it. Consoles you
  started yourself are listed under *consoles*. Headless sessions that other apps start (`claude -p`, SDK) are listed
  under *hidden*.
- **Usage** uses the login token that Claude Code keeps in `.claude\.credentials.json`. It asks the same endpoint as
  Claude Code's `/usage`, every 3 minutes. The panel never refreshes the token itself. If the token expires, the panel
  says so until Claude Code renews it.
- **Save / Restore** keeps its list in `data\saved-consoles.json`. Restore asks before it opens anything. It skips
  consoles that are already open.
- Logs are in `data\tray.log`.

Self-checks: `.venv\Scripts\python -m claudetray.sessions` and `.venv\Scripts\python -m claudetray.usage --selftest`.

## Contributing

Changes are welcome. Fork the repo, make your change on a branch, and open a pull request against `main`.
Run the two self-checks above before you send it. Bugs and ideas go in
[Issues](https://github.com/Adrian323/claude-hub-lite/issues).

## License

MIT, free to use, change and share; keep the copyright notice. See `LICENSE`.
