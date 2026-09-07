# Echo — Claude Code Context

**Phil's Notes (features/bugs):** `philVault/dev/Echo/phils_notes.md`

---

## What It Is

A local configuration UX and Vox visualizer widget for the voice/vox system (Piper TTS readback of Claude Code responses, the SUPER+R recap replay, and the "derelict vox" radio-effect filter chain) that lives elsewhere as `~/.config/claude-speak/config.json` + `~/.claude/hooks/speak_stop.py`.

**Guest-module shape (same pattern as Mindfl):** the hook script Claude Code actually invokes stays at `~/.claude/hooks/speak_stop.py` — outside this repo, since Claude Code's hook system needs it there. This repo owns the config file *format*, the settings UI, and visualizer/asset work. Both sides read/write the same `~/.config/claude-speak/config.json` — no duplicated state, no sync step.

---

## Architecture

_Not yet built. Decided so far:_
- No server, no daemon — a standalone local HTML/JS page opened directly, editing `~/.config/claude-speak/config.json` in place.
- Design philosophy: pending a conversation with Phil — see `philVault/dev/Echo/phils_notes.md` for the open thread. Write it down once settled, don't build the UI ahead of it.

---

## Running & Deploying

Local only, no deploy target yet — open the settings page directly in a browser once it exists.

---

## Key Paths

| Item | Path |
|------|------|
| Vault docs | `philVault/dev/Echo/` |
| Project dir | `/home/phil/Dev/Claude/Echo` |
| Shared config (source of truth) | `~/.config/claude-speak/config.json` |
| Hook script (lives outside this repo) | `~/.claude/hooks/speak_stop.py` |
| Last spoken clip cache | `~/.cache/claude-speak/last.wav` |
