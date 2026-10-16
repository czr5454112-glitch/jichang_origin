from pathlib import Path
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
DEST = OUT/'initial_single_failure_pure_001'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def child():
    assert input() == 'single-failure-pure-001'
    plan = json.loads((DEST/'plan.json').read_bytes())
    for name, digest in plan['sources'].items():
        assert sha(ROOT/name) == sha(DEST/'source'/name) == digest, name
    import pytest
    code = pytest.main(['-q', '-p', 'no:cacheprovider',
        'tests/test_g31_circulation_single_capture_failure_review.py',
        '--junitxml=' + str(DEST/'tests.xml')])
    loaded = {}
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                name = str(path.relative_to(ROOT))
                assert name in plan['sources'] and sha(path) == plan['sources'][name], name
                loaded[name] = sha(path)
    write(DEST/'loaded_exit.json', loaded)
    for name, digest in plan['sources'].items():
        assert sha(ROOT/name) == sha(DEST/'source'/name) == digest, name
    raise SystemExit(code)


def parent():
    started = time.perf_counter_ns()
    assert not DEST.exists()
    DEST.mkdir()
    old = OUT/'initial_single_capture_source_prepare_001/plan.json'
    assert sha(old) == 'ac5461efa4fbf7f097b05cb873a5be949f03fb5b88a912f9b27cf3fa4e38a51d'
    sources = json.loads(old.read_bytes())['sources']
    for name, digest in sources.items():
        assert sha(ROOT/name) == digest, name
        frozen = old.parent/'source'/name
        assert sha(frozen) == digest, name
    for name in (
        'scripts/experiments/g31_ics_circulation/verify_initial_single_capture_failure.py',
        'tests/test_g31_circulation_single_capture_failure_review.py',
        str(Path(__file__).resolve().relative_to(ROOT)),
    ):
        name = str(Path(name))
        sources[name] = sha(ROOT/name)
    for name, digest in sources.items():
        target = DEST/'source'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
        assert sha(target) == digest
    write(DEST/'plan.json', {'schema': 'g31.single_failure_pure.v1', 'sources': sources,
        'old_source_plan_sha256': sha(old), 'native_calls': 0, 'model_calls': 0,
        'scope': 'Standalone failed prefix checker only; not installed in campaign/verifier.',
        'hard_timeout_seconds': 120})
    from scripts.experiments.g31_ics_circulation import bounded_windows_job as job
    code = ("from pathlib import Path; p=Path(" + repr(str(Path(__file__).resolve())) +
            "); n={'__file__':str(p),'__name__':'pure_child'}; "
            "exec(compile(p.read_text(encoding='utf8'),str(p),'exec'),n); n['child']()")
    with (DEST/'stdout.log').open('x', encoding='utf8') as stdout, (DEST/'stderr.log').open('x', encoding='utf8') as stderr:
        bounded = job.run([sys.executable, '-c', code], timeout=120,
            stdout=stdout, stderr=stderr, admission='single-failure-pure-001', cwd=ROOT)
    write(DEST/'bounded_process.json', bounded)
    result = {'bounded': bounded, 'whole_seconds': (time.perf_counter_ns()-started)/1e9,
              'plan_sha256': sha(DEST/'plan.json'), 'native_calls': 0, 'model_calls': 0}
    if (DEST/'tests.xml').exists():
        suites = ET.parse(DEST/'tests.xml').getroot().findall('testsuite')
        result['tests'] = {k: sum(int(s.attrib[k]) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
        result['tests_sha256'] = sha(DEST/'tests.xml')
    write(DEST/'receipt.json', result)
    print(json.dumps(result))
    assert bounded['status'] == 'exited' and bounded['exitcode'] == 0


if __name__ == '__main__':
    parent()
