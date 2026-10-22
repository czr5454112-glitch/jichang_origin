"""Explicitly synthetic finite figure/guard smoke test; never writes final science."""
import copy
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('science_figures', ROOT / 'terminal_flow_science_figures005.py')
figures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(figures)
OUT = ROOT / 'terminal_flow_science_figures005_synthetic_test_001'

def fixture():
    rows = []
    values = {(p, m): 486_000_000. + ((p - 2200) * 60_000.) + (i - 2) * 19_000. * (p - 2202)
              for p in figures.PARENTS for i, m in enumerate(figures.METHODS)}
    for p in figures.PARENTS:
        for i, (a, b) in enumerate(figures.PAIRS):
            counts = dict.fromkeys(figures.CATEGORIES, 0)
            counts.update(exact_harmed=(i + 1) * (p - 2200) * 9,
                          reference_only_finished=i, exact_equal=40,
                          both_arrived_unfinished=19000)
            counts['both_not_yet_arrived'] = 28506 - sum(counts.values())
            rows.append(dict(parent=p, reference_method=a, candidate_method=b,
                population=28506, population_exclusions=0, cost_window=[7200., 59400.],
                completion_times_imputed=False, both_unfinished_never_declared_equal=True,
                independent_airport_day_claim=False,
                completion_direction=dict(categories=counts, population=28506,
                    known_direction_harm=counts['exact_harmed'] + counts['reference_only_finished'],
                    completion_times_imputed=False, bounds_are_not_completion_times=True),
                reference_cost={'backlog_integral_bag_seconds': values[p, a]},
                candidate_cost={'backlog_integral_bag_seconds': values[p, b]},
                gain_bag_seconds=values[p, a] - values[p, b]))
    return dict(schema='g31.terminal_flow.final_science.v1', status='complete',
        synthetic_test_data=True, registered_runs=28, scientific_per_bag_pairs=24,
        scientific_pair_definitions=figures.PAIRS,
        runs=[dict(parent=p, method=m) for p in figures.PARENTS for m in figures.METHODS],
        all_unfinished_and_not_yet_arrived_bags_retained=True,
        strict_per_bag_nonharm_certified=False, pair_summaries=rows)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', default=OUT, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    assert any('synthetic_test' in part for part in output.parts), 'synthetic test directory required'
    run(output)

def run(OUT):
    assert not OUT.exists(), 'fresh synthetic test directory required'
    OUT.mkdir()
    report = fixture()
    data = figures.derive_data(report)
    assert len(data['costs']) == 28 and len(data['harms']) == 24
    assert data['harms'][2201, 'C00', 'C10'] == 9
    checks = ['complete_28_run_24_pair_synthetic_derivation']
    def rejects(name, change):
        bad = copy.deepcopy(report)
        change(bad)
        try:
            figures.derive_data(bad)
        except ValueError:
            checks.append(name)
        else:
            raise AssertionError('guard accepted: ' + name)
    rejects('missing_run', lambda r: r['runs'].pop())
    rejects('duplicate_run', lambda r: r['runs'].__setitem__(0, r['runs'][1]))
    rejects('missing_pair', lambda r: r['pair_summaries'].pop())
    rejects('duplicate_pair', lambda r: r['pair_summaries'].__setitem__(0, r['pair_summaries'][1]))
    rejects('wrong_harm_definition', lambda r: r['pair_summaries'][0]['completion_direction'].__setitem__('known_direction_harm', 19009))
    rejects('both_unfinished_not_equal', lambda r: r['pair_summaries'][0].__setitem__('both_unfinished_never_declared_equal', False))
    rejects('cost_conflict_between_pairs', lambda r: r['pair_summaries'][1]['reference_cost'].__setitem__('backlog_integral_bag_seconds', 1.))
    bound_file = OUT / 'synthetic_binding.txt'
    bound_file.write_text('synthetic initial bytes', encoding='utf8')
    binding = figures.bind(bound_file)
    bound_file.write_text('synthetic changed bytes', encoding='utf8')
    try:
        figures.verified(binding, {}, load=False)
    except ValueError:
        checks.append('changed_bound_hash_rejected')
    else:
        raise AssertionError('hash guard accepted changed file')
    data['synthetic'] = True
    figures.render(data, OUT / 'figures')
    (OUT / 'synthetic_input.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
    result = dict(schema='g31.terminal_flow.figure_synthetic_smoke.v1', synthetic_test_data=True,
        tests_passed=len(checks), checks=checks, figures=2, native_starts=0,
        final_science_result=False, producer=figures.bind(ROOT / 'terminal_flow_science_figures005.py'))
    (OUT / 'SMOKE_RESULT.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
