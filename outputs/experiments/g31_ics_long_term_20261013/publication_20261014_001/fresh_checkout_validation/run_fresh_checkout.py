from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time

REPO = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
CHECKOUT = OUT.parent / 'clean_checkout_001'
COMMIT = '89c2935ef2963d769ab6ca75764009b2b3e9365f'
PYTHON = Path('C:/PROGRAMING/python3.11.9/python.exe')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    started = time.perf_counter()
    receipt = {'schema':'g31.fresh_source_archive_validation.v1', 'commit':COMMIT,
        'scope':'Fresh git archive, same author Windows Python toolchain and explicitly restored author precompiled native artifacts; not independent rebuild or external review.',
        'checkout':str(CHECKOUT), 'python':str(PYTHON), 'commands':[], 'status':'running'}
    def save():
        receipt['wall_seconds'] = time.perf_counter()-started
        (OUT/'execution_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    def run(name,command,cwd,env=None,timeout=300):
        row={'name':name,'command':[str(s) for s in command],'cwd':str(cwd)}
        receipt['commands'].append(row)
        save()
        start=time.perf_counter()
        with (OUT/(name+'.stdout.log')).open('wb') as out,(OUT/(name+'.stderr.log')).open('wb') as err:
            result=subprocess.run(command,cwd=cwd,stdout=out,stderr=err,env=env,timeout=timeout)
        row.update(exit_code=result.returncode,wall_seconds=time.perf_counter()-start)
        save()
        if result.returncode:
            raise RuntimeError(name+' failed with exit '+str(result.returncode))
    try:
        if CHECKOUT.exists():
            raise RuntimeError('fresh checkout must not preexist')
        archive=OUT/'source_commit_A.tar'
        if archive.exists():
            raise RuntimeError('archive must not preexist')
        run('archive',['git','archive','--format=tar','--output='+str(archive),COMMIT],REPO)
        receipt['archive']={'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive)}
        CHECKOUT.mkdir()
        with tarfile.open(archive) as tar:
            members=tar.getmembers()
            for member in members:
                destination=(CHECKOUT/member.name).resolve()
                if Path(member.name).is_absolute() or not destination.is_relative_to(CHECKOUT.resolve()):
                    raise RuntimeError('unsafe archive path '+member.name)
                if not (member.isfile() or member.isdir()):
                    raise RuntimeError('unsupported link/device archive member '+member.name)
            tar.extractall(CHECKOUT,members=members)
        manifest_path=CHECKOUT/'docs/g31_ics_circulation/publication_20261014/source_manifest.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        failures=[]
        for name, expected in manifest['files'].items():
            path=CHECKOUT/name
            if not path.is_file():
                failures.append({'path':name,'error':'missing'})
            elif path.stat().st_size!=expected['bytes'] or sha(path)!=expected['sha256']:
                failures.append({'path':name,'error':'hash_or_size_mismatch','actual_sha256':sha(path),'expected_sha256':expected['sha256']})
        receipt['source_manifest']={'path':str(manifest_path),'sha256':sha(manifest_path),'files':len(manifest['files']),'mismatches':failures}
        save()
        if failures:
            raise RuntimeError('source manifest verification failed')
        run('restore_author_artifacts',[str(PYTHON),'docs/g31_ics_circulation/publication_20261014/restore_author_artifacts.py','--root',str(CHECKOUT)],CHECKOUT)
        env=dict(os.environ,PYTHONPATH='src;.',PYTHONIOENCODING='utf-8',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
        run('validate_live',[str(PYTHON),'-m','scripts.experiments.g31_ics_circulation.validate_live',
            '--binary','build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd',
            '--build-receipt','outputs/experiments/g31_ics_long_term_20261013/p1_build_016/receipt.json',
            '--output',str(OUT/'fresh_check_live')],CHECKOUT,env)
        result=json.loads((OUT/'fresh_check_live/receipt.json').read_text(encoding='utf-8'))
        receipt['regression']={key:result.get(key) for key in ('status','counts','current_native_and_python_test_count','source_changed','compiled_source_mismatch','binary_sha256','historical_order_regression','native_identity_regression')}
        if result['counts']!={'tests':407,'failures':0,'errors':0,'skipped':0} or result['current_native_and_python_test_count']!=401:
            raise RuntimeError('unexpected regression counts')
        receipt['status']='passed'
    except Exception as exc:
        receipt['status']='failed'
        receipt['error']=repr(exc)
    save()
    print(json.dumps({k:receipt[k] for k in ('status','error','source_manifest','regression') if k in receipt},ensure_ascii=False))
    return 0 if receipt['status']=='passed' else 1

if __name__=='__main__':
    raise SystemExit(main())
