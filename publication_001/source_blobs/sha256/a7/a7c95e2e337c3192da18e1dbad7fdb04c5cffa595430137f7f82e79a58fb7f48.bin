"""Canonical source-only preparation, superseding invalid archive001.

Legacy absolute source identities are read-only inputs. Every new source key is
ROOT-relative POSIX, and every archive target is proved within output/source
before any source bytes are written. Runtime core sources are unchanged.
"""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path,PurePosixPath,PureWindowsPath
import sys
import xml.etree.ElementTree as ET
from . import prepare_live_owned_initial_runtime as old
from . import initial_owner_route_image as image

ROOT,OUT=old.ROOT,old.OUT
MODULE=__package__+'.prepare_live_owned_initial_runtime_v2'
PURE=OUT/'live_owned_initial_runtime_pure_002'
TESTS=(*old.TESTS,'tests/test_g31_circulation_owned_runtime_archive_v2.py')
EXPECTED_TESTS=71
sha,read,write,ref=old.sha,old.read,old.write,old.ref
require=old.require


def canonical_source(root,name):
    """Read identity only; absolute legacy paths never become output keys."""
    require(type(name) is str and name and '\x00' not in name,'source_name_type')
    win=PureWindowsPath(name)
    require(not win.drive or win.is_absolute(),'drive_relative_source')
    require('..' not in win.parts and '..' not in PurePosixPath(name).parts,'parent_source_component')
    root=Path(root).resolve();path=Path(name)
    path=(path if path.is_absolute() else root/path).resolve()
    require(path.is_relative_to(root) and path!=root,'source_outside_root')
    key=path.relative_to(root).as_posix()
    require(path.suffix=='.py' and key and ':' not in key and '\\' not in key,'python_canonical_key')
    return key,path


def merge_sources(root,entries):
    """Aliases merge only after resolving to the same source and same bytes."""
    result={};identities={}
    for name,data in entries:
        require(type(data) is bytes,'source_bytes')
        key,path=canonical_source(root,name);identity=os.path.normcase(str(path))
        prior=identities.get(identity)
        if prior is not None:
            require(result[prior]==data,'source_alias_content_conflict');continue
        require(key not in result or result[key]==data,'source_key_content_conflict')
        identities[identity]=key;result[key]=data
    return dict(sorted(result.items()))


def canonical_archive_target(output,name):
    require(type(name) is str and name and '\\' not in name and ':' not in name,'archive_key_form')
    pure=PurePosixPath(name)
    require(not pure.is_absolute() and str(pure)==name and all(part not in ('.','..') for part in pure.parts)
        and pure.suffix=='.py','archive_key_relative_canonical')
    output=Path(output).resolve();base=(output/'source').resolve();target=(base/Path(*pure.parts)).resolve()
    require(base.is_relative_to(output) and target.is_relative_to(base) and target!=base,'archive_containment')
    return target


def archive_sources(root,output,files):
    """Validate the complete destination set before any mkdir/write operation."""
    root=Path(root).resolve();output=Path(output).resolve();targets={}
    require(type(files) is dict and files,'nonempty_source_dictionary')
    for name,data in files.items():
        key,source=canonical_source(root,name)
        require(name==key and type(data) is bytes,'canonical_archive_source')
        target=canonical_archive_target(output,name)
        require(target!=source,'archive_must_not_be_current_source')
        require(target not in targets.values(),'archive_alias_collision')
        targets[name]=target
    for name,target in targets.items():
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(files[name])
    return {name:target.relative_to(output).as_posix() for name,target in targets.items()}


def verify_archive(root,output,plan):
    pins=plan['source_sha256'];mapping=plan['source_archive']
    require(type(pins) is dict and set(pins)==set(mapping),'archive_pin_domain')
    for name,digest in pins.items():
        key,path=canonical_source(root,name);target=canonical_archive_target(output,name)
        require(name==key and mapping[name]==target.relative_to(Path(output).resolve()).as_posix(),'archive_exact_mapping')
        require(sha(path)==digest and sha(target)==digest,'source_and_archive_bytes:'+name)


def source_gate():
    # The older gate only reads the independently valid162/180 predecessors;
    # it does not consume the invalid336-source archive or its pass labels.
    return old.source_gate()


def source_files():
    entries=[]
    for name,digest in read(old.V2/'plan.json')['source_sha256'].items():
        _,path=canonical_source(ROOT,name);data=path.read_bytes()
        require(hashlib.sha256(data).hexdigest()==digest,'legacy_source_identity');entries.append((name,data))
    modules=[MODULE,__package__+'.run_live_owned_initial_runtime_pure_v2',
        __package__+'.live_obligation_owned_prefix_evaluator',__package__+'.live_obligation_owned_initial_provider',
        __package__+'.live_obligation_owned_same_information_search',
        'tests.test_g31_circulation_owned_initial_runtime','tests.test_g31_circulation_owned_runtime_archive_v2',
        'tests.test_g31_circulation_future_later_paired_driver','tests.test_g31_circulation_live_initial_decision_seam',
        'tests.test_g31_circulation_future_later_fork']
    entries.extend(image.source_closure(ROOT,modules).items())
    return merge_sources(ROOT,entries)


def pure_gate():
    receipt=read(PURE/'receipt.json');bounded=read(PURE/'bounded_parent_receipt.json')
    cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['tests']==EXPECTED_TESTS and receipt['source_changed']==[],'pure_receipt_v2')
    require(len(cases)==EXPECTED_TESTS and not any(n.tag in ('failure','error','skipped') for r in cases for n in r),'pure_cases_v2')
    require(sha(PURE/'tests.xml')==receipt['XML_sha256'] and bounded['status']=='passed'
        and bounded['receipt_sha256']==sha(PURE/'receipt.json'),'pure_closed_v2')
    verify_archive(ROOT,PURE,read(PURE/'plan.json'))
    return {name:ref(PURE/name) for name in ('plan.json','receipt.json','tests.xml','bounded_parent_receipt.json','external_application_wall.json')}


def prepare(output):
    from . import live_obligation_owned_same_information_search as search
    prior=source_gate();pure=pure_gate();proof=search.source_proof();files=source_files()
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    mapping=archive_sources(ROOT,output,files)
    plan={'schema':'g31.owned_initial_runtime.source_preparation.v2','status':'pure_source_only_real_runtime_unexecuted',
        'source_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()},'source_archive':mapping,
        'prior_evidence':prior,'focused_pure':pure,'source_proof':proof,'tests':list(TESTS),'expected_tests':EXPECTED_TESTS,
        'environment':{'python':sys.executable,'sha256':sha(sys.executable)},
        'retained_obligations':{'candidate_denominator':32,'initial_contexts':16,'full_graph_clones':32,
            'future_source_inventory_calls':65,'original_cut_calls':80,'v2_actual_revalidation':True},
        'superseded_invalid_archive':{'plan':ref(OUT/'live_owned_initial_runtime_source_prepare_001/plan.json'),
            'pure_receipt':ref(OUT/'live_owned_initial_runtime_pure_001/receipt.json'),
            'reason':'Absolute predecessor source keys were combined with relative keys, and output/source/absolute discarded the archive root. Prior47 test assertions passed but the336 closure/archive claim is invalid. Originals retained without promotion.'},
        'canonical_source_keys':'ROOT-relative as_posix; legacy absolute identities are read-only; duplicate paths require identical bytes.',
        'archive_checked_before_write':True,'current_source_writes':False,
        'next_gate':'Separate unchanged96 prediction+retained semantic point/terminal comparison; no fabricated graph flags.',
        'limits':['Only private closed serial construction ownership; no arbitrary tamper resistance.',
            'No new scoped-input/owned-bundle/source-inventory cache; all dynamic checks and32 fullgraph clones remain.',
            'Pure source tests only; no native/model/C or full96 execution; no complete-request100ms/protection claim.'],
        'native_calls':0,'real_model_predictions':0,'actual_C_loads':0,'actual_fixture_decodes':0}
    verify_archive(ROOT,output,plan);write(output/'plan.json',plan)
    # Re-read exact serialized plan before declaring source readiness.
    verify_archive(ROOT,output,read(output/'plan.json'))
    write(output/'ready.json',{'status':plan['status'],'plan':ref(output/'plan.json'),'source_count':len(files),
        'tests':EXPECTED_TESTS,'actual_dispatch_ready':False,'native_calls':0,'real_model_predictions':0})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.resolve());return 0


if __name__=='__main__':raise SystemExit(main())
