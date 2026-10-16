"""Owned120 combined synthetic131; no C load/saved fixture/model/performance."""
import time
BOOT = time.monotonic()
from types import SimpleNamespace
from . import run_complete_root_owned_decode_c_binding_pure as original
from . import measure_complete_root_owned_decode_c as campaign

MODULE = 'scripts.experiments.g31_ics_circulation.run_complete_root_owned_decode_c_campaign_pure'
TESTS = (*original.TESTS, campaign.TEST)


def source_closure(root, entries):
    campaign.require(root == campaign.ROOT and entries ==
        (MODULE, campaign.MODULE, *(name[:-3].replace('/', '.') for name in TESTS)),
        'owned_C_campaign_pure_source_entries')
    return campaign.source_files()


# Original complete pure-launcher function with only explicit closed settings.
# Its source archive, full live/archive checks, ownedJob, XML and error logic stay.
image = SimpleNamespace(**vars(original.image))
image.source_closure = source_closure
main = campaign.private(original.main, {'BOOT': BOOT, 'MODULE': MODULE,
    'CANDIDATE': campaign.MODULE, 'TESTS': TESTS, 'EXPECTED_TESTS': 131, 'image': image})

if __name__ == '__main__': raise SystemExit(main())
