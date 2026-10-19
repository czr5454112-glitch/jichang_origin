# Current-state evaluate remaining-cost profile

## Scope and evidence

- Source: `g31_ics_service_update_20261017/native_002/guarded_default/episode/native/raw.json.gz`, actual A first-return at 7.339999999999996 and B first-reuse-route at 9.689999999999994.
- Only the new `foundation_later_seed.evaluate` was called: one uninstrumented and one cProfile call per owner, two candidates per call. No legacy model call, native execution, production edit, global monkeypatch, or cross-event cache.
- Windows Job hard limit 60 seconds; natural exit 0 in 2.859 seconds. All registered source pins unchanged. All four reports match the saved complete seed and both complete predictions under strict JSON comparison.
- Timings exclude caller evidence copying, imports, outer report detachment, collection, submission and ACK. These two samples are not a latency distribution or a 100ms certificate. cProfile inflates time substantially; cumulative subtrees overlap and must not be added.

## Measurements

| Item | A | B |
|---|---:|---:|
| Uninstrumented evaluate, ms | 150.3893 | 182.0114 |
| Profiled evaluate, ms | 504.6588 | 607.5035 |
| Seed build cumulative, ms | 389.293 | 467.527 |
| Two dynamic later-context calls cumulative, ms | 264.546 | 321.622 |
| 31 isolated static-catalog reads cumulative, ms | 187.840 | 185.780 |
| All deepcopy cumulative, ms | 323.152 | 366.776 |
| deepcopy exclusive, ms | 173.138 | 197.204 |
| Strict payload encoding cumulative, ms | 89.902 | 139.646 |
| Strict recursive type/key/finite/cycle checks exclusive, ms | 50.233 | 77.532 |
| JSON iterencode exclusive, ms | 29.773 | 35.336 |
| Two full physical loops cumulative, ms | 18.140 | 14.850 |
| Source path_sha cumulative, 32 calls, ms | 12.007 | 13.301 |
| One static catalog construction cumulative, ms | 18.274 | 20.072 |

The two dynamic guard passes remain present. Their large cumulative cost is mostly copying and encoding beneath the guards, not the guard predicates themselves. The event loop is only about 3.6% / 2.4% of profiled evaluate time; changing physical scheduling is not the justified next optimization.

### Copy attribution

`RequestContext.inputs` deep-copies the complete three-case catalog 31 times, even when `public_input(case)` needs one case. It accounts for 187.617 / 185.537 ms of deepcopy cumulative cost. The catalog is already constructed only once; further optimization must target safe isolation cost rather than removing dynamic validation.

Beyond the catalog, two `SuppliedContext.__init__` copies cost 40.347 / 62.990 ms; the foundation seed builder's four copy calls cost 18.640 / 26.080 ms; endpoint validation copies cost 16.821 / 25.696 ms; the validated-result copy in `revalidate` costs 11.686 / 16.619 ms. These are overlapping provenance envelopes, but they are not redundant authority checks that may simply be removed.

Actual serialized evidence sizes are 74,055 / 119,036 bytes; full seeds are 85,887 / 132,410 bytes, whereas physical bundles are only 10,698 / 11,760 bytes. The unchanged evidence dominates the seed size. Each candidate's identity/mutation check still encodes the full seed; its two calls cost 20.835 / 31.668 ms profiled. These checks must remain semantically intact.

## Minimal safe implementation proposal, not yet implemented

1. First optimize isolated builtin-data copying, not model logic. Add a request-local copier for a strictly supported builtin value graph, with atomic scalar fast paths and memoized dict/list/tuple containers. Preserve exact key/value types, signed-zero and float values, tuple/list distinction, shared references, and caller isolation. Reject unsupported hooks/classes or fall back to unchanged deepcopy outside the proven supported domain. Do not replace `copy.deepcopy` globally.
2. Start with the static catalog closure only. It is generated inside this request from pinned sources, has no caller-owned capabilities, and currently accounts for the largest standalone cost. Every read must still return an independent object. This is a small bounded change to the new request-context module and admits exhaustive type/alias/mutation/parity tests.
3. Only after that passes, consider using the same copier in the existing private function namespaces for evidence and validated structures. `SuppliedContext` methods currently retain original module globals, so replacing a cloned module's `copy` name alone does not optimize the class. Any private class-method binding must preserve exact `SuppliedContext` type checks, slot semantics, payload bytes/digests and both dynamic guard executions; do not silently skip those copies or subclass and weaken the type guard.
4. A separate alternative is request-local static per-case copies and precomputed static fingerprints. It can avoid copying unrelated catalog cases, but it changes more helper bindings and should be a separate reviewed step. Current dynamic contract/job/entry/service checks must still run on current evidence and compare against those static values every time.
5. Leave strict encoding and full-seed mutation checks unchanged initially. Reusing an encoding by object identity while the object remains mutable is unsafe. Returning mutable catalog objects, JSON-roundtripping tuple-containing static data without type proof, caching across owner events, reusing old v3 epochs, rebasing the original reference, or dropping source checks is not acceptable.

Expected benefit is material but not a guaranteed sub-100ms result. The full native collection-to-decision window remains a separate requirement. Required validation includes complete A/B/delayed-B seed and prediction parity, all existing dynamic negatives, mutation isolation, retained preference behavior, source/archive inclusion, and a new bounded actual native branch after source freeze.
