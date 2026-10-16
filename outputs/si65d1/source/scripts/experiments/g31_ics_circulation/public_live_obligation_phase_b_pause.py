"""Passive model decision snapshots; neither native authority nor resumable state.

The sole inserted statement runs after the original collection has returned and
before its result is recorded or acted on.  No actual observations or outcomes
are inputs to the hook.  This is a model-history inspection interface, not a
belief coverage proof or an implementation of restarting the interrupted stack.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
from pathlib import Path
import textwrap
from types import FunctionType

from . import public_live_obligation_lazy_communication_projection as lazy

VERSION = 'g31.live_obligation.passive_decision_point.v1'
EXPECTED_LAZY = '980f245dc3b3563968015a626ed5e127fd94efb70044eb24b67d9d948835f86f'
EXPECTED_ORIGINAL = '0c77f130e31f2727d0f6b7f6e6425ae073e3bf5b97515843cf1d03cced5c56ea'
PROGRAM_COUNTER = 'decide_after_collect_before_record_and_action'


def require(condition, reason):
    if not condition:
        raise ValueError('passive_decision_point:' + reason)


class DecisionPoint:
    """An isolated copy of one model state and the just-collected values.

    The engine, pending row, information, screen and view are cloned together.
    Aliases between the heap, request ledger, pending row and CaptureWorld's
    engine back-reference therefore survive.  The external recorder is replaced
    by None in that single deepcopy operation, so neither prior snapshots nor
    the live recorder are reachable through the copied engine.
    """

    def __init__(self, engine, owner, pending, information, screen, view, recorder):
        require(type(recorder) is PointRecorder, 'recorder_type')
        require(owner in ('A', 'B'), 'owner')
        require(pending is engine.owner_state[owner]['pending'], 'pending_alias')
        self.owner = owner
        self.program_counter = PROGRAM_COUNTER
        self.resumable = False
        self.native_authority = False
        self.coverage_certified = False
        self._state = copy.deepcopy(
            (engine, pending, information, screen, view), {id(recorder): None})
        require(self._state[0]._phase_b_recorder is None, 'recorder_detached')
        require(self._state[1] is self._state[0].owner_state[owner]['pending'],
                'copied_pending_alias')

    def copied_state(self):
        """Return another isolated graph; callers cannot edit the retained copy."""
        return copy.deepcopy(self._state)

    def description(self):
        engine, pending, information, screen, _ = self._state
        return {'schema': VERSION, 'owner': self.owner, 'at': engine.time,
                'phase': pending['phase'], 'recollection_index': pending['recollection_index'],
                'information_status': information.get('status'),
                'retry_status': screen.get('status'), 'program_counter': self.program_counter,
                'resumable': False, 'native_authority': False, 'coverage_certified': False,
                'scope': 'Conditional model history only; no interrupted-stack restoration.'}

    def resume(self):
        raise ValueError('passive_decision_point:resume_not_implemented')


class PointRecorder:
    def __init__(self):
        self._points = []

    @property
    def points(self):
        return tuple(self._points)

    def _capture(self, engine, owner, pending, information, screen, view):
        self._points.append(DecisionPoint(engine, owner, pending, information, screen, view, self))


def make_decide():
    require(hashlib.sha256(Path(lazy.__file__).read_bytes()).hexdigest() == EXPECTED_LAZY,
            'frozen_lazy_source')
    original = lazy.original
    require(hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest() == EXPECTED_ORIGINAL,
            'frozen_original_source')
    function = original.Projection.decide
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    before = copy.deepcopy(tree)
    body = tree.body[0].body
    collect = ast.parse('info,screen,view=self.collect(owner,p)').body[0]
    matches = [i for i, node in enumerate(body)
               if ast.dump(node, include_attributes=False) == ast.dump(collect, include_attributes=False)]
    require(len(matches) == 1, 'unique_collect_statement')
    hook = ast.parse('self._record_phase_b_point(owner,p,info,screen,view)').body[0]
    position = matches[0] + 1
    body.insert(position, hook)
    inverse = copy.deepcopy(tree)
    del inverse.body[0].body[position]
    require(ast.dump(inverse, include_attributes=False) == ast.dump(before, include_attributes=False),
            'inverse_AST_exact')
    ast.fix_missing_locations(tree)
    namespace = dict(function.__globals__)
    exec(compile(tree, '<passive_collected_decision_point>', 'exec'), namespace)
    return namespace['decide'], {
        'original_source_sha256': EXPECTED_ORIGINAL, 'lazy_source_sha256': EXPECTED_LAZY,
        'inserted_statements': 1, 'inverse_AST_exact': True,
        'program_counter': PROGRAM_COUNTER, 'run_loop_changed': False,
        'collection_or_action_code_changed': False, 'numeric_expressions_added': 0,
        'scope': 'Normal valid-model execution; allocation failures are not claimed equivalent.'}


_decide, PROOF = make_decide()


class Projection(lazy.Projection):
    decide = _decide

    def __init__(self, bundle, action, initial, *, recorder=None):
        require(recorder is None or type(recorder) is PointRecorder, 'recorder_type')
        self._phase_b_recorder = recorder
        super().__init__(bundle, action, initial)

    def _record_phase_b_point(self, owner, pending, information, screen, view):
        recorder = self._phase_b_recorder
        if recorder is not None:
            require(type(recorder) is PointRecorder, 'recorder_type')
            recorder._capture(self, owner, pending, information, screen, view)


def predict_with_points(supplied_context, action):
    """Original prediction plus separate passive records, without output edits.

    This entry is not an online policy and does not restart a saved point.  All
    copies and original context/collection guards execute in the calling cost.
    """
    recorder = PointRecorder()

    def construct(bundle, selected_action, initial):
        return Projection(bundle, selected_action, initial, recorder=recorder)

    original = lazy.predict
    prediction = FunctionType(original.__code__, {**original.__globals__, 'Projection': construct},
                              original.__name__, original.__defaults__, original.__closure__)
    prediction.__kwdefaults__ = original.__kwdefaults__
    return prediction(supplied_context, action), recorder.points


def source_proof():
    return copy.deepcopy(PROOF)
