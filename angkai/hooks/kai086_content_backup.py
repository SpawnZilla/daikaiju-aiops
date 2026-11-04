"""
kai086_content_backup.py (, 2026-09-25) -- real file-content
backup/restore, extending 's snapshot mechanism.

WHY THIS EXISTS: 's sandbox_snapshot_gate.py already computes and
stores an mtime+sha256 hash of a target BEFORE any gated call, to DETECT
whether something changed unexpectedly. It never kept the actual content,
only enough to notice drift -- it cannot restore anything. the operator asked
directly (2026-09-25) whether Daikaiju AIOps snapshots a target before
applying a fix so it can be restored if the fix goes wrong. The honest
answer at the time was no. This module is that missing piece, but SCOPED
HONESTLY -- see KNOWN LIMITS below before assuming this solves rollback
in general.

SCOPE, stated plainly: this only makes sense for FILE-CONTENT changes
(a code edit, a config edit) -- the exact shape of change 's own
dry-run promotion tested (a sed -i on a production Python file). It does
NOT apply to restart-shaped fixes (fm01 restarting a crashed container --
there is no prior "good" file state to restore, the down container IS
the problem) or toggle-shaped fixes (fm04's NTP toggle -- a real rollback
would mean toggling back, which is script-specific logic, not a generic
content restore). Do not wire this into FASHSD's fix scripts expecting
it to give them rollback; it doesn't apply to what they do.

KNOWN LIMIT: restoring a file's CONTENT does not, by itself, make a
running service pick up the reverted content. Whatever needed a restart
to apply the original change also needs a restart to apply the
rollback -- this module does not know how to restart an arbitrary
service, that's inherently domain-specific. kai086_auto_rollback_gate.py
(the caller) logs this limitation explicitly in its own alert.
"""

import hashlib
import os
import shutil

BACKUP_DIR = os.environ.get("KAI086_BACKUP_DIR", "/srv/angkai/content_backups")


def _backup_path(task_id, target):
    key = hashlib.sha256(target.encode("utf-8")).hexdigest()[:32]
    return os.path.join(BACKUP_DIR, "%s__%s.bak" % (task_id, key))


def save_backup(task_id, target):
    """Copy target's CURRENT content to a backup location, keyed by
    (task_id, target). Only meaningful for real, existing regular files --
    silently no-ops for directories or nonexistent paths (nothing to back
    up yet; the "doesn't exist" case is itself the correct pre-state for
    a file being newly created, which needs no content backup to roll
    back to -- rolling back a creation means deleting it, a distinct and
    simpler case handled by the caller checking existence, not this
    function). Overwrites any prior backup for this exact (task_id,
    target) pair -- each gated call gets a FRESH backup of the state
    immediately before IT executes, matching 's own per-call
    snapshot granularity."""
    if not os.path.isfile(target):
        return False
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dest = _backup_path(task_id, target)
    shutil.copy2(target, dest)
    return True


def has_backup(task_id, target):
    return os.path.isfile(_backup_path(task_id, target))


def restore_backup(task_id, target):
    """Restore target's content from its stored backup. Returns True on
    success, False if no backup exists (caller must not treat False as
    success -- fail loudly, never silently pretend a rollback happened)."""
    src = _backup_path(task_id, target)
    if not os.path.isfile(src):
        return False
    shutil.copy2(src, target)
    return True
