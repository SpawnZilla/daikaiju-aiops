# KAI Brief Template

v1.1 — 2026-08-16. Required sections, in order. Do not
leave any blank — if a section has nothing to say, state that
explicitly with a one-line reason instead of an empty field.

1. **Title and ID**
2. **Status**
3. **Problem Statement** — one line
4. **Related:** — soft relation (informs/feeds/cites, non-blocking).
   Plain IDs, comma-separated, 2-4 max. If none: `Related: none —
   [one-line reason]`.
5. **Blocked-by:** — real blocking dependency / hard precondition.
   Plain IDs. If none: `Blocked-by: none — [one-line reason]`.
6. **Same-as:** — this item is the same deliverable as another ID
   under a different numbering system (e.g.  = , not
   two things). Plain ID. If none: `Same-as: none`.
7. **Not-related:** — OPTIONAL. Only use when an obvious-looking
   connection needs to be explicitly ruled out to prevent future
   conflation (e.g.  explicitly flagged as NOT the same scope
   as ). Omit the section entirely if there's nothing to
   flag — do not manufacture an entry.
8. **Tier:** — `doc` or `infra`, per . Doc/design tier: only
   markdown, briefs, PENDING.md, templates — low blast radius, git-
   reversible. Infra tier: anything touching Bakaidah prompts, Caddy
   config, model configs, live containers — higher blast radius.
9. **Rollback plan:** — one line, mandatory. No "N/A" for infra
   tier (per  Decision item 4) — infra-tier items must state
   a real rollback mechanism (e.g. git worktree isolation, checkpoint
   commit + reset --hard). Doc-tier may state the standard git
   checkpoint pattern in one line.
10. **Investigation / Findings**
11. **Decision / Resolution**
12. **Follow-up Items** — if any spawned; state "none" if not.

## Self-check before finalizing

- Confirm sections 1-6 and 8-12 are present and non-empty. A blank
  field without a stated reason is a fail, not a silent omission —
  flag it rather than skip it.
- For every ID referenced in Related / Blocked-by / Same-as, run the
  `existence-verification-escalation` skill to confirm the ID
  actually exists before finalizing. A referenced ID that turns out
  not to exist is worse than an empty field.
- Section 7 is optional — its absence is never a fail.
- Section 9 (Rollback plan) fails the check if it says "N/A" while
  Section 8 (Tier) says `infra` — infra-tier items must name a real
  mechanism, per  Decision item 4.
- **Current mode: WARNING LIST, not a hard gate.** Append flags at
  the bottom of the brief rather than blocking finalization. See
  `vault-sync` skill for promotion criteria to a hard gate.

## Source

This convention's edge taxonomy (Related / Blocked-by / Same-as /
Not-related) was seeded from the existing edge types already in
production use in `august2026_the operator_KAI_ANG_Dependency_Diagram.md`
(real dependency, soft relation, same-deliverable-two-IDs,
explicitly-not-related) rather than invented from scratch.
