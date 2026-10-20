"""Owned120 synthetic profile controls; no C/native/model/real fixture load."""
import time
BOOT=time.monotonic()
import argparse,hashlib,json,sys,uuid,xml.etree.ElementTree as ET
from pathlib import Path
from . import bounded_windows_job
from . import profile_complete_c_publisher_saved18 as p
MODULE='scripts.experiments.g31_ics_circulation.run_complete_c_publisher_profile_pure'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission');a=parser.parse_args();output=a.output.resolve()
    if a.worker:
        assert sys.stdin.readline()==a.admission+'\n'
        import pytest
        return pytest.main(['-q',p.TEST,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(exist_ok=False);files=p.source_files()
    before={str(p.ROOT/name):hashlib.sha256(data).hexdigest() for name,data in files.items()}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--admission',token]
    with (output/'stdout.log').open('x') as stdout,(output/'stderr.log').open('x') as stderr:
        remaining=120-(time.monotonic()-BOOT)-1;assert remaining>0
        process=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,admission=token,cwd=p.ROOT)
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').exists() else []
    changed=[path for path,d in before.items() if p.sha(path)!=d or p.sha(output/'source'/Path(path).relative_to(p.ROOT))!=d]
    elapsed=time.monotonic()-BOOT
    passed=process['status']=='exited' and process['exitcode']==0 and len(rows)==8 and not changed and elapsed<120
    passed=passed and not any(n.tag in ('failure','error','skipped') for row in rows for n in row)
    p.write(output/'receipt.json',{'status':'passed' if passed else 'failed_or_unknown','tests':len(rows),
        'source_sha256':before,'source_changed':changed,'XML_sha256':p.sha(output/'tests.xml') if rows else None,
        'process':process,'command':command,'whole_before_receipt_seconds':elapsed,
        'actual_model_calls':0,'native_calls':0,'C_extension_loads':0,'actual_raw_decodes':0})
    print(json.dumps({'status':'passed' if passed else 'failed_or_unknown','tests':len(rows),'seconds':elapsed}))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
