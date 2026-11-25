#!/usr/bin/env bash
# run_all.sh -- run every offline test suite in the repo from a fresh checkout.
# Usage: bash tests/run_all.sh   (needs: python3 with pytest, mcp==1.28.1 and the
# packages in relay/requirements.txt and agent-wiring/mokaima-adapter/requirements.txt)
# Nothing here touches docker, ssh, systemd or the network; every external call is mocked.
set -u
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
export PYTHONDONTWRITEBYTECODE=1
fail=0
run() { local name=$1; shift; echo "=== $name"; if "$@"; then echo "--- PASS $name"; else echo "--- FAIL $name"; fail=1; fi; }

run "guardrails + source validation" "$PY" -m pytest -q -p no:cacheprovider tests/test_offline_guardrails.py tests/test_source_validation.py
run "broker v3"                       "$PY" angkai/broker/tests/test_kaiju_broker_v3.py
run "relay MCP server"                "$PY" -m pytest -q -p no:cacheprovider relay/tests/test_kaiju_relay_mcp.py
run "relay edit brief suite"          "$PY" relay/tests/test_edit_brief_suite.py
run "relay edit brief runs scoring"   "$PY" relay/tests/test_edit_brief_runs.py
run "mokaima candidate_to_brief"      "$PY" -m pytest -q -p no:cacheprovider agent-wiring/tests/test_candidate_to_brief.py
run "mokaima adapter MCP in-process"  "$PY" agent-wiring/tests/test_server_integration.py
run "mokaima adapter MCP stdio"       "$PY" agent-wiring/tests/test_stdio_subprocess.py
run "fm12 mocked (incident-loop)"     bash incident-loop/tests/test_fm12_mocked.sh
run "fm12 mocked (gais package)"      bash kaiju-gais-package/fashsd/tests/test_fm12_mocked.sh

[ "$fail" -eq 0 ] && echo "ALL SUITES PASS" || echo "SOME SUITES FAILED"
exit "$fail"
