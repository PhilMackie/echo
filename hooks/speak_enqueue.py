#!/usr/bin/env python3
"""Enqueues a rendered Piper TTS clip for sequential playback and, if no
other invocation is already draining the queue, becomes the worker itself.

Multiple Claude Code terminals can each fire the Stop hook around the same
moment; without this, their `paplay` calls would talk over each other.
Instead every finished clip is dropped into a shared queue directory and
whichever invocation gets there when the queue is empty grabs an flock and
plays everything in it (including anything added by other invocations
while it's working), in turn order (see `seq` below) rather than in the
order clips happen to finish rendering - including waiting out a
still-rendering earlier turn (via its <seq>.pending marker) instead of
draining early just because the queue looked empty at that instant.

Also drops a copy of the clip keyed by the owning terminal window's stable
Hyprland address (independent of playback order) so a later "recap the
window I'm looking at right now" request has something to read — see
recap_focused.sh. And records which window is currently playing in
now_playing.json, for anything (e.g. the Echo visualizer widget) that wants
to display whose response is being read aloud.

Invoked as: speak_enqueue.py <wav_path> <window_address> <window_title> <seq>
window_address/window_title may be empty strings if the owning window
couldn't be determined (e.g. hyprctl unavailable). seq is a monotonic
ordering key (nanoseconds) captured by speak_stop.py at Stop-hook fire
time, before rendering — used as the queue sort key instead of this
script's own arrival time, since rendering (Piper + the optional vox
effect) takes a variable amount of time per clip and a later turn can
otherwise finish rendering, and so get played, before an earlier one.
"""
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time

CACHE_DIR = os.path.expanduser("~/.cache/claude-speak")
QUEUE_DIR = os.path.join(CACHE_DIR, "queue")
BY_WINDOW_DIR = os.path.join(CACHE_DIR, "by-window")
LAST_WAV = os.path.join(CACHE_DIR, "last.wav")
NOW_PLAYING = os.path.join(CACHE_DIR, "now_playing.json")
LOCK_PATH = os.path.join(CACHE_DIR, "queue.lock")

# How long the worker will wait for a lower-seq <seq>.pending marker (see
# speak_stop.py) to turn into an actual clip before giving up on it. Bounds
# the damage from a crashed/killed render: without this, its abandoned
# marker would look like "an earlier turn is still coming" forever and
# permanently stall playback for every terminal, not just its own.
PENDING_MAX_AGE_NS = 10 * 1_000_000_000


def atomic_copy(src, dst):
    tmp = dst + ".tmp"
    subprocess.run(["cp", "-f", src, tmp], check=False)
    os.replace(tmp, dst)


def drain_queue_if_free():
    """Become the queue worker if nobody else currently is. Loops until
    the queue is empty, re-listing each time so jobs added mid-drain by
    other concurrent invocations still get picked up."""
    lock_fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # another invocation is already the worker

    try:
        while True:
            entries = os.listdir(QUEUE_DIR)
            jobs = sorted(f for f in entries if f.endswith(".json"))
            next_seq = int(jobs[0][:-5]) if jobs else None

            # A .pending marker with a lower seq than the job we're about
            # to play (or any marker at all, if no job has landed yet)
            # means an earlier turn's clip may still be rendering - wait
            # for it rather than let this later one jump the queue and get
            # played (and heard) out of turn order.
            stale_cutoff = time.time_ns() - PENDING_MAX_AGE_NS
            still_rendering = False
            for f in entries:
                if not f.endswith(".pending"):
                    continue
                pending_seq = int(f[:-8])
                if next_seq is not None and pending_seq >= next_seq:
                    continue
                if pending_seq < stale_cutoff:
                    try:
                        os.remove(os.path.join(QUEUE_DIR, f))
                    except OSError:
                        pass
                    continue
                still_rendering = True
            if still_rendering:
                time.sleep(0.1)
                continue

            if not jobs:
                break
            job_json = os.path.join(QUEUE_DIR, jobs[0])
            job_wav = job_json[:-5] + ".wav"

            try:
                with open(job_json) as f:
                    meta = json.load(f)
            except (OSError, json.JSONDecodeError):
                meta = {}

            if os.path.exists(job_wav):
                with open(NOW_PLAYING, "w") as f:
                    json.dump(meta, f)
                atomic_copy(job_wav, LAST_WAV)
                subprocess.run(["paplay", job_wav])
                os.remove(job_wav)

            os.remove(job_json)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def main():
    if len(sys.argv) != 5:
        return
    wav_path, address, title, seq = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    if not os.path.exists(wav_path):
        return
    try:
        int(seq)  # validate before trusting it in a filename
    except ValueError:
        return

    os.makedirs(QUEUE_DIR, exist_ok=True)
    os.makedirs(BY_WINDOW_DIR, exist_ok=True)

    if address:
        atomic_copy(wav_path, os.path.join(BY_WINDOW_DIR, f"{address}.wav"))

    job_wav = os.path.join(QUEUE_DIR, f"{seq}.wav")
    job_json = os.path.join(QUEUE_DIR, f"{seq}.json")
    # source (system tempdir, from tempfile.mkstemp) may be a different
    # filesystem than the cache dir, so a plain os.rename can raise
    # "Invalid cross-device link" — shutil.move falls back to copy+remove.
    shutil.move(wav_path, job_wav)
    with open(job_json, "w") as f:
        json.dump({"address": address, "title": title}, f)

    drain_queue_if_free()


if __name__ == "__main__":
    main()
