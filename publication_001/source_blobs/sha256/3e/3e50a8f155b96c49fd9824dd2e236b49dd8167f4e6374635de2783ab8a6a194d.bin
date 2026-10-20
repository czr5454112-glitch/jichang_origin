"""Closed synthetic build/functional authority, never simulator authority.

Metadata checks do not load the extension. Actual measurement must call begin
and finish: both retain the original complete dependency checks. No previous
functional timing or synthetic result is a real-fixture performance result.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from . import planning_capture_v2_c_encoder as candidate_module
from . import run_planning_v2_c_encoder_gate_v3 as gate

ROOT,OUT=gate.old.ROOT,gate.old.OUT
PLAN=OUT/'planning_v2_C_encoder_gate_prepare_003/plan.json'
PLAN_SHA='d6912d695e36707dbba6bd7a0359e5ec6c6ed1a964323e99c4aae4fecf28579b'
BUILD=OUT/'planning_v2_C_encoder_build_002'
FUNCTIONAL=OUT/'planning_v2_C_encoder_functional_002'
PINS={
    PLAN:PLAN_SHA,
    BUILD/'receipt.json':'fb2c4ddfabfc0277da6f40d397ecba86e50c4a9cb9f67820ebd11f4346d56979',
    BUILD/'bounded_execution.json':'7fe746e399f43884a10581bb8394fe6689e6a6d71bec7993a6017270f5f3958c',
    BUILD/'external_application_wall.json':'c9ae7c89205f72c87734fc60d16a4e9b9c9d59a78031e047e20dbae2422aeaa4',
    FUNCTIONAL/'receipt.json':'3116ddf66830d8f3f70cb6dc6651a29ecf539bf328db4ae1e28906edc49212cd',
    FUNCTIONAL/'bounded_execution.json':'2629c9c4ca7af41c05b89582873babc8c2afe35cad3c7f377715c94b5608edd0',
    FUNCTIONAL/'external_application_wall.json':'50709239e57767b579b79f03235a0aa6d082b30487798b4f69eddf8002bedb32',
    FUNCTIONAL/'tests.xml':'d1cc3a6e6cd8ec08533626bd795a09fd1e17ff5be17d418cc7874ab8e35e3290',
    FUNCTIONAL/'byte_probe.json':'02158ae42a45c2141531052775d47aa996d1a25f22fc71496bb39b558f0407a3',
    FUNCTIONAL/'root_saved_review_001.json':'395d5f14dbbcb2b8d2b0d842fdaacd25075f86b42e2849a70125329a2c821521',
}
require,sha=gate.old.require,gate.old.sha


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))


def external_functional(value,receipt,bounded,review):
    require(value['schema']=='g31.planning_v2.C_encoder.functional_external_application_wall.v1','functional_external_schema')
    require(type(value['exit_code']) is int and value['exit_code']==0 and
        value['source_changed']==[] and value['outer_timeout'] is False and value['exception'] is None,
        'functional_external_success')
    ticks,frequency,wall=value['elapsed_ticks'],value['tick_frequency'],value['whole_python_seconds']
    require(type(ticks) is int and ticks>=0 and type(frequency) is int and frequency>0 and
        type(wall) in (int,float) and math.isfinite(wall) and 0<wall<=120 and
        abs(wall-ticks/frequency)<=1e-9,'functional_external_clock')
    require(value['command']==review['command'] and value['plan']=={'path':str(PLAN),'sha256':PLAN_SHA},'functional_command_plan')
    require(receipt['status']=='functional_passed_synthetic_full_bytes' and receipt['identity_verified_on_exit'] is True
        and type(receipt['test_count']) is int and receipt['test_count']==159
        and type(receipt['pytest_exit_code']) is int and receipt['pytest_exit_code']==0 and receipt['bad_tests']==[]
        and bounded['status']=='exited' and type(bounded['exitcode']) is int and bounded['exitcode']==0,
        'functional_success')
    require(type(receipt['direct_support']['direct_supported_count']) is int and receipt['direct_support']['direct_supported_count']==126
        and type(receipt['direct_support']['fallback_count']) is int and receipt['direct_support']['fallback_count']==10
        and receipt['direct_support']['fallback_is_not_direct_C_support'] is True,'functional_direct_denominators')


def metadata():
    for path,digest in PINS.items():require(sha(path)==digest,'C_authority_pin:'+str(path))
    plan=read(PLAN);build=read(BUILD/'receipt.json');functional=read(FUNCTIONAL/'receipt.json')
    ns=gate.namespace()
    ns['external_build_identity'](BUILD,PINS[BUILD/'external_application_wall.json'],PLAN,PLAN_SHA,plan)
    require(build['status']=='build_passed_unloaded' and build['identity_verified_on_exit'] is True
        and build['extension_loads']==0,'build_accepted')
    outer=read(FUNCTIONAL/'external_application_wall.json')
    for name in ('plan','runner','wrapper','root_review'):
        item=outer[name];require(type(item) is dict and set(item)=={'path','sha256'} and sha(item['path'])==item['sha256'],'functional_ref:'+name)
    external_functional(outer,functional,read(FUNCTIONAL/'bounded_execution.json'),read(outer['root_review']['path']))
    require(outer['runner']=={'path':str(Path(gate.__file__).resolve()),'sha256':plan['source_sha256'][Path(gate.__file__).relative_to(ROOT).as_posix()]},'functional_runner')
    require(outer['output_sha256']=={name:sha(FUNCTIONAL/name) for name in ('receipt.json','bounded_execution.json','tests.xml','byte_probe.json')},'functional_outputs')
    rows=ET.parse(FUNCTIONAL/'tests.xml').getroot().findall('.//testcase')
    require(len(rows)==159 and not any(c.tag in ('failure','error','skipped') for row in rows for c in row),'functional_XML')
    probes=read(FUNCTIONAL/'byte_probe.json')
    require(len(probes)==136 and len({p['label'] for p in probes})==136 and
        sum(p['classification']=='direct_C_bytes' for p in probes)==126 and
        sum(p['classification']=='original_fallback_not_C_support' for p in probes)==10 and
        all(bytes.fromhex(p['actual_hex'])==bytes.fromhex(p['expected_hex']) for p in probes),'functional_full_bytes')
    require(build['binary']==functional['binary'],'functional_binary_identity')
    binary=build['binary']
    require(sha(binary['path'])==sha(binary['archive'])==binary['sha256'],'binary_archive_identity')
    for name,digest in plan['source_sha256'].items():
        require(sha(ROOT/name)==sha(PLAN.parent/'source'/name)==digest,'C_source:'+name)
    return {'plan':plan,'build':build,'functional':functional}


def references():
    value=metadata()
    return {'files':{str(path):digest for path,digest in PINS.items()},'binary':value['build']['binary'],
        'synthetic_tests':159,'direct_C_probes':126,'fallback_probes':10,
        'toolchain_members':len(value['plan']['toolchain_sha256']),
        'runtime_members':len(value['plan']['runtime_sha256']),
        'no_extension_loaded_by_metadata':True}


def merged_sources(plan,source_hashes):
    result=dict(plan['source_sha256'])
    for name,digest in source_hashes.items():
        require(name not in result or result[name]==digest,'source_union_conflict:'+name)
        result[name]=digest
    return {**plan,'source_sha256':result}


def begin(source_hashes):
    proof=metadata();ns=gate.namespace();plan=ns['verify_plan'](PLAN,PLAN_SHA)
    candidate=candidate_module.load_candidate(proof['build']['binary']['path'],
        proof['build']['binary']['sha256'],candidate_module.source_proof())
    actual=ns['actual_extension_identity'](candidate,Path(proof['build']['binary']['path']),
        proof['build']['binary']['sha256'],proof['build']['imported_DLLs'],plan)
    require(actual==proof['functional']['actual_extension'],'loaded_C_identity_changed')
    loaded=ns['loaded_sources'](merged_sources(plan,source_hashes))
    return candidate,{'actual_extension':actual,'loaded_entry':loaded,
        'complete_toolchain_and_runtime_entry_check':True}


def finish(candidate,source_hashes):
    proof=metadata();ns=gate.namespace();plan=ns['verify_plan'](PLAN,PLAN_SHA)
    actual=ns['actual_extension_identity'](candidate,Path(proof['build']['binary']['path']),
        proof['build']['binary']['sha256'],proof['build']['imported_DLLs'],plan)
    require(actual==proof['functional']['actual_extension'],'exit_C_identity_changed')
    return {'actual_extension':actual,'loaded_exit':ns['loaded_sources'](merged_sources(plan,source_hashes)),
        'complete_toolchain_and_runtime_exit_check':True}
