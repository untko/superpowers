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
# This script owns the repo -> hub layer. When $SKILLS_SYNC is executable, it
# owns the hub -> CLI layer (and honors its per-CLI disable list), so this
# script only clears real directories out of its way and then runs it.
# Without it, this script links every library skill into every CLI itself.
#
# Usage: scripts/link-skills.sh [--dry-run]
# Env:   SKILLS_HUB (default ~/.agents/skills)
#        SKILLS_TARGETS (space-separated CLI skill dirs; defaults below)
#        SKILLS_SYNC (default ~/.agents/bin/sync-skills.sh)

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
SYNC="${SKILLS_SYNC:-$HOME/.agents/bin/sync-skills.sh}"

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
    if [[ -x "$SYNC" ]]; then
      # The sync script skips real directories; clear drift out of its way.
      [[ -e "$dir/$name" && ! -L "$dir/$name" ]] && stash "$dir/$name"
    else
      ensure_link "$dir/$name" "$HUB/$name"
    fi
  done
done

prune "$HUB"
if [[ -x "$SYNC" ]]; then
  echo "hub -> CLI links: $SYNC"
  if $DRY_RUN; then "$SYNC" --dry-run; else "$SYNC"; fi
else
  for dir in $TARGETS; do
    [[ -d "$dir" ]] && prune "$dir"
  done
fi

echo "done: $(find "$SKILLS" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ') skills linked from $SKILLS"
