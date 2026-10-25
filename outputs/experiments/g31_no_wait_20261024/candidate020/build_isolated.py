"""Build the isolated020 source with the agreed Python3.11.9 environment."""
from pathlib import Path
import argparse, hashlib, json, shutil, subprocess, sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def build(name):
    if Path(sys.executable).resolve()!=Path('C:/PROGRAMING/python3.11.9/python.exe').resolve():
        raise RuntimeError('Use C:/PROGRAMING/python3.11.9/python.exe')
    if not name.replace('_','').isalnum():raise ValueError('invalid new build name')
    out=ROOT/'build'/('g31_no_wait_'+name)
    if out.exists():raise FileExistsError(out)
    source=out/'source';source.mkdir(parents=True)
    for filename in ('core.cpp','CMakeLists.txt'):shutil.copyfile(HERE/'source'/filename,source/filename)
    shutil.copyfile(__file__,source/'build_isolated.py')
    receipt=dict(status='building',python=sys.executable,python_version=sys.version,
        prepared_candidate=str(HERE),source_sha256={p.name:sha(p) for p in source.iterdir()})
    save(out/'build_receipt.json',receipt)
    pybind=Path(sys.executable).parent/'Lib/site-packages/pybind11/share/cmake/pybind11'
    commands=['@echo off','call "C:\\PROGRAMING\\visual studio\\Visual studio\\VC\\Auxiliary\\Build\\vcvars64.bat"',
      'if errorlevel 1 exit /b %errorlevel%',
      f'"C:\\Program Files\\CMake\\bin\\cmake.exe" -S "{source}" -B "{out}" -G Ninja '
      '-DCMAKE_MAKE_PROGRAM="C:/Users/38908/.conda/envs/czr005/Library/bin/ninja.exe" '
      f'-Dpybind11_DIR="{pybind}" -DPython_EXECUTABLE="{sys.executable}" '
      '-DCMAKE_BUILD_TYPE=Release -DCMAKE_TRY_COMPILE_CONFIGURATION=Release -DCMAKE_CXX_FLAGS_DEBUG="/Z7 /Ob0 /Od /RTC1"',
      'if errorlevel 1 exit /b %errorlevel%',
      f'"C:\\Program Files\\CMake\\bin\\cmake.exe" --build "{out}" --config Release --parallel 2',
      'exit /b %errorlevel%']
    batch=out/'build.cmd';batch.write_text('\n'.join(commands)+'\n',encoding='ascii')
    with (out/'build.log').open('w',encoding='utf-8') as log:
        result=subprocess.run(['cmd.exe','/d','/c',str(batch)],stdout=log,stderr=subprocess.STDOUT)
    binaries=list((out/'python').glob('g31_nowait*.pyd'))
    receipt.update(status='complete' if result.returncode==0 and len(binaries)==1 else 'failed',
        returncode=result.returncode,binaries={str(p):sha(p) for p in binaries})
    save(out/'build_receipt.json',receipt)
    if receipt['status']!='complete':raise RuntimeError('build failed; see '+str(out/'build.log'))
    return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',default='020')
    print(json.dumps(build(p.parse_args().name),indent=2))
