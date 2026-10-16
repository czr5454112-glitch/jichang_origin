"""One complete exact saved replay, with passive cap-proof/relay collection."""
from __future__ import annotations
from copy import deepcopy
from . import research_original_low_wip_cap_relay as r
from . import diagnose_repeat_postcap_saved as diagnostic
from .review_original_low_wip_repeat_saved import verify_case_corrected, independent_outcomes, ordered

p = r.reference


def assess_relays(raw, plan, proofs, submits, queries):
    expected = set(plan['parking_plan']['owners'])
    p.require(len(raw['owners']) == 2 and {o['owner'] for o in raw['owners']} == expected, 'cap_relay_owner_domain')
    evidence = {}
    for owner in raw['owners']:
        who = owner['owner']; relay = owner.get('cap_barrier_relay')
        historical = r.candidate.relay_evidence(owner)
        proof = proofs.get(who)
        item = {'own_historical_relay': historical, 'fresh_cap_proof': proof, 'status': 'unknown'}
        evidence[who] = item
        if not relay or not proof or historical['status'] != 'delivered_historical_cap_relay': continue
        rid = relay['request_id']; actual = submits.get(rid); actual_queries = queries.get(rid, [])
        p.require(relay['at'] == proof['at'] and relay['fresh_cap_proof'] == proof['physical_barrier']
            and relay['fresh_cap_proof']['known_supply_count'] == plan['supply_cap'], 'cap_relay_proof_binding')
        p.require(actual is not None and actual['ordinal'] == proof['after_api_ordinal'] + 1
            and actual['before'] == actual['after'] == relay['at'], 'cap_relay_actual_submit_order')
        payload = actual['args'][0]
        p.require(payload == owner['outbox']['outbox'][rid]['payload']
            and payload['owner_id'] == who and payload['target_owner'] == relay['target_owner']
            and payload['kind'] == 'planning_snapshot_v2', 'cap_relay_actual_payload')
        ack = owner['outbox']['outbox'][rid]['client_view']['last_delivered_ack']
        matches = [q for q in actual_queries if q['result'].get('last_delivered_ack') == ack]
        p.require(matches and all(q['args'] == [who, rid] and q['before'] == q['after']
            and q['before'] >= ack['delivered_at'] for q in matches), 'cap_relay_actual_ack_query')
        env = ack['planning_snapshot_v2']
        p.require(env['payload_sha256'] == p.base.capture_digest_v2(env['capture']), 'cap_relay_typed_digest')
        publications = [x for x in owner['repeat_publications'] if x['reason'].get('kind') == 'terminal_cap_barrier_relay']
        p.require(len(publications) == 1 and publications[0]['request_id'] == rid, 'cap_relay_once')
        item.update(status='actual_fresh_cap_proof_and_delivered_own_relay',
            submit_api_ordinal=actual['ordinal'], actual_ack_query_ordinals=[q['ordinal'] for q in matches],
            request_id=rid, payload_sha256=env['payload_sha256'])
    assessment = p.assess(raw, plan)
    complete = (assessment['status'] == 'complete_finite_policy_evidence'
        and assessment['actual_supplies'] == 8 and len(assessment['completion_witnesses']) == 8
        and raw['physical_time'] == 86400. and raw['physical_audit']['status'] == 'passed'
        and set(proofs) == expected and all(v['status'] == 'actual_fresh_cap_proof_and_delivered_own_relay' for v in evidence.values()))
    return {'status': 'complete_cap8_with_bidirectional_cap_relay' if complete else 'unknown_or_incomplete_cap_relay',
        'owner_proofs': evidence, 'physical_assessment': assessment, 'new_same_policy_cap3_pair': False,
        'strict_protection': 'unknown_unfinished_offered_jobs', 'complete_100ms_certified': False}


def verify_case(directory):
    plan = p.base.read(directory / 'preregistered_protocol.json')
    raw = p.base.gzread(directory / 'raw_final.json.gz')
    counter = diagnostic.ProofCounter(8, plan['parking_plan']['token_tray_id'])
    relay_ids = {o['cap_barrier_relay']['request_id'] for o in raw['owners'] if o.get('cap_barrier_relay')}
    submits, queries = {}, {}
    old_tape = p.base.ReplayTape; old_barrier = p.physical_barrier
    old_q_barrier = r.candidate.reference.physical_barrier
    class ObservedTape(old_tape):
        def __getattr__(self, name):
            method = super().__getattr__(name)
            def call(*args, **kwargs):
                at, ordinal = self.physical_time, self.index
                value = method(*args, **kwargs)
                if name in {'observe_protocol_control_policy_recent', 'protocol_planning_snapshots_v2'}:
                    counter.read(name, args[0], at, ordinal, value)
                if name == 'submit_protocol_command' and args[0]['request_id'] in relay_ids:
                    row = {'ordinal': ordinal, 'before': at, 'after': self.physical_time,
                        'args': p.base.canonical(args), 'result': deepcopy(value)}
                    rid = args[0]['request_id']
                    if rid in submits: p.require(submits[rid]['args'] == row['args'], 'cap_relay_mutable_retry')
                    else: submits[rid] = row
                if name == 'protocol_command' and args[1] in relay_ids:
                    queries.setdefault(args[1], []).append({'ordinal': ordinal, 'before': at,
                        'after': self.physical_time, 'args': list(args), 'result': deepcopy(value)})
                return value
            return call
    def barrier(outbox, owner, peer, parking):
        result = old_barrier(outbox, owner, peer, parking)
        counter.barrier(owner, result)
        return result
    try:
        p.base.ReplayTape = ObservedTape; p.physical_barrier = barrier
        r.candidate.reference.physical_barrier = barrier
        with r.installed():
            result = verify_case_corrected(directory)
            data = p.base.gzread(directory / 'input.json.gz')
            outcomes = independent_outcomes(data, raw, plan)
            result['cap_relay_assessment'] = assess_relays(raw, plan, counter.summary(), submits, queries)
    finally:
        p.base.ReplayTape = old_tape; p.physical_barrier = old_barrier
        r.candidate.reference.physical_barrier = old_q_barrier
    result['independent_outcomes'] = outcomes
    result['variant_verifier_sha256'] = p.base.sha(__file__)
    result['full_saved_api_replays'] = 1
    result['prior_cap3_is_historical_reference_only'] = True
    states = directory / 'all_job_states.json.gz'
    p.require(not states.exists(), 'cap_relay_all_job_export_exists')
    p.base.gzwrite(states, {'offered': 28506, 'horizon': raw['physical_time'], 'jobs': raw['result']['jobs']})
    result['all_job_states'] = {'path': str(states), 'sha256': p.base.sha(states),
        'job_count': len(raw['result']['jobs']), 'status_counts': outcomes['status_counts']}
    result['evidence_sha256'][str(states)] = p.base.sha(states)
    with r.installed(): p.verify_pins(directory, plan)
    return result
