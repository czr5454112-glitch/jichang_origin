"""Opt-in, detached physical observations for future audit/replay tooling.

The historical physical_projection keeps three mutable mapping references.
Leave that frozen compatibility representation untouched and explicitly copy
its complete value here. Observations never enter controller input/checkpoints.
"""
from copy import deepcopy

from .role_coverage import CursorSimulation
from .run_network_opportunities import physical_projection


def instant_physical_projection(state):
    """Return the actual current value, with no aliases back into live state."""
    return deepcopy(physical_projection(state))


class InstantPhysicalCursorSimulation(CursorSimulation):
    """One-tick diagnostic driver, with out-of-band immutable observations.

    Checkpoint restoration intentionally starts a new observer history. The
    base checkpoint remains complete for control, without serializing this
    side-channel or feeding future observations back into a policy.
    """
    @classmethod
    def from_base_checkpoint(cls, base, *, cursor=None, contract=None):
        engine = super().from_base_checkpoint(base, cursor=cursor, contract=contract)
        engine.instant_physical_ticks = []
        return engine

    def advance(self, horizon):
        if type(horizon) is not int or horizon != self.state.now + 1:
            raise ValueError('instant trace driver requires exactly one integer tick per advance')
        result = super().advance(horizon)
        self.instant_physical_ticks.append(instant_physical_projection(self.state))
        return result
