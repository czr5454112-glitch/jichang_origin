# G4IRSF8 Candidate v2 Validation Report

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `ab835c53e589fd8463675ea5901086f2f86a2648`
committed_head_at_generation: `ab835c53e589fd8463675ea5901086f2f86a2648`
remote_head_at_generation: `ab835c53e589fd8463675ea5901086f2f86a2648`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

Repeat hashes identical: `True`.
Rows: 39.
Denominator evidence: `release_denominator_supported`.
Open-end evidence: `engineering_reasonable_but_not_java_proven`.

Fault rows are diagnostic and keep their own boundary; they are not hidden behind the no-fault main THT result.

| Scenario | Mean | Complete | Failures | Claim | Material |
| --- | --- | --- | --- | --- | --- |
| repeat_2_5_run_1 | 3.5467070090507438 | 28506 | 0 | False | False |
| repeat_2_5_run_2 | 3.5467070090507438 | 28506 | 0 | False | False |
| repeat_2_5_run_3 | 3.5467070090507438 | 28506 | 0 | False | False |
| repeat_2_5_run_4 | 3.5467070090507438 | 28506 | 0 | False | False |
| repeat_2_5_run_5 | 3.5467070090507438 | 28506 | 0 | False | False |
| speed_sweep_1.5 | 5.756881007507207 | 28506 | 0 | False | False |
| speed_sweep_2.0 | 4.3641999345167095 | 28506 | 0 | False | False |
| speed_sweep_2.5 | 3.5467070090507438 | 28506 | 0 | False | False |
| speed_sweep_3.0 | 2.989577048106817 | 28506 | 0 | False | False |
| fault_16_paper_fault_arc_1 | 3.5379043178166167 | 25306 | 3200 | False | False |
| fault_16_paper_fault_arc_2 | 3.5336616231449223 | 25313 | 3193 | False | False |
| fault_16_paper_fault_arc_3 | 3.5259463126144643 | 25307 | 3199 | False | False |
| fault_16_paper_fault_arc_4 | 3.529605684688888 | 23619 | 4887 | False | False |
| fault_16_paper_fault_arc_5 | 3.539950040221871 | 23619 | 4887 | False | False |
| fault_16_paper_fault_arc_6 | 3.544044171605996 | 23620 | 4886 | False | False |
| fault_16_paper_fault_arc_7 | 3.5815269300030526 | 28506 | 0 | False | False |
| fault_16_paper_fault_arc_8 | 3.550066301831209 | 28506 | 0 | False | False |
| fault_16_paper_fault_arcs_1_7 | 3.5379043178166167 | 25306 | 3200 | False | False |
| fault_16_paper_fault_arcs_2_4 | 3.5162420444531706 | 20426 | 8080 | False | False |
| fault_16_paper_fault_arcs_3_5 | 3.521481880509337 | 20420 | 8086 | False | False |
| fault_16_paper_fault_arcs_4_5 | 3.5324327354260143 | 18732 | 9774 | False | False |
| fault_16_paper_fault_arcs_5_7 | 3.578436569428576 | 23619 | 4887 | False | False |
| fault_16_paper_fault_arcs_2_4_6 | 3.5252672672672762 | 15540 | 12966 | False | False |
| fault_16_paper_fault_arcs_3_5_8 | 3.527942376754841 | 20420 | 8086 | False | False |
| fault_16_paper_fault_arcs_4_6_7 | 3.5773165002935863 | 18733 | 9773 | False | False |
| dynamic_static_1.5_10 | 6.379444721622469 | 28506 | 0 | False | False |
| dynamic_static_1.5_20 | 7.143326648580788 | 28506 | 0 | False | False |
| dynamic_static_1.5_30 | 8.149104727604083 | 28506 | 0 | False | False |
| dynamic_static_2.0_10 | 4.836270076994683 | 28506 | 0 | False | False |
| dynamic_static_2.0_20 | 5.414594369021726 | 28506 | 0 | False | False |
| dynamic_static_2.0_30 | 6.157389922923533 | 28506 | 0 | False | False |
| dynamic_static_2.5_10 | 3.9153916264543636 | 28506 | 0 | False | False |
| dynamic_static_2.5_20 | 4.3641999345167095 | 28506 | 0 | False | False |
| dynamic_static_2.5_30 | 4.9691673933307134 | 28506 | 0 | False | False |
| dynamic_static_3.0_10 | 3.3006672625991706 | 28506 | 0 | False | False |
| dynamic_static_3.0_20 | 3.6847942830749236 | 28506 | 0 | False | False |
| dynamic_static_3.0_30 | 4.181240067532567 | 28506 | 0 | False | False |
| high_flow_extension_subset_32768 | 49.64291068139956 | 28960 | 0 | False | False |
| high_flow_extension_full_348824_prior_context |  |  |  | False | False |
