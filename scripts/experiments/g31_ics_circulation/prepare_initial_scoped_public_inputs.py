"""Source-only preparation for initial-context and model scope sharing."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import sys
from . import public_live_obligation_initial_scoped_inputs as candidate
from . import measure_scoped_public_inputs_v2_six as utility

ROOT, OUT = utility.ROOT, utility.OUT
MODULE = 'scripts.experiments.g31_ics_circulation.prepare_initial_scoped_public_inputs'
PURE = OUT/'initial_scoped_public_inputs_pure_001'
PREVIOUS = OUT/'live_communication_scoped_inputs_v2_prepare_001'
PREVIOUS_PLAN = 'd64ab44189e5c7cb3d79b109072a6f29d22c9004cd8da872ceffc65dbc8a9fe9'
sha, read, ref, write, require = utility.sha, utility.read, utility.ref, utility.write, utility.require


def prepare(output):
    utility.frozen.base.no_execution_extensions(); pure = utility._pure_receipt(PURE, 22)
    require(sha(PREVIOUS/'plan.json') == PREVIOUS_PLAN, 'frozen_v2_full96_plan')
    old = read(PREVIOUS/'plan.json'); final = read(PREVIOUS/'final_receipt.json')
    require(len(old['source_sha256']) == 164 and final['status'] == 'exact_all96_original_checks_and_full_outputs'
        and final['full_output_exact'] == 96 and final['unknown_or_difference'] == 0
        and final['actual_collection_data_checks'] == 226 and final['actual_known_collection_data'] == 192
        and final['source_changed'] == [], 'v2_actual_full96')
    files = utility.frozen.image.source_closure(ROOT, (MODULE,
        'scripts.experiments.g31_ics_circulation.run_initial_scoped_public_inputs_pure',
        'tests.test_g31_circulation_initial_scoped_public_inputs'))
    for path,digest in old['source_sha256'].items():
        require(sha(path) == digest == sha(PREVIOUS/old['source_archive'][path]), 'frozen_v2_sources')
        files[str(Path(path).relative_to(ROOT))] = Path(path).read_bytes()
    for name,digest in pure['source_sha256'].items(): require(hashlib.sha256(files[name]).hexdigest() == digest, 'tested_sources')
    output.mkdir(exist_ok=False); pins = {}; archives = {}
    for name,data in sorted(files.items()):
        path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        pins[str(ROOT/name)] = hashlib.sha256(data).hexdigest(); archives[str(ROOT/name)] = str(path.relative_to(output))
    evidence = {}
    for folder,names in ((PURE, ('receipt.json', 'tests.xml', 'external_application_wall.json')),
        (PREVIOUS, ('plan.json', 'final_receipt.json', 'receipt.json', 'bounded_execution.json', 'external_application_wall.json'))):
        for name in names: evidence[str(folder/name)] = sha(folder/name)
    plan = {'status': 'prepared_source_only_unexecuted_model', 'schema': candidate.SCHEMA,
        'source_sha256': pins, 'source_archive': archives, 'evidence_sha256': evidence,
        'source_proof': candidate.source_proof(), 'candidate': ref(candidate.__file__),
        'environment': {'python': sys.executable, 'sha256': sha(sys.executable)},
        'pure_tests': 22, 'preparation_model_calls': 0, 'preparation_raw_decodes': 0, 'native_calls': 0,
        'future_cost_boundary': 'A original full build_initial plus scoped-v2 prediction; B one fresh scope for identical A/B initial guards/comparison and prediction. Both start before context/scope construction; prior predictor-only ABBA is not the comparator.',
        'sample_cleanup_certified': False, 'complete_request_100ms_certified': False}
    write(output/'plan.json', plan)
    write(output/'source_preparation.json', {'status': plan['status'], 'plan': ref(output/'plan.json'),
        'source_count': len(pins), 'pure_tests': 22, 'source_changed': [], 'model_calls': 0, 'native_calls': 0})


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); prepare(args.output.resolve())


if __name__ == '__main__': main()
