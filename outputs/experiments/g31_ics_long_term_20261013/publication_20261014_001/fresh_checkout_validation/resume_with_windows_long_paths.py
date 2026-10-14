from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
import traceback

OUT=Path(__file__).resolve().parent
ROOT=Path('\\\\?\\'+str(OUT.parent/'clean_checkout_001'))
PYTHON=Path('C:/PROGRAMING/python3.11.9/python.exe')
COMMIT='89c2935ef2963d769ab6ca75764009b2b3e9365f'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    start=time.perf_counter()
    receipt={'schema':'g31.fresh_source_archive_validation.v1','commit':COMMIT,
        'scope':'Fresh git archive; same author Windows Python toolchain and explicitly restored author precompiled native artifacts. Not an independent rebuild or external review.',
        'prior_failed_attempt':'execution_receipt.json','diagnosis':'extraction_diagnosis.json',
        'workaround':'Use the Windows extended-length path prefix for the same owned fresh checkout; all source bytes still come exclusively from the exact git archive.',
        'checkout':str(ROOT),'commands':[],'status':'running'}
    def save():
        receipt['wall_seconds']=time.perf_counter()-start
        (OUT/'long_path_execution_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    def run(name,command,env=None):
        row={'name':name,'command':command,'cwd':str(ROOT)}
        receipt['commands'].append(row); save()
        begin=time.perf_counter()
        with (OUT/(name+'.stdout.log')).open('wb') as out,(OUT/(name+'.stderr.log')).open('wb') as err:
            r=subprocess.run(command,cwd=ROOT,env=env,stdout=out,stderr=err,timeout=300)
        row.update(exit_code=r.returncode,wall_seconds=time.perf_counter()-begin); save()
        if r.returncode: raise RuntimeError(name+' failed with exit '+str(r.returncode))
    try:
        archive=OUT/'source_commit_A.tar'
        expected=json.loads((OUT/'execution_receipt.json').read_text(encoding='utf-8'))['archive']
        if sha(archive)!=expected['sha256']: raise RuntimeError('archive changed since git archive')
        receipt['archive']=expected
        # Already extracted members are validated against archive bytes, not overwritten.
        kept=restored=0
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                target=(ROOT/member.name).resolve()
                if not target.is_relative_to(ROOT.resolve()) or not(member.isfile() or member.isdir()):
                    raise RuntimeError('unsafe archive member '+member.name)
                if member.isdir(): target.mkdir(parents=True,exist_ok=True); continue
                content=tar.extractfile(member).read()
                if target.exists():
                    if target.read_bytes()!=content: raise RuntimeError('existing extraction bytes differ '+member.name)
                    kept+=1
                else:
                    target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(content); restored+=1
        receipt['archive_file_counts']={'existing_exact':kept,'restored_from_archive':restored}
        path=ROOT/'docs/g31_ics_circulation/publication_20261014/source_manifest.json'
        manifest=json.loads(path.read_text(encoding='utf-8')); mismatches=[]
        for name,expected in manifest['files'].items():
            item=ROOT/name
            if not item.is_file() or item.stat().st_size!=expected['bytes'] or sha(item)!=expected['sha256']:
                mismatches.append(name)
        receipt['source_manifest']={'sha256':sha(path),'files':len(manifest['files']),'mismatches':mismatches}; save()
        if mismatches: raise RuntimeError('source manifest mismatch')
        run('long_path_restore',[str(PYTHON),'docs/g31_ics_circulation/publication_20261014/restore_author_artifacts.py','--root',str(ROOT)])
        env=dict(os.environ,PYTHONPATH='src;.',PYTHONIOENCODING='utf-8',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
        destination=str(Path('\\\\?\\'+str(OUT/'fresh_check_live')))
        run('long_path_validate_live',[str(PYTHON),'-m','scripts.experiments.g31_ics_circulation.validate_live',
            '--binary','build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd',
            '--build-receipt','outputs/experiments/g31_ics_long_term_20261013/p1_build_016/receipt.json',
            '--output',destination],env)
        result=json.loads((OUT/'fresh_check_live/receipt.json').read_text(encoding='utf-8'))
        receipt['regression']={key:result.get(key) for key in ('status','counts','current_native_and_python_test_count','source_changed','compiled_source_mismatch','binary_sha256','historical_order_regression','native_identity_regression')}
        if result['counts']!={'tests':407,'failures':0,'errors':0,'skipped':0} or result['current_native_and_python_test_count']!=401:
            raise RuntimeError('unexpected regression counts')
        receipt['status']='passed'
    except Exception as exc:
        receipt.update(status='failed',error=str(exc),traceback=traceback.format_exc())
    save(); print(json.dumps(receipt))
    return int(receipt['status']!='passed')
if __name__=='__main__': raise SystemExit(main())
