"""Owned120 saved-verifier synthetic gate; no actual fixtures/native/models."""
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job as bounded
from . import initial_owner_route_image as image
from . import run_initial_single_capture_integration_pure as previous

ROOT,OUT=previous.ROOT,previous.OUT
MODULE='scripts.experiments.g31_ics_circulation.run_initial_single_capture_verifier_pure'
TESTS=('tests/test_g31_circulation_single_capture_campaign_verifier.py',
    'tests/test_g31_circulation_single_capture_endpoint_dispatch.py',
    'tests/test_g31_circulation_single_capture_failure_review.py')
PLANS=(('initial_single_capture_integration_source_prepare_001','b3043d1fc5170da7aa1a139fb0479c8d4f5134a6d3d7c174849482de1cfa81d2'),
    ('initial_single_capture_endpoint_source_prepare_001','ecc78936817d981eb7818e8edc79cade55a1618b159fb023d77b38e2d05e85b8'))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen():
    result=previous.frozen()
    for name,digest in PLANS:
        output=OUT/name;path=output/'plan.json'
        if sha(path)!=digest:raise ValueError('single_saved_source_plan:'+name)
        plan=json.loads(path.read_text(encoding='utf8'))
        for filename,expected in plan['source_sha256'].items():
            live=Path(filename);live=live if live.is_absolute() else ROOT/live
            archives=plan['source_archive']
            archive=Path(archives[filename]) if type(archives) is dict else Path(archives)/filename
            archive=archive if archive.is_absolute() else output/archive
            if sha(live)!=expected or sha(archive)!=expected:raise ValueError('single_saved_frozen_source:'+filename)
        result.append({'path':str(path),'sha256':digest,'sources':len(plan['source_sha256'])})
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve()
    if args.worker:
        if sys.stdin.readline()!=args.admission+'\n':raise ValueError('single_saved_pure_admission')
        import pytest
        code=pytest.main(['-q',*TESTS,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
        if any('_g31_complete_tree_normalizer' in name or 'czr005_circulation' in name for name in sys.modules):
            raise ValueError('single_saved_pure_extension_loaded')
        return code
    output.mkdir(parents=True,exist_ok=False)
    receipt={'status':'failed_or_unknown','native_calls':0,'predictor_calls':0,'actual_saved_raw_reads':0,
        'performance_runs':0,'C_extension_loads':0}
    try:
        receipt['frozen_entry']=frozen()
        entries=(MODULE,'scripts.experiments.g31_ics_circulation.verify_initial_owner_route_single_capture_campaign',
            *(path[:-3].replace('/','.') for path in TESTS),'tests.test_g31_circulation_preexisting_online_model',
            'tests.test_g31_circulation_public_rolling_reuse_model')
        files=image.source_closure(ROOT,entries)
        before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
        for name,data in files.items():
            path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        receipt['source_sha256']=before
        token=uuid.uuid4().hex
        command=[sys.executable,'-m',MODULE,'--output',str(output),'--worker','--admission',token]
        remaining=120-(time.monotonic()-BOOT)-1
        if remaining<=0:raise TimeoutError('single_saved_pure_prework_budget')
        with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
            receipt['process']=bounded.run(command,timeout=remaining,admission=token,stdout=out,stderr=err,cwd=ROOT)
        xml=output/'tests.xml';rows=ET.parse(xml).getroot().findall('.//testcase') if xml.is_file() else []
        receipt['tests']=len(rows);receipt['XML_sha256']=sha(xml) if xml.is_file() else None
        receipt['source_changed']=[name for name,digest in before.items() if sha(ROOT/name)!=digest]
        receipt['frozen_exit']=frozen()
        if (receipt['process']['status']=='exited' and receipt['process']['exitcode']==0 and len(rows)==117
            and not receipt['source_changed'] and receipt['frozen_entry']==receipt['frozen_exit']
            and not any(n.tag in ('failure','error','skipped') for row in rows for n in row)):
            from . import verify_initial_owner_route_single_capture_campaign as verifier
            from . import initial_owner_route_entry_codec_campaign as historical
            receipt['source_proof']=verifier.make_namespace(historical).source_proof()
            receipt['status']='passed'
    except BaseException as error:
        receipt['error']=repr(error);receipt['traceback']=traceback.format_exc()
    receipt['post_interpreter_before_receipt_seconds']=time.monotonic()-BOOT
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps({key:value for key,value in receipt.items() if key not in ('source_sha256','source_proof')}))
    return 0 if receipt['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
