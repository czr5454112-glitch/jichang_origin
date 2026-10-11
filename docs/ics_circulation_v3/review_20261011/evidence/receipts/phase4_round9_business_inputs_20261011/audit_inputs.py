"""Round9 complete pure-input audit. No physical/runtime calls."""
from pathlib import Path
import sys
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())
sys.path.insert(0, str(ROOT))
from collections import Counter, defaultdict
from hashlib import sha256
import json
from time import process_time, perf_counter
import traceback
from scripts.experiments.ics_circulation_v3.business_inputs import load_business_workload

HERE = Path(__file__).parent
OLD = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_w3_round8_business_input_research_repaired_20261010'
TASKS = ROOT / '.g4irsf24_worktree/artifacts/tasks/g4irsf31_nanning'
PROFILE = ROOT / 'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def run():
    run_id = sys.argv[1] if len(sys.argv) > 1 else '001'
    result_path = HERE / ('audit_' + run_id + '.json')
    if result_path.exists():
        raise FileExistsError('retain prior audit attempts; select a fresh run ID')
    cpu, wall = process_time(), perf_counter()
    source = ROOT / 'scripts/experiments/ics_circulation_v3/business_inputs.py'
    source_sha = digest(source)
    report = {'status': 'running', 'physical_calls': 0, 'source_sha256_before': source_sha,
        'qualification': 'Pure environment-input audit only. Explicit proxy assumptions; no field operating contract or runtime integration.',
        'scales': []}
    try:
        profile = json.loads(PROFILE.read_bytes())
        contract = {
            'schema': 'ics_business_inputs_v1', 'scope': 'input_only_fixed_storage_proxy',
            'contract_id': 'round9-input-demonstration-proxy-v1',
            'title': 'Input-only proxy demonstration; not an executable airport scenario',
            'evidence_status': 'proxy_research', 'graph_sha256': digest(PROFILE), 'tick_seconds': '1',
            'deadline': {'policy': 'std_minus_lead', 'lead_seconds': '0'},
            'protection': {'policy': 'all', 'business_ids': []},
            'initial_trays': [{'tray_id': f'proxy-initial-{n}', 'node_id': str(n), 'available_seconds': '0'}
                               for n in profile['business_roles']['source_candidate_ids']],
            'initial_storage': [],
            'nodes': [{'node_id': str(n['location']), 'capacity': 1, 'loaded_wait_allowed': True}
                       for n in profile['nodes']],
            'storage': {'node_id': '53', 'capacity': 1, 'carrier_policy': 'on_carrier',
                'publication_policy': 'irrevocable_at_bag_arrival',
                'release_policy': 'normalized_scheduled_release',
                'uses_node_wait_capacity': True, 'dedicated_retrieval': False},
            'evidence': [{'field': field, 'source_ref': 'BUSINESS_INPUT_RESULTS.md#explicit-assumptions',
                          'assumption_id': 'round9-input-demo-' + field}
                         for field in ('clock', 'deadline', 'protection', 'initial_trays', 'nodes', 'storage')]
        }
        write(HERE / ('proxy_contract_' + run_id + '.json'), contract)
        adjacency = defaultdict(set)
        for edge in profile['edges']:
            if edge['capacity'] > 0:
                adjacency[str(edge['start'])].add(str(edge['end']))
        reach = {}
        for origin in set(str(n) for n in profile['business_roles']['source_candidate_ids']) | {'53'}:
            visited = {origin}
            queue = [origin]
            while queue:
                for target in adjacency[queue.pop()]:
                    if target not in visited:
                        visited.add(target)
                        queue.append(target)
            reach[origin] = visited
        for scale in (1, 2):
            scale_cpu, scale_wall = process_time(), perf_counter()
            workload = load_business_workload(
                normalized=OLD / f'business_tasks_{scale}x.jsonl.gz',
                normalization_manifest=OLD / 'manifest.json',
                raw=TASKS / f'nanning_{scale}x_raw.txt',
                canonical=TASKS / f'nanning_{scale}x_canonical.jsonl',
                source_timetable=ROOT / 'legacy/jichang_origin_readonly/inputdata.txt',
                source_manifest=TASKS / f'nanning_{scale}x_manifest.json', graph_profile=PROFILE, contract=contract)
            quantization = max((t.arrival * workload.contract.tick_seconds - t.arrival_seconds) for t in workload.tasks)
            counts = Counter(t.lifecycle for t in workload.tasks)
            unreachable = sum(t.final_destination not in reach[t.origin] for t in workload.tasks)
            stage_unreachable = sum((t.storage_node not in reach[t.origin] or t.final_destination not in reach[t.storage_node])
                                    if t.storage_node else t.final_destination not in reach[t.origin]
                                    for t in workload.tasks)
            rows = [dict(business_bag_id=t.business_bag_id, raw_identity=t.source_identity,
                         parent_id=t.source.parent_task_id, arrival=t.arrival, deadline=t.deadline,
                         protected=t.protected, release_at=t.release_at, published_at=t.published_at,
                         source_seconds=str(t.arrival_seconds), origin=t.origin, destination=t.final_destination)
                    for t in workload.tasks]
            import gzip
            payload = '\n'.join(json.dumps(x, separators=(',', ':'), sort_keys=True) for x in rows).encode()
            identity_path = HERE / f'full_business_clock_binding_{scale}x_{run_id}.jsonl.gz'
            identity_path.write_bytes(gzip.compress(payload, mtime=0))
            report['scales'].append(dict(scale=scale, raw_business_count=workload.raw_business_count,
                old_segment_count=workload.old_segment_count, original_count=workload.original_count,
                derived_count=workload.derived_count, source_timetable_count=workload.source_timetable_count,
                independent_observed_operating_days=workload.independent_observed_operating_days,
                lifecycle_counts=dict(counts), protected_count=sum(t.protected for t in workload.tasks),
                finite_initial_trays=len(workload.contract.initial_trays),
                static_positive_capacity_outbound_unreachable_kept=unreachable,
                static_positive_capacity_stage_unreachable_kept=stage_unreachable,
                max_arrival_rounding_seconds=str(quantization),
                final_deadline_rounding='floor; no relaxed deadline',
                all_storage_publication_at_arrival=all(t.published_at == t.arrival for t in workload.tasks if t.storage_node),
                all_storage_release_after_publication=all(t.release_at >= t.published_at for t in workload.tasks if t.storage_node),
                impossible_discrete_arrival_deadline_kept=sum(t.arrival > t.deadline for t in workload.tasks),
                source_flight_proxy_groups=len({t.source.flight_surrogate for t in workload.tasks}),
                shifted_flight_proxy_groups=len({(t.source.flight_surrogate, t.source.time_shift_seconds) for t in workload.tasks}),
                input_sha256=dict(workload.input_sha256), contract_sha256=workload.contract.canonical_sha256,
                output_clock_binding_sha256=digest(identity_path), output_clock_binding=identity_path.name,
                cpu_seconds=process_time()-scale_cpu, wall_seconds=perf_counter()-scale_wall))
        report['source_sha256_after'] = digest(source)
        assert report['source_sha256_after'] == source_sha
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        report['cpu_seconds'] = process_time() - cpu
        report['wall_seconds'] = perf_counter() - wall
        report['resource_scope'] = 'explicit interval after stdlib/module import; child scale CPU is nested, not additive'
        write(result_path, report)


if __name__ == '__main__':
    run()
