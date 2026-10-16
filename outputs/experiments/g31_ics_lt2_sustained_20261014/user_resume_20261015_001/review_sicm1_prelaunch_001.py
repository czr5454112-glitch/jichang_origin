"""Saved-only prelaunch binding review; no project/native/model imports."""
import hashlib
import json
from pathlib import Path
import time
START=time.perf_counter()
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/sicm1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def require(ok,why):
    if not ok:raise ValueError('sicm1_root:'+why)
pins={
 'campaign.json':'8aa7f63c50310532fa97b0b6251ec118aeae247ff6b072ddbc73edb7f9d3018e',
 'source_preparation.json':'8491ae7eea188e86e76c499e961ed446faf538bb7c46e5fd19da816fd38e4ce2',
 'metadata_source_binding.json':'f4bf536c67baaf14d3aa28cd8a5b900f1428bdcbd5575085de0ed9f51ddd1c43',
 'external_application_wall.json':'66b4a52fd1864a33eaf8dd80e239720ccf048d4e91fbb3c5d5d8911073aa9c98',
 'submission_ready_001.json':'14ab16ee5f740005a3d302761a40661ecc99e6ec391c3f1de401782b31729e9d'}
for name,digest in pins.items():require(sha(OUT/name)==digest,'pin:'+name)
p,s,b,e=map(read,(OUT/'campaign.json',OUT/'source_preparation.json',OUT/'metadata_source_binding.json',OUT/'external_application_wall.json'))
require(sha(ROOT/'outputs/sicm1.metadata_parent.json')=='8c7dc5bc734c2962630a2829023c0fc76051b055219acb5809f9a6456b8d9a8b','parent_pin')
parent=read(ROOT/'outputs/sicm1.metadata_parent.json')
py='C:\\PROGRAMING\\python3.11.9\\python.exe'
module='scripts.experiments.g31_ics_circulation.run_static_inventory_campaign_prepare'
command=[py,'-m',module,'--output',str(OUT),'--pure-directory',str(ROOT/'outputs/sicp1')]
require(e['command']==command and e['cwd']==str(ROOT) and e['output_directory']==str(OUT),'metadata_command')
require(e['status']=='exited_zero' and type(e['exitcode']) is int and e['exitcode']==0
    and type(e['wrapper_exitcode']) is int and e['wrapper_exitcode']==0 and e['exception'] is None
    and e['fixed_entry_passed'] is True and e['fixed_exit_passed'] is True,'metadata_status')
f,t=e['stopwatch_frequency'],e['elapsed_ticks']
require(type(f) is int and f>0 and type(t) is int and 0<=t<=120*f
    and e['external_application_seconds']==t/f and e['shared_seconds']==120,'metadata_full120')
require(parent['status']=='passed' and parent['error'] is None and parent['shared_seconds']==120
    and parent['process']['status']=='exited' and type(parent['process']['exitcode']) is int
    and parent['process']['exitcode']==0 and parent['process']['windows_job_kill_on_close'] is True
    and parent['process']['child_released_only_after_job_assignment'] is True,'owned_metadata')
require(parent['command'][:len(command)]==command and parent['command'][len(command):-1]==['--worker','--admission'],'owned_command')
require(e['environment']=={'PYTHONPATH':'src;.;tests','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONIOENCODING':'utf-8'},'environment')
require(sha(py)==e['python_sha256']==e['python_after_sha256']=='5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec','interpreter')
for kind in ('wrapper','runner'):
    require(sha(e[kind]['path'])==e[kind]['sha256']==e[kind+'_after_sha256'],'metadata_'+kind)
for row in e['fixed_source_and_evidence_pins'].values():
    require(row['entry_matches'] is True and row['exit_matches'] is True
        and sha(row['path'])==row['expected_sha256']==row['entry_sha256']==row['exit_sha256'],'fixed_entry_exit')
for name,row in e['outputs'].items():
    if row is None:require(name=='preparation_failure.json' and not (OUT/name).exists(),'missing_output')
    else:require(sha(row['path'])==row['sha256'],'metadata_output:'+name)
require(p['schema']=='g31.initial_single_capture.static_inventory_campaign.v1'
    and p['status']=='prepared_for_root_review_no_execution' and p['hard_timeout_seconds']==600
    and p['native_branch_budget']==18 and p['max_native_workers']==1,'campaign_scope')
require(s['campaign']==b['campaign']=={'path':str(OUT/'campaign.json'),'sha256':pins['campaign.json']}
    and s['not_dispatched'] is True and s['focused_synthetic_tests']==54,'prepare_reference')
require(b['original_prepare_code_defaults_closure_retained'] is True
    and b['only_prepare_global_rebinding']=='source_files','private_metadata_rebinding')
for row in b['pure_evidence'].values():require(sha(row['path'])==row['sha256'],'pure_reference')
oldref=p['frozen_owned_C18_campaign']
require(sha(oldref['path'])==oldref['sha256']=='4ac4569ad5145ccf62e83a39d29ad238077bf00fa0657c130fb12916cfb91bdc','original_plan')
old=read(oldref['path'])
same=('rows','row_order','input_file_sha256','native_contract_reference','native_binary','image','C_provider',
      'hard_timeout_seconds','max_native_workers','native_branch_budget','participation_contract','participation_contract_sha256')
for key in same:require(p[key]==old[key],'same_original_contract:'+key)
require(len(p['source_sha256'])==232 and set(p['source_sha256'])==set(p['source_archive']),'source_domain232')
seen=set();maximum=0
for name,digest in p['source_sha256'].items():
    current=(ROOT/name).resolve();saved=(OUT/p['source_archive'][name]).resolve()
    require(not Path(name).is_absolute() and Path(name).as_posix()==name and '..' not in Path(name).parts
        and p['source_archive'][name]=='source/'+name,'canonical_source')
    require(current.is_relative_to(ROOT) and saved.is_relative_to(OUT/'source') and current!=saved
        and saved not in seen and len(str(saved))<260,'independent_archive')
    seen.add(saved);maximum=max(maximum,len(str(saved)))
    require(sha(current)==sha(saved)==digest,'current_archive:'+name)
require(len(p['compiled_source_archive_sha256'])==67,'compiled67')
for path,digest in p['compiled_source_archive_sha256'].items():require(sha(path)==digest,'native_archive')
require(sha(p['native_binary']['path'])==p['native_binary']['sha256']=='845486b745bc6e65a9988d1ef5429336b60fd472eb73c39e133e19ec93a7e7be','native027')
ledger=read(OUT/'branch_ledger.json')
require(len(p['row_order'])==len(set(p['row_order']))==18 and set(ledger)==set(p['row_order']),'18denominator')
for key in p['row_order']:
    require(sha(OUT/'inputs'/(key+'.json'))==p['input_file_sha256'][key],'input:'+key)
    require(ledger[key]=={**p['rows'][key],'status':'unknown_unexecuted'},'unexecuted_row')
for name in ('execution_claim.json','worker_claim.json','receipt.json','verification.json','external_launch_receipt.json',
             'C_provider_lifetime.json','static_inventory_lifetime.json','actual_external_application_wall.json'):
    require(not (OUT/name).exists(),'actual_not_dispatched:'+name)
wrapper=ROOT/'outputs/invoke_sicm1_actual_001.ps1'
require(sha(wrapper)=='cd06e16b5f7ad4f24ac42d4f4d4ed8f773bc092434a729bbd5fed8bdb12191a5','actual_wrapper_source_reviewed')
record={'schema':'g31.static_inventory_campaign.root_prelaunch_review.v1',
    'status':'saved_preparation_bindings_verified_actual_unexecuted','pins':pins,
    'sources':232,'native_archive':67,'inputs':18,'maximum_archive_path':maximum,
    'same_original_contract_fields':list(same),'metadata_whole_seconds':t/f,
    'actual_wrapper':{'path':str(wrapper),'sha256':sha(wrapper)},'execute_command':s['execute_command'],
    'source_review_complete':True,'project_imports':0,'native_model_C_calls':0,
    'C6124_scope':'Prepared C metadata matches the accepted original. This independent saved review does not repeat6124 checks; actual entry, exit and saved verifier must charge all three.',
    'complete100ms_or_joint_or_all_day_certificate':False,'saved_review_seconds':time.perf_counter()-START}
target=OUT/'root_prelaunch_review_001.json'
with target.open('x',encoding='utf8') as stream:json.dump(record,stream,indent=2);stream.write('\n')
print(json.dumps({'path':str(target),'sha256':sha(target),'sources':232,'metadata_whole_seconds':t/f}))
