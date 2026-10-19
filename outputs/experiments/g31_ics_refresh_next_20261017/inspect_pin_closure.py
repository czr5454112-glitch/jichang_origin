"""List unmatched historic Python pins without executing any project code."""
import gzip
import hashlib
import json
from pathlib import Path

from build_review_bundle import ROOT, pin_references, selected_files


BASE = Path(__file__).resolve().parent
GROUPS = ('g31_ics_learning_next_20261017', 'g31_ics_service_update_20261017', 'g31_ics_refresh_next_20261017')


def main():
    files = [path for group in GROUPS for path in selected_files(ROOT / 'outputs/experiments' / group)]
    hashes = {}
    references = {}
    for path in files:
        payload = path.read_bytes()
        hashes.setdefault(hashlib.sha256(payload).hexdigest(), []).append(str(path))
        if path.name.endswith(('.json', '.json.gz')):
            document = json.loads(gzip.decompress(payload) if path.suffix == '.gz' else payload)
            for original, expected, location, native in pin_references(document):
                if original.endswith('.py') and not native:
                    references.setdefault((original, expected), []).append(str(path))
    unmatched = []
    for (original, expected), sources in sorted(references.items()):
        if expected in hashes:
            continue
        path = Path(original)
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            continue
        unmatched.append({'path': original, 'sha256': expected, 'referenced_by': sorted(set(sources))})
    report = {'status': 'inventory_only_not_bundle_verification', 'selected_file_count': len(files),
              'unmatched_python_pin_count': len(unmatched), 'unmatched': unmatched,
              'native_executions': 0, 'project_runtime_imports': 0}
    output = BASE / 'pin_closure_inventory_001.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
