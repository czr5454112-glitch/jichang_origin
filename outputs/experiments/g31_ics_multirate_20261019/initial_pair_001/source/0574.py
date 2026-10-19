"""Owned120 four synthetic binding tests, no actual model/native run."""
import time
BOOT=time.monotonic()
import argparse,hashlib,json,sys,uuid,xml.etree.ElementTree as ET
from pathlib import Path
from . import bounded_windows_job,initial_owner_route_image as image
from . import profile_scoped_public_inputs_six as p
MODULE='scripts.experiments.g31_ics_circulation.run_scoped_profile_binding_pure'


def main():
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True)
    a.add_argument('--worker',action='store_true');a.add_argument('--admission');args=a.parse_args();output=args.output.resolve()
    if args.worker:
        assert sys.stdin.readline()==args.admission+'\n'
        import pytest
        return pytest.main(['-q',p.TEST,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(exist_ok=False)
    files=image.source_closure(p.ROOT,(MODULE,p.TEST[:-3].replace('/','.')))
    before={str(p.ROOT/name):hashlib.sha256(data).hexdigest() for name,data in files.items()}
    for name,data in files.items():
        dest=output/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--admission',token]
    with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
        remaining=120-(time.monotonic()-BOOT)-1;assert remaining>0
        process=bounded_windows_job.run(command,timeout=remaining,admission=token,stdout=out,stderr=err,cwd=str(p.ROOT))
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').exists() else []
    changed=[path for path,d in before.items() if p.old.sha(path)!=d or p.old.sha(output/'source'/Path(path).relative_to(p.ROOT))!=d]
    elapsed=time.monotonic()-BOOT
    passed=process['status']=='exited' and process['exitcode']==0 and len(rows)==4 and not changed and elapsed<120
    passed=passed and not any(n.tag in ('failure','error','skipped') for r in rows for n in r)
    p.old.write(output/'receipt.json',{'status':'passed' if passed else 'failed_or_unknown','tests':len(rows),
        'source_sha256':before,'source_changed':changed,'XML_sha256':p.old.sha(output/'tests.xml') if rows else None,
        'process':process,'command':command,'whole_before_receipt_seconds':elapsed,
        'actual_model_calls':0,'native_calls':0,'C_extension_loads':0})
    print(json.dumps({'status':'passed' if passed else 'failed_or_unknown','tests':len(rows),'seconds':elapsed}))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
