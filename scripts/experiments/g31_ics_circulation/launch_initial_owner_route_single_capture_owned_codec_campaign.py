"""Same owned600 child tree; original full startup/exit outer clock required."""
import time
BOOT = time.monotonic()
from . import launch_initial_owner_route_campaign_v3 as old
from . import initial_owner_route_single_capture_owned_codec as binding

LIMIT = 600.
MODULE = 'scripts.experiments.g31_ics_circulation.initial_owner_route_single_capture_owned_codec_campaign'
main = binding.private(old.main, {**old.main.__globals__, **globals()})

if __name__ == '__main__': raise SystemExit(main())
