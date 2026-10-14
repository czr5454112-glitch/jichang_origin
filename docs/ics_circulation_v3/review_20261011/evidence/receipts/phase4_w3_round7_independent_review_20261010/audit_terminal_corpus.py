"""Independent finite-horizon terminal obstruction sweep on every saved query."""
from dataclasses import asdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
import pickle
from time import process_time, perf_counter
from audit_collection import ROOT, HERE, BASE, digest
from scripts.experiments.ics_circulation_v3.runtime import INFINITY, effective_reservations


def main():
    cpu, wall = process_time(), perf_counter()
    run = BASE / 'phase4_w3_terminal_capacity_screen_20261010'
    origin = BASE / 'phase4_w3_same_zone_query_coverage_20261010'
    bound, errors, checks = {}, [], 0

    def check(ok, label):
        nonlocal checks
        checks += 1
        if not ok: errors.append(label)

    def data(path, expected=None):
        path = Path(path).resolve()
        value = path.read_bytes()
        actual = sha256(value).hexdigest()
        check(expected is None or expected == actual, 'SHA:' + str(path))
        if expected is not None and expected != actual: raise ValueError('mismatching artifact')
        check(str(path) not in bound or bound[str(path)] == actual, 'stable input:' + str(path))
        bound[str(path)] = actual
        return value

    def read(path, expected=None): return json.loads(data(path, expected))
    for p, expected in read(run / 'preparation_manifest.json').items(): data(p, expected)
    protocol = read(run / 'protocol.json')
    for kind, folder in [('source', ROOT / 'scripts/experiments/ics_circulation_v3'), ('test', ROOT / 'tests')]:
        for name, expected in protocol[kind + '_sha256'].items(): data(folder / name, expected)
    for p, expected in protocol['input_sha256'].items(): data(p, expected)
    for p, expected in read(run / 'corpus_manifest.json').items(): data(p, expected)
    corpus = read(run / 'corpus.json')
    prior = read(HERE / 'query_coverage_pilot_audit.json')
    check(not prior['errors'] and prior['query_count'] == 2467, 'complete prior collection audit')
    for p, expected in prior['bound_files'].items(): data(p, expected)
    rows = corpus['rows']
    definitions = {r['query_id']: r for r in rows}
    check(len(rows) == len(definitions) == corpus['queries'] == 2467, 'complete unique query denominator')
    certified, facts = 0, {}
    sum_work, rejected_work, screen_work = 0, 0, 0
    for case in read(origin / 'collections/summary.json')['rows']:
        for index in read(origin / case['query_index_file'], case['query_index_sha256']):
            identity = index['query_id']
            query = pickle.loads(gzip.decompress(data(origin / index['file'], index['sha256'])))
            state = query['snapshot']
            observed = definitions[identity]
            cert = observed['certificate']
            cutoff = state.now + query['generator_settings']['horizon']
            check(cert['cutoff'] == cutoff and cert['tray_id'] == query['tray_id'] and cert['destination'] == query['destination'], identity + ':same actual terminal domain')
            slots = [slot for slot in effective_reservations(state) if slot.tray_id != query['tray_id'] and
                     slot.resource == 'node:' + query['destination'] and slot.end > cutoff]
            # Independent formulation: enumerate all changes, count distinct
            # physical owners at each half-open point, rather than sum deltas.
            moments = sorted({cutoff} | {max(cutoff, s.start) for s in slots if s.start < INFINITY})
            capacity = state.network.nodes[query['destination']].capacity
            witness = None
            for tick in moments:
                owners = {s.tray_id for s in slots if s.start <= tick < s.end}
                if len(owners) >= capacity:
                    witness = (tick, len(owners))
                    break
            check(cert['certified'] == (witness is not None), identity + ':independent terminal interval obstruction')
            if witness is not None:
                check((cert['conflict_at'], cert['other_occupancy']) == witness and cert['capacity'] == capacity,
                      identity + ':exact earliest obstruction and physical owner count')
                expected_slots = [{'tray_id':s.tray_id, 'start':s.start, 'end':s.end} for s in slots if s.start <= witness[0] < s.end]
                check(cert['witness_slots'] == expected_slots and not query['options'], identity + ':all real obstruction slots and zero original candidates')
            check(cert['screen_work'] == sum(cert['work_by_stage'].values()) and cert['screen_work'] > 0, identity + ':nonzero separately accounted screen work')
            check(observed['original_status'] == query['last_search_status'] and observed['original_work'] == query['last_expansions'] and
                  observed['original_raw_count'] == len(query['options']) and observed['observed_false_positive'] is False, identity + ':original query facts')
            certified += bool(witness)
            sum_work += query['last_expansions']
            rejected_work += query['last_expansions'] if witness else 0
            screen_work += cert['screen_work']
            facts[identity] = {'case_id': case['case_id'], 'query_file': str(origin / index['file']), 'query_sha256': index['sha256'],
                **{key:query[key] for key in ('time', 'version', 'bag_id', 'tray_id', 'destination', 'requested_k', 'public_snapshot_sha256')},
                'raw_pool_sha256': digest([asdict(o) for o in query['options']]), 'certified': bool(witness),
                'original_work': query['last_expansions'], 'original_status':query['last_search_status']}
    check(certified == corpus['certified_count'] == 93 and corpus['false_positives_against_saved_raw'] == 0, 'all93 and zero false positives')
    check((sum_work, rejected_work, screen_work) == (corpus['original_search_work'], corpus['certified_query_original_search_work'], corpus['screen_work']), 'entire work accounting')
    for p, expected in bound.items(): check(sha256(Path(p).read_bytes()).hexdigest() == expected, 'final unchanged:' + p)
    report = dict(schema='round7_independent_terminal_corpus_audit_v1', checks=checks, errors=errors,
        query_count=len(facts), certified_count=certified, original_search_work=sum_work,
        certified_original_search_work=rejected_work, screen_work=screen_work, query_facts=facts, bound_files=bound,
        new_physical_simulations=0, new_routing_searches=0,
        cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Independent half-open owner-set interval sweep on all2467 saved public queries, exact original pool digests retained for subsequent deployment audit. Proof is scoped to current Snapshot/H full witnesses; no future business infeasibility or CPU speedup claim.')
    with (HERE / 'terminal_corpus_artifact_audit.json').open('x', encoding='utf8') as stream: json.dump(report, stream, indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in ('bound_files', 'query_facts')}))
    return bool(errors)


if __name__ == '__main__': raise SystemExit(main())
