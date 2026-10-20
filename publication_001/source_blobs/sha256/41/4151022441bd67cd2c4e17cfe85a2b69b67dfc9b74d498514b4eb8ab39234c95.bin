"""Owned parent/worker log composition gate; no build/load or real fixture."""
import time
BOOT=time.monotonic()
import argparse
import json
import os
from pathlib import Path
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import run_planning_v2_c_encoder_gate_v3 as v3

EXPECTED=39


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve();old=v3.old
    if args.worker:
        old.require(sys.stdin.readline()==args.admission+'\n','admission')
        report={'status':'started','expected_tests':EXPECTED,'builds':0,'C_loads':0,'actual_fixture_reads':0,
                'composition_scope':'Actual original parent and command-runner file opens; subprocesses replaced by deterministic fake writers.'}
        before={}
        try:
            before=v3.namespace()['project_closure']();report['source_before']=before
            import pytest
            config=output/'pytest.ini';config.write_text('[pytest]\n',encoding='utf8')
            result=int(pytest.main([v3.previous.TEST,v3.TEST,'-q','--noconftest','-c',str(config),
                '--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')]))
            rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase')
            bad=[{'name':r.attrib.get('name'),'tag':child.tag} for r in rows for child in r
                 if child.tag in ('failure','error','skipped')]
            report.update(pytest_exit_code=result,tests=len(rows),bad=bad,XML_sha256=old.sha(output/'tests.xml'))
            old.require(result==0 and len(rows)==EXPECTED and not bad,'pure_failed')
            report['status']='passed'
        except BaseException as error:
            report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
            (output/'exception.txt').write_text(traceback.format_exc(),encoding='utf8')
        finally:
            report['source_after']=v3.namespace()['project_closure']()
            report['source_changed']=report['source_after']!=before
            if report['source_changed']:report['status']='failed_source_changed'
            report['worker_pre_report_seconds']=time.monotonic()-BOOT
            old.write(output/'receipt.json',report)
        return 0 if report['status']=='passed' else 1
    output.mkdir(parents=True,exist_ok=False);token=uuid.uuid4().hex
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1';os.environ['PYTEST_ADDOPTS']=''
    command=[str(old.PYTHON),'-m',__package__+'.run_planning_v2_c_encoder_parent_logs_pure',
             '--output',str(output),'--worker','--admission',token]
    with (output/'parent.stdout.log').open('x',encoding='utf8') as stdout,(output/'parent.stderr.log').open('x',encoding='utf8') as stderr:
        result=bounded_windows_job.run(command,timeout=120-(time.monotonic()-BOOT),
            stdout=stdout,stderr=stderr,admission=token,cwd=old.ROOT)
    result.update(command=command,whole_bound_seconds=120,parent_pre_export_seconds=time.monotonic()-BOOT)
    old.write(output/'bounded_execution.json',result);print(json.dumps(result))
    return 0 if result['status']=='exited' and result['exitcode']==0 else 1


if __name__=='__main__':raise SystemExit(main())
