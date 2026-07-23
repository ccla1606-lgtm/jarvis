#!/usr/bin/env bash
set -euo pipefail

project_name="${COMPOSE_PROJECT_NAME:-jarvis-demo}"
export POSTGRES_PORT="${POSTGRES_PORT:-55432}"
compose=(docker compose --project-name "${project_name}")

teardown() {
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}

on_exit() {
  status="$?"
  trap - EXIT

  if ((status != 0)); then
    echo "M0 demo failed; service status follows:" >&2
    "${compose[@]}" ps >&2 || true
    echo "M0 demo service logs follow:" >&2
    "${compose[@]}" logs --no-color --tail=200 >&2 || true
  fi

  teardown
  exit "${status}"
}
trap on_exit EXIT

teardown
"${compose[@]}" up --detach --build --wait

ready_payload="$(curl --fail --silent --show-error http://localhost:8000/health/ready)"
demo_payload="$(
  curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data '{"message":"Jarvis M0 demo"}' \
    http://localhost:8000/v1/demo
)"
web_status="$(curl --silent --output /dev/null --write-out '%{http_code}' http://localhost:3000/)"

python3 - "${ready_payload}" "${demo_payload}" "${web_status}" <<'PY'
import json
import sys

ready = json.loads(sys.argv[1])
demo = json.loads(sys.argv[2])
web_status = sys.argv[3]

assert ready["status"] == "ok", ready
assert demo["status"] == "accepted", demo
assert demo["route"] == "m0_scaffold", demo
assert demo["message"] == "Jarvis M0 demo", demo
assert web_status == "200", web_status

print("M0 demo passed")
print(f"task_id={demo['task_id']}")
PY
