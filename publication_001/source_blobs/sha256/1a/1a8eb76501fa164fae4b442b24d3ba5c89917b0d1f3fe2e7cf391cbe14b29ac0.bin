"""Small saved-summary/source receipt only; never opens raw endpoint archives."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from . import complete_root_evidence_candidate as candidate

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
SUMMARY = OUT/'initial_owner_route_gate_independent_actual_review_001/report.json'
SUMMARY_SHA = '95361ce13acfd4711a3bc3c68fe37fb51aae1a9a841dd56ed3ddaae693bc9849'
PURE = OUT/'complete_root_evidence_codec_pure_001'
PURE_SHA = '3df735e6ef69fec3731e2f4691a80b686a115c8e803de152f16be08c51b89591'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference(path):
    return {'path': str(path.resolve()), 'sha256': digest(path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if digest(SUMMARY) != SUMMARY_SHA or digest(PURE/'receipt.json') != PURE_SHA:
        raise ValueError('analysis_saved_reference_changed')
    saved = json.loads(SUMMARY.read_text(encoding='utf8'))
    pure = json.loads((PURE/'receipt.json').read_text(encoding='utf8'))
    if pure['status'] != 'passed' or pure['tests'] != 68 or pure['source_changed']:
        raise ValueError('analysis_functional_gate')
    for name, expected in pure['source_sha256'].items():
        if digest(ROOT/name) != expected or digest(PURE/'source'/name) != expected:
            raise ValueError('analysis_functional_source_changed:' + name)
    body_name = 'evidence_body_construction_normalization_encoding'
    tail_name = 'outside_return_ledger_codec_tail'
    rows = {}
    for name, row in saved['rows'].items():
        parts = row['warm_boundary_partition_ms']
        rows[name] = {'closed': row['root']['closed'], 'warm_ms': row['root']['warm_ms'],
            'body_ms': parts[body_name], 'tail_ms': parts[tail_name],
            'body_plus_tail_ms': parts[body_name] + parts[tail_name],
            'postcheck_through_last_observation_ms': parts['postcheck_through_last_observation'],
            'encoded_bytes': row['encoded_root_bytes']}
    closed = {key: value for key, value in rows.items() if value['closed']}
    def span(field):
        values = [r[field] for r in closed.values()]
        return {'min': min(values), 'max': max(values)}
    maximum = max(closed, key=lambda key: closed[key]['body_plus_tail_ms'])
    report = {
        'schema': 'g31.complete_root_evidence_codec_analysis.v1',
        'status': 'source_candidate_functional_gate_passed_uninstalled',
        'saved_summary': reference(SUMMARY), 'pure_receipt': reference(PURE/'receipt.json'),
        'pure_XML': reference(PURE/'tests.xml'), 'pure_external_wall': reference(PURE/'external_wall.json'),
        'pure_source_count': len(pure['source_sha256']),
        'candidate_sources': {name: reference(ROOT/name) for name in (
            'scripts/experiments/g31_ics_circulation/complete_root_evidence_codec.py',
            'scripts/experiments/g31_ics_circulation/complete_root_evidence_candidate.py',
            'tests/test_g31_circulation_complete_root_evidence_codec.py',
            'scripts/experiments/g31_ics_circulation/run_complete_root_evidence_codec_pure.py')},
        'analysis_source': reference(Path(__file__)), 'source_proof': candidate.source_proof(),
        'actual_root_denominator': {'all': len(rows), 'closed': len(closed), 'unknown': len(rows)-len(closed),
            'observed_at_most_100ms': saved['roots_at_most_100ms']},
        'closed_envelopes_ms': {name: span(name) for name in ('body_ms', 'tail_ms', 'body_plus_tail_ms')},
        'largest_closed_complete_evidence_envelope': {'branch': maximum, **closed[maximum]},
        'rows': rows,
        'source_cost_path': [
            'Frozen gated EVIDENCE builds every original field and complete runtime query proof.',
            'Original normalize recursively validates and makes the fresh isolated JSON tree.',
            'Original artifact_encode repeats _tree, then C json.dumps and strict UTF-8.',
            'Original artifact_decode uses duplicate-key hook and repeats _tree on decoded data.',
            'Original exact_tree performs another Python ordered/scalar comparison before hash/ledger/publication.'
        ],
        'candidate_change': [
            'Retain original normalize exactly, including unsupported/error handling.',
            'Remove only encoder _tree after normalize using inverse AST proof; all original JSON settings and byte bound remain.',
            'Retain original strict artifact_decode and its _tree.',
            'Replace Python exact_tree with identical C encoding of validated decoded output and exact byte comparison.',
            'Run this check before fresh result escapes; retain original body timestamp and enclosing tail accounting.',
            'Retain every runtime query proof field, ledger and original publisher; no first-hop, scheduler, client or native changes.'
        ],
        'limits': [
            'Recorded body and tail envelopes are not isolated normalization/JSON/exact_tree timings.',
            'No source traversal count proves an acceleration; C re-encoding adds allocation and may lose.',
            'Original Python normalization, duplicate-key hook and decoder _tree remain.',
            'Canonical-byte argument applies only to this owned finite builtin tree, ensure_ascii=False and strict UTF-8.',
            'No actual saved18 codec differential or performance run has been done for this new candidate.',
            'No runtime/full campaign installed; no 100ms, native, protection or cross-request authority claim.'
        ],
        'proposed_next_review_gate': {
            'requires_root_review_before_dispatch': True,
            'scope': 'At most one bounded saved18 whole-root differential read, all fields and clocks preserved, no native/prediction.',
            'source_raw_references': {name: row['raw'] for name, row in saved['rows'].items()},
            'timing_interpretation': 'A later fixed A/B must include normalize, first encode, strict decode, re-encode, ledger, publication and setup; no subtraction.'
        },
        'new_native_calls': 0, 'new_prediction_calls': 0, 'new_raw_scans': 0,
        'new_performance_runs': 0,
    }
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    path = output/'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({'report': reference(path), 'closed_envelopes_ms': report['closed_envelopes_ms'],
                      'largest_closed_complete_evidence_envelope': report['largest_closed_complete_evidence_envelope']}))


if __name__ == '__main__':
    main()
