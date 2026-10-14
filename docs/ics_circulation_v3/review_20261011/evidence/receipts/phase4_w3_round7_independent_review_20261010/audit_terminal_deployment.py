"""Pure file audit of opt-in screen deployments against all original evidence."""
from hashlib import sha256
import gzip
import json
from pathlib import Path
import sys
from time import process_time, perf_counter
from audit_collection import ROOT, HERE, BASE, digest, physical


def main(stage):
    cpu, wall = process_time(), perf_counter()
    run = BASE / 'phase4_w3_terminal_capacity_screen_20261010'
    old = BASE / 'phase4_w3_same_zone_supply_repaired_20261010'
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

    def read(path, expected=None):
        value = data(path, expected)
        return json.loads(gzip.decompress(value) if Path(path).name.endswith('.gz') else value)

    for p, expected in read(run / 'preparation_manifest.json').items(): data(p, expected)
    protocol = read(run / 'protocol.json')
    for kind, folder in [('source', ROOT / 'scripts/experiments/ics_circulation_v3'), ('test', ROOT / 'tests')]:
        for name, expected in protocol[kind + '_sha256'].items(): data(folder / name, expected)
    for p, expected in protocol['input_sha256'].items(): data(p, expected)
    corpus_audit = read(HERE / 'terminal_corpus_artifact_audit.json')
    check(not corpus_audit['errors'] and corpus_audit['query_count'] == 2467, 'full independently recomputed certificate corpus')
    for p, expected in corpus_audit['bound_files'].items(): data(p, expected)
    facts = corpus_audit['query_facts']
    corpus = {r['query_id']:r for r in read(run / 'corpus.json')['rows']}
    for p, expected in read(run / (stage + '_manifest.json')).items(): data(p, expected)
    summary = read(run / stage / 'summary.json')
    requests = protocol['pilot'] if stage == 'pilot' else protocol['requests']
    definitions = {r['case_id']:r for r in requests}
    check(len(definitions) == len(summary['rows']) == summary['planned_requests'] == (3 if stage == 'pilot' else 27), 'complete actual deployment denominator')
    check({r['case_id'] for r in summary['rows']} == set(definitions), 'exact planned case identities')
    check(summary['source_inputs_tests_unchanged'] and not summary['pilot_reused_by_formal'], 'source stable and no reused physical calls')
    totals = {'query_count':0, 'certified_count':0, 'old_search_work':0, 'new_search_work':0, 'screen_work':0, 'physical_task_count':0}
    case_rows = []
    for row in summary['rows']:
        identity = row['case_id']
        request = definitions[identity]
        check(row['status'] == 'controller_quiescent' and row['raw_complete'] and row['actual_physical_call'], identity + ':complete independent physical execution')
        raw = read(run / row['file'], row['sha256'])
        original = read(old / request['file'], request['sha256'])
        current = raw['outcome']
        check(raw['case'] == request, identity + ':entire original deployment request')
        check(physical(current['result']) == physical(original['result']) and
              physical(current['original_endpoint']['result']) == physical(original['original_endpoint']['result']), identity + ':full and original-endpoint physical results')
        for key in ('status', 'stopped_at', 'initial_state', 'initial_cursor', 'opportunities', 'actual_slow_trigger_times',
                    'physical_tick_trace', 'event_trace_suffix', 'milestones', 'last_cycle_state', 'evaluation_ledger', 'selector_history_suffix'):
            check(current[key] == original[key], identity + ':exact ' + key)
        check([{k:v for k,v in item.items() if k != 'diagnostics'} for item in current['slow_history_suffix']] ==
              [{k:v for k,v in item.items() if k != 'diagnostics'} for item in original['slow_history_suffix']], identity + ':every actual slow trigger/proposal unchanged')
        accounting = raw['screen_accounting']
        observed = accounting['rows']
        expected_facts = sorted(((key, f) for key, f in facts.items() if f['case_id'] == identity), key=lambda item: item[0])
        check(len(observed) == len(expected_facts) == len(raw['query_checks']) == len(current['searches']) == original['search_calls'] == current['search_calls'] == row['search_calls'], identity + ':all query calls including certified returns')
        certified, old_work = 0, 0
        for actual, (query_id, expected), comparison, search in zip(observed, expected_facts, raw['query_checks'], current['searches']):
            check(all(actual[key] == expected[key] for key in ('time', 'version', 'bag_id', 'tray_id', 'destination', 'requested_k', 'public_snapshot_sha256')),
                  query_id + ':same full public Snapshot and request')
            check(digest(actual['options']) == expected['raw_pool_sha256'], query_id + ':entire actual ordered raw candidate pool')
            clean = lambda c: {k:v for k,v in c.items() if k not in ('screen_cpu_seconds', 'screen_wall_seconds')}
            check(clean(actual['certificate']) == clean(corpus[query_id]['certificate']), query_id + ':all certificate fields match independently audited same state')
            check(actual['phase'] == 'returned' and actual['error'] is None, query_id + ':completed measured query')
            check(search['work'] == actual['search_work'] and search['status'] == actual['search_status'] and
                  all(search[key] == actual[key] for key in ('time', 'bag_id', 'tray_id')) and
                  search['candidate_count'] == len(actual['options']), query_id + ':outer budget accounting still records query')
            if expected['certified']:
                check(actual['search_work'] == 0 and actual['search_status'] == 'terminal_capacity_certificate' and not actual['options'], query_id + ':only proven search suppressed')
            else:
                check(actual['search_work'] == expected['original_work'] and actual['search_status'] == expected['original_status'], query_id + ':all delegated logical search work/status unchanged')
            check(comparison['query_id'] == query_id and comparison['exact_input_identity_and_raw_pool'], query_id + ':runner comparison confirmed independently')
            certified += expected['certified']
            old_work += expected['original_work']
        check(accounting['screen_work'] == sum(r['certificate']['screen_work'] for r in observed) == row['screen_work'], identity + ':separate entire record-work axis')
        check(accounting['screen_cpu_seconds'] == sum(r['certificate']['screen_cpu_seconds'] for r in observed), identity + ':nested screen CPU sum')
        check(accounting['observation_cpu_seconds'] == sum(r['observation_cpu_seconds'] for r in observed), identity + ':snapshot observation CPU separately identified')
        check(row['search_work'] == current['search_work'] == sum(r['search_work'] for r in observed), identity + ':complete actual routing work')
        check(row['certified_queries'] == certified, identity + ':exact suppressed query denominator')
        check(row['cache_after_equal'] == raw['cache_after_equal'] == (original['cache_after'] == current['cache_after']), identity + ':explicit actual private-cache difference')
        totals['query_count'] += len(observed)
        totals['certified_count'] += certified
        totals['old_search_work'] += old_work
        totals['new_search_work'] += current['search_work']
        totals['screen_work'] += accounting['screen_work']
        totals['physical_task_count'] += len(current['evaluation_ledger'])
        case_rows.append({'case_id':identity, 'queries':len(observed), 'certified':certified, 'old_search_work':old_work,
            'new_search_work':current['search_work'], 'screen_work':accounting['screen_work'], 'cost':current['result']['total_cost'], 'cache_after_equal':row['cache_after_equal']})
    if stage == 'formal':
        check(totals['query_count'] == 2467 and totals['certified_count'] == 93 and totals['old_search_work'] == corpus_audit['original_search_work'] and
              totals['new_search_work'] == corpus_audit['original_search_work'] - corpus_audit['certified_original_search_work'] and
              totals['screen_work'] == corpus_audit['screen_work'], 'entire corpus deployment work equivalence')
    for p, expected in bound.items(): check(sha256(Path(p).read_bytes()).hexdigest() == expected, 'final unchanged:' + p)
    report = dict(schema='round7_independent_terminal_deployment_audit_v1', stage=stage, checks=checks, errors=errors,
        totals=totals, rows=case_rows, bound_files=bound, new_physical_simulations=0, new_routing_searches=0,
        cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        qualification='Exact candidate/physical equivalence; cache and search diagnostics may differ as explicitly shown. Screen work differs from search work; observed collector overhead differs, so no CPU speedup claim.')
    with (HERE / ('terminal_' + stage + '_artifact_audit.json')).open('x', encoding='utf8') as stream: json.dump(report, stream, indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in ('bound_files', 'rows')}))
    return bool(errors)


if __name__ == '__main__': raise SystemExit(main(sys.argv[1]))
