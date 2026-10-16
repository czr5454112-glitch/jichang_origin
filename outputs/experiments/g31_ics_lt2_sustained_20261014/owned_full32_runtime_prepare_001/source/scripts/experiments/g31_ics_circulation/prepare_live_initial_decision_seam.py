"""Source-only initial delivered decision seam preparation; no native/model run."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from . import validate_full32_future_suffix as prior
from . import initial_owner_route_image as image

ROOT,OUT=prior.ROOT,prior.OUT
MODULE=__package__+'.prepare_live_initial_decision_seam'
PURE=OUT/'live_initial_decision_seam_pure_001'
FROZEN=OUT/'full32_future_suffix_prepare_001'
TESTS=('tests/test_g31_circulation_live_initial_decision_seam.py',)
EXPECTED_TESTS=47
sha,read,write,ref=prior.sha,prior.read,prior.write,prior.ref


def require(ok,reason):
    if not ok:raise ValueError('initial_seam_prepare:'+reason)


def source_files():
    files=prior.source_files()
    entries=[MODULE,__package__+'.run_live_initial_decision_seam_pure',
        __package__+'.live_obligation_initial_decision_adapter',
        __package__+'.live_obligation_initial_candidate_provider',
        __package__+'.live_obligation_same_information_search',
        'tests.test_g31_circulation_live_initial_decision_seam']
    for name,data in image.source_closure(ROOT,entries).items():
        require(name not in files or files[name]==data,'source_conflict');files[name]=data
    return dict(sorted(files.items()))


def previous_gate():
    plan=read(FROZEN/'plan.json');receipt=read(FROZEN/'receipt.json')
    require(sha(FROZEN/'plan.json')=='c48367f67be44aea409369d72f632228d28839fe1580fcda6bdacdabbdf7d811','original_plan')
    require(len(plan['source_sha256'])==162,'original_source_count')
    for name,digest in plan['source_sha256'].items():
        require(sha(ROOT/name)==digest and sha(FROZEN/plan['source_archive'][name])==digest,'original_source:'+name)
    require(receipt['status']=='exact_full96_future_suffixes' and receipt['exact_rows']==96
        and receipt['unknown_rows']==0 and receipt['source_changed']==[],'original_conformance')
    # Prior evidence is a source/implementation regression reference only. Its
    # inputs and outcomes are never loaded by the new online provider.
    return {'plan':ref(FROZEN/'plan.json'),'receipt':ref(FROZEN/'receipt.json'),
        'source_count':162,'scope':'Historical implementation conformance, not current native authority or an online input.'}


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
    previous=previous_gate();pure=pure_gate();files=source_files()
    output.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    plan={'schema':'g31.live_initial_decision_seam.source_preparation.v1',
        'status':'source_pure_only_actual_input_seam_unexecuted',
        'source_sha256':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()},
        'source_archive':{n:'source/'+n for n in files},'previous_frozen':previous,'focused_pure':pure,
        'tests':list(TESTS),'expected_tests':EXPECTED_TESTS,
        'environment':{'python':sys.executable,'sha256':sha(sys.executable)},
        'layers':{'actual_adapter':'Same exact LocalTransport/session/admission, immutable own publication, own three endpoints, NativeJobLedger and current revalidation.',
            'provider':'Same32 original Cartesian actions;16 fresh guarded contexts and prefixes plus32 suffixes; full provider cost charged to every method.',
            'selection':'Public preregistered incumbent; strict all-five forecast comparison; coordinate can internally visit unprotected proposals; full unknown denominator.',
            'dispatch':'No dispatcher installed. Fresh owner-local proposal still does not authorize submission.'},
        'limitations':['All actual-origin primitives in these unit fixtures are faked. No actual supplied context or real model was evaluated.',
            'Finite model forecasts are conditional estimates, not robust hidden-state coverage or native protection.',
            'No demonstrated joint-search superiority. No complete-request100ms certificate.',
            'Unchanged native initial collector may omit an already-read endpoint prefix on exception; a later complete-request campaign must retain it or explicitly remain unknown.',
            'The proposed next six actual collections require a separate fixed plan, runtime acceptance, owner scope and failure-prefix evidence; this preparation authorizes no execution.'],
        'native_calls':0,'real_model_predictions':0,'actual_fixture_decodes':0,'actual_C_loads':0}
    write(output/'plan.json',plan)
    write(output/'ready.json',{'status':plan['status'],'plan':ref(output/'plan.json'),'source_count':len(files),
        'tests':EXPECTED_TESTS,'actual_dispatch_ready':False,'native_calls':0,'real_model_predictions':0})


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    prepare(a.output.resolve());return 0


if __name__=='__main__':raise SystemExit(main())
