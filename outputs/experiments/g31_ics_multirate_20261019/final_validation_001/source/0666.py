"""Saved-only exact replay and finite cap3/cap8 comparison; no NativeSession."""
from copy import deepcopy
import json
import math
from pathlib import Path
from . import research_original_low_wip_repeat as p


def semantic(row):
    row = deepcopy(row)
    if row['endpoint'] == 'advance_to':
        value = row['result'].pop('wall_seconds')
        p.require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'invalid_api_diagnostic')
    return json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def manifest(directory):
    rows = [json.loads(s) for s in (directory/'api/manifest.jsonl').read_text(encoding='utf8').splitlines()]
    p.require(len(list((directory/'api').glob('*.json.gz'))) == len(rows), 'tape_files_omitted')
    for i, row in enumerate(rows):
        p.require(row['path'] == f'{i:06d}.json.gz' and p.base.sha(directory/'api'/row['path']) == row['sha256'], 'tape_manifest')
    return rows


def prefix(left, right, through):
    a, b = manifest(left), manifest(right); compared = 0
    for x, y in zip(a, b):
        x = p.base.gzread(left/'api'/x['path']); y = p.base.gzread(right/'api'/y['path'])
        p.require(semantic(x) == semantic(y), 'ordered_prefix_difference')
        compared += 1
        if x['endpoint'] == 'advance_to' and x['after'] >= through:
            return {'compared_api_rows': compared, 'through_physical_time': x['after'], 'requested_through': through,
                'only_excluded': 'advance_to.result.wall_seconds; finite nonnegative numeric'}
    raise ValueError('repeat:missing_complete_prefix_boundary')


def bootstrap_replay(cap):
    """Pure actual005 tape replay to the first supply's next complete boundary."""
    p.require(cap in p.CAPS.values(), 'bootstrap_cap')
    old = p.OUT/'original_low_wip_prepare_005'
    plan = p.base.read(old/'preregistered_protocol.json'); raw = p.base.gzread(old/'raw_final.json.gz')
    first = next(o['supply'] for o in raw['owners'] if o['supply'])
    tape = p.base.ReplayTape(old/'api'); local = {**plan['parking_plan'], 'supply_cap': cap}
    owners = [p.RepeatOwner(tape, owner, local) for owner in local['owners']]
    for _ in range(p.MAX_TICKS):
        for owner in owners: owner.activate()
        response = tape.advance_to(tape.physical_time+p.base.PERIOD, max_events=100000)
        p.require(response['status'] == 'reached' and response['horizon_complete'] is True, 'bootstrap_boundary')
        if tape.physical_time >= first['at']+p.base.PERIOD: break
    selected = [o.supply for o in owners if o.supply]
    p.require(selected == [first] and all(not o.repeated for o in owners), 'bootstrap_first_supply')
    return {'status':'passed_actual_saved_bootstrap_prefix','cap':cap,'api_rows':tape.index,
        'through':tape.physical_time,'old_manifest_sha256':p.base.sha(old/'api/manifest.jsonl'),
        'new_source_sha256':p.base.sha(p.__file__),'native_executions':0}


def verify_case(directory):
    plan = p.base.read(directory/'preregistered_protocol.json'); p.verify_pins(directory, plan)
    with p.installed(): replay = p.base.verify_saved(directory)
    data = p.base.gzread(directory/'input.json.gz'); raw = p.base.gzread(directory/'raw_final.json.gz')
    source_ids = [j['business_bag_id'] for j in data['jobs']]; actual_ids = [j['business_bag_id'] for j in raw['result']['jobs']]
    p.require(len(source_ids) == len(set(source_ids)) == len(actual_ids) == len(set(actual_ids)) == 28506
        and set(source_ids) == set(actual_ids), 'all_offered_ids')
    p.require(len(raw['result']['trays']) == 22 and {t['tray_id'] for t in raw['result']['trays']} == {t['tray_id'] for t in data['trays']}, 'all_trays')
    selected = p.supplies(raw); token = plan['parking_plan']['token_tray_id']; parks = {r['request_id'] for r in plan['parking_plan']['parking']}
    p.require(len(selected) <= plan['supply_cap'], 'supply_cap')
    for owner in raw['owners']:
        p.require(len(owner['repeat_publications']) <= p.MAX_PUBLICATIONS and len(owner['consumed']) == len(set(owner['consumed'])) == len(owner['repeated']), 'permit_publication_denominator')
        for row in owner['calls']:
            cost = row['submit_compute_ms']
            p.require(type(cost) in (int, float) and math.isfinite(cost) and cost >= 0, 'invalid_submit_clock')
            if row['kind'] == 'transfer' and row['request_id'] not in parks:
                p.require(row['request']['tray_id'] == token, 'parked_tray_reused')
    p.require(len(raw['native_state_sha256']) == 64 and all(c in '0123456789abcdef' for c in raw['native_state_sha256']), 'native_seal')
    # The old prototype is used only as an immutable startup comparison.
    old = Path(plan['bootstrap_reference'])
    old_raw = p.base.gzread(old/'raw_final.json.gz'); first = next(o['supply'] for o in old_raw['owners'] if o['supply'])
    if selected:
        p.require(selected[0] == first, 'first_supply_difference')
        startup = prefix(old, directory, first['at']+p.base.PERIOD)
    else:
        startup = {'status': 'unknown_bootstrap_incomplete', 'compared_api_rows': 0}
    return {'schema': p.SCHEMA, 'status': 'passed_saved_policy_replay', 'replay': replay,
        'startup_exact': startup, 'all_offered': 28506, 'trays': 22,
        'assessment': p.assess(raw, plan), 'producer_native_seal': raw['native_state_sha256'],
        'evidence_sha256': {str(directory/n): p.base.sha(directory/n) for n in ('preregistered_protocol.json','input.json.gz','raw_final.json.gz','assessment.json','api/manifest.jsonl')},
        'reviewer_source_sha256': p.base.sha(__file__), 'native_executions': 0,
        'strict_protection': 'not_assessed', 'complete_100ms_certified': False}


def compare(output):
    p.verify_campaign(output)
    evidence = {name: p.base.read(output/name/'independent_verification.json') for name in p.CAPS}
    raw = {name: p.base.gzread(output/name/'raw_final.json.gz') for name in p.CAPS}
    for name in p.CAPS:
        p.require(evidence[name]['status'] == 'passed_saved_policy_replay', 'case_not_verified')
        for path, digest in evidence[name]['evidence_sha256'].items(): p.require(p.base.sha(path) == digest, 'case_evidence_changed')
    assessments = {name: evidence[name]['assessment'] for name in p.CAPS}
    thirds = [a['completion_witnesses'][2]['hold_complete']['time'] if len(a['completion_witnesses']) >= 3 else None for a in assessments.values()]
    if all(t is not None for t in thirds):
        p.require(thirds[0] == thirds[1], 'third_completion_time_changed')
        same_prefix = prefix(output/'cap3', output/'cap8', thirds[0])
    else:
        through = min(r['physical_time'] for r in raw.values())
        same_prefix = prefix(output/'cap3', output/'cap8', through) if through > 0 else {'status': 'unknown_no_complete_boundary'}
    closed = all(a['status'] == 'complete_finite_policy_evidence' for a in assessments.values())
    counts = {name: len(a['completion_witnesses']) for name, a in assessments.items()}
    return {'schema': p.SCHEMA, 'status': 'assessed_finite_pair' if closed else 'unknown_incomplete_policy_pair',
        'cases': assessments, 'completion_counts': counts, 'extra_observed_completions': counts['cap8']-counts['cap3'] if closed else None,
        'exact_common_prefix': same_prefix, 'all_offered_each': 28506,
        'strict_protection': 'unknown_unfinished_offered_jobs', 'complete_100ms_certified': False,
        'scope': 'Completion-count comparison only. Unfinished jobs have no protected completion vector; no deadline/throughput optimality or39 bound achievability claim.'}
