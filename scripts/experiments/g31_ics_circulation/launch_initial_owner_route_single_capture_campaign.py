"""Original owned600 launcher with a private single-capture worker target."""
import time
BOOT = time.monotonic()
from types import FunctionType
from . import launch_initial_owner_route_campaign_v3 as old

LIMIT = 600.
MODULE = 'scripts.experiments.g31_ics_circulation.initial_owner_route_single_capture_campaign'
main = FunctionType(old.main.__code__, {**old.main.__globals__, **globals()}, old.main.__name__,
    old.main.__defaults__, old.main.__closure__)
main.__kwdefaults__ = old.main.__kwdefaults__

if __name__ == '__main__':
    raise SystemExit(main())
