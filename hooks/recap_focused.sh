#!/bin/bash
# Replays the Piper TTS recap for the currently focused terminal window
# specifically — never some other terminal's last response, even if this
# one has never spoken. Each window's own last clip is kept in by-window/
# (see speak_enqueue.py). Deliberately does NOT fall back to the global
# last.wav: that would play a different terminal's content, which is worse
# than saying nothing since it looks like a wrong/broken recap rather than
# an obviously-empty one.
CACHE_DIR="$HOME/.cache/claude-speak"

address=$(hyprctl activewindow -j 2>/dev/null | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('address', ''))
except Exception:
    print('')
")

wav="$CACHE_DIR/by-window/${address}.wav"
if [ -n "$address" ] && [ -f "$wav" ]; then
  paplay "$wav"
else
  omarchy-notification-send -u low "Echo: no recap yet for this window" 2>/dev/null
fi
