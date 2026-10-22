"""Three tiny synthetic review cases only; no native or real TRAIN/DEV inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOTDATA = Path(__file__).resolve().parent
BASE = ROOTDATA / 'time_expansion_candidate_preparation_006'


def bound(path):
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    bindings = [bound(BASE / name) for name in ('pending_time_solver.py', 'test_pending_time_solver.py', 'README.md')]
    spec = importlib.util.spec_from_file_location('independent_pending_fixture', BASE / 'test_pending_time_solver.py')
    fixture = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = fixture
    spec.loader.exec_module(fixture)
    rows = []
    for blocked in ('receiver_cap_zero', 'source_cap_zero'):
        case = fixture.scene([('ordinary', 1, 10, 1., 'ordinary_return'), ('optional', 2, 20, .125)],
                             waiting={1: 0., 2: 0., 10: 1., 20: 5.})
        if blocked == 'receiver_cap_zero':
            case['receiver_contract'][10]['available_slots'] = 0
        else:
            case['offers']['sources'][1]['source_cap'] = 0
        result = fixture.w.solve_pending(**case)
        rows.append(dict(case=blocked, input_scope='synthetic accepted prototype input, not proven production menu reachability',
                         status=result['status'], ordinary_return_present=result['ordinary_return_present'],
                         protected_planned_quantity=result['protected_planned_quantity'],
                         current_slot_action=result['current_slot_action'],
                         baseline_fallback_required=result['baseline_fallback_required']))
        assert result['ordinary_return_present'] and result['protected_planned_quantity'] == 0
        assert result['current_slot_action']['source_category'] == 'loader_optional'
        assert result['baseline_fallback_required'] is False
    case = fixture.scene([('A', 1, 2, 1.), ('B', 2, 10, 450.)], waiting={1: 0., 2: 0., 10: 0.},
        curves={1: [0., 0., 0.], 2: [0., 2., 0.], 10: [1., 0., 0.]}, edges=[0., 100., 101., 600.])
    result = fixture.w.solve_pending(**case)
    assert result['objective']['net_proxy_gain'] > 0 and result['current_slot_standalone_gain_positive'] is False
    rows.append(dict(case='joint_positive_does_not_authorize_nonpositive_first_action',
                     joint_net_proxy_gain=result['objective']['net_proxy_gain'],
                     current_slot_action=result['current_slot_action'],
                     current_slot_standalone_score=result['current_slot_standalone_score'],
                     current_slot_standalone_gain_positive=result['current_slot_standalone_gain_positive'],
                     native_execution_authority=result['native_execution_authority']))
    for binding in bindings:
        assert bound(Path(binding['path'])) == binding
    report = dict(schema='g31.terminal_flow.pending_time_solver.independent_review.v1',
        scope='read-only prototype review plus three tiny synthetic reproductions; no production claim',
        native_or_real_DEV_executed=False, inputs=bindings, producer=bound(Path(__file__)),
        source_entry_exit_equal=True, reproductions=rows,
        required_before_any_production_connection=[
            'Preserve task 7.3.1 exact-positive optional first-action gate; joint-positive plans cannot relax it.',
            'When ordinary is protected but no ordinary current suggestion survives internal caps, return explicit ordinary baseline fallback or reject inconsistent inputs, not an optional current recommendation.',
        ])
    output = ROOTDATA / 'time_expansion_independent_review_006.json'
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(bound(output), indent=2))


if __name__ == '__main__':
    main()
