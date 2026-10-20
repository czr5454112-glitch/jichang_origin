"""Owned120 focused composition regression gate; no native or fixture replay."""
import time
BOOT=time.monotonic()
import argparse,json,hashlib,sys,uuid
from pathlib import Path
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import initial_owner_route_image as image
from . import run_initial_owner_route_entry_verifier_v2_pure as old

ROOT=old.ROOT
TEST='tests/test_g31_circulation_initial_owner_route_entry_codec_integration.py'
CODEC=old.SOURCE.parent/'complete_root_evidence_codec_pair_prepare_001'
CODEC_PLAN='11451e03fd2ff9ccda080b82a5fa2497b55f37463f0c30b07fd7467fda31d9ff'


def frozen():
    result=old.frozen_sources()
    assert old.sha(CODEC/'plan.json')==CODEC_PLAN
    plan=json.loads((CODEC/'plan.json').read_text(encoding='utf8'))
    for name,digest in plan['source_sha256'].items():
        path=Path(name);path=path if path.is_absolute() else ROOT/path
        assert old.sha(path)==old.sha(CODEC/plan['source_archive'][name])==digest
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--admission');a=p.parse_args();output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline()!=a.admission+'\n':raise ValueError('entry_codec_pure_admission')
        import pytest
        return pytest.main(['-q',TEST,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False);before_old=frozen()
    modules=(__package__+'.run_initial_entry_codec_integration_pure',
        __package__+'.initial_owner_route_entry_codec_integration',TEST[:-3].replace('/','.'),
        'tests.test_g31_circulation_initial_owner_route_entry_integration',
        'tests.test_g31_circulation_initial_owner_route_entry_hop')
    files=image.source_closure(ROOT,modules);before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',__package__+'.run_initial_entry_codec_integration_pure',
        '--output',str(output),'--worker','--admission',token]
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=max(.001,120-(time.monotonic()-BOOT)),
            admission=token,stdout=out,stderr=err,cwd=ROOT)
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    changed=[name for name,digest in before.items() if old.sha(ROOT/name)!=digest]
    original_unchanged=frozen()==before_old
    bad=any(n.tag in ('failure','error','skipped') for row in rows for n in row)
    report={'status':'passed' if process['status']=='exited' and process['exitcode']==0 and len(rows)==7
        and not bad and not changed and original_unchanged else 'failed_or_unknown',
        'process':process,'source_sha256':before,'source_changed':changed,'tests':len(rows),
        'original151_and_codec135_current_and_archive_unchanged':original_unchanged,
        'XML_sha256':old.sha(output/'tests.xml') if rows else None,
        'native_calls':0,'predictor_calls':0,'saved_raw_reads':0,'performance_runs':0,
        'post_interpreter_before_receipt_seconds':time.monotonic()-BOOT}
    (output/'receipt.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
