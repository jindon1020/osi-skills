#!/usr/bin/env python3
"""
macOS Desktop Control Script
Provides screenshot capture, mouse control, and keyboard input.
Uses only macOS built-in tools + cliclick (installable via brew).

Usage:
    python3 desktop_control.py screenshot [--path PATH]
    python3 desktop_control.py click X Y
    python3 desktop_control.py doubleclick X Y
    python3 desktop_control.py rightclick X Y
    python3 desktop_control.py move X Y
    python3 desktop_control.py type "text"
    python3 desktop_control.py key "keystroke"       # e.g. "return", "tab", "escape"
    python3 desktop_control.py hotkey "cmd+s"        # modifier combos
    python3 desktop_control.py drag X1 Y1 X2 Y2
    python3 desktop_control.py scroll DIRECTION [AMOUNT]  # up/down/left/right
    python3 desktop_control.py mousepos              # print current mouse position
    python3 desktop_control.py screensize            # print screen dimensions
    python3 desktop_control.py wait SECONDS
    python3 desktop_control.py open "app_name"       # open an application
    python3 desktop_control.py focus "app_name"      # bring app to foreground
"""

import subprocess
import sys
import os
import time
import json
import tempfile
import shutil


def check_cliclick():
    """Check if cliclick is installed, provide install instructions if not."""
    if shutil.which("cliclick"):
        return True
    print("ERROR: cliclick is not installed.", file=sys.stderr)
    print("Install it with: brew install cliclick", file=sys.stderr)
    print("Then grant Accessibility permissions in System Settings > Privacy & Security > Accessibility", file=sys.stderr)
    return False


def screenshot(path=None):
    """Capture screenshot of the entire screen."""
    if path is None:
        path = os.path.join(tempfile.gettempdir(), f"desktop_screenshot_{int(time.time())}.png")
    subprocess.run(["screencapture", "-x", path], check=True)
    print(json.dumps({"action": "screenshot", "path": os.path.abspath(path)}))
    return path


def click(x, y):
    subprocess.run(["cliclick", f"c:{x},{y}"], check=True)
    print(json.dumps({"action": "click", "x": x, "y": y}))


def doubleclick(x, y):
    subprocess.run(["cliclick", f"dc:{x},{y}"], check=True)
    print(json.dumps({"action": "doubleclick", "x": x, "y": y}))


def rightclick(x, y):
    subprocess.run(["cliclick", f"rc:{x},{y}"], check=True)
    print(json.dumps({"action": "rightclick", "x": x, "y": y}))


def move(x, y):
    subprocess.run(["cliclick", f"m:{x},{y}"], check=True)
    print(json.dumps({"action": "move", "x": x, "y": y}))


def type_text(text):
    """Type text using cliclick. Handles special characters."""
    subprocess.run(["cliclick", f"t:{text}"], check=True)
    print(json.dumps({"action": "type", "text": text}))


def key_press(key_name):
    """Press a single key. Supports: return, tab, escape, delete, space, arrow-up/down/left/right, f1-f12, etc."""
    key_map = {
        "return": "kp:return",
        "enter": "kp:return",
        "tab": "kp:tab",
        "escape": "kp:escape",
        "esc": "kp:escape",
        "delete": "kp:delete",
        "backspace": "kp:delete",
        "space": "kp:space",
        "up": "kp:arrow-up",
        "down": "kp:arrow-down",
        "left": "kp:arrow-left",
        "right": "kp:arrow-right",
        "home": "kp:home",
        "end": "kp:end",
        "pageup": "kp:page-up",
        "pagedown": "kp:page-down",
        "f1": "kp:f1", "f2": "kp:f2", "f3": "kp:f3", "f4": "kp:f4",
        "f5": "kp:f5", "f6": "kp:f6", "f7": "kp:f7", "f8": "kp:f8",
        "f9": "kp:f9", "f10": "kp:f10", "f11": "kp:f11", "f12": "kp:f12",
    }
    cmd = key_map.get(key_name.lower(), f"kp:{key_name}")
    subprocess.run(["cliclick", cmd], check=True)
    print(json.dumps({"action": "key", "key": key_name}))


def hotkey(combo):
    """Press a hotkey combination like cmd+s, cmd+shift+n, ctrl+alt+delete.
    Modifier names: cmd, ctrl, alt/option, shift, fn."""
    parts = combo.lower().split("+")
    key = parts[-1]
    modifiers = parts[:-1]

    # Map modifier names to cliclick modifier keys
    mod_map = {
        "cmd": "cmd",
        "command": "cmd",
        "ctrl": "ctrl",
        "control": "ctrl",
        "alt": "alt",
        "option": "alt",
        "shift": "shift",
        "fn": "fn",
    }

    # Build key-down / key-up sequence
    cliclick_args = []
    for mod in modifiers:
        m = mod_map.get(mod)
        if m is None:
            print(f"ERROR: Unknown modifier '{mod}'", file=sys.stderr)
            sys.exit(1)
        cliclick_args.append(f"kd:{m}")

    # Map the final key - special keys use kp:, regular characters use t:
    special_key_map = {
        "return": "return", "enter": "return", "tab": "tab",
        "escape": "escape", "esc": "escape", "delete": "delete",
        "backspace": "delete", "space": "space",
        "up": "arrow-up", "down": "arrow-down",
        "left": "arrow-left", "right": "arrow-right",
        "home": "home", "end": "end",
        "pageup": "page-up", "pagedown": "page-down",
        "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
        "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
        "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
    }
    if key.lower() in special_key_map:
        cliclick_args.append(f"kp:{special_key_map[key.lower()]}")
    else:
        # Regular character key - use t: (type) instead of kp:
        cliclick_args.append(f"t:{key}")

    for mod in reversed(modifiers):
        m = mod_map.get(mod)
        cliclick_args.append(f"ku:{m}")

    subprocess.run(["cliclick"] + cliclick_args, check=True)
    print(json.dumps({"action": "hotkey", "combo": combo}))


def drag(x1, y1, x2, y2):
    subprocess.run(["cliclick", f"dd:{x1},{y1}", f"du:{x2},{y2}"], check=True)
    print(json.dumps({"action": "drag", "from": [x1, y1], "to": [x2, y2]}))


def scroll(direction, amount=3):
    """Scroll in a direction. Uses AppleScript for reliable scrolling."""
    amount = int(amount)
    # Use cliclick scroll (available in newer versions)
    # Fallback to AppleScript if needed
    scroll_map = {
        "up": f"su:{amount}",
        "down": f"sd:{amount}",
        "left": f"sl:{amount}",
        "right": f"sr:{amount}",
    }
    cmd = scroll_map.get(direction.lower())
    if cmd is None:
        print(f"ERROR: Unknown scroll direction '{direction}'. Use up/down/left/right.", file=sys.stderr)
        sys.exit(1)

    try:
        subprocess.run(["cliclick", cmd], check=True)
    except subprocess.CalledProcessError:
        # Fallback: use AppleScript for vertical scrolling
        if direction.lower() in ("up", "down"):
            delta = amount if direction.lower() == "up" else -amount
            script = f'''
            tell application "System Events"
                scroll area 1 by {delta}
            end tell
            '''
            subprocess.run(["osascript", "-e", script], check=True)

    print(json.dumps({"action": "scroll", "direction": direction, "amount": amount}))


def mousepos():
    result = subprocess.run(["cliclick", "p:."], capture_output=True, text=True, check=True)
    pos = result.stdout.strip()
    print(json.dumps({"action": "mousepos", "position": pos}))


def screensize():
    """Get screen dimensions using system_profiler."""
    result = subprocess.run(
        ["system_profiler", "SPDisplaysDataType", "-json"],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    displays = []
    for gpu in data.get("SPDisplaysDataType", []):
        for display in gpu.get("spdisplays_ndrvs", []):
            res = display.get("_spdisplays_resolution", "")
            displays.append({"name": display.get("_name", ""), "resolution": res})
    print(json.dumps({"action": "screensize", "displays": displays}))


def wait_seconds(seconds):
    time.sleep(float(seconds))
    print(json.dumps({"action": "wait", "seconds": float(seconds)}))


def open_app(app_name):
    subprocess.run(["open", "-a", app_name], check=True)
    time.sleep(1)  # Give app time to launch
    print(json.dumps({"action": "open", "app": app_name}))


def focus_app(app_name):
    script = f'''
    tell application "{app_name}"
        activate
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=True)
    time.sleep(0.5)
    print(json.dumps({"action": "focus", "app": app_name}))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "screenshot":
        path = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--path" else None
        screenshot(path)
        return

    if cmd == "screensize":
        screensize()
        return

    if cmd in ("open", "focus"):
        if len(sys.argv) < 3:
            print(f"ERROR: {cmd} requires an app name", file=sys.stderr)
            sys.exit(1)

    if cmd == "open":
        open_app(sys.argv[2])
        return

    if cmd == "focus":
        focus_app(sys.argv[2])
        return

    if cmd == "wait":
        wait_seconds(sys.argv[2])
        return

    # All other commands require cliclick
    if not check_cliclick():
        sys.exit(1)

    if cmd == "click":
        click(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "doubleclick":
        doubleclick(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "rightclick":
        rightclick(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "move":
        move(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "type":
        type_text(sys.argv[2])
    elif cmd == "key":
        key_press(sys.argv[2])
    elif cmd == "hotkey":
        hotkey(sys.argv[2])
    elif cmd == "drag":
        drag(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
    elif cmd == "scroll":
        direction = sys.argv[2]
        amount = sys.argv[3] if len(sys.argv) > 3 else 3
        scroll(direction, amount)
    elif cmd == "mousepos":
        mousepos()
    else:
        print(f"ERROR: Unknown command '{cmd}'", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
