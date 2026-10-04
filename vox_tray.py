#!/usr/bin/env python3
# Tray icon for Echo's voice: mirrors and toggles ~/.cache/claude-speak/muted,
# the same sentinel hooks/speak_stop.py checks and hooks/toggle_speak.sh
# (SUPER+M) flips. Uses AyatanaAppIndicator3 so it shows up in any standard
# StatusNotifierItem tray host (omarchy-shell's included) without needing a
# window of its own.
import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import GLib, Gtk
from gi.repository import AyatanaAppIndicator3 as AppIndicator3

CACHE_DIR = os.path.expanduser("~/.cache/claude-speak")
MUTE_FLAG = os.path.join(CACHE_DIR, "muted")

ICON_ON = "audio-input-microphone-symbolic"
ICON_OFF = "microphone-sensitivity-muted-symbolic"

indicator = AppIndicator3.Indicator.new(
    "echo-vox", ICON_ON, AppIndicator3.IndicatorCategory.APPLICATION_STATUS
)
indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

menu = Gtk.Menu()
toggle_item = Gtk.MenuItem()
menu.append(toggle_item)
menu.append(Gtk.SeparatorMenuItem())
quit_item = Gtk.MenuItem(label="Quit")
menu.append(quit_item)
menu.show_all()
indicator.set_menu(menu)

muted = False


def refresh():
    global muted
    muted = os.path.exists(MUTE_FLAG)
    indicator.set_icon_full(
        ICON_OFF if muted else ICON_ON,
        "Echo voice " + ("muted" if muted else "enabled"),
    )
    toggle_item.set_label("Enable voice" if muted else "Disable voice")


def on_toggle(_item):
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(MUTE_FLAG):
        os.remove(MUTE_FLAG)
    else:
        open(MUTE_FLAG, "w").close()
    refresh()


def on_quit(_item):
    Gtk.main_quit()


def poll(*_args):
    refresh()
    return True


toggle_item.connect("activate", on_toggle)
quit_item.connect("activate", on_quit)

refresh()
GLib.timeout_add_seconds(1, poll)  # picks up SUPER+M / CLI toggles too
Gtk.main()
