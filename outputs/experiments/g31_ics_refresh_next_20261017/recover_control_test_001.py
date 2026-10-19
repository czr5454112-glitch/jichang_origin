"""Apply the authorized exact-hash historical timing-test reconstruction."""
import json
from pathlib import Path

from build_review_bundle import Collector, ROOT


def main():
    expected = '1258970a5b8cc0bdf07d9bd9598a0806c8189acb911e6b674167315f3fa13881'
    original = ROOT / 'tests/test_g31_foundation_later_control.py'
    collector = Collector({})
    collector.resolve_pin(str(original), expected, 'service_update/final_validation_001/plan.json', (), False)
    member = collector.references[(str(original).replace('\\', '/'), expected)]
    output = Path(__file__).resolve().parent / 'historical_control_test_001'
    output.mkdir(exist_ok=False)
    with (output / original.name).open('xb') as stream:
        stream.write(collector.entries[member])
    with (output / 'manifest.json').open('x', encoding='utf8') as stream:
        json.dump({'status': 'exact_registered_hash_recovered', 'reconstruction': collector.reconstructions}, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': 'exact_registered_hash_recovered', 'sha256': expected, 'path': str(output)}))


if __name__ == '__main__':
    main()
