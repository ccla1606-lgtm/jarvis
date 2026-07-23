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
    echo "M4 demo failed; service status follows:" >&2
    "${compose[@]}" ps >&2 || true
    echo "M4 demo service logs follow:" >&2
    "${compose[@]}" logs --no-color --tail=200 >&2 || true
  fi

  teardown
  exit "${status}"
}
trap on_exit EXIT

teardown
"${compose[@]}" up --detach --build --wait

ready_payload="$(curl --fail --silent --show-error http://localhost:8000/health/ready)"
api_token="${JARVIS_API_TOKEN:-development-only-token}"
task_payload="$(
  curl --fail --silent --show-error \
    --header "Authorization: Bearer ${api_token}" \
    --header "Content-Type: application/json" \
    --header "Idempotency-Key: jarvis-disposable-demo" \
    --data '{"objective":"Verify the Jarvis M4 API"}' \
    http://localhost:8000/v1/tasks
)"
duplicate_payload="$(
  curl --fail --silent --show-error \
    --header "Authorization: Bearer ${api_token}" \
    --header "Content-Type: application/json" \
    --header "Idempotency-Key: jarvis-disposable-demo" \
    --data '{"objective":"Verify the Jarvis M4 API"}' \
    http://localhost:8000/v1/tasks
)"
web_status="$(curl --silent --output /dev/null --write-out '%{http_code}' http://localhost:3000/)"

python3 - "${ready_payload}" "${task_payload}" "${duplicate_payload}" "${web_status}" <<'PY'
import json
import sys

ready = json.loads(sys.argv[1])
task = json.loads(sys.argv[2])
duplicate = json.loads(sys.argv[3])
web_status = sys.argv[4]

assert ready["status"] == "ok", ready
assert task["task"]["status"] == "RECEIVED", task
assert task["task"]["objective"] == "Verify the Jarvis M4 API", task
assert task["task"]["id"] == duplicate["task"]["id"], (task, duplicate)
assert web_status == "200", web_status

print("M4 demo passed")
print(f"task_id={task['task']['id']}")
PY
