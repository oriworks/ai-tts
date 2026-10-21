#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Install the `speak` voice (Piper TTS) for coding agents on Linux/WSL.
#
#   ./install.sh [--voice NAME] [--skills-dir DIR]... [--no-hooks] [--no-auto] [--no-test]
#   ./install.sh --uninstall
#
# Safe to run again: it updates the venv, the wrapper, the skill links and the Claude Code hooks in place.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO/.venv"
PY="$VENV/bin/python"
BIN_DIR="$HOME/.local/bin"
WRAPPER="$BIN_DIR/speak"
CONFIG_DIR="$HOME/.config/speak"
CONFIG="$CONFIG_DIR/config.toml"
VOICES_DIR="$HOME/.local/share/speak/voices"
RUN_DIR="$HOME/.cache/speak"
CLAUDE_DIR="$HOME/.claude"

VOICE="" HOOKS=1 AUTO=1 TEST=1 UNINSTALL=0
SKILL_DIRS=("$HOME/.agents/skills")
[ -d "$CLAUDE_DIR" ] && SKILL_DIRS+=("$CLAUDE_DIR/skills")

usage() { sed -n '3,8p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --voice) VOICE="$2"; shift ;;
    --skills-dir) SKILL_DIRS+=("$2"); shift ;;
    --no-hooks) HOOKS=0 ;;
    --no-auto) AUTO=0 ;;
    --no-test) TEST=0 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage ;;
    *) echo "unknown option: $1" >&2; usage 1 ;;
  esac
  shift
done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }

# Add (install) or remove (uninstall) the speak hooks and permission in ~/.claude/settings.json.
claude_settings() {
  local settings="$CLAUDE_DIR/settings.json"
  [ -f "$settings" ] && cp "$settings" "$settings.bak"
  python3 - "$1" "$settings" "$WRAPPER" "$PY" "$REPO/autospeak.py" <<'EOF'
import json, os, sys

mode, path, wrapper, py, autospeak = sys.argv[1:]
try:
    settings = json.load(open(path))
except FileNotFoundError:
    settings = {}
ours = lambda h: any(m in h.get("command", "").replace("'", "") for m in ("speak --start", "autospeak.py"))

hooks = settings.setdefault("hooks", {})
for event in list(hooks):
    groups = []
    for g in hooks[event]:
        g["hooks"] = [h for h in g.get("hooks", []) if not ours(h)]
        if g["hooks"]:
            groups.append(g)
    hooks[event] = groups
allow = settings.setdefault("permissions", {}).setdefault("allow", [])
allow[:] = [p for p in allow if p != "Bash(speak:*)"]

if mode == "install":
    hooks.setdefault("SessionStart", []).append({
        "matcher": "^(startup|resume|clear)$",
        "hooks": [{"type": "command", "command": f"('{wrapper}' --start >/dev/null 2>&1 &)", "timeout": 10}],
    })
    hooks.setdefault("Stop", []).append({
        "hooks": [{"type": "command", "command": f"'{py}' '{autospeak}'", "timeout": 10}],
    })
    allow.append("Bash(speak:*)")

for key in [k for k, v in hooks.items() if not v]:
    del hooks[key]
if not hooks:
    del settings["hooks"]
if not allow:
    del settings["permissions"]["allow"]
if not settings["permissions"]:
    del settings["permissions"]
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
    f.write("\n")
EOF
}

stop_daemon() {
  [ -x "$WRAPPER" ] && "$WRAPPER" --stop 2>/dev/null || true
  pkill -f "$REPO/speak.py --daemon" 2>/dev/null || true
}

if [ "$UNINSTALL" = 1 ]; then
  stop_daemon
  if [ -d "$CLAUDE_DIR" ]; then
    say "Removing Claude Code hooks and permission"
    claude_settings uninstall
  fi
  for dir in "${SKILL_DIRS[@]}"; do
    link="$dir/speech"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$REPO/skill/speech" ]; then
      say "Removing skill link $link"; rm "$link"
    fi
  done
  if [ -f "$WRAPPER" ] && grep -q "$REPO" "$WRAPPER"; then
    say "Removing $WRAPPER"; rm "$WRAPPER"
  fi
  rm -rf "$RUN_DIR"
  if [ -t 0 ]; then
    read -rp "Also delete voices ($VOICES_DIR) and config ($CONFIG_DIR)? [y/N] " ans
    [[ "$ans" =~ ^[yY] ]] && rm -rf "$VOICES_DIR" "$CONFIG_DIR" && say "Deleted voices and config"
  fi
  say "Uninstalled. Remove $VENV or the whole clone if you no longer need it."
  exit 0
fi

# 1. Requirements (uv is used when present; it also fetches a suitable Python)
if ! command -v uv >/dev/null && [ ! -x "$PY" ]; then
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null \
    || { echo "speak needs Python 3.11 or newer (python3 is $(python3 --version 2>&1)), or uv" >&2; exit 1; }
  python3 -c 'import venv, ensurepip' 2>/dev/null \
    || { echo "python3 venv support is missing: sudo apt install python3-venv (or install uv)" >&2; exit 1; }
fi
if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
  warn "PortAudio not found, speech will only be saved to WAV files. To hear it:"
  warn "  sudo apt install libportaudio2 libasound2-plugins"
  grep -qi microsoft /proc/version 2>/dev/null && warn "  (on WSL, audio goes through WSLg's PulseAudio server)"
fi

# 2. Python environment
say "Installing Python packages in $VENV"
if command -v uv >/dev/null; then
  [ -x "$PY" ] || uv venv --quiet --python 3.12 "$VENV"
  uv pip install --quiet --python "$PY" -r "$REPO/requirements.txt"
else
  [ -x "$PY" ] || python3 -m venv "$VENV"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r "$REPO/requirements.txt"
fi

# 3. Command wrapper
say "Writing $WRAPPER"
mkdir -p "$BIN_DIR"
printf '#!/usr/bin/env bash\nexec "%s" "%s" "$@"\n' "$PY" "$REPO/speak.py" > "$WRAPPER"
chmod +x "$WRAPPER"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) warn "$BIN_DIR is not in your PATH; add it to your shell profile" ;; esac

# 4. Config and pronunciations
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG" ]; then
  say "Creating $CONFIG"
  rate=$(cat "$RUN_DIR/rate" 2>/dev/null || echo 1.15)  # pace saved by older versions
  sed -e "s/^rate = .*/rate = $rate/" "$REPO/config.example.toml" > "$CONFIG"
  rm -f "$RUN_DIR/rate"
fi

# 5. Voice model: only the one the user chose (no default voice is installed)
[ -n "$VOICE" ] && "$WRAPPER" --use "$VOICE" >/dev/null
VOICE=$("$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); import speak; print(speak.load_config()["voice"])' "$REPO")
LANG_FILE="$REPO/pronunciations/${VOICE%%-*}.txt"
if [ -n "$VOICE" ] && [ ! -f "$CONFIG_DIR/pronunciations.txt" ] && [ -f "$LANG_FILE" ]; then
  say "Copying pronunciations for ${VOICE%%-*} to $CONFIG_DIR/pronunciations.txt"
  cp "$LANG_FILE" "$CONFIG_DIR/pronunciations.txt"
fi

# 6. Skill (Agent Skills format, shared by agents that read ~/.agents/skills)
for dir in "${SKILL_DIRS[@]}"; do
  link="$dir/speech"
  mkdir -p "$dir"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    warn "moving existing $link to $link.bak"
    rm -rf "$link.bak"; mv "$link" "$link.bak"
  fi
  ln -sfn "$REPO/skill/speech" "$link"
  say "Linked skill into $dir"
done

# 7. Claude Code hooks (start the daemon with each session, speak every reply)
stop_daemon  # a running daemon may be from an older version
if [ "$HOOKS" = 1 ] && [ -d "$CLAUDE_DIR" ]; then
  say "Adding Claude Code hooks to $CLAUDE_DIR/settings.json (backup in settings.json.bak)"
  claude_settings install
fi

# 8. Automatic mode and a test sentence
"$WRAPPER" --auto "$([ "$AUTO" = 1 ] && echo on || echo off)"
if [ -z "$VOICE" ]; then
  warn "no voice installed yet. Pick one (and check its licence) with:"
  warn "  speak --list pt        # or en, es, fr..."
  warn "  speak --use NAME"
elif [ "$TEST" = 1 ]; then
  case "$VOICE" in
    pt_*) "$WRAPPER" "A voz está instalada." ;;
    *) "$WRAPPER" "The voice is installed." ;;
  esac
fi
say "Done. Try: speak \"hello\"   |   settings: $CONFIG"
