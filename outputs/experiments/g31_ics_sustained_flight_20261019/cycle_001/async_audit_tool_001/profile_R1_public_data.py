"""Offline diagnostic only. Reads saved legal data, never grants native authority.

Run only after all timing calibrations close. Endpoint getter cost is omitted;
cProfile perturbs timing, so this is not a live-request latency benchmark.
"""
import argparse
import cProfile
import gzip
import hashlib
import io
import json
from pathlib import Path
import pstats
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_repeated_native as native


def ref(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def run(folder, output):
    folder, output = Path(folder).resolve(), Path(output).resolve()
    assert not output.exists()
    raw = json.loads(gzip.decompress((folder/'raw.json.gz').read_bytes()))
    assert (folder/'receipt.json').exists() and raw['summary']['status'] == 'assessed'
    rows = []
    profiler = cProfile.Profile(timer=time.thread_time)
    for decision in raw['repeated_decisions']:
        if decision['current_admission']['execution_mode'] != 'protected_current':
            continue
        evidence = next(item['evidence'] for item in raw['repeated_attempts'][decision['owner']]
            if item['evidence']['collection']['request_id'] == decision['current_admission']['collection_request_id'])
        endpoints = evidence['information']['raw_endpoints']; retained = evidence['retained']
        session = SimpleNamespace(physical_time=evidence['at'],
            protocol_planning_snapshots_v3=lambda owner: endpoints['received'])
        ledger = native.ContractLedger(session, decision['owner'])
        ledger.contracts, ledger.sources = retained['contracts'], retained['sources']
        ledger.static, ledger.at = retained['static_contract_sha256'], retained['retained_at']
        client = SimpleNamespace(owned=lambda owner: evidence['own_outbox'])
        policy = SimpleNamespace(owner=decision['owner'], session=session, ledger=ledger, client=client,
            resident=object() if raw['specification']['mode'] == 'async' else None)
        public = native.observation(policy, endpoints['view'], decision['opportunity'])
        assert public == decision['observation'], 'saved actual pre-submit public data parity'
        profiler.enable()
        for _ in range(5):
            assert native.observation(policy, endpoints['view'], decision['opportunity']) == public
        profiler.disable()
        rows.append({'decision_id': decision['decision_id'], 'target_job': decision['opportunity']['target']['business_bag_id'],
            'exact_public_parity': True, 'repetitions': 5, 'delivered_messages': len(endpoints['received']),
            'own_outbox_rows': len(evidence['own_outbox'])})
    stream = io.StringIO(); stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats('cumulative').print_stats(25)
    serialized = [{'file': key[0], 'line': key[1], 'function': key[2], 'primitive_calls': value[0],
        'total_calls': value[1], 'self_cpu_seconds': value[2], 'cumulative_seconds': value[3]}
        for key, value in sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:40]]
    output.write_text(json.dumps({'schema': 'g31.R1.offline_public_data_profile.v1',
        'raw': ref(folder/'raw.json.gz'), 'script': ref(__file__), 'source': ref(native.__file__),
        'condition': 'After registered R1 calibration closed; native not started by profiler. CPU contention is not experimentally controlled.',
        'scope': 'Actual observation function over saved endpoint dictionaries; original native getter cost is deliberately absent.',
        'profiler_timer': 'explicit_time.thread_time_CPU_seconds; this does not instrument live native request CPU',
        'clock_label_correction': 'Profile 001 used cProfile default wall timer despite self_cpu_seconds label; only profile 002 with explicit thread_time is CPU. The old diagnostic must not be cited as CPU evidence.',
        'not_a_native_latency_benchmark': True, 'source_edited': False, 'grant_current_authority': False,
        'decisions': rows, 'profile': serialized, 'human_profile': stream.getvalue()}, indent=2), encoding='utf8')
    print(stream.getvalue())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('run'); parser.add_argument('--output', required=True)
    args = parser.parse_args(); run(args.run, args.output)
