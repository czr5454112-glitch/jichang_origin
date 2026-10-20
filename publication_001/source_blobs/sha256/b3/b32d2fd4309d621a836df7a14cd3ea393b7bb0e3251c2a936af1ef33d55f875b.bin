"""Owned120 saved-data semantic gate, no native or model evaluation."""
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import initial_owner_route_image as image

ROOT=Path(__file__).resolve().parents[3]
TEST='tests/test_g31_circulation_single_root_evidence.py'
TOKEN='single_root_evidence_pure_v1'


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    p.add_argument('--worker',action='store_true');a=p.parse_args();output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline()!=TOKEN+'\n':raise ValueError('pure_job_admission')
        import pytest
        return pytest.main(['-q',TEST,'--basetemp='+str(ROOT/'outputs'/('tmp_'+output.name)),
                           '--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False)
    files=image.source_closure(ROOT,(__package__+'.run_single_root_evidence_pure',
        __package__+'.measure_single_root_evidence','tests.test_g31_circulation_single_root_evidence'))
    before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    command=[sys.executable,'-m',__package__+'.run_single_root_evidence_pure','--output',str(output),'--worker']
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=max(.001,120-(time.monotonic()-BOOT)),
            admission=TOKEN,stdout=out,stderr=err,cwd=ROOT)
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').exists() else []
    changed=[name for name,h in before.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    bad=any(n.tag in ('failure','error','skipped') for row in rows for n in row)
    report={'status':'passed' if process['status']=='exited' and process['exitcode']==0 and rows and not bad and not changed else 'failed_or_unknown',
        'process':process,'source_sha256':before,'source_changed':changed,'tests':len(rows),
        'XML_sha256':hashlib.sha256((output/'tests.xml').read_bytes()).hexdigest() if rows else None,
        'native_calls':0,'new_predictions':0,'performance_campaigns':0,
        'scope':'Fixed saved18 old/new semantic constructions with frozen body/publication clock; no timing comparison or new prediction.',
        'post_import_before_final_receipt_seconds':time.monotonic()-BOOT}
    (output/'receipt.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
