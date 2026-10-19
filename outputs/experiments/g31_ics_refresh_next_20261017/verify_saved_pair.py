"""Independent saved-file adapter for the standard-library pair verifier."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import traceback

from verify_review_bundle import check_successful_pair


class SavedFiles:
    def __init__(self):
        self.pins = {}

    def read(self, name):
        path = Path(name).resolve()
        payload = path.read_bytes()
        self.pins[str(path)] = hashlib.sha256(payload).hexdigest()
        return payload

    def json(self, name):
        payload = self.read(name)
        return json.loads(gzip.decompress(payload) if str(name).endswith('.gz') else payload)

    def mapped(self, reference):
        payload = self.read(reference['path'])
        if hashlib.sha256(payload).hexdigest() != reference['sha256']:
            raise ValueError('saved_reference_hash_mismatch:' + reference['path'])
        return reference['path']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise ValueError('output_already_exists')
    reader = SavedFiles()
    try:
        checks = check_successful_pair(reader, reader.mapped, str(arguments.receipt.resolve()))
        report = {'status': 'passed', 'checks': checks}
    except Exception:
        report = {'status': 'failed', 'exception': traceback.format_exc()}
    for source in (Path(__file__), Path(__file__).with_name('verify_review_bundle.py')):
        reader.read(source)
    report.update(input_sha256=reader.pins, native_executions=0, model_inference_executions=0,
                  training_executions=0, project_runtime_imports=0)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
