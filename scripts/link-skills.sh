#!/usr/bin/env bash
# Link every skill in this repo into the shared hub and each agent CLI.
#
#   repo/skills/<name>  <-  $HUB/<name>  <-  <cli>/skills/<name>
#
# The repo is the only copy; everything else is a symlink, so skills cannot
# drift between CLIs. Idempotent. Never deletes a real directory: anything
# in the way is moved to $BACKUP. Names in scripts/retired-skills.txt are
# moved out of the hub and CLI dirs the same way.
#
# Usage: scripts/link-skills.sh [--dry-run]
# Env:   SKILLS_HUB (default ~/.agents/skills)
#        SKILLS_TARGETS (space-separated CLI skill dirs; defaults below)

set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
SKILLS="$REPO/skills"
HUB="${SKILLS_HUB:-$HOME/.agents/skills}"
DEFAULT_TARGETS="$HOME/.claude/skills $HOME/.codex/skills $HOME/.config/opencode/skills $HOME/.gemini/skills $HOME/.cursor/skills"
TARGETS="${SKILLS_TARGETS:-$DEFAULT_TARGETS}"
BACKUP="$(dirname "$HUB")/skills-replaced/$(date +%Y%m%d-%H%M%S)"
RETIRED="$REPO/scripts/retired-skills.txt"

run() {
  if $DRY_RUN; then echo "  would: $*"; else "$@"; fi
}

# Move whatever occupies $1 into the backup dir, keyed by its parent dir.
stash() {
  local path="$1" tag
  tag="$(echo "$(dirname "$path")" | sed "s|^$HOME/||; s|/|_|g")"
  run mkdir -p "$BACKUP/$tag"
  run mv "$path" "$BACKUP/$tag/"
  echo "stashed  $path -> $BACKUP/$tag/"
}

# Make $1 a symlink to $2.
ensure_link() {
  local dest="$1" src="$2"
  if [[ -L "$dest" ]]; then
    local old
    old="$(readlink "$dest")"
    [[ "$old" == "$src" ]] && return 0
    case "$old" in
      "$SKILLS"/*|"$HUB"/*) run rm "$dest"; echo "relinked $dest (was -> $old)" ;;
      *) stash "$dest" ;;
    esac
  elif [[ -e "$dest" ]]; then
    stash "$dest"
  else
    echo "linked   $dest"
  fi
  run ln -s "$src" "$dest"
}

# Remove dangling symlinks that pointed into the repo or the hub.
prune() {
  local dir="$1" link target
  for link in "$dir"/*; do
    [[ -L "$link" && ! -e "$link" ]] || continue
    target="$(readlink "$link")"
    case "$target" in
      "$SKILLS"/*|"$HUB"/*) run rm "$link"; echo "pruned   $link (-> $target)" ;;
    esac
  done
}

[[ -d "$HUB" ]] || run mkdir -p "$HUB"

# Retire first, so a retired name can never be re-linked below.
if [[ -f "$RETIRED" ]]; then
  while read -r name; do
    [[ -z "$name" || "$name" == \#* ]] && continue
    [[ -e "$SKILLS/$name" ]] && { echo "error: $name is both retired and in skills/" >&2; exit 1; }
    for dir in $TARGETS "$HUB"; do
      [[ -e "$dir/$name" || -L "$dir/$name" ]] && stash "$dir/$name"
    done
  done < "$RETIRED"
fi

for skill in "$SKILLS"/*/; do
  name="$(basename "$skill")"
  [[ -f "$skill/SKILL.md" ]] || continue
  ensure_link "$HUB/$name" "$SKILLS/$name"
  for dir in $TARGETS; do
    [[ -d "$dir" ]] || continue
    ensure_link "$dir/$name" "$HUB/$name"
  done
done

prune "$HUB"
for dir in $TARGETS; do
  [[ -d "$dir" ]] && prune "$dir"
done

echo "done: $(find "$SKILLS" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ') skills linked from $SKILLS"
