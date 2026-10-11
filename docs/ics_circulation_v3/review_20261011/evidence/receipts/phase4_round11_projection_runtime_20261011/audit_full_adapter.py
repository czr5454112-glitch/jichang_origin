"""Full 1x/2x source-authenticated adaptation; zero Simulation/physics calls."""
from pathlib import Path
import sys
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())
sys.path.insert(0, str(ROOT))
from dataclasses import asdict, replace
from hashlib import sha256
import gzip
import json
from time import process_time, perf_counter
import traceback
from scripts.experiments.ics_circulation_v3.business_inputs import load_business_workload
from scripts.experiments.ics_circulation_v3.business_projection import project_business_destinations
from scripts.experiments.ics_circulation_v3.business_runtime import build_business_runtime, parse_runtime_proxy_contract
from scripts.experiments.ics_circulation_v3.business_projection_runtime import RUN_POLICIES, build_projected_business_runtime

HERE = Path(__file__).parent
EXPERIMENTS = HERE.parent
OLD = EXPERIMENTS / 'phase4_w3_round8_business_input_research_repaired_20261010'
BUSINESS = EXPERIMENTS / 'phase4_round9_business_inputs_20261011'
PROJECTED = EXPERIMENTS / 'phase4_round10_business_projection_20261011/full_audit_002'
TASKS = ROOT / '.g4irsf24_worktree/artifacts/tasks/g4irsf31_nanning'
PROFILE = ROOT / 'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding='utf-8')


def main():
    out = HERE / sys.argv[1]
    out.mkdir()
    cpu, wall = process_time(), perf_counter()
    bindings = {}
    sources = [ROOT / 'scripts/experiments/ics_circulation_v3' / n for n in
        ('business_inputs.py', 'business_runtime.py', 'business_projection.py', 'business_projection_runtime.py')]
    sources += [ROOT / 'tests/test_ics_circulation_v3_business_projection_runtime.py', Path(__file__).resolve(), HERE / 'run_tests.py']
    def read(path):
        data = path.read_bytes()
        bindings[path.relative_to(ROOT).as_posix()] = sha256(data).hexdigest()
        return data
    report = dict(status='running', physical_calls=0, scales=[],
        qualification='Complete source-authenticated static-destination research proxy adaptation only; no physical capacity or algorithm-benefit claim.')
    before = {}
    try:
        (out / 'source_snapshot').mkdir()
        for path in sources:
            before[path.relative_to(ROOT).as_posix()] = sha256(read(path)).hexdigest()
            (out / 'source_snapshot' / path.name).write_bytes(path.read_bytes())
        for document in (HERE / 'DESIGN.md', OLD / 'BUSINESS_INPUT_DESIGN.md',
            ROOT / 'docs/ics_circulation_v3/phase4_external_review_20261009/ICS_V3_030493_audit_and_phase4_plan_20261009.md'):
            read(document)
        input_contract = json.loads(read(BUSINESS / 'runtime_input_contract_002.json'))
        runtime_contract = json.loads(read(BUSINESS / 'runtime_proxy_contract_002.json'))
        prior_manifest = json.loads(read(PROJECTED / 'manifest.json'))
        decisions = None
        for scale in (1, 2):
            scale_cpu, scale_wall = process_time(), perf_counter()
            report.update(current_scale=scale, current_stage='full_original_loader')
            source = dict(normalized=OLD / f'business_tasks_{scale}x.jsonl.gz',
                normalization_manifest=OLD / 'manifest.json', raw=TASKS / f'nanning_{scale}x_raw.txt',
                canonical=TASKS / f'nanning_{scale}x_canonical.jsonl',
                source_timetable=ROOT / 'legacy/jichang_origin_readonly/inputdata.txt',
                source_manifest=TASKS / f'nanning_{scale}x_manifest.json', graph_profile=PROFILE, contract=input_contract)
            original = load_business_workload(**source)
            for key, value in source.items():
                if key != 'contract':
                    read(value)
            declaration_bytes = read(PROJECTED / f'projection_contract_{scale}x.json')
            metadata_bytes = read(PROJECTED / f'projection_metadata_{scale}x.json')
            for name, data in ((f'projection_contract_{scale}x.json', declaration_bytes),
                               (f'projection_metadata_{scale}x.json', metadata_bytes)):
                assert prior_manifest[name] == sha256(data).hexdigest()
            declaration, metadata = json.loads(declaration_bytes), json.loads(metadata_bytes)
            assert declaration['source_workload_sha256'] == original.content_sha256
            report['current_stage'] = 'reconstruct_frozen_round10_projection'
            projection = project_business_destinations(original, PROFILE, declaration)
            assert projection.content_sha256 == metadata['content_sha256']
            assert projection.contract.canonical_sha256 == metadata['contract']['canonical_sha256']
            runtime = parse_runtime_proxy_contract(runtime_contract, original)
            run = dict(RUN_POLICIES, run_id=f'round11-full-adaptation-{scale}x',
                title=f'Complete {scale}x static destination adapter research proxy',
                source_workload_sha256=original.content_sha256, input_contract_sha256=original.contract.canonical_sha256,
                projection_sha256=metadata['content_sha256'], projection_contract_sha256=metadata['contract']['canonical_sha256'],
                runtime_contract_sha256=runtime.canonical_sha256, graph_sha256=original.contract.graph_sha256,
                assumption_id='round11-source-authenticated-full-adaptation-proxy', source_ref='DESIGN.md; frozen Round10 full_audit_002')
            write(out / f'run_contract_{scale}x.json', run)
            report['current_stage'] = 'full_adapter_raw_reload_and_domain_validation'
            adapted = build_projected_business_runtime(original, projection, source_inputs=source,
                projection_declaration=declaration, runtime_contract=runtime_contract, run_contract=run, profile_path=PROFILE)
            baseline = build_business_runtime(original, PROFILE, runtime_contract)
            assert adapted.initial == baseline.initial and len(adapted.initial.trays) == 11
            assert not adapted.initial.bags and not adapted.initial.storage_progress
            assert adapted.simulation_kwargs() == baseline.simulation_kwargs()
            assert adapted.environment_projection.original == original
            assert adapted.environment_projection.projection == projection
            assert len(adapted.future_bags) == original.raw_business_count == scale * 28506
            assert adapted.source_segment_count == scale * 43603
            report['current_stage'] = 'every_bag_preservation_and_runtime_tape_export'
            with gzip.open(out / f'private_runtime_tape_{scale}x.jsonl.gz', 'wt', encoding='utf-8') as stream:
                for before_bag, after, record in zip(baseline.future_bags, adapted.future_bags, projection.records):
                    assert after == replace(before_bag, destination=record.projected_destination)
                    assert type(after) is type(before_bag)
                    assert after.bag_id == record.original.business_bag_id
                    assert before_bag.destination == record.original_destination
                    row = dict(runtime_bag=asdict(after), original=asdict(record.original),
                        original_destination=record.original_destination, projected_destination=record.projected_destination,
                        group_id=record.group_id, run_contract_sha256=adapted.environment_projection.run_contract.canonical_sha256)
                    stream.write(json.dumps(row, sort_keys=True, default=str) + '\n')
            by_group = {g.group_id: g.projected_destination for g in projection.groups}
            assert len(by_group) == 360
            if decisions is None:
                decisions = by_group
            else:
                assert decisions == by_group
            report['scales'].append(dict(scale=scale, status='passed', business_count=original.raw_business_count,
                old_segment_count=original.old_segment_count, original_count=original.original_count, derived_count=original.derived_count,
                early_count=sum(t.lifecycle == 'early_storage' for t in original.tasks),
                changed_final_count=sum(r.original_destination != r.projected_destination for r in projection.records),
                parent_groups=len(projection.groups), flight_instances=sum(g.flight_instance_count for g in projection.groups),
                initial_trays=len(adapted.initial.trays), initial_public_bags=len(adapted.initial.bags),
                source_timetable_count=original.source_timetable_count,
                independent_observed_operating_days=original.independent_observed_operating_days,
                source_workload_sha256=original.content_sha256, projection_sha256=projection.content_sha256,
                run_contract_sha256=adapted.environment_projection.run_contract.canonical_sha256,
                physical_calls=0, cpu_seconds=process_time()-scale_cpu, wall_seconds=perf_counter()-scale_wall,
                cpu_accounting='Nested in parent; never add separately.'))
            write(out / 'progress.json', report)
        report['status'] = 'passed'
        report['current_stage'] = 'complete'
    except BaseException:
        report['status'] = 'failed'
        report['exception'] = traceback.format_exc()
    finally:
        after = {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sources}
        report.update(cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
            source_sha256_before=before, source_sha256_after=after, source_changed=before != after,
            scope='Single process parent includes both source loaders, both projection recomputations, baseline adapters, all comparisons/exports and nested per-scale CPU.',
            unmetered_auxiliary='Interpreter startup/imports and final resource/manifest writes; reading/editing auxiliary commands unknown.')
        if before != after:
            report['status'] = 'failed'
        write(out / 'resource.json', report)
        write(out / 'manifest.json', dict(input_sha256=bindings, outputs={
            p.relative_to(out).as_posix(): sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}))
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
