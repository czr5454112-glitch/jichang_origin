"""Process-local experimental installation of the public static-path cache.

The frozen controller files remain byte-identical. This explicit opt-in is for
one serial research worker only; it does not cache observations or decisions.
"""
from contextlib import contextmanager
from . import analytic_control
from .public_travel_pool import PublicTravelPool, PublicTravel


@contextmanager
def installed_public_travel_pool(*, max_graphs=4):
    if analytic_control.PublicTravel is not PublicTravel:
        raise ValueError("travel_pool:another_installation_active")
    pool = PublicTravelPool(max_graphs=max_graphs)
    counters = {"checkouts": 0, "explicit_fresh_searches": 0}

    def factory(observation, *, _reuse_source_searches=True):
        if not _reuse_source_searches:
            counters["explicit_fresh_searches"] += 1
            return PublicTravel(observation, _reuse_source_searches=False)
        counters["checkouts"] += 1
        return pool.checkout(observation)

    analytic_control.PublicTravel = factory
    try:
        yield pool, counters
    finally:
        # Even exceptional workers must not leak the experimental factory.
        changed = analytic_control.PublicTravel is not factory
        analytic_control.PublicTravel = PublicTravel
        if changed:
            raise RuntimeError("travel_pool:factory_changed_during_installation")
