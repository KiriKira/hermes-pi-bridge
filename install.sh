#!/usr/bin/env bash
# hermes-pi-bridge installer
# Installs the plugin, the single pi-flow skill, and a model-routing template.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PI_PACKAGE="@earendil-works/pi-coding-agent"

PLUGIN_SRC="$REPO_DIR/plugin"
FLOW_SKILL_SRC="$REPO_DIR/skill/SKILL_FLOW.md"
FLOW_CONFIG_SRC="$REPO_DIR/config/pi-flow.example.yaml"

PLUGIN_DEST="$HERMES_HOME/plugins/pi-bridge"
FLOW_SKILL_DEST="$HERMES_HOME/skills/software-development/pi-flow"
FLOW_CONFIG_DEST="$HERMES_HOME/pi-flow.yaml"
FLOW_LIBRARY_DEST="$HERMES_HOME/pi-flows"

FORCE=false
INSTALL_PI=false
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
    --install-pi) INSTALL_PI=true ;;
    --help|-h)
      cat <<EOF
Usage: bash install.sh [--install-pi] [--force]

  --install-pi  Install $PI_PACKAGE with npm if pi is missing.
  --force       Replace existing non-symlink plugin/skill paths.

Existing pi credentials and ~/.hermes/pi-flow.yaml are never overwritten.
EOF
      exit 0
      ;;
  esac
done

ok()   { echo "  [ok] $*"; }
info() { echo "  [--] $*"; }
warn() { echo "  [!!] $*"; }
fail() { echo "  [xx] $*" >&2; exit 1; }

link_path() {
  local src="$1"
  local dest="$2"
  local label="$3"

  echo "$label -> $dest"
  mkdir -p "$(dirname "$dest")"

  if [[ -L "$dest" ]]; then
    rm "$dest"
    ln -s "$src" "$dest"
    ok "symlink updated"
  elif [[ -e "$dest" ]]; then
    if $FORCE; then
      rm -rf "$dest"
      ln -s "$src" "$dest"
      ok "replaced with symlink (--force)"
    else
      warn "$dest already exists; use --force to replace it"
    fi
  else
    ln -s "$src" "$dest"
    ok "symlink created"
  fi
}

echo
echo "hermes-pi-bridge installer"
echo "=========================="
echo

echo "0. pi coding agent"
if command -v pi >/dev/null 2>&1; then
  ok "pi found: $(pi --version 2>/dev/null || echo unknown)"
elif $INSTALL_PI; then
  command -v npm >/dev/null 2>&1 || fail "npm is required to install pi"
  info "installing $PI_PACKAGE"
  npm install -g --ignore-scripts "$PI_PACKAGE"
  command -v pi >/dev/null 2>&1 || fail "npm finished but pi is not reachable in PATH"
  ok "pi installed: $(pi --version 2>/dev/null || echo unknown)"
else
  warn "pi not found"
  info "re-run with --install-pi, or install manually: npm install -g --ignore-scripts $PI_PACKAGE"
fi

link_path "$PLUGIN_SRC" "$PLUGIN_DEST" "1. Hermes plugin"

mkdir -p "$FLOW_SKILL_DEST"
link_path "$FLOW_SKILL_SRC" "$FLOW_SKILL_DEST/SKILL.md" "2. pi-flow skill"

echo "3. pi-flow routing config -> $FLOW_CONFIG_DEST"
mkdir -p "$HERMES_HOME"
if [[ -f "$FLOW_CONFIG_DEST" ]]; then
  ok "existing config preserved"
else
  cp "$FLOW_CONFIG_SRC" "$FLOW_CONFIG_DEST"
  ok "created from template"
fi

mkdir -p "$FLOW_LIBRARY_DEST"
ok "flow library directory: $FLOW_LIBRARY_DEST"

echo "4. Hermes config"
HERMES_CONFIG="$HERMES_HOME/config.yaml"
if [[ ! -f "$HERMES_CONFIG" ]]; then
  warn "$HERMES_CONFIG does not exist yet; add pi_bridge to the appropriate toolsets list after Hermes creates it"
elif grep -qE '^[[:space:]]*-[[:space:]]*pi_bridge[[:space:]]*$' "$HERMES_CONFIG"; then
  ok "pi_bridge already enabled"
elif command -v python3 >/dev/null 2>&1; then
  if python3 - "$HERMES_CONFIG" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
lines = text.splitlines(keepends=True)
anchor = re.compile(r'^(\s*)-\s*hermes-cli\s*(?:#.*)?$')

for index, line in enumerate(lines):
    match = anchor.match(line.rstrip('\n'))
    if match:
        newline = '\n' if line.endswith('\n') else ''
        lines.insert(index + 1, f"{match.group(1)}- pi_bridge{newline}")
        path.write_text(''.join(lines))
        raise SystemExit(0)
raise SystemExit(2)
PY
  then
    ok "pi_bridge added next to hermes-cli with matching indentation"
  else
    warn "could not find a hermes-cli toolset entry; add '- pi_bridge' to the intended toolsets list manually"
  fi
else
  warn "python3 unavailable; add '- pi_bridge' to the intended toolsets list manually"
fi

echo "5. verification"
if command -v pi >/dev/null 2>&1; then
  ok "pi reachable"
else
  warn "pi is still missing; bridge execution will fail until it is installed"
fi

cat <<EOF

Done.

Restart Hermes, then:
  1. call pi_check()
  2. review $FLOW_CONFIG_DEST if you want different fast/standard/deep models
  3. use: "通过 pi_flow 去 <goal>"

For first-time setup instructions readable by Hermes, see:
  $REPO_DIR/HERMES_BOOTSTRAP.md

EOF
