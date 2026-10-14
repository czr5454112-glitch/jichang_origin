"""All-source 1x/2x projection and semantic audit, with no simulation imports."""
from pathlib import Path
import sys
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())
sys.path.insert(0, str(ROOT))
from collections import Counter
from dataclasses import asdict
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from time import process_time, perf_counter
import traceback
from scripts.experiments.ics_circulation_v3.business_inputs import load_business_workload
from scripts.experiments.ics_circulation_v3.business_projection import project_business_destinations, validate_business_projection

HERE = Path(__file__).parent
EXPERIMENTS = HERE.parent
OLD = EXPERIMENTS / 'phase4_w3_round8_business_input_research_repaired_20261010'
BUSINESS = EXPERIMENTS / 'phase4_round9_business_inputs_20261011'
STATIC = EXPERIMENTS / 'phase4_round9_resource_ledger_20261011/static_domains_001'
TASKS = ROOT / '.g4irsf24_worktree/artifacts/tasks/g4irsf31_nanning'
PROFILE = ROOT / 'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding='utf-8')


def main():
    out = HERE / sys.argv[1]
    out.mkdir()  # Never overwrite a failed or successful prior invocation.
    cpu, wall = process_time(), perf_counter()
    bindings = {}
    def read(path):
        data = path.read_bytes()
        bindings[path.relative_to(ROOT).as_posix()] = sha256(data).hexdigest()
        return data
    report = dict(status='running', physical_calls=0, scales=[],
        qualification='Separate static necessary-domain proxy input version only; no capacity feasibility, real allocation, online or algorithm-benefit claim.')
    sources = [ROOT / 'scripts/experiments/ics_circulation_v3' / n for n in
               ('business_inputs.py', 'business_runtime.py', 'business_projection.py')]
    sources += [ROOT / 'tests/test_ics_circulation_v3_business_projection.py', Path(__file__).resolve(), HERE / 'run_tests.py']
    try:
        snapshot = out / 'source_snapshot'
        snapshot.mkdir()
        for source in sources:
            (snapshot / source.name).write_bytes(read(source))
        for document in (HERE / 'DESIGN.md',
            ROOT / 'docs/ics_circulation_v3/phase4_external_review_20261009/ICS_V3_030493_audit_and_phase4_plan_20261009.md',
            OLD / 'BUSINESS_INPUT_DESIGN.md'):
            read(document)
        template = json.loads(read(HERE / 'projection_declaration.json'))
        assert template['source_workload_sha256'] is None
        input_contract = json.loads(read(BUSINESS / 'runtime_input_contract_002.json'))
        runtime_contract = json.loads(read(BUSINESS / 'runtime_proxy_contract_002.json'))
        assert template['unload_seconds'] == runtime_contract['module']['unload_seconds']
        static_manifest = json.loads(read(STATIC / 'manifest.json'))
        static_bytes = read(STATIC / 'analysis.json')
        assert sha256(static_bytes).hexdigest() == static_manifest['outputs']['analysis.json']
        static = json.loads(static_bytes)
        static_groups = {(str(Fraction(str(r['flight_surrogate'][0]))), str(r['flight_surrogate'][1]), str(r['flight_surrogate'][2])): r
                         for r in static['flight_rows']}
        for relative, expected in static['input_sha256'].items():
            assert sha256(read(ROOT / relative)).hexdigest() == expected
        decisions = {}
        for scale in (1, 2):
            scale_cpu, scale_wall = process_time(), perf_counter()
            report['current_scale'] = scale
            report['current_stage'] = 'load_full_source'
            workload = load_business_workload(normalized=OLD / f'business_tasks_{scale}x.jsonl.gz',
                normalization_manifest=OLD / 'manifest.json', raw=TASKS / f'nanning_{scale}x_raw.txt',
                canonical=TASKS / f'nanning_{scale}x_canonical.jsonl',
                source_timetable=ROOT / 'legacy/jichang_origin_readonly/inputdata.txt',
                source_manifest=TASKS / f'nanning_{scale}x_manifest.json', graph_profile=PROFILE, contract=input_contract)
            for name, value in workload.input_sha256:
                path = Path(name)
                if not path.is_absolute():
                    path = ROOT / path
                if path.exists():
                    assert sha256(read(path)).hexdigest() == value
            contract = dict(template, source_workload_sha256=workload.content_sha256)
            # Source binding is populated once before either domain computation or selection.
            write(out / f'projection_contract_{scale}x.json', contract)
            report['current_stage'] = 'construct_full_projection'
            projected = project_business_destinations(workload, PROFILE, contract)
            report['current_stage'] = 'full_source_revalidation'
            validate_business_projection(projected, workload, PROFILE)
            report['current_stage'] = 'compare_frozen_round9_domains_and_identities'
            source_by_id = {t.business_bag_id: t for t in workload.tasks}
            assert tuple(r.original for r in projected.records) == workload.tasks
            assert projected.source_operation_contract == workload.contract
            assert projected.source_input_sha256 == workload.input_sha256
            assert projected.source_business_count == 28506 * scale
            assert len(projected.groups) == len(static_groups) == 360
            assert sum(g.flight_instance_count for g in projected.groups) == 360 * scale
            for group in projected.groups:
                previous = static_groups[group.parent_flight_key[1:]]
                assert tuple(previous['static_reachability_and_return_domain']) == group.structural_domain
                assert tuple(previous['static_deadline_necessary_domain']) == group.necessary_domain
                assert len(group.necessary_domain) == 36
                assert group.original_destination == previous['original_destination']
                if scale == 1:
                    assert {source_by_id[bag].source.raw_task_id for bag in group.business_bag_ids} == set(previous['raw_task_ids'])
                    decisions[group.group_id] = group.projected_destination
                else:
                    assert decisions[group.group_id] == group.projected_destination
            changed = [r for r in projected.records if r.original_destination != r.projected_destination]
            changed_groups = [g for g in projected.groups if g.original_destination != g.projected_destination]
            assert len(changed) == 4001 * scale and len(changed_groups) == 48
            report['current_stage'] = 'write_all_records_and_group_decisions'
            records_payload = '\n'.join(json.dumps(asdict(r), sort_keys=True, separators=(',', ':'), default=str)
                                       for r in projected.records).encode()
            (out / f'projected_tasks_{scale}x.jsonl.gz').write_bytes(gzip.compress(records_payload, mtime=0))
            write(out / f'flight_projection_{scale}x.json', [asdict(g) for g in projected.groups])
            metadata = {k: v for k, v in asdict(projected).items() if k not in ('records', 'groups')}
            write(out / f'projection_metadata_{scale}x.json', metadata)
            report['scales'].append(dict(scale=scale, business_count=projected.source_business_count,
                original_count=projected.original_count, derived_count=projected.derived_count,
                source_segment_count=projected.source_segment_count,
                parent_flight_families=len(projected.groups), flight_instances=sum(g.flight_instance_count for g in projected.groups),
                changed_parent_families=len(changed_groups), changed_bags=len(changed),
                unchanged_bags=projected.source_business_count-len(changed), all_original_fields_preserved=True,
                original_destination_counts=dict(Counter(r.original_destination for r in projected.records)),
                projected_destination_counts=dict(Counter(r.projected_destination for r in projected.records)),
                changed_target_counts=dict(Counter(r.projected_destination for r in changed)),
                domain_sizes=dict(Counter(len(g.necessary_domain) for g in projected.groups)),
                source_timetable_count=projected.source_timetable_count,
                independent_observed_operating_days=projected.independent_observed_operating_days,
                lifecycle_counts=dict(Counter(r.original.lifecycle for r in projected.records)),
                finite_initial_trays=len(projected.source_operation_contract.initial_trays),
                source_workload_sha256=workload.content_sha256, projection_sha256=projected.content_sha256,
                projection_contract_sha256=projected.contract.canonical_sha256,
                cpu_seconds_nested=process_time()-scale_cpu, wall_seconds_nested=perf_counter()-scale_wall))
            print(json.dumps(report['scales'][-1], indent=2), flush=True)
        report['status'] = 'passed'
        report['current_stage'] = 'complete'
    except BaseException:
        report['status'] = 'failed'
        report['exception'] = traceback.format_exc()
    finally:
        report['input_sha256'] = bindings
        report['changed_inputs'] = [name for name, digest in bindings.items()
            if sha256((ROOT / name).read_bytes()).hexdigest() != digest]
        if report['changed_inputs']:
            report['status'] = 'failed'
        report.update(cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
            scope='Same process all source reads, loading, full projection, full revalidation, records and group writes; imports and final receipt/manifest writes excluded.',
            nested_intervals_not_additional=True,
            unmetered_auxiliary='Earlier reading/editing/failed path lookup and JSON key discovery, imports and final receipt/manifest writes; no physics.')
        write(out / 'resource.json', report)
        write(out / 'manifest.json', {p.relative_to(out).as_posix(): sha256(p.read_bytes()).hexdigest()
                                     for p in out.rglob('*') if p.is_file()})
    print(json.dumps({k: report[k] for k in ('status', 'physical_calls', 'cpu_seconds', 'wall_seconds')}, indent=2))
    if report['status'] != 'passed':
        print(report.get('exception', report['changed_inputs']))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
