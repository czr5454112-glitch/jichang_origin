"""Explicit single-branch registration helper; never retries or batches natives."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
from scripts.experiments.g31_ics_circulation import run_sustained_learning as ledger

def main():
    p=argparse.ArgumentParser()
    for key in ('name','case','mode','contract'):
        p.add_argument('--'+key,required=True)
    p.add_argument('--selection',default='score')
    p.add_argument('--reference')
    p.add_argument('--model')
    a=p.parse_args();root=Path(__file__).resolve().parent;out=root/a.name
    module='scripts.experiments.g31_ics_circulation.foundation_repeated_campaign'
    command=[sys.executable,'-m',module,'--prepare','--case',a.case,'--mode',a.mode,
             '--selection',a.selection,'--output',str(out)]
    if a.reference: command+=['--reference',str(root/a.reference/'raw.json.gz')]
    if a.model: command+=['--model',str(root/a.model)]
    subprocess.run(command,check=True,cwd=ledger.ROOT)
    plan=ledger.read(out/'plan.json')
    sources=[*plan['source_sha256'],str(out/'plan.json'),str(root/a.contract),str(Path(__file__).resolve())]
    if a.model: sources.append(str(root/a.model))
    spec=dict(task_id=a.name,module=module,args=['--launch','--output',str(out)],
        native_branches=1,hard_seconds=180,sources=sources,requires=[a.reference] if a.reference else [],
        assessment={'path':str(out/'receipt.json'),'allowed_statuses':['completed_native_branch']},
        next_action='Inspect guarded current evidence, exact ACK/effect and every business result before promotion')
    ledger.write_new(root/(a.name+'_task.json'),spec)
    ledger.register(root/'manifest.json',spec)
    result=ledger.run_task(root/'manifest.json',a.name)
    print(json.dumps({'task':a.name,'status':result['status'],'process':result.get('process')}))
    return 0 if result['status']=='completed' else 1

if __name__=='__main__':
    raise SystemExit(main())
