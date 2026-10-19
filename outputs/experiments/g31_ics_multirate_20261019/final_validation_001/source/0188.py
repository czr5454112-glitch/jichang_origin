"""Unchanged owned600 launcher, with only the versioned worker entrypoint."""
import time
BOOT=time.monotonic()
from types import FunctionType
from . import launch_initial_owner_route_campaign_v3 as old

LIMIT=600.
MODULE='scripts.experiments.g31_ics_circulation.initial_owner_route_gate_campaign_v2'
main=FunctionType(old.main.__code__,{**old.main.__globals__,**globals()},old.main.__name__,
                  old.main.__defaults__,old.main.__closure__)
if __name__=='__main__':raise SystemExit(main())
