"""Probe fixed declaration integrity versus caller replacement of the trust root.

Reconstructs the published 1x input object and verifies its original content hash;
it does not rerun projection, source normalization, or physical simulation.
"""
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import process_time, perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
OUT = BASE / 'projection_boundary_001'
OUT.mkdir(exist_ok=False)
cpu, wall = process_time(), perf_counter()
sys.path.insert(0, str(ROOT))
bindings = {}
def read(path):
    data = path.read_bytes()
    bindings[path.relative_to(ROOT).as_posix()] = sha256(data).hexdigest()
    return data
report = {'status': 'running', 'physical_runs': 0, 'exception': None}
try:
    from scripts.experiments.ics_circulation_v3.business_inputs import (
        BusinessTask, BusinessWorkload, OperationContract, InitialTray, NodeInputContract,
        FixedStorageInputContract, EvidenceReference, SourceReference, business_workload_sha256)
    from scripts.experiments.ics_circulation_v3.business_projection import (
        BusinessProjectionError, _validate_source, parse_projection_contract)
    folder = BASE.parent / 'phase4_round10_business_projection_20261011/full_audit_002'
    metadata = json.loads(read(folder / 'projection_metadata_1x.json'))
    declaration = json.loads(read(folder / 'projection_contract_1x.json'))
    read(ROOT / 'scripts/experiments/ics_circulation_v3/business_projection.py')
    read(ROOT / 'scripts/experiments/ics_circulation_v3/business_inputs.py')
    contract = dict(metadata['source_operation_contract'])
    for name in ('tick_seconds', 'deadline_lead_seconds'):
        contract[name] = Decimal(contract[name])
    contract['protected_business_ids'] = tuple(contract['protected_business_ids'])
    contract['initial_trays'] = tuple(InitialTray(**{**r, 'available_seconds': Decimal(r['available_seconds'])}) for r in contract['initial_trays'])
    contract['nodes'] = tuple(NodeInputContract(**r) for r in contract['nodes'])
    contract['storage'] = FixedStorageInputContract(**contract['storage'])
    contract['evidence'] = tuple(EvidenceReference(**r) for r in contract['evidence'])
    contract = OperationContract(**contract)
    tasks = []
    for line in gzip.decompress(read(folder / 'projected_tasks_1x.jsonl.gz')).splitlines():
        row = json.loads(line)['original']
        source = row['source']
        source['flight_surrogate'] = (Decimal(source['flight_surrogate'][0]), *source['flight_surrogate'][1:])
        source['time_shift_seconds'] = Decimal(source['time_shift_seconds'])
        row['source'] = SourceReference(**source)
        row['old_segment_ids'] = tuple(row['old_segment_ids'])
        for key in ('arrival_seconds', 'std_seconds', 'deadline_seconds', 'scheduled_release_seconds'):
            if row[key] is not None:
                row[key] = Decimal(row[key])
        tasks.append(BusinessTask(**row))
    original = BusinessWorkload(tuple(tasks), contract, tuple(tuple(v) for v in metadata['source_input_sha256']),
        metadata['source_business_count'], metadata['source_segment_count'], metadata['original_count'], metadata['derived_count'],
        metadata['source_timetable_count'], metadata['independent_observed_operating_days'], metadata['information_scope'],
        declaration['source_workload_sha256'])
    assert original.content_sha256 == business_workload_sha256(original)
    _validate_source(original)
    parse_projection_contract(declaration, original)
    def key(t):
        return (t.source.parent_timetable_sha256, Fraction(t.source.flight_surrogate[0]),
                *t.source.flight_surrogate[1:])
    first_key = key(tasks[0])
    modified = replace(original, tasks=tuple(replace(t, final_destination='116') if key(t) == first_key else t for t in tasks))
    try:
        _validate_source(modified)
    except BusinessProjectionError as error:
        report['unsealed_payload_rejected'] = str(error)
    else:
        raise AssertionError('mutated payload with old content hash accepted')
    modified = replace(modified, content_sha256=business_workload_sha256(modified))
    _validate_source(modified)
    try:
        parse_projection_contract(declaration, modified)
    except BusinessProjectionError as error:
        report['resealed_payload_with_unchanged_external_declaration_rejected'] = str(error)
    else:
        raise AssertionError('changed payload bypassed unchanged declaration')
    replaced_declaration = {**declaration, 'source_workload_sha256': modified.content_sha256}
    parsed = parse_projection_contract(replaced_declaration, modified)
    assert parsed.source_workload_sha256 == modified.content_sha256 != original.content_sha256
    assert modified.input_sha256 == original.input_sha256
    report.update(status='passed', original_workload_hash=original.content_sha256,
        modified_workload_hash=modified.content_sha256,
        changed_original_tasks=sum(a != b for a, b in zip(original.tasks, modified.tasks)),
        replaced_declaration_contract_binding_accepted=True,
        qualification='Fixed external declaration rejects both stale and resealed payload mutations. Replacing the payload and its declaration replaces the trusted input root; this pure API does not reauthenticate raw files. This probe checks the binding gate, not complete projection validity for modified data. No new projected artifact or runtime input was created.')
    for path, digest in bindings.items():
        assert sha256((ROOT / path).read_bytes()).hexdigest() == digest
except Exception:
    report['status'], report['exception'] = 'failed', traceback.format_exc()
finally:
    report.update(cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
        inputs_sha256=bindings, script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        resource_scope='Read/decode/reconstruct/hash and binding probes only; initial imports/final write excluded; zero simulation and zero full projection calls.')
    (OUT / 'results.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != 'inputs_sha256'}, indent=2))
sys.exit(0 if report['status'] == 'passed' else 1)
