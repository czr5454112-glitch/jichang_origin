"""Create one frozen owned synthetic wrapper; does not execute it."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[4]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
source=ROOT/'outputs/invoke_bsvp1.ps1'
assert sha(source)=='df61d6b4cbdde75b05826248ca1fc298833e57f8057bf21492e45ce6829aa159'
raw=source.read_text(encoding='utf8')
start=raw.index('$taskSources = [ordered]@{')
end=raw.index('\nfunction Task-Sha',start)
files=('scripts/experiments/g31_ics_circulation/live_obligation_online_initial_dispatch.py',
       'tests/test_g31_circulation_online_initial_dispatch.py',
       'scripts/experiments/g31_ics_circulation/run_online_initial_dispatch_pure.py',
       'scripts/experiments/g31_ics_circulation/run_bound_source_proof_pure.py')
block='$taskSources = [ordered]@{\n'+''.join("    '%s' = '%s'\n"%(n,sha(ROOT/n)) for n in files)+'}'
raw=raw[:start]+block+raw[end:]
raw=raw.replace('bsvp1','odp1').replace('run_bound_source_proof_v2_pure','run_online_initial_dispatch_pure')
raw=raw.replace('tests/test_g31_circulation_bound_source_proof_v2.py','tests/test_g31_circulation_online_initial_dispatch.py')
for before,after in (('-ne 25','-ne 24'),('exact25','exact24'),('passed25','passed24'),('Only25','Only24')):
    raw=raw.replace(before,after)
lines=raw.splitlines()
remove=('if ($taskPlan.fixture_module', 'if ($taskPlan.binder_v2_source_proof', 'if ($taskPlan.future_adapter_v2_source_proof')
removed=[line for line in lines if line.strip().startswith(remove)]
assert len(removed)==3
lines=[line for line in lines if line not in removed]
at=next(i for i,l in enumerate(lines) if "throw 'test domain'" in l)+1
lines.insert(at,"    if ($taskPlan.runner_source_proof.test_count -ne 24 -or $taskPlan.runner_source_proof.original_worker_and_main_code -cne $true -or $taskPlan.runner_source_proof.complete_private_namespace -cne $true -or $taskPlan.runner_source_proof.sticky_original_execution_monitor_unchanged -cne $true -or $taskPlan.runner_source_proof.initial_dispatch_only -cne $true) { throw 'online synthetic runner proof' }")
raw='\n'.join(lines)+'\n'
raw=raw.replace('g31.bound_source_proof.v2_pure_external.v1','g31.online_initial_dispatch.pure_external.v1')
old="Only24 v2 synthetic static-float and factory-lifecycle tests; original37 and driver15 are not repeated; producer monitor reports no original proof/model/native/custom C execution. External checks bind saved results, not a second test run."
assert old in raw
raw=raw.replace(old,'Only24 synthetic initial dispatch and failure-boundary tests; actual Transport code uses fake sessions. No real proof/model/native/custom C execution or complete request latency claim. External checks bind saved results, not a second test run.')
target=ROOT/'outputs/invoke_odp1.ps1'
if target.exists():
    failed=Path(__file__).with_name('odp1_preexecution_wrapper_broad_replace_error.ps1')
    with failed.open('xb') as f:f.write(target.read_bytes())
    assert sha(target)=='cdbf195489d6b74a6ad5f824928906648fd600036ef45ca2cafe46b9f314f717'
    target.unlink()
with target.open('x',encoding='utf8') as f:f.write(raw)
print({'wrapper':str(target),'sha256':sha(target),'sources':{n:sha(ROOT/n) for n in files}})
