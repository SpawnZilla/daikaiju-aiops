# Tests

`bash tests/run_all.sh` runs every offline suite in the repo. CI runs it on each push and pull request (`.github/workflows/tests.yml`).

Nothing touches docker, ssh, systemd or the network: those calls are mocked, and state roots (`KAIJU_VAULT_ROOT`, `KAIJU_GOVERNANCE_ROOT`) point at temp dirs.

- `tests/test_offline_guardrails.py`: ticket runner (signature, validity window, incident, allowlist, sha256 pins, autonomy switch, replay, container health, lock), autonomy scope gate, checkpoint gate.
- `tests/test_source_validation.py`: Python and bash syntax, systemd unit parsing. Syntax only, not behavior.
- Per-component suites live next to their code (`*/tests/`).

Not covered yet: the Angkai hooks, the Bakaidah filters, and `install.sh`.
