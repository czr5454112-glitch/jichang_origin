#!/usr/bin/env python3
"""Reproduce focused ICS V3 audit observations without editing the repository.

Usage:
  python reproduce_audit_probes.py --root /path/to/jichang_origin --output new.json
  python reproduce_audit_probes.py --root /path/to/fixed_checkout --output fixed.json --require-fixed

Default exit 0 means the probes executed, NOT that production is defect-free.
--require-fixed returns 1 if any of the three targeted defects is observed.
A new output path is required. The receipt includes complete tiny inputs,
returned candidates, independent witnesses, source hashes, and scope limits.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys
import time
import traceback
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-fixed', action='store_true')
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    module_dir = root / 'scripts/experiments/ics_circulation_v3'
    if not (module_dir / 'runtime.py').is_file():
        parser.error('--root must contain the ICS V3 modules')
    if output.exists():
        parser.error('--output must not already exist')
    output.parent.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))
    prefix = 'scripts.experiments.ics_circulation_v3.'
    names = ['model', 'runtime', 'routing', 'routing_reference', 'routing_cache_contract',
             'storage_contracts', 'storage_routing', 'terminal_capacity_screen',
             'partition_observation', 'joint_reference']
    files = [module_dir / (name + '.py') for name in names]
    hashes = lambda: {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in files}
    before = hashes()
    started, cpu = time.perf_counter(), time.process_time()
    receipt: dict[str, Any] = {
        'schema': 'ics_v3_independent_audit_probes_v1',
        'frozen_production_reference': 'defd79effe02ee13f1a5bbbbc5143f6d0dce2f63',
        'uploaded_release_reference': 'fccd4819532701ee4173ec598822450d962d4e61',
        'root': str(root), 'source_before': before, 'results': {},
        'explicit_simulation_advance_calls': 0, 'full_business_replay': False,
        'native_g31_executed': False,
        'scope': 'Tiny API/correctness probes. No original 44-bag replay, training, native G31 run, or repository mutation.',
        'status': 'not_completed',
    }
    try:
        modules = {name: importlib.import_module(prefix + name) for name in names}
        m, r = modules['model'], modules['runtime']
        rg, ref = modules['routing'], modules['routing_reference']
        sc, sr = modules['storage_contracts'], modules['storage_routing']
        tc = modules['terminal_capacity_screen']
        for name, mod in modules.items():
            if Path(mod.__file__).resolve() != (module_dir / (name + '.py')).resolve():
                raise RuntimeError('Unexpected import location: ' + str(mod.__file__))

        def regional(horizon: int = 10):
            return rg.RegionalCandidateGenerator(horizon=horizon, expansion_limit=200000,
                static_path_limit=20, deadline_ms=None, cache_contract='isolated_replay_v1')

        def storage_state(with_long_alternative: bool = False):
            nodes = {n: m.Node(n, 'Z', 'P', capacity=4) for n in ('S', 'A', 'W', 'X', 'G')}
            edges = [m.Edge('a-SA','S','A',1), m.Edge('b-SW','S','W',1),
                     m.Edge('c-AX','A','X',1), m.Edge('d-WX','W','X',1), m.Edge('e-XG','X','G',1)]
            if with_long_alternative:
                edges.append(m.Edge('f-WG','W','G',4))
            bag = sc.StorageBag('b','S','G',0,20,True,sc.StorageWaypointContract('W',0,0))
            return sc.StorageSnapshot(0, m.Network(nodes,{e.edge_id:e for e in edges}),
                {'t':m.Tray('t','S','loaded','b')}, {'b':bag})

        def hand_witness(state):
            return m.RouteCandidate('hand','b','t',
                (m.Leg('b-SW',0,1),m.Leg('d-WX',1,2),m.Leg('e-XG',2,3)),
                4,4,state.version,'hand',True,'G')

        def four_paths_state():
            # Distinct partitions make all four paths available in the ordinary
            # static regional abstraction; one-region shortest-only is not this test.
            nodes = {n:m.Node(n,'Z',n) for n in ('S','A','B','C','D','G')}
            edges = [e for n in 'ABCD' for e in (m.Edge('S'+n,'S',n,1),m.Edge(n+'G',n,'G',1))]
            return m.Snapshot(0,m.Network(nodes,{e.edge_id:e for e in edges}),
                {'t':m.Tray('t','S','loaded','b')},{'b':m.Bag('b','S','G',0,20)})

        observations = receipt['results']
        state = storage_state(True)
        witness = hand_witness(state)
        validation = r.ExecutionValidator().validate(state,witness)
        if not validation.accepted:
            raise AssertionError('Hand witness must be independently accepted: ' + validation.reason)
        variants = []
        for k in (1,2,3):
            rg.clear_static_cache()
            generator = ref.FullGraphReferenceGenerator(horizon=6,expansion_limit=200000,
                                                         deadline_ms=None,integer_ticks=True)
            try:
                candidates = generator.generate(state,'b','t',k=k)
                row = {'k':k,'candidates':[asdict(c) for c in candidates],
                       'diagnostics':generator.last_diagnostics,'status':generator.last_search_status,
                       'guard_rejection':None}
                first_arrival = candidates[0].legs[-1].arrive if candidates else None
                row['false_earliest_observed'] = bool(candidates and
                    generator.last_diagnostics.get('earliest_arrival_certified') and first_arrival > 3)
            except ValueError as exc:
                # Explicitly rejecting an unsupported model is an acceptable boundary fix.
                row = {'k':k,'guard_rejection':str(exc),'false_earliest_observed':False}
            variants.append(row)
        observations['N1_false_earliest_storage'] = {
            'snapshot':asdict(state),'hand_witness':asdict(witness),
            'hand_validation':asdict(validation),'hand_final_arrival':3,'variants':variants,
            'defect_observed':any(row['false_earliest_observed'] for row in variants),
            'scope':'Direct old FullGraphReferenceGenerator API, not the independent Storage test oracle or a claim about the production business runner.'}

        state = storage_state(False); rg.clear_static_cache()
        generator = ref.FullGraphReferenceGenerator(horizon=5,expansion_limit=200000,
                                                     deadline_ms=None,integer_ticks=True)
        try:
            candidates = generator.generate(state,'b','t',k=1)
            observations['N1b_storage_missed_witness'] = {
                'snapshot':asdict(state),'returned_count':len(candidates),
                'diagnostics':generator.last_diagnostics,
                'hand_validation':asdict(r.ExecutionValidator().validate(state,hand_witness(state))),
                'guard_rejection':None}
        except ValueError as exc:
            observations['N1b_storage_missed_witness'] = {'guard_rejection':str(exc)}

        state = four_paths_state()
        ordinary, wrapped = regional(), tc.TerminalScreenGenerator(regional())
        base_options, screen_options = ordinary.generate(state,'b','t'), wrapped.generate(state,'b','t')
        observations['N2_ordinary_screen_default_k'] = {
            'snapshot':asdict(state),'unwrapped_count':len(base_options),'wrapped_count':len(screen_options),
            'unwrapped':[asdict(c) for c in base_options],'wrapped':[asdict(c) for c in screen_options],
            'defect_observed':base_options != screen_options,
            'scope':'Omitted-k ordinary wrapper. Not the corrected StorageTerminalScreenGenerator or latest explicit k=1 experiment.'}

        factory = modules['routing_cache_contract'].ReplayRegionalFactory.from_generator(regional())
        engine = r.Simulation(state,generator_factory=factory)
        tc.install_terminal_screen(engine)
        cp = engine.checkpoint()
        def accounting_count(obj):
            ledger = getattr(obj,'accounting',None)
            return None if ledger is None else len(ledger.rows)
        before_cp = (accounting_count(cp.generator),accounting_count(cp.generator_factory))
        engine.generator_factory().generate(state,'b','t',k=1)
        after_cp = (accounting_count(cp.generator),accounting_count(cp.generator_factory))
        restored = r.Simulation.from_checkpoint(cp)
        observations['N3_checkpoint_factory_alias'] = {
            'checkpoint_counts_before':before_cp,'checkpoint_counts_after_original_factory_query':after_cp,
            'restored_counts':(accounting_count(restored._generator),accounting_count(restored.generator_factory)),
            'factory_is_shared_with_original':cp.generator_factory is engine.generator_factory,
            'defect_observed':before_cp != after_cp,
            'scope':'Observed accounting contamination. No physical-trajectory corruption asserted.'}

        state = storage_state(False)
        engine = r.Simulation(state,generator_factory=factory,slow_controller=lambda _: ())
        receipt['explicit_simulation_advance_calls'] += 1
        result = engine.advance(6)
        observations['B1_storage_noop_slow'] = {'completed':result.completed,
            'slow_calls':result.policy_stats['slow_calls'],
            'scope':'No-op callback compatibility only, NOT real predictive prebalancing.'}
        checks = [
            ('partition',lambda:modules['partition_observation'].observe_partition(state,'P')),
            ('joint',lambda:modules['joint_reference'].solve_joint(state,domain=modules['joint_reference'].JointDomain(6)))
        ]
        for label, call in checks:
            try:
                call(); verdict = 'accepted'
            except ValueError as exc:
                verdict = str(exc)
            observations['B2_' + label + '_storage_guard'] = {'observed':verdict}

        state = four_paths_state()
        state.bags['b'] = replace(state.bags['b'],protected=True)
        state.replaceable_trays = ('t',)
        old = m.RouteCandidate('old','b','t',(m.Leg('SA',2,3),m.Leg('AG',3,4)),5,5,state.version,'old',True,'G')
        if not r.ExecutionValidator().commit(state,old).accepted:
            raise AssertionError('Protected initial route should be accepted')
        try:
            r.ExecutionValidator().prepare_replacement(state,'t'); refusal = None
        except ValueError as exc:
            refusal = str(exc)
        observations['B3_protected_replacement'] = {'refusal':refusal,
            'scope':'Intentional legacy permission contract; not a cause assigned to original 0/44.'}

        state = m.Snapshot(0,m.Network({'S':m.Node('S','Z','P'),'G':m.Node('G','Z','P')},
            {'SG':m.Edge('SG','S','G',1)}),{'t':m.Tray('t','S','loaded','b')},
            {'b':m.Bag('b','S','G',0,10)})
        engine = r.Simulation(state,reactive_empty_dispatch=False)
        receipt['explicit_simulation_advance_calls'] += 1
        result = engine.advance(3)
        observations['B4_terminal_actual_empty'] = {'completed':result.completed,
            'plans':list(engine.state.plans),'tray':asdict(engine.state.trays['t']),
            'effective_reservations':[asdict(slot) for slot in r.effective_reservations(engine.state)]}
        receipt['status'] = 'completed_observations_not_acceptance'
    except Exception:
        receipt['status'] = 'probe_execution_error'
        receipt['exception'] = traceback.format_exc()
    receipt['source_after'] = hashes()
    receipt['source_changed'] = [p for p,value in before.items() if receipt['source_after'][p] != value]
    receipt['wall_seconds'] = time.perf_counter() - started
    receipt['process_cpu_seconds'] = time.process_time() - cpu
    receipt['resource_scope'] = 'Same process incl module imports and probes; excludes pre-hash and final receipt serialization; not a full-session resource total.'
    receipt['observed_defect_keys'] = [k for k,v in receipt['results'].items() if v.get('defect_observed')]
    output.write_text(json.dumps(receipt,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ('status','observed_defect_keys','explicit_simulation_advance_calls',
                                           'source_changed','wall_seconds','process_cpu_seconds')},indent=2))
    if receipt['status'] == 'probe_execution_error' or receipt['source_changed']:
        return 2
    return 1 if args.require_fixed and receipt['observed_defect_keys'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
