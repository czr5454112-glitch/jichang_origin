# Authoring failure record

`test_001.json`: 48 independent storage tests passed; all 7 new lifecycle tests
failed before constructing a Simulation because the fixture passed `cache_scope`
instead of the existing `cache_contract` generator keyword. The failed fixture is
saved as `storage_lifecycle_attempt001.py`. New lifecycle physical runs: 0.
CPU 1.203125 s includes pytest execution but not initial imports or final JSON
write. The independent tests did run physics; their exact physical count was not
instrumented and is not silently counted as zero. The original terminal traceback
was not redirected to disk; subsequent runs use a captured-output runner.

Repair: use the documented existing isolated replay cache keyword. No runtime,
scenario values or assertions were weakened for this fixture error.

Independent runner attempts 008 and 009 retain the next two fixture setup errors:
isolated cache requires `deadline_ms=None`; Simulation requires a generator
factory, so pass `functools.partial` rather than an already constructed instance.
Each attempt had 74 other tests pass and these same 7 setup failures. New lifecycle
physics still had not started. These are authoring mistakes, not scientific runs.
