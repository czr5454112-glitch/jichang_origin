"""New fixed-image two-choice worker; no native access or runtime code input.

Atomic baseline/candidate overruns are returned, never silently interrupted or
relabeled feasible. The caller still owes final native revalidation and ACK.
Only code is retained across requests; the context/results are request-local.
"""
from __future__ import annotations
import time
BOOT_NS = time.perf_counter_ns()
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

MODE = 'initial_A_two'


class Engine:
    def __init__(self, mode, codec):
        if mode != MODE:
            raise ValueError('fixed_initial_A_mode')
        from scripts.experiments.g31_ics_circulation.json_prediction_worker import compiled_context_type
        from scripts.experiments.g31_ics_circulation import initial_owner_route_contract as contract
        self.context, proof = compiled_context_type()
        self.contract, self.codec = contract, codec
        self.proof = {**proof, 'participation_contract_sha256': contract.contract_sha256(),
            'logical_choices': 2, 'baseline_is_default_candidate': True,
            'candidate_simulations_maximum': 1, 'native_authority': False}

    def predict(self, request):
        c = self.contract
        start = time.perf_counter_ns()
        if (type(request) is not dict or set(request) != {'schema','bundle','root_started_ns',
                'decision_cutoff_ns','root_deadline_ns','participation_contract_sha256'}
                or request['schema'] != c.SCHEMA or type(request['bundle']) is not dict
                or request['participation_contract_sha256'] != c.contract_sha256()
                or any(type(request[k]) is not int for k in ('root_started_ns','decision_cutoff_ns','root_deadline_ns'))
                or not 0 <= request['root_started_ns'] <= start
                or request['root_deadline_ns']-request['root_started_ns'] != c.BUDGET_NS
                or request['decision_cutoff_ns'] != request['root_deadline_ns']-c.FINALIZATION_RESERVE_NS):
            raise ValueError('initial_A_request_contract_or_clock')
        snapshot = request['bundle']
        digest = self.codec.sha_bytes(self.codec.encode(snapshot))
        result = {'schema': c.SCHEMA, 'snapshot_sha256': digest,
            'participation_contract_sha256': c.contract_sha256(), 'baseline': None,
            'actions': [], 'predictions': [], 'selection': {'status': 'unknown_unexecuted', 'choice': None},
            'counts': {'logical_choices': 2, 'baseline_evaluation_calls': 0,
                'complete_baselines': 0, 'additional_candidate_calls': 0},
            'budget': {'worker_started_ns': start, 'root_started_ns': request['root_started_ns'],
                'decision_cutoff_ns': request['decision_cutoff_ns'], 'root_deadline_ns': request['root_deadline_ns'],
                'finalization_reserve_is_WCET': False},
            'native_authority': False, 'complete_100ms_certified': False,
            'full_32_search_performed': False}
        if start >= request['decision_cutoff_ns']:
            result['budget']['worker_finished_ns'] = time.perf_counter_ns()
            result['budget']['atomic_overrun'] = False
            result['selection']['status'] = 'unknown_no_baseline_budget'
            return result
        context = self.context(snapshot)  # Full guards/isolation/potential/full baseline.
        baseline = context.baseline()
        result['baseline'] = baseline
        result['counts']['baseline_evaluation_calls'] = 1
        result['counts']['complete_baselines'] = int(c.completion(baseline) is not None)
        actions = context.actions()
        after_baseline = time.perf_counter_ns()
        candidate = {'status': 'unknown_unexecuted_budget', 'completion': {},
                     'native_protection_certified': False}
        if actions:
            result['actions'] = c.fixed_actions(actions)
        if result['actions'] and c.completion(baseline) is not None and after_baseline < request['decision_cutoff_ns']:
            candidate = context.predict(result['actions'][1])
            result['counts']['additional_candidate_calls'] = 1
        after_candidate = time.perf_counter_ns()
        # Reuse the exact full baseline result as the default candidate. No
        # duplicate simulation; separate return objects prevent aliasing.
        result['predictions'] = [copy.deepcopy(baseline), candidate] if result['actions'] else []
        expired = after_candidate >= request['decision_cutoff_ns']
        result['selection'] = c.select(baseline, candidate, decision_budget_expired=expired)
        result['budget'].update(baseline_finished_ns=after_baseline,
            candidate_finished_ns=after_candidate, atomic_overrun=expired,
            candidate_unexecuted=result['counts']['additional_candidate_calls'] == 0)
        result['budget']['worker_finished_ns'] = time.perf_counter_ns()
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--mode', choices=(MODE,), required=True)
    parser.add_argument('--admission', required=True)
    args = parser.parse_args()
    if sys.stdin.buffer.readline(256) != (args.admission+'\n').encode('ascii'):
        raise ValueError('missing_owned_job_admission')
    directory = args.image.resolve()
    raw = (directory/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.version:
        raise ValueError('bootstrap_version')
    manifest = json.loads(raw)
    helper_name = 'scripts/experiments/g31_ics_circulation/initial_owner_route_image.py'
    helper = directory/helper_name
    helper_raw = helper.read_bytes()
    if hashlib.sha256(helper_raw).hexdigest() != manifest['files'][helper_name]:
        raise ValueError('bootstrap_helper_hash')
    spec = importlib.util.spec_from_file_location('_initial_owner_image_bootstrap', helper)
    codec = importlib.util.module_from_spec(spec)
    exec(compile(helper_raw, str(helper), 'exec', dont_inherit=True), codec.__dict__)
    manifest, files = codec.verify_image(directory, args.version)
    entry = 'scripts/experiments/g31_ics_circulation/initial_owner_route_worker.py'
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != manifest['files'][entry]:
        raise ValueError('bootstrap_entry_hash')
    loader = codec.ImageLoader(directory, files)
    sys.meta_path.insert(0, loader)
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
