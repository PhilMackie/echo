#!/usr/bin/env bash
# Toggles the Piper TTS Stop-hook on/off. Does not touch Handy (speech-in)
# at all — the two are fully independent.
FLAG="$HOME/.cache/claude-speak/muted"
mkdir -p "$HOME/.cache/claude-speak"
if [ -f "$FLAG" ]; then
    rm -f "$FLAG"
    notify-send "Piper TTS" "Unmuted — responses will be read aloud again"
else
    touch "$FLAG"
    notify-send "Piper TTS" "Muted — responses will stay silent"
fi
