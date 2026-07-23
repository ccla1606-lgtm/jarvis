#!/usr/bin/env bash
# Managed by Jarvis bootstrap.
set -euo pipefail

repository_root="$(git rev-parse --show-toplevel)"
cd "${repository_root}"

make verify-python verify-web
