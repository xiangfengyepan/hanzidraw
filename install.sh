#!/usr/bin/env bash
# Install hanzidraw on Linux (or macOS). Idempotent: safe to re-run.
#
# Usage:
#   ./install.sh                 # install, then build the character database if absent
#   ./install.sh --no-data       # skip the database step entirely
#   ./install.sh --db FILE       # import a prebuilt database (.sqlite or .sqlite.gz)
#   ./install.sh --yes           # never prompt; assume yes to uv install and system packages
#   ./install.sh --no-extras     # base install only: no GUI, no mouse backend
set -euo pipefail

# Piped execution ("curl ... | bash") has no script file, so BASH_SOURCE is unset.
# Fall back to the working directory, which is also where a wheel or checkout would be.
SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$SELF" ]; then
  HERE="$(cd "$(dirname "$SELF")" && pwd)"
else
  HERE="$PWD"
fi
ASSUME_YES=0; SKIP_DATA=0; DB_FILE=""; EXTRAS="[gui,mouse]"
PYTHON_VERSION="3.12"          # PySide6 has no wheels for 3.13+ yet; do not "upgrade" this
REPO_URL="https://github.com/xiangfengyepan/hanzidraw"

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)    ASSUME_YES=1 ;;
    --no-data)   SKIP_DATA=1 ;;
    --no-extras) EXTRAS="" ;;
    --db)        shift; DB_FILE="${1:-}"; [ -n "$DB_FILE" ] || { echo "--db needs a file path" >&2; exit 2; } ;;
    --python)    shift; PYTHON_VERSION="${1:-}" ;;
    -h|--help)
      if [ -n "$SELF" ] && [ -f "$SELF" ]; then
        awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$SELF"
      else
        # Piped in: the comment block is not on disk to read back.
        printf '%s\n' \
          "Install hanzidraw on Linux (or macOS). Idempotent: safe to re-run." "" \
          "  --no-data     skip the character database step" \
          "  --db FILE     import a prebuilt database (.sqlite or .sqlite.gz)" \
          "  --no-extras   base install only: no GUI, no mouse backend" \
          "  --yes         never prompt" \
          "  --python VER  Python version to install under (default 3.12)"
      fi
      exit 0 ;;
    *)           echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

ask() {   # ask "question" -> 0 for yes. --yes answers yes; a non-tty answers no.
  [ "$ASSUME_YES" = 1 ] && return 0
  [ -t 0 ] || { warn "not a terminal, assuming no: $1"; return 1; }
  printf '%s [y/N] ' "$1"; read -r reply
  case "$reply" in [yY]*) return 0 ;; *) return 1 ;; esac
}

# ---------------------------------------------------------------- uv
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  say "uv is not installed. It manages the Python version and installs the app."
  ask "Install uv from https://astral.sh/uv (official installer)?" \
    || die "uv is required. Install it yourself, then re-run this script."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null 2>&1 || die "uv installed but not on PATH; open a new shell and re-run"
say "uv $(uv --version | awk '{print $2}')"

# ------------------------------------------------------- install the app
# Prefer this checkout, then a wheel sitting next to the script, then GitHub.
if [ -f "$HERE/pyproject.toml" ]; then
  TARGET="$HERE"; SOURCE="this checkout"
elif WHEEL=$(ls "$HERE"/hanzidraw-*.whl 2>/dev/null | head -1) && [ -n "${WHEEL:-}" ]; then
  TARGET="$WHEEL"; SOURCE="$(basename "$WHEEL")"
else
  TARGET="git+$REPO_URL"; SOURCE="$REPO_URL"
fi
say "installing hanzidraw${EXTRAS:+ with extras $EXTRAS} from $SOURCE"
# VIRTUAL_ENV would make uv install into an activated venv instead of as a tool.
env -u VIRTUAL_ENV uv tool install --force --python "$PYTHON_VERSION" "${TARGET}${EXTRAS}"

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) warn "$HOME/.local/bin is not on your PATH. Add it to ~/.bashrc:"
     printf '       export PATH="$HOME/.local/bin:$PATH"\n' ;;
esac

# --------------------------------------------- Qt's X11 system dependency
# PySide6 6.5+ needs libxcb-cursor at runtime. Without it the window does not
# open; it aborts with a wall of Qt plugin text instead, which is why this
# script checks rather than leaving you to decode that.
if [ -n "$EXTRAS" ] && [ "$(uname -s)" = "Linux" ]; then
  if ! ldconfig -p 2>/dev/null | grep -q 'libxcb-cursor\.so\.0'; then
    if command -v apt-get >/dev/null 2>&1; then
      say "Qt needs the system library libxcb-cursor0, which is missing."
      if ask "Install it now with sudo apt-get install libxcb-cursor0?"; then
        # Non-fatal on purpose: a sudo prompt that cannot be answered (no tty, no
        # rights) must not abort an otherwise complete install.
        sudo apt-get install -y libxcb-cursor0 \
          || warn "could not install it. Run this yourself: sudo apt-get install libxcb-cursor0"
      else
        warn "the drawing window will not open until you run: sudo apt-get install libxcb-cursor0"
      fi
    else
      warn "missing system library libxcb-cursor (package is usually libxcb-cursor0 / xcb-util-cursor)"
    fi
  fi
fi

# ------------------------------------------------------- character database
DB_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/hanzidraw"
DB="$DB_DIR/hanzidraw.sqlite"
if [ "$SKIP_DATA" = 1 ]; then
  say "skipping the database step (--no-data). Run 'hanzidraw fetch-data' when you want it."
elif [ -n "$DB_FILE" ]; then
  [ -f "$DB_FILE" ] || die "no such file: $DB_FILE"
  mkdir -p "$DB_DIR"
  say "importing $DB_FILE"
  case "$DB_FILE" in
    *.gz) gzip -dc "$DB_FILE" > "$DB.tmp" ;;
    *)    cp "$DB_FILE" "$DB.tmp" ;;
  esac
  mv "$DB.tmp" "$DB"           # swap in only once it is whole
elif [ -f "$DB" ]; then
  say "database already present: $DB ($(du -h "$DB" | cut -f1))"
else
  # Look for a prebuilt copy shipped next to the script before downloading 40 MB.
  if LOCAL_DB=$(ls "$HERE"/hanzidraw.sqlite.gz "$HERE"/hanzidraw.sqlite 2>/dev/null | head -1) && [ -n "${LOCAL_DB:-}" ]; then
    say "found a prebuilt database next to this script: $(basename "$LOCAL_DB")"
    mkdir -p "$DB_DIR"
    case "$LOCAL_DB" in *.gz) gzip -dc "$LOCAL_DB" > "$DB.tmp" ;; *) cp "$LOCAL_DB" "$DB.tmp" ;; esac
    mv "$DB.tmp" "$DB"
  else
    say "building the character database (~40 MB download, roughly 20 minutes)"
    ask "Download the datasets and build it now?" \
      && hanzidraw fetch-data \
      || warn "skipped. Run 'hanzidraw fetch-data' before using the app."
  fi
fi

# ------------------------------------------------------------- verify
say "verifying"
hanzidraw --version
if [ -f "$DB" ]; then
  OUT="$(mktemp -d)/check.svg"
  if hanzidraw draw 沣潘叶祥 -o "$OUT" >/dev/null 2>&1; then
    printf '    rendered a test glyph sheet: %s polylines\n' "$(grep -o '<polyline' "$OUT" | wc -l)"
  else
    warn "the test render failed; the app is installed but something is wrong with the database"
  fi
  rm -rf "$(dirname "$OUT")"
fi

cat <<'DONE'

Installed. Start the drawing window with:

    hanzidraw

Type pinyin, pick a candidate with the number keys, and the character is drawn
stroke by stroke. Ctrl+L clears, Ctrl+Z undoes, Ctrl+S saves a PNG.
Settings: ~/.config/hanzidraw/config.toml (reloads while running).
DONE
