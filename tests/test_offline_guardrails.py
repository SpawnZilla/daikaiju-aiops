"""Hermetic guardrail regression tests; no production commands are executed."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(rel):
    spec = importlib.util.spec_from_file_location('test_' + Path(rel).stem, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load('incident-loop/watchdog/kaiju_ticket_runner.py')
scope = load('agent-wiring/mokaima-adapter/autonomy_scope_gate.py')
checkpoint = load('agent-wiring/mokaima-adapter/checkpoint_gate.py')


@pytest.fixture
def ticket_case(tmp_path):
    for n in ('lib', 'state', 'incidents'):
        (tmp_path / n).mkdir()
    script = tmp_path / 'lib' / 'fix.sh'
    script.write_text('#!/bin/sh\nexit 0\n')
    script.chmod(0o700)
    (tmp_path / 'allow').write_text('fix.sh svc /srv/compose\n')
    (tmp_path / 'pins').write_text(f'{hashlib.sha256(script.read_bytes()).hexdigest()}  fix.sh\n')
    (tmp_path / 'autonomy').write_text('fully_autonomous\n')
    incident = {'status': 'open', 'capped': True, 'service': 'svc', 'first_seen': 123, 'container': 'container1'}
    (tmp_path / 'incidents' / 'svc.json').write_text(json.dumps(incident))
    iid = hashlib.sha256(b'svc|123').hexdigest()[:16]
    cfg = runner.Cfg(lib_dir=str(tmp_path / 'lib'), state_dir=str(tmp_path / 'state'),
                     incident_dir=str(tmp_path / 'incidents'), allow=str(tmp_path / 'allow'),
                     pins=str(tmp_path / 'pins'), autonomy_file=str(tmp_path / 'autonomy'),
                     log=str(tmp_path / 'log'), health_wait=0)
    base = dict(schema='kaiju-run-ticket/1', ticket_id='0123456789abcdef', incident_id=iid,
                service='svc', script='fix.sh', compose_dir='/srv/compose',
                checkpoint_state='fully_autonomous', issued_at=100, expires_at=200)
    calls = []
    deps = {'now': lambda: 150, 'run': lambda c, argv: (calls.append(argv) or (0, False)),
            'health': lambda c, s: ('200', '200'), 'container': lambda c, s: 'healthy'}
    return tmp_path, cfg, base, deps, calls


def invoke(case, changes=None, signature=True, raw=None):
    _, cfg, base, deps, calls = case
    t = dict(base, **(changes or {}))
    t = runner.sign(b'testkey', t)
    if not signature:
        t['sig'] = '0' * 64
    return runner.handle(cfg, b'testkey', raw if raw is not None else json.dumps({'op': 'run', 'ticket': t}), deps)


@pytest.mark.parametrize('raw,reason', [('{', 'bad_json'), ('[]', 'bad_request'), ('x'*8193, 'too_large'),
                                       (json.dumps({'op': 'invalid'}), 'bad_request')])
def test_request_refusal(ticket_case, raw, reason):
    assert runner.handle(ticket_case[1], b'testkey', raw, ticket_case[3]) == {'status': 'refused', 'reason': reason}
    assert ticket_case[4] == []


@pytest.mark.parametrize('changes,reason', [
    ({'script': '../escape'}, 'bad_ticket'),
    ({'compose_dir': '/srv/../escape'}, 'bad_ticket'),
    ({'ticket_id': 'nothex'}, 'bad_ticket'),
    ({'issued_at': True}, 'bad_ticket'),
    ({'checkpoint_state': 'manual'}, 'checkpoint_state'),
    ({'issued_at': 0, 'expires_at': 10000}, 'bad_ttl'),
    ({'issued_at': 300, 'expires_at': 400}, 'outside_validity_window'),
    ({'expires_at': 149}, 'outside_validity_window'),
    ({'service': 'other'}, 'not_allowlisted'),
    ({'script': 'missing.sh'}, 'not_allowlisted'),
])
def test_ticket_refusal(ticket_case, changes, reason):
    r = invoke(ticket_case, changes)
    assert (r['status'], r['reason']) == ('refused', reason)
    assert ticket_case[4] == []


def test_bad_signature(ticket_case):
    assert invoke(ticket_case, signature=False)['reason'] == 'bad_signature'
    assert not ticket_case[4]


@pytest.mark.parametrize('file,content,reason', [
    ('autonomy', 'manual\n', 'runner_autonomy_off'),
    ('allow', 'fix.sh other /srv/compose\n', 'not_allowlisted'),
    ('pins', 'invalid\n', 'pins_malformed'),
    ('pins', '', 'script_not_pinned'),
    ('pins', '0'*64 + '  fix.sh\n', 'pin_mismatch:fix.sh'),
])
def test_file_refusals(ticket_case, file, content, reason):
    (ticket_case[0] / file).write_text(content)
    assert invoke(ticket_case)['reason'] == reason
    assert not ticket_case[4]


@pytest.mark.parametrize('field,value,reason', [
    ('status', 'closed', 'incident_not_open'),
    ('capped', False, 'incident_not_capped'),
    ('first_seen', 999, 'incident_id_mismatch'),
    ('container', '../bad', 'bad_container'),
])
def test_incident_refusals(ticket_case, field, value, reason):
    p = ticket_case[0] / 'incidents' / 'svc.json'
    obj = json.loads(p.read_text()); obj[field] = value; p.write_text(json.dumps(obj))
    assert invoke(ticket_case)['reason'] == reason
    assert not ticket_case[4]


def test_missing_pins(ticket_case):
    (ticket_case[0] / 'pins').unlink()
    assert invoke(ticket_case)['reason'] == 'pins_missing'


def test_missing_autonomy(ticket_case):
    (ticket_case[0] / 'autonomy').unlink()
    assert invoke(ticket_case)['reason'] == 'runner_autonomy_off'


def test_nonexecutable_script(ticket_case):
    (ticket_case[0] / 'lib' / 'fix.sh').chmod(0o600)
    assert invoke(ticket_case)['reason'] == 'script_not_executable_in_lib_dir'


def test_success_pinned_private_copy(ticket_case):
    result = invoke(ticket_case)
    assert result['status'] == 'done' and result['passed'] is True
    assert len(ticket_case[4]) == 1
    assert ticket_case[4][0][0].endswith('.run')
    assert not Path(ticket_case[4][0][0]).exists()
    assert invoke(ticket_case) == result
    assert len(ticket_case[4]) == 1


def test_one_run_per_incident(ticket_case):
    assert invoke(ticket_case)['status'] == 'done'
    assert invoke(ticket_case, {'ticket_id': '1111111111111111'})['reason'] == 'incident_already_run'
    assert len(ticket_case[4]) == 1


@pytest.mark.parametrize('state', ['unknown', 'unhealthy', 'not_running', 'starting'])
def test_container_not_healthy(ticket_case, state):
    ticket_case[3]['container'] = lambda c, s: state
    r = invoke(ticket_case)
    assert r['status'] == 'done' and r['passed'] is False and r['container_state'] == state


def test_lock_not_obtained(ticket_case):
    ticket_case[3]['run'] = lambda c, a: (200, False)
    assert invoke(ticket_case)['reason'] == 'watchdog_lock_not_obtained'


@pytest.mark.parametrize('command,needle', [('ssh host', "contains 'ssh'"),
                                           ('docker ps', "contains 'docker'"),
                                           ('systemctl status x', "contains 'systemctl'"),
                                           ('restart service', "production-affecting keyword 'restart'")])
def test_autonomy_manual_exclusions(command, needle):
    contract = SimpleNamespace(command_type='execute', target_path='', command=command,
                               justification='', evidence_references=[])
    verdict = scope.evaluate_autonomy_scope(contract)
    assert verdict.eligible is False and verdict.category == 'out_of_scope'
    assert needle in verdict.reasons[0]


def test_autonomy_out_of_scope():
    contract = SimpleNamespace(command_type='install', target_path='', command='echo harmless',
                               justification='', evidence_references=[])
    verdict = scope.evaluate_autonomy_scope(contract)
    assert not verdict.eligible
    assert "task category 'out_of_scope' is not one of the 3" in verdict.reasons[0]


def test_known_fix_requires_exact_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr(scope, 'KNOWN_FIX_ALLOWLIST', str(tmp_path / 'allow'))
    (tmp_path / 'allow').write_text('fix.sh svc /srv/compose\n')
    contract = SimpleNamespace(command_type='known_fix_script_run', target_path='/srv/compose',
                               command='fix.sh svc /srv/compose', justification='', evidence_references=['incident:abc'])
    assert scope.evaluate_autonomy_scope(contract).eligible
    contract.command = 'fix.sh  svc /srv/compose'
    assert not scope.evaluate_autonomy_scope(contract).eligible


def test_checkpoint_failure_reason():
    assert checkpoint.should_checkpoint('draft', [], True) == (True, "Stage 'draft' errored outright -- always mandatory.")
    assert checkpoint.should_checkpoint('draft', ['bad']) == (True, "Stage 'draft' triggered 1 mechanical check warning(s): bad")
    assert checkpoint.should_checkpoint('draft', []) == (False, "Stage 'draft' clean -- auto-proceeding.")
