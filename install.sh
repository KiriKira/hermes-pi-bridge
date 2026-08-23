#!/usr/bin/env bash
# hermes-pi-bridge installer
# Installs/symlinks the plugin and skills into place and creates a model-tier
# configuration template. Safe to re-run: existing symlinks are refreshed and
# user configuration/authentication files are never overwritten.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

PLUGIN_SRC="$REPO_DIR/plugin"
SKILL_SRC="$REPO_DIR/skill/SKILL.md"
SKILL_SESSION_SRC="$REPO_DIR/skill/SKILL_SESSION.md"
SKILL_BOOTSTRAP_SRC="$REPO_DIR/skill/SKILL_BOOTSTRAP.md"
SKILL_RE_SRC="$REPO_DIR/skill/SKILL_RE.md"
MODEL_CONFIG_SRC="$REPO_DIR/config/pi-bridge-models.example.yaml"

PLUGIN_DEST="$HERMES_HOME/plugins/pi-bridge"
SKILL_DEST="$HERMES_HOME/skills/software-development/pi-task-delegation"
SKILL_SESSION_DEST="$HERMES_HOME/skills/software-development/pi-interactive-session"
SKILL_BOOTSTRAP_DEST="$HERMES_HOME/skills/software-development/pi-bootstrap"
SKILL_RE_DEST="$HERMES_HOME/skills/software-development/pi-reverse-engineering-flow"
MODEL_CONFIG_DEST="$HERMES_HOME/pi-bridge-models.yaml"

FORCE=false
INSTALL_PI=false
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
    --install-pi) INSTALL_PI=true ;;
    --help|-h)
      cat <<'EOF'
Usage: bash install.sh [--install-pi] [--force]

  --install-pi  Install @mariozechner/pi-coding-agent with npm when `pi` is missing.
  --force       Replace existing non-symlink plugin/skill files with repository symlinks.

The installer never overwrites ~/.pi/agent authentication/configuration files
or an existing ~/.hermes/pi-bridge-models.yaml.
EOF
      exit 0
      ;;
  esac
done

ok()   { echo "  [ok] $*"; }
info() { echo "  [--] $*"; }
warn() { echo "  [!!] $*"; }
fail() { echo "  [xx] $*" >&2; exit 1; }

echo
echo "hermes-pi-bridge installer"
echo "=========================="
echo

# ── Optional pi bootstrap ───────────────────────────────────────────────────
echo "0. Checking pi coding agent"
if command -v pi &>/dev/null; then
  PI_VER=$(pi --version 2>/dev/null || echo "unknown")
  ok "pi found: $PI_VER"
elif $INSTALL_PI; then
  command -v npm &>/dev/null || fail "npm is required for --install-pi"
  info "pi not found; installing @mariozechner/pi-coding-agent"
  npm install -g @mariozechner/pi-coding-agent
  command -v pi &>/dev/null || fail "npm completed but pi is still not reachable in PATH"
  PI_VER=$(pi --version 2>/dev/null || echo "unknown")
  ok "pi installed: $PI_VER"
else
  warn "pi not found in PATH"
  info "Re-run with --install-pi, or install manually: npm install -g @mariozechner/pi-coding-agent"
fi

link_skill() {
  local src="$1"
  local dest_dir="$2"
  local label="$3"

  echo "$label → $dest_dir/SKILL.md"
  mkdir -p "$dest_dir"
  if [[ -L "$dest_dir/SKILL.md" ]]; then
    rm "$dest_dir/SKILL.md"
    ln -s "$src" "$dest_dir/SKILL.md"
    ok "symlink updated"
  elif [[ -f "$dest_dir/SKILL.md" ]]; then
    if $FORCE; then
      rm "$dest_dir/SKILL.md"
      ln -s "$src" "$dest_dir/SKILL.md"
      ok "replaced with symlink (--force)"
    else
      warn "$dest_dir/SKILL.md exists. Use --force to replace."
    fi
  else
    ln -s "$src" "$dest_dir/SKILL.md"
    ok "symlink created"
  fi
}

# ── Plugin ─────────────────────────────────────────────────────────────────
echo "1. Hermes plugin → $PLUGIN_DEST"
mkdir -p "$HERMES_HOME/plugins"
if [[ -L "$PLUGIN_DEST" ]]; then
  rm "$PLUGIN_DEST"
  ln -s "$PLUGIN_SRC" "$PLUGIN_DEST"
  ok "symlink updated"
elif [[ -d "$PLUGIN_DEST" ]]; then
  if $FORCE; then
    rm -rf "$PLUGIN_DEST"
    ln -s "$PLUGIN_SRC" "$PLUGIN_DEST"
    ok "replaced with symlink (--force)"
  else
    warn "$PLUGIN_DEST exists. Use --force to replace."
  fi
else
  ln -s "$PLUGIN_SRC" "$PLUGIN_DEST"
  ok "symlink created"
fi

# ── Skills ─────────────────────────────────────────────────────────────────
link_skill "$SKILL_SRC" "$SKILL_DEST" "2. Task delegation skill"
link_skill "$SKILL_SESSION_SRC" "$SKILL_SESSION_DEST" "3. Interactive session skill"
link_skill "$SKILL_BOOTSTRAP_SRC" "$SKILL_BOOTSTRAP_DEST" "4. Bootstrap skill"
link_skill "$SKILL_RE_SRC" "$SKILL_RE_DEST" "5. Reverse-engineering flow skill"

# ── Model-tier config ───────────────────────────────────────────────────────
echo "6. Model-tier config → $MODEL_CONFIG_DEST"
mkdir -p "$HERMES_HOME"
if [[ -f "$MODEL_CONFIG_DEST" ]]; then
  ok "existing model-tier config preserved"
else
  cp "$MODEL_CONFIG_SRC" "$MODEL_CONFIG_DEST"
  ok "created from template"
fi

# ── Hermes config ───────────────────────────────────────────────────────────
echo "7. Hermes config.yaml — checking pi_bridge toolset"
HERMES_CONFIG="$HERMES_HOME/config.yaml"
if [[ -f "$HERMES_CONFIG" ]]; then
  if grep -q "pi_bridge" "$HERMES_CONFIG"; then
    ok "pi_bridge already present in config.yaml"
  elif grep -q -- "- hermes-cli" "$HERMES_CONFIG"; then
    # Keep the original installer's behavior for compatible Hermes configs.
    # This is deliberately narrow: if the expected anchor is absent, do not
    # guess at the user's YAML structure.
    sed -i '/- hermes-cli/a\- pi_bridge' "$HERMES_CONFIG"
    ok "pi_bridge added to toolsets in config.yaml"
  else
    warn "Could not find '- hermes-cli' anchor in config.yaml"
    info "Add 'pi_bridge' to the appropriate toolsets list manually."
  fi
else
  warn "config.yaml not found at $HERMES_CONFIG"
  info "After Hermes creates it, add 'pi_bridge' to the appropriate toolsets list."
fi

# ── Final verification hints ────────────────────────────────────────────────
echo "8. Verification"
if command -v pi &>/dev/null; then
  PI_VER=$(pi --version 2>/dev/null || echo "unknown")
  ok "pi reachable: $PI_VER"
else
  warn "pi still not reachable; the bridge will not execute tasks until pi is installed"
fi

if [[ -d "$HOME/.pi/agent" ]]; then
  ok "pi agent directory exists: $HOME/.pi/agent"
else
  warn "~/.pi/agent does not exist yet; pi may still need provider/model setup"
fi

cat <<EOF

Done.

Next steps for Hermes:
  1. Restart Hermes so the plugin and skills load.
  2. Run pi_check().
  3. Read/edit: $MODEL_CONFIG_DEST
  4. For RE work: skill_view("pi-reverse-engineering-flow")

For a machine-readable/operator-oriented bootstrap sequence, read:
  $REPO_DIR/HERMES_BOOTSTRAP.md

EOF
