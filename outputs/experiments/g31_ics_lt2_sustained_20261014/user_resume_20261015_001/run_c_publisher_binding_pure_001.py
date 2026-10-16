from pathlib import Path
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
DEST = OUT/'complete_C_publisher_binding_pure_001'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def check(plan):
    for name, digest in plan['sources'].items():
        assert sha(ROOT/name) == sha(DEST/'source'/name) == digest, name


def child():
    assert input() == 'C-publisher-binding-pure-001'
    plan = json.loads((DEST/'plan.json').read_bytes())
    check(plan)
    import pytest
    code = pytest.main(['-q', '-p', 'no:cacheprovider',
        'tests/test_g31_circulation_complete_root_evidence_c_normalizer.py',
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
    assert '_g31_complete_tree_normalizer' not in sys.modules
    write(DEST/'loaded_exit.json', loaded)
    check(plan)
    raise SystemExit(code)


def parent():
    started = time.perf_counter_ns()
    DEST.mkdir(exist_ok=False)
    old_plans = (
        ('initial_owner_route_entry_codec_campaign_prepare_001/campaign.json',
         '8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a'),
        ('complete_root_evidence_codec_pair_prepare_001/plan.json',
         '11451e03fd2ff9ccda080b82a5fa2497b55f37463f0c30b07fd7467fda31d9ff'),
        ('c_tree_normalizer_saved18_prepare_002/plan.json',
         '3d9688ced5b68f72d924f46876a064c0063276ac9b20bf5c2ccc88a182025e3e'),
    )
    sources = {}
    for filename, expected in old_plans:
        path = OUT/filename
        assert sha(path) == expected
        old = json.loads(path.read_bytes())
        for name, digest in old['source_sha256'].items():
            live = Path(name)
            if not live.is_absolute(): live = ROOT/live
            assert sha(live) == digest, name
            if 'source_archive' in old:
                assert sha(path.parent/old['source_archive'][name]) == digest, name
            relative = str(live.relative_to(ROOT))
            assert relative not in sources or sources[relative] == digest
            sources[relative] = digest
    for name in (
        'scripts/experiments/g31_ics_circulation/complete_root_evidence_c_normalizer.py',
        'tests/test_g31_circulation_complete_root_evidence_c_normalizer.py',
        str(Path(__file__).resolve().relative_to(ROOT)),
    ):
        name = str(Path(name)); sources[name] = sha(ROOT/name)
    for name, digest in sources.items():
        target = DEST/'source'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
        assert sha(target) == digest
    plan = {'schema': 'g31.complete_C_publisher.binding_pure.v1', 'sources': sources,
        'old_plans': dict(old_plans), 'native_calls': 0, 'model_calls': 0, 'C_extension_loads': 0,
        'scope': 'Private full publisher binding tested with original Python provider only; actual C and cost remain separate gates.',
        'hard_timeout_seconds': 120}
    write(DEST/'plan.json', plan)
    from scripts.experiments.g31_ics_circulation import bounded_windows_job as job
    code = ("from pathlib import Path; p=Path(" + repr(str(Path(__file__).resolve())) +
            "); n={'__file__':str(p),'__name__':'pure_child'}; "
            "exec(compile(p.read_text(encoding='utf8'),str(p),'exec'),n); n['child']()")
    with (DEST/'stdout.log').open('x', encoding='utf8') as stdout, (DEST/'stderr.log').open('x', encoding='utf8') as stderr:
        bounded = job.run([sys.executable, '-c', code], timeout=120-(time.perf_counter_ns()-started)/1e9-1,
            stdout=stdout, stderr=stderr, admission='C-publisher-binding-pure-001', cwd=ROOT)
    write(DEST/'bounded_process.json', bounded)
    result = {'bounded': bounded, 'whole_seconds': (time.perf_counter_ns()-started)/1e9,
              'plan_sha256': sha(DEST/'plan.json'), 'native_calls': 0, 'model_calls': 0, 'C_extension_loads': 0}
    if (DEST/'tests.xml').exists():
        suites = ET.parse(DEST/'tests.xml').getroot().findall('testsuite')
        result['tests'] = {k: sum(int(s.attrib[k]) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
        result['tests_sha256'] = sha(DEST/'tests.xml')
    write(DEST/'receipt.json', result)
    print(json.dumps(result))
    assert bounded['status'] == 'exited' and bounded['exitcode'] == 0


if __name__ == '__main__': parent()
