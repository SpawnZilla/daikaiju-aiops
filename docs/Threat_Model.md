# Daikaiju AIOps — STRIDE threat model

**Source:** `SpawnZilla/daikaiju-aiops` at commit `8179350`. **Method:** static source inspection; no deployment access, execution, external validation or proof that example policies are installed. **Rating:** High = privileged execution, identity or sensitive-data compromise plausible; Medium = significant integrity/availability impact or contingent privilege; Low = bounded impact with a clear code guard. Ratings are qualitative, not exploit confirmations.

## 1. System and trust model

This model separates implemented checks from deployment requirements. A referenced code check is not evidence that the corresponding service, hook, filter, firewall rule, SSH forced command or policy was deployed. Placeholder addresses and usernames are examples, not verified endpoints.

### Subsystems and process/data flows

Data-flow diagrams for these subsystems are in `diagrams/Mangokai_public.html`.

### Boundary register

| Boundary | Source → destination | Trust transition | Code anchor |
|---|---|---|---|
| B01 | Docker daemon/events → watchdog | Unauthenticated or untrusted Docker event metadata drives incident publication | `incident-loop/watchdog/docker_events_trigger.sh:3` |
| B02 | Watchdog/FASHSD → incident publisher | Forged incident payload or corrupted evidence enters the intake channel | `incident-loop/watchdog/kaiju_incident_publish.sh:5` |
| B03 | Incident notification transport → intake | A crafted notification passes into the incident candidate queue | `incident-loop/intake/kaiju_incident_intake.py:26` |
| B04 | Intake → vault candidate and state files | Untrusted message becomes durable JSONL and tracking state | `incident-loop/intake/kaiju_incident_intake.py:46` |
| B05 | Candidate/allowlist → orchestrator decision | Poisoned candidate or allowlist influences automatic dispatch | `incident-loop/orchestrator/kaiju_incident_orchestrator.py:66` |
| B06 | Orchestrator → gateway / Bakaidah / Mokaima | Untrusted model/tool reply becomes a remediation decision | `incident-loop/orchestrator/kaiju_incident_orchestrator.py:237` |
| B07 | Orchestrator → SSH runner | Signed ticket crosses host/network boundary to privileged runner | `incident-loop/orchestrator/kaiju_incident_orchestrator.py:404` |
| B08 | SSH stdin ticket → runner execution | Ticket input triggers allowlisted script execution | `incident-loop/watchdog/kaiju_ticket_runner.py:59` |
| B09 | Agent A2A/stdio → MCP gateway | Agent-provided arguments reach external tools | `agent-wiring/mokaima-adapter/kaiju_mokaima_a2a_adapter.py:32` |
| B10 | Bakaidah output → filter and reviewer | Model output influences draft and approval context | `bakaidah/filters/bakaidah_enforcement_gate_filter.py:15` |
| B11 | Angkai tool call → pre/post hooks | Tool call executes under agent runtime after hook decision | `angkai/hooks/pretooluse_chain.sh:1` |
| B12 | Angkai proposal → promotion broker | Agent-authored change becomes promoted files and service restart | `angkai/broker/kaiju_broker.py:156` |
| B13 | MCP/relay HTTP → vault file access | Network request reads vault content and generates edit instructions | `relay/kaiju_relay_mcp_server.py:30` |
| B14 | Operator → installer → host privileged paths | Untrusted checkout or installer input writes root-owned service configuration | `install.sh:193` |
| B15 | FASHSD config → shell health/remediation | Mutable service configuration changes remediation targets | `kaiju-gais-package/fashsd/fashsd_config_lib.sh:11` |
| B16 | GitHub Actions → published documentation | Repository content crosses CI into public hosted documentation | `.github/workflows/pages.yml:7` |
| B17 | Broker → systemctl / git / local target | Approved change reaches service management or production tree | `angkai/broker/kaiju_broker.py:341` |
| B18 | Bakaidah filter → mcpo vault HTTP | History and vault reads cross local service trust boundary | `bakaidah/filters/bakaidah_diagnostic_history_filter.py:16` |

### Security-relevant host paths

Static strings from the code (defaults; not proof that a host has them). Everything else the code touches is under `/srv/angkai`, `/srv/vault`, `/srv/kaiju-vault`, `/srv/governance` and `/opt/kaiju-spine`.

| Path | Used by | Why it matters |
|---|---|---|
| `/etc/kaiju-os/incident.key` | `incident-loop/watchdog/kaiju_incident_publish.sh`, `incident-loop/intake/kaiju_incident_intake.py` | HMAC key that signs incidents |
| `/etc/kaiju-os/runticket.key` | `incident-loop/orchestrator/kaiju_incident_orchestrator.py`, `incident-loop/watchdog/kaiju_ticket_runner.py` | HMAC key that signs run tickets |
| `/etc/kaiju-os/runner_ed25519`, `/etc/kaiju-os/runner_known_hosts` | orchestrator | SSH identity and pinned runner host key |
| `/etc/kaiju-os/known-fix-run.allow` | orchestrator, runner, `agent-wiring/mokaima-adapter/autonomy_scope_gate.py` | Exact service/script allowlist |
| `/etc/kaiju-os/known-fix-run.sha256` | runner | sha256 pins of every fix script and sourced lib |
| `/etc/kaiju-os/runner_autonomy` | runner | Runner-local autonomy switch |
| `/etc/kaiju-os/incident-services.allow` | intake | Services that may raise incidents |
| `/etc/kaiju-broker/policy.json` | `angkai/broker/kaiju_broker.py` | Promotion policy |
| `/srv/angkai/.claude/settings.json`, `/srv/angkai/.claude/hooks/` | Angkai hooks | Hook wiring and authorization state |
| `/srv/governance/Health/a2a_checkpoint_state.json` | Mokaima adapter, orchestrator, broker | Autonomy checkpoint state |
| `/etc/kaiju-spine/services.yaml` | FASHSD, `install.sh` | Watched services and repair targets |

## 2. Threat register — boundary-specific STRIDE risks

Only applicable threats are included. Code evidence identifies existing checks or the entry point; a cited check does not prove deployment or eliminate the residual risk. These are static-analysis scenarios, not demonstrated exploits.

| ID | Boundary / STRIDE threat | Code-specific attack path and existing controls | Residual risk | Recommended action |
|---|---|---|---|---|
| B01-T | **Docker event integrity** | A process with Docker socket access can create misleading container events; docker_events_trigger routes event-derived service names into watchdog handling. **Evidence:** `incident-loop/watchdog/docker_events_trigger.sh:1-65`. | **Medium** | Constrain Docker socket access; corroborate event with container state. |
| B01-D | **Event flood** | Repeated container start/stop events repeatedly trigger checks, consuming watchdog resources. **Evidence:** `incident-loop/watchdog/docker_events_trigger.sh:1-65`. | **Medium** | Debounce per container and cap concurrent triggers. |
| B02-T | **Publisher evidence poisoning** | Compromised local watchdog input can supply fabricated failure evidence before kaiju_incident_publish.sh canonicalizes and signs it; HMAC authenticates the publisher, not the observation. **Evidence:** `incident-loop/watchdog/kaiju_incident_publish.sh:60-112`. | **Medium** | Correlate signed reports with independently collected service state. |
| B02-I | **Evidence secret leakage** | Diagnostic snippets are carried in signed incidents; publisher sed redaction is pattern-based and can miss unusual secret formats. **Evidence:** `incident-loop/watchdog/kaiju_incident_publish.sh:70-80`. | **Medium** | Use structured evidence allowlists and secret canary tests. |
| B03-S | **Forged notification** | An actor with incident signing key can submit a schema-valid forged message through notification transport; intake verifies HMAC and service allowlist but cannot distinguish a stolen key. **Evidence:** `incident-loop/intake/kaiju_incident_intake.py:105-148`. | **High** | Use per-publisher keys, key rotation and independent event attestation. |
| B03-D | **Feed saturation** | High volumes of individually valid notifications can exhaust intake processing or backlog; signature checks authenticate messages but do not establish rate entitlement. **Evidence:** `incident-loop/intake/kaiju_incident_intake.py:105-148`. | **Medium** | Apply publisher quotas and bounded feed ingestion. |
| B04-T | **Candidate-state tampering** | An actor able to write candidate JSONL or tracking files can alter what orchestrator later consumes, independently of original signed transport. **Evidence:** `incident-loop/intake/kaiju_incident_intake.py:46-65; incident-loop/orchestrator/kaiju_incident_orchestrator.py:66-95`. | **High** | Restrict state file ownership and reverify provenance when consumed. |
| B05-E | **Allowlist modification** | A local writer to the remediation allowlist can expand eligible script/service combinations used for dispatch; allowlisting protects only if the file is trusted. **Evidence:** `incident-loop/orchestrator/kaiju_incident_orchestrator.py:340-395; incident-loop/watchdog/kaiju_ticket_runner.py:113-118,284-286`. | **High** | Protect allowlists with root ownership, signed versions and independent approval. |
| B05-T | **Poisoned diagnosis evidence** | Candidate text can steer Bakaidah toward an incorrect allowed fix; orchestrator checks structured selection against allowlist, not correctness of the diagnosis. **Evidence:** `incident-loop/orchestrator/kaiju_incident_orchestrator.py:340-395`. | **Medium** | Require independent health signature corroboration before dispatch. |
| B06-T | **Model response manipulation** | Prompt injection in incident evidence may cause Bakaidah to propose a wrong repair; strict parsing and allowlist narrow execution but do not prove semantic suitability. **Evidence:** `incident-loop/orchestrator/kaiju_incident_orchestrator.py:340-395`. | **Medium** | Bind choices to machine-observed failure signatures and test injected evidence. |
| B06-S | **Review response spoofing** | A compromised gateway or review service can return an apparently favorable Mokaima decision; autonomy scope and checkpoint gates constrain routes but service identity is deployment-dependent. **Evidence:** `agent-wiring/mokaima-adapter/autonomy_scope_gate.py:1-100; agent-wiring/mokaima-adapter/checkpoint_gate.py:1-100`. | **High** | Authenticate review endpoint and sign approval artifacts. |
| B07-S | **SSH endpoint impersonation** | If configured pinned known-hosts material is replaced, orchestrator may send signed tickets to an attacker endpoint. **Evidence:** `incident-loop/orchestrator/kaiju_incident_orchestrator.py:35-55; incident-loop/orchestrator/kaiju_incident_orchestrator.py:400-420`. | **High** | Protect known-hosts file and verify forced-command installation. |
| B07-D | **Dispatch availability** | SSH outage or unresponsive remote runner blocks execution; dispatch errors should remain visible rather than being treated as successful repairs. **Evidence:** `incident-loop/orchestrator/kaiju_incident_orchestrator.py:400-460`. | **Medium** | Bound SSH duration and alert on repeated dispatch failures. |
| B08-E | **Signed ticket misuse** | The runner validates HMAC, expiry, checkpoint, exact allowlist and script path; stolen signing key plus permissive checkpoint and allowlist could authorize unwanted existing fixes. **Evidence:** `incident-loop/watchdog/kaiju_ticket_runner.py:231-310`. | **High** | Separate signing authority from approval; audit key custody and revoke compromised keys. |
| B08-T | **Pin or allowlist file tampering** | The runner refuses any ticket whose script, or any sourced lib, does not match `/etc/kaiju-os/known-fix-run.sha256`, and refuses if the pin file is missing or malformed; it executes a private copy of the hashed bytes. An attacker who can write both a fix script and the pin file (or the allowlist) can still authorize changed code. **Evidence:** `incident-loop/watchdog/kaiju_ticket_runner.py:145-175`. | **Medium** | Keep pin file, allowlist and scripts root-owned and immutable; re-pin only through a reviewed change. |
| B08-R | **Replay and result attribution** | Runner returns stored results for repeated ticket IDs rather than rerunning, limiting replay execution; mutable result storage still affects audit reliability. **Evidence:** `incident-loop/watchdog/kaiju_ticket_runner.py:240-264`. | **Medium** | Protect result store and forward signed results to append-only audit. |
| B09-E | **Gateway tool authority** | Agent-origin arguments cross A2A into gateway tools; adapter scope and hard-stop checks cover selected workflows, not every independently reachable MCP tool. **Evidence:** `agent-wiring/mokaima-adapter/kaiju_mokaima_a2a_adapter.py:30-60; agent-wiring/mokaima-adapter/hard_stop_credentials_installpath_filter.py:150-205`. | **High** | Enforce authorization at every tool server and restrict gateway credentials. |
| B10-T | **Fabricated citations in model output** | Bakaidah can emit unsupported references in a draft; citation and reference filters examine text but are not a proof of source truth and may be configured as advisory. **Evidence:** `bakaidah/filters/bakaidah_citation_grounding_filter.py:1-45; bakaidah/filters/bakaidah_reference_existence_filter.py:1-45`. | **Medium** | Require source-linked evidence and reject unverifiable operational claims. |
| B10-E | **Filter bypass on failure** | A filter exception or disabled filter can leave model text available to a reviewer; enforcement gate presence does not establish all filters are active in production. **Evidence:** `bakaidah/filters/bakaidah_enforcement_gate_filter.py:1-85`. | **Medium** | Test fail-closed behavior and attest deployed filter ordering. |
| B11-E | **Unmatched tool invocation** | The PreToolUse matcher covers `Read|Write|Edit|MultiEdit|NotebookEdit|Bash|Glob|Grep|WebFetch|WebSearch|Task|mcp__.*|EnterPlanMode`, so every built-in write tool and every MCP tool runs through the chain. Residual: a tool added to the runtime later under a new name would not match until the matcher is updated. **Evidence:** `angkai/hooks/settings.example.json:15`; `angkai/hooks/pretooluse_chain.sh`. | **Low** | Re-check the matcher whenever the agent runtime adds tools; keep settings.json immutable. |
| B11-T | **Authorized command state tampering** | Command fidelity compares Bash commands to task_authorized_command.txt; arm writes matching command and state, while a writer to hook state files can change what is authorized. **Evidence:** `angkai/hooks/authorized_command_lib.py:70-165; angkai/hooks/arm_authorized_command.py:1-20; angkai/hooks/command_fidelity_pretooluse.sh:40-90`. | **High** | Make authorization state writable only by trusted controller; bind to task and session. |
| B11-D | **Hook failure and blocked workflow** | Malformed hook JSON or unavailable dependencies can interrupt agent execution; safety depends on exit semantics of the full pretooluse chain. **Evidence:** `angkai/hooks/pretooluse_chain.sh:1-110`. | **Medium** | Regression-test malformed stdin and each stage failure path. |
| B12-E | **Broker policy tampering** | A writer to broker policy, checkpoint or staging artifacts can alter promotion scope; broker validates paths and stages but trusts policy files. **Evidence:** `angkai/broker/kaiju_broker.py:310-345; angkai/broker/kaiju_broker.py:870-900`. | **High** | Protect policy and stage directories, require signed approvals. |
| B12-T | **Staging artifact swap** | An artifact may change between validation and application if staging tree is writable by an adversary; broker performs realpath checks but filesystem races remain relevant. **Evidence:** `angkai/broker/kaiju_broker.py:319-325; angkai/broker/kaiju_broker.py:540-555`. | **High** | Use immutable staging snapshots and descriptor-based operations. |
| B13-I | **Vault file disclosure** | Relay accepts a target path and reads under VAULT_ROOT; realpath containment limits traversal but any caller with endpoint access may read files inside permitted vault scope. **Evidence:** `relay/kaiju_relay_mcp_server.py:30-55`. | **Medium** | Authenticate relay callers and apply per-document authorization. |
| B13-T | **Prompt injection in relay excerpts** | Untrusted vault content enters generated edit instructions; relay_edit_brief allowlists excerpt fields but cannot establish that quoted content is safe instruction. **Evidence:** `relay/relay_edit_brief.py:20-45; relay/relay_edit_brief.py:135-160`. | **Medium** | Treat excerpts as data and revalidate proposed edits at apply time. |
| B14-E | **Privileged install input** | Running install.sh from a modified checkout grants its shell commands authority to write service files and host paths; the installer cannot defend against malicious source it executes. **Evidence:** `install.sh:190-260`. | **High** | Verify release provenance, pin artifacts and review privileged install manifest. |
| B15-T | **Mutable health config** | An attacker with write access to FASHSD configuration can redirect checks or repair targets; config parsing is not an authorization boundary against a privileged writer. **Evidence:** `kaiju-gais-package/fashsd/fashsd_config_lib.sh:1-100`. | **High** | Restrict config ownership and validate service/compose directories. |
| B15-D | **Health check instability** | Malformed or slow service probes can repeatedly consume watchdog time or produce false failure states. **Evidence:** `kaiju-gais-package/fashsd/pi5_watchdog.sh:1-100`. | **Medium** | Use bounded probe timeouts, hysteresis and per-service budgets. |
| B16-T | **Docs supply chain** | A malicious repository change to MkDocs config or dependencies is executed or published by Pages workflow; CI integrity depends on repository and workflow permissions. **Evidence:** `.github/workflows/pages.yml:1-40`. | **Medium** | Pin dependencies/actions and restrict Pages deployment permissions. |
| B17-E | **Service management reach** | Broker-approved promotion reaches production paths and service operations; compromised broker identity or policy can turn narrow approval into privileged host changes. **Evidence:** `angkai/broker/kaiju_broker.py:770-810; angkai/broker/kaiju_broker.py:1005-1030`. | **High** | Isolate broker OS identity and use narrowly scoped service privileges. |
| B17-T | **Production target race** | Broker resolves production destination paths before operations; symlink or directory swaps by a concurrent writer can invalidate earlier containment checks. **Evidence:** `angkai/broker/kaiju_broker.py:540-555; angkai/broker/kaiju_broker.py:1005-1025`. | **High** | Use immutable deployment roots and no-follow descriptor-based writes. |
| B18-I | **Diagnostic history disclosure** | History filter requests vault/MCPO content, which may contain sensitive operational details; exposure depends on service network reach and vault authorization. **Evidence:** `bakaidah/filters/bakaidah_diagnostic_history_filter.py:1-95`. | **Medium** | Scope MCPO credentials and redact history before model context. |
| B18-T | **Poisoned history** | Attacker-modified vault history can be retrieved into Bakaidah context and presented as precedent for an incorrect fix. **Evidence:** `bakaidah/filters/bakaidah_diagnostic_history_filter.py:1-95`. | **Medium** | Sign historical records and distinguish observations from instructions. |

## 3. Key, credential and secret lifecycle

Static references identify key locations and uses; the archive cannot establish actual ownership, ACLs, rotation, backup handling, or whether any secret has ever leaked.

| Material | Location / evidence | Purpose | Readers and exposure / compromise consequence |
|---|---|---|
| Incident HMAC signing key | `incident-loop/intake/kaiju_incident_intake.py:26` | Authenticate incident notifications | Publisher and intake must possess compatible key; theft permits forged signed incident messages. Verify ACLs, distribution, expiration, rotation and revocation on host. |
| Runner ticket signing key | `incident-loop/watchdog/kaiju_ticket_runner.py:25` | Authorize remediation tickets | Orchestrator and runner must access shared material; theft enables forged execution tickets subject to other gates. Verify ACLs, distribution, expiration, rotation and revocation on host. |
| SSH private key | `incident-loop/orchestrator/kaiju_incident_orchestrator.py:41` | Authenticate orchestrator to runner host | Orchestrator identity; theft permits attempts to access remote forced-command endpoint. Verify ACLs, distribution, expiration, rotation and revocation on host. |
| SSH pinned host keys | `incident-loop/orchestrator/kaiju_incident_orchestrator.py:42` | Pin runner host identity | Orchestrator; modification may redirect tickets to impostor host. Verify ACLs, distribution, expiration, rotation and revocation on host. |
| Notification transport credentials | `incident-loop/intake/kaiju_incident_intake.py:68` | Fetch incident feed | Intake process; theft enables feed access and potentially notification impersonation depending on server. Verify ACLs, distribution, expiration, rotation and revocation on host. |
| MCP/gateway credentials | `agent-wiring/mokaima-adapter/kaiju_mokaima_a2a_adapter.py:155` | Tool access | Gateway process or environment; leak can enable tool calls if gateway relies on bearer authorization. Verify ACLs, distribution, expiration, rotation and revocation on host. |
| Broker authorization state/policy | `angkai/broker/kaiju_broker.py:226` | Authorize promotion and service changes | Broker and filesystem writers; unauthorized modification can undermine approval. Verify ACLs, distribution, expiration, rotation and revocation on host. |
| Hook authorized-command state (not a cryptographic token) | `angkai/hooks/authorized_command_lib.py:70-90,110-165`; `angkai/hooks/arm_authorized_command.py:1-20` | Bind an exact command to a task and health check | Arm/disarm utilities write local authorization files; anyone able to modify those files may alter command binding. Protect file ownership and task lifecycle. |
| Hook task/session authorization markers | `angkai/hooks/command_fidelity_pretooluse.sh:40-90`; `angkai/hooks/authorized_command_lib.py:70-90` | Persist task command authorization | Local files are authorization state, not proof of cryptographic authentication. Audit permissions, reset and replay behavior. |

**Lifecycle gaps:** No archive-only evidence establishes secret generation entropy in deployed installations, rotation schedule, revocation procedure, centralized key inventory, secure backup, automatic cleanup, incident-response rotation or host-level read access. These require operator verification.

## 4. Existing controls: code vs deployment

| Control | Source anchor | Enforced in code? | Deployment dependency |
|---|---|---|---|
| Intake signed-message validation | `incident-loop/intake/kaiju_incident_intake.py:105` | Yes, when this intake is invoked | Feed credential and key distribution |
| Ticket HMAC verification | `incident-loop/watchdog/kaiju_ticket_runner.py:59` | Yes, when runner is invoked | Remote forced command, key secrecy |
| Ticket script pins | `incident-loop/watchdog/kaiju_ticket_runner.py:145` | Yes, when configured and runner executes | Pinned file ownership and immutable deployment |
| Autonomy switch | `incident-loop/watchdog/kaiju_ticket_runner.py:176` | Yes, when runner executes | Switch file ownership |
| SSH strict host-key checking | `incident-loop/orchestrator/kaiju_incident_orchestrator.py:407` | Yes, for this SSH call | Trusted known_hosts file and SSH server configuration |
| Scope gate | `agent-wiring/mokaima-adapter/autonomy_scope_gate.py:95` | Present as reference module | Installed invocation path and no alternate tools |
| Credential/install-path filter | `agent-wiring/mokaima-adapter/hard_stop_credentials_installpath_filter.py:62` | Present as reference module | Filter wiring and enforcement order |
| Hook pretool chain | `angkai/hooks/pretooluse_chain.sh:3` | Present as executable script | Runtime settings point to it and honor exit codes |
| Broker policy evaluation | `angkai/broker/kaiju_broker.py:245` | Present in broker | Policy ACL, broker service installation |
| Relay target check | `relay/kaiju_relay_mcp_server.py:30` | Yes for checked relay request | Firewall and service authentication |
| Installer sudo preflight | `install.sh:193` | Yes, when installer runs | Trusted checkout and operator privileges |

## 5. Assumptions not established by repository

The model depends on host-enforced separation: root-owned and non-agent-writable `/etc` keys, allowlists, pin manifests, systemd units and broker policies; dedicated service accounts; restricted sudoers (no general-purpose shell); SSH `authorized_keys` forced command, source restrictions and no forwarding; correct SSH host-key provisioning; trusted Docker socket permissions; safe mount ownership and symlink policies; locked-down vault and journal permissions; authenticated and network-isolated HTTP/MCP endpoints; firewall rules that survive restarts; secure notification credentials; atomic and durable audit storage; resource limits and monitoring; authenticated human checkpoint approvals; GitHub branch protection and Actions permissions; trusted dependency/package supply chain; prompt injection resilience and independently verified tool outputs. None of these should be treated as guaranteed merely because documentation or example files mention them.

## 6. Prioritized remediation

1. **P0:** Verify the runner forced-command restriction and sudoers on the actual host; root-own key, pin, allowlist and autonomy-switch files; prevent the agent and service accounts from modifying their own policy.
2. **P0:** Authenticate and authorize every HTTP/MCP/A2A hop, bind to a limited interface or require mTLS, and verify relay vault path controls against symlink and traversal risks.
3. **P0:** Ensure pretool hooks, filters and reviewer gates are mandatory on every execution path, fail closed on error and cannot be disabled by the agent.
4. **P1:** Add end-to-end replay-resistant signing with bounded expiry, nonce persistence and audit correlation across notification, candidate, ticket and execution.
5. **P1:** Apply strict service-account isolation, timeouts, queue caps, model call budgets, request size limits and bounded retries across each boundary.
6. **P1:** Centralize append-only audit with integrity checking, alert on failed verification and ensure secrets are never logged.
7. **P1:** Establish key inventory, rotation, revocation, backup encryption and compromise playbooks.
8. **P2:** Deploy negative-path integration tests in an isolated environment and separately attest installed versions, hook settings, SSH server config and host ACLs.

## 7. Limits and verification

Static analysis only. The threat register contains **34** threats across **18** boundaries; B08-T and B11-E were corrected against the code by the maintainer. File/line anchors were resolved against the extracted archive; an anchor demonstrates code presence, not an installed or effective safeguard. No penetration test, runtime observation, or independent confirmation of public commit identity was performed.
