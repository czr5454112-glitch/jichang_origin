"""Construct complete 1x/2x environment tapes under root's declared proxy.

No Simulation is constructed or stepped. All values are research assumptions.
"""
from pathlib import Path
import sys
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())
sys.path.insert(0, str(ROOT))
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from time import process_time, perf_counter
import traceback
from scripts.experiments.ics_circulation_v3.business_inputs import load_business_workload, parse_operation_contract
from scripts.experiments.ics_circulation_v3.business_runtime import build_business_runtime

HERE = Path(__file__).parent
OLD = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_w3_round8_business_input_research_repaired_20261010'
TASKS = ROOT / '.g4irsf24_worktree/artifacts/tasks/g4irsf31_nanning'
PROFILE = ROOT / 'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def main():
    run_id = sys.argv[1] if len(sys.argv) > 1 else '001'
    output = HERE / ('runtime_adapter_audit_' + run_id + '.json')
    if output.exists():
        raise FileExistsError('retain prior attempts; choose fresh run ID')
    cpu, wall = process_time(), perf_counter()
    sources = [ROOT / 'scripts/experiments/ics_circulation_v3' / name
               for name in ('business_inputs.py', 'business_runtime.py')]
    before = {str(p): digest(p) for p in sources}
    report = {'status': 'running', 'physical_calls': 0, 'scales': [], 'source_sha256_before': before}
    try:
        profile = json.loads(PROFILE.read_bytes())
        input_contract = json.loads((HERE / 'proxy_contract_003.json').read_bytes())
        input_contract['contract_id'] = 'round9-original-graph-runtime-input-proxy-v1'
        input_contract['title'] = 'Root declared original-graph 1s runtime development proxy'
        for node in input_contract['nodes']:
            node['capacity'] = 1 if node['node_id'] == '53' else 4
        for item in input_contract['evidence']:
            item['source_ref'] = 'BUSINESS_INPUT_RESULTS.md#runtime-proxy-assumptions'
            item['assumption_id'] = 'round9-root-runtime-' + item['field']
        input_obj = parse_operation_contract(input_contract, profile, digest(PROFILE))
        runtime = dict(schema='ics_business_runtime_proxy_v1', contract_id='round9-root-runtime-proxy-v1',
            evidence_status='proxy_research', input_contract_sha256=input_obj.canonical_sha256,
            graph_sha256=digest(PROFILE),
            node_resource_policy='exact_bound_input_node_capacity_and_loaded_wait',
            empty_wait_policy='same_as_declared_loaded_wait_proxy',
            edge_permission_policy='both_modes_all_source_directed_edges_proxy',
            edge_capacity_policy='preserve_source_integer_including_closed_zero',
            travel_policy='exact_length_over_speed_ceil_to_input_tick',
            partition_by_node={str(n['location']): 'central-development-proxy' for n in profile['nodes']},
            module=dict(kind='existing_fixed_fifo_proxy', loading_seconds='0', unload_seconds='1',
                hold_seconds_by_node={str(n['location']): '0' for n in profile['nodes']},
                reception_capacity=1, export_min_stock=0),
            routing=dict(route_mode='whole_route', search_horizon=80, candidate_count=4,
                expansion_limit=10000, static_path_limit=12, local_label_limit=3,
                dynamic_local=True, deadline_ms=None, cache_contract='isolated_replay_v1'),
            reactive_empty_dispatch=True, coordination_order='route_then_prebalance',
            evidence=[dict(field=k, source_ref='BUSINESS_INPUT_RESULTS.md#runtime-proxy-assumptions',
                           assumption_id='round9-root-runtime-'+k) for k in
                      ('permissions', 'module', 'partition', 'travel_capacity', 'routing', 'coordination')])
        write(HERE / ('runtime_input_contract_' + run_id + '.json'), input_contract)
        write(HERE / ('runtime_proxy_contract_' + run_id + '.json'), runtime)
        for scale in (1, 2):
            start_cpu, start_wall = process_time(), perf_counter()
            workload = load_business_workload(normalized=OLD / f'business_tasks_{scale}x.jsonl.gz',
                normalization_manifest=OLD / 'manifest.json', raw=TASKS / f'nanning_{scale}x_raw.txt',
                canonical=TASKS / f'nanning_{scale}x_canonical.jsonl', source_timetable=ROOT / 'legacy/jichang_origin_readonly/inputdata.txt',
                source_manifest=TASKS / f'nanning_{scale}x_manifest.json', graph_profile=PROFILE, contract=input_contract)
            adapted = build_business_runtime(workload, PROFILE, runtime)
            result_sha = sha256()
            for task in adapted.future_bags:
                result_sha.update((json.dumps(asdict(task), sort_keys=True, separators=(',', ':')) + '\n').encode())
            report['scales'].append(dict(scale=scale, business_count=adapted.source_business_count,
                old_segment_count=adapted.source_segment_count, bag_types=dict(Counter(type(b).__name__ for b in adapted.future_bags)),
                environment_bag_sha256=result_sha.hexdigest(), observed_initial_bag_count=len(adapted.initial.bags),
                observed_initial_storage_progress=len(adapted.initial.storage_progress),
                initial_tray_count=len(adapted.initial.trays), graph_nodes=len(adapted.initial.network.nodes),
                graph_edges=len(adapted.initial.network.edges), closed_edge_ids=adapted.closed_edge_ids,
                module=asdict(adapted.initial.module), input_contract_sha256=workload.contract.canonical_sha256,
                runtime_contract_sha256=adapted.contract.canonical_sha256,
                input_sha256=dict(workload.input_sha256), cpu_seconds=process_time()-start_cpu,
                wall_seconds=perf_counter()-start_wall))
        report['source_sha256_after'] = {str(p): digest(p) for p in sources}
        assert report['source_sha256_after'] == before
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        report['cpu_seconds'] = process_time()-cpu
        report['wall_seconds'] = perf_counter()-wall
        report['resource_scope'] = 'explicit interval after imports; per-scale measurements nested, do not add twice'
        write(output, report)


if __name__ == '__main__':
    main()
