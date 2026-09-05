"""Verify portable full-population evidence and original executable preservation."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

from run_feng_dh_semantics_reaudit import EXPECTED, stats

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'outputs/runtime/feng_dh_semantics_reaudit_20260905'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check(path: Path, expected: str) -> None:
    if digest(path.read_bytes()) != expected:
        raise RuntimeError(f'identity mismatch: {path}')


def portable(value: str) -> Path:
    # Run identities keep the actual machine paths. Locate the repository
    # portion so validation also works after a clone to another directory.
    normalized = value.replace('\\', '/')
    for marker in ('benchmarks/', 'docs/', 'legacy/', 'data/', 'outputs/'):
        position = normalized.find(marker)
        if position >= 0:
            return ROOT / normalized[position:]
    raise ValueError(f'no repository path in {value}')


def main() -> None:
    for value, expected in EXPECTED.values():
        check(ROOT/value, expected)
    with (ROOT/EXPECTED['schedule'][0]).open(encoding='utf-8-sig',newline='') as f:
        schedule = {(int(r['raw_bag_id']),int(r['segment_id'])): r for r in csv.DictReader(f)}
    checked = []
    for identity_path in sorted(RUNTIME.glob('*/run_identity.json')):
        identity = json.loads(identity_path.read_text(encoding='utf-8'))
        if identity['status'] != 'COMPLETE':
            raise RuntimeError(f'run did not complete: {identity_path}')
        for name, expected in identity['source_files'].items():
            check(portable(identity['source_dir'])/name, expected)
        protocol = identity.get('protocol_path','docs/baselines/feng_dh_map2_reaudit_protocol_20260905.md')
        check(portable(protocol),identity['protocol_sha256'])
        for name, expected in identity['outputs'].items():
            path = identity_path.parent/name
            if name in ('bags.csv','segments.csv'):
                raw = gzip.decompress((identity_path.parent/(name+'.gz')).read_bytes())
                if digest(raw) != expected:
                    raise RuntimeError(f'compressed full-population source differs: {path}')
            elif name == 'trace.csv' and not path.exists():
                # Formal full runs deliberately used traceSampleModulo=0.
                # The empty trace header is not portable evidence.
                if '--trace-sample-modulo' not in identity['command']:
                    raise RuntimeError('missing trace policy')
                i = identity['command'].index('--trace-sample-modulo')
                if identity['command'][i+1] != '0':
                    raise RuntimeError('missing nonempty trace')
            else:
                check(path,expected)
        with gzip.open(identity_path.parent/'segments.csv.gz','rt',encoding='utf-8',newline='') as f:
            segments = list(csv.DictReader(f))
        if len(segments) != len(schedule):
            raise RuntimeError('segment population differs')
        seen, totals = set(), {}
        for row in segments:
            key = int(row['raw_bag_id']),int(row['segment_id'])
            if key in seen or key not in schedule:
                raise RuntimeError('duplicate or foreign segment')
            seen.add(key)
            s = schedule[key]
            if row['status'] != 'COMPLETED' or any(row[k]!=s[k] for k in ('start','goal')):
                raise RuntimeError('incomplete or different OD')
            release = float(s['scheduled_release_seconds'])
            value = float(row['completion_time_seconds'])-release
            if abs(float(row['release_seconds'])-release)>1e-7 or abs(value-float(row['table53_scheduled_interval_seconds']))>1e-6:
                raise RuntimeError('shared-D leg timing differs')
            totals[key[0]] = totals.get(key[0],0.0)+value
        with gzip.open(identity_path.parent/'bags.csv.gz','rt',encoding='utf-8',newline='') as f:
            bags = list(csv.DictReader(f))
        ids = {int(b['raw_bag_id']) for b in bags}
        if len(bags)!=28506 or ids!=set(range(28506)) or len(totals)!=28506:
            raise RuntimeError('bag population differs')
        for row in bags:
            if row['complete']!='true' or abs(totals[int(row['raw_bag_id'])]-float(row['table53_scheduled_interval_seconds']))>1e-6:
                raise RuntimeError('per-bag sum differs')
        audit = json.loads((identity_path.parent/'population_and_gate.json').read_text(encoding='utf-8'))
        measured = stats(list(totals.values()))
        if not all(audit['checks'].values()) or any(abs(measured[k]-audit['THT_seconds_shared_D'][k])>1e-6 for k in measured):
            raise RuntimeError('native audit differs')
        checked.append({'run':identity_path.parent.name,'bags':len(bags),'segments':len(segments),'pass':True})
    if not checked:
        raise RuntimeError('no completed full-population evidence')
    historical_path = ROOT/'outputs/runtime/feng_dh_historical_signatures_20260905/manifest.json'
    historical = json.loads(historical_path.read_text(encoding='utf-8'))
    check(ROOT/historical['generator']['path'],historical['generator']['sha256'])
    for artifact in historical['artifacts']:
        check(ROOT/artifact['path'],artifact['sha256'])
    tail = json.loads((RUNTIME/'boundary_clearance_tail_review/manifest.json').read_text(encoding='utf-8'))
    for name, expected in tail['inputs'].items():
        check(ROOT/name,expected)
    for item in [tail['generator'],tail['report'],*tail['artifacts']]:
        check(ROOT/item['path'],item['sha256'])
    report = {'schema':'feng.dh.portable_reaudit_verification.v1','runs':checked,
              'historical_artifacts_verified':len(historical['artifacts']),
              'tail_inputs_and_artifacts_verified':len(tail['inputs'])+2+len(tail['artifacts']),
              'protected_inputs_verified':len(EXPECTED),'full_population_archive_roundtrip':True,
              'source_and_protocol_identities_verified':True,
              'scope':'Map2 semantic re-audit only; the later user-selected V5 campaign has separate records.',
              'new_nanning_or_expanded_population_runs_in_this_reaudit_root':0}
    (RUNTIME/'portable_verification.json').write_bytes((json.dumps(report,indent=2)+'\n').encode('utf-8'))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
