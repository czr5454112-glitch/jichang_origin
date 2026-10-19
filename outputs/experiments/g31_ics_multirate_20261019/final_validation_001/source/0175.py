"""Closed source image and strict JSON protocol for a supplied-data experiment.

This module does not run a predictor or grant native authority. The source
image is a versioned process contract, not an OS sandbox against its owner.
"""
from __future__ import annotations
import ast
import hashlib
import importlib.abc
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import sys

SCHEMA = 'g31.json_prediction_image.v1'
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 64
MAX_NODES = 200000
MAX_REQUESTS = 64
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_ARTIFACT_NODES = 2000000
ENTRY = 'scripts.experiments.g31_ics_circulation.json_prediction_worker'
MODEL = 'scripts.experiments.g31_ics_circulation.public_preference_protection_request_context'


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _tree(value, depth=0, count=None, node_limit=None):
    count = [0] if count is None else count
    node_limit = MAX_NODES if node_limit is None else node_limit
    count[0] += 1
    if depth > MAX_DEPTH or count[0] > node_limit:
        raise ValueError('json_limit')
    if type(value) in (str, int, bool, type(None)):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('json_nonfinite')
        return
    if type(value) not in (dict, list):
        raise ValueError('json_non_builtin')
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError('json_non_string_key')
        for key, item in value.items():
            _tree(key, depth + 1, count, node_limit)
            _tree(item, depth + 1, count, node_limit)
    else:
        for item in value:
            _tree(item, depth + 1, count, node_limit)


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('json_duplicate_key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('json_nonfinite')


def encode(value):
    _tree(value)
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8') + b'\n'
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError('json_frame_limit')
    return raw


def decode(raw):
    if (type(raw) is not bytes or not raw.endswith(b'\n') or len(raw) > MAX_FRAME_BYTES
            or raw.count(b'\n') != 1 or raw.startswith(b'\xef\xbb\xbf')):
        raise ValueError('json_frame')
    value = json.loads(raw[:-1].decode('utf8'), object_pairs_hook=_pairs, parse_constant=_constant)
    _tree(value)
    return value


def read_frame(stream):
    raw = stream.readline(MAX_FRAME_BYTES + 1)
    if raw == b'':
        return None
    return decode(raw)


def artifact_encode(value):
    """Separate fixed artifact bound; it is never accepted by the wire parser."""
    _tree(value, node_limit=MAX_ARTIFACT_NODES)
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')+b'\n'
    if len(raw) > MAX_ARTIFACT_BYTES: raise ValueError('artifact_limit')
    return raw


def artifact_decode(raw):
    if type(raw) is not bytes or len(raw)>MAX_ARTIFACT_BYTES: raise ValueError('artifact_limit')
    value=json.loads(raw.decode('utf8'),object_pairs_hook=_pairs,parse_constant=_constant)
    _tree(value,node_limit=MAX_ARTIFACT_NODES)
    return value


def safe_name(name):
    path = PurePosixPath(name)
    if (type(name) is not str or '\\' in name or path.is_absolute() or '..' in path.parts
            or not name.endswith('.py') or str(path) != name):
        raise ValueError('unsafe_source_path')
    return name


def source_closure(root, entries):
    """Conservative repository AST imports, preserving package initializers."""
    root = Path(root).resolve()
    found = {}
    pending = list(entries)
    def resolve(name):
        for prefix in (root,root/'src'):
            stem = prefix.joinpath(*name.split('.'))
            for candidate in (stem.with_suffix('.py'), stem/'__init__.py'):
                if candidate.is_file():
                    return candidate
        return None
    while pending:
        module = pending.pop()
        path = resolve(module)
        if path is None:
            continue  # stdlib or a symbol imported from an already included module
        name = path.relative_to(root).as_posix()
        if name in found:
            continue
        data = path.read_bytes()
        found[name] = data
        package = module if path.name == '__init__.py' else module.rpartition('.')[0]
        for n in range(1, len(module.split('.'))):
            pending.append('.'.join(module.split('.')[:n]))
        for node in ast.walk(ast.parse(data, filename=name)):
            if isinstance(node, ast.Import):
                pending.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ''
                if node.level:
                    parts = package.split('.')
                    base = '.'.join(parts[:len(parts)-node.level+1] + ([base] if base else []))
                if base:
                    pending.append(base)
                    pending.extend(base + '.' + alias.name for alias in node.names if alias.name != '*')
    return dict(sorted(found.items()))


def build_image(root, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    files = source_closure(root, (ENTRY, MODEL, 'scripts.experiments.g31_ics_circulation.json_prediction_image'))
    for name, data in files.items():
        destination = directory/safe_name(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    manifest = {'schema': SCHEMA, 'entry': ENTRY, 'model': MODEL,
        'files': {name: sha_bytes(data) for name, data in files.items()},
        'limits': {'frame_bytes': MAX_FRAME_BYTES, 'depth': MAX_DEPTH,
                   'nodes': MAX_NODES, 'requests': MAX_REQUESTS},
        'scope': 'Code-only startup reuse; every request has fresh supplied data and complete dynamic guards.'}
    raw = encode(manifest)
    (directory/'manifest.json').write_bytes(raw)
    return sha_bytes(raw)


def verify_image(directory, expected_version):
    directory = Path(directory).resolve()
    raw = (directory/'manifest.json').read_bytes()
    if sha_bytes(raw) != expected_version:
        raise ValueError('source_version_mismatch')
    manifest = decode(raw)
    if (set(manifest) != {'schema', 'entry', 'model', 'files', 'limits', 'scope'}
            or manifest['schema'] != SCHEMA or manifest['entry'] != ENTRY or manifest['model'] != MODEL
            or manifest['limits'] != {'frame_bytes': MAX_FRAME_BYTES, 'depth': MAX_DEPTH,
                                     'nodes': MAX_NODES, 'requests': MAX_REQUESTS}
            or type(manifest['files']) is not dict or not manifest['files']):
        raise ValueError('source_manifest')
    files = {}
    for name, digest in manifest['files'].items():
        path = directory/safe_name(name)
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError('source_escape')
        data = path.read_bytes()
        if type(digest) is not str or sha_bytes(data) != digest:
            raise ValueError('source_bytes_changed')
        files[name] = data
    if set(files) != {path.relative_to(directory).as_posix() for path in directory.rglob('*.py')}:
        raise ValueError('unlisted_source')
    return manifest, files


class ImageLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Import only verified bytes, never stale pyc or a mutable checkout."""
    def __init__(self, directory, files):
        self.directory = Path(directory).resolve()
        self.files = dict(files)
        self.modules = {}
        self.packages = set()
        self.roots = set()
        self.sealed = False
        for name in files:
            parts = name[:-3].split('/')
            if parts[0] == 'src': parts = parts[1:]
            self.roots.add(parts[0])
            package = parts[-1] == '__init__'
            if package:
                parts.pop()
            self.modules['.'.join(parts)] = (name, package)
            for n in range(1, len(parts)):
                self.packages.add('.'.join(parts[:n]))

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in self.roots:
            if self.sealed:
                raise ImportError('new_project_import_after_READY')
            if fullname in self.modules:
                name, package = self.modules[fullname]
                return importlib.util.spec_from_file_location(fullname, self.directory/name,
                    loader=self, submodule_search_locations=[str((self.directory/name).parent)] if package else None)
            if fullname in self.packages:
                spec = importlib.util.spec_from_loader(fullname, self, is_package=True)
                return spec
            raise ImportError('unlisted_project_import')
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        if module.__name__ in self.modules:
            name, _ = self.modules[module.__name__]
            exec(compile(self.files[name], str(self.directory/name), 'exec', dont_inherit=True), module.__dict__)

    def get_source(self, fullname):
        name, _ = self.modules[fullname]
        return self.files[name].decode('utf8-sig')

    def seal(self):
        loaded = {}
        for name, module in tuple(sys.modules.items()):
            if name.split('.')[0] in self.roots:
                if name in self.modules:
                    filename, _ = self.modules[name]
                    if Path(module.__file__).resolve() != self.directory/filename or module.__loader__ is not self:
                        raise ValueError('foreign_loaded_project_source')
                    loaded[filename] = sha_bytes(self.files[filename])
                elif name not in self.packages:
                    raise ValueError('unlisted_loaded_module')
        self.sealed = True
        return dict(sorted(loaded.items()))
