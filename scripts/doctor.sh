#!/usr/bin/env bash
set -uo pipefail

missing=0

require_command() {
  local command_name="$1"
  local install_hint="$2"
  if command -v "${command_name}" >/dev/null 2>&1; then
    printf "ok      %-12s %s\n" "${command_name}" "$("${command_name}" --version 2>/dev/null | tail -n 1)"
  else
    printf "missing %-12s %s\n" "${command_name}" "${install_hint}"
    missing=1
  fi
}

require_command python3 "Install Python 3.12."
require_command uv "Install uv 0.11 or newer."
require_command node "Install Node.js 24 or newer."
require_command npm "Install npm with Node.js."
require_command make "Install GNU Make."
require_command curl "Install curl."
require_command docker "Install Docker Engine or Docker Desktop."

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    printf "ok      %-12s %s\n" "compose" "$(docker compose version)"
  else
    printf "missing %-12s %s\n" "compose" "Install the Docker Compose plugin."
    missing=1
  fi
fi

python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${python_version}" != "3.12" ]]; then
  printf "invalid %-12s expected Python 3.12, found %s\n" "python3" "${python_version}"
  missing=1
fi

node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || printf 0)"
if (( node_major < 24 )); then
  printf "invalid %-12s expected Node.js 24+, found major %s\n" "node" "${node_major}"
  missing=1
fi

if (( missing != 0 )); then
  printf "\nDoctor found missing or incompatible requirements.\n"
  exit 1
fi

printf "\nJarvis development requirements are ready.\n"
