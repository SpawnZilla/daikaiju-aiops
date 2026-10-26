╔══════════════════════════════════════════════════════════════════════╗
║  KAIJU SPINE — NAMING CONVENTION GUIDE                                 ║
║  Version: 1.1 | Created: 2026-07-22 | Public edition: 2026-10-18    ║
╚══════════════════════════════════════════════════════════════════════╝

A packaged version of the naming convention the Kaidosho reference
deployment uses internally, so someone adopting Kaiju Spine can apply a
similarly legible scheme to their own nodes, agents, and systems — or
understand why one is worth having even if they build their own instead.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHY BOTHER NAMING THINGS AT ALL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A homelab running Kaiju Spine ends up with several distinct things that
all need to be referred to constantly, in conversation with your
planning agent, in scripts, in documentation: physical machines, AI
agent roles, subsystems, drives. "The Pi5" and "the execution agent"
work fine until you have three Pis and two execution agents at
different points in your pipeline's evolution.

A consistent naming scheme does two things:
  1. Makes a complex system legible at a glance — a name signals what
     role something plays without you having to look it up.
  2. Makes documentation and conversation with your planning agent
     dramatically less ambiguous. "Restart Vakai" is unambiguous.
     "Restart the second node" invites a mistake.

You do not need to use monster-flavored names. What matters is picking
ONE consistent scheme and applying it everywhere — to nodes, to agent
roles, to major subsystems — rather than naming things ad hoc as you
build them.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE KAIDOSHO SCHEME — USE AS-IS OR AS A TEMPLATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Kaidosho names things with invented, monster-flavored names built
around a "kai" syllable, sorted into four categories:

CATEGORY 1 — NODES (physical/virtual machines)
  Dokaisho  — primary workstation (AI inference, execution agent host)
  pi-node   — services host (Docker containers, always-on)
  Vakai     — secondary/mobile access node
  Rodkai    — (planned) remote wake/relay node
  Pattern: the flagship/primary machine gets the most prominent name;
  secondary/support nodes get shorter, quieter names. This isn't
  required — just what the reference deployment happened to do — but
  the size/prominence-matching pattern is worth keeping, since it gives
  new names an intuitive slot ("this is a big important node, it should
  get a flagship-sounding name").

CATEGORY 2 — AGENT ROLES
  Mokaima   — planning/documentation agent
  Angkai    — execution agent
  Bakaidah  — reasoning/conversation agent
  Pattern: pick names whose feel loosely maps to the agent's role, if
  you want the mnemonic to actually help you remember which is which: a
  calm, careful name for the planning agent, a sharp, fast name for the
  execution agent. This is optional flavor — functionally any name
  works — but it does seem to make the roles easier to keep straight in
  conversation over time.

CATEGORY 3 — SYSTEM/SUBSYSTEM NAMES
  FASHSD — the self-healing layer (an acronym, not a monster name —
    Full Autonomous Self-Healing System Design)
  Vault  — the memory/documentation layer (a descriptive name, not
    monster-themed)
  MABS   — the governance/brief-writing standard (acronym: Mokaima
    Angkai Brief Standard — references the agent-name scheme above)
  Kaidosho — the umbrella name for the whole system; Daikaiju AIOps is
    the product underneath it
  Pattern: not every subsystem needs a themed name — acronyms that
  describe function (FASHSD, the vault) are often clearer than forcing
  a themed name onto something that isn't a node or an agent. Reserve
  themed names for nodes and agents; use descriptive names for
  subsystems and protocols.

CATEGORY 4 — STORAGE
  hola1 through hola5 — the five external drives on the services host
  vault1              — the primary documentation vault's drive
  Pattern: a simple numbered scheme for interchangeable/fungible
  storage (hola1-5, all playing the same role) rather than individual
  names — individual names are reserved for things with a distinct
  identity/role (nodes, agents), not for a pool of otherwise-identical
  drives.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAKING UP YOUR OWN NAMES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If you like the monster-flavored theme, invent your own names rather
than borrowing existing characters: it keeps the names genuinely yours
and avoids anyone else's trademarks. A simple recipe that produced the
names above:

  1. Pick a short root with the feel you want (heavy and iconic for a
     flagship node, light and quick for a relay node).
  2. Add a recurring syllable (here "kai") so every name in the system
     visibly belongs to the same family.
  3. Check that no two names in your system start with the same letter
     pair, so they stay distinguishable at a glance in logs.

Roles to name, as a checklist: a primary compute node, an always-on
services node, a secondary or mobile node, and three agent roles
(planning, execution, reasoning).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IF NOT USING THEMED NAMES: BUILD YOUR OWN SCHEME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Any consistent theme works as well as monster-flavored names
functionally. Whatever you pick, carry over the four category
distinctions above, since they're the actually load-bearing part of the
scheme:

  1. Nodes get individual, memorable names (not "node1, node2")
  2. Agent roles get names distinct from node names (so "Angkai" the
     agent is never confused with a node it happens to run on)
  3. Subsystems get descriptive acronyms, not forced theme names
  4. Fungible/interchangeable resources (drive pools, etc.) get a
     simple numbered scheme, not individual names

Other themes that work well for this purpose: mythology (Greek/Norse),
constellations, geographic features, or simply role-descriptive names
(Planner, Executor, Reasoner) if you'd rather skip theming entirely —
the mnemonic benefit is smaller without a theme, but the legibility
benefit (consistent, distinct names) still holds.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOOTSTRAP INSTALLER INTEGRATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The installer's Phase 4 prompt ("Kaiju template / custom / skip") offers
the scheme above as the "Kaiju template" option, or simply records the
user's custom scheme with a brief note pointing them to this guide's
four category distinctions as good practice, regardless of theme chosen.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
END OF NAMING CONVENTION GUIDE v1.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
