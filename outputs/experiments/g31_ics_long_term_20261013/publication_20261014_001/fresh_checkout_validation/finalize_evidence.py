from pathlib import Path
import hashlib
import json
import zipfile

out=Path(__file__).resolve().parent
root=Path('\\\\?\\'+str(out.parent/'clean_checkout_001'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((root/'docs/g31_ics_circulation/publication_20261014/source_manifest.json').read_text(encoding='utf-8'))
mismatches=[name for name,row in manifest['files'].items() if not (root/name).is_file() or sha(root/name)!=row['sha256'] or (root/name).stat().st_size!=row['bytes']]
artifacts=json.loads((root/'docs/g31_ics_circulation/publication_20261014/author_artifacts_manifest.json').read_text(encoding='utf-8'))
artifact_rows={name:{'expected_sha256':row['sha256'],'actual_sha256':sha(root/name),'bytes':(root/name).stat().st_size} for name,row in artifacts['files'].items()}
receipt=json.loads((out/'fresh_check_live/receipt.json').read_text(encoding='utf-8'))
report={'schema':'g31.fresh_archive_postcheck.v1','status':'passed' if not mismatches and all(r['expected_sha256']==r['actual_sha256'] for r in artifact_rows.values()) else 'failed',
    'source_manifest_files':len(manifest['files']),'source_manifest_mismatches_after_tests':mismatches,
    'author_artifacts':artifact_rows,
    'available_build_directories':sorted(p.name for p in root.glob('build*') if p.is_dir()),
    'archive_xlsx_files':sorted(str(p.relative_to(root)) for p in (root/'map_nanning').glob('*.xlsx')),
    'test_scope':{'current_native_and_python':401,'historical_011_counterexample':1,'native_identity_011_015':5},
    'original_project_parent_used':False,
    'provenance_scope':'Archive-relative Python dependencies and explicit author artifacts; same author Windows toolchain. Not an independent native build, a clean external operating system, or third-party review.',
    'counts':receipt['counts'],'evidence_hashes':{}}
for rel in ['execution_receipt.json','extraction_diagnosis.json','long_path_execution_receipt.json','fresh_check_live/receipt.json','fresh_check_live/junit.xml']:
    report['evidence_hashes'][rel]=sha(out/rel)
(out/'postcheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
