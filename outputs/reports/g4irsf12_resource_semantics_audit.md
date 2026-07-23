# G4IRSF12 Resource Semantics Audit

Status: `STATIC_EVIDENCE_COMPLETE_RUNTIME_AB_NOT_EXECUTED`.

This is a static topology/source audit. It does not claim that R1--R4 have been implemented, executed, or promoted.

## Fixed evidence identity

| Field | Value |
| --- | --- |
| map | data/processed/maps/map2.json |
| raw SHA-256 | 9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4 |
| semantic SHA-256 | 67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63 |
| topology mutation | False |

## Static topology

| Measure | Count |
| --- | --- |
| node_count | 54 |
| directed_edge_count | 69 |
| undirected_corridor_key_count | 69 |
| reverse_pair_count | 0 |
| directed_edges_aliased_by_reverse_pair_count | 0 |
| direction_aliasing_present_on_fixed_map | False |
| topological_merge_count | 23 |
| topological_split_count | 20 |
| declared_merge_node_count | 22 |
| declared_split_node_count | 19 |
| directed_scc_count | 31 |
| nontrivial_directed_scc_count | 1 |
| largest_directed_scc_size | 24 |
| weak_component_count | 1 |
| weak_projection_articulation_count | 11 |
| weak_projection_bridge_count | 11 |

Articulation points and bridges are computed on the explicitly labelled undirected weak projection. Directional structure is reported separately through strongly connected components.

### Reverse directions currently sharing one corridor calendar

| Current key | Direction A | Direction B |
| --- | --- | --- |
| none |  |  |

The protected map contains no reverse edge pair. The current min/max key therefore aliases zero real directed-edge calendars on this topology, so an R0-versus-R1 runtime delta is not expected from directionality alone. The full-travel exclusivity question remains separate.

## Reviewed source evidence

| Evidence | Location | Meaning |
| --- | --- | --- |
| current_runtime_corridor_reservation_duration | cpp/ics_core/runtime/event_driven_junction.hpp:841 | The runtime selects full-travel versus entry-headway reservation duration from the declared resource mode. |
| current_runtime_destination_service_calendar | cpp/ics_core/runtime/event_driven_junction.hpp:1824 | The destination service interval is reserved separately. |
| current_runtime_unbounded_queue_default | cpp/ics_core/runtime/event_driven_junction.hpp:116 | Zero is explicitly documented as no configured local queue cap. |
| current_runtime_undirected_corridor_key | cpp/ics_core/runtime/event_driven_junction.hpp:368 | The current runtime canonicalises both directions to min/max. |
| legacy_astar_directed_edge_lookup | legacy/jichang_origin_readonly/src/App/Astar.java:79 | A* looks up the exact current-to-next directed edge. |
| legacy_astar_node_window_conflict | legacy/jichang_origin_readonly/src/App/Astar.java:83 | Conflict checks index destination-node windows and exempt the goal. |
| legacy_astar_travel_then_node_service | legacy/jichang_origin_readonly/src/App/Astar.java:80 | Travel advances arrival time; the destination service interval follows. |
| legacy_constraint_is_node_interval | legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java:299 | update_constrain records task, arrival and departure per path node. |
| legacy_map_directed_adjacency | legacy/jichang_origin_readonly/src/App/Map.java:59 | Map.N stores each node's listed outgoing neighbours. |
| legacy_map_directed_edge_start | legacy/jichang_origin_readonly/src/App/Map.java:76 | The first edge endpoint is parsed as directed start. |
| legacy_source_single_unfinished_per_start | legacy/jichang_origin_readonly/src/App/Tasks.java:151 | Task generation gates a source when an unfinished task already uses it. |

## Legacy semantics answers

1. **Edge capacity=1:** not implemented by the reviewed Java planning constraint path. This is not proof that the physical conveyor has unlimited capacity.
2. **Full-travel edge exclusivity:** not implemented by that reviewed path; travel advances time between node windows.
3. **Reverse-pair merging:** not observed. Map adjacency and edge lookup are directed.
4. **Primary conflict object:** node arrival/departure windows; the goal is exempt in `Astar.research`.
5. **Special handling:** the goal-window exemption and a source gate for one unfinished task per start are explicit. No authoritative physical merge-buffer capacity was found in the reviewed files.
6. **Minimum carrier headway:** not extractable from the reviewed code. It remains unknown and any R2/R4 value must be labelled sensitivity-only until sourced.

## Predeclared R0--R4 ladder

| ID | Semantics | Direction | Occupancy | Headway s | Readiness |
| --- | --- | --- | --- | --- | --- |
| R0 | R0_current_undirected_full_travel_exclusive | undirected_minmax_corridor_alias | exclusive_full_travel_interval | None | READY_AS_NEGATIVE_CONTROL |
| R1 | R1_directed_full_travel_exclusive | directed | exclusive_full_travel_interval | None | DECLARED_FOR_CONTROLLED_AB_NOT_EXECUTED |
| R2 | R2_directed_entry_headway | directed | entry_headway_only_multiple_inflight_allowed | None | REQUIRES_EXPLICIT_SENSITIVITY_HEADWAY_BEFORE_EXECUTION |
| R3 | R3_java_node_window_compatible | directed_topology_no_edge_calendar_in_reviewed_java_path | travel_time_without_reviewed_edge_exclusivity | None | DECLARED_FOR_CONTROLLED_AB_NOT_EXECUTED |
| R4 | R4_directed_headway_plus_merge_service_calendar | directed | entry_headway_only_multiple_inflight_allowed | None | REQUIRES_EXPLICIT_SENSITIVITY_HEADWAY_BEFORE_EXECUTION |

Reviewed Java conflict resource: `node_arrival_departure_windows`. Authoritative entry headway: `None`.

R0 is the existing negative control. R1/R3 are declared controlled A/B modes; R2/R4 additionally require an explicit sensitivity-only headway binding. This static audit does not establish build/runtime readiness for any new mode. Execute 144/512/2048 first and validate the runtime echo. No static result authorizes 43,603-segment full execution.
