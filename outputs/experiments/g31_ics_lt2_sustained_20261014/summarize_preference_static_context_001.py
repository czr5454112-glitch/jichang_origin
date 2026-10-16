"""Small saved-output summary; no policy inputs, simulation, or timing rerun."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PAIR = OUT / 'preference_static_context_pair_001'
TESTS = OUT / 'preference_static_context_tests_005'
TARGET = OUT / 'preference_static_context_summary_001.json'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def stats(values):
    return {'count': len(values), 'minimum': min(values), 'median': statistics.median(values),
        'maximum': max(values), 'sum': sum(values)}


def main():
    if TARGET.exists(): raise ValueError('preserve_summary')
    plan, result = read(PAIR / 'worker/plan.json'), read(PAIR / 'worker/report.json')
    launch, external = read(PAIR / 'receipt.json'), read(PAIR / 'external_wall.json')
    assert result['status'] == 'passed_exact_pure_static_context_pair' and result['source_changed'] == []
    assert launch['status'] == 'child_passed' and launch['process']['exitcode'] == 0 and external['exit_code'] == 0
    assert len(result['paired_rows']) == 24 and len(result['cold_full32_rows']) == 12 and len(result['budget_probes']) == 6
    for relative, digest in plan['source_sha256'].items():
        assert sha(ROOT / relative) == sha(PAIR / 'worker/source' / relative) == digest
    for path, digest in plan['input_evidence_sha256'].items(): assert sha(path) == digest
    testplan = read(TESTS / 'worker/plan.json')
    core = ['scripts/experiments/g31_ics_circulation/public_preference_static_context.py',
        'scripts/experiments/g31_ics_circulation/preference_wall_budget.py',
        'tests/test_g31_circulation_preference_static_context.py']
    for relative in core:
        digest = testplan['source_sha256'].get(relative, testplan['source_sha256'].get(str(Path(relative))))
        assert sha(ROOT / relative) == sha(TESTS / 'worker/source' / relative) == digest
    xml = ET.parse(TESTS / 'worker/tests.xml').getroot().find('testsuite')
    assert [int(xml.attrib[k]) for k in ('tests', 'failures', 'errors', 'skipped')] == [45, 0, 0, 0]
    reference = [r['timings']['reference_context']['wall_ns']/1e6 for r in result['paired_rows']]
    warm = [r['timings']['static_warm']['wall_ns']/1e6 for r in result['paired_rows']]
    cold = [r['wall_ns']/1e6 for r in result['cold_full32_rows']]
    probes = []
    for probe in result['budget_probes']:
        envelope, response = probe['envelope'], probe['response']
        assert response['declared_action_count'] == 32 and response['action_domain_scope'] == 'derived_inside_request'
        assert response['finalization']['status'] == 'unknown_no_native_final_revalidation'
        assert envelope['complete_request_100ms_certified'] is False
        probes.append({'case': probe['case'],
            'evaluated': sum(r['status'] == 'evaluated' for r in response['candidate_rows']),
            'unknown_unexecuted': sum(r['status'] == 'unknown_unexecuted' for r in response['candidate_rows']),
            'admission_through_codec_ms': envelope['observed_admission_through_codec_ns']/1e6,
            'outer_function_ms': probe['outer_function']['wall_ns']/1e6,
            'internal_overrun_ms': envelope['observed_overrun_ns']/1e6,
            'finalization': response['finalization']['status'], 'native_permission_verified': False})
    evidence = {str(p.relative_to(OUT)): sha(p) for p in (PAIR / 'worker/plan.json', PAIR / 'worker/report.json',
        PAIR / 'worker/supplied_inputs.json', PAIR / 'receipt.json', PAIR / 'external_wall.json',
        TESTS / 'worker/plan.json', TESTS / 'worker/tests.xml', TESTS / 'worker/source_after.json',
        TESTS / 'receipt.json', TESTS / 'external_wall.json', Path(__file__))}
    failures = []
    for name in ('preference_static_context_tests_001', 'preference_static_context_tests_002'):
        prior = read(OUT / name / 'receipt.json')
        assert prior['process']['status'] == 'hard_timeout'
        evidence[f'{name}/receipt.json'] = sha(OUT / name / 'receipt.json')
        evidence[f'{name}/external_wall.json'] = sha(OUT / name / 'external_wall.json')
        failures.append({'attempt': name, 'status': prior['status'], 'hard_limit_seconds': 120,
            'external_wall_seconds': read(OUT / name / 'external_wall.json')['whole_python_application_wall_seconds'],
            'complete_test_pass': False})
    report = {'schema': 'g31.static_context.saved_summary.v1', 'status': 'source_bound_pure_results',
        'recorded_utc': datetime.now(timezone.utc).isoformat(), 'evidence_sha256': evidence,
        'test_count': 45, 'test_failures': 0, 'test_core_sources_unchanged': True,
        'test_helper_change_after_tests': 'Measurement driver only gained incremental partial evidence/log writes in profile mode after005; tested core modules/test bytes remain exact, actual pair archives its exact driver.',
        'paired_complete_output_equality': 'All24 pair rows, each complete ordered32 outputs, plus12 cold rows; six cases and both supplied owner bundles.',
        'reference_context_full32_wall_ms': stats(reference), 'static_warm_full32_wall_ms': stats(warm),
        'static_warm_reduction_fraction': 1-sum(warm)/sum(reference),
        'static_cold_full32_wall_ms': stats(cold), 'factory_build_wall_ms': result['factory_cold_build']['wall_ns']/1e6,
        'factory_build_cpu_ms': result['factory_cold_build']['cpu_ns']/1e6,
        'profile_full_python_application_wall_seconds': external['whole_python_application_wall_seconds'],
        'all_full32_warm_over100ms': all(v > 100 for v in warm),
        'budget_probes': probes, 'prior_failed_attempts': failures, 'native_executions': 0,
        'complete_business_request_100ms_certified': False,
        'limits': ['Warm comparison retains source identity and dynamic guards; cold cost is separate and not averaged away.',
            'No isolated speed or future deadline guarantee. Other workspace workers may have been active.',
            'Budget shell is an adaptive method interface with a common total/reserve/candidate cap; existing four scheduling methods and native final validation have not been integrated.',
            'The six illustrative100ms budget probes retain all unexecuted candidates and explicitly end unknown_no_native_final_revalidation. Their reserved20ms is not a proven native commit/ACK bound.',
            'Admission-to-codec and complete outer function are both retained; original observation/transport/native source-receiver validation/commit/ACK are absent, so these are not complete business request measurements.',
            'Factory inventory is code-only; it does not retain observations, score potentials or candidate state across requests.',
            '001/002 test timeouts remain failures, not converted into passes.']}
    with TARGET.open('x', encoding='utf8') as stream: json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'path': str(TARGET), 'sha256': sha(TARGET), 'warm_reduction': report['static_warm_reduction_fraction'],
        'reference_ms': report['reference_context_full32_wall_ms'], 'warm_ms': report['static_warm_full32_wall_ms'],
        'cold_ms': report['static_cold_full32_wall_ms'], 'factory_ms': report['factory_build_wall_ms'],
        'external_seconds': report['profile_full_python_application_wall_seconds'], 'budget_probes': probes}))


if __name__ == '__main__': main()
