"""Private fixed-version JSON predictor; no native session or remote code API.

Run the archived file with -I -S. Only trusted startup builds code; JSON data
can never name modules, commands, callbacks, proof labels or completion values.
"""
from __future__ import annotations
import time
BOOT_NS = time.perf_counter_ns()
import argparse
import ast
import copy
import hashlib
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import textwrap
from types import FunctionType, SimpleNamespace


def compiled_context_type():
    """Move exactly the two implementation checks to startup, not input guards."""
    from scripts.experiments.g31_ics_circulation import public_preference_protection_request_context as original
    base, proof = original.base, original.proof
    for module, expected in ((base, original.EXPECTED_CONTEXT), (proof, original.EXPECTED_CUT)):
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError('unreviewed_startup_context')
    source_proof = proof.source_proof()
    validate, action_check, guard_proof = base.compile_guards()
    def compiler():
        return validate, action_check, copy.deepcopy(guard_proof)
    init = base.RequestContext.__init__
    private_init = FunctionType(init.__code__, {**init.__globals__, 'compile_guards': compiler},
        init.__name__, init.__defaults__, init.__closure__)
    private_init.__kwdefaults__ = copy.deepcopy(init.__kwdefaults__)
    facade = SimpleNamespace(original=base.original, RequestContext=SimpleNamespace(
        __init__=private_init, predict=base.RequestContext.predict, describe=base.RequestContext.describe))
    source = ast.parse(textwrap.dedent(inspect.getsource(original.ProtectionRequestContext.__init__))).body[0]
    if (not isinstance(source.body[0], ast.For)
            or ast.unparse(source.body[0].iter) != '((base, EXPECTED_CONTEXT), (proof, EXPECTED_CUT))'
            or ast.unparse(source.body[1]) != 'proof.source_proof()'):
        raise ValueError('startup_check_AST_changed')
    initial = ast.dump(ast.Module(body=source.body[2:], type_ignores=[]), include_attributes=False)
    source.body = source.body[2:]
    if ast.dump(ast.Module(body=source.body, type_ignores=[]), include_attributes=False) != initial:
        raise ValueError('dynamic_constructor_changed')
    namespace = {**original.ProtectionRequestContext.__init__.__globals__, 'base': facade}
    # Keep the original class name so Python's private slot name mangling is
    # identical; this temporary class never replaces the imported original.
    wrapper = ast.ClassDef(name='ProtectionRequestContext', bases=[], keywords=[], body=[source], decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[])),
                 __file__ + ':startup_checks_only', 'exec'), namespace)
    context = type('_FixedVersionProtectionRequestContext', (original.ProtectionRequestContext,),
                   {'__slots__': (), '__init__': namespace['ProtectionRequestContext'].__init__})
    return context, {'guard_compilations': 1, 'source_proof': source_proof,
        'constructor_remainder_AST_sha256': hashlib.sha256(initial.encode()).hexdigest(),
        'per_request_inventory': False, 'request_data_cache': False}


class Engine:
    def __init__(self, mode):
        if mode not in ('reference', 'compiled'):
            raise ValueError('invalid_mode')
        self.mode = mode
        if mode == 'compiled':
            self.context, self.proof = compiled_context_type()
        else:
            from scripts.experiments.g31_ics_circulation.public_preference_protection_request_context import ProtectionRequestContext
            self.context = ProtectionRequestContext
            self.proof = {'guard_compilations': 0, 'per_request_inventory': True, 'request_data_cache': False}

    def predict(self, snapshot):
        context = self.context(snapshot)
        actions = context.actions()
        baseline = context.baseline()
        if len(actions) not in (0, 32):
            raise ValueError('unexpected_action_denominator')
        predictions = [context.predict(action) for action in actions]
        # No context, snapshot, label, potential or output is stored on Engine.
        return {'baseline': baseline, 'actions': actions, 'predictions': predictions}


class Protocol:
    def __init__(self, version, engine, codec):
        self.version, self.engine, self.codec = version, engine, codec
        self.sequence = 0
        self.identities = set()
        self.closed = False

    def accept(self, value):
        if self.closed or type(value) is not dict:
            raise ValueError('closed_or_invalid_request')
        if value.get('kind') == 'close':
            if set(value) != {'kind', 'version', 'sequence'} or value['version'] != self.version or type(value['sequence']) is not int or value['sequence'] != self.sequence + 1:
                raise ValueError('close_identity')
            self.closed = True
            return None
        if (set(value) != {'kind', 'version', 'sequence', 'request_id', 'snapshot'} or value['kind'] != 'predict'
                or value['version'] != self.version or type(value['sequence']) is not int
                or value['sequence'] != self.sequence + 1 or self.sequence >= self.codec.MAX_REQUESTS
                or type(value['request_id']) is not str or not 1 <= len(value['request_id']) <= 128
                or value['request_id'] in self.identities or type(value['snapshot']) is not dict):
            raise ValueError('request_identity_or_schema')
        self.sequence += 1
        self.identities.add(value['request_id'])
        started = time.perf_counter_ns()
        payload = self.engine.predict(value['snapshot'])
        return {'kind': 'prediction', 'version': self.version, 'sequence': self.sequence,
            'request_id': value['request_id'], 'payload': payload,
            'compute_wall_ns': time.perf_counter_ns() - started,
            'complete_100ms_certified': False, 'native_authority': False}


def serve(stdin, stdout, version, engine, codec, final_check):
    protocol = Protocol(version, engine, codec)
    while True:
        value = codec.read_frame(stdin)
        if value is None:
            raise ValueError('EOF_without_close')
        response = protocol.accept(value)
        if response is None:
            checked = final_check()
            stdout.write(codec.encode({'kind': 'closed', 'version': version, 'requests': protocol.sequence,
                'source_unchanged': checked, 'worker_post_import_wall_ns': time.perf_counter_ns()-BOOT_NS}))
            stdout.flush()
            return
        # Encoding and synchronous output are part of the live RPC envelope.
        stdout.write(codec.encode(response))
        stdout.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--mode', choices=('reference', 'compiled'), required=True)
    parser.add_argument('--admission', required=True)
    args = parser.parse_args()
    if sys.stdin.buffer.readline(256) != (args.admission + '\n').encode('ascii'):
        raise ValueError('missing_owned_job_admission')
    directory = args.image.resolve()
    manifest_raw = (directory/'manifest.json').read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != args.version:
        raise ValueError('bootstrap_version')
    # Bootstrap helper is verified before executing any repository code.
    manifest = json.loads(manifest_raw)
    helper_name = 'scripts/experiments/g31_ics_circulation/json_prediction_image.py'
    helper = directory/helper_name
    if hashlib.sha256(helper.read_bytes()).hexdigest() != manifest['files'][helper_name]:
        raise ValueError('bootstrap_helper_hash')
    spec = importlib.util.spec_from_file_location('_prediction_image_bootstrap', helper)
    codec = importlib.util.module_from_spec(spec)
    exec(compile(helper.read_bytes(), str(helper), 'exec', dont_inherit=True), codec.__dict__)
    manifest, files = codec.verify_image(directory, args.version)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != manifest['files']['scripts/experiments/g31_ics_circulation/json_prediction_worker.py']:
        raise ValueError('bootstrap_entry_hash')
    loader = codec.ImageLoader(directory, files)
    sys.meta_path.insert(0, loader)
    engine = Engine(args.mode)
    loaded = loader.seal()
    sys.stdout.buffer.write(codec.encode({'kind': 'ready', 'version': args.version, 'mode': args.mode,
        'loaded_sources': loaded, 'proof': engine.proof,
        'startup_post_import_wall_ns': time.perf_counter_ns()-BOOT_NS,
        'limits': manifest['limits'], 'native_authority': False}))
    sys.stdout.buffer.flush()
    def final_check():
        codec.verify_image(directory, args.version)
        if loader.seal() != loaded:
            raise ValueError('loaded_sources_changed')
        return True
    serve(sys.stdin.buffer, sys.stdout.buffer, args.version, engine, codec, final_check)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
