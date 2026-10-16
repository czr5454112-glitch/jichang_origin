from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
DEST=OUT/'live_owned_initial_runtime_source_prepare_001'
plan=json.loads((DEST/'plan.json').read_bytes());canonical={};absolute=[];source_changed=[];archive_bad=[]
for name,digest in plan['source_sha256'].items():
    path=(ROOT/name).resolve()
    assert path.is_relative_to(ROOT)
    key=path.relative_to(ROOT).as_posix()
    if Path(name).is_absolute():absolute.append(name)
    if key in canonical:assert canonical[key]==digest
    canonical[key]=digest
    if sha(path)!=digest:source_changed.append(name)
    archive=DEST/plan['source_archive'][name]
    if not archive.is_file() or not archive.resolve().is_relative_to(DEST):
        archive_bad.append({'name':name,'declared_archive':plan['source_archive'][name],
            'constructed_path':str(archive),'exists':archive.is_file()})
    elif sha(archive)!=digest:archive_bad.append({'name':name,'reason':'hash_mismatch'})
result={'schema':'g31.owned_runtime.root_archive_failure.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'source_archive_preparation_rejected','plan_sha256':sha(DEST/'plan.json'),
 'failed_root_review_script_sha256':sha(HERE/'review_owned_runtime_source_root_001.py'),
 'pure_result_scope':'47 tests passed on current sources; claimed full archived closure is invalid. No actual model/native run.',
 'declared_source_keys':len(plan['source_sha256']),'absolute_source_keys':len(absolute),'unique_canonical_sources':len(canonical),
 'current_source_changed':source_changed,'invalid_declared_archives':archive_bad,
 'cause':'Source_files copied old absolute source-map keys, then merged new relative keys without canonicalization. Output/source/absolute-key discarded the archive root and rewrote current files with the same bytes; source/+absolute archive strings did not designate those files.',
 'scope':'Current source hashes verified unchanged. Same-byte writes can alter file timestamps; no claim that original files were never written. No rollback or fabricated archive performed.',
 'required_repair':'New version canonicalizes old absolute read paths to resolved ROOT-relative POSIX keys before merging, rejects escapes, merges only equal bytes, verifies archive containment. Add full path/prepare composition tests; new pure and prepare outputs, no rerun or promotion of failed001.',
 'model_calls':0,'native_calls':0,'current_sources_written_by_this_root_inspection':0}
with (HERE/'owned_runtime_archive_failure_root_001.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'declared':len(plan['source_sha256']),'absolute':len(absolute),'unique':len(canonical),'invalid_archive_count':len(archive_bad),
 'current_source_changed':source_changed,'failure_record_sha256':sha(HERE/'owned_runtime_archive_failure_root_001.json')}))
