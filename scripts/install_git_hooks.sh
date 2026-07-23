#!/usr/bin/env bash
set -euo pipefail

repository_root="$(git rev-parse --show-toplevel)"
git_directory="$(git rev-parse --absolute-git-dir)"
source_hook="${repository_root}/scripts/pre-commit.sh"
target_hook="${git_directory}/hooks/pre-commit"

if [[ -e "${target_hook}" ]] && ! grep --quiet "^# Managed by Jarvis bootstrap\\.$" "${target_hook}"; then
  echo "Refusing to replace existing pre-commit hook: ${target_hook}" >&2
  echo "Move or compose the existing hook, then run make bootstrap again." >&2
  exit 1
fi

install -m 0755 "${source_hook}" "${target_hook}"
echo "Installed Jarvis pre-commit hook."
