"""Owned120 functional gate; no benchmark or NativeSession execution."""
from __future__ import annotations
import time
BOOT=time.perf_counter()
import argparse
import os
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import measure_json_prediction_shards as measure


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve()
    if args.worker:
        if sys.stdin.readline().strip()!=args.admission:raise ValueError('no_owned_job_admission')
        os.environ['G31_SHARD_FUNCTIONAL_OUTPUT']=str(output)
        import pytest
        return pytest.main(['-q',*measure.TEST_NAMES,'--basetemp='+str(measure.ROOT/'outputs'/('jsp_'+output.name[-3:])),
            '--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False)
    before={name:measure.codec.sha_bytes(data) for name,data in measure.closure().items()}
    for name in before:
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((measure.ROOT/name).read_bytes())
    admission=uuid.uuid4().hex
    command=[sys.executable,'-m',__package__+'.run_json_shards_pure','--worker','--output',str(output),'--admission',admission]
    with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
        process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.perf_counter()-BOOT)),
            admission=admission,stdout=stdout,stderr=stderr,cwd=measure.ROOT)
    changed=[name for name,digest in before.items() if measure.sha(measure.ROOT/name)!=digest]
    cases=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    bad=any(c.tag in ('failure','error','skipped') for row in cases for c in row)
    report={'schema':'g31.json_prediction_shards_functional_gate.v1','process':process,'command':command,
        'source_sha256':before,'source_changed':changed,'native_calls':0,'performance_campaign_executed':False,
        'tests':len(cases),'XML_sha256':measure.sha(output/'tests.xml') if cases else None,
        'startup_attestations':{mode:{'path':str(output/('startup_'+mode+'.json')),'sha256':measure.sha(output/('startup_'+mode+'.json'))}
            for mode in ('compiled','shard0','shard1') if (output/('startup_'+mode+'.json')).is_file()},
        'post_interpreter_wall_seconds':time.perf_counter()-BOOT,
        'status':'passed' if process['status']=='exited' and process['exitcode']==0 and not changed and len(cases)==measure.EXPECTED_PURE_TESTS and not bad else 'failed_or_unknown'}
    measure.write(output/'receipt.json',report)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
