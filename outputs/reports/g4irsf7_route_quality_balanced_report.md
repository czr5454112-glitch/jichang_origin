# G4IRSF7 Route Quality Balanced Report

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
committed_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
remote_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

Deterministic repeat exact: True.

| Scope | Run | Mean | Complete | Conflicts | Full A* | Promotion |
| --- | --- | --- | --- | --- | --- | --- |
| repeat_2_5 | route_quality_repeat_1 | 3.974431057596331 | 28506 | 0 | 0 | diagnostic_improvement_only |
| repeat_2_5 | route_quality_repeat_2 | 3.974431057596331 | 28506 | 0 | 0 | diagnostic_improvement_only |
| repeat_2_5 | route_quality_repeat_3 | 3.974431057596331 | 28506 | 0 | 0 | diagnostic_improvement_only |
| repeat_2_5 | route_quality_repeat_4 | 3.974431057596331 | 28506 | 0 | 0 | diagnostic_improvement_only |
| repeat_2_5 | route_quality_repeat_5 | 3.974431057596331 | 28506 | 0 | 0 | diagnostic_improvement_only |
| speed_sweep | route_quality_speed_1.5 | 6.198362026195601 | 28506 | 0 | 0 | not_promoted |
| speed_sweep | route_quality_speed_2.0 | 4.80998504980266 | 28506 | 0 | 0 | not_promoted |
| speed_sweep | route_quality_speed_2.5 | 3.974431057596331 | 28506 | 0 | 0 | diagnostic_improvement_only |
| speed_sweep | route_quality_speed_3.0 | 3.41651469959875 | 28506 | 0 | 0 | candidate_noninferior_strict |
| fault_16 | route_quality_fault_paper_fault_arc_1 | 3.965428200884178 | 25306 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arc_2 | 3.961081885323418 | 25313 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arc_3 | 3.956549993784669 | 25307 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arc_4 | 3.9678359964841543 | 23619 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arc_5 | 3.9827882149996086 | 23619 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arc_6 | 3.9853899090986036 | 23620 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arc_7 | 4.007674786432347 | 28506 | 0 | 0 | not_promoted |
| fault_16 | route_quality_fault_paper_fault_arc_8 | 3.9791948112037545 | 28506 | 0 | 0 | not_promoted |
| fault_16 | route_quality_fault_paper_fault_arcs_1_7 | 3.965428200884178 | 25306 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arcs_2_4 | 3.9571357594255767 | 20426 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arcs_3_5 | 3.9692402884023883 | 20420 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arcs_4_5 | 3.9946209871339926 | 18732 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arcs_5_7 | 4.019027151201393 | 23619 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arcs_2_4_6 | 3.991663105518762 | 15540 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arcs_3_5_8 | 3.9758976342079633 | 20420 | 0 | 0 | reject_guardrail |
| fault_16 | route_quality_fault_paper_fault_arcs_4_6_7 | 4.037414806363665 | 18733 | 0 | 0 | reject_guardrail |
| high_flow_subset | route_quality_high_flow_subset_32768 | 55.177704751712824 | 28960 | 0 | 0 | extension_only |

`route_quality_balanced` may be an engineering candidate only; it is not a paper/Java/CIE victory claim.
