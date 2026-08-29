#!/usr/bin/env bash
# Install opencode config from the skills repo.
#
# Clones (or updates) the repo into ~/.config/opencode-config, then links:
#   opencode.jsonc      -> ~/.config/opencode/opencode.jsonc
#   tui.jsonc           -> ~/.config/opencode/tui.jsonc
#   .opencode/agent/    -> ~/.config/opencode/agent/
#
# Existing files/links at the targets are replaced (ln -sfn). A pre-existing
# real directory at ~/.config/opencode/agent is moved aside once with a
# timestamp suffix, since a symlink cannot replace a non-empty directory.
set -euo pipefail

REPO_URL="${OPENCODE_CONFIG_REPO:-https://github.com/Swaggerzhan/skills.git}"
REPO_DIR="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode-config}"
TARGET_DIR="$HOME/.config/opencode"

log() { printf '[install] %s\n' "$*"; }

if ! command -v git >/dev/null 2>&1; then
  printf '[install] error: git is not installed\n' >&2
  exit 1
fi

# Clone or update the repo.
if [ -d "$REPO_DIR/.git" ]; then
  log "updating repo in $REPO_DIR"
  git -C "$REPO_DIR" pull --ff-only
else
  if [ -e "$REPO_DIR" ]; then
    printf '[install] error: %s exists but is not a git repo; move it away first\n' "$REPO_DIR" >&2
    exit 1
  fi
  log "cloning $REPO_URL into $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

mkdir -p "$TARGET_DIR"

# If the agent target is a real directory, move it aside once; a symlink
# cannot replace a non-empty directory with ln -sfn alone.
if [ -d "$TARGET_DIR/agent" ] && [ ! -L "$TARGET_DIR/agent" ]; then
  backup="$TARGET_DIR/agent.bak.$(date +%Y%m%d%H%M%S)"
  log "moving existing agent directory to $backup"
  mv "$TARGET_DIR/agent" "$backup"
fi

log "linking opencode.jsonc"
ln -sfn "$REPO_DIR/opencode.jsonc" "$TARGET_DIR/opencode.jsonc"

log "linking tui.jsonc"
ln -sfn "$REPO_DIR/tui.jsonc" "$TARGET_DIR/tui.jsonc"

log "linking agent directory"
ln -sfn "$REPO_DIR/.opencode/agent" "$TARGET_DIR/agent"

log "done. restart opencode for changes to take effect."
