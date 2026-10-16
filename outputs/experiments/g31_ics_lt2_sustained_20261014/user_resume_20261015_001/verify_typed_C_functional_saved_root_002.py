from pathlib import Path
from collections import Counter
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent; OUT=HERE.parent; ROOT=HERE.parents[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
DEST=OUT/'planning_v2_C_encoder_functional_002';PREP=OUT/'planning_v2_C_encoder_gate_prepare_003'
pins={'receipt.json':'3116ddf66830d8f3f70cb6dc6651a29ecf539bf328db4ae1e28906edc49212cd',
 'bounded_execution.json':'2629c9c4ca7af41c05b89582873babc8c2afe35cad3c7f377715c94b5608edd0',
 'external_application_wall.json':'50709239e57767b579b79f03235a0aa6d082b30487798b4f69eddf8002bedb32',
 'tests.xml':'d1cc3a6e6cd8ec08533626bd795a09fd1e17ff5be17d418cc7874ab8e35e3290',
 'byte_probe.json':'02158ae42a45c2141531052775d47aa996d1a25f22fc71496bb39b558f0407a3',
 'small_readback_001.json':'e0ba0fe9cb63542605bf7eb84d58160839931b6742710f2c378bc5c2446c0dca'}
for name,digest in pins.items():assert sha(DEST/name)==digest,name
read=lambda p:json.loads(Path(p).read_bytes())
receipt=read(DEST/'receipt.json');outer=read(DEST/'external_application_wall.json');bounded=read(DEST/'bounded_execution.json')
review=read(PREP/'root_functional_review_002.json');plan=read(PREP/'plan.json')
assert receipt['status']=='functional_passed_synthetic_full_bytes' and receipt['identity_verified_on_exit'] is True
assert receipt['test_count']==159 and receipt['bad_tests']==[] and receipt['pytest_exit_code']==0
assert bounded['status']=='exited' and bounded['exitcode']==0 and bounded['windows_job_kill_on_close'] is True
assert outer['command']==review['command'] and outer['source_changed']==[] and outer['exit_code']==0
assert outer['outer_timeout'] is False and outer['exception'] is None
ticks,freq,wall=outer['elapsed_ticks'],outer['tick_frequency'],outer['whole_python_seconds']
assert type(ticks)is int and ticks>0 and type(freq)is int and freq>0 and 0<wall<=120 and abs(wall-ticks/freq)<=1e-9
for key in ('plan','runner','wrapper','root_review'):assert sha(outer[key]['path'])==outer[key]['sha256']
assert outer['output_sha256']=={n:pins[n] for n in ('receipt.json','bounded_execution.json','tests.xml','byte_probe.json')}
for name,digest in plan['source_sha256'].items():assert sha(ROOT/name)==digest==sha(PREP/'source'/name)
binary=receipt['binary'];assert sha(binary['path'])==binary['sha256']==sha(binary['archive'])=='a690ba550c49cd437afbeb2286e6a2082213ce44d3f1f64840e1b9d41f68a809'
actual=receipt['actual_extension'];assert actual['loader_type']=='ExtensionFileLoader'
assert all(Path(actual[n]).resolve()==Path(binary['path']).resolve() for n in ('file','spec_origin','loader_path'))
assert actual['binary_sha256']==binary['sha256'] and actual['contract']['native_simulation_authority'] is False
for name,item in actual['actual_imported_DLL_files'].items():
    if 'path' in item:assert sha(item['path'])==item['sha256']
cases=ET.parse(DEST/'tests.xml').findall('.//testcase');assert len(cases)==159
assert not any(node.tag in ('failure','error','skipped') for row in cases for node in row)
probes=read(DEST/'byte_probe.json');counts=Counter(row['classification'] for row in probes)
assert len(probes)==136 and counts['direct_C_bytes']==126 and sum(counts.values())==136
assert receipt['direct_support']['direct_supported_count']==126 and receipt['direct_support']['fallback_count']==10
assert all(bytes.fromhex(row['expected_hex'])==bytes.fromhex(row['actual_hex']) for row in probes)
result={'schema':'g31.typed_C.functional_saved_root_review.v1','status':'accepted_synthetic_full_bytes',
 'review_script_sha256':sha(__file__),'evidence_sha256':pins,'test_count':159,'full_byte_pairs_verified':136,
 'classifications':dict(counts),'whole_python_seconds':wall,'source_current_and_archive_verified':16,
 'binary_sha256':binary['sha256'],'actual_extension_report':actual,
 'scope':['Independent saved-only review; root decoded and compared136 full byte pairs, checked159 XML tests and exact external clock/command/wrapper/source/output binding.','Actual extension origin/DLL loading belongs to the functional run; root rehashed saved actual DLL files and binary now, did not reload C or rehash full7779/3082 toolchain/runtime inventory.','126 direct C and10 original fallback are separate. No actual fixture speed, all-day or complete100ms claim. Failed old build001 remains.'],
 'native_calls':0,'model_calls':0,'new_extension_loads':0}
path=DEST/'root_saved_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'root_saved_review_sha256':sha(path),'classifications':dict(counts),'whole_python_seconds':wall}))
