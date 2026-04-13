#!/usr/bin/env bash
# hermes-pi-bridge installer
# Symlinks the plugin and skills into place.
# Safe to re-run — existing symlinks are updated, files are not overwritten unless --force.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

PLUGIN_SRC="$REPO_DIR/plugin"
SKILL_SRC="$REPO_DIR/skill/SKILL.md"
SKILL_SESSION_SRC="$REPO_DIR/skill/SKILL_SESSION.md"

PLUGIN_DEST="$HERMES_HOME/plugins/pi-bridge"
SKILL_DEST="$HERMES_HOME/skills/software-development/pi-task-delegation"
SKILL_SESSION_DEST="$HERMES_HOME/skills/software-development/pi-interactive-session"

FORCE=false
for arg in "$@"; do
  [[ "$arg" == "--force" ]] && FORCE=true
done

ok()   { echo "  [ok] $*"; }
info() { echo "  [--] $*"; }
warn() { echo "  [!!] $*"; }

echo
echo "hermes-pi-bridge installer"
echo "=========================="
echo

# ── Plugin ─────────────────────────────────────────────────────────────────
echo "1. Hermes plugin → $PLUGIN_DEST"
mkdir -p "$HERMES_HOME/plugins"
if [[ -L "$PLUGIN_DEST" ]]; then
  rm "$PLUGIN_DEST"; ln -s "$PLUGIN_SRC" "$PLUGIN_DEST"; ok "symlink updated"
elif [[ -d "$PLUGIN_DEST" ]]; then
  if $FORCE; then rm -rf "$PLUGIN_DEST"; ln -s "$PLUGIN_SRC" "$PLUGIN_DEST"; ok "replaced with symlink (--force)"
  else warn "$PLUGIN_DEST exists. Use --force to replace."; fi
else
  ln -s "$PLUGIN_SRC" "$PLUGIN_DEST"; ok "symlink created"
fi

# ── Task delegation skill ───────────────────────────────────────────────────
echo "2. Task delegation skill → $SKILL_DEST/SKILL.md"
mkdir -p "$SKILL_DEST"
if [[ -L "$SKILL_DEST/SKILL.md" ]]; then
  rm "$SKILL_DEST/SKILL.md"; ln -s "$SKILL_SRC" "$SKILL_DEST/SKILL.md"; ok "symlink updated"
elif [[ -f "$SKILL_DEST/SKILL.md" ]]; then
  if $FORCE; then rm "$SKILL_DEST/SKILL.md"; ln -s "$SKILL_SRC" "$SKILL_DEST/SKILL.md"; ok "replaced (--force)"
  else warn "$SKILL_DEST/SKILL.md exists. Use --force."; fi
else
  ln -s "$SKILL_SRC" "$SKILL_DEST/SKILL.md"; ok "symlink created"
fi

# ── Interactive session skill ───────────────────────────────────────────────
echo "3. Interactive session skill → $SKILL_SESSION_DEST/SKILL.md"
mkdir -p "$SKILL_SESSION_DEST"
if [[ -L "$SKILL_SESSION_DEST/SKILL.md" ]]; then
  rm "$SKILL_SESSION_DEST/SKILL.md"; ln -s "$SKILL_SESSION_SRC" "$SKILL_SESSION_DEST/SKILL.md"; ok "symlink updated"
elif [[ -f "$SKILL_SESSION_DEST/SKILL.md" ]]; then
  if $FORCE; then rm "$SKILL_SESSION_DEST/SKILL.md"; ln -s "$SKILL_SESSION_SRC" "$SKILL_SESSION_DEST/SKILL.md"; ok "replaced (--force)"
  else warn "$SKILL_SESSION_DEST/SKILL.md exists. Use --force."; fi
else
  ln -s "$SKILL_SESSION_SRC" "$SKILL_SESSION_DEST/SKILL.md"; ok "symlink created"
fi

# ── Hermes config ───────────────────────────────────────────────────────────
echo "4. Hermes config.yaml — checking pi_bridge toolset"
HERMES_CONFIG="$HERMES_HOME/config.yaml"
if [[ -f "$HERMES_CONFIG" ]]; then
  if grep -q "pi_bridge" "$HERMES_CONFIG"; then
    ok "pi_bridge already in config.yaml"
  else
    sed -i '/- hermes-cli/a - pi_bridge' "$HERMES_CONFIG"
    ok "pi_bridge added to toolsets in config.yaml"
  fi
else
  warn "config.yaml not found at $HERMES_CONFIG — add 'pi_bridge' to toolsets manually"
fi

# ── Check pi installation ───────────────────────────────────────────────────
echo "5. Checking pi installation"
if command -v pi &>/dev/null; then
  PI_VER=$(pi --version 2>/dev/null || echo "unknown")
  ok "pi found: $PI_VER"
else
  PI_LOCAL="$HOME/.local/bin/pi"
  if [[ -f "$PI_LOCAL" ]]; then
    PI_VER=$("$PI_LOCAL" --version 2>/dev/null || echo "unknown")
    ok "pi found at $PI_LOCAL: $PI_VER"
  else
    warn "pi not found in PATH"
    info "Install with: npm install -g @mariozechner/pi-coding-agent"
  fi
fi

echo
echo "Done. Restart Hermes to load the plugin."
echo
