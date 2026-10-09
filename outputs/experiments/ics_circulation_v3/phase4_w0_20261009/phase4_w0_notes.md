# Phase4 W0 entry contracts

W0 is a small reproducibility repair, not the coupled research milestone. Historical results remain unchanged.

All ten existing run entrypoints plus the Nanning benchmark reject nonempty directories and occupied file paths. Invalid external inputs are checked before output creation where available. `audit_nanning` uses the packaged fixture and exclusive JSON creation; missing maps fail explicitly.

Configuration modes: `development` is the compatible default and records repeated sources as development, never new held-out evidence. `reproduce` requires `--reference-protocol` and `--reference-manifest`, restores their exact sources/counts/seed, rejects overrides and adds zero independent samples. `fresh-confirmation` requires `--evaluation-namespace`; validation/test IDs must be absent from every registered historical split. `--training-manifest` permits explicit training reuse. `--history-manifest` adds external registries. Renamed equivalent data or unregistered prior use cannot be detected by ID checks.

The saved reproduction_manifest is real historical preflight (8 train/4 validation/4 test), not a repeat of the old learning table. The targeted CLI regression runs the full write/selection path with a small stubbed collector. See targeted_tests.log/XML and verification.json. External frozen probes are owned by the parent task and linked there; they were not rerun here.

Use the frozen source checkout for bit-identical algorithm reproduction. Current W1 runtime changes are intentionally separate from this protocol repair. Output guards are not a concurrent-writer transaction lock. The old `empty_distance` key measures travel ticks, not metres; assumption_registry.json separates known, proxy and unconfirmed units and authorities. The 66 ODs lost under the zero-edge closure proxy remain outside full-business acceptance.

Example (new output path required):

```powershell
python -m scripts.experiments.ics_circulation_v3.run_scene_configuration --mode reproduce --reference-protocol outputs/experiments/ics_circulation_v3/phase3_scene_configuration_smoke_20261009/protocol.json --reference-manifest outputs/experiments/ics_circulation_v3/phase3_scene_configuration_smoke_20261009/split_manifest.json --output outputs/experiments/ics_circulation_v3/phase4_reproduce_new
```
