"""Offline shadow search on captured public query arguments, never execution.

The four fixed variants keep the request's horizon, K and validator. Expanded
regional search changes only its work cap. The full-graph event reference is
bounded and does not certify all K routes or downstream objective optimality.
"""
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from time import process_time, perf_counter

from .routing import RegionalCandidateGenerator, _TOPOLOGY_CACHE
from .routing_reference import FullGraphReferenceGenerator
from .runtime import ExecutionValidator, actual_action_key


VARIANTS = (('regional3000', 'regional', 3000), ('regional12000', 'regional', 12000),
            ('regional48000', 'regional', 48000), ('fullgraph_event48000', 'fullgraph_event', 48000))


def public_sha(snapshot):
    return sha256(json.dumps(asdict(snapshot), sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def query_summary(query):
    state = query['snapshot']; bag = state.bags.get(query['bag_id'])
    return {k: query[k] for k in ('query_ordinal', 'time', 'version', 'callsite',
        'method', 'bag_id', 'tray_id', 'destination', 'requested_k', 'last_search_status',
        'last_expansions', 'raw_candidate_count', 'public_snapshot_sha256')} | {
        'source': state.trays[query['tray_id']].node,
        'protected': bool(bag and bag.protected),
        'role': None if bag is None else 'destination' if state.trays[query['tray_id']].node==bag.destination
            else 'origin' if state.trays[query['tray_id']].node==bag.origin else 'continuation'}


def coverage_cell(row):
    return tuple(row[key] for key in ('scene', 'callsite', 'source', 'destination', 'requested_k', 'protected'))


def select_requests(rows):
    """All truncated queries plus one earliest successful control per cell."""
    failures = [r for r in rows if r['last_search_status']=='expansion_budget_exhausted']
    successes = defaultdict(list)
    for row in rows:
        if row['last_search_status']=='candidate_limit_reached' and row['raw_candidate_count']>0:
            successes[coverage_cell(row)].append(row)
    order = lambda r: (r['case_id'], r['time'], r['query_ordinal'])
    chosen = {r['query_id']: {**r, 'selection':'all_truncated'} for r in failures}
    controls = []
    for cell in sorted({coverage_cell(r) for r in failures}):
        candidates = successes[cell]
        control = min(candidates, key=order) if candidates else None
        controls.append({'cell':cell,'control_query_id':None if control is None else control['query_id'],
                         'available_successful_queries':len(candidates)})
        if control is not None:
            chosen.setdefault(control['query_id'], {**control,'selection':'earliest_successful_control'})
    formal = sorted(chosen.values(), key=order)
    pilot_ids = set()
    for scene in sorted({r['scene'] for r in failures}):
        first = min((r for r in failures if r['scene']==scene), key=order)
        pilot_ids.add(first['query_id'])
        control = next(c for c in controls if tuple(c['cell'])==coverage_cell(first))
        if control['control_query_id'] is not None:
            pilot_ids.add(control['control_query_id'])
    return {'formal':formal, 'pilot':[r for r in formal if r['query_id'] in pilot_ids],
            'controls':controls,'truncated_count':len(failures),
            'missing_control_cells':sum(c['control_query_id'] is None for c in controls),
            'selection_note':'No cost/value fields used. Pilot is first truncated query per scene plus its control; formal repeats pilot identities independently.'}


@contextmanager
def cold_fullgraph_cache():
    """Dedicated-worker only: isolate legacy reference cache without code edits."""
    previous = deepcopy(_TOPOLOGY_CACHE)
    _TOPOLOGY_CACHE.clear()
    try:
        yield
    finally:
        _TOPOLOGY_CACHE.clear()
        _TOPOLOGY_CACHE.update(previous)


def _generate(generator, state, query):
    if query['method']=='generate':
        return generator.generate(state, query['bag_id'], query['tray_id'], k=query['requested_k'])
    if query['method']=='generate_empty':
        return generator.generate_empty(state, query['tray_id'], query['destination'], k=query['requested_k'])
    raise ValueError('unknown captured method')


def shadow_variant(query, variant):
    name, family, expansion = variant
    started, cpu = perf_counter(), process_time()
    state = query['snapshot'].clone(); settings=query['generator_settings']
    if public_sha(state)!=query['public_snapshot_sha256']:
        raise ValueError('captured query public Snapshot binding differs')
    if settings.get('deadline_ms') is not None or settings.get('cache_contract')!='isolated_replay_v1':
        raise ValueError('deterministic captured regional cache contract required')
    if family=='regional':
        generator=RegionalCandidateGenerator(horizon=settings['horizon'], expansion_limit=expansion,
            static_path_limit=settings['static_path_limit'], deadline_ms=None,
            dynamic_local=settings['dynamic_local'], local_label_limit=settings['local_label_limit'],
            cache_contract=settings['cache_contract'])
    elif family=='fullgraph_event':
        generator=FullGraphReferenceGenerator(horizon=settings['horizon'],expansion_limit=expansion,deadline_ms=None)
    else:
        raise ValueError('unknown fixed shadow family')
    failure=None; options=()
    try:
        if family=='fullgraph_event':
            with cold_fullgraph_cache():options=_generate(generator,state,query)
        else:options=_generate(generator,state,query)
    except Exception as error:
        failure={'type':type(error).__name__,'message':str(error)}
    mode='whole_route' if query['callsite']=='slow_empty' else 'next_edge'
    validator=ExecutionValidator(); accepted=[]; rejected=[]
    for option in options:
        try:
            verdict=validator.validate(state,option,route_mode=mode)
            (accepted if verdict.accepted else rejected).append(option if verdict.accepted else
                {'candidate':asdict(option),'reason':verdict.reason})
        except Exception as error:
            failure={'scope':'authorization','type':type(error).__name__,'message':str(error)}
            break
    result={'variant':name,'family':family,'settings':{'horizon':settings['horizon'],
        'expansion_limit':expansion,'requested_k':query['requested_k'],'deadline_ms':None},
        'status':generator.last_search_status,'work':generator.last_expansions,
        'diagnostics':deepcopy(generator.last_diagnostics),'failure':failure,
        'raw_options':[asdict(o)for o in options], 'raw_candidate_count':len(options),
        'authorized_options':[asdict(o)for o in accepted],'authorized_candidate_count':len(accepted),
        'rejections':rejected,'execution_mode_for_authorization':mode,
        'actual_action_keys':[actual_action_key(state,o,route_mode=mode)for o in accepted],
        'minimum_usable_at':min((o.usable_at for o in accepted),default=None),
        'query_input_unchanged':public_sha(state)==query['public_snapshot_sha256'],
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-started,
        'resource_scope':'Entire shadow function from input clone through generation/filtering; final caller serialization excluded.',
        'interpretation':'bounded shadow generation only; no candidate executed or offered to deployed policy'}
    if name=='regional3000':
        result['original_query_reproduced']=(result['raw_options']==[asdict(o)for o in query['options']]
            and result['status']==query['last_search_status'] and result['work']==query['last_expansions'])
        result['cache_comparison']='logical work/status/options exact; fresh private cold cache may do more physical preprocessing than captured warm cache'
    return result


def probe_query(query):
    """Fixed four-way probe; original-budget mismatch blocks further shadows."""
    if query['phase']!='returned':
        raise ValueError('only successfully completed query observations may be probed')
    if query['generator_settings']['expansion_limit']!=3000:
        raise ValueError('predeclared original3000 contract required')
    before=public_sha(query['snapshot']);results=[]
    if before!=query['public_snapshot_sha256']:
        raise ValueError('captured query public Snapshot binding differs')
    for variant in VARIANTS:
        try:result=shadow_variant(query,variant)
        except Exception as error:
            return {'status':'shadow_variant_failure','variants':results,
                'failed_variant':variant[0],'failure':{'type':type(error).__name__,'message':str(error)},
                'remaining_variants':'not run after measurement failure; prior completed variants retained'}
        results.append(result)
        if result['failure']:
            return {'status':'shadow_variant_failure','variants':results,'failed_variant':variant[0],
                'remaining_variants':'not run after generation/authorization failure; partial current evidence retained'}
        if variant[0]=='regional3000' and not result['original_query_reproduced']:
            return {'status':'baseline_query_mismatch','variants':results,'remaining_variants':'not run on unverified baseline'}
    if public_sha(query['snapshot'])!=before:
        raise ValueError('live captured query mutated')
    original_keys=set(results[0]['actual_action_keys'])
    original_usable=results[0]['minimum_usable_at']
    for result in results:
        result['new_authorized_action_keys']=sorted(set(result['actual_action_keys'])-original_keys)
        result['earlier_usable_than_original']=(original_usable is not None and result['minimum_usable_at']is not None
                                               and result['minimum_usable_at']<original_usable)
        result['resolves_original_zero']=not original_keys and bool(result['actual_action_keys'])
    return {'status':'completed_shadow_probe','variants':results,
            'no_physical_branch_executed':True,'input_sha256':before,
            'new_prefix_or_earlier_route_is_not_global_value_optimality':True}
