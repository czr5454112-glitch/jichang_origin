"""Owned120 namespace regression gate; no native, prediction or saved raw scan."""
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import initial_owner_route_image as image

ROOT=Path(__file__).resolve().parents[3]
TEST='tests/test_g31_circulation_initial_owner_route_entry_verifier_v2.py'
SOURCE=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/initial_owner_route_entry_campaign_prepare_001'
CAMPAIGN='d37d3e0ea9378974a8a331b97c21be48d6dfe3bab9c18d08b686c68041bd0097'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_sources():
    if sha(SOURCE/'campaign.json')!=CAMPAIGN:raise ValueError('entry_pure_original_plan')
    plan=json.loads((SOURCE/'campaign.json').read_text(encoding='utf8'))
    if len(plan['source_sha256'])!=151:raise ValueError('entry_pure_original_source_domain')
    for name,digest in plan['source_sha256'].items():
        if sha(name)!=digest or sha(SOURCE/plan['source_archive'][name])!=digest:
            raise ValueError('entry_pure_original_source_changed:'+name)
    return plan['source_sha256']


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--admission');a=p.parse_args();output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline()!=a.admission+'\n':raise ValueError('entry_verifier_pure_admission')
        import pytest
        return pytest.main(['-q',TEST,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False)
    old=frozen_sources()
    files=image.source_closure(ROOT,(__package__+'.run_initial_owner_route_entry_verifier_v2_pure',
        __package__+'.verify_initial_owner_route_entry_campaign_v2',TEST[:-3].replace('/','.')))
    before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',__package__+'.run_initial_owner_route_entry_verifier_v2_pure',
        '--output',str(output),'--worker','--admission',token]
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=max(.001,120-(time.monotonic()-BOOT)),
            admission=token,stdout=out,stderr=err,cwd=ROOT)
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    changed=[name for name,digest in before.items() if sha(ROOT/name)!=digest]
    original_unchanged=frozen_sources()==old
    bad=any(n.tag in ('failure','error','skipped') for row in rows for n in row)
    report={'status':'passed' if process['status']=='exited' and process['exitcode']==0 and
        len(rows)==12 and not bad and not changed and original_unchanged else 'failed_or_unknown',
        'process':process,'source_sha256':before,'source_changed':changed,'tests':len(rows),
        'original151_current_and_archive_unchanged':original_unchanged,
        'original_failed_producer_status_changed':False,'XML_sha256':sha(output/'tests.xml') if rows else None,
        'native_calls':0,'predictor_calls':0,'saved_raw_reads':0,'performance_runs':0,
        'post_interpreter_before_receipt_seconds':time.monotonic()-BOOT}
    (output/'receipt.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
