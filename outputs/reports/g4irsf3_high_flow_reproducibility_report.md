# G4IRSF3 High-Flow Reproducibility Report

governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Result

verification_status: `PASS`
expected_sha256: `904e39132b08e20242566977436a1daf7fa325c8941b1c5ebf7ad6ad77fbeefc`
actual_sha256: `904e39132b08e20242566977436a1daf7fa325c8941b1c5ebf7ad6ad77fbeefc`
file_size_bytes: `146397454`
line_count: `348824`
task_count_from_manifest: `348824`
regenerated_this_run: `False`
regeneration_command: `python scripts/data/g4irsf3_reproduce_high_flow_tasks.py --manifest artifacts/tasks/g4irsf2_high_flow_manifest.json --output artifacts/tasks/g4irsf2_high_flow_tasks.jsonl --verify-sha256`

The large JSONL task stream stays out of Git. This script either verifies the local copy against the tracked manifest or regenerates it through the audited G4IRSF2 rule-preserving generator.

note: `existing_file_sha256_matches_manifest`
