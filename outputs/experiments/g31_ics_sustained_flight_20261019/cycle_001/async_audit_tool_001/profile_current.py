"""Diagnostic cProfile of saved actual evidence. No native process or source edits."""
import cProfile
import gzip
import hashlib
import json
import platform
from pathlib import Path
import pstats
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_repeated_domain as domain


def ref(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    destination = Path(__file__).resolve().parent/'profile_001'
    if destination.exists():
        raise ValueError('fresh_profile_directory_required')
    destination.mkdir()
    source = destination.parent.parent/'A2_train_prefer8_001'/'raw.json.gz'
    raw = json.loads(gzip.decompress(source.read_bytes()))
    rows = []
    for index, attempt in enumerate(raw['repeated_attempts']['B']):
        evidence = attempt['evidence']
        if evidence['phase'] != 'cycle_route':
            continue
        before = domain.digest(evidence)
        profiler = cProfile.Profile()
        started, cpu = time.perf_counter_ns(), time.process_time_ns()
        result = profiler.runcall(domain.evaluate, evidence, domain.ACTIONS['cycle_route'])
        elapsed, cpu_elapsed = (time.perf_counter_ns()-started)/1e6, (time.process_time_ns()-cpu)/1e6
        if domain.digest(evidence) != before:
            raise ValueError('profile_mutated_evidence')
        exact = result['status'] == attempt['model_report']['status'] and all(
            result['candidate_results'][action]['completion'] == attempt['model_report']['candidate_results'][action]['completion']
            for action in domain.ACTIONS['cycle_route'])
        path = destination/f'current_{index:02d}.pstats'; profiler.dump_stats(str(path))
        stats = pstats.Stats(profiler)
        calls = [{'path': filename, 'line': lineno, 'function': name, 'primitive_calls': values[0],
            'total_calls': values[1], 'self_seconds': values[2], 'cumulative_seconds': values[3]}
            for (filename, lineno, name), values in stats.stats.items()]
        with (destination/f'current_{index:02d}_cumulative.txt').open('w', encoding='utf8') as stream:
            pstats.Stats(profiler, stream=stream).sort_stats('cumulative').print_stats(45)
        rows.append({'actual_evidence_sha256': before, 'sim_at': evidence['at'],
            'target_job': evidence['collection']['trigger_tray']['business_bag_id'],
            'profiled_call': 'domain.evaluate(existing_actual_evidence, three_registered_candidates)',
            'profile_wall_ms_not_benchmark': elapsed, 'profile_cpu_ms_not_benchmark': cpu_elapsed,
            'saved_actual_collect_plus_projection_ms': attempt['collection_and_guard_wall_ms'],
            'predicted_completion_exactly_matches_closed_actual_run_report': exact,
            'profile': ref(path), 'top_cumulative': sorted(calls, key=lambda row: -row['cumulative_seconds'])[:30],
            'top_self': sorted(calls, key=lambda row: -row['self_seconds'])[:30]})
    result = {'schema': 'g31.independent.current_profile.v1', 'status': 'diagnostic_not_benchmark',
        'raw_reference': ref(source), 'script': ref(Path(__file__).resolve()), 'domain_source': ref(Path(domain.__file__)),
        'python': sys.version, 'platform': platform.platform(), 'native_started': False,
        'source_edited': False, 'input_or_case_changed': False, 'only_saved_current_evidence_used': True,
        'conditions': ['Single profiling process, cases sequential, one cProfile call per saved current evidence.',
            'Get-Process -Name python,pythonw immediately before launch reported no Python process; this is only a point-in-time observation.',
            'No exclusive CPU reservation; concurrent processes may start or run. CIM process inventory was unavailable.',
            'Imports completed before profile, no unprofiled warmup; file caches inherited from this desktop session.',
            'cProfile adds overhead; these elapsed values are diagnostic and must not replace real run timings.',
            'Only domain.evaluate is profiled. Collect, submit, native progression and end-to-end path are excluded.'],
        'rows': rows}
    (destination/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({'status': result['status'], 'rows': len(rows), 'all_exact_completion_parity': all(
        row['predicted_completion_exactly_matches_closed_actual_run_report'] for row in rows)}))


if __name__ == '__main__':
    main()
