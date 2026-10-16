"""Pure authority checks; mutated signed bodies below are hypothetical fixtures."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import pytest
from scripts.experiments.g31_ics_circulation import current_empty_possession_permit as c


@lru_cache(maxsize=1)
def saved():
    path = c.base.OUT / 'original_low_wip_third_prepare_001'
    plan = c.base.read(path / 'preregistered_protocol.json')
    assert c.base.sha(path / 'preregistered_protocol.json') == '2d40bea147cbe63efbeb1bc54d6383ee8a6a8fb3316d07d67da698302a56b1c8'
    assert c.base.sha(path / 'raw_final.json.gz') == '9dfa90fe96d10b3efa6262cd6ba3716d41179e4afda0aedcec123a35601f8eeb'
    data, raw = c.base.gzread(path / 'input.json.gz'), c.base.gzread(path / 'raw_final.json.gz')
    assert c.base.sha(path / 'input.json.gz') == plan['input_sha256']
    return data, raw, plan


def fixture():
    data, raw, plan = saved()
    source = next(o for o in raw['owners'] if o.get('third_supply'))
    selected = source['third_supply']; proof = selected['return_proof']
    owner = source['owner']; parking = deepcopy(plan['parking_plan'])
    view = {**{k: deepcopy(data[k]) for k in ('node_records', 'edge_records', 'node_contracts', 'edge_contracts')},
            'owner_id': owner, 'now': selected['at'], 'trays': [deepcopy(proof['current_token'])]}
    box = {rid: deepcopy(row) for rid, row in source['outbox']['outbox'].items()
           if row['kind'] == 'transfer' and rid != selected['request_id']}
    own = proof['own_delivered_self_copy']; rid = own['request_id']
    box[rid] = deepcopy(source['outbox']['outbox'][rid])
    box[rid]['client_view']['last_delivered_ack'] = deepcopy(own['ack'])
    peer = deepcopy(selected['choice']['delivered_message'])
    gate = c.PossessionGate(owner, parking, [p['request_id'] for p in parking['parking']])
    return gate, view, box, peer


def resign_hypothetical(envelope):
    body = envelope['capture']; actions = body['extension']['submitted_physical_actions']
    coverage = body['extension']['action_coverage']
    coverage['submitted_request_ids'] = [a['request_id'] for a in actions]
    coverage['unresolved_request_ids'] = [a['request_id'] for a in actions if not c.base.action_resolved(a)]
    envelope['payload_sha256'] = c.base.capture_digest_v2(body)


def test_real_saved_facts_support_current_possession_not_arrival_causality():
    gate, view, box, peer = fixture()
    permit = gate.consume(view, box, [peer])
    assert permit['status'] == 'conditional_cooperative_current_possession_permit'
    assert len(permit['previous_action_ids']) == 22 and len(permit['consumed_action_ids']) == 24
    assert len(permit['new_action_ids']) == 2
    assert permit['native_revalidation_required'] and not permit['operation_submitted']
    assert not permit['remote_payload_or_arrival_causality_certified']
    assert gate.consume(view, box, [peer]) is None
    restored = c.PossessionGate(gate.owner, gate.plan, gate.checkpoint()['consumed_action_ids'])
    assert restored.consume(view, box, [peer]) is None


@pytest.mark.parametrize('defect', ['loaded', 'holding', 'future_available', 'edge', 'reception', 'moved', 'generation', 'traversal', 'foreign_owner'])
def test_live_local_token_and_selfcopy_must_both_match(defect):
    gate, view, box, peer = fixture(); tray = view['trays'][0]
    if defect == 'loaded': tray['business_bag_id'] = 'uncompleted'
    elif defect == 'holding': tray['mode'] = 'holding'
    elif defect == 'future_available': tray['available_at'] = view['now'] + 1
    elif defect == 'edge': tray['edge_to'] = 3
    elif defect == 'reception': tray['reception_node'] = 3
    elif defect == 'moved': tray['node'] = 57
    elif defect == 'generation': tray['generation'] += 1
    elif defect == 'traversal': tray['traversal_id'] += 1
    else: view['owner_id'] = gate.peer
    if defect == 'foreign_owner':
        with pytest.raises(ValueError): gate.consume(view, box, [peer])
    else:
        assert gate.consume(view, box, [peer]) is None


@pytest.mark.parametrize('defect', ['pending', 'rejected', 'nontoken', 'new_unpublished', 'expired_self', 'expired_peer', 'missing_parking', 'peer_pending', 'unknown_kind'])
def test_complete_delivered_action_barrier_and_own_payload(defect):
    gate, view, box, peer = fixture()
    rid = next(k for k, r in box.items() if r['kind'] == 'transfer' and k not in gate.parking)
    row = box[rid]
    if defect == 'pending': row['terminal'] = False
    elif defect == 'rejected': row['submission_reply']['status'] = 'rejected'
    elif defect == 'nontoken': row['payload']['tray_id'] = 'another_parked_tray'
    elif defect == 'new_unpublished':
        box['new-own-id'] = deepcopy(row); box['new-own-id']['payload']['request_id'] = 'new-own-id'
    elif defect == 'expired_self':
        next(r for r in box.values() if r['kind'] == 'planning_snapshot_v2')['client_view']['last_delivered_ack']['planning_snapshot_v2']['status'] = 'expired'
    elif defect == 'expired_peer': peer['status'] = 'expired'
    else:
        actions = peer['capture']['extension']['submitted_physical_actions']
        if defect == 'missing_parking': actions.pop(0)
        elif defect == 'peer_pending': actions[0]['last_delivered_ack'] = None
        else: actions[0]['kind'] = 'route'
        resign_hypothetical(peer)
    if defect in ('nontoken', 'unknown_kind'):
        with pytest.raises(ValueError): gate.consume(view, box, [peer])
    else:
        assert gate.consume(view, box, [peer]) is None


def test_exact_set_not_count_and_no_ack_revision_reopens_consumption():
    gate, view, box, peer = fixture()
    permit = gate.consume(view, box, [peer]); ids = permit['consumed_action_ids']
    removed = next(identity for identity in ids if identity not in gate.parking)
    wrong = [identity for identity in ids if identity != removed] + ['unrelated_action_identity']
    other = c.PossessionGate(gate.owner, gate.plan, wrong)
    assert other.consume(view, box, [peer]) is None
    action = peer['capture']['extension']['submitted_physical_actions'][0]
    action['last_delivered_ack']['sequence'] += 1
    resign_hypothetical(peer)
    assert gate.consume(view, box, [peer]) is None


def test_emitted_evidence_and_checkpoint_cannot_mutate_gate():
    gate, view, box, peer = fixture(); permit = gate.consume(view, box, [peer])
    permit['consumed_action_ids'].clear(); gate.checkpoint()['consumed_action_ids'].clear()
    assert len(gate.consumed) == 24 and gate.consume(view, box, [peer]) is None


@pytest.mark.parametrize('bad', [None, [], ['duplicate', 'duplicate']])
def test_missing_or_corrupt_consumed_state_does_not_restore(bad):
    gate, _, _, _ = fixture()
    with pytest.raises((ValueError, TypeError)): c.PossessionGate(gate.owner, gate.plan, bad)
