# Echo — Claude Code Context

**Phil's Notes (features/bugs):** `philVault/dev/Echo/phils_notes.md`

---

## What It Is

A local configuration UX and tray-icon mute control for the voice/vox system (Piper TTS readback of Claude Code responses, the SUPER+R recap replay, and the "derelict vox" radio-effect filter chain), including the Claude Code Stop hook (`hooks/speak_stop.py`) that drives it and the shared config it reads, `~/.config/claude-speak/config.json`.

`vox_tray.py` is built and running as a tray icon (see Architecture below). `visualizer.html` ("Vox Uplink") still exists as a manual test/debug page — load a clip, watch the clips folder live, mute — but is no longer auto-launched as a desktop accessory (retired 2026-10-04; it didn't behave like a native panel element on this Hyprland/Arch setup, see that date's entry in `phils_notes.md`). The configuration UX settings page itself is still not built (queued in `philVault/dev/Echo/todo.md`).

**One repo, symlinked out where the OS requires it:** the hook scripts live and are version-controlled at `hooks/` in this repo — Claude Code's hook system requires them at `~/.claude/hooks/`, so each one there (`speak_stop.py`, `speak_enqueue.py`, `recap_focused.sh`, `toggle_speak.sh`) is a symlink back into this repo's `hooks/` directory, not a separate copy. (Previously these lived unversioned outside the repo, "guest-module shape" — same pattern Mindfl still uses — but Echo folded them in on 2026-09-08 for real version control; see that date's entry in `phils_notes.md`.) Config still isn't duplicated into the repo — both sides read/write the one file at `~/.config/claude-speak/config.json` directly, no sync step.

---

## Architecture

No server, no daemon anywhere in this system — everything below is either a static page, a tray-icon process, or short-lived cooperating processes using file locks.

**Tray icon** (`vox_tray.py`): a standalone AyatanaAppIndicator3 process (PyGObject + Gtk), no build step. Registers a mic icon with whatever StatusNotifierItem host the panel runs — on this Hyprland/Arch setup that's omarchy-shell's built-in `omarchy.tray` bar module, so the icon shows up as a normal panel tray applet rather than a separate window. Click opens a menu with "Disable/Enable voice", which writes/removes `~/.cache/claude-speak/muted` — the same sentinel `hooks/speak_stop.py` checks and `SUPER+M` (`hooks/toggle_speak.sh`) flips — and polls that file every second so the icon stays in sync regardless of which of the three ways it was toggled.

**Visualizer page** (`visualizer.html`, "Vox Uplink"): a standalone HTML/JS page, no build step, opened manually when wanted (not autostarted). Live-watches the `~/.cache/claude-speak/` directory via the File System Access API (Chromium-only; one-time grant) — auto-plays new clips (muted; system audio comes from the hook's own `paplay`) and shows which terminal is speaking via `now_playing.json`. Also has its own mute button, same sentinel file as the tray icon. (This page used to run as an always-on floating desktop-accessory window; that mode — `?widget=1`, the Hyprland `special:vox` workspace rule, `SUPER+SHIFT+V`, `~/.local/bin/vox-toggle` — was removed 2026-10-04 in favor of the tray icon. Design history in this project's Claude memory, `echo-vox-widget-architecture`, written before that removal.)

**Multi-terminal speech queue** (`hooks/` in this repo, symlinked to `~/.claude/hooks/`): `speak_stop.py` identifies which Hyprland window (terminal) triggered it and hands the rendered clip to `speak_enqueue.py`, which queues it (`~/.cache/claude-speak/queue/`) and drains it via an flock-based worker so concurrent terminals' TTS never overlaps. Each clip is also kept per-window (`by-window/<hyprland-address>.wav`); `SUPER+R` → `recap_focused.sh` replays only the currently-focused terminal's own clip (no fallback to a different terminal's content — see `recap-scoping-lesson` memory for why).

Design philosophy for the *settings page* specifically is still pending a conversation with Phil — see `philVault/dev/Echo/phils_notes.md` for the open thread.

---

## Running & Deploying

Local only, no deploy target. `vox_tray.py` autostarts at login (`~/.config/hypr/autostart.lua`) and lives in the panel tray from then on — no window, no keybind needed to reach it. `visualizer.html` is opened manually (`file://` in any Chromium-based browser) when wanted. The settings page doesn't exist yet — once built, open it directly in a browser.

---

## Key Paths

| Item | Path |
|------|------|
| Vault docs | `philVault/dev/Echo/` |
| Project dir | `/home/phil/Dev/Claude/Echo` (symlink to `/run/media/phil/shared-data/Dev/Claude/Echo`) |
| Tray icon | `vox_tray.py` (this repo; autostarted directly by path, no symlink needed) |
| Visualizer page (manual use) | `visualizer.html` (this repo) |
| Shared config (source of truth) | `~/.config/claude-speak/config.json` |
| Mute flag (shared by tray icon, visualizer page, SUPER+M) | `~/.cache/claude-speak/muted` |
| Hook script | `hooks/speak_stop.py` (this repo; symlinked at `~/.claude/hooks/speak_stop.py`) |
| Speech queue worker | `hooks/speak_enqueue.py` (this repo; symlinked at `~/.claude/hooks/speak_enqueue.py`) |
| Focused-window recap script | `hooks/recap_focused.sh` (this repo; symlinked at `~/.claude/hooks/recap_focused.sh`) |
| Vox mute toggle script | `hooks/toggle_speak.sh` (this repo; symlinked at `~/.claude/hooks/toggle_speak.sh`) |
| Last spoken clip cache (global) | `~/.cache/claude-speak/last.wav` |
| Per-terminal recap clips | `~/.cache/claude-speak/by-window/<hyprland-address>.wav` |
| Currently-speaking terminal info | `~/.cache/claude-speak/now_playing.json` |
| Hyprland config touched (autostart only now) | `~/.config/hypr/autostart.lua` |
