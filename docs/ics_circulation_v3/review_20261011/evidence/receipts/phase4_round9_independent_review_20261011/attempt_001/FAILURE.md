# Initial audit launcher failure

The requested filename `tests/test_ics_circulation_v3_joint_bundle_reference.py`
does not exist. Binding collection failed with FileNotFoundError before pytest
or bridge workers started. No physical simulation ran. Parent CPU was not
written because the initial binding scan preceded the runner's try/finally;
CPU is unknown, not zero. Shell wall was 0.6914782 s.

Repair: verify exact test paths and retain missing inputs as null in the audit
binding capture so any later usage error receives a resource receipt.
