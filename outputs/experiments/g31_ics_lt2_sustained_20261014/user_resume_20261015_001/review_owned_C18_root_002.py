from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import initial_owner_route_single_capture_owned_codec_campaign as c
from scripts.experiments.g31_ics_circulation import prepare_single_capture_owned_codec_campaign as prep
from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_single_capture_owned_codec_campaign as launch
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=c.ROOT;sha=c.sha
DEST=OUT/'single_owned_C18_prepare_002';expected='4ac4569ad5145ccf62e83a39d29ad238077bf00fa0657c130fb12916cfb91bdc'
assert sha(DEST/'campaign.json')==expected
assert sha(DEST/'source_preparation.json')=='e1c7642a6cef3f78549f8b8207e7bef797db2145248d64186146542584eb93ce'
plan=c.verify_plan(DEST,expected);prepared=c.read(DEST/'source_preparation.json')
assert len(plan['source_sha256'])==218 and len(plan['compiled_source_archive_sha256'])==67
lengths=[]
for name,digest in plan['source_sha256'].items():
    current=(ROOT/name).resolve();archive=(DEST/plan['source_archive'][name]).resolve()
    assert not Path(name).is_absolute() and not Path(name).drive and '..' not in Path(name).parts
    assert current.is_relative_to(ROOT) and archive.is_relative_to(DEST/'source') and current!=archive
    assert sha(current)==digest==sha(archive);lengths.append(len(str(archive)))
assert max(lengths)<260
base=c.read(prep.BASE/'campaign.json')
for name in ('row_order','rows','input_file_sha256','image','expected_READY','compiled_source_archive_sha256','native_contract_reference','semantic_gate_reference'):
    assert plan[name]==base[name],name
assert plan['hard_timeout_seconds']==600. and plan['native_branch_budget']==18 and plan['max_native_workers']==1
assert c.contract.BUDGET_NS==100_000_000 and len(plan['rows'])==18 and c.declarations()==plan['rows']
assert plan['C_provider']==c.runtime.metadata() and len(plan['C_provider']['toolchain_sha256'])==6124
assert plan['C_provider']['provider_includes_original_fallback'] is True and plan['C_provider']['actual_direct_C_supported'] is None
assert c.source_proof()==plan['owned_C_campaign_source_proof'] and launch.main.__code__ is launch.old.main.__code__
PURE=OUT/'single_capture_owned_codec_campaign_pure_002';tested,testplan=prep.checked_pure(PURE)
assert len(testplan['source_sha256'])==161 and tested['tests']==38
assert sha(PURE/'receipt.json')=='165f0bd2bcc148b5b34230de56e2fae033338a80a51cb0ae5d1e45f3d07b9958'
assert sha(PURE/'tests.xml')=='80e491b982331e49b7c4db91c62627429ea9acecf77a493fc5562c9e69af99ce'
outer=c.read(DEST/'external_application_wall.json');parent=c.read(OUT/'single_owned_C18_prepare_002.metadata_parent.json')
assert outer['exitcode']==0 and outer['exception'] is None and 0<outer['whole_python_wall_seconds']<=120
assert parent['process']['status']=='exited' and parent['process']['exitcode']==0 and parent['process']['windows_job_kill_on_close'] is True
assert sha(OUT/'invoke_single_owned_C18_prepare_002.ps1')==outer['wrapper_sha256']
assert all(outer[k]==0 for k in ('native_calls','model_calls','C_loads','performance_runs'))
correction=c.read(OUT/'single_capture_owned_codec_campaign_pure_001/fixture_correction_before_002.json')
assert sha(OUT/'single_capture_owned_codec_campaign_pure_001/fixture_correction_before_002.json')=='fcd1fbdb66277630d8636c6629910dae0e850feea47cae0fedafeb03c0ae140c'
for name,digest in correction['four_business_sources_unchanged'].items():assert sha(ROOT/name)==digest==plan['source_sha256'][name]
assert not any((DEST/name).exists() for name in ('execution_claim.json','worker_claim.json','receipt.json'))
assert prepared['execute_command']==[str(c.sys.executable) if hasattr(c,'sys') else str(prep.sys.executable),'-m',launch.__package__+'.launch_initial_owner_route_single_capture_owned_codec_campaign','--output',str(DEST),'--campaign-sha256',expected]
result={'schema':'g31.single_capture.owned_C18.root_review.v1','status':'one_original18_campaign_authorized',
 'review_script_sha256':sha(__file__),'campaign_sha256':expected,'command':prepared['execute_command'],
 'verified_current_independent_archive_sources':218,'old_reference_domains':c.SOURCE_DOMAINS,
 'compiled_native_archive_files_verified':67,'C_toolchain_files_declared':6124,
 'C_toolchain_files_rehashed_in_this_root_review':False,'pure_tests':38,'pure_seconds':17.8191388,
 'metadata_seconds':outer['whole_python_wall_seconds'],'maximum_archive_path_chars':max(lengths),
 'source_proof':c.source_proof(),'owned600_required':True,'exclusive_performance_window_required':True,
 'requirements':['Exactly original18 rows/inputs/faults/finite2 with same60ms decision cutoff and100ms complete request boundary. Full startup, provider andnative/RPC setup, all roots, cleanup, sources, three full6124 checks, export and saved verification belong to600.','Actual accepted004 module file/spec/ExtensionFileLoader, bound builtin and DLL files at entry/exit. Original exact Python inventory separately retained. Direct C support/fallback count unknown; original fallback retained.','Original failure-aware saved verification through both replay levels; unknowns remain in18 denominator, failure must not mint success. All5 physical/strict normal protection, source/current/ACK/firsthop/drain checks unchanged.','External launch-to-exit clock with exact command/plan/runner/wrapper/output binding; no automatic retry or extension. Use distinct actual external receipt filename because metadata external_application_wall.json already exists.'],
 'limits':['Root read all runtime/campaign/verifier/launcher/test/pure/preparer code, plus original worker and launcher. Only test fixture changed after37pass/1fail; strengthened38 pass; old failure frozen.','Long-path metadata001 failure retained. Short002 same source and gates passed,218 contained paths max243.','No actual C/native/model loaded in review. Earlier finite2 baseline16closed/2unknown/0under100 remains until separately interpreted actual result. No full32 or all-day/joint-method claim.']}
path=DEST/'root_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'root_review_sha256':sha(path),'status':result['status'],'sources':218,'max_path':max(lengths)}))
