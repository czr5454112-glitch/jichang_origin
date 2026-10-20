"""Read-only, bounded opportunity census; no proposed API deletion is executed."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
REFERENCE = OUT / 'original_route_pending_ack_prepare_001'
CASES = ('baseline', 'drop_first_ack', 'ack_withheld_in_window')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
def write(p, value):
    with Path(p).open('x', encoding='utf8') as stream: json.dump(value, stream, indent=2, allow_nan=False)


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    sources = {str(Path(__file__).resolve()): sha(__file__),
               str(Path(bounded_windows_job.__file__).resolve()): sha(bounded_windows_job.__file__)}
    paths = [REFERENCE / 'independent_verification.json', REFERENCE / 'receipt.json']
    paths += [REFERENCE / case / name for case in CASES for name in ('raw.json.gz', 'service_tape.jsonl.gz')]
    assert sha(paths[0]) == '660547e068fe019793090200ff269b2697fe1bdb7465dff03e6465edb1f8c0cc'
    write(output/'plan.json', {'schema': 'g31.pending_ack_notification_census.v1',
        'sources': sources, 'files': {str(p): sha(p) for p in paths}, 'cases': list(CASES),
        'hard_timeout_seconds': 120, 'new_native_executions': 0,
        'hypothesis': 'After witnessed first hop, fresh contiguous owner notification without ACK16 or timeout32, before immutable retry due, may permit skipping only the query. No policy modified here.',
        'limits': 'Read-only opportunities, not actual speedup, source proof, complete request attribution, or certified removable time.'})


def worker(output):
    start = time.perf_counter()
    plan_path = output/'plan.json'; plan = read(plan_path); plan_sha = sha(plan_path)
    for path, digest in (plan['sources'] | plan['files']).items(): assert sha(path) == digest, path
    result = {}
    for case in CASES:
        raw = json.loads(gzip.decompress((REFERENCE/case/'raw.json.gz').read_bytes()))
        root = raw['root']; owner = root['owner']; proof = root['pending_ack_path']['sticky_observed_hop']
        request_id = root['intent']['decision']['request_id']
        last_sequence = None; last_advance = None; next_retry = None; count = 0
        queries, opportunities, masks = [], [], Counter()
        with gzip.open(REFERENCE/case/'service_tape.jsonl.gz', 'rt', encoding='utf8') as stream:
            for index, line in enumerate(stream):
                row = json.loads(line); assert row['ordinal'] == index
                count += 1
                if row['endpoint'] == 'advance_until_owner_notification':
                    after = row['args'][1][owner]
                    continuous = last_sequence is not None and after == last_sequence
                    response = row['result']; notice = response.get('notifications', {}).get(owner)
                    if response.get('timestamp_complete') is True:
                        last_sequence = notice['sequence'] if notice else after
                    else:
                        last_sequence = None
                    last_advance = {'ordinal': index, 'after_cursor': after, 'continuous_cursor': continuous,
                        'timestamp_complete': response.get('timestamp_complete') is True,
                        'after': row['after'], 'notice': notice}
                if row['role'] == 'request' and row['endpoint'] == 'submit_protocol_command':
                    assert row['args'][0]['request_id'] == request_id
                    next_retry = row['after'] + 60.
                if row['role'] != 'request' or row['endpoint'] != 'protocol_command': continue
                assert row['args'] == [owner, request_id]
                if proof is None or row['before'] <= proof['observed_at']: continue
                notice = last_advance['notice'] if last_advance else None
                mask = notice.get('change_mask') if notice else None
                reason = 'no_fresh_contiguous_notice'
                if (last_advance and last_advance['continuous_cursor'] and last_advance['timestamp_complete']
                        and last_advance['after'] == row['before'] and notice
                        and notice.get('observed_at') == row['before']
                        and type(mask) is int and 0 < mask <= 255):
                    if mask & 48: reason = 'ack_or_timeout_notice'
                    elif next_retry is None or row['before'] >= next_retry: reason = 'retry_due_or_unknown'
                    else: reason = 'candidate_no_ack_before_retry'
                ack = row['result'].get('last_delivered_ack', {})
                entry = {'ordinal': index, 'at': row['before'], 'next_retry': next_retry,
                    'notice': notice, 'advance_ordinal': last_advance['ordinal'] if last_advance else None,
                    'cursor_contiguous': last_advance['continuous_cursor'] if last_advance else False,
                    'reason': reason, 'api_envelope_ns': row['end_ns']-row['start_ns'],
                    'delivered_ack': ack}
                queries.append(entry); masks[str(mask)] += 1
                if reason == 'candidate_no_ack_before_retry': opportunities.append(entry)
        assert count == raw['api_rows'] and sha(REFERENCE/case/'service_tape.jsonl.gz') == raw['api_sha256']
        result[case] = {'all_tape_rows': count, 'post_hop_request_queries': len(queries),
            'candidate_query_omissions': len(opportunities), 'reason_counts': dict(Counter(x['reason'] for x in queries)),
            'mask_counts': dict(masks), 'candidate_api_envelope_ns': sum(x['api_envelope_ns'] for x in opportunities),
            'all_post_hop_query_envelope_ns': sum(x['api_envelope_ns'] for x in queries),
            'candidate_queries_with_delivered_ack': sum(bool(x['delivered_ack']) for x in opportunities),
            'root_warm_ns': (root['returned_ns'] if root['returned_ns'] is not None else root['censored_ns'])-root['started_ns'],
            'root_closed': root['returned_ns'] is not None, 'rows': queries}
        write(output/(case+'.json'), result[case])
    for path, digest in (plan['sources'] | plan['files']).items(): assert sha(path) == digest, path
    assert sha(plan_path) == plan_sha
    write(output/'report.json', {'status': 'completed_read_only_census', 'plan_sha256': plan_sha,
        'cases': {k: {name: value for name, value in row.items() if name != 'rows'} for k, row in result.items()},
        'wall_seconds': time.perf_counter()-start, 'source_changed': [], 'new_native_executions': 0,
        'physics_or_shared_cost_subtracted_ns': 0, 'complete_100ms_certified': False,
        'limits': plan['limits']})


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ('prepare', 'launch', 'worker'): modes.add_argument('--'+mode, action='store_true')
    parser.add_argument('--admission'); args = parser.parse_args(); output = args.output.resolve()
    if args.prepare: prepare(output); return
    if args.worker:
        assert args.admission and sys.stdin.readline().strip() == args.admission
        worker(output); return
    assert not (output/'external_process.json').exists() and not (output/'stdout.log').exists()
    token = str(uuid.uuid4()); start = time.perf_counter()
    with (output/'stdout.log').open('x') as stdout, (output/'stderr.log').open('x') as stderr:
        result = bounded_windows_job.run([sys.executable, '-m', __package__+'.diagnose_pending_ack_notifications',
            '--worker', '--output', str(output), '--admission', token], timeout=120., stdout=stdout, stderr=stderr,
            admission=token, cwd=str(ROOT))
    write(output/'external_process.json', {**result, 'parent_after_import_wall_seconds': time.perf_counter()-start})
    raise SystemExit(0 if result['status'] == 'exited' and result['exitcode'] == 0 else 1)

if __name__ == '__main__': main()
