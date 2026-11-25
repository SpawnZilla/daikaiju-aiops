# One-page summary — Bounded Autonomy Is an Authorization Property, Not a Model Property

**Case study:** Daikaiju AIOps (`SpawnZilla/daikaiju-aiops`, commit `2e5e3f1`; test evidence `8179350`)  
**Research question:** When can an AI operations agent act without per-action human approval while remaining within defensible safety limits?

## Central claim

**Bounded autonomy can be defensible when the system—not the model—independently enforces what may be done, to which targets, on what evidence, for how long, and with what verification and revocation.** This is a conditional engineering argument, **not** proof that an AI model is reliable or a deployment is universally safe.

## Why the objection matters

The strongest opposing argument is that a model can misread evidence, be prompt-injected, hallucinate repairs, or act through compromised tools and credentials. Multiple layers may fail together; even a correct allowlisted command can be harmful in the wrong context. For unfamiliar, irreversible, or high-impact actions, human authorization remains appropriate. The paper agrees with this objection to **unrestricted** autonomy, but distinguishes it from tightly constrained routine repair.

## What Daikaiju actually provides

- **Installable substrate:** Kaiju GAIS/Kaiju Spine bootstrap, versioned memory vault, and FASHSD watchdog with fixed failure-mode handlers (`README.md`; `install.sh`; `kaiju-gais-package/fashsd/`).
- **Separate incident reference path:** watchdog → signed incident → intake → Bakaidah read-only diagnosis → structured response and exact service-specific allowlist → review/checkpoint → signed ticket → constrained runner (`incident-loop/README.md`; `incident-loop/orchestrator/kaiju_incident_orchestrator.py`; `incident-loop/watchdog/kaiju_ticket_runner.py`).
- **Agent controls:** Mokaima adapter, autonomy scope/checkpoint gates, Bakaidah grounding/reference filters, and Angkai execution hooks for command fidelity, budgets, sandbox evidence, and logging (`agent-wiring/`; `bakaidah/filters/`; `angkai/hooks/`).
- **Deployment caveat:** agent wiring and incident loop are **not included in `install.sh`**; the A2A gateway is an external upstream component (`README.md`; `agent-wiring/gateway/NOTICE.md`).

## How autonomy should be earned and revoked

Start with observation and recommendations, then supervised execution. Promote only **specific action classes** after qualifying tests and clean evidence; require the actual authorization checkpoint and allowlist to agree before autonomous release. Revoke authority on violations, drift, failed verification, or uncertain evidence. The repository has checkpoint/review mechanisms and an orchestrator hold unless `fully_autonomous`; the full ladder is a proposed safety-case framework, not a proven universal state machine (`agent-wiring/mokaima-adapter/checkpoint_gate.py`; `incident-loop/orchestrator/kaiju_incident_orchestrator.py`).

## Evidence and gaps

The archive contains FASHSD shell tests, mocked fm12 repair tests, agent-wiring tests, broker/relay tests, and Angkai guardrail regression checks (`kaiju-gais-package/fashsd/tests/`; `incident-loop/tests/`; `agent-wiring/tests/`; `angkai/tests/`). Project documentation reports disposable-infrastructure and clean-VM runs and forced-live fm12 tests (`README.md`; `docs-site/docs/status.md`). The paper's design review is static; since then all 12 offline suites run in CI and pass at commit `8179350` (`tests/run_all.sh`), with the hooks, filters and installer not yet covered. The repository does not provide a comprehensive, independently audited denominator-based field safety dataset, attack-resistance study, or proof of all deployment configurations.

## Practical implication

The right question is not “Can the model be trusted?” but **“Can every permitted effect be justified by authenticated evidence, narrow authorization, independent enforcement, and a measured ability to stop?”** The next evidence needed is an end-to-end reproducible testbed, adversarial failure injection, key-compromise and bypass tests, and longitudinal incident/rollback metrics.

**Full argument and references:** `docs/Whitepaper_Bounded_Autonomy.md`. External foundations: NIST AI RMF (https://doi.org/10.6028/NIST.AI.100-1); OWASP LLM Top 10 (https://genai.owasp.org/llm-top-10/); Parasuraman et al. (https://doi.org/10.1109/3468.844354); ReAct (https://arxiv.org/abs/2210.03629); Google SRE (https://sre.google/sre-book/automation-at-google/).
