---
name: mac-desktop-use
description: >
  Autonomous macOS desktop application control through screenshot recognition,
  mouse movement/clicking, and keyboard input. Use this skill when the user asks
  to interact with desktop applications (not browsers), automate GUI workflows,
  click buttons in apps, fill forms in native software, navigate menus, or
  perform any task that requires seeing the screen and operating the mouse/keyboard
  like a human. Triggers: "open Finder and...", "click on...", "use [app name]",
  "automate [desktop task]", "fill in the form in...", "navigate to menu...",
  "take a screenshot", "interact with desktop", "control my Mac",
  "operate [application]", "desktop automation".
---

# macOS Desktop Use

Control desktop applications by taking screenshots, analyzing them visually,
then executing mouse/keyboard actions — operating the Mac like a human would.

## Prerequisites

Run setup check first:
```bash
bash ~/.claude/skills/mac-desktop-use/scripts/setup_check.sh
```

Required:
- **cliclick**: `brew install cliclick`
- **Accessibility permission**: System Settings > Privacy & Security > Accessibility > enable your terminal
- **Screen Recording permission**: System Settings > Privacy & Security > Screen Recording > enable your terminal

## Core Script

All actions go through `scripts/desktop_control.py`:

```
python3 ~/.claude/skills/mac-desktop-use/scripts/desktop_control.py <command> [args]
```

| Command | Args | Description |
|---------|------|-------------|
| `screenshot` | `[--path FILE]` | Capture full screen, returns file path |
| `click` | `X Y` | Left click at coordinates |
| `doubleclick` | `X Y` | Double click |
| `rightclick` | `X Y` | Right click (context menu) |
| `move` | `X Y` | Move mouse cursor |
| `type` | `"text"` | Type text string |
| `key` | `"keyname"` | Press key: return, tab, escape, delete, space, up/down/left/right, f1-f12 |
| `hotkey` | `"mod+key"` | Hotkey combo: cmd+s, cmd+shift+n, ctrl+c |
| `drag` | `X1 Y1 X2 Y2` | Drag from point to point |
| `scroll` | `DIR [N]` | Scroll up/down/left/right by N clicks |
| `mousepos` | | Print current mouse position |
| `screensize` | | Print screen resolution |
| `wait` | `SECONDS` | Pause execution |
| `open` | `"App Name"` | Launch application |
| `focus` | `"App Name"` | Bring app to foreground |

## Workflow: The See-Think-Act Loop

Follow this loop for every desktop interaction task:

### 1. SETUP — Prepare the environment
```bash
# Check prerequisites on first use
bash ~/.claude/skills/mac-desktop-use/scripts/setup_check.sh

# Get screen dimensions for coordinate reference
python3 ~/.claude/skills/mac-desktop-use/scripts/desktop_control.py screensize

# Open/focus the target application
python3 ~/.claude/skills/mac-desktop-use/scripts/desktop_control.py open "App Name"
python3 ~/.claude/skills/mac-desktop-use/scripts/desktop_control.py wait 2
```

### 2. SEE — Take a screenshot and analyze it
```bash
python3 ~/.claude/skills/mac-desktop-use/scripts/desktop_control.py screenshot --path /tmp/step_N.png
```
Then read the screenshot with the Read tool to visually analyze it.
Identify UI elements, their positions, and what action to take next.

### 3. THINK — Determine the action
Based on the screenshot analysis:
- Identify the target UI element (button, text field, menu item, etc.)
- Estimate its pixel coordinates (center of the element)
- Decide the action type (click, type, hotkey, etc.)

### 4. ACT — Execute the action
```bash
python3 ~/.claude/skills/mac-desktop-use/scripts/desktop_control.py click 500 300
```

### 5. VERIFY — Screenshot again to confirm the result
```bash
python3 ~/.claude/skills/mac-desktop-use/scripts/desktop_control.py wait 1
python3 ~/.claude/skills/mac-desktop-use/scripts/desktop_control.py screenshot --path /tmp/step_N_verify.png
```
Read the verification screenshot. If the action succeeded, proceed to next step.
If not (e.g., no page transition, button not pressed):
- **Retry with jitter**: Try clicking again but shift the coordinates slightly (e.g., ±2-5 pixels) in different directions (up, down, left, right). Sometimes the interactive area of a button is slightly offset from its visual center.
- **Fresh analysis**: If retries fail, take a new screenshot and re-calculate coordinates.

### 6. REPEAT — Continue until task is complete

## Coordinate Estimation Tips

- macOS screen origin (0,0) is top-left corner
- On Retina displays, screencapture produces 2x resolution images. The **coordinates used by cliclick are in logical points** (not physical pixels). If the screenshot is 2x the screen resolution, divide observed pixel positions by 2 for cliclick coordinates
- Menu bar is approximately at y=11 (center of the 22px menu bar)
- Dock position varies; check screenshot to determine
- When estimating button/element centers, look at the visual center of the element in the screenshot
- For text fields: click to focus, then use `type` command
- For dropdown menus: click to open, wait, then click the option
- **Hitbox variability**: If a click at the visual center doesn't work, try clicking slightly offset positions (up, down, left, right) as the actual "hitbox" might not perfectly align with the visual element.

## Common Patterns

**Open app and click a menu:**
```bash
DC=~/.claude/skills/mac-desktop-use/scripts/desktop_control.py
python3 $DC open "TextEdit"
python3 $DC wait 2
python3 $DC screenshot --path /tmp/s1.png
# [analyze screenshot, find menu position]
python3 $DC click 50 11     # Click "File" menu
python3 $DC wait 0.5
python3 $DC screenshot --path /tmp/s2.png
# [analyze, find menu item]
python3 $DC click 50 140    # Click menu item
```

**Type into a text field:**
```bash
python3 $DC click 400 300   # Click the text field
python3 $DC wait 0.3
python3 $DC hotkey "cmd+a"  # Select all existing text
python3 $DC type "New text content"
```

**Save a file:**
```bash
python3 $DC hotkey "cmd+s"
python3 $DC wait 1
python3 $DC screenshot --path /tmp/save_dialog.png
# [analyze save dialog, find filename field and save button]
```

## Important Notes

- **Click Jitter Strategy**: If a click fails to trigger the expected response (no UI change or transition), do not just repeat the exact same coordinates. Instead, **float the coordinates by a few pixels (±3-5px) in different directions** and try again. UI elements sometimes have non-responsive borders or slightly offset hitboxes.
- Always take a screenshot before acting — never guess coordinates blindly
- Add `wait` between actions to let the UI update (0.3-1s for simple actions, 2-3s for app launches)
- If an action fails, retry with adjusted coordinates based on a fresh screenshot
- For Retina displays: screenshot pixel coordinates must be divided by the scale factor (usually 2) to get cliclick coordinates
- Confirm with the user before performing destructive actions (deleting files, sending messages, etc.)
- If the task involves sensitive data, inform the user that screenshots will be saved to /tmp
