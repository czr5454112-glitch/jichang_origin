"""Source/pure preparation only for the separate owned full32 runtime."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from . import prepare_live_initial_decision_seam as old
from . import initial_owner_route_image as image

ROOT,OUT=old.ROOT,old.OUT
MODULE=__package__+'.prepare_live_owned_initial_runtime'
PURE=OUT/'live_owned_initial_runtime_pure_001'
V2=OUT/'live_initial_six_seam_v2_prepare_001'
V2_PLAN='e555fe2ac3b74a87e8bfc5e246b2dc62ef61546a5c6f1b6aca7661e23651d0de'
V2_RECEIPT='85149c5a3535b59835304e8f32d550616abc9eafe7e639c587280e82055f4750'
TESTS=('tests/test_g31_circulation_owned_initial_runtime.py',)
EXPECTED_TESTS=47
sha,read,write,ref=old.sha,old.read,old.write,old.ref


def require(ok,reason):
    if not ok:raise ValueError('owned_initial_prepare:'+reason)


def source_gate():
    original=old.previous_gate()
    require(sha(V2/'plan.json')==V2_PLAN and sha(V2/'receipt.json')==V2_RECEIPT,'v2_evidence_identity')
    plan=read(V2/'plan.json');receipt=read(V2/'receipt.json')
    require(len(plan['source_sha256'])==180 and receipt['status']=='six_actual_initial_seams_validated'
        and receipt['known_initial_domains']==6 and receipt['unknown_initial_domains']==0
        and receipt['source_changed']==[] and receipt['run_acceptance_status']=='closed_run_acceptance_passed',
        'v2_initial_actual_scope')
    for name,digest in plan['source_sha256'].items():
        require(sha(ROOT/name)==digest and sha(V2/plan['source_archive'][name])==digest,'v2_source:'+name)
    return {'original_diagnostic':original,'actual_v2_plan':ref(V2/'plan.json'),'actual_v2_receipt':ref(V2/'receipt.json'),
        'scope':'Prior source and initial schema/authority conformance only; no past target or outcome enters this new provider.'}


def source_files():
    files={name:(ROOT/name).read_bytes() for name in read(V2/'plan.json')['source_sha256']}
    entries=[MODULE,__package__+'.run_live_owned_initial_runtime_pure',
        __package__+'.live_obligation_owned_prefix_evaluator',__package__+'.live_obligation_owned_initial_provider',
        __package__+'.live_obligation_owned_same_information_search',
        'tests.test_g31_circulation_owned_initial_runtime',
        # Pytest helpers use bare module imports; list exact qualified source
        # entries rather than assuming conservative AST discovery finds them.
        'tests.test_g31_circulation_future_later_paired_driver',
        'tests.test_g31_circulation_live_initial_decision_seam',
        'tests.test_g31_circulation_future_later_fork']
    for name,data in image.source_closure(ROOT,entries).items():
        require(name not in files or files[name]==data,'source_conflict:'+name);files[name]=data
    return dict(sorted(files.items()))


def pure_gate():
    receipt=read(PURE/'receipt.json');bounded=read(PURE/'bounded_parent_receipt.json')
    cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['tests']==EXPECTED_TESTS and receipt['source_changed']==[],'pure_receipt')
    require(len(cases)==EXPECTED_TESTS and not any(n.tag in ('failure','error','skipped') for r in cases for n in r),'pure_cases')
    require(sha(PURE/'tests.xml')==receipt['XML_sha256'] and bounded['status']=='passed'
        and bounded['receipt_sha256']==sha(PURE/'receipt.json'),'pure_bounded')
    for name,digest in receipt['source_sha256'].items():
        require(sha(ROOT/name)==digest and sha(PURE/'source'/name)==digest,'tested_source:'+name)
    return {name:ref(PURE/name) for name in ('plan.json','receipt.json','tests.xml','bounded_parent_receipt.json','external_application_wall.json')}


def prepare(output):
    from . import live_obligation_owned_same_information_search as search
    prior=source_gate();pure=pure_gate();proof=search.source_proof();files=source_files()
    output.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    plan={'schema':'g31.owned_initial_runtime.source_preparation.v1','status':'pure_source_only_real_runtime_unexecuted',
        'source_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
        'source_archive':{name:'source/'+name for name in files},'prior_evidence':prior,'focused_pure':pure,
        'source_proof':proof,'tests':list(TESTS),'expected_tests':EXPECTED_TESTS,
        'environment':{'python':sys.executable,'sha256':sha(sys.executable)},
        'retained_obligations':{'candidate_denominator':32,'initial_contexts':16,'full_graph_clones':32,
            'future_source_inventory_calls':65,'original_cut_calls':80,
            'same_information_selectors':list(search.METHODS),'v2_actual_revalidation':True},
        'changed_scope':'Only diagnostic graph encodings/walks/action-graph comparisons/completed mutation probes removed. Private factories retain all actual context/cut/owner/ACK/wire guards, source inventories and output saves.',
        'next_gate':'Separately preregister all96 complete predictions and semantic point/chronology comparisons to frozen diagnostic path; never synthesize removed graph flags. All construction/source/clone/guard/output costs charged.',
        'limits':['Closed serial construction ownership, not arbitrary private-state tamper detection.',
            'Synthetic fake-origin/real guard+fork tests are not actual model or native acceptance.',
            'No scope/context/source-inventory optimization added. Owned-bundle candidate is not used.',
            'No native protection, general hidden-state coverage, method advantage or complete-request100ms certificate.'],
        'native_calls':0,'real_model_predictions':0,'actual_C_loads':0,'actual_fixture_decodes':0}
    write(output/'plan.json',plan)
    write(output/'ready.json',{'status':plan['status'],'plan':ref(output/'plan.json'),'source_count':len(files),
        'tests':EXPECTED_TESTS,'actual_dispatch_ready':False,'native_calls':0,'real_model_predictions':0})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.resolve());return 0


if __name__=='__main__':raise SystemExit(main())
