#!/bin/sh

# Install one repository Skill as symlinks for Codex and Agent-compatible clients.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jindon1020/osi-skills/main/install-linked-skill.sh \
#     | sh -s -- translate-agentos-workflow-package

set -eu

SKILL_NAME="${1:-translate-agentos-workflow-package}"
REPO_URL="${OSI_SKILLS_REPO_URL:-https://github.com/jindon1020/osi-skills.git}"
INSTALL_ROOT="${OSI_SKILLS_INSTALL_ROOT:-$HOME/.local/share/osi-skills}"
REPO_DIR="$INSTALL_ROOT/repo"
TARGET_DIRS="${OSI_SKILLS_TARGET_DIRS:-$HOME/.codex/skills:$HOME/.agent/skills:$HOME/.agents/skills}"

case "$SKILL_NAME" in
  ''|*[!A-Za-z0-9._-]*)
    echo "Invalid skill name: $SKILL_NAME" >&2
    exit 2
    ;;
esac

if [ -n "${OSI_SKILLS_CHECKOUT:-}" ]; then
  REPO_DIR="$OSI_SKILLS_CHECKOUT"
else
  if ! command -v git >/dev/null 2>&1; then
    echo "git is required" >&2
    exit 1
  fi

  mkdir -p "$INSTALL_ROOT"
  if [ -d "$REPO_DIR/.git" ]; then
    CURRENT_REMOTE="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null || true)"
    if [ "$CURRENT_REMOTE" != "$REPO_URL" ]; then
      echo "Refusing to update $REPO_DIR: origin is '$CURRENT_REMOTE', expected '$REPO_URL'" >&2
      exit 1
    fi
    git -C "$REPO_DIR" pull --ff-only
  elif [ -e "$REPO_DIR" ]; then
    echo "Refusing to overwrite existing non-repository path: $REPO_DIR" >&2
    exit 1
  else
    git clone --depth 1 "$REPO_URL" "$REPO_DIR"
  fi
fi

SOURCE="$REPO_DIR/$SKILL_NAME"
if [ ! -f "$SOURCE/SKILL.md" ]; then
  echo "Skill not found in repository: $SKILL_NAME" >&2
  exit 1
fi

SOURCE="$(cd "$SOURCE" && pwd -P)"
OLD_IFS="$IFS"
IFS=':'
set -- $TARGET_DIRS
IFS="$OLD_IFS"

CONFLICTS=0
for TARGET_DIR in "$@"; do
  [ -n "$TARGET_DIR" ] || continue
  mkdir -p "$TARGET_DIR"
  DEST="$TARGET_DIR/$SKILL_NAME"

  if [ -L "$DEST" ]; then
    CURRENT="$(readlink "$DEST")"
    if [ "$CURRENT" = "$SOURCE" ]; then
      echo "Already linked: $DEST"
    else
      echo "Refusing to replace symlink: $DEST -> $CURRENT" >&2
      CONFLICTS=1
    fi
  elif [ -e "$DEST" ]; then
    echo "Refusing to replace existing path: $DEST" >&2
    CONFLICTS=1
  else
    ln -s "$SOURCE" "$DEST"
    echo "Linked: $DEST -> $SOURCE"
  fi
done

if [ "$CONFLICTS" -ne 0 ]; then
  echo "Installation completed with conflicts; existing paths were preserved." >&2
  exit 1
fi

echo "Installed $SKILL_NAME. Restart the relevant agent to reload skills."
