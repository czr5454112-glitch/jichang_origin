"""Build a byte-exact uncommitted review snapshot after an explicit final freeze."""
from __future__ import annotations

import argparse
import ast
from collections import deque
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
import zipfile

from verify_review_bundle import safe_name, verify


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = 'da8d39ed4e36b6db31e3a7a6b17b0f73b85eed9a'
IGNORED = {'__pycache__', '.pytest_cache', '.git', 'tmp', 'tmpdir'}
BINARY_NATIVE = {'.pyd', '.dll', '.exe', '.lib', '.obj', '.pdb'}
SHA_PATTERN = re.compile(r'[0-9a-fA-F]{64}')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT)


def normalized(path):
    return str(path).replace('\\', '/')


def is_path(value):
    return type(value) is str and (re.match(r'^[A-Za-z]:[/\\]', value) is not None
                                   or value.startswith('/'))


def pin_references(value, location=(), native=False):
    if type(value) is dict:
        native = native or 'evidence_sha256' in location
        if is_path(value.get('path')) and type(value.get('sha256')) is str \
                and SHA_PATTERN.fullmatch(value['sha256']):
            yield value['path'], value['sha256'].lower(), location, native
        for key, item in value.items():
            if is_path(key) and type(item) is str and SHA_PATTERN.fullmatch(item):
                yield key, item.lower(), location + (key,), native
            elif type(item) in (dict, list):
                yield from pin_references(item, location + (key,), native)
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from pin_references(item, location + (index,), native)


def selected_files(path):
    if path.is_file():
        yield path
    else:
        require(path.is_dir(), 'missing_selected_path:' + str(path))
        for item in sorted(path.rglob('*')):
            if item.is_file() and not any(part in IGNORED or 'pytest_tmp' in part or part.startswith('pytest-')
                                         or part.startswith('bundle_')
                                         for part in item.relative_to(path).parts[:-1]):
                yield item


def module_index():
    result = {}
    for directory, prefix in ((ROOT / 'scripts', 'scripts'), (ROOT / 'src', ''), (ROOT / 'tests', 'tests')):
        for path in directory.rglob('*.py'):
            if any(part in IGNORED for part in path.parts):
                continue
            pieces = list(path.relative_to(directory).with_suffix('').parts)
            if pieces[-1] == '__init__':
                pieces.pop()
            name = '.'.join(([prefix] if prefix else []) + pieces)
            result[name] = path.resolve()
    return result


class Collector:
    def __init__(self, spec):
        self.spec = spec
        self.entries = {}
        self.origins = {}
        self.by_hash = {}
        self.references = {}
        self.omissions = {}
        self.historical_gaps = {}
        self.pending = deque()
        self.parsed = set()
        self.imports = []
        self.dynamic_imports = []
        self.externals = set()
        self.reconstructions = []
        self.total_bytes = 0
        self.modules = module_index()
        self.reverse_modules = {path: name for name, path in self.modules.items()}

    def add_bytes(self, member, payload, original=None):
        safe_name(member)
        require(member not in self.entries or self.entries[member] == payload, 'member_collision:' + member)
        if member not in self.entries:
            self.total_bytes += len(payload)
            require(self.total_bytes <= self.spec.get('max_uncompressed_bytes', 200 * 1024 * 1024),
                    'bundle_size_budget_exceeded_while_collecting')
            self.entries[member] = payload
            self.by_hash.setdefault(digest(payload), []).append(member)
            self.pending.append(member)
        if original:
            self.origins[normalized(original)] = digest(payload)
            self.references[(normalized(original), digest(payload))] = member
        return member

    def add(self, path):
        path = Path(path).resolve()
        require(path.is_file() and path.suffix.lower() not in BINARY_NATIVE, 'not_review_file:' + str(path))
        require(path.is_relative_to(ROOT), 'outside_root_requires_explicit_attachment:' + str(path))
        return self.add_bytes('repo/' + path.relative_to(ROOT).as_posix(), path.read_bytes(), path)

    def import_closure(self, member, payload):
        if not member.startswith(('repo/scripts/', 'repo/src/', 'repo/tests/')) or not member.endswith('.py'):
            return
        path = (ROOT / member[5:]).resolve()
        module = self.reverse_modules.get(path)
        if not module:
            return
        package = module if path.name == '__init__.py' else module.rpartition('.')[0]
        tree = ast.parse(payload.decode('utf-8-sig'), filename=member)
        wanted = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                wanted.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    pieces = package.split('.')
                    require(node.level <= len(pieces), 'relative_import_outside_package:' + member)
                    base = '.'.join(pieces[:len(pieces) - node.level + 1])
                    base += ('.' + node.module) if node.module else ''
                else:
                    base = node.module or ''
                wanted.add(base)
                wanted.update(base + '.' + alias.name for alias in node.names
                              if alias.name != '*' and base + '.' + alias.name in self.modules)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ('import_module', 'spec_from_file_location'):
                argument = node.args[0] if node.args else None
                literal = argument.value if isinstance(argument, ast.Constant) and type(argument.value) is str else None
                self.dynamic_imports.append({'member': member, 'line': node.lineno,
                                             'operation': node.func.attr, 'literal': literal})
                if node.func.attr == 'import_module' and literal and not literal.startswith('.'):
                    wanted.add(literal)
        for name in sorted(wanted):
            if name in self.modules:
                target = self.add(self.modules[name])
                self.imports.append({'from': member, 'module': name, 'member': target})
            elif name.split('.')[0] in {'scripts', 'czr005', 'tests'}:
                require(any(candidate.startswith(name + '.') for candidate in self.modules),
                        'unresolved_project_import:' + member + ':' + name)
            elif name and name.split('.')[0] not in sys.stdlib_module_names:
                self.externals.add(name.split('.')[0])
        pieces = module.split('.')
        for count in range(1, len(pieces)):
            parent = '.'.join(pieces[:count])
            if parent in self.modules:
                self.add(self.modules[parent])

    def resolve_pin(self, original, expected, source, location, native):
        key = (normalized(original), expected)
        if key in self.references:
            return
        path = Path(original)
        if path.is_file() and path.suffix.lower() not in BINARY_NATIVE and path.resolve().is_relative_to(ROOT):
            payload = path.read_bytes()
            if digest(payload) == expected:
                if not native or 'repo/' + path.resolve().relative_to(ROOT).as_posix() in self.entries:
                    self.add(path)
                    return
        matches = self.by_hash.get(expected, [])
        if matches:
            self.references[key] = sorted(matches, key=lambda name: (Path(name).name != path.name, name))[0]
            return
        if native or path.suffix.lower() in BINARY_NATIVE:
            self.omissions[key] = {'original_path': original, 'sha256': expected,
                'reason': 'native_replay_environment_not_required_by_offline_checks', 'referenced_by': source}
            return
        explicit = self.spec.get('allowed_omissions', [])
        if any(normalized(row['path']) == key[0] and row['sha256'] == expected for row in explicit):
            row = next(row for row in explicit if normalized(row['path']) == key[0] and row['sha256'] == expected)
            self.omissions[key] = {'original_path': original, 'sha256': expected,
                                  'reason': row['reason'], 'referenced_by': source}
            return
        historical = self.spec.get('historical_unavailable_pins', [])
        matched = [row for row in historical if normalized(row['path']) == key[0] and row['sha256'] == expected]
        if matched:
            self.historical_gaps[key] = dict(matched[0], encountered_in=source)
            return
        if path.suffix == '.py' and path.resolve().is_relative_to(ROOT):
            relative = path.resolve().relative_to(ROOT).as_posix()
            if relative == 'tests/test_g31_foundation_later_control.py':
                payload = path.read_bytes()
                lines = payload.decode('utf-8-sig').replace('\r\n', '\n').splitlines(keepends=True)
                tree = ast.parse(''.join(lines))
                removed = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                           and node.name == 'test_collection_timing_segments_are_nested_not_additional_latency']
                if len(removed) == 1:
                    node = removed[0]
                    for trailing in range(3):
                        if any(line.strip() for line in lines[node.end_lineno:node.end_lineno + trailing]):
                            continue
                        text = ''.join(lines[:node.lineno - 1] + lines[node.end_lineno + trailing:])
                        for newline, candidate in (('LF', text.encode()), ('CRLF', text.replace('\n', '\r\n').encode())):
                            if digest(candidate) == expected:
                                member = self.add_bytes('historical_sources/' + expected + '/' + path.name, candidate)
                                self.references[key] = member
                                self.reconstructions.append({'original_path': original, 'member': member,
                                    'sha256': expected, 'current_source_sha256': digest(payload),
                                    'operation': 'remove_explicitly_authorized_new_timing_test',
                                    'removed_function': node.name, 'following_blank_lines_removed': trailing,
                                    'newline': newline, 'exact_registered_sha256_matched': True})
                                return
            for revision in dict.fromkeys((self.spec.get('base_commit', BASE), 'HEAD')):
                attempt = subprocess.run(['git', 'show', revision + ':' + relative], cwd=ROOT, capture_output=True)
                if attempt.returncode == 0 and digest(attempt.stdout) == expected:
                    member = self.add_bytes('historical_sources/' + expected + '/' + path.name, attempt.stdout)
                    self.references[key] = member
                    return
        raise ValueError('unresolved_required_pin:' + json.dumps({'path': original, 'sha256': expected,
                         'referenced_by': source, 'location': location}, ensure_ascii=False))

    def close(self):
        deferred = []
        while self.pending:
            member = self.pending.popleft()
            if member in self.parsed:
                continue
            self.parsed.add(member)
            payload = self.entries[member]
            self.import_closure(member, payload)
            if member.endswith(('.json', '.json.gz', '.jsonl')):
                plain = gzip.decompress(payload) if member.endswith('.gz') else payload
                documents = [json.loads(line) for line in plain.splitlines() if line.strip()] \
                    if member.endswith('.jsonl') else [json.loads(plain)]
                for document in documents:
                    for original, expected, location, native in pin_references(document):
                        deferred.append((original, expected, member, location, native))
        remaining = []
        for arguments in deferred:
            try:
                self.resolve_pin(*arguments)
            except ValueError as error:
                if str(error).startswith('unresolved_required_pin:'):
                    remaining.append((arguments, error))
                else:
                    raise
        if self.pending:
            self.close()
        for arguments, error in remaining:
            self.resolve_pin(*arguments)
        if self.pending:
            self.close()


def smoke(extracted, modules):
    program = '''import importlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root), str(root / 'src')]
def deny(event, arguments):
    if event in ('subprocess.Popen', 'os.system', 'os.exec', 'socket.connect'):
        raise RuntimeError('import_smoke_external_side_effect:' + event)
sys.addaudithook(deny)
loaded = []
for name in json.loads(sys.argv[2]):
    module = importlib.import_module(name)
    loaded.append({'module': name, 'path': str(pathlib.Path(module.__file__).resolve().relative_to(root))})
for name, module in tuple(sys.modules.items()):
    filename = getattr(module, '__file__', None)
    if filename and name.split('.')[0] in ('scripts', 'czr005'):
        assert pathlib.Path(filename).resolve().is_relative_to(root), (name, filename)
print(json.dumps({'status': 'passed', 'entry_modules': loaded, 'native_executions': 0}))
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', program,
                             str(extracted / 'repo'), json.dumps(modules)],
                            cwd=extracted, capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, 'relocated_import_failure:' + result.stdout + result.stderr)
    return json.loads(result.stdout)


def build(spec_path, output):
    spec_path, output = spec_path.resolve(), output.resolve()
    require(output.is_relative_to(HERE), 'output_must_stay_in_refresh_next')
    require(not output.exists(), 'output_already_exists')
    spec = json.loads(spec_path.read_bytes())
    require(spec['schema'] == 'g31.refresh.bundle_spec.v1', 'spec_schema')
    require(spec.get('final_freeze_authorized') is True, 'final_freeze_not_authorized')
    require(spec['base_commit'] == BASE, 'unexpected_review_baseline')
    require(git('rev-parse', 'HEAD').decode().strip() == BASE, 'HEAD_changed_reauthorize_snapshot')
    selected = Collector(spec)
    for name in spec['include']:
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT), 'include_outside_repository')
        for item in selected_files(path):
            if not item.resolve().is_relative_to(output):
                selected.add(item)
    for attachment in spec.get('attachments', []):
        path = Path(attachment['path']).resolve()
        payload = path.read_bytes()
        require(digest(payload) == attachment['sha256'], 'attachment_changed:' + str(path))
        selected.add_bytes('attachments/' + safe_name(attachment['name']), payload, path)
    for name in ('pyproject.toml', 'requirements.txt', '.gitattributes'):
        if (ROOT / name).is_file():
            selected.add(ROOT / name)
    selected.add(Path(__file__))
    selected.add(HERE / 'verify_review_bundle.py')
    for module in spec['entry_modules']:
        require(module in selected.modules, 'unknown_smoke_module:' + module)
        selected.add(selected.modules[module])
    selected.close()
    failed_packages = []
    for directory in sorted(HERE.glob('bundle_*')):
        if directory.is_dir() and directory != output:
            for name in ('bundle_build_failure.json', 'bundle_validation.json'):
                path = directory / name
                if path.is_file():
                    member = selected.add_bytes('prior_packaging_attempts/' + directory.name + '/' + name, path.read_bytes(), path)
                    failed_packages.append({'original_directory': str(directory), 'receipt_member': member})
            for path in sorted((directory / 'source').glob('*.py')):
                selected.add_bytes('prior_packaging_attempts/' + directory.name + '/source/' + path.name,
                                   path.read_bytes(), path)
    selected.add_bytes('PRIOR_PACKAGING_ATTEMPTS.json', encode({'attempts': failed_packages,
        'prior_zip_or_extraction_trees_recursively_included': False}))
    request = ROOT / spec['review_request']
    selected.add(request)
    selected.add_bytes('00_给GPTPro的审阅请求.md', request.read_bytes())
    selected.add_bytes('verify_bundle.py', (HERE / 'verify_review_bundle.py').read_bytes())
    selected.add_bytes('BUNDLE_SPEC.json', spec_path.read_bytes())
    selected.add_bytes('AUDIT_SPEC.json', encode({'checks': spec.get('checks', [])}))
    selected.add_bytes('PATH_MAP.json', encode({'schema': 'g31.review.original_path_mapping.v1',
        'original_repository_root': str(ROOT), 'original_evidence_bytes_rewritten': False,
        'references': [{'original_path': key[0], 'sha256': key[1], 'member': member}
                       for key, member in sorted(selected.references.items())]}))
    selected.add_bytes('NATIVE_DEPENDENCIES_NOT_BUNDLED.json', encode({
        'fresh_native_execution_portable': False, 'dependencies': list(selected.omissions.values()),
        'reason': 'Original Windows interpreter, native026/native027 builds and admission paths are not a portable runtime image.'}))
    selected.add_bytes('HISTORICAL_SOURCE_GAPS.json', encode({
        'historical_source_closure_complete': not bool(selected.historical_gaps),
        'gaps': list(selected.historical_gaps.values()),
        'scope': 'Explicitly enumerated unavailable historical intermediate source versions only. Original registered hashes remain unchanged; no byte-exact reproduction of those versions is claimed. Current final-tested and native-executed versions are not waived.'}))
    selected.add_bytes('SOURCE_CLOSURE.json', encode({'static_project_imports': selected.imports,
        'dynamic_import_sites_for_review': selected.dynamic_imports,
        'exact_hash_historical_reconstructions': selected.reconstructions,
        'external_import_roots': sorted(selected.externals),
        'entry_modules_for_relocated_import_smoke': spec['entry_modules'],
        'limitations': 'Static import closure plus recorded source/evidence pins; dynamic nonliteral imports require explicit input selection and entry-point smoke, not a universal execution proof.'}))
    selected.add_bytes('SNAPSHOT_IDENTITY.json', encode({'base_commit': BASE,
        'branch': git('branch', '--show-current').decode().strip(),
        'snapshot_kind': 'uncommitted_workspace_bytes', 'commit_or_push_performed_by_packager': False,
        'fresh_native_execution_portable': False,
        'git_status_tracked': git('status', '--short', '--untracked-files=no').decode(),
        'all_files_equal_HEAD_not_claimed': True}))
    selected.add_bytes('changes_from_da8d39ed.patch', git('diff', '--binary', BASE, '--',
        'scripts', 'src', 'tests', 'configs', 'docs/g31_ics_circulation'))
    selected.add_bytes('README.md', ('''# G31 独立审阅包

先读 `00_给GPTPro的审阅请求.md`。本包是未提交的源码与证据逐字节快照；基线为 da8d39ed，不声称已推送。

独立轻量复核（Python 3.11+，只用标准库；不 import 项目、不训练、不推理、不启动 native）：

```text
python verify_bundle.py .
python verify_bundle.py /path/to/bundle.zip
```

`MANIFEST.sha256.json` 逐字节覆盖除自身外全部文件；自身哈希以交付 ZIP SHA 为外部身份。
`PATH_MAP.json` 将原绝对路径与特定 SHA 映射到实际包成员。原始 JSON、换行、浮点/类型与失败记录均不改写。
`repo/` 是可审阅/导入的当前源闭包；`historical_sources/` 仅存已登记旧版本，不会暗中替换当前 import。
独立核查范围由 `AUDIT_SPEC.json` 明示；计时重算只重算已有数字，不是重跑性能实验或 100 ms 证明。
失败、未知、未执行证据不升级为成功。测试 XML 是保存的执行结果，不宣称解压后已重跑测试。
`SOURCE_CLOSURE.json` 与 `IMPORT_SMOKE.json` 说明真实依赖及隔离导入结果；外部库不随包安装。
`HISTORICAL_SOURCE_GAPS.json` 单独列明未保留的旧中间源码版本；原登记 SHA 不改写，不把这些历史缺项伪称已复核，当前最终测试/原生执行版本不能借此豁免。

**本包不是可移植 native 部署镜像。** Windows 解释器、native026/native027 二进制/构建与旧准入路径没有全部打包，见 `NATIVE_DEPENDENCIES_NOT_BUNDLED.json`。
不得通过修改旧哈希、绝对路径、保护条件来伪造 fresh-native 成功。轻量复核与原生重放是两个不同门。
文献正文不在包内转授权转载；以仓库文献映射文档中的原作者 URL、版本及章节支持范围为准。
''').encode())
    total = sum(len(payload) for payload in selected.entries.values())
    require(total <= spec.get('max_uncompressed_bytes', 200 * 1024 * 1024), 'bundle_size_budget_exceeded')
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='bundle_import_', dir=output) as temporary:
        extracted = Path(temporary)
        for name, payload in selected.entries.items():
            target = extracted / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        import_result = smoke(extracted, spec['entry_modules'])
    selected.add_bytes('IMPORT_SMOKE.json', encode(import_result))
    for original, expected in selected.origins.items():
        require(digest(Path(original).read_bytes()) == expected, 'input_changed_during_packaging:' + original)
    manifest = {'schema': 'g31.refresh.review_bundle.v1', 'manifest_self_hash_excluded': True,
        'files': [{'path': name, 'bytes': len(payload), 'sha256': digest(payload)}
                  for name, payload in sorted(selected.entries.items())]}
    selected.entries['MANIFEST.sha256.json'] = encode(manifest)
    archive = output / 'G31_20261017_服务刷新与学习阶段审阅证据.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for name, payload in sorted(selected.entries.items()):
            zipped.writestr(name, payload)
    verification = verify(archive)
    verification.update({'archive': str(archive), 'zip_sha256': digest(archive.read_bytes()),
                         'zip_bytes': archive.stat().st_size})
    (output / 'bundle_validation.json').write_bytes(encode(verification))
    (output / 'G31_给GPTPro的审阅请求_20261017.md').write_bytes(request.read_bytes())
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    try:
        build(arguments.spec, arguments.output)
    except Exception:
        failure = {'status': 'failed', 'exception': traceback.format_exc(),
                   'native_executions': 0, 'output': str(arguments.output)}
        output = arguments.output.resolve()
        if output.is_relative_to(HERE) and output.is_dir() and not (output / 'bundle_build_failure.json').exists():
            with (output / 'bundle_build_failure.json').open('xb') as stream:
                stream.write(encode(failure))
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
