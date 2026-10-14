"""Export only the three repairs and new tests against pinned V3 bytes."""
import difflib
import json
from pathlib import Path
import subprocess

root = Path(__file__).absolute().parents[4]
out = Path(__file__).absolute().parent
base = 'fccd4819532701ee4173ec598822450d962d4e61'
paths = ['scripts/experiments/ics_circulation_v3/'+name for name in
         ('routing_reference.py', 'runtime.py', 'terminal_capacity_screen.py')]
new_test = 'tests/test_ics_v3_executed_audit_regressions.py'
chunks = []
for path in [*paths, new_test]:
    before = '' if path == new_test else subprocess.check_output(['git', 'show', base+':'+path], cwd=root).decode()
    after = (root/path).read_text(encoding='utf-8')
    chunks.extend(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                  fromfile='/dev/null' if path == new_test else 'a/'+path, tofile='b/'+path))
(out/'v3_correctness.patch').write_text(''.join(chunks), encoding='utf-8', newline='\n')
print(json.dumps({'base': base, 'files': [*paths, new_test], 'patch': str(out/'v3_correctness.patch')}))
