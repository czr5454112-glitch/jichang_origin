"""One-pass saved clock/payload census. No policy import, model, native or C load."""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
SOURCE = BASE / 'single_owned_C18_prepare_002'
OUTPUT = BASE / 'single_owned_C18_cost_analysis_001'
LIMIT = 120.
PIN = 'f01b6e3f743ce5fb73f561d71774d1e9960c2cea36969dffef099bb290510480'
PHASES = ('admission_through_A_collection', 'collection_through_final_check',
          'postcheck_through_last_event', 'last_event_to_finalization',
          'complete_evidence_build_through_first_encode', 'strict_roundtrip_hash_ledger_return_tail')

def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_bytes())
def reference(path): return {'path': str(path), 'sha256': sha(path.read_bytes())}
def encoded(value): return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')
def write(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
def stats(values):
    return {'count': len(values), 'sum': sum(values), 'median': statistics.median(values) if values else None,
            'min': min(values) if values else None, 'max': max(values) if values else None}
def interval(a, b):
    assert type(a) is int and type(b) is int and 0 <= a <= b
    return a, b
def clipped(rows, begin, end):
    return [(max(a, begin), min(b, end)) for a, b in rows if a < end and b > begin]
def total(rows): return sum(b-a for a,b in rows)
def disjoint(rows):
    ordered = sorted(rows)
    assert all(a[1] <= b[0] for a,b in zip(ordered, ordered[1:])), 'overlapping clock categories'

def analyze(raw, verified, sample):
    assert len(raw['root_records']) == 1
    record = raw['root_records'][0]
    root = record['value']['evidence']
    events = root['events']
    start, end = root['root_started_ns'], record['outside_return_ns']
    final = record['finalization_started_ns']
    collection = next(e for e in events if e['stage'] == 'actual_A_collection')
    checks = [e for e in events if e['stage'] == 'final_local_and_receiver_check']
    boundaries = [start, collection['wall_ns'], checks[0]['wall_ns'] if checks else collection['wall_ns'],
                  events[-1]['wall_ns'], final, record['value']['body_finished_ns'], end]
    assert all(type(x) is int for x in boundaries) and boundaries == sorted(boundaries)
    partition = dict(zip(PHASES, (b-a for a,b in zip(boundaries, boundaries[1:]))))
    assert sum(partition.values()) == end-start == record['warm_caller_elapsed_ns']
    assert (end-start)/1e6 == verified['root']['warm_ms']
    evidence_bytes = encoded(root)
    assert len(evidence_bytes) == record['ledger']['bytes']
    assert sha(evidence_bytes) == record['ledger']['evidence_sha256']
    proof = root['runtime_query_proof']
    trace = proof['trace']
    native_intervals = [interval(c['started_ns'], c['finished_ns']) for c in proof['advance_calls']]
    refresh_intervals = [interval(c['started_ns'], c['finished_ns']) for c in trace['refreshes']]
    query_intervals = [interval(c['started_ns'], c['query_finished_ns']) for c in trace['reads']]
    rpc_intervals = [interval(e['value']['started_ns'], e['value']['finished_ns'])
                     for e in events if e['stage'] == 'RPC_attempt']
    categories = {'recorded_native_advance_with_response_copy': clipped(native_intervals, start, final),
                  'original_refresh_with_trace_and_queries': clipped(refresh_intervals, start, final),
                  'RPC_attempt_with_validation': clipped(rpc_intervals, start, final)}
    for rows in categories.values(): disjoint(rows)
    disjoint([row for rows in categories.values() for row in rows])
    disjoint(query_intervals)
    for q, data in zip(query_intervals, trace['reads']):
        r = refresh_intervals[data['refresh']]
        assert r[0] <= q[0] <= q[1] <= r[1]
    measured = {k: total(v) for k,v in categories.items()}
    measured['unclassified_prefinalization'] = final-start-sum(measured.values())
    measured['complete_finalization'] = end-final
    assert measured['unclassified_prefinalization'] >= 0
    assert sum(measured.values()) == end-start
    query_ns = total(clipped(query_intervals, start, final))
    assert query_ns <= measured['original_refresh_with_trace_and_queries']
    size_by_body = [len(encoded(b)) for b in trace['ack_bodies']]
    repeated = [q for q in trace['reads'] if q['ack_ref'] is not None and not q['body_is_new']]
    new = [q for q in trace['reads'] if q['body_is_new']]
    ids = {}
    for q in trace['reads']:
        entry = ids.setdefault(q['request_id'], {'queries': 0, 'reused_body_reads': 0, 'body_payload_bytes_examined_proxy': 0})
        entry['queries'] += 1
        if q['ack_ref'] is not None and not q['body_is_new']:
            entry['reused_body_reads'] += 1
            entry['body_payload_bytes_examined_proxy'] += size_by_body[q['ack_ref']]
    event_sizes = Counter()
    for event in events: event_sizes[event['stage']] += len(encoded(event))
    interevent = Counter()
    previous = start
    for event in events:
        assert previous <= event['wall_ns']
        interevent[event['stage']] += event['wall_ns'] - previous
        previous = event['wall_ns']
    phase_coverage = {}
    for name, begin, finish in zip(PHASES, boundaries, boundaries[1:]):
        phase_coverage[name] = {k: total(clipped(v, begin, finish))/1e6 for k,v in categories.items()}
    return {
        'root': verified['root'], 'choice': root['choice'], 'hop': root['hop'],
        'root_started_ns': start, 'outside_return_ns': end,
        'warm_partition_ns': partition, 'warm_partition_ms': {k:v/1e6 for k,v in partition.items()},
        'exclusive_known_and_residual_ms': {k:v/1e6 for k,v in measured.items()},
        'nested_query_ms': query_ns/1e6,
        'refresh_excluding_query_envelope_ms': (measured['original_refresh_with_trace_and_queries']-query_ns)/1e6,
        'phase_clock_coverage_ms': phase_coverage,
        'counts': {'events': len(events), 'advance_calls': len(native_intervals),
                   'refreshes': len(refresh_intervals), 'queries': len(query_intervals),
                   'new_ACK_bodies': len(new), 'reused_ACK_body_reads': len(repeated)},
        'event_counts': dict(Counter(e['stage'] for e in events)),
        'event_interarrival_ms_not_function_cost': {k:v/1e6 for k,v in interevent.items()},
        'payload': {'complete_bytes': len(evidence_bytes),
                    'top_level_value_bytes': {k: len(encoded(v)) for k,v in root.items()},
                    'runtime_proof_value_bytes': {k: len(encoded(v)) for k,v in proof.items()},
                    'trace_value_bytes': {k: len(encoded(v)) for k,v in trace.items()},
                    'event_bytes_by_stage': dict(event_sizes),
                    'ACK_unique_body_bytes': sum(size_by_body),
                    'ACK_reused_body_read_bytes_proxy': sum(size_by_body[q['ack_ref']] for q in repeated),
                    'ACK_by_request': ids},
        'overrides': [{'stage':e['stage'], 'at':e['at'], 'root_elapsed_ms':(e['wall_ns']-start)/1e6}
                      for e in events if 'overrun' in e['stage']],
        'native_setup_before_root_ms': (start-raw['clocks']['branch_setup_started_ns'])/1e6,
        'RPC': None if sample is None else {
            'caller_ms': sample['caller_elapsed_ns']/1e6,
            'worker_compute_ms': sample['response']['compute_wall_ns']/1e6,
            'selection': sample['response']['payload']['selection'],
            'budget': sample['response']['payload']['budget']},
    }

def worker():
    start = time.perf_counter_ns()
    own = reference(Path(__file__).resolve())
    assert sha((SOURCE/'verification.json').read_bytes()) == PIN
    verification, ledger = read(SOURCE/'verification.json'), read(SOURCE/'branch_ledger.json')
    lifetime = read(SOURCE/'predictor_lifetime.json')
    samples = {r['request_id']:r for r in lifetime['ledger']}
    assert verification['branches'] == len(ledger) == 18
    rows, raw_pins = {}, {}
    for key, entry in ledger.items():
        path = Path(entry['raw']['path'])
        compressed = path.read_bytes()  # one physical read; hash and decode share these bytes
        assert sha(compressed) == entry['raw']['sha256']
        decoded = gzip.decompress(compressed)
        raw = json.loads(decoded)
        assert raw['key'] == key
        root_id = raw['root_records'][0]['value']['evidence']['root_id']
        rows[key] = analyze(raw, verification['rows'][key], samples.get(root_id))
        raw_pins[key] = {**entry['raw'], 'compressed_bytes':len(compressed), 'decoded_bytes':len(decoded)}
        del raw, decoded, compressed
    summaries = {}
    for label, selected in [('all18', list(rows.values())),
                            ('closed16', [r for r in rows.values() if r['root']['closed']]),
                            ('default_closed', [r for k,r in rows.items() if k.endswith('/fixed_default') and r['root']['closed']]),
                            ('budget_closed', [r for k,r in rows.items() if k.endswith('/budget_two') and r['root']['closed']]),
                            ('unknown2', [r for r in rows.values() if not r['root']['closed']])]:
        summaries[label] = {'warm_ms': stats([r['root']['warm_ms'] for r in selected]),
            'partitions_ms': {k:stats([r['warm_partition_ms'][k] for r in selected]) for k in PHASES},
            'exclusive_ms': {k:stats([r['exclusive_known_and_residual_ms'][k] for r in selected])
                              for k in selected[0]['exclusive_known_and_residual_ms']},
            'nested_query_ms': stats([r['nested_query_ms'] for r in selected]),
            'payload_bytes': stats([r['payload']['complete_bytes'] for r in selected]),
            'counts': {k:sum(r['counts'][k] for r in selected) for k in selected[0]['counts']}}
    source_files = ['initial_owner_route_request.py', 'initial_owner_route_campaign.py',
        'initial_owner_route_gated_evidence_v2.py','initial_owner_route_outbox_trace.py',
        'initial_owner_route_outbox_trace_v2.py','initial_owner_route_gate_adapter.py',
        'research_native_preexisting_v3_bound.py','complete_root_evidence_owned_decode_v2.py',
        'single_root_evidence.py','complete_root_evidence_codec.py',
        'initial_owner_route_single_capture_owned_codec.py']
    pins = {name:reference(Path(__file__).parent/name) for name in source_files}
    report = {'schema':'g31.single_owned_C18.saved_cost_analysis.v1', 'status':'saved18_clock_partition_complete',
        'source':reference(SOURCE/'verification.json'),'compact':reference(SOURCE/'actual_compact_summary_001.json'),
        'rows':rows,'summaries':summaries,'raw_inputs_read_once':raw_pins,'source_pins':pins,'reader':own,
        'interval_semantics': {
            'partition':'Six adjacent integer-clock intervals sum exactly to full root. Medians of columns need not sum to median root.',
            'event_clock':'_record timestamps before its deepcopy; event-to-event spans include prior record copying and intervening work, not isolated stage functions.',
            'exclusive':'Recorded advance, refresh, and RPC-attempt intervals verified disjoint; prefinal remainder is not attributed to a function.',
            'query':'Actual query envelopes are nested inside refresh and MUST NOT be added to refresh; refresh remainder includes ACK comparison, strict_same, copies, trace bookkeeping and retry dispatch with no finer clock.',
            'advance':'Starts after argument snapshot; includes native call and response deepcopy. Not isolated native computation.',
            'finalization':'Build-to-first-encode includes runtime proof/C-or-fallback normalize/first encode. Tail includes strict parse/reencode, hash, ledger encode, append/return. No exact split inside either interval.',
            'payload':'Byte sizes/counts are structure proxies, not time or C-direct-support evidence.'},
        'cold': {'C_provider':verification['C_provider_lifetime'],
                 'RPC_startup_ms':verification['predictor_startup_ms'],
                 'RPC_cleanup_ms':verification['predictor_close_with_cleanup_ms'],
                 'scope':'Cold setup, 3 full file checks, native branch setup, whole40 continuation, export and saved audit remain separately charged; none is amortized out of full campaign.'},
        'no_new_native_model_C_profile':True,'full_saved_verifier_rerun':False,
        'GC':'Default process GC remains enabled; no sample-local cycle reclamation claim.',
        'elapsed_before_export_ms':(time.perf_counter_ns()-start)/1e6}
    assert reference(Path(__file__).resolve()) == own
    write(OUTPUT/'report.json', report)
    print(json.dumps({'report':reference(OUTPUT/'report.json'),'rows':len(rows),
                      'closed':summaries['closed16']}, ensure_ascii=False))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true');parser.add_argument('--admission');args=parser.parse_args()
    if args.worker:
        assert args.admission == reference(Path(__file__).resolve())['sha256']
        assert sys.stdin.readline() == args.admission+'\n'
        worker();return 0
    from . import bounded_windows_job
    OUTPUT.mkdir(exist_ok=False)
    admission=reference(Path(__file__).resolve())['sha256']
    command=[sys.executable,'-m',__spec__.name,'--worker','--admission',admission]
    execution={'schema':'g31.saved_cost_owned_execution.v1','limit_seconds':LIMIT,
               'command':command,'reader':reference(Path(__file__).resolve()),'no_native_model_C':True}
    try:
        with (OUTPUT/'worker.stdout.log').open('x',encoding='utf8') as out,(OUTPUT/'worker.stderr.log').open('x',encoding='utf8') as err:
            execution['process']=bounded_windows_job.run(command,timeout=max(.001,LIMIT-(time.monotonic()-BOOT)),
                                                        stdout=out,stderr=err,cwd=ROOT,admission=admission)
        execution['status']='passed' if execution['process']['status']=='exited' and execution['process']['exitcode']==0 else 'failed_or_unknown'
    finally:
        execution['before_final_export_seconds']=time.monotonic()-BOOT
        if (OUTPUT/'report.json').exists(): execution['report']=reference(OUTPUT/'report.json')
        write(OUTPUT/'execution.json',execution)
    return 0 if execution['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
