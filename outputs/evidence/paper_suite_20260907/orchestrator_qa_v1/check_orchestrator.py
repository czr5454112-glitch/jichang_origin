"""SYNTHETIC QA: scheduler/identity fixtures only, no transport simulation."""
from pathlib import Path
import hashlib,json,subprocess,sys,threading,time,uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.eval import run_feng_paper_suite as m

OUT=Path(__file__).parent/uuid.uuid4().hex[:12]
OUT.mkdir(parents=True)
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
def reject(name,fn):
    try: fn()
    except (ValueError,FileExistsError): checks.append(name)
    else: raise AssertionError(name)

campaign=OUT/'campaign'
protocols=[]
for family in ('base','all_day_fault'):
    path=OUT/(family+'.md'); path.write_text('SYNTHETIC QA '+family)
    protocols.append(dict(path=str(path),sha256=m.sha(path),family=family))
cells=[]
for index,(method,map_name) in enumerate(((m.NEW_G31,'map2'),(m.HCA,'map2'),(m.DH,'nanning'),(m.TARAU,'nanning'))):
    spec=dict(method=method,map=map_name,load_factor=1.0,speed_mps=2.5,seed=104729,family='base',scenario_index=0,
              timing_policy='full_population_only',horizon_seconds=98259,protocol_path=protocols[0]['path'],protocol_sha256=protocols[0]['sha256'])
    path=OUT/f'spec_{index}.json'; m.write(path,spec)
    cell_id=f'qa_{index}'
    cells.append(dict(cell_id=cell_id,method=method,map=map_name,load_factor=1.0,speed_mps=2.5,seed=104729,family='base',scenario_index=0,
                      spec_path=str(path),spec_sha256=m.sha(path),runner_path=str(m.RUNNERS[method]),runner_sha256=m.sha(m.RUNNERS[method]),
                      output_dir=str(campaign/'cells'/cell_id)))
plan_path=OUT/'plan.json'; m.write(plan_path,dict(schema=m.PLAN_SCHEMA,status='FROZEN_SPECS_NOT_ALL_EXECUTED',result_root=str(campaign/'cells'),protocols=protocols,cells=cells))
plan=m.load_plan(plan_path)
check('cells-root-plan-and-fixed-runners',len(plan['cells'])==4)
check('map-method-filter',m.select_cells(plan,{'map':['map2'],'method':[m.HCA]})==[plan['cells'][1]])
check('preflight-limit-in-plan-order',m.select_cells(plan,{},2)==plan['cells'][:2])
reject('empty-selection-rejected',lambda:m.select_cells(plan,{'seed':[1]}))
bad=dict(cells[0],runner_path=str(ROOT/'scripts/eval/run_hca_paper_suite.py'))
reject('arbitrary-runner-refused',lambda:m.verify_bound_cell(bad))
bad=dict(cells[0],spec_sha256='0'*64)
reject('spec-byte-tamper-refused',lambda:m.verify_bound_cell(bad))
bad_plan=json.loads(plan_path.read_text());bad_plan['cells'][3].update(family='all_day_fault',scenario_index=1)
bad_path=OUT/'invalid-fault-plan.json';m.write(bad_path,bad_plan)
reject('tarau-fault-outside-final-scope-refused',lambda:m.load_plan(bad_path))

called=[]; guard=threading.Lock()
def fake_ok(cell,*args):
    with guard: called.append(cell['cell_id'])
    return dict(cell_id=cell['cell_id'],status='COMPLETE',full_population_complete=False)
with patch.object(m,'execute_cell',side_effect=fake_ok):
    result=m.run_plan(plan,plan['cells'],workers=2)
check('pool-executes-each-selected-cell-once',result['status']=='COMPLETE' and sorted(called)==sorted(c['cell_id'] for c in cells))
check('unfinished-population-is-valid-terminal',all(not c['full_population_complete'] for c in result['cells']))
called=[]
def fake_fail(cell,*args):
    called.append(cell['cell_id']);return dict(cell_id=cell['cell_id'],status='FAILED')
with patch.object(m,'execute_cell',side_effect=fake_fail):
    result=m.run_plan(plan,plan['cells'],workers=1)
check('failure-stops-additional-dispatch',called==[cells[0]['cell_id']] and len(result['not_started_cell_ids'])==3 and result['status']=='FAILED')
lock=campaign/'.paper_suite_orchestration.lock';lock.write_text('SYNTHETIC QA live lock')
try: reject('second-pool-refused',lambda:m.run_plan(plan,plan['cells']))
finally: lock.unlink()

cell=cells[0]; native=Path(cell['output_dir']);native.mkdir(parents=True)
(native/'partial.txt').write_text('preserve me')
with patch.object(m.subprocess,'Popen',side_effect=AssertionError('must not launch')):
    result=m.execute_cell(cell,OUT/'partial-refusal',0,threading.Event())
check('partial-evidence-refused-without-launch',result['status']=='FAILED' and (native/'partial.txt').read_text()=='preserve me')
(native/'normalized_result.json').write_text('{}')
with patch.object(m,'verify_cell',return_value={'full_population_complete':False}) as verify, patch.object(m.subprocess,'Popen',side_effect=AssertionError('must not launch')):
    result=m.execute_cell(cell,OUT/'reuse',0,threading.Event())
check('resume-calls-real-loader-interface-without-launch',result['status']=='REUSED_VERIFIED' and verify.call_count==1)

envelope=dict(status='COMPLETE',method=m.NEW_G31,map='map2',load_factor=1.0,seed=104729,spec={'speed_mps':2.5},population_audit={'status':'PASS','full_population_complete':False})
m.write(native/'normalized_result.json',envelope)
m.write(native/'runner_status.json',dict(status='COMPLETE',normalized_result_sha256=m.sha(native/'normalized_result.json')))
check('envelope-allows-horizon-unfinished-with-pass',m.check_result_envelope(cell)['full_population_complete'] is False)
envelope['population_audit']['status']='FAIL';m.write(native/'normalized_result.json',envelope)
m.write(native/'runner_status.json',dict(status='COMPLETE',normalized_result_sha256=m.sha(native/'normalized_result.json')))
reject('envelope-rejects-failed-population-gate',lambda:m.check_result_envelope(cell))

# A real harmless Python sleeper exercises confirmed OR explicitly refused
# child-tree timeout termination. Some sandbox hosts deny taskkill /T.
# It deliberately does not execute the supplied transport runner command.
timeout_cell=dict(cells[1],output_dir=str(campaign/'cells'/'qa_timeout'))
real_popen=subprocess.Popen; children=[]
def sleeper(command,**kwargs):
    child=real_popen([sys.executable,'-c','import time; print("SYNTHETIC QA sleeper",flush=True); time.sleep(2)'],**kwargs)
    children.append(child);return child
with patch.object(m.subprocess,'Popen',side_effect=sleeper):
    # taskkill itself uses subprocess.run->Popen, so avoid patch recursion by
    # delegating that command to the real constructor.
    def launched(command,**kwargs):
        return real_popen(command,**kwargs) if command[0]=='taskkill' else sleeper(command,**kwargs)
    with patch.object(m.subprocess,'Popen',side_effect=launched):
        result=m.execute_cell(timeout_cell,OUT/'timeout',.05,threading.Event())
confirmed=result['termination']['tree_termination_confirmed']
check('real-python-child-timeout-truthful',result['status']==('TIMED_OUT' if confirmed else 'TIMEOUT_TERMINATION_FAILED'))
for child in children: child.wait(timeout=5)
check('timeout-retains-log',b'SYNTHETIC QA sleeper' in (OUT/'timeout/stdout.txt').read_bytes())
with patch.object(m,'execute_cell',return_value=dict(cell_id=cells[0]['cell_id'],status='TIMEOUT_TERMINATION_FAILED',termination={'tree_termination_confirmed':False})):
    blocked=m.run_plan(plan,plan['cells'],workers=1,keep_going=True)
check('unconfirmed-tree-stop-retains-pool-lock',blocked['campaign_lock_retained'] and lock.exists() and len(blocked['not_started_cell_ids'])==3)
lock.unlink()  # Fixture-only lock; both harmless Python children have exited.

manifest=dict(scope=__doc__,status='PASS',check_count=len(checks),checks=checks,orchestrator_sha256=m.sha(Path(m.__file__)),
              fixture_source_sha256=m.sha(Path(__file__)),output=str(OUT))
m.write(OUT/'verification.json',manifest)
print(json.dumps(manifest,ensure_ascii=False))
