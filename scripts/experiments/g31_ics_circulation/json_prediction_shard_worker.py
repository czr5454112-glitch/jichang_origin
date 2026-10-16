"""Fixed half-domain predictor process; no native or caller-selected code.

The new image is independent of the frozen single-worker image. Every RPC
constructs its own complete context and baseline, then evaluates exactly the
fixed half selected at process startup. Only compiled code survives a request.
"""
from __future__ import annotations
import time
BOOT_NS = time.perf_counter_ns()
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

MODES = ('shard0', 'shard1')


class Engine:
    def __init__(self, mode, codec):
        if mode not in MODES:
            raise ValueError('fixed_shard_mode')
        from scripts.experiments.g31_ics_circulation.json_prediction_worker import compiled_context_type
        self.mode, self.codec = mode, codec
        self.context, self.proof = compiled_context_type()
        self.proof = {**self.proof, 'fixed_ordinals': list(range(0, 16) if mode == 'shard0' else range(16, 32)),
            'physical_baselines_per_request': 1, 'full_dynamic_guards_per_request': True}

    def predict(self, snapshot):
        context = self.context(snapshot)
        actions, baseline = context.actions(), context.baseline()
        if len(actions) not in (0, 32):
            raise ValueError('unexpected_action_denominator')
        ordinals = self.proof['fixed_ordinals'] if actions else []
        predictions = [context.predict(actions[i]) for i in ordinals]
        return {'baseline': baseline, 'actions': actions, 'predictions': predictions,
            'ordinals': list(ordinals), 'snapshot_sha256': self.codec.sha_bytes(self.codec.encode(snapshot)),
            'action_domain_sha256': self.codec.sha_bytes(self.codec.encode(actions)),
            'physical_baselines': 1, 'candidate_queries': len(predictions)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--mode', choices=MODES, required=True)
    parser.add_argument('--admission', required=True)
    args = parser.parse_args()
    if sys.stdin.buffer.readline(256) != (args.admission+'\n').encode('ascii'):
        raise ValueError('missing_owned_job_admission')
    directory = args.image.resolve()
    raw = (directory/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.version:
        raise ValueError('bootstrap_version')
    manifest = json.loads(raw)
    helper_name = 'scripts/experiments/g31_ics_circulation/json_prediction_shard_image.py'
    helper = directory/helper_name
    helper_raw = helper.read_bytes()
    if hashlib.sha256(helper_raw).hexdigest() != manifest['files'][helper_name]:
        raise ValueError('bootstrap_helper_hash')
    spec = importlib.util.spec_from_file_location('_prediction_shard_image_bootstrap', helper)
    codec = importlib.util.module_from_spec(spec)
    exec(compile(helper_raw, str(helper), 'exec', dont_inherit=True), codec.__dict__)
    manifest, files = codec.verify_image(directory, args.version)
    entry = 'scripts/experiments/g31_ics_circulation/json_prediction_shard_worker.py'
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != manifest['files'][entry]:
        raise ValueError('bootstrap_entry_hash')
    loader = codec.ImageLoader(directory, files)
    sys.meta_path.insert(0, loader)
    # Same closed predict/close protocol and server codec as the old worker.
    from scripts.experiments.g31_ics_circulation.json_prediction_worker import serve
    engine = Engine(args.mode, codec)
    loaded = loader.seal()
    sys.stdout.buffer.write(codec.encode({'kind':'ready', 'version':args.version, 'mode':args.mode,
        'loaded_sources':loaded, 'proof':engine.proof, 'limits':manifest['limits'],
        'startup_post_import_wall_ns':time.perf_counter_ns()-BOOT_NS, 'native_authority':False}))
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
