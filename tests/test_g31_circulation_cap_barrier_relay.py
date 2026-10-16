"""Pure old/new activation checks, including hash-pinned actual cap-proof rows."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import repeat_cap_barrier_relay as c
from scripts.experiments.g31_ics_circulation import repeat_quiescent_cap as q

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/original_low_wip_quiescent_prepare_001/cap8'
MANIFEST_SHA = '02fd8d2a757a26de5f2a39f58d757d7aa63df81040b8052d339d1bc657df229c'


def actual(index):
    manifest = (EVIDENCE / 'api/manifest.jsonl').read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == MANIFEST_SHA
    row = json.loads(manifest.splitlines()[index])
    data = (EVIDENCE / 'api' / row['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == row['sha256']
    result = json.loads(gzip.decompress(data))
    assert result['ordinal'] == index and result['endpoint'] == row['endpoint']
    return result


class Client:
    def __init__(self, actions=()):
        self.state = {'outbox': {r['request_id']: {'kind': 'transfer', 'terminal': True,
            'submission_reply': {'status': 'accepted'},
            'client_view': {'last_delivered_ack': deepcopy(r['last_delivered_ack'])}}
            for r in actions}}
        self.refreshed = 0
        self.submits = []
    def refresh(self, **kwargs):
        self.refreshed += 1
    def submit(self, owner, kind, payload, *, request_id):
        self.submits.append((owner, kind, deepcopy(payload), request_id))
        self.state['outbox'][request_id] = {'kind': kind, 'terminal': False,
            'payload': {**deepcopy(payload), 'owner_id': owner, 'kind': kind, 'request_id': request_id},
            'client_view': {}}
        return request_id, {'status': 'queued'}  # hypothetical new call, never actual native evidence


def owner(cls, view, peer, actions=(), cap=8):
    value = cls.__new__(cls)
    value.halt_new_actions = False; value.quiet = True; value.failure = None
    value.index = 0; value.rows = []; value.owner = view['owner_id']
    value.peer = next(o for o in ['owner:system_domestic', 'owner:system_international'] if o != value.owner)
    value.client = Client(actions); value.cap_observed = False; value.cap_barrier_relay = None
    plan = json.loads((EVIDENCE / 'preregistered_protocol.json').read_text())
    value.plan = {**plan['parking_plan'], 'supply_cap': cap}
    value.relayed = [[r['request_id'], 'received'] for r in actions if q.is_supply(r['request_id'], value.owner)]
    value.replied = []; value.repeat_publications = []; value.next_publication = view['now'] + 10
    value.publications = 1000; value.last_barrier = None; value.reads = []
    def observe(*args):
        value.reads.append(('observe_protocol_control_policy_recent', args))
        assert args == (value.owner, 120.)
        return deepcopy(view)
    def delivered(*args):
        value.reads.append(('protocol_planning_snapshots_v2', args))
        assert args == (value.owner,)
        return deepcopy(peer)
    value.session = SimpleNamespace(physical_time=view['now'],
        observe_protocol_control_policy_recent=observe, protocol_planning_snapshots_v2=delivered)
    return value


def proof_fixture(cls=c.RepeatOwner):
    view = actual(18022)['result']
    peer = actual(18023)['result']
    # This earlier native source-local body contains exactly the domestic
    # submitted-action IDs/received ACKs needed by the current source barrier.
    own_actions = actual(18026)['result'][0]['capture']['extension']['submitted_physical_actions']
    return owner(cls, view, peer, own_actions)


def test_actual_26030_proof_read_prefix_exact_then_one_new_typed_publication():
    old, new = proof_fixture(q.RepeatOwner), proof_fixture()
    old.activate(); new.activate()
    assert old.reads == new.reads and len(new.reads) == 2
    assert old.cap_observed is new.cap_observed is True
    assert old.last_barrier == new.last_barrier and new.last_barrier['known_supply_count'] == 8
    assert old.client.submits == [] and len(new.client.submits) == 1
    source, kind, payload, rid = new.client.submits[0]
    assert source == 'owner:system_domestic' and kind == 'planning_snapshot_v2'
    assert payload == {'target_owner': 'owner:system_international', 'message_delay': 2.,
                       'publication_delay': 2., 'expiry': 26150.}
    assert rid == q.base.owner_request_id(source, 'snapshot:1000')
    assert new.cap_barrier_relay['at'] == 26030.
    assert new.repeat_publications[0]['reason']['kind'] == 'terminal_cap_barrier_relay'
    assert not any(call[1] == 'transfer' for call in new.client.submits)


@pytest.mark.parametrize('later', [26040., 26150., 50000., 86400.])
def test_postcap_outage_or_expiry_never_restarts_publication_but_refreshes(later):
    new = proof_fixture(); new.activate()
    new.session.physical_time = later
    new.activate(); new.activate()
    assert new.client.refreshed == 3 and len(new.reads) == 2 and len(new.client.submits) == 1


def test_missing_received_ack_does_not_create_cap_proof():
    new = proof_fixture()
    row = next(r for r in new.client.state['outbox'].values() if r['kind'] == 'transfer')
    row['client_view']['last_delivered_ack'] = {'status': 'departed', 'delivered_at': 1.}
    row['terminal'] = False
    new.activate()
    assert not new.cap_observed and new.cap_barrier_relay is None and not new.client.submits


def test_actual_expired_peer_does_not_form_a_cap_proof():
    view, peer = actual(18019)['result'], actual(18020)['result']
    actions = actual(18023)['result'][0]['capture']['extension']['submitted_physical_actions']
    old, new = owner(q.RepeatOwner, view, peer, actions), owner(c.RepeatOwner, view, peer, actions)
    old.activate(); new.activate()
    assert old.reads == new.reads and not new.cap_observed and new.cap_barrier_relay is None
    assert old.client.submits == new.client.submits


def test_publication_budget_is_retained_and_failure_not_erased():
    new = proof_fixture(); new.repeat_publications = [{} for _ in range(q.MAX_PUBLICATIONS)]
    new.activate()
    assert new.cap_observed and new.failure['reason'] == 'unknown_publication_budget'
    assert new.cap_barrier_relay['publication_enqueued'] is False and not new.client.submits


def test_no_new_work_after_global_failure():
    new = proof_fixture(); new.halt_new_actions = True
    new.activate()
    assert new.client.refreshed == 1 and not new.reads and not new.client.submits


def actual_delivered_summary():
    submission = actual(18018)['args'][0]
    query = actual(18024)['result']
    rid = submission['request_id']
    return {'cap_observed': True, 'cap_barrier_relay': {
        'request_id': rid, 'at': 26020., 'source_owner': submission['owner_id'],
        'target_owner': submission['target_owner'], 'publication_enqueued': True},
        'outbox': {'outbox': {rid: {'kind': 'planning_snapshot_v2', 'payload': submission,
                                  'client_view': query}}}}


def test_actual_native_delivered_receipt_shape_and_historical_expiry_scope():
    summary = actual_delivered_summary()
    result = c.relay_evidence(summary)
    assert result['status'] == 'delivered_historical_cap_relay'
    assert result['captured_at'] == 26022. and result['delivered_at'] == 26024.
    assert result['new_physical_actions_authorized'] is False
    # This validates a native receipt shape only; the separate full replay must
    # prove it was the new terminal-cap publication rather than an ACK relay.


@pytest.mark.parametrize('status', [None, 'queued', 'expired', 'rejected', 'delivering'])
def test_missing_lost_or_expired_ack_does_not_certify_relay(status):
    summary = actual_delivered_summary()
    row = next(iter(summary['outbox']['outbox'].values()))
    row['client_view']['last_delivered_ack']['status'] = status
    assert c.relay_evidence(summary)['status'] == 'unknown'


@pytest.mark.parametrize('change', ['result_id', 'owner', 'target', 'expiry', 'late_delivery', 'bool_clock', 'kind'])
def test_wrong_identity_or_freshened_time_is_unknown(change):
    summary = actual_delivered_summary(); row = next(iter(summary['outbox']['outbox'].values()))
    ack = row['client_view']['last_delivered_ack']; env = ack['planning_snapshot_v2']
    local = env['capture']['local_capture']
    if change == 'result_id': ack['result_id'] = 'other'
    elif change == 'owner': local['source_owner'] = 'other'
    elif change == 'target': row['payload']['target_owner'] = 'other'
    elif change == 'expiry': row['payload']['expiry'] += 1
    elif change == 'late_delivery': env['delivered_at'] = local['valid_until']
    elif change == 'bool_clock': local['captured_at'] = True
    elif change == 'kind': env['kind'] = 'planning_snapshot'
    assert c.relay_evidence(summary)['status'] == 'unknown'


def test_rejected_submission_or_unenqueued_publication_stays_unknown():
    summary = actual_delivered_summary(); summary['cap_barrier_relay']['publication_enqueued'] = False
    assert c.relay_evidence(summary)['reason'] == 'publication_not_enqueued'


def test_scope_is_new_policy_not_relabelled_old_cap3_execution():
    value = c.scope()
    assert value['status'] == 'pure_candidate_native_unexecuted'
    assert value['physical_changes'] == 0 and value['additional_publications_per_owner_maximum'] == 1
