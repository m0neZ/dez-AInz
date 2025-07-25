#!/usr/bin/env bash
# Run Locust load tests with strict settings and GPU performance tests.

set -euo pipefail

command -v locust >/dev/null 2>&1 || {
  echo "locust is required" >&2
  exit 1
}

command -v k6 >/dev/null 2>&1 || {
  echo "k6 is required" >&2
  exit 1
}

locust -f load_tests/locustfile.py \
  --headless \
  -u "${USERS:-10}" \
  -r "${SPAWN_RATE:-5}" \
  --run-time "${RUN_TIME:-1m}"

# Run the k6 script against the API gateway
k6 run \
  --env RESULTS_PATH="${K6_RESULTS:-load_tests/k6_results.json}" \
  load_tests/k6_api_gateway.js

pytest -W error backend/mockup-generation/tests/test_performance.py::test_concurrent_generation_gpu_utilization "$@"
