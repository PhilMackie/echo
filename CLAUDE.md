# Echo — Claude Code Context

**Phil's Notes (features/bugs):** `philVault/dev/Echo/phils_notes.md`

---

## What It Is

A local configuration UX and Vox visualizer widget for the voice/vox system (Piper TTS readback of Claude Code responses, the SUPER+R recap replay, and the "derelict vox" radio-effect filter chain) that lives elsewhere as `~/.config/claude-speak/config.json` + `~/.claude/hooks/speak_stop.py`.

The visualizer widget (`visualizer.html`, "Vox Uplink") is built and running as a live desktop accessory — see Architecture below. The configuration UX settings page itself is still not built (queued in `philVault/dev/Echo/todo.md`).

**Guest-module shape (same pattern as Mindfl):** the hook script Claude Code actually invokes stays at `~/.claude/hooks/speak_stop.py` — outside this repo, since Claude Code's hook system needs it there. This repo owns the config file *format*, the settings UI, and visualizer/asset work. Both sides read/write the same `~/.config/claude-speak/config.json` — no duplicated state, no sync step.

---

## Architecture

No server, no daemon anywhere in this system — everything below is either a static page or short-lived cooperating processes using file locks.

**Visualizer widget** (`visualizer.html`): a standalone HTML/JS page, no build step. Live-watches the `~/.cache/claude-speak/` directory via the File System Access API (Chromium-only; one-time grant) — auto-plays new clips (muted; system audio comes from the hook's own `paplay`) and shows which terminal is speaking via `now_playing.json`. `?widget=1` (or pressing `W`) strips it to just the ring+bars for docking as a desktop accessory. Runs as a dedicated Chromium `--app=` window on its own Hyprland special workspace (`special:vox`), toggled by `SUPER+SHIFT+V` → `~/.local/bin/vox-toggle` (relaunches it if closed, since closing the window kills the whole process). Full design + gotchas (Hyprland positioning limits, Chromium `--class` quirk, FSA permission lifetime) written up in this project's Claude memory (`echo-vox-widget-architecture`), not duplicated here.

**Multi-terminal speech queue** (hook-side, outside this repo): `speak_stop.py` identifies which Hyprland window (terminal) triggered it and hands the rendered clip to `speak_enqueue.py`, which queues it (`~/.cache/claude-speak/queue/`) and drains it via an flock-based worker so concurrent terminals' TTS never overlaps. Each clip is also kept per-window (`by-window/<hyprland-address>.wav`); `SUPER+R` → `recap_focused.sh` replays only the currently-focused terminal's own clip (no fallback to a different terminal's content — see `recap-scoping-lesson` memory for why).

Design philosophy for the *settings page* specifically is still pending a conversation with Phil — see `philVault/dev/Echo/phils_notes.md` for the open thread.

---

## Running & Deploying

Local only, no deploy target. The visualizer widget autostarts hidden at login (`~/.config/hypr/autostart.lua`) and toggles with `SUPER+SHIFT+V`. The settings page doesn't exist yet — once built, open it directly in a browser.

---

## Key Paths

| Item | Path |
|------|------|
| Vault docs | `philVault/dev/Echo/` |
| Project dir | `/home/phil/Dev/Claude/Echo` |
| Visualizer widget | `visualizer.html` (this repo) |
| Shared config (source of truth) | `~/.config/claude-speak/config.json` |
| Hook script (lives outside this repo) | `~/.claude/hooks/speak_stop.py` |
| Speech queue worker (outside this repo) | `~/.claude/hooks/speak_enqueue.py` |
| Focused-window recap script (outside this repo) | `~/.claude/hooks/recap_focused.sh` |
| Widget toggle/relaunch script | `~/.local/bin/vox-toggle` |
| Last spoken clip cache (global) | `~/.cache/claude-speak/last.wav` |
| Per-terminal recap clips | `~/.cache/claude-speak/by-window/<hyprland-address>.wav` |
| Currently-speaking terminal info | `~/.cache/claude-speak/now_playing.json` |
| Hyprland config touched (window rule, keybinds, autostart) | `~/.config/hypr/{hyprland,bindings,autostart}.lua` |
