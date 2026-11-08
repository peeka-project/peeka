#!/usr/bin/env bash
# Drive a TUI inside a real kitty window parked on a hidden Hyprland special
# workspace, without touching the user's focus, cursor, workspace or monitors.
#
# Input  : kitty remote control over a private unix socket (real kitty key encoding).
# Output : `kitty @ get-text` for text assertions, `grim -T` for pixel screenshots.
#
# Requires: Hyprland >= 0.56 (Lua config), kitty, grim >= 1.5, jq.
set -euo pipefail

RUNTIME="${XDG_RUNTIME_DIR:-/tmp}/peeka-tui-agent"
mkdir -p "$RUNTIME"

usage() {
  cat <<'USAGE'
Usage: tui-agent.sh <command> [args]

  start <name> [--size WxH] [--cwd DIR] -- <cmd...>
                          Open kitty on hidden workspace special:tui-<name>, running <cmd>
  send <name> <text>      Type literal text (no Enter appended)
  key <name> <key>...     Press keys, kitty syntax: enter tab shift+tab escape ctrl+q 2 ...
  text <name> [--ansi]    Print the current screen text
  wait <name> <regex> [timeout_s]
                          Poll screen text until regex (grep -E) matches; default 15s
  shot <name> <out.png>   Capture the window (grim -T, captured twice to avoid a stale frame)
  stop <name>             Close the window
  list                    List agent windows
  state                   Print the user's focus state (compare before/after)
USAGE
}

sock() { echo "$RUNTIME/$1.sock"; }
kc() { local n="$1"; shift; kitty @ --to "unix:$(sock "$n")" "$@"; }
client_json() { hyprctl clients -j | jq -c --arg c "tui-agent-$1" '[.[] | select(.class == $c)] | first // empty'; }

state() {
  local mon
  mon="$(hyprctl monitors -j | jq -c '[.[] | select(.focused)] | first // {}')"
  printf 'STATE monitor=%s workspace=%s special=%s window=%s cursor=%s\n' \
    "$(jq -r '.name // "none"' <<<"$mon")" \
    "$(hyprctl activeworkspace -j | jq -r '.id')" \
    "$(jq -r '.specialWorkspace.name // "" | if . == "" then "none" else . end' <<<"$mon")" \
    "$(hyprctl activewindow -j 2>/dev/null | jq -r '.address // "none"')" \
    "$(hyprctl cursorpos | tr -d ' ')"
}

cmd_start() {
  local name="$1"; shift
  local size="1600x1000" cwd="$PWD"
  while [[ $# -gt 0 && "$1" != "--" ]]; do
    case "$1" in
      --size) size="$2"; shift 2 ;;
      --cwd) cwd="$2"; shift 2 ;;
      *) echo "unknown option $1" >&2; exit 2 ;;
    esac
  done
  [[ "${1:-}" == "--" ]] && shift
  [[ $# -gt 0 ]] || { echo "start: missing command" >&2; exit 2; }

  if [[ -n "$(client_json "$name")" ]]; then
    echo "already running: $name (reuse it, or stop it first)" >&2; return 0
  fi
  local s; s="$(sock "$name")"; rm -f "$s"
  local w="${size%x*}" h="${size#*x}"

  # Build the shell command kitty will run; %q keeps arguments intact.
  local inner; printf -v inner '%q ' "$@"
  inner="${inner% }"  # a trailing escaped space would survive as a literal backslash
  local launch
  # --hold keeps the window (and the error) visible if the command exits.
  printf -v launch '[workspace special:tui-%s silent; float; size %s %s] kitty --class tui-agent-%s --title tui-agent-%s --directory %q -o allow_remote_control=socket-only -o confirm_os_window_close=0 --hold --listen-on unix:%s bash -lc %q' \
    "$name" "$w" "$h" "$name" "$name" "$cwd" "$s" "$inner"
  # Lua long-bracket string: no escaping needed as long as the text has no "]]".
  hyprctl dispatch "hl.dsp.exec_cmd([==[$launch]==])" >/dev/null

  for _ in $(seq 1 50); do
    [[ -S "$s" && -n "$(client_json "$name")" ]] && break
    sleep 0.2
  done
  [[ -S "$s" ]] || { echo "kitty socket did not appear: $s" >&2; exit 1; }
  client_json "$name" | jq -r '"started \(.class) address=\(.address) workspace=\(.workspace.name) size=\(.size|join("x"))"'
}

cmd_wait() {
  local name="$1" re="$2" timeout="${3:-15}" end
  end=$(( $(date +%s) + timeout ))
  while (( $(date +%s) < end )); do
    if kc "$name" get-text | grep -Eq -- "$re"; then echo "matched: $re"; return 0; fi
    sleep 0.3
  done
  echo "timeout waiting for: $re" >&2
  kc "$name" get-text | grep -v '^\s*$' | tail -20 >&2
  return 1
}

cmd_shot() {
  local name="$1" out="$2" id
  id="$(client_json "$name" | jq -r '.stableId // empty')"
  [[ -n "$id" ]] || { echo "no window for $name" >&2; exit 1; }
  mkdir -p "$(dirname "$out")"
  # A hidden window only commits a new frame when asked; the first capture can
  # return the previous buffer, so capture twice and keep the second.
  grim -T "$id" "$out"; sleep 0.4; grim -T "$id" "$out"
  echo "$out"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  start) cmd_start "$@" ;;
  send)  kc "$1" send-text -- "$2" ;;
  key)   n="$1"; shift; kc "$n" send-key "$@" ;;
  text)  if [[ "${2:-}" == "--ansi" ]]; then kc "$1" get-text --ansi; else kc "$1" get-text; fi ;;
  wait)  cmd_wait "$@" ;;
  shot)  cmd_shot "$@" ;;
  stop)
    # Quit the TUI first: closing the window alone leaves `docker exec -it`
    # children running inside the container, still attached to the target.
    kc "$1" send-key ctrl+q 2>/dev/null || true
    sleep "${TUI_AGENT_QUIT_WAIT:-1.5}"
    kc "$1" close-window 2>/dev/null || true
    rm -f "$(sock "$1")" ;;
  list)  hyprctl clients -j | jq -r '.[] | select(.class | startswith("tui-agent-")) | [.class, .address, .workspace.name, (.size|join("x"))] | @tsv' ;;
  state) state ;;
  -h|--help|"") usage ;;
  *) echo "unknown command: $cmd" >&2; usage >&2; exit 2 ;;
esac
