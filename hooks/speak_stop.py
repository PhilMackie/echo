#!/usr/bin/env python3
"""Claude Code Stop hook: speaks an abbreviated version of the last
assistant response aloud via Piper TTS, for hands-free use alongside Handy.

Heuristic abbreviation only (no LLM call): strips code blocks/markdown and
reads back the final paragraph of the response, since that's where Claude
Code's own end-of-turn summary convention puts the "what changed / what's
next" line.

All tunables (voice, speed, and the optional "derelict vox" radio effect)
live in ~/.config/claude-speak/config.json — edit that file, no code changes
needed. Missing keys fall back to the defaults below.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

VOICES_DIR = os.path.expanduser("~/.local/share/piper/voices")
CONFIG_PATH = os.path.expanduser("~/.config/claude-speak/config.json")
CACHE_DIR = os.path.expanduser("~/.cache/claude-speak")
LAST_WAV = os.path.join(CACHE_DIR, "last.wav")
MUTE_FLAG = os.path.join(CACHE_DIR, "muted")
ENQUEUE_SCRIPT = os.path.expanduser("~/.claude/hooks/speak_enqueue.py")

DEFAULTS = {
    "voice_model": "en_US-ljspeech-high.onnx",
    "speaker": None,  # only meaningful for multi-speaker models like en_GB-vctk-medium
    "length_scale": 1.15,
    "noise_scale": 0.667,  # Piper's default generator noise
    "noise_w": 0.8,  # Piper's default phoneme-duration noise (syllable stress variation)
    "max_chars": 500,
    "vox_effect": {
        "enabled": False,
        "highpass_hz": 150,
        "lowpass_hz": 3400,
        "crusher_bits": 6,
        "crusher_aa": 0.5,
        "echo": "0.8:0.7:40|90:0.35|0.2",
        "vibrato_freq_hz": 5,
        "vibrato_depth": 0.2,
        "flutter_freq_hz": 6,
        "flutter_depth": 0.3,
        "static_amplitude": 0.02,
        "static_mix_weight": 0.06,
        "voice_gain": 1.0,
        "overall_gain": 1.8,
        "signal_wobble_freq_hz": 0.4,
        "signal_wobble_depth": 0.45,
        "limiter": 0.95,
        "taper_seconds": 0.5,  # crackle burst that decays before/swells after the voice, like a radio keying on/off
        "crackle_amplitude": 0.3,
        "crackle_mix_weight": 0.5,
    },
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    try:
        with open(CONFIG_PATH) as f:
            user_cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return cfg
    for key, value in user_cfg.items():
        if key == "vox_effect" and isinstance(value, dict):
            cfg["vox_effect"].update(value)
        else:
            cfg[key] = value
    return cfg


def last_assistant_text(transcript_path):
    text = None
    with open(transcript_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "assistant":
                continue
            content = entry.get("message", {}).get("content", [])
            blocks = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if blocks:
                text = "\n\n".join(blocks)
    return text


def abbreviate(text, max_chars):
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return None

    summary = re.sub(r"\s+", " ", paragraphs[-1]).strip()
    if len(summary) > max_chars:
        summary = summary[:max_chars].rsplit(" ", 1)[0] + "..."
    return summary or None


def get_owner_window():
    """Identify which Hyprland window (terminal) launched this hook
    invocation, by walking up the process tree from our own PID until a
    parent matches a client's owning process. Keyed by the window's
    stable address rather than its title, since Claude Code rewrites the
    title constantly as it works."""
    try:
        out = subprocess.run(
            ["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=2
        ).stdout
        clients = json.loads(out)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None

    pid_to_window = {c["pid"]: c for c in clients if "pid" in c}

    pid = os.getpid()
    seen = set()
    while pid and pid > 1 and pid not in seen:
        seen.add(pid)
        window = pid_to_window.get(pid)
        if window:
            return {"address": window.get("address", ""), "title": window.get("title", "")}
        try:
            with open(f"/proc/{pid}/stat") as f:
                # comm field (2nd) may itself contain spaces/parens, so
                # split from the closing paren rather than by whitespace.
                after_comm = f.read().rsplit(")", 1)[1].split()
            pid = int(after_comm[1])  # ppid is the 4th field overall
        except (OSError, IndexError, ValueError):
            break
    return None


def vox_filter_cmd(vox, raw_wav, out_wav):
    """Build the shell snippet for the optional derelict-vox radio effect:
    a filtered/crushed voice over a constant static/hiss bed, bookended by
    a crackle burst that decays into the voice and swells back out after
    it, like a transmission keying on and off.

    raw_wav doesn't exist yet at command-build time (piper hasn't rendered
    it — this whole snippet runs later in a detached shell), so the total
    duration and taper offsets can't be computed here in Python. Instead
    this emits shell code that ffprobes raw_wav and does the arithmetic
    via `python3 -c` at render time, exporting TOTAL/TAPER_MS/POST_MS/
    POST_PAD as shell variables the ffmpeg command then references
    directly (hence filter_complex/bed_noise/burst_noise below are
    double-quoted by hand, not shlex.quote, since shlex.quote would
    single-quote them and suppress that variable expansion)."""
    taper = vox["taper_seconds"]
    inline_py = (
        f"d=$DUR; t={taper}; "
        f"print('TOTAL=' + str(d+2*t)); "
        f"print('TAPER_MS=' + str(int(t*1000))); "
        f"print('POST_MS=' + str(int((t+d)*1000))); "
        f"print('POST_PAD=' + str(t+d))"
    )
    duration_setup = (
        f"DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 {shlex.quote(raw_wav)}) && "
        f'eval "$(python3 -c "{inline_py}")"'
    )

    filter_complex = (
        f"[0:a]highpass=f={vox['highpass_hz']},lowpass=f={vox['lowpass_hz']},"
        f"acrusher=bits={vox['crusher_bits']}:mode=log:aa={vox['crusher_aa']}:samples=3,"
        f"vibrato=f={vox['vibrato_freq_hz']}:d={vox['vibrato_depth']},"
        f"aecho={vox['echo']},"
        f"tremolo=f={vox['flutter_freq_hz']}:d={vox['flutter_depth']},"
        f"volume={vox['voice_gain']},"
        f"adelay=delays=$TAPER_MS:all=1,apad=pad_dur={taper}[voice];"
        f"[2:a]highpass=f=800,lowpass=f=6000,tremolo=f=40:d=0.9,"
        f"volume={vox['crackle_amplitude']},afade=t=out:st=0:d={taper},"
        f"apad=pad_dur=$POST_PAD[burst_open];"
        f"[3:a]highpass=f=800,lowpass=f=6000,tremolo=f=40:d=0.9,"
        f"volume={vox['crackle_amplitude']},afade=t=in:st=0:d={taper},"
        f"adelay=delays=$POST_MS:all=1[burst_close];"
        f"[voice][1:a][burst_open][burst_close]amix=inputs=4:duration=longest:normalize=0:"
        f"weights=1 {vox['static_mix_weight']} {vox['crackle_mix_weight']} {vox['crackle_mix_weight']},"
        f"volume={vox['overall_gain']},"
        f"tremolo=f={vox['signal_wobble_freq_hz']}:d={vox['signal_wobble_depth']},"
        f"alimiter=limit={vox['limiter']}[out]"
    )
    bed_noise = f"anoisesrc=color=white:amplitude={vox['static_amplitude']}:sample_rate=22050:duration=$TOTAL"
    burst_noise = f"anoisesrc=color=white:amplitude=1.0:sample_rate=22050:duration={taper}"

    ffmpeg_cmd = (
        f"ffmpeg -y -i {shlex.quote(raw_wav)} "
        f'-f lavfi -i "{bed_noise}" '
        f'-f lavfi -i "{burst_noise}" '
        f'-f lavfi -i "{burst_noise}" '
        f'-filter_complex "{filter_complex}" -map "[out]" {shlex.quote(out_wav)}'
    )
    return f"{duration_setup} && {ffmpeg_cmd}"


def speak_async(text, cfg, window):
    voice_model = os.path.join(VOICES_DIR, cfg["voice_model"])
    if not os.path.exists(voice_model):
        return

    fd, text_file = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    raw_wav = text_file[:-4] + "_raw.wav"

    speaker_flag = f"--speaker {int(cfg['speaker'])} " if cfg.get("speaker") is not None else ""
    piper_cmd = (
        f"piper-tts --model {shlex.quote(voice_model)} --length_scale {cfg['length_scale']} "
        f"--noise_scale {cfg['noise_scale']} --noise_w {cfg['noise_w']} "
        f"{speaker_flag}--output_file {shlex.quote(raw_wav)} --quiet < {shlex.quote(text_file)}"
    )

    vox = cfg["vox_effect"]
    if vox.get("enabled"):
        final_wav = text_file[:-4] + "_fx.wav"
        render_cmd = f"{piper_cmd} && {vox_filter_cmd(vox, raw_wav, final_wav)}"
        cleanup = f"rm -f {shlex.quote(text_file)} {shlex.quote(raw_wav)}"
    else:
        final_wav = raw_wav
        render_cmd = piper_cmd
        cleanup = f"rm -f {shlex.quote(text_file)}"

    address = window.get("address", "") if window else ""
    title = window.get("title", "") if window else ""

    # Render to a temp file, then hand it to the queue so concurrent
    # terminals speak one at a time instead of talking over each other.
    cmd = (
        f"mkdir -p {shlex.quote(CACHE_DIR)} && {render_cmd} "
        f"&& python3 {shlex.quote(ENQUEUE_SCRIPT)} {shlex.quote(final_wav)} "
        f"{shlex.quote(address)} {shlex.quote(title)}; {cleanup}"
    )
    subprocess.Popen(
        ["bash", "-c", cmd],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def main():
    if os.path.exists(MUTE_FLAG):
        return

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    if data.get("stop_hook_active"):
        return

    transcript_path = data.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        return

    text = last_assistant_text(transcript_path)
    if not text:
        return

    cfg = load_config()
    summary = abbreviate(text, cfg["max_chars"])
    if summary:
        window = get_owner_window()
        speak_async(summary, cfg, window)


if __name__ == "__main__":
    main()
