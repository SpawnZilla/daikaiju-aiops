"""
checkpoint_gate.py -- gating decision logic for human checkpoints.
Written 2026-07-31 (dosho lan, Daikaiju AIOps 1.3), drafted and tested
during the preceding dosho wan window.

Core decision logic for "should this stage's completion trigger a
mandatory human checkpoint, or auto-proceed?" -- see
checkpoint_gate_design.md in this same folder for the full design and
reasoning. This file is just the one piece worth testing in isolation:
the gate itself.

INTENTIONALLY REUSES the existing check functions built this session
(update_preservation_check, brief_id_check) as inputs rather than
building a parallel warning system -- checkpoint frequency should
correlate with what the ALREADY-BUILT mechanical checks find, not a
new, separate notion of risk.

STATUS: gate logic tested (5 cases, see __main__). NOT YET wired into
model_relay.py's actual Stage A/B call sites -- see
checkpoint_gate_design.md Section 7 for the remaining integration work.

DEPLOYED 2026-08-27 (Daikaiju AIOps/ part 7 continuation
3) as a sibling-module dependency of kaiju_mokaima_a2a_adapter.py -- this
is an exact copy of the authoritative kaiju-relay/checkpoint_gate.py,
not a divergent trimmed stub.
"""


def should_checkpoint(stage_name, check_warnings, stage_errored=False):
    """
    stage_name: str, e.g. "verify", "draft"
    check_warnings: list of warning strings from any mechanical check
        that ran against this stage's output (uncertainty_preservation_
        check, mechanical_postcheck, brief_id_check, etc. -- caller is
        responsible for running the relevant checks and passing in
        whatever came back, combined).
    stage_errored: True if the stage itself failed outright (schema
        violation, fetch failure, model unreachable, etc.) -- always
        forces a mandatory checkpoint regardless of check_warnings.

    Returns: (is_mandatory: bool, reason: str)
    """
    if stage_errored:
        return True, f"Stage '{stage_name}' errored outright -- always mandatory."

    if check_warnings:
        warning_summary = "; ".join(check_warnings[:3])
        if len(check_warnings) > 3:
            warning_summary += f" (+{len(check_warnings) - 3} more)"
        return True, (
            f"Stage '{stage_name}' triggered {len(check_warnings)} "
            f"mechanical check warning(s): {warning_summary}"
        )

    return False, f"Stage '{stage_name}' clean -- auto-proceeding."


if __name__ == "__main__":
    # TEST 1: clean stage, no warnings -> auto-proceed
    mandatory, reason = should_checkpoint("verify", [])
    print("TEST 1 (clean stage):", mandatory, "-", reason)
    assert mandatory is False
    print("  -> PASS\n")

    # TEST 2: stage with real warnings (using this session's actual
    # warning text shapes) -> mandatory
    real_warnings = [
        "UNCERTAINTY MAY NOT BE PRESERVED: Stage A marked 'health_endpoint' as unconfirmed.",
    ]
    mandatory2, reason2 = should_checkpoint("draft", real_warnings)
    print("TEST 2 (real uncertainty-preservation warning):", mandatory2, "-", reason2)
    assert mandatory2 is True
    print("  -> PASS\n")

    # TEST 3: stage errored outright, even with NO warnings passed in
    # (e.g. schema forcing failed before any check could even run) ->
    # still mandatory
    mandatory3, reason3 = should_checkpoint("draft", [], stage_errored=True)
    print("TEST 3 (stage errored, no warnings possible):", mandatory3, "-", reason3)
    assert mandatory3 is True
    print("  -> PASS\n")

    # TEST 4: many warnings -> summary truncates sanely, doesn't just dump everything
    many_warnings = [f"warning {i}" for i in range(7)]
    mandatory4, reason4 = should_checkpoint("draft", many_warnings)
    print("TEST 4 (7 warnings, truncation check):", mandatory4, "-", reason4)
    assert "+4 more" in reason4
    print("  -> PASS\n")

    # TEST 5: brief_id_check-style single collision warning routes through correctly
    from_brief_id_check = [
        "BRIEF ID COLLISION: '' is already in use. Suggested next free ID:."
    ]
    mandatory5, reason5 = should_checkpoint("draft", from_brief_id_check)
    print("TEST 5 (brief-ID collision warning):", mandatory5, "-", reason5)
    assert mandatory5 is True
    print("  -> PASS\n")

    print("ALL TESTS PASS")
