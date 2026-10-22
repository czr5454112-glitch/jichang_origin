"""Bounded first-ten-observation diagnostic, not a full-period cache audit."""
import importlib.util
from itertools import islice
from pathlib import Path
import sys

DATA = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cache_prefix_audit', DATA/'final_science_audit_004.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)

def main():
    output = DATA/'cache_prefix_diagnostic_005_001.json'
    a.need(not output.exists(), 'fresh_prefix_diagnostic')
    producer = a.bind(__file__)
    audit = a.bind(DATA/'final_science_audit_004.py')
    a.need(audit['sha256'] == 'fa3518b68ed3e0c6abea0293752ba58c922c53bc290bfe31ea1a1d9bf96ca6c2', 'original_audit_producer')
    report_ref = a.bind(DATA/'final_science_005_resumed_001/P2201_TF-B1-300-replan300_behavior_timing.json.gz')
    report = a.bound_read(report_ref)
    plan = a.bound_read(report['evidence']['plan.json'])
    source_ref = plan['source_bundle']; root = a.verify_sources(source_ref); h = a.load_helpers(root)
    obs_ref = report['evidence']['observations.json.gz']; dec_ref = report['evidence']['decisions.json.gz']
    refs = [producer, audit, report_ref, report['evidence']['plan.json'], source_ref, obs_ref, dec_ref]
    a.verify_bindings(refs, 'prefix_input_changed')
    decisions = {(d['owner_id'],d['decision_time']):d for d in islice(h['stream'].iter_json_array_gz(dec_ref['path']),10)}
    previous = {}; rows = []
    for record in islice(h['stream'].iter_json_array_gz(obs_ref['path']),10):
        obs = record['observation']; owner = obs['owner_id']; at = obs['now']
        d = decisions[(owner,at)]
        a.need(h['digest'].digest(obs) == d['public_observation_ref'], 'prefix_observation_binding')
        projection = h['projection'].prepare_inventory_projection(obs)
        accounts = {n:{k:v for k,v in state.items() if k in ('stock','waiting','inventory_known','waiting_known','service_rate')}
                    for n,state in projection.nodes.items()}
        parts = dict(topology=[obs['node_records'],obs['edge_records'],obs.get('edge_contracts'),obs.get('known_faults')],
                     contracts=obs['node_contracts'], accounts=accounts,
                     menu=sorted((r['tray_id'],r['source'],r['destination']) for r in d['catalog']['candidates'] if r['action_type']=='transfer'),
                     commitments=[(r.get('request_id'),r.get('status')) for r in obs['client_transfer_ledger']])
        old = previous.get(owner)
        changes = None if old is None else {key:old[key] != value for key,value in parts.items()}
        changed_accounts = [] if old is None else [dict(node=n,before=old['accounts'][n],after=value)
                                                  for n,value in accounts.items() if old['accounts'][n] != value]
        snapshots = [dict(status=s['status'], delivered_at=s['delivered_at'], payload_sha256=s['payload_sha256'],
                         captured_at=s['capture']['captured_at'],valid_until=s['capture']['valid_until'])
                     for s in obs.get('planning_snapshots',[])]
        rows.append(dict(at=at,owner=owner,flow_cache=d['flow_cache'],snapshots=snapshots,
                         component_changes=changes, changed_accounts=changed_accounts,
                         known_inventory_nodes=sum(v['inventory_known'] for v in accounts.values())))
        previous[owner] = parts
    a.need(len(rows)==10, 'exact_prefix_count')
    a.verify_bindings(refs, 'prefix_input_changed_at_end'); a.verify_sources(source_ref)
    a.fresh(output,dict(schema='g31.terminal_flow.cache_prefix_diagnostic.v1',source_bundle=source_ref,
        inputs=refs,rows=rows,native_starts=0,
        scope='Only P2201 replan300 first ten observations, t=7200..7440, two owners. No population extrapolation.',
        missing_components=['logical_claims'],
        full_invalidation_signature_reproduced=False,
        reconstruction='Frozen no-forecast projection used only for forecast-independent account fields.',
        interpretation='Coverage becoming known or expiring changes accounts even when topology, menu and commitments are unchanged. Expired remote inventory remains unknown, not zero.'))

if __name__ == '__main__': main()
