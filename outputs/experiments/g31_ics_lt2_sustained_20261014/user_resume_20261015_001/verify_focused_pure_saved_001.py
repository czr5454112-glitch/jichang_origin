"""Saved pure-result readback, not a second test or source-proof execution."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
PYTHON_SHA = '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError('root_pure_readback:' + reason)


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--tests', required=True, type=int)
    for name in ('plan', 'receipt', 'external', 'xml'):
        parser.add_argument('--' + name + '-sha', required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / 'outputs'), 'output_domain')
    filenames = {'plan': 'plan.json', 'receipt': 'receipt.json',
                 'external': 'external_application_wall.json', 'xml': 'tests.xml'}
    pinned = {}
    for name, filename in filenames.items():
        digest = getattr(args, name + '_sha')
        require(sha(output / filename) == digest, 'independent_pin:' + name)
        pinned[filename] = digest
    plan = json.loads((output / filenames['plan']).read_bytes())
    receipt = json.loads((output / filenames['receipt']).read_bytes())
    external = json.loads((output / filenames['external']).read_bytes())
    require(receipt['status'] in ('passed', 'passed_synthetic_routing'), 'producer_status')
    require(type(external['exitcode']) is int and external['exitcode'] == 0
            and type(external['wrapper_exitcode']) is int and external['wrapper_exitcode'] == 0,
            'external_closed_zero')
    ticks, frequency = external['elapsed_ticks'], external['stopwatch_frequency']
    require(type(ticks) is int and type(frequency) is int and frequency > 0
            and 0 <= ticks <= 120 * frequency, 'whole120_typed_clock')
    require(external['external_application_seconds'] == ticks / frequency, 'clock_exact_ratio')
    require(Path(external['output_directory']).resolve() == output
            and Path(external['cwd']).resolve() == ROOT, 'external_location')
    command = external['command']
    require(type(command) is list and len(command) == 5 and command[1] == '-m'
            and command[3] == '--output' and Path(command[4]).resolve() == output,
            'external_exact_command_shape')
    require(sha(command[0]) == PYTHON_SHA, 'interpreter_bytes')
    for name, ref in external['outputs'].items():
        require(type(ref) is dict and Path(ref['path']).resolve() == (output / name).resolve()
                and sha(ref['path']) == ref['sha256'], 'external_output_binding:' + name)
    expected = external.get('expected_pins')
    if expected is not None:
        require(external['pins_before'] == expected == external['pins_after'], 'external_fixed_pin_maps')
        for path, digest in expected.items():
            require(sha(path) == digest, 'current_external_pin:' + path)
    if 'fixed_source_pins' in external:
        require(external['fixed_source_entry_passed'] is True
                and external['fixed_source_exit_passed'] is True, 'fixed_source_results')
        for row in external['fixed_source_pins'].values():
            require(row['entry_matches'] is True and row['exit_matches'] is True
                    and row['expected_sha256'] == row['entry_sha256'] == row['exit_sha256'] == sha(row['path']),
                    'fixed_source_entry_exit')
    tests = ET.parse(output / 'tests.xml').getroot().findall('.//testcase')
    require(len(tests) == args.tests and not any(n.tag in ('failure', 'error', 'skipped')
            for case in tests for n in case), 'complete_XML_denominator')
    require(receipt['XML_sha256'] == pinned['tests.xml'], 'receipt_XML_binding')
    if 'plan_sha256' in receipt:
        require(receipt['plan_sha256'] == pinned['plan.json'], 'receipt_plan_binding')
    if (output / 'collection.json').is_file():
        collection = json.loads((output / 'collection.json').read_bytes())
        require(collection['count'] == len(collection['nodeids']) == args.tests
                and len(set(collection['nodeids'])) == args.tests
                and collection['recorded_before_execution'] is True
                and receipt['collection_sha256'] == sha(output / 'collection.json'), 'actual_collection')
    pins = plan['source_sha256']
    archives = plan.get('source_archive', {name: 'source/' + name for name in pins})
    require(set(pins) == set(archives), 'source_archive_domain')
    saved_paths = set()
    for name, digest in pins.items():
        current, saved = (ROOT / name).resolve(), (output / archives[name]).resolve()
        require(not Path(name).is_absolute() and Path(name).as_posix() == name
                and '..' not in Path(name).parts and archives[name] == 'source/' + name,
                'canonical_source_key:' + name)
        require(current.is_relative_to(ROOT) and saved.is_relative_to(output / 'source')
                and current != saved and saved not in saved_paths and len(str(saved)) < 260,
                'independent_contained_archive:' + name)
        require(sha(current) == digest == sha(saved), 'current_and_archive:' + name)
        saved_paths.add(saved)
    for key in ('source_changed', 'final_source_changed', 'blocked_real_calls'):
        if key in receipt:
            require(receipt[key] == [], 'producer_nonempty:' + key)
    for key in ('loaded_entry', 'loaded_exit', 'loaded_exit_final'):
        if key in receipt:
            rows = receipt[key]
            require(type(rows) is dict and all(name in pins and digest == pins[name]
                    for name, digest in rows.items()), 'loaded_binding:' + key)
    parent = output / 'bounded_parent_receipt.json'
    if parent.is_file():
        bounded = json.loads(parent.read_bytes())
        require(bounded['status'] == 'passed' and bounded['process']['status'] == 'exited'
                and bounded['process']['exitcode'] == 0 and bounded['shared_seconds'] == 120
                and bounded['receipt_sha256'] == pinned['receipt.json']
                and bounded['command'] == command, 'owned_parent_closure')
    for name in ('plan', 'receipt', 'external', 'xml'):
        require(sha(output / filenames[name]) == getattr(args, name + '_sha'), 'final_saved_pin:' + name)
    report = {'schema': 'g31.focused_pure.root_saved_review.v1',
        'status': 'saved_artifact_bindings_and_complete_test_denominator_verified',
        'tests': args.tests, 'sources_current_archive': len(pins),
        'whole_python_seconds': ticks / frequency, 'pins': pinned,
        'review_source_sha256': sha(__file__), 'saved_only_seconds': time.perf_counter() - started,
        'tests_rerun': 0, 'project_code_imports': 0, 'model': 0, 'native': 0, 'custom_C_loads': 0,
        'scope': 'Saved producer evidence and file bindings, not a second execution or native/performance certificate.'}
    target = output / 'root_saved_review_001.json'
    with target.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'path': str(target), 'sha256': sha(target), 'tests': args.tests,
                      'sources': len(pins), 'saved_only_seconds': report['saved_only_seconds']}))


if __name__ == '__main__':
    main()
