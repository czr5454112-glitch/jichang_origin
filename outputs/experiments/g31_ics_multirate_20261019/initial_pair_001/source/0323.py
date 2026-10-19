"""Archive a source-only bridge prototype; deliberately no execution mode."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
from . import cooperative_bridge_policy as policy

ROOT, OUT = policy.base.ROOT, policy.base.OUT


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def reference(path): return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def require(ok,why):
    if not ok: raise ValueError('bridge_prepare:'+why)


def same_json_structure(left,right):
    """Tuple/list normalize only at the persisted JSON boundary; preserve order."""
    encode=lambda value:json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))
    return encode(left)==encode(right)


def source_paths():
    seeds=[Path(__file__),Path(policy.__file__),
        ROOT/'tests/test_g31_circulation_cooperative_bridge_policy.py',
        ROOT/'tests/test_g31_circulation_current_possession_permit.py',
        ROOT/'tests/test_g31_circulation_bridge_prepare.py']
    pending=list(seeds);found=set()
    def enqueue(target):
        for path in (target.with_suffix('.py'),target/'__init__.py'):
            if path.is_file() and path.resolve().is_relative_to(ROOT):
                pending.append(path)
                for parent in path.parents:
                    if parent==ROOT:break
                    if (parent/'__init__.py').is_file():pending.append(parent/'__init__.py')
    while pending:
        path=pending.pop().resolve()
        if path in found:continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node,ast.ImportFrom):
                for prefix in ([path.parent] if node.level else [ROOT,ROOT/'src',ROOT/'tests']):
                    for _ in range(max(0,node.level-1)):prefix=prefix.parent
                    if node.module:prefix=prefix.joinpath(*node.module.split('.'));enqueue(prefix)
                    for alias in node.names:
                        if alias.name!='*':enqueue(prefix/alias.name)
            elif isinstance(node,ast.Import):
                for alias in node.names:
                    for prefix in (ROOT,ROOT/'src'):enqueue(prefix.joinpath(*alias.name.split('.')))
    return sorted(found)


def prepare(output,tests_xml):
    require(not output.exists(),'immutable_output')
    prior=OUT/'original_low_wip_prepare_005';plan=policy.base.read(prior/'preregistered_protocol.json')
    policy.base.verify_pins(prior,plan)
    require(sha(policy.base.__file__)==policy.reuse.BASE_SHA,'frozen005_source')
    data=policy.base.gzread(prior/'input.json.gz')
    require(len(data['jobs'])==28506 and len(data['trays'])==22
        and all(not j.get('allow_suffix_reroute',False) for j in data['jobs'])
        and not data['faults'] and not data['transfers'],'original_domain')
    public={k:data[k] for k in ('node_records','node_contracts','edge_records','edge_contracts')}
    require(same_json_structure(policy.base.parking_plan(public,data['trays']),plan['parking_plan']),'same_original_parking')
    suites=list(ET.parse(tests_xml).getroot().iter('testsuite'))
    counts={key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
    require(counts['tests']>=72 and all(counts[k]==0 for k in ('failures','errors','skipped')),'pure_tests')
    paths=source_paths();pins={str(p):sha(p) for p in paths}
    loaded={str(Path(m.__file__).resolve()) for m in list(sys.modules.values()) if getattr(m,'__file__',None)
        and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
    require(loaded<=set(pins),'actual_loaded_closure')
    output.mkdir(parents=True)
    for path in paths:
        target=output/'source_archive'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    shutil.copyfile(prior/'input.json.gz',output/'input.json.gz')
    for rel,digest in plan['compiled_source_sha256'].items():
        source=prior/'compiled_source_archive'/rel;require(sha(source)==digest,'compiled_archive')
        target=output/'compiled_source_archive'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    result={'schema':'g31.cooperative_bridge.source_only_plan.v1','status':'prepared_source_only_unexecuted',
        'policy':policy.scope(),'source_before':pins,'actual_loaded_repo_paths':sorted(loaded),
        'tests':{**reference(tests_xml),'counts':counts},'interpreter':reference(sys.executable),
        'input_sha256':plan['input_sha256'],'binary':plan['binary'],'binary_sha256':plan['binary_sha256'],
        'compiled_source_sha256':plan['compiled_source_sha256'],'authority_pins':plan['authority_pins'],
        'public_contract':public,'parking_plan':plan['parking_plan'],
        'reference005':reference(prior/'preregistered_protocol.json'),
        'existing_bound':reference(OUT/'original_carrier_bound_002/analysis.json.gz'),
        'gate_source_review':reference(OUT/'current_possession_permit_independent_source_review_001.json'),
        'compact_fifo_correction':{'actual_input':reference(OUT/'original_low_wip_third_prepare_001/api/013737.json.gz'),
            'actual_scope':'Native compact jobs is empty at20840 while current own projection has seven FIFO heads; complete contracts are joined from actual delivered own selfcopy.',
            'prior_tests':'pure002 full-jobs synthetic fixture did not exercise actual compact projection. pure003 retained one timestamp-fixture error causing34 failures. pure004 exactactual20840 binding passes all84.',
            'hypothetical_positive':'The actual compact own facts are retained; peer waitingjobs are explicitly mutated only in a pure bridge feasibility case, not claimed as delivered or executed.'},
        'execution_authorized':False,'execution_command':None,'native_executions':0,
        'unimplemented_acceptance':['Owned finite launcher and complete outer wall/cost accounting.',
            'Lossless whole API tape and independent exact policy replay.',
            'All28506 state accounting, actual LOAD/UNLOAD/HOLD and empty bridge receipts, every physical ACK and no other tray movement.',
            'Both actual fresh cap barriers plus delivered relay ACK; helper output alone is not a terminal certificate.',
            'Native physical/current source and receiver validations; graph screens cannot substitute for them.'],
        'checkpoint_contract':'Both consumed sets change in memory before submission. Explicit controller_checkpoint calls export them with current client state; no durable write-before-submit is implemented. Fresh trial only; no controller/native restoration API exists. Crash recovery remains unimplemented.',
        'failure_contract':'Global halt is experiment management after failure, not owner-visible consensus or online recovery. ReachedH with any failure remains unknown.',
        'comparison_contract':'Oldcap8 is prior evidence only, never a new same-policy performance or per-job protection comparison.'}
    policy.base.write(output/'preregistered_protocol.json',result)
    require(all(sha(p)==digest and sha(output/'source_archive'/Path(p).relative_to(ROOT))==digest for p,digest in pins.items()),'source_changed')
    receipt={'status':'prepared_source_only_unexecuted','plan':reference(output/'preregistered_protocol.json'),
        'source_count':len(pins),'compiled_source_count':len(plan['compiled_source_sha256']),
        'pure_counts':counts,'native_executions':0,'execution_ready':False,'source_changed':[]}
    policy.base.write(output/'prepare_receipt.json',receipt);return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--tests-xml',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.output.resolve(),args.tests_xml.resolve())))
