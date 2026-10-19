"""Recover only identified post-targeted edits, accepting exact registered SHA bytes."""
import ast
import hashlib
import json
from pathlib import Path


BASE = Path(__file__).resolve().parent


def remove_function(text, name):
    lines = text.splitlines(keepends=True)
    function = next(node for node in ast.parse(text).body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    return ''.join(lines[:function.lineno - 1] + lines[function.end_lineno + 2:])


def remove_test_methods(text, names):
    lines = text.splitlines(keepends=True)
    nodes = [node for node in ast.walk(ast.parse(text))
             if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in sorted(nodes, key=lambda item: item.lineno, reverse=True):
        del lines[node.lineno - 2:node.end_lineno]
    return ''.join(lines)


def main():
    pins = json.loads((BASE / 'targeted_001/plan.json').read_bytes())['source_pins']
    expected = {Path(name).name: value for name, value in pins.items()
                if Path(name).parent == BASE and Path(name).name in {
                    'build_review_bundle.py', 'verify_review_bundle.py', 'test_review_bundle.py'}}
    candidate = {}
    text = (BASE / 'packager_source_before_final_guard_001/build_review_bundle.py').read_text(encoding='utf8')
    text = text.replace('import traceback\n', '').replace('        self.total_bytes = 0\n', '')
    text = text.replace("            self.total_bytes += len(payload)\n            require(self.total_bytes <= self.spec.get('max_uncompressed_bytes', 200 * 1024 * 1024),\n                    'bundle_size_budget_exceeded_while_collecting')\n", '')
    start = text.index('    try:\n        build(arguments.spec, arguments.output)')
    end = text.index("\n\n\nif __name__ == '__main__':", start)
    text = text[:start] + '    build(arguments.spec, arguments.output)' + text[end:]
    text = text.replace('    sys.exit(main())\n', '    main()\n')
    candidate['build_review_bundle.py'] = text
    text = (BASE / 'independent_freshpair_001/source/verify_review_bundle.py').read_text(encoding='utf8')
    block = "                    if 'baseline_archive' in plan:\n"
    start = text.index(block)
    end = text.index("                    require(type(row['wall_ms'])", start)
    text = text[:start] + text[end:]
    start = text.index("                    if 'median_ratio_previous_over_current' in context:\n")
    end = text.index("                checks.append({'kind': kind", start)
    text = text[:start] + text[end:]
    candidate['verify_review_bundle.py'] = text
    text = (BASE / 'packager_source_before_final_guard_001/test_review_bundle.py').read_text(encoding='utf8')
    text = remove_test_methods(text, {'test_complement_preserves_transfer_acks_and_unknown_new_events',
        'test_prediction_known_rejects_boolean_negative_and_missing_jobs',
        'test_collection_size_budget_fails_before_unrelated_large_pull'})
    text = text.replace('import hashlib\n', 'import hashlib\nimport importlib.util\n')
    candidate['test_review_bundle.py'] = text
    matches = {}
    for name, text in candidate.items():
        for newline, payload in (('LF', text.encode()), ('CRLF', text.replace('\n', '\r\n').encode())):
            actual = hashlib.sha256(payload).hexdigest()
            if actual == expected[name]:
                matches[name] = (payload, newline)
        print(json.dumps({'name': name, 'expected': expected[name], 'matched': name in matches,
                          'lf_candidate_sha256': hashlib.sha256(text.encode()).hexdigest()}))
    if len(matches) != len(expected):
        raise ValueError('exact_hash_recovery_incomplete_no_files_written')
    output = BASE / 'targeted_001/source_recovered_exact'
    output.mkdir(exist_ok=False)
    for name, (payload, newline) in matches.items():
        with (output / name).open('xb') as stream:
            stream.write(payload)
    manifest = {'status': 'exact_registered_hash_recovered', 'source': 'targeted_001/plan.json',
        'method': 'Reverse explicitly identified edits made after targeted execution; no candidate is accepted except exact original SHA256.',
        'files': {name: {'sha256': expected[name], 'newline': newline} for name, (_, newline) in matches.items()}}
    with (output / 'manifest.json').open('x', encoding='utf8') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
