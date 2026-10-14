"""Preserve every independent focused attempt, including source bindings."""
from pathlib import Path
import contextlib
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def main():
    import pytest
    label, *files = sys.argv[1:]
    out = Path(__file__).resolve().parent / label
    out.mkdir(exist_ok=False)
    started, cpu = time.perf_counter(), time.process_time()
    paths = sorted((ROOT / 'scripts/experiments/ics_circulation_v3').glob('*.py'))
    paths += [ROOT / name for name in files]
    before = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    arguments = files + ['-q', '--basetemp=.tmp/pytest_round8_' + label,
                         '--junitxml=' + str(out / 'junit.xml')]
    (out / 'protocol.json').write_text(json.dumps({'arguments': arguments, 'before': before}, indent=2), encoding='utf8')
    with (out / 'pytest.txt').open('w', encoding='utf8') as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        code = int(pytest.main(arguments))
    after = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    suites = ET.parse(out / 'junit.xml').getroot().findall('testsuite')
    result = {'exit_code': code,
              **{k: sum(int(s.attrib.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')},
              'cpu_seconds': time.process_time() - cpu, 'wall_seconds': time.perf_counter() - started,
              'source_and_test_unchanged': before == after,
              'changed_files': [name for name in before if before[name] != after[name]],
              'before': before, 'after': after,
              'resource_scope': 'In-process focused pytest and binding interval; excludes Python/pytest import bootstrap. No child physical replay.'}
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('before', 'after')}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
