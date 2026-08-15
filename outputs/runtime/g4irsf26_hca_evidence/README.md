# G4IRSF26 fresh HCA evidence

This directory is the compact, reviewable projection of the fresh Java/HCA campaigns used by the G26 reporter.

- `speed_*`: four full-day speed campaigns; each speed has two independent Java process repeats.
- `fault_*`: the sixteen registered Table 5.5 reconstructions; each has one full-day Java run.
- `fault_pair_5_7_workbook_probe`: the additional `33→44 + 46→36` worksheet-label probe. It did not reproduce the archived worksheet numerator and is not admitted for a fresh verdict.

Each campaign keeps `fresh_hca_summary.json` and the matching `run_*/run_status.json`. Machine-local executable and workspace prefixes in the status command were normalized to `java` and repository-relative paths. Numeric results, schedule arguments, epochs, counters, and status fields were not changed.

Large per-epoch task files, route traces, and duplicate raw timing streams remain local. They can be regenerated with `scripts/eval/run_g4irsf24_fresh_hca.py`; the compact files here contain every field used by `scripts/eval/run_g4irsf26_reporting.py`.
