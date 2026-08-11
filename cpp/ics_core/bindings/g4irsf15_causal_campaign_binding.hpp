#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "ics_core/runtime/event_driven_junction.hpp"

namespace czr005::bindings::g4irsf15 {

namespace py = pybind11;

using EdgeRecordTuple = std::tuple<int, int, double, double>;
using EventRuntimeBagTuple =
    std::tuple<std::string, int, double, double, int, int, std::string>;
using NodeRecordTuple =
    std::tuple<int, int, double, int, int, std::vector<int>>;

inline constexpr const char* kSkeletonScanSchema =
    "czr005.g4irsf15.causal_skeleton_population.v1";
inline constexpr const char* kSkeletonSchema =
    "czr005.g4irsf15.causal_skeleton.v1";
inline constexpr const char* kMaterializationSchema =
    "czr005.g4irsf15.causal_descriptor_materialization.v1";
inline constexpr const char* kDescriptorSchema =
    "czr005.g4irsf15.causal_target_descriptor.v1";
inline constexpr const char* kTargetAddressSchema =
    "czr005.g4irsf15.causal_target_address.v1";
inline constexpr const char* kTargetAddressHorizonSchema =
    "czr005.g4irsf15.causal_target_address_horizon.v1";
inline constexpr const char* kG4IRSF20RouteTargetSchema =
    "czr005.g4irsf20.route_target.v1";
inline constexpr const char* kG4IRSF21RouteActionTargetSchema =
    "czr005.g4irsf21.route_action_target.v1";
inline constexpr const char* kPrepopEventGroupSchema =
    "czr005.g4irsf15.prepop_event_group.v1";
inline constexpr const char* kPairRunSchema =
    "czr005.g4irsf15.causal_target_pairs.v1";

namespace detail {

using Boundary = ics::G4IRSF14CloneBoundary;
using BoundaryKind = ics::G4IRSF14CloneBoundaryKind;
using Horizon = ics::G4IRSF14CloneHorizon;
using Intervention = ics::G4IRSF14CloneIntervention;
using InterventionKind = ics::G4IRSF14CloneInterventionKind;
using Runtime = ics::EventDrivenJunctionRuntime;
using Skeleton = ics::G4IRSF15CausalOpportunitySkeleton;
using SkeletonStep = ics::G4IRSF15CausalSkeletonStepResult;
using Strata = ics::G4IRSF15CausalPrepopStrata;

inline py::handle required_item(const py::dict& row,
                                const char* key) {
  PyObject* value = PyDict_GetItemString(row.ptr(), key);
  if (value == nullptr) {
    throw py::value_error(std::string("target descriptor is missing ") +
                          key);
  }
  return py::handle(value);
}

inline py::handle optional_item(const py::dict& row,
                                const char* key) {
  return py::handle(PyDict_GetItemString(row.ptr(), key));
}

inline int strict_int(const py::handle& value,
                      const char* name) {
  if (PyBool_Check(value.ptr()) || !PyLong_Check(value.ptr())) {
    throw py::type_error(std::string(name) +
                         " must be an integer, not bool");
  }
  const long long converted = PyLong_AsLongLong(value.ptr());
  if (converted == -1 && PyErr_Occurred()) {
    throw py::error_already_set();
  }
  if (converted <
          static_cast<long long>(std::numeric_limits<int>::min()) ||
      converted >
          static_cast<long long>(std::numeric_limits<int>::max())) {
    throw py::value_error(std::string(name) +
                          " is outside the supported integer range");
  }
  return static_cast<int>(converted);
}

inline std::uint64_t strict_uint64(const py::handle& value,
                                   const char* name) {
  if (PyBool_Check(value.ptr()) || !PyLong_Check(value.ptr())) {
    throw py::type_error(std::string(name) +
                         " must be a non-negative integer, not bool");
  }
  const unsigned long long converted =
      PyLong_AsUnsignedLongLong(value.ptr());
  if (converted == static_cast<unsigned long long>(-1) &&
      PyErr_Occurred()) {
    throw py::error_already_set();
  }
  return static_cast<std::uint64_t>(converted);
}

inline std::string strict_string(const py::handle& value,
                                 const char* name) {
  if (!PyUnicode_Check(value.ptr())) {
    throw py::type_error(std::string(name) + " must be a string");
  }
  return py::cast<std::string>(value);
}

inline bool strict_bool(const py::handle& value,
                        const char* name) {
  if (!PyBool_Check(value.ptr())) {
    throw py::type_error(std::string(name) + " must be bool");
  }
  return value.ptr() == Py_True;
}

inline std::vector<int> strict_int_vector(
    const py::handle& value, const char* name) {
  if (!PyList_Check(value.ptr()) && !PyTuple_Check(value.ptr())) {
    throw py::type_error(std::string(name) + " must be a list of integers");
  }
  std::vector<int> result;
  result.reserve(static_cast<std::size_t>(py::len(value)));
  for (const py::handle item : py::reinterpret_borrow<py::sequence>(value)) {
    result.push_back(strict_int(item, name));
  }
  return result;
}

inline bool is_lower_sha256(const std::string& value) {
  return value.size() == 64U &&
         std::all_of(value.begin(), value.end(), [](char ch) {
           return (ch >= '0' && ch <= '9') ||
                  (ch >= 'a' && ch <= 'f');
         });
}

inline std::string strict_sha256(const py::handle& value,
                                 const char* name) {
  const auto converted = strict_string(value, name);
  if (!is_lower_sha256(converted)) {
    throw py::value_error(std::string(name) +
                          " must be a lowercase SHA-256 hex digest");
  }
  return converted;
}

inline std::string prepop_event_group_sha256(
    const std::string& input_runtime_cohort_sha256,
    std::uint64_t event_ordinal,
    std::uint64_t event_seq,
    std::uint64_t event_time_bits,
    int node) {
  const auto json =
      std::string("{\"event_ordinal\":") +
      std::to_string(event_ordinal) +
      ",\"event_seq\":" + std::to_string(event_seq) +
      ",\"event_time_bits\":" + std::to_string(event_time_bits) +
      ",\"input_runtime_cohort_sha256\":\"" +
      input_runtime_cohort_sha256 +
      "\",\"node\":" + std::to_string(node) +
      ",\"schema\":\"" + kPrepopEventGroupSchema + "\"}";
  return ics::canonical_map2_detail::sha256_hex(json);
}

inline std::string target_address_horizon_sha256(
    const std::string& target_address_id,
    const char* horizon) {
  const auto json =
      std::string("{\"horizon\":\"") + horizon +
      "\",\"schema\":\"" + kTargetAddressHorizonSchema +
      "\",\"target_address_id\":\"" + target_address_id + "\"}";
  return ics::canonical_map2_detail::sha256_hex(json);
}

inline ics::Graph graph_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time) {
  ics::Graph graph;
  for (const auto& [location, node_type, service_time, x, y, outgoing] :
       node_records) {
    graph.add_node(
        ics::Node{location, node_type, service_time, x, y, outgoing});
  }
  graph.set_heuristic(heuristic_time);
  for (const auto& [start, end, length, speed] : edge_records) {
    graph.add_edge(ics::Edge{start, end, length, speed});
  }
  return graph;
}

inline std::vector<ics::EventRuntimeBagRequest> requests_from_records(
    const std::vector<EventRuntimeBagTuple>& bag_records) {
  if (bag_records.empty()) {
    throw py::value_error(
        "G4IRSF15 causal campaign requires at least one request");
  }
  std::vector<ics::EventRuntimeBagRequest> requests;
  requests.reserve(bag_records.size());
  for (const auto& record : bag_records) {
    requests.push_back(ics::EventRuntimeBagRequest{
        std::get<0>(record),
        std::get<1>(record),
        std::get<2>(record),
        std::get<3>(record),
        std::get<4>(record),
        std::get<5>(record),
        std::get<6>(record)});
  }
  return requests;
}

inline std::string workload_cohort_sha256(
    const std::vector<ics::EventRuntimeBagRequest>& requests) {
  ics::g4irsf14_clone_detail::CanonicalFields fields;
  fields.string(
      "schema",
      "czr005.g4irsf15.input_runtime_cohort_order.v1");
  fields.unsigned_integer(
      "request_count",
      static_cast<std::uint64_t>(requests.size()));
  for (std::size_t index = 0; index < requests.size(); ++index) {
    const auto& request = requests[index];
    ics::g4irsf14_clone_detail::CanonicalFields item;
    item.unsigned_integer(
        "runtime_bag_id",
        static_cast<std::uint64_t>(index));
    item.integer("task_id", request.task_id);
    item.string("segment_id", request.segment_id);
    item.integer("start", request.start);
    item.integer("goal", request.goal);
    item.floating("release_time", request.release_time);
    item.floating("deadline", request.deadline);
    item.string("source", request.source);
    fields.string("request", item.payload());
  }
  return ics::canonical_map2_detail::sha256_hex(
      fields.payload());
}

inline std::string canonical_json_string(
    const std::string& value) {
  static constexpr char hex[] = "0123456789abcdef";
  std::string escaped;
  escaped.reserve(value.size() + 2U);
  escaped.push_back('"');
  for (const unsigned char ch : value) {
    switch (ch) {
      case '"':
        escaped += "\\\"";
        break;
      case '\\':
        escaped += "\\\\";
        break;
      case '\b':
        escaped += "\\b";
        break;
      case '\f':
        escaped += "\\f";
        break;
      case '\n':
        escaped += "\\n";
        break;
      case '\r':
        escaped += "\\r";
        break;
      case '\t':
        escaped += "\\t";
        break;
      default:
        if (ch < 0x20U) {
          escaped += "\\u00";
          escaped.push_back(hex[(ch >> 4U) & 0x0fU]);
          escaped.push_back(hex[ch & 0x0fU]);
        } else {
          escaped.push_back(static_cast<char>(ch));
        }
        break;
    }
  }
  escaped.push_back('"');
  return escaped;
}

inline std::string runtime_segment_mapping_sha256(
    const std::vector<ics::EventRuntimeBagRequest>& requests) {
  std::string json = "[";
  for (std::size_t index = 0; index < requests.size(); ++index) {
    if (index != 0U) {
      json.push_back(',');
    }
    const auto& request = requests[index];
    json += "{\"runtime_bag_id\":";
    json += std::to_string(index);
    json += ",\"segment_id\":";
    json += canonical_json_string(request.segment_id);
    json += ",\"task_id\":";
    json += std::to_string(request.task_id);
    json.push_back('}');
  }
  json.push_back(']');
  return ics::canonical_map2_detail::sha256_hex(json);
}

inline std::map<int, std::vector<std::size_t>>
raw_bag_runtime_mapping(
    const std::vector<ics::EventRuntimeBagRequest>& requests) {
  std::map<int, std::vector<std::size_t>> mapping;
  for (std::size_t index = 0; index < requests.size(); ++index) {
    mapping[requests[index].task_id].push_back(index);
  }
  return mapping;
}

inline std::string raw_bag_mapping_sha256(
    const std::vector<ics::EventRuntimeBagRequest>& requests) {
  const auto mapping = raw_bag_runtime_mapping(requests);
  std::string json = "[";
  bool first_task = true;
  for (const auto& [task_id, runtime_ids] : mapping) {
    if (!first_task) {
      json.push_back(',');
    }
    first_task = false;
    json +=
        "{\"segment_ids_in_protected_input_order\":[";
    for (std::size_t index = 0;
         index < runtime_ids.size(); ++index) {
      if (index != 0U) {
        json.push_back(',');
      }
      json += canonical_json_string(
          requests[runtime_ids[index]].segment_id);
    }
    json += "],\"task_id\":";
    json += std::to_string(task_id);
    json.push_back('}');
  }
  json.push_back(']');
  return ics::canonical_map2_detail::sha256_hex(json);
}

inline std::vector<double> validated_original_entry_times(
    const std::vector<ics::EventRuntimeBagRequest>& requests,
    const std::vector<double>& original_entry_times) {
  if (original_entry_times.size() != requests.size()) {
    throw py::value_error(
        "original_entry_times must align one-to-one with bag_records");
  }
  std::map<int, std::uint64_t> task_time_bits;
  for (std::size_t index = 0; index < requests.size(); ++index) {
    const double value = original_entry_times[index];
    if (!std::isfinite(value) || value < 0.0 ||
        value > requests[index].release_time + 1.0e-9) {
      throw py::value_error(
          "original_entry_times must be finite, non-negative, "
          "and no later than segment release_time");
    }
    const auto bits =
        ics::event_runtime_detail::timestamp_bits(value);
    const auto [found, inserted] =
        task_time_bits.emplace(requests[index].task_id, bits);
    if (!inserted && found->second != bits) {
      throw py::value_error(
          "all segments of one raw task must share the exact "
          "original_entry_time");
    }
  }
  return original_entry_times;
}

inline std::string raw_bag_original_entry_mapping_sha256(
    const std::vector<ics::EventRuntimeBagRequest>& requests,
    const std::vector<double>& original_entry_times) {
  const auto mapping = raw_bag_runtime_mapping(requests);
  ics::g4irsf14_clone_detail::CanonicalFields fields;
  fields.string(
      "schema",
      "czr005.g4irsf15.raw_bag_original_entry_mapping.v1");
  fields.unsigned_integer(
      "raw_bag_count",
      static_cast<std::uint64_t>(mapping.size()));
  for (const auto& [task_id, runtime_ids] : mapping) {
    ics::g4irsf14_clone_detail::CanonicalFields item;
    item.integer("task_id", task_id);
    std::vector<int> ids;
    ids.reserve(runtime_ids.size());
    for (const auto runtime_id : runtime_ids) {
      ids.push_back(static_cast<int>(runtime_id));
    }
    item.integers("runtime_bag_ids", ids);
    item.floating(
        "original_entry_time",
        original_entry_times[runtime_ids.front()]);
    fields.string("raw_bag", item.payload());
  }
  return ics::canonical_map2_detail::sha256_hex(
      fields.payload());
}

inline ics::EventDrivenJunctionConfig frozen_config(
    const std::vector<std::vector<double>>& scorer_w1,
    const std::vector<double>& scorer_b1,
    const std::vector<double>& scorer_w2,
    double scorer_b2,
    double scorer_risk_margin_threshold,
    double scorer_risk_bottleneck_threshold,
    const std::string& scorer_model_sha256,
    const std::string& research_profile) {
  if (research_profile != "G15_FROZEN" &&
      research_profile != "G20_S4_J2") {
    throw std::invalid_argument(
        "research_profile must be G15_FROZEN or G20_S4_J2");
  }
  // Do not add knobs here.  Descriptor discovery and both matched branches
  // must use the exact Stage-14E production tuple.
  ics::EventDrivenJunctionConfig config;
  config.queue_discipline = "aging";
  config.retry_interval = 0.25;
  config.minimum_service_seconds = 1.0e-3;
  config.dispatch_headway_seconds = 1.0e-3;
  config.history_limit = 8;
  config.max_decisions_per_bag = 512;
  config.max_events = 20000000;
  config.max_simulation_time = -1.0;
  config.trace_limit = 0;
  config.event_trace_limit = 0;
  config.trace_shard_count = 1;
  config.trace_shard_index = 0;
  config.local_queue_capacity = 32;
  config.deadlock_retry_threshold = 8;
  config.diagnostic_hops = 2;
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  config.enable_pibt_lite = false;
  config.enable_deadlock_escape = true;
  config.enable_fault_policy = true;
  config.resource_semantics = "R3_java_node_window_compatible";
  config.entry_headway_seconds = 1.0e-3;
  config.pressure_mode = "off";
  config.pressure_weight = 2.0;
  config.pressure_age_weight = 0.05;
  config.pressure_distance_bias = 0.25;
  config.admission_mode = "off";
  config.credit_validity_seconds = 1.0;
  config.credit_snapshot_max_age_seconds = 1.0;
  config.credit_capacity_per_edge = 1;
  config.credit_lifecycle_limit = 512;
  config.pibt_mode = "P2";
  config.pibt_max_ready_bags = 8;
  config.pibt_max_local_resources = 32;
  config.pibt_max_candidates_per_bag = 8;
  config.scorer_mode = "S1_frozen_g4e_legal_local_adapter";
  config.scorer_w1 = scorer_w1;
  config.scorer_b1 = scorer_b1;
  config.scorer_w2 = scorer_w2;
  config.scorer_b2 = scorer_b2;
  config.scorer_risk_margin_threshold =
      scorer_risk_margin_threshold;
  config.scorer_risk_bottleneck_threshold =
      scorer_risk_bottleneck_threshold;
  config.scorer_model_sha256 = scorer_model_sha256;
  config.framework_mode = "event_loop_one_step";
  config.priority_mode = "Q0";
  config.pibt_preference_mode = "current";
  config.selective_credit_contention_threshold = 1;
  config.event_semantics =
      "E4_batch_plus_destination_merge_request";
  config.enable_opportunity_telemetry = false;
  config.opportunity_trace_limit = 0;
  config.merge_grant_rule = "M0";
  config.merge_grant_max_pending_requests = 256;
  config.merge_grant_lifecycle_limit = 8192;
  // Outcome-free, local-only sidecar for I1 model training.  This toggle
  // records observations but cannot alter source, junction, or merge order.
  config.enable_g4irsf17_causal_source_features = true;
  if (research_profile == "G20_S4_J2") {
    // G20 reuses the exact clone/intervention engine while changing only the
    // frozen control arm to the selected G19 decentralized baseline.  No
    // future route, global reservation scan, or second planning framework is
    // introduced here.
    config.scorer_mode = "S4_queue_aware_rule_only";
    config.scorer_model_sha256.clear();
    config.merge_grant_rule = "M3";
    config.merge_grant_timing_mode =
        "jit_fair_aging_deadline";
    config.enable_g4irsf17_causal_source_features = false;
  }
  return config;
}

inline py::dict frozen_controls_row(
    const std::string& research_profile) {
  py::dict row;
  row["research_profile"] = research_profile;
  row["resource_semantics"] = "R3_java_node_window_compatible";
  row["scorer_mode"] =
      research_profile == "G20_S4_J2"
          ? "S4_queue_aware_rule_only"
          : "S1_frozen_g4e_legal_local_adapter";
  row["pibt_mode"] = "P2";
  row["pressure_mode"] = "C0_off";
  row["priority_mode"] = "Q0";
  row["event_semantics"] =
      "E4_batch_plus_destination_merge_request";
  row["merge_grant_rule"] =
      research_profile == "G20_S4_J2" ? "M3" : "M0";
  row["merge_grant_timing_mode"] =
      research_profile == "G20_S4_J2"
          ? "jit_fair_aging_deadline"
          : "eager";
  row["admission_mode"] = "off";
  row["frozen_tuple"] =
      research_profile == "G20_S4_J2"
          ? "R3/S4/P2/C0/Q0/E4/J2"
          : ics::kG4IRSF14CausalFrozenTuple;
  row["reservation_depth"] = 1;
  row["max_events"] = 20000000;
  row["max_simulation_time"] = -1.0;
  return row;
}

inline int kind_index(BoundaryKind kind) {
  switch (kind) {
    case BoundaryKind::kSourceArbitration:
      return 0;
    case BoundaryKind::kJunctionRouteArbitration:
      return 1;
    case BoundaryKind::kHoldReleaseOpportunity:
      return 2;
    default:
      return -1;
  }
}

inline const char* kind_token(int index) {
  static constexpr std::array<const char*, 3> names{
      "I1", "I3", "I4"};
  if (index < 0 || index >= static_cast<int>(names.size())) {
    throw std::logic_error("invalid G4IRSF15 intervention kind index");
  }
  return names[static_cast<std::size_t>(index)];
}

inline InterventionKind intervention_kind_for(int index) {
  switch (index) {
    case 0:
      return InterventionKind::kSourceOrderSwap;
    case 1:
      return InterventionKind::kNextEdge;
    case 2:
      return InterventionKind::kHoldRelease;
    default:
      throw std::logic_error("invalid G4IRSF15 intervention kind index");
  }
}

inline std::uint32_t mask_for_index(int index) {
  switch (index) {
    case 0:
      return ics::kG4IRSF14CausalCandidateI1;
    case 1:
      return ics::kG4IRSF14CausalCandidateI3;
    case 2:
      return ics::kG4IRSF14CausalCandidateI4;
    default:
      throw std::logic_error("invalid G4IRSF15 intervention kind index");
  }
}

inline py::dict state_digest_row(
    const ics::G4IRSF14RuntimeStateDigests& state) {
  state.validate();
  py::dict row;
  row["event_queue_sha256"] = state.event_queue_sha256;
  row["current_time_sha256"] = state.current_time_sha256;
  row["bags_sha256"] = state.bags_sha256;
  row["source_queues_sha256"] = state.source_queues_sha256;
  row["junction_queues_sha256"] = state.junction_queues_sha256;
  row["local_service_calendars_sha256"] =
      state.local_service_calendars_sha256;
  row["corridor_state_sha256"] = state.corridor_state_sha256;
  row["scheduled_incoming_sha256"] =
      state.scheduled_incoming_sha256;
  row["credits_sha256"] = state.credits_sha256;
  row["merge_grants_sha256"] = state.merge_grants_sha256;
  row["fault_state_sha256"] = state.fault_state_sha256;
  row["pibt_owner_state_sha256"] =
      state.pibt_owner_state_sha256;
  row["deterministic_counters_sha256"] =
      state.deterministic_counters_sha256;
  row["scorer_state_sha256"] = state.scorer_state_sha256;
  row["result_accumulator_sha256"] =
      state.result_accumulator_sha256;
  row["current_runtime_hashes_sha256"] =
      state.current_runtime_hashes_sha256;
  row["congestion_beacons_sha256"] =
      state.congestion_beacons_sha256;
  row["microphase_state_sha256"] =
      state.microphase_state_sha256;
  return row;
}

inline std::string i1_action(int runtime_bag_id) {
  return "SOURCE_ADMIT_RUNTIME_BAG_ID=" +
         std::to_string(runtime_bag_id);
}

inline std::string i3_action(int runtime_bag_id,
                             int next_node) {
  return "NEXT_EDGE_RUNTIME_BAG_ID=" +
         std::to_string(runtime_bag_id) +
         ";NEXT_NODE=" + std::to_string(next_node);
}

inline std::string i4_action(int runtime_bag_id,
                             bool release) {
  return std::string(release ? "RELEASE_RUNTIME_BAG_ID="
                             : "SAFE_HOLD_RUNTIME_BAG_ID=") +
         std::to_string(runtime_bag_id);
}

struct PopulationCandidate {
  Skeleton skeleton;
  Strata strata;
  std::uint64_t event_ordinal = 0;
  bool pibt_prefilter_candidate_event = false;
  int peer_runtime_bag_id = -1;
  int selected_next_node = -1;
  bool selected_boolean = false;
  int candidate_action_count = 0;
  std::string population_group_sha256;
  std::string population_selection_sha256;
  std::string baseline_action;
  std::string intervention_action;
  std::string expected_action_change_type;
  bool explicitly_selected_route_action = false;
};

inline std::string population_group_sha256(
    const Skeleton& skeleton,
    const Strata& strata,
    std::uint64_t event_ordinal,
    bool pibt_prefilter_candidate_event) {
  const int index = kind_index(skeleton.kind);
  if (index < 0) {
    throw std::invalid_argument(
        "population skeleton kind is outside I1/I3/I4");
  }
  return ics::g4irsf15_offline_population_group_sha256(
      skeleton, strata, event_ordinal,
      pibt_prefilter_candidate_event);
}

inline std::optional<PopulationCandidate>
primary_population_candidate(
    const Skeleton& skeleton,
    const Strata& strata,
    std::uint64_t event_ordinal,
    bool pibt_prefilter_candidate_event) {
  const int index = kind_index(skeleton.kind);
  if (index < 0) {
    return std::nullopt;
  }
  PopulationCandidate candidate;
  candidate.skeleton = skeleton;
  candidate.strata = strata;
  candidate.event_ordinal = event_ordinal;
  candidate.pibt_prefilter_candidate_event =
      pibt_prefilter_candidate_event;
  const auto projection =
      ics::g4irsf15_project_offline_population(
          skeleton, strata, event_ordinal,
          pibt_prefilter_candidate_event);
  if (!projection.has_value()) {
    return std::nullopt;
  }
  candidate.population_group_sha256 =
      projection->population_group_sha256;
  candidate.peer_runtime_bag_id =
      projection->primary_local_action.peer_runtime_bag_id;
  candidate.selected_next_node =
      projection->primary_local_action.selected_next_node;
  candidate.selected_boolean =
      projection->primary_local_action.selected_boolean;
  candidate.population_selection_sha256 =
      projection->population_selection_evidence_sha256;
  candidate.candidate_action_count =
      projection->primary_local_action.candidate_action_count;
  if (index == 0) {
    candidate.baseline_action =
        i1_action(skeleton.runtime_bag_id);
    candidate.intervention_action =
        i1_action(candidate.peer_runtime_bag_id);
    candidate.expected_action_change_type =
        "SOURCE_ADMIT_COMMIT";
  } else if (index == 1) {
    candidate.baseline_action =
        i3_action(skeleton.runtime_bag_id,
                  skeleton.baseline_next_node);
    candidate.intervention_action =
        i3_action(skeleton.runtime_bag_id,
                  candidate.selected_next_node);
    candidate.expected_action_change_type =
        "EDGE_COMMIT_OR_MERGE_REQUEST_ENQUEUED";
  } else {
    candidate.baseline_action =
        i4_action(skeleton.runtime_bag_id, true);
    candidate.intervention_action =
        i4_action(skeleton.runtime_bag_id, false);
    candidate.expected_action_change_type =
        "SAFE_HOLD_UNTIL_NEXT_JUNCTION_SERVICE_OPPORTUNITY";
  }
  return candidate;
}

inline std::optional<PopulationCandidate>
route_action_population_candidate(
    const Skeleton& skeleton,
    const Strata& strata,
    std::uint64_t event_ordinal,
    bool pibt_prefilter_candidate_event,
    const std::string& action_kind,
    int selected_next_node) {
  const int index = kind_index(skeleton.kind);
  const bool next_edge = action_kind == "NEXT_EDGE";
  const bool wait = action_kind == "WAIT";
  if ((next_edge && index != 1) || (wait && index != 2) ||
      (!next_edge && !wait)) {
    return std::nullopt;
  }

  ics::G4IRSF15PrimaryLocalAction action;
  if (next_edge) {
    if (selected_next_node == skeleton.baseline_next_node ||
        std::find(skeleton.legal_next_edges.begin(),
                  skeleton.legal_next_edges.end(),
                  selected_next_node) ==
            skeleton.legal_next_edges.end()) {
      return std::nullopt;
    }
    action.selected_next_node = selected_next_node;
    action.candidate_action_count = static_cast<int>(
        std::count_if(
            skeleton.legal_next_edges.begin(),
            skeleton.legal_next_edges.end(),
            [&](int next) {
              return next != skeleton.baseline_next_node;
            }));
  } else {
    if (!skeleton.baseline_release) {
      return std::nullopt;
    }
    action.selected_boolean = false;
    action.candidate_action_count = 1;
  }

  PopulationCandidate candidate;
  candidate.skeleton = skeleton;
  candidate.strata = strata;
  candidate.event_ordinal = event_ordinal;
  candidate.pibt_prefilter_candidate_event =
      pibt_prefilter_candidate_event;
  candidate.selected_next_node = action.selected_next_node;
  candidate.selected_boolean = action.selected_boolean;
  candidate.candidate_action_count = action.candidate_action_count;
  candidate.population_group_sha256 = population_group_sha256(
      skeleton, strata, event_ordinal,
      pibt_prefilter_candidate_event);
  candidate.population_selection_sha256 =
      ics::g4irsf15_population_selection_evidence_sha256(
          candidate.population_group_sha256, action);
  candidate.explicitly_selected_route_action = true;
  if (next_edge) {
    candidate.baseline_action = i3_action(
        skeleton.runtime_bag_id, skeleton.baseline_next_node);
    candidate.intervention_action = i3_action(
        skeleton.runtime_bag_id, selected_next_node);
    candidate.expected_action_change_type =
        "EDGE_COMMIT_OR_MERGE_REQUEST_ENQUEUED";
  } else {
    candidate.baseline_action =
        i4_action(skeleton.runtime_bag_id, true);
    candidate.intervention_action =
        i4_action(skeleton.runtime_bag_id, false);
    candidate.expected_action_change_type =
        "SAFE_HOLD_UNTIL_NEXT_JUNCTION_SERVICE_OPPORTUNITY";
  }
  return candidate;
}

inline Skeleton skeleton_from_boundary(
    const Boundary& boundary) {
  Skeleton skeleton;
  skeleton.kind = boundary.kind;
  skeleton.time = boundary.time;
  skeleton.event_seq = boundary.event_seq;
  skeleton.node = boundary.node;
  skeleton.runtime_bag_id = boundary.runtime_bag_id;
  skeleton.baseline_next_node =
      boundary.baseline_next_node;
  skeleton.baseline_release = boundary.baseline_release;
  skeleton.source_ready_order =
      boundary.source_ready_order;
  skeleton.g4irsf17_i1_observation_available =
      boundary.g4irsf17_i1_observation_available;
  skeleton.g4irsf17_i1_observation_peer_runtime_bag_id =
      boundary.g4irsf17_i1_observation_peer_runtime_bag_id;
  skeleton.g4irsf17_i1_baseline_observation =
      boundary.g4irsf17_i1_baseline_observation;
  skeleton.g4irsf17_i1_treatment_observation =
      boundary.g4irsf17_i1_treatment_observation;
  skeleton.g4irsf17_i1_pairwise_features =
      boundary.g4irsf17_i1_pairwise_features;
  skeleton.g4irsf20_route_observation_available =
      boundary.g4irsf20_route_observation_available;
  skeleton.g4irsf20_route_normal_flow =
      boundary.g4irsf20_route_normal_flow;
  skeleton.g4irsf20_route_baseline_candidate_index =
      boundary.g4irsf20_route_baseline_candidate_index;
  skeleton.g4irsf20_route_candidate_next_nodes =
      boundary.g4irsf20_route_candidate_next_nodes;
  skeleton.g4irsf20_route_candidate_features =
      boundary.g4irsf20_route_candidate_features;
  skeleton.legal_next_edges =
      boundary.legal_next_edges;
  return skeleton;
}

template <typename ObservationOwner>
inline py::object g4irsf17_i1_observation_pair_row(
    const ObservationOwner& owner,
    int expected_peer_runtime_bag_id) {
  if (!owner.g4irsf17_i1_observation_available) {
    return py::none();
  }
  if (owner.g4irsf17_i1_observation_peer_runtime_bag_id !=
      expected_peer_runtime_bag_id) {
    throw std::logic_error(
        "G17 I1 observation peer disagrees with primary causal action");
  }
  const auto candidate_names =
      ics::g4irsf17_source_candidate_feature_names();
  const auto context_names =
      ics::g4irsf17_source_context_feature_names();
  const auto pairwise_names =
      ics::g4irsf17_source_pairwise_feature_names();
  py::list canonical_feature_names;
  for (const char* name : candidate_names) {
    canonical_feature_names.append(name);
  }
  for (const char* name : context_names) {
    canonical_feature_names.append(name);
  }
  py::list pairwise_feature_names;
  for (const char* name : pairwise_names) {
    pairwise_feature_names.append(name);
  }
  const auto observation_mapping =
      [&](const auto& values) {
    py::dict mapped;
    for (std::size_t index = 0; index < candidate_names.size(); ++index) {
      mapped[candidate_names[index]] = values[index];
    }
    for (std::size_t index = 0; index < context_names.size(); ++index) {
      mapped[context_names[index]] =
          values[candidate_names.size() + index];
    }
    return mapped;
  };
  const auto vector_row = [&](const auto& values) {
    py::list row;
    for (const double value : values) {
      row.append(value);
    }
    return row;
  };
  py::dict baseline = observation_mapping(
      owner.g4irsf17_i1_baseline_observation);
  py::dict treatment = observation_mapping(
      owner.g4irsf17_i1_treatment_observation);
  py::list candidates;
  candidates.append(baseline);
  candidates.append(treatment);
  py::list vectors;
  vectors.append(vector_row(
      owner.g4irsf17_i1_baseline_observation));
  vectors.append(vector_row(
      owner.g4irsf17_i1_treatment_observation));
  py::dict row;
  row["schema"] =
      "czr005.g4irsf17.i1_pre_action_observation_pair.v1";
  row["feature_names"] = std::move(canonical_feature_names);
  row["pairwise_feature_names"] =
      std::move(pairwise_feature_names);
  row["candidate_observations"] = std::move(candidates);
  row["canonical_candidate_observations"] =
      std::move(vectors);
  row["baseline_observation"] = std::move(baseline);
  row["treatment_observation"] = std::move(treatment);
  row["baseline_candidate_index"] = 0;
  row["treatment_candidate_index"] = 1;
  row["pairwise_features"] = vector_row(
      owner.g4irsf17_i1_pairwise_features);
  row["runtime_global_scan_count"] = 0;
  row["runtime_future_route_read_count"] = 0;
  row["runtime_future_schedule_read_count"] = 0;
  row["runtime_full_astar_call_count"] = 0;
  row["identity_fields_are_trace_only"] = true;
  return std::move(row);
}

template <typename ObservationOwner>
inline py::object g4irsf20_route_observation_row(
    const ObservationOwner& owner,
    int expected_treatment_next_node) {
  if (!owner.g4irsf20_route_observation_available) {
    return py::none();
  }
  static constexpr std::array<const char*, 23> kFeatureNames{{
      "event_time",
      "target_queue_length",
      "target_scheduled_incoming",
      "corridor_next_available",
      "target_next_available",
      "travel_time",
      "static_potential",
      "priority_slack_seconds",
      "priority_age_seconds",
      "recent_visit_count",
      "junction_queue_length",
      "junction_next_available_time",
      "priority_local_contention",
      "current_goal_queue_length",
      "target_goal_queue_length",
      "target_goal_scheduled_incoming",
      "current_goal_max_wait",
      "goal_conditioned_differential",
      "estimated_service_rate",
      "service_weighted_pressure",
      "advertised_fault",
      "fault_message_age_seconds",
      "two_hop_queue_pressure",
  }};
  const auto& nodes = owner.g4irsf20_route_candidate_next_nodes;
  const auto& features = owner.g4irsf20_route_candidate_features;
  if (nodes.size() != features.size() || nodes.size() < 2U) {
    throw std::logic_error("G20 Route observation shape drifted");
  }
  const auto treatment_it = std::find(
      nodes.begin(), nodes.end(), expected_treatment_next_node);
  if (treatment_it == nodes.end()) {
    throw std::logic_error(
        "G20 Route treatment is absent from candidate observation");
  }
  const int treatment_index = static_cast<int>(
      std::distance(nodes.begin(), treatment_it));
  py::list feature_names;
  for (const char* name : kFeatureNames) {
    feature_names.append(name);
  }
  py::list candidate_observations;
  py::list canonical_candidate_observations;
  for (const auto& values : features) {
    if (values.size() != kFeatureNames.size()) {
      throw std::logic_error(
          "G20 Route observation width drifted");
    }
    py::dict mapped;
    py::list vector;
    for (std::size_t index = 0; index < values.size(); ++index) {
      if (index == 20U) {
        mapped[kFeatureNames[index]] =
            py::bool_(values[index] != 0.0);
      } else {
        mapped[kFeatureNames[index]] = values[index];
      }
      vector.append(values[index]);
    }
    candidate_observations.append(std::move(mapped));
    canonical_candidate_observations.append(std::move(vector));
  }
  py::dict row;
  row["schema"] =
      "czr005.g4irsf20.route_pre_action_observation_set.v1";
  row["feature_names"] = std::move(feature_names);
  row["candidate_observations"] =
      std::move(candidate_observations);
  row["canonical_candidate_observations"] =
      std::move(canonical_candidate_observations);
  row["candidate_next_nodes"] = nodes;
  row["baseline_candidate_index"] =
      owner.g4irsf20_route_baseline_candidate_index;
  row["treatment_candidate_index"] = treatment_index;
  row["normal_flow"] = owner.g4irsf20_route_normal_flow;
  row["identity_fields_are_trace_only"] = true;
  row["runtime_global_scan_count"] = 0;
  row["runtime_future_route_read_count"] = 0;
  row["runtime_future_schedule_read_count"] = 0;
  row["runtime_full_astar_call_count"] = 0;
  return std::move(row);
}

inline py::dict population_candidate_row(
    const PopulationCandidate& candidate,
    const std::vector<ics::EventRuntimeBagRequest>& requests) {
  if (candidate.skeleton.runtime_bag_id < 0 ||
      static_cast<std::size_t>(
          candidate.skeleton.runtime_bag_id) >=
          requests.size()) {
    throw std::logic_error(
        "skeleton runtime bag id is outside input request order");
  }
  const auto& request = requests.at(
      static_cast<std::size_t>(
          candidate.skeleton.runtime_bag_id));
  const int index = kind_index(candidate.skeleton.kind);
  py::dict row;
  row["schema"] = kSkeletonSchema;
  row["skeleton_id"] =
      candidate.population_selection_sha256;
  row["population_group_sha256"] =
      candidate.population_group_sha256;
  row["skeleton_selection_sha256"] =
      candidate.population_selection_sha256;
  row["kind"] = kind_token(index);
  row["event_ordinal"] =
      py::int_(candidate.event_ordinal);
  row["event_seq"] =
      py::int_(candidate.skeleton.event_seq);
  row["event_time"] = candidate.skeleton.time;
  row["event_time_bits"] = py::int_(
      ics::event_runtime_detail::timestamp_bits(
          candidate.skeleton.time));
  row["event_hour_floor"] = static_cast<int>(
      std::floor(candidate.skeleton.time / 3600.0));
  row["node"] = candidate.skeleton.node;
  row["runtime_bag_id"] =
      candidate.skeleton.runtime_bag_id;
  row["task_id"] = request.task_id;
  row["segment_id"] = request.segment_id;
  row["start"] = request.start;
  row["goal"] = request.goal;
  row["release_time"] = request.release_time;
  row["deadline"] = request.deadline;
  row["source"] = request.source;
  row["peer_runtime_bag_id"] =
      candidate.peer_runtime_bag_id;
  row["baseline_next_node"] =
      candidate.skeleton.baseline_next_node;
  row["selected_next_node"] =
      candidate.selected_next_node;
  row["baseline_release"] =
      candidate.skeleton.baseline_release;
  row["selected_boolean"] =
      candidate.selected_boolean;
  row["source_ready_order"] =
      candidate.skeleton.source_ready_order;
  row["legal_next_edges"] =
      candidate.skeleton.legal_next_edges;
  row["candidate_action_count"] =
      candidate.candidate_action_count;
  row["candidate_action_count_semantics"] =
      "ALTERNATIVES_EXCLUDING_BASELINE";
  row["alternative_action_count"] =
      candidate.candidate_action_count;
  row["total_legal_action_count"] =
      candidate.candidate_action_count + 1;
  row["active_merge_capability_count"] =
      candidate.strata.active_merge_capability_count;
  row["pending_merge_request_count"] =
      candidate.strata.pending_merge_request_count;
  row["active_physical_fault_edge_count"] =
      candidate.strata.active_physical_fault_edge_count;
  row["queued_bag_count"] =
      candidate.strata.queued_bag_count;
  row["pibt_prefilter_candidate_event"] =
      candidate.pibt_prefilter_candidate_event;
  row["baseline_action"] = candidate.baseline_action;
  row["intervention_action"] =
      candidate.intervention_action;
  row["expected_action_change_type"] =
      candidate.expected_action_change_type;
  py::object observation = py::none();
  if (index == 0) {
    observation = g4irsf17_i1_observation_pair_row(
        candidate.skeleton,
        candidate.peer_runtime_bag_id);
  } else if (index == 1) {
    observation = g4irsf20_route_observation_row(
        candidate.skeleton,
        candidate.selected_next_node);
  }
  row["observation_pair"] = observation;
  row["route_observation"] =
      index == 1 ? observation : py::object(py::none());
  row["primary_action_selection"] =
      "LOCAL_STABLE_NUMERIC_MIN_PEER_OR_NEXT_NODE_I4_UNIQUE";
  row["outcome_free"] = true;
  row["runtime_state_sha256"] = py::none();
  row["boundary_sha256"] = py::none();
  return row;
}

inline py::dict g4irsf20_route_census_row(
    const PopulationCandidate& candidate) {
  const auto& skeleton = candidate.skeleton;
  if (!skeleton.g4irsf20_route_observation_available ||
      skeleton.g4irsf20_route_baseline_candidate_index < 0 ||
      static_cast<std::size_t>(
          skeleton.g4irsf20_route_baseline_candidate_index) >=
          skeleton.g4irsf20_route_candidate_features.size()) {
    throw std::logic_error(
        "G20 Route census row lacks its pre-action observation");
  }
  const auto& baseline =
      skeleton.g4irsf20_route_candidate_features.at(
          static_cast<std::size_t>(
              skeleton.g4irsf20_route_baseline_candidate_index));
  if (baseline.size() != 23U) {
    throw std::logic_error("G20 Route census feature width drifted");
  }
  py::dict row;
  row["schema"] = kSkeletonSchema;
  row["skeleton_id"] = candidate.population_selection_sha256;
  row["population_group_sha256"] = candidate.population_group_sha256;
  row["skeleton_selection_sha256"] =
      candidate.population_selection_sha256;
  row["kind"] = "I3";
  row["event_ordinal"] = py::int_(candidate.event_ordinal);
  row["runtime_bag_id"] = skeleton.runtime_bag_id;
  row["wait_age_seconds"] = baseline[8];
  row["candidate_count"] =
      static_cast<int>(
          skeleton.g4irsf20_route_candidate_next_nodes.size());
  row["baseline_next_node"] = skeleton.baseline_next_node;
  row["legal_next_edges"] = skeleton.legal_next_edges;
  row["wait_available"] = true;
  row["normal_flow"] = skeleton.g4irsf20_route_normal_flow;
  return row;
}

struct PrimaryDescriptor {
  PopulationCandidate population;
  Boundary boundary;
  Intervention intervention;
  std::string descriptor_id;
  std::string h_system_sha256;
};

inline PrimaryDescriptor seal_primary_descriptor(
    const PopulationCandidate& selected_population,
    const Boundary& boundary,
    const Strata& strata,
    bool pibt_prefilter_candidate_event) {
  boundary.validate();
  const auto replayed_population =
      primary_population_candidate(
          skeleton_from_boundary(boundary), strata,
          selected_population.event_ordinal,
          pibt_prefilter_candidate_event);
  if (!replayed_population.has_value() ||
      replayed_population->population_group_sha256 !=
          selected_population.population_group_sha256 ||
      replayed_population->population_selection_sha256 !=
          selected_population.population_selection_sha256) {
    throw std::invalid_argument(
        "selected skeleton is not the replayed native primary action");
  }
  Intervention intervention;
  intervention.kind = intervention_kind_for(
      kind_index(boundary.kind));
  intervention.horizon = Horizon::kAffectedBag;
  intervention.runtime_bag_id = boundary.runtime_bag_id;
  intervention.peer_runtime_bag_id =
      selected_population.peer_runtime_bag_id;
  intervention.selected_next_node =
      selected_population.selected_next_node;
  intervention.selected_boolean =
      selected_population.selected_boolean;
  intervention.validate_against(boundary);

  PrimaryDescriptor descriptor;
  descriptor.population = *replayed_population;
  descriptor.boundary = boundary;
  descriptor.intervention = intervention;
  descriptor.descriptor_id =
      intervention.intervention_sha256(boundary);
  auto h_system = intervention;
  h_system.horizon = Horizon::kSelectedSystem;
  descriptor.h_system_sha256 =
      h_system.intervention_sha256(boundary);
  return descriptor;
}

inline PrimaryDescriptor seal_route_action_descriptor(
    const PopulationCandidate& selected_population,
    const Boundary& boundary,
    const Strata& strata,
    bool pibt_prefilter_candidate_event,
    const std::string& action_kind) {
  boundary.validate();
  const auto replayed_population =
      route_action_population_candidate(
          skeleton_from_boundary(boundary), strata,
          selected_population.event_ordinal,
          pibt_prefilter_candidate_event, action_kind,
          selected_population.selected_next_node);
  if (!replayed_population.has_value() ||
      replayed_population->population_group_sha256 !=
          selected_population.population_group_sha256 ||
      replayed_population->population_selection_sha256 !=
          selected_population.population_selection_sha256 ||
      replayed_population->selected_next_node !=
          selected_population.selected_next_node ||
      replayed_population->selected_boolean !=
          selected_population.selected_boolean) {
    throw std::invalid_argument(
        "selected Route action is not the replayed native legal action");
  }
  Intervention intervention;
  intervention.kind = intervention_kind_for(
      kind_index(boundary.kind));
  intervention.horizon = Horizon::kAffectedBag;
  intervention.runtime_bag_id = boundary.runtime_bag_id;
  intervention.selected_next_node =
      selected_population.selected_next_node;
  intervention.selected_boolean =
      selected_population.selected_boolean;
  intervention.validate_against(boundary);

  PrimaryDescriptor descriptor;
  descriptor.population = *replayed_population;
  descriptor.boundary = boundary;
  descriptor.intervention = intervention;
  descriptor.descriptor_id =
      intervention.intervention_sha256(boundary);
  auto h_system = intervention;
  h_system.horizon = Horizon::kSelectedSystem;
  descriptor.h_system_sha256 =
      h_system.intervention_sha256(boundary);
  return descriptor;
}

inline py::dict descriptor_row(
    const PrimaryDescriptor& descriptor) {
  const auto& boundary = descriptor.boundary;
  const auto& population = descriptor.population;
  const int index = kind_index(boundary.kind);
  py::dict row;
  row["schema"] = kDescriptorSchema;
  row["descriptor_id"] = descriptor.descriptor_id;
  row["skeleton_id"] =
      population.population_selection_sha256;
  row["population_group_sha256"] =
      population.population_group_sha256;
  row["population_selection_sha256"] =
      population.population_selection_sha256;
  row["kind"] = kind_token(index);
  row["kind_name"] =
      ics::g4irsf14_clone_intervention_kind_name(
          descriptor.intervention.kind);
  row["clone_group_id"] = boundary.clone_group_id;
  row["event_ordinal"] =
      py::int_(population.event_ordinal);
  row["event_seq"] = py::int_(boundary.event_seq);
  row["event_time"] = boundary.time;
  row["event_time_bits"] = py::int_(
      ics::event_runtime_detail::timestamp_bits(boundary.time));
  row["node"] = boundary.node;
  row["runtime_state_sha256"] = boundary.runtime_state_sha256;
  row["boundary_sha256"] = boundary.boundary_sha256();
  row["boundary_kind"] =
      ics::g4irsf14_clone_boundary_kind_name(boundary.kind);
  row["runtime_bag_id"] =
      descriptor.intervention.runtime_bag_id;
  row["peer_runtime_bag_id"] =
      descriptor.intervention.peer_runtime_bag_id;
  row["baseline_next_node"] = boundary.baseline_next_node;
  row["selected_next_node"] =
      descriptor.intervention.selected_next_node;
  row["baseline_release"] = boundary.baseline_release;
  row["selected_boolean"] =
      descriptor.intervention.selected_boolean;
  row["source_ready_order"] = boundary.source_ready_order;
  row["legal_next_edges"] = boundary.legal_next_edges;
  row["candidate_action_count"] =
      population.candidate_action_count;
  row["candidate_action_count_semantics"] =
      "ALTERNATIVES_EXCLUDING_BASELINE";
  row["alternative_action_count"] =
      population.candidate_action_count;
  row["total_legal_action_count"] =
      population.candidate_action_count + 1;
  row["active_merge_capability_count"] =
      population.strata.active_merge_capability_count;
  row["pending_merge_request_count"] =
      population.strata.pending_merge_request_count;
  row["active_physical_fault_edge_count"] =
      population.strata.active_physical_fault_edge_count;
  row["queued_bag_count"] =
      population.strata.queued_bag_count;
  row["pibt_prefilter_candidate_event"] =
      population.pibt_prefilter_candidate_event;
  row["primary_action_selection"] =
      population.explicitly_selected_route_action
          ? "EXPLICIT_NATIVE_LEGAL_ROUTE_ACTION"
          : "LOCAL_STABLE_NUMERIC_MIN_PEER_OR_NEXT_NODE_I4_UNIQUE";
  row["baseline_action"] = population.baseline_action;
  row["intervention_action"] =
      population.intervention_action;
  row["expected_action_change_type"] =
      population.expected_action_change_type;
  py::object observation = py::none();
  if (index == 0) {
    observation = g4irsf17_i1_observation_pair_row(
        boundary,
        descriptor.intervention.peer_runtime_bag_id);
  } else if (index == 1) {
    observation = g4irsf20_route_observation_row(
        boundary,
        descriptor.intervention.selected_next_node);
  }
  row["observation_pair"] = observation;
  row["route_observation"] =
      index == 1 ? observation : py::object(py::none());
  row["horizon"] = "H_bag";
  row["intervention_sha256"] = descriptor.descriptor_id;
  py::dict horizon_hashes;
  horizon_hashes["H_bag"] = descriptor.descriptor_id;
  horizon_hashes["H_system"] = descriptor.h_system_sha256;
  row["intervention_sha256_by_horizon"] =
      std::move(horizon_hashes);
  row["state_components"] = state_digest_row(boundary.state);
  row["queue_top_not_popped"] = boundary.queue_top_not_popped;
  row["staged_event_sink_empty"] =
      boundary.staged_event_sink_empty;
  row["runtime_global_scan_count"] =
      boundary.runtime_global_scan_count;
  row["runtime_future_route_read_count"] =
      boundary.runtime_future_route_read_count;
  row["runtime_future_schedule_read_count"] =
      boundary.runtime_future_schedule_read_count;
  row["reservation_depth"] = boundary.reservation_depth;
  row["max_selected_edges_per_bag"] =
      boundary.max_selected_edges_per_bag;
  return row;
}

struct KindScanAccumulator {
  std::uint64_t mask_candidate_event_count = 0;
  std::uint64_t observed_skeleton_count = 0;
  std::uint64_t duplicate_population_group_count = 0;
  std::uint64_t eligible_action_count = 0;
  std::set<std::string> population_group_ids;
  std::vector<PopulationCandidate> population;
};

inline bool replay_skeleton_transition(Runtime& runtime) {
  const std::uint32_t mask =
      runtime.peek_causal_candidate_kind_mask() &
      (ics::kG4IRSF14CausalCandidateI1 |
       ics::kG4IRSF14CausalCandidateI3 |
       ics::kG4IRSF14CausalCandidateI4);
  if (mask == 0U) {
    return runtime.process_one_event();
  }
  const auto probe =
      runtime.probe_one_event_for_causal_skeletons();
  if (!probe.event_processed) {
    if (probe.application_reason ==
        "SKELETON_PROBE_SKIPPED_RUNTIME_LIMIT") {
      return false;
    }
    throw std::logic_error(
        "skeleton-policy replay stopped without a runtime limit");
  }
  if (probe.application_reason !=
      "SKELETON_PROBE_ONLY_NO_ACTION_CHANGED") {
    throw std::logic_error(
        "skeleton-policy replay changed a runtime action");
  }
  return true;
}

struct SelectedSkeleton {
  std::string skeleton_id;
  std::string population_group_sha256;
  int kind_index = -1;
  std::uint64_t event_ordinal = 0;
};

inline SelectedSkeleton parse_selected_skeleton(
    const py::dict& row) {
  if (strict_string(required_item(row, "schema"), "schema") !=
      kSkeletonSchema) {
    throw py::value_error(
        "unsupported G4IRSF15 causal skeleton schema");
  }
  SelectedSkeleton selected;
  selected.skeleton_id =
      strict_sha256(required_item(row, "skeleton_id"),
                    "skeleton_id");
  selected.population_group_sha256 =
      strict_sha256(
          required_item(row, "population_group_sha256"),
          "population_group_sha256");
  const auto selection_item =
      optional_item(row, "skeleton_selection_sha256");
  if (selection_item &&
      strict_sha256(selection_item,
                    "skeleton_selection_sha256") !=
          selected.skeleton_id) {
    throw py::value_error(
        "skeleton_id and skeleton_selection_sha256 disagree");
  }
  const auto kind =
      strict_string(required_item(row, "kind"), "kind");
  if (kind == "I1") {
    selected.kind_index = 0;
  } else if (kind == "I3") {
    selected.kind_index = 1;
  } else if (kind == "I4") {
    selected.kind_index = 2;
  } else {
    throw py::value_error("kind must be I1, I3, or I4");
  }
  selected.event_ordinal =
      strict_uint64(required_item(row, "event_ordinal"),
                    "event_ordinal");
  return selected;
}

inline py::dict outcome_row(
    const ics::G4IRSF15CausalBagOutcome& outcome) {
  py::dict row;
  row["runtime_bag_id"] = outcome.runtime_bag_id;
  row["task_id"] = outcome.task_id;
  row["segment_id"] = outcome.segment_id;
  row["start"] = outcome.start;
  row["goal"] = outcome.goal;
  row["current_node"] = outcome.current_node;
  row["known"] = outcome.known;
  row["completed"] = outcome.completed;
  row["failed"] = outcome.failed;
  row["status"] = outcome.status;
  row["failure_reason"] = outcome.failure_reason;
  row["release_time"] = outcome.release_time;
  row["deadline"] = outcome.deadline;
  row["admitted_time"] = outcome.admitted_time;
  row["finish_time"] = outcome.finish_time;
  row["source_wait_seconds"] = outcome.source_wait_seconds;
  row["total_local_wait_seconds"] =
      outcome.total_local_wait_seconds;
  row["junction_wait_seconds"] =
      outcome.junction_wait_seconds;
  row["merge_wait_seconds"] = outcome.merge_wait_seconds;
  row["edge_travel_seconds"] = outcome.edge_travel_seconds;
  row["node_service_seconds"] = outcome.node_service_seconds;
  row["loop_extra_seconds"] = outcome.loop_extra_seconds;
  row["completion_seconds"] = outcome.completion_seconds;
  row["decision_count"] = outcome.decision_count;
  row["retry_count"] = outcome.retry_count;
  row["loop_count"] = outcome.loop_count;
  return row;
}

inline py::dict local_snapshot_row(
    const ics::G4IRSF15LocalActionSnapshot& snapshot) {
  py::dict row;
  row["runtime_bag_id"] = snapshot.runtime_bag_id;
  row["known"] = snapshot.known;
  row["status"] = snapshot.status;
  row["current_node"] = snapshot.current_node;
  row["transit_from"] = snapshot.transit_from;
  row["transit_to"] = snapshot.transit_to;
  row["admitted_time"] = snapshot.admitted_time;
  row["decision_count"] = snapshot.decision_count;
  row["retry_count"] = snapshot.retry_count;
  row["pending_merge_request_id"] =
      py::int_(snapshot.pending_merge_request_id);
  row["pending_merge_lineage"] =
      py::int_(snapshot.pending_merge_lineage);
  row["pending_merge_upstream"] =
      snapshot.pending_merge_upstream;
  row["pending_merge_destination"] =
      snapshot.pending_merge_destination;
  row["queued_at_current_node"] =
      snapshot.queued_at_current_node;
  row["source_queued_at_current_node"] =
      snapshot.source_queued_at_current_node;
  row["junction_wakeup_pending"] =
      snapshot.junction_wakeup_pending;
  row["junction_wakeup_generation"] =
      py::int_(snapshot.junction_wakeup_generation);
  row["junction_wakeup_time"] =
      snapshot.junction_wakeup_time;
  return row;
}

inline double nearest_rank_quantile(std::vector<double> values,
                                    double probability) {
  if (values.empty()) {
    return 0.0;
  }
  std::sort(values.begin(), values.end());
  const auto rank = static_cast<std::size_t>(
      std::ceil(probability * static_cast<double>(values.size())));
  return values[std::max<std::size_t>(1U, rank) - 1U];
}

inline py::dict cohort_metrics_row(
    const std::vector<ics::G4IRSF15CausalBagOutcome>& outcomes) {
  std::vector<double> completion;
  double source_wait = 0.0;
  double local_wait = 0.0;
  double junction_wait = 0.0;
  double merge_wait = 0.0;
  double edge_travel = 0.0;
  double node_service = 0.0;
  double loop_extra = 0.0;
  std::int64_t decisions = 0;
  std::int64_t retries = 0;
  std::int64_t loops = 0;
  int known = 0;
  int completed = 0;
  int failed = 0;
  int deadline_miss = 0;
  for (const auto& outcome : outcomes) {
    known += outcome.known ? 1 : 0;
    completed += outcome.completed ? 1 : 0;
    failed += outcome.failed ? 1 : 0;
    if (outcome.completed) {
      completion.push_back(outcome.completion_seconds);
      if (outcome.deadline >= 0.0 &&
          outcome.finish_time > outcome.deadline) {
        ++deadline_miss;
      }
    }
    source_wait += outcome.source_wait_seconds;
    local_wait += outcome.total_local_wait_seconds;
    junction_wait += outcome.junction_wait_seconds;
    merge_wait += outcome.merge_wait_seconds;
    edge_travel += outcome.edge_travel_seconds;
    node_service += outcome.node_service_seconds;
    loop_extra += outcome.loop_extra_seconds;
    decisions += outcome.decision_count;
    retries += outcome.retry_count;
    loops += outcome.loop_count;
  }
  const double denominator =
      outcomes.empty() ? 1.0 : static_cast<double>(outcomes.size());
  const double completion_mean =
      completion.empty()
          ? 0.0
          : std::accumulate(completion.begin(), completion.end(), 0.0) /
                static_cast<double>(completion.size());
  py::dict row;
  row["cohort_size"] = static_cast<int>(outcomes.size());
  row["known_count"] = known;
  row["completed_count"] = completed;
  row["failed_count"] = failed;
  row["deadline_miss_count"] = deadline_miss;
  row["completion_mean_seconds"] = completion_mean;
  row["completion_p95_seconds"] =
      nearest_rank_quantile(completion, 0.95);
  row["completion_p99_seconds"] =
      nearest_rank_quantile(completion, 0.99);
  row["quantile_method"] = "NEAREST_RANK_CEILING";
  row["source_wait_mean_seconds"] = source_wait / denominator;
  row["total_local_wait_mean_seconds"] = local_wait / denominator;
  row["junction_wait_mean_seconds"] = junction_wait / denominator;
  row["merge_wait_mean_seconds"] = merge_wait / denominator;
  row["edge_travel_mean_seconds"] = edge_travel / denominator;
  row["node_service_mean_seconds"] = node_service / denominator;
  row["loop_extra_mean_seconds"] = loop_extra / denominator;
  row["decision_count"] = py::int_(decisions);
  row["retry_count"] = py::int_(retries);
  row["loop_count"] = py::int_(loops);
  row["path_length_hops_total"] = py::int_(decisions);
  row["path_length_hops_mean"] =
      static_cast<double>(decisions) / denominator;
  row["path_length_definition"] =
      "COMMITTED_ONE_EDGE_ACTION_COUNT";
  return row;
}

inline double linear_quantile(std::vector<double> values,
                              double probability) {
  if (values.empty()) {
    return 0.0;
  }
  std::sort(values.begin(), values.end());
  if (values.size() == 1U) {
    return values.front();
  }
  const double position =
      probability * static_cast<double>(values.size() - 1U);
  const auto lower =
      static_cast<std::size_t>(std::floor(position));
  const auto upper =
      static_cast<std::size_t>(std::ceil(position));
  if (lower == upper) {
    return values[lower];
  }
  const double fraction =
      position - static_cast<double>(lower);
  return values[lower] * (1.0 - fraction) +
         values[upper] * fraction;
}

inline py::dict raw_bag_cohort_metrics_row(
    const std::vector<ics::G4IRSF15CausalBagOutcome>& outcomes,
    const std::vector<ics::EventRuntimeBagRequest>& requests,
    const std::vector<double>& original_entry_times) {
  const auto sufficient =
      ics::g4irsf15_build_raw_bag_sufficient_statistics(
          outcomes, requests, original_entry_times);
  std::vector<double> original_entry_totals;
  std::vector<double> java_release_totals;
  std::vector<double> scheduled_pre_release_totals;
  std::vector<double> source_wait_totals;
  std::vector<double> network_totals;
  std::vector<double> total_system_totals;
  int complete_raw_bag_count = 0;
  int completed_segment_count = 0;
  int failed_raw_bag_count = 0;
  int deadline_miss_raw_bag_count = 0;
  for (const auto& raw_bag : sufficient.rows) {
    completed_segment_count +=
        raw_bag.completed_segment_count;
    if (raw_bag.failed) {
      ++failed_raw_bag_count;
    }
    if (!raw_bag.complete) {
      continue;
    }
    ++complete_raw_bag_count;
    deadline_miss_raw_bag_count +=
        raw_bag.deadline_miss ? 1 : 0;
    original_entry_totals.push_back(
        raw_bag.original_entry_total_seconds);
    java_release_totals.push_back(
        raw_bag.java_release_total_seconds);
    scheduled_pre_release_totals.push_back(
        raw_bag.scheduled_pre_release_wait_total_seconds);
    source_wait_totals.push_back(
        raw_bag.source_wait_total_seconds);
    network_totals.push_back(
        raw_bag.network_time_total_seconds);
    total_system_totals.push_back(
        raw_bag.total_system_time_total_seconds);
  }
  const bool full_completion =
      complete_raw_bag_count ==
          static_cast<int>(sufficient.rows.size()) &&
      completed_segment_count ==
          sufficient.selected_segment_count;
  const auto mean = [](const std::vector<double>& values) {
    return values.empty()
               ? 0.0
               : std::accumulate(
                     values.begin(), values.end(), 0.0) /
                     static_cast<double>(values.size());
  };
  py::dict row;
  row["selected_segment_count"] =
      sufficient.selected_segment_count;
  row["selected_raw_bag_count"] =
      static_cast<int>(sufficient.rows.size());
  row["completed_segment_count"] =
      completed_segment_count;
  row["complete_raw_bag_count"] =
      complete_raw_bag_count;
  row["failed_raw_bag_count"] =
      failed_raw_bag_count;
  row["deadline_miss_raw_bag_count"] =
      deadline_miss_raw_bag_count;
  row["completion_rate"] =
      sufficient.rows.empty()
          ? 0.0
          : static_cast<double>(complete_raw_bag_count) /
                static_cast<double>(sufficient.rows.size());
  row["comparison_eligible"] = full_completion;
  row["primary_denominator"] =
      "original_entry_time_tth";
  row["denominator_scope"] =
      "SUM_PER_RAW_TASK_OVER_ALL_PROTECTED_SEGMENTS";
  if (full_completion) {
    row["original_entry_mean_minutes"] =
        mean(original_entry_totals) / 60.0;
    row["original_entry_median_seconds"] =
        linear_quantile(original_entry_totals, 0.5);
    row["original_entry_p95_seconds"] =
        linear_quantile(original_entry_totals, 0.95);
    row["original_entry_p99_seconds"] =
        linear_quantile(original_entry_totals, 0.99);
    row["original_entry_max_seconds"] =
        *std::max_element(original_entry_totals.begin(),
                          original_entry_totals.end());
    row["java_release_mean_minutes"] =
        mean(java_release_totals) / 60.0;
    row["scheduled_pre_release_wait_mean_minutes"] =
        mean(scheduled_pre_release_totals) / 60.0;
    row["source_wait_mean_minutes"] =
        mean(source_wait_totals) / 60.0;
    row["network_time_mean_minutes"] =
        mean(network_totals) / 60.0;
    row["total_system_time_mean_minutes"] =
        mean(total_system_totals) / 60.0;
  } else {
    row["original_entry_mean_minutes"] = py::none();
    row["original_entry_median_seconds"] = py::none();
    row["original_entry_p95_seconds"] = py::none();
    row["original_entry_p99_seconds"] = py::none();
    row["original_entry_max_seconds"] = py::none();
    row["java_release_mean_minutes"] = py::none();
    row["scheduled_pre_release_wait_mean_minutes"] =
        py::none();
    row["source_wait_mean_minutes"] = py::none();
    row["network_time_mean_minutes"] = py::none();
    row["total_system_time_mean_minutes"] = py::none();
  }
  row["survivor_original_entry_mean_minutes"] =
      original_entry_totals.empty()
          ? py::object(py::none())
          : py::object(py::float_(
                mean(original_entry_totals) / 60.0));
  row["survivor_metric_comparison_allowed"] = false;
  row["quantile_method"] =
      "LINEAR_TYPE7_N_MINUS_ONE";
  return row;
}

inline py::dict raw_bag_sufficient_statistics_sidecar_row(
    const std::vector<ics::G4IRSF15CausalBagOutcome>& outcomes,
    const std::vector<ics::EventRuntimeBagRequest>& requests,
    const std::vector<double>& original_entry_times) {
  const auto sufficient =
      ics::g4irsf15_build_raw_bag_sufficient_statistics(
          outcomes, requests, original_entry_times);
  const auto runtime_mapping_sha256 =
      runtime_segment_mapping_sha256(requests);
  const auto raw_mapping_sha256 =
      raw_bag_mapping_sha256(requests);
  const auto raw_original_entry_mapping_sha256 =
      raw_bag_original_entry_mapping_sha256(
          requests, original_entry_times);
  const auto expected_raw_bag_count =
      static_cast<int>(
          raw_bag_runtime_mapping(requests).size());
  const bool complete_coverage =
      sufficient.complete_coverage &&
      static_cast<int>(sufficient.rows.size()) ==
          expected_raw_bag_count;
  if (!complete_coverage) {
    throw std::logic_error(
        "raw-bag sufficient-statistics sidecar coverage drifted");
  }

  py::list rows;
  for (const auto& sufficient_row : sufficient.rows) {
    const auto runtime_id_mapping_sha256 =
        sufficient_row.runtime_id_mapping_sha256();
    const auto row_sha256 =
        sufficient_row.row_sha256();
    py::dict row;
    row["task_id"] = sufficient_row.task_id;
    row["runtime_bag_ids"] =
        sufficient_row.runtime_bag_ids;
    row["runtime_segment_count"] =
        static_cast<int>(
            sufficient_row.runtime_bag_ids.size());
    row["completed_segment_count"] =
        sufficient_row.completed_segment_count;
    row["complete"] = sufficient_row.complete;
    row["failed"] = sufficient_row.failed;
    row["deadline_miss"] =
        sufficient_row.deadline_miss;
    row["original_entry_total_seconds"] =
        sufficient_row.original_entry_total_seconds;
    row["java_release_total_seconds"] =
        sufficient_row.java_release_total_seconds;
    row["scheduled_pre_release_wait_total_seconds"] =
        sufficient_row
            .scheduled_pre_release_wait_total_seconds;
    row["source_wait_total_seconds"] =
        sufficient_row.source_wait_total_seconds;
    row["network_time_total_seconds"] =
        sufficient_row.network_time_total_seconds;
    row["total_system_time_total_seconds"] =
        sufficient_row.total_system_time_total_seconds;
    row["runtime_id_mapping_sha256"] =
        runtime_id_mapping_sha256;
    row["row_sha256"] = row_sha256;
    rows.append(std::move(row));
  }

  py::dict sidecar;
  sidecar["schema"] =
      "czr005.g4irsf15.raw_bag_sufficient_statistics.v1";
  sidecar["row_count"] =
      static_cast<int>(sufficient.rows.size());
  sidecar["expected_raw_bag_count"] =
      expected_raw_bag_count;
  sidecar["selected_segment_count"] =
      sufficient.selected_segment_count;
  sidecar["complete_coverage"] =
      complete_coverage;
  sidecar["task_id_order"] =
      "STRICT_ASCENDING_NUMERIC";
  sidecar["runtime_segment_mapping_sha256"] =
      runtime_mapping_sha256;
  sidecar["raw_bag_mapping_sha256"] =
      raw_mapping_sha256;
  sidecar["raw_bag_original_entry_mapping_sha256"] =
      raw_original_entry_mapping_sha256;
  sidecar["rows"] = std::move(rows);
  sidecar["content_sha256"] =
      sufficient.content_sha256(
          runtime_mapping_sha256, raw_mapping_sha256,
          raw_original_entry_mapping_sha256);
  return sidecar;
}

inline std::string causal_outcome_payload(
    const ics::G4IRSF15CausalBagOutcome& outcome) {
  ics::g4irsf14_clone_detail::CanonicalFields fields;
  fields.string("schema",
                "czr005.g4irsf15.causal_bag_outcome.v1");
  fields.integer("runtime_bag_id", outcome.runtime_bag_id);
  fields.integer("task_id", outcome.task_id);
  fields.string("segment_id", outcome.segment_id);
  fields.integer("start", outcome.start);
  fields.integer("goal", outcome.goal);
  fields.integer("current_node", outcome.current_node);
  fields.boolean("known", outcome.known);
  fields.boolean("completed", outcome.completed);
  fields.boolean("failed", outcome.failed);
  fields.string("status", outcome.status);
  fields.string("failure_reason", outcome.failure_reason);
  fields.floating("release_time", outcome.release_time);
  fields.floating("deadline", outcome.deadline);
  fields.floating("admitted_time", outcome.admitted_time);
  fields.floating("finish_time", outcome.finish_time);
  fields.floating("source_wait_seconds",
                  outcome.source_wait_seconds);
  fields.floating("total_local_wait_seconds",
                  outcome.total_local_wait_seconds);
  fields.floating("junction_wait_seconds",
                  outcome.junction_wait_seconds);
  fields.floating("merge_wait_seconds",
                  outcome.merge_wait_seconds);
  fields.floating("edge_travel_seconds",
                  outcome.edge_travel_seconds);
  fields.floating("node_service_seconds",
                  outcome.node_service_seconds);
  fields.floating("loop_extra_seconds",
                  outcome.loop_extra_seconds);
  fields.floating("completion_seconds",
                  outcome.completion_seconds);
  fields.integer("decision_count", outcome.decision_count);
  fields.integer("retry_count", outcome.retry_count);
  fields.integer("loop_count", outcome.loop_count);
  return fields.payload();
}

inline std::string causal_outcome_sha256(
    const ics::G4IRSF15CausalBagOutcome& outcome) {
  return ics::canonical_map2_detail::sha256_hex(
      causal_outcome_payload(outcome));
}

inline std::string cohort_outcome_sha256(
    const std::vector<ics::G4IRSF15CausalBagOutcome>& outcomes) {
  ics::g4irsf14_clone_detail::CanonicalFields fields;
  fields.string("schema",
                "czr005.g4irsf15.causal_cohort_outcomes.v1");
  fields.unsigned_integer(
      "cohort_size",
      static_cast<std::uint64_t>(outcomes.size()));
  for (const auto& outcome : outcomes) {
    fields.string("bag", causal_outcome_payload(outcome));
  }
  return ics::canonical_map2_detail::sha256_hex(fields.payload());
}

inline bool same_causal_outcome(
    const ics::G4IRSF15CausalBagOutcome& left,
    const ics::G4IRSF15CausalBagOutcome& right) {
  return left.runtime_bag_id == right.runtime_bag_id &&
         left.known == right.known &&
         left.completed == right.completed &&
         left.failed == right.failed &&
         left.status == right.status &&
         left.failure_reason == right.failure_reason &&
         left.finish_time == right.finish_time &&
         left.source_wait_seconds == right.source_wait_seconds &&
         left.total_local_wait_seconds ==
             right.total_local_wait_seconds &&
         left.junction_wait_seconds ==
             right.junction_wait_seconds &&
         left.merge_wait_seconds == right.merge_wait_seconds &&
         left.edge_travel_seconds == right.edge_travel_seconds &&
         left.node_service_seconds == right.node_service_seconds &&
         left.loop_extra_seconds == right.loop_extra_seconds &&
         left.completion_seconds == right.completion_seconds &&
         left.decision_count == right.decision_count &&
         left.retry_count == right.retry_count &&
         left.loop_count == right.loop_count;
}

inline py::dict replay_hash_row(
    const ics::G4IRSF14CloneReplayHashes& hashes) {
  hashes.validate();
  py::dict row;
  row["complete_bags_sha256"] = hashes.complete_bags_sha256;
  row["segment_result_sha256"] = hashes.segment_result_sha256;
  row["junction_state_sha256"] = hashes.junction_state_sha256;
  row["algorithm_summary_sha256"] =
      hashes.algorithm_summary_sha256;
  row["deterministic_result_sha256"] =
      hashes.deterministic_result_sha256;
  return row;
}

struct InvariantEvidence {
  int requested_count = 0;
  int completed_count = 0;
  int failed_count = 0;
  int event_count = 0;
  int unsafe_entry_count = 0;
  int reservation_conflict_count = 0;
  int runtime_full_astar_call_count = 0;
  int runtime_global_scan_count = 0;
  int runtime_future_route_read_count = 0;
  int runtime_future_schedule_read_count = 0;
  int teacher_input_count = 0;
  int max_selected_edges_per_bag = 0;
  int two_step_reservation_count = 0;
  int unresolved_deadlock_count = 0;
  bool event_limit_reached = false;
  bool time_limit_reached = false;
  bool merge_grant_conservation_holds = false;
  bool merge_grant_active_bijection_holds = false;
  bool merge_grant_runtime_owned_capability = false;
  bool merge_grant_exact_slot_no_future_shift = false;
  std::uint64_t merge_grant_stale_arbitration_count = 0;
  std::uint64_t stale_arbitration_event_count = 0;
  std::uint64_t merge_grant_outstanding_request_count = 0;
  int merge_grant_final_active_unconsumed = 0;
  double artificial_batch_delay_seconds = 0.0;
  bool live_safety_pass = false;
  bool formal_hard_gate_evaluated = false;
  bool formal_hard_gate_pass = false;
  std::vector<std::string> hard_gate_fail_reasons;
};

inline InvariantEvidence invariant_evidence(
    const ics::EventRuntimeSummary& summary,
    bool finalized_system_horizon,
    bool protected_full_1x_shape,
    bool allow_lazy_stale_merge_wakeups = false) {
  InvariantEvidence evidence;
  evidence.requested_count = summary.requested_count;
  evidence.completed_count = summary.completed_count;
  evidence.failed_count = summary.failed_count;
  evidence.event_count = summary.event_count;
  evidence.unsafe_entry_count =
      summary.physical_fault_edge_entry_violation_count;
  evidence.reservation_conflict_count =
      summary.reservation_conflicts;
  evidence.runtime_full_astar_call_count =
      summary.runtime_full_astar_calls;
  evidence.runtime_global_scan_count =
      summary.global_reservation_scan_count +
      summary.priority_global_scan_count +
      summary.scorer_runtime_global_scan_count +
      summary.microphase_runtime_global_scan_count +
      summary.first_edge_credit_global_scan_count;
  evidence.runtime_future_route_read_count =
      summary.priority_future_route_input_count +
      summary.scorer_future_route_input_count +
      summary.first_edge_credit_future_route_count;
  evidence.runtime_future_schedule_read_count =
      summary.scorer_future_schedule_input_count;
  evidence.teacher_input_count =
      summary.priority_teacher_input_count +
      summary.scorer_teacher_input_count;
  evidence.max_selected_edges_per_bag =
      summary.max_edges_selected_per_bag_per_decision;
  evidence.two_step_reservation_count =
      summary.two_step_reservation_count;
  evidence.unresolved_deadlock_count =
      summary.unresolved_deadlock_count;
  evidence.event_limit_reached = summary.event_limit_reached;
  evidence.time_limit_reached = summary.time_limit_reached;
  evidence.merge_grant_conservation_holds =
      summary.merge_grant_conservation_holds;
  evidence.merge_grant_active_bijection_holds =
      summary.merge_grant_active_bijection_holds;
  evidence.merge_grant_runtime_owned_capability =
      summary.merge_grant_runtime_owned_capability;
  evidence.merge_grant_exact_slot_no_future_shift =
      summary.merge_grant_exact_slot_no_future_shift;
  evidence.merge_grant_stale_arbitration_count =
      summary.merge_grant_stale_arbitration_count;
  evidence.stale_arbitration_event_count =
      summary.stale_arbitration_event_count;
  evidence.merge_grant_outstanding_request_count =
      summary.merge_grant_outstanding_request_count;
  evidence.merge_grant_final_active_unconsumed =
      summary.merge_grant_final_active_unconsumed;
  evidence.artificial_batch_delay_seconds =
      summary.artificial_batch_delay_seconds;
  const auto fail = [&](bool condition, const char* reason) {
    if (condition) {
      evidence.hard_gate_fail_reasons.emplace_back(reason);
    }
  };
  fail(evidence.unsafe_entry_count != 0,
       "UNSAFE_PHYSICAL_FAULT_EDGE_ENTRY");
  fail(evidence.reservation_conflict_count != 0,
       "RESERVATION_CONFLICT");
  fail(evidence.runtime_full_astar_call_count != 0,
       "RUNTIME_FULL_ASTAR_CALL");
  fail(evidence.runtime_global_scan_count != 0,
       "RUNTIME_GLOBAL_SCAN");
  fail(evidence.runtime_future_route_read_count != 0,
       "RUNTIME_FUTURE_ROUTE_READ");
  fail(evidence.runtime_future_schedule_read_count != 0,
       "RUNTIME_FUTURE_SCHEDULE_READ");
  fail(evidence.teacher_input_count != 0,
       "TEACHER_INPUT_USED");
  fail(evidence.max_selected_edges_per_bag > 1,
       "MORE_THAN_ONE_EDGE_SELECTED_PER_DECISION");
  fail(evidence.two_step_reservation_count != 0,
       "TWO_STEP_RESERVATION");
  fail(evidence.unresolved_deadlock_count != 0,
       "UNRESOLVED_DEADLOCK");
  fail(evidence.event_limit_reached,
       "EVENT_LIMIT_REACHED");
  fail(evidence.time_limit_reached,
       "TIME_LIMIT_REACHED");
  // J2 deliberately uses generation-invalidated lazy wakeups; its native
  // protocol tests require these superseded timers to be observable.  They
  // are not stale action execution (tracked separately below).
  fail(!allow_lazy_stale_merge_wakeups &&
           evidence.merge_grant_stale_arbitration_count != 0U,
       "MERGE_GRANT_STALE_ARBITRATION");
  fail(evidence.stale_arbitration_event_count != 0U,
       "STALE_ARBITRATION_EVENT");
  fail(evidence.artificial_batch_delay_seconds != 0.0,
       "ARTIFICIAL_BATCH_DELAY");
  fail(!evidence.merge_grant_conservation_holds,
       "MERGE_GRANT_CONSERVATION_FAILED");
  fail(!evidence.merge_grant_active_bijection_holds,
       "MERGE_GRANT_ACTIVE_BIJECTION_FAILED");
  fail(!evidence.merge_grant_runtime_owned_capability,
       "MERGE_GRANT_CAPABILITY_NOT_RUNTIME_OWNED");
  fail(!evidence.merge_grant_exact_slot_no_future_shift,
       "MERGE_GRANT_FUTURE_SHIFT");
  evidence.live_safety_pass =
      evidence.hard_gate_fail_reasons.empty();
  evidence.formal_hard_gate_evaluated =
      finalized_system_horizon;
  if (finalized_system_horizon) {
    fail(!protected_full_1x_shape,
         "PROTECTED_FULL_1X_SHAPE_MISMATCH");
    fail(evidence.completed_count != evidence.requested_count,
         "SYSTEM_COHORT_NOT_ALL_COMPLETED");
    fail(evidence.failed_count != 0,
         "SYSTEM_COHORT_FAILED_SEGMENT");
    fail(evidence.merge_grant_final_active_unconsumed != 0,
         "FINAL_ACTIVE_MERGE_GRANT_UNCONSUMED");
    fail(evidence.merge_grant_outstanding_request_count != 0U,
         "FINAL_OUTSTANDING_MERGE_REQUEST");
  }
  evidence.formal_hard_gate_pass =
      finalized_system_horizon &&
      evidence.hard_gate_fail_reasons.empty();
  return evidence;
}

inline py::dict invariant_row(const InvariantEvidence& evidence) {
  py::dict row;
  row["requested_count"] = evidence.requested_count;
  row["completed_count"] = evidence.completed_count;
  row["failed_segment_count"] = evidence.failed_count;
  row["event_count"] = evidence.event_count;
  row["unsafe_entry_count"] = evidence.unsafe_entry_count;
  row["reservation_conflict_count"] =
      evidence.reservation_conflict_count;
  row["runtime_full_astar_call_count"] =
      evidence.runtime_full_astar_call_count;
  row["runtime_global_scan_count"] =
      evidence.runtime_global_scan_count;
  row["runtime_future_route_read_count"] =
      evidence.runtime_future_route_read_count;
  row["runtime_future_schedule_read_count"] =
      evidence.runtime_future_schedule_read_count;
  row["teacher_input_count"] = evidence.teacher_input_count;
  row["max_selected_edges_per_bag"] =
      evidence.max_selected_edges_per_bag;
  row["two_step_reservation_count"] =
      evidence.two_step_reservation_count;
  row["unresolved_deadlock_count"] =
      evidence.unresolved_deadlock_count;
  row["event_limit_reached"] = evidence.event_limit_reached;
  row["time_limit_reached"] = evidence.time_limit_reached;
  row["merge_grant_conservation_holds"] =
      evidence.merge_grant_conservation_holds;
  row["merge_grant_active_bijection_holds"] =
      evidence.merge_grant_active_bijection_holds;
  row["merge_grant_runtime_owned_capability"] =
      evidence.merge_grant_runtime_owned_capability;
  row["merge_grant_exact_slot_no_future_shift"] =
      evidence.merge_grant_exact_slot_no_future_shift;
  row["merge_grant_stale_arbitration_count"] =
      py::int_(evidence.merge_grant_stale_arbitration_count);
  row["stale_arbitration_event_count"] =
      py::int_(evidence.stale_arbitration_event_count);
  row["merge_grant_outstanding_request_count"] =
      py::int_(evidence.merge_grant_outstanding_request_count);
  row["merge_grant_final_active_unconsumed"] =
      evidence.merge_grant_final_active_unconsumed;
  row["artificial_batch_delay_seconds"] =
      evidence.artificial_batch_delay_seconds;
  row["live_safety_pass"] = evidence.live_safety_pass;
  row["formal_hard_gate_evaluated"] =
      evidence.formal_hard_gate_evaluated;
  row["formal_hard_gate_pass"] =
      evidence.formal_hard_gate_pass;
  row["hard_gate_fail_reasons"] =
      evidence.hard_gate_fail_reasons;
  return row;
}

struct Target {
  bool deferred_address = false;
  bool g4irsf20_route_target = false;
  bool g4irsf21_route_action_target = false;
  std::string route_action_kind;
  int requested_route_next_node = -1;
  std::string descriptor_id;
  std::string skeleton_id;
  std::string population_group_sha256;
  std::string population_selection_sha256;
  int kind_index = -1;
  std::string clone_group_id;
  std::uint64_t event_ordinal = 0;
  std::uint64_t event_seq = 0;
  std::uint64_t event_time_bits = 0;
  int node = -1;
  std::string runtime_state_sha256;
  std::string boundary_sha256;
  int runtime_bag_id = -1;
  int peer_runtime_bag_id = -1;
  int baseline_next_node = -1;
  int selected_next_node = -1;
  bool baseline_release = false;
  bool selected_boolean = false;
  std::vector<int> source_ready_order;
  std::vector<int> legal_next_edges;
  std::string baseline_action;
  std::string intervention_action;
  std::string expected_action_change_type;
  std::string input_runtime_cohort_sha256;
  Horizon horizon = Horizon::kAffectedBag;
  std::string expected_intervention_sha256;
  std::string expected_target_address_sha256;
};

inline Target parse_target(const py::dict& row) {
  const auto schema_item = optional_item(row, "schema");
  const auto schema = schema_item
                          ? strict_string(schema_item, "schema")
                          : std::string(kDescriptorSchema);
  if (schema != kDescriptorSchema &&
      schema != kTargetAddressSchema &&
      schema != kG4IRSF20RouteTargetSchema &&
      schema != kG4IRSF21RouteActionTargetSchema) {
    throw py::value_error("unsupported G4IRSF15 descriptor schema");
  }
  Target target;
  target.g4irsf20_route_target =
      schema == kG4IRSF20RouteTargetSchema;
  target.g4irsf21_route_action_target =
      schema == kG4IRSF21RouteActionTargetSchema;
  target.deferred_address =
      schema == kTargetAddressSchema ||
      target.g4irsf20_route_target ||
      target.g4irsf21_route_action_target;
  if (target.g4irsf20_route_target ||
      target.g4irsf21_route_action_target) {
    target.population_group_sha256 = strict_string(
        required_item(row, "population_group_id"),
        "population_group_id");
    target.population_selection_sha256 = strict_string(
        required_item(row, "population_selection_id"),
        "population_selection_id");
    if (target.population_group_sha256.empty() ||
        target.population_selection_sha256.empty()) {
      throw py::value_error(
          "G20 Route population IDs must be non-empty");
    }
    target.skeleton_id =
        target.population_selection_sha256;
    target.kind_index = 1;
    target.event_ordinal = strict_uint64(
        required_item(row, "event_ordinal"),
        "event_ordinal");
    const auto horizon = strict_string(
        required_item(row, "horizon"), "horizon");
    if (horizon == "H_bag") {
      target.horizon = Horizon::kAffectedBag;
    } else if (horizon == "H_system") {
      target.horizon = Horizon::kSelectedSystem;
    } else {
      throw py::value_error("horizon must be H_bag or H_system");
    }
    if (target.g4irsf20_route_target) {
      target.descriptor_id =
          target.population_selection_sha256;
      return target;
    }

    target.route_action_kind = strict_string(
        required_item(row, "action_kind"), "action_kind");
    if (target.route_action_kind == "NEXT_EDGE") {
      target.requested_route_next_node = strict_int(
          required_item(row, "selected_next_node"),
          "selected_next_node");
      target.selected_next_node =
          target.requested_route_next_node;
    } else if (target.route_action_kind == "WAIT") {
      if (optional_item(row, "selected_next_node")) {
        throw py::value_error(
            "WAIT Route action must not carry selected_next_node");
      }
    } else {
      throw py::value_error(
          "action_kind must be NEXT_EDGE or WAIT");
    }
    const char* horizon_token =
        target.horizon == Horizon::kSelectedSystem
            ? "H_system"
            : "H_bag";
    target.descriptor_id =
        "G21_ROUTE_ACTION|GROUP=" +
        target.population_group_sha256 +
        "|SELECTION=" + target.population_selection_sha256 +
        "|EVENT=" + std::to_string(target.event_ordinal) +
        "|ACTION=" + target.route_action_kind +
        (target.route_action_kind == "NEXT_EDGE"
             ? "|NEXT_NODE=" +
                   std::to_string(target.requested_route_next_node)
             : std::string()) +
        "|HORIZON=" + horizon_token;
    return target;
  }
  target.descriptor_id =
      strict_sha256(required_item(row, "descriptor_id"),
                    "descriptor_id");
  target.skeleton_id =
      strict_sha256(required_item(row, "skeleton_id"),
                    "skeleton_id");
  target.population_group_sha256 =
      strict_sha256(
          required_item(row, "population_group_sha256"),
          "population_group_sha256");
  target.population_selection_sha256 =
      strict_sha256(
          required_item(row, "population_selection_sha256"),
          "population_selection_sha256");
  if (target.skeleton_id !=
      target.population_selection_sha256) {
    throw py::value_error(
        "skeleton_id and population_selection_sha256 disagree");
  }
  const auto kind =
      strict_string(required_item(row, "kind"), "kind");
  if (kind == "I1") {
    target.kind_index = 0;
  } else if (kind == "I3") {
    target.kind_index = 1;
  } else if (kind == "I4") {
    target.kind_index = 2;
  } else {
    throw py::value_error("kind must be I1, I3, or I4");
  }
  target.clone_group_id =
      strict_sha256(required_item(row, "clone_group_id"),
                    "clone_group_id");
  target.event_ordinal =
      strict_uint64(required_item(row, "event_ordinal"),
                    "event_ordinal");
  target.event_seq =
      strict_uint64(required_item(row, "event_seq"), "event_seq");
  target.event_time_bits =
      strict_uint64(required_item(row, "event_time_bits"),
                    "event_time_bits");
  target.node = strict_int(required_item(row, "node"), "node");
  target.runtime_bag_id =
      strict_int(required_item(row, "runtime_bag_id"),
                 "runtime_bag_id");
  target.peer_runtime_bag_id =
      strict_int(required_item(row, "peer_runtime_bag_id"),
                 "peer_runtime_bag_id");
  target.baseline_next_node =
      strict_int(required_item(row, "baseline_next_node"),
                 "baseline_next_node");
  target.selected_next_node =
      strict_int(required_item(row, "selected_next_node"),
                 "selected_next_node");
  target.baseline_release =
      strict_bool(required_item(row, "baseline_release"),
                  "baseline_release");
  target.selected_boolean =
      strict_bool(required_item(row, "selected_boolean"),
                  "selected_boolean");
  const auto horizon =
      strict_string(required_item(row, "horizon"), "horizon");
  if (horizon == "H_bag") {
    target.horizon = Horizon::kAffectedBag;
  } else if (horizon == "H_system") {
    target.horizon = Horizon::kSelectedSystem;
  } else {
    throw py::value_error("horizon must be H_bag or H_system");
  }
  if (target.deferred_address) {
    const auto target_address_id = strict_sha256(
        required_item(row, "target_address_id"),
        "target_address_id");
    const auto skeleton_selection_sha256 = strict_sha256(
        required_item(row, "skeleton_selection_sha256"),
        "skeleton_selection_sha256");
    const auto sample_sha256 = strict_sha256(
        required_item(row, "sample_sha256"),
        "sample_sha256");
    const auto prepop_event_group = strict_sha256(
        required_item(row, "prepop_event_group_sha256"),
        "prepop_event_group_sha256");
    if (target.descriptor_id != target.skeleton_id ||
        target_address_id != target.skeleton_id ||
        skeleton_selection_sha256 != target.skeleton_id ||
        sample_sha256 != target.skeleton_id ||
        target.clone_group_id != prepop_event_group) {
      throw py::value_error(
          "deferred target address identity aliases disagree");
    }
    if (strict_string(required_item(row, "target_address_id_semantics"),
                      "target_address_id_semantics") !=
        "ALIAS_OF_NATIVE_SKELETON_SELECTION_SHA256") {
      throw py::value_error(
          "deferred target address identity semantics are invalid");
    }
    target.input_runtime_cohort_sha256 = strict_sha256(
        required_item(row, "input_runtime_cohort_sha256"),
        "input_runtime_cohort_sha256");
    if (prepop_event_group != prepop_event_group_sha256(
            target.input_runtime_cohort_sha256,
            target.event_ordinal, target.event_seq,
            target.event_time_bits, target.node)) {
      throw py::value_error(
          "deferred target address pre-pop event group drifted");
    }
    const auto runtime_state = required_item(
        row, "runtime_state_sha256");
    const auto boundary = required_item(row, "boundary_sha256");
    if (!runtime_state.is_none() || !boundary.is_none()) {
      throw py::value_error(
          "deferred target address must not carry a full state seal");
    }
    for (const char* eager_field : {
             "intervention_sha256",
             "intervention_sha256_by_horizon",
             "state_components",
             "kind_name",
             "boundary_kind",
             "queue_top_not_popped",
             "staged_event_sink_empty",
             "runtime_global_scan_count",
             "runtime_future_route_read_count",
             "runtime_future_schedule_read_count",
             "reservation_depth",
             "max_selected_edges_per_bag"}) {
      const auto eager_item = optional_item(row, eager_field);
      if (eager_item && !eager_item.is_none()) {
        throw py::value_error(
            std::string("deferred target address must not carry eager ") +
            eager_field);
      }
    }
    if (strict_string(required_item(row, "seal_level"),
                      "seal_level") != "LOCAL_PREPOP_ADDRESS" ||
        strict_string(required_item(row, "full_state_seal"),
                      "full_state_seal") !=
            "DEFERRED_TO_EXECUTED_PAIR" ||
        !strict_bool(required_item(row, "outcome_free"),
                     "outcome_free")) {
      throw py::value_error(
          "deferred target address policy fields are invalid");
    }
    target.source_ready_order = strict_int_vector(
        required_item(row, "source_ready_order"),
        "source_ready_order");
    target.legal_next_edges = strict_int_vector(
        required_item(row, "legal_next_edges"),
        "legal_next_edges");
    target.baseline_action = strict_string(
        required_item(row, "baseline_action"),
        "baseline_action");
    target.intervention_action = strict_string(
        required_item(row, "intervention_action"),
        "intervention_action");
    target.expected_action_change_type = strict_string(
        required_item(row, "expected_action_change_type"),
        "expected_action_change_type");
    const auto hashes_item = required_item(
        row, "target_address_sha256_by_horizon");
    if (!PyDict_Check(hashes_item.ptr())) {
      throw py::type_error(
          "target_address_sha256_by_horizon must be a dict");
    }
    const auto hashes =
        py::reinterpret_borrow<py::dict>(hashes_item);
    if (py::len(hashes) != 2) {
      throw py::value_error(
          "target address must carry exactly H_bag and H_system hashes");
    }
    const auto h_bag_sha256 = strict_sha256(
        required_item(hashes, "H_bag"), "target_address.H_bag");
    const auto h_system_sha256 = strict_sha256(
        required_item(hashes, "H_system"), "target_address.H_system");
    if (h_bag_sha256 != target_address_horizon_sha256(
                            target_address_id, "H_bag") ||
        h_system_sha256 != target_address_horizon_sha256(
                               target_address_id, "H_system")) {
      throw py::value_error(
          "deferred target address horizon hashes drifted");
    }
    target.expected_target_address_sha256 = strict_sha256(
        required_item(row, "target_address_sha256"),
        "target_address_sha256");
    const auto& expected_horizon_sha256 =
        target.horizon == Horizon::kAffectedBag
            ? h_bag_sha256
            : h_system_sha256;
    if (target.expected_target_address_sha256 !=
        expected_horizon_sha256) {
      throw py::value_error(
          "deferred target address requested horizon hash drifted");
    }
  } else {
    target.runtime_state_sha256 =
        strict_sha256(required_item(row, "runtime_state_sha256"),
                      "runtime_state_sha256");
    target.boundary_sha256 =
        strict_sha256(required_item(row, "boundary_sha256"),
                      "boundary_sha256");
    target.expected_intervention_sha256 =
        strict_sha256(required_item(row, "intervention_sha256"),
                      "intervention_sha256");
  }
  return target;
}

inline void verify_target_boundary(const Target& target,
                                   const Boundary& boundary) {
  boundary.validate();
  if (kind_index(boundary.kind) != target.kind_index ||
      boundary.event_seq != target.event_seq ||
      ics::event_runtime_detail::timestamp_bits(boundary.time) !=
          target.event_time_bits ||
      boundary.node != target.node ||
      boundary.runtime_bag_id != target.runtime_bag_id ||
      boundary.baseline_next_node != target.baseline_next_node ||
      boundary.baseline_release != target.baseline_release) {
    throw py::value_error(
        "target descriptor does not exactly match the native boundary");
  }
  if (target.deferred_address) {
    if (boundary.source_ready_order != target.source_ready_order ||
        boundary.legal_next_edges != target.legal_next_edges) {
      throw py::value_error(
          "deferred target address local boundary projection drifted");
    }
  } else if (
      boundary.clone_group_id != target.clone_group_id ||
      boundary.runtime_state_sha256 != target.runtime_state_sha256 ||
      boundary.boundary_sha256() != target.boundary_sha256) {
    throw py::value_error(
        "sealed target descriptor full boundary identity drifted");
  }
}

inline PopulationCandidate verify_target_population(
    const Target& target,
    const Boundary& boundary,
    const Strata& strata,
    bool pibt_prefilter_candidate_event) {
  const auto primary = primary_population_candidate(
      skeleton_from_boundary(boundary), strata,
      target.event_ordinal, pibt_prefilter_candidate_event);
  if (!primary.has_value() ||
      primary->population_group_sha256 !=
          target.population_group_sha256 ||
      primary->population_selection_sha256 !=
          target.population_selection_sha256 ||
      primary->population_selection_sha256 !=
          target.skeleton_id ||
      primary->peer_runtime_bag_id !=
          target.peer_runtime_bag_id ||
      primary->selected_next_node !=
          target.selected_next_node ||
      primary->selected_boolean !=
          target.selected_boolean) {
    throw py::value_error(
        "target descriptor is not the replayed native primary "
        "skeleton action");
  }
  if (target.deferred_address &&
      (primary->baseline_action != target.baseline_action ||
       primary->intervention_action != target.intervention_action ||
       primary->expected_action_change_type !=
           target.expected_action_change_type)) {
    throw py::value_error(
        "deferred target address local action projection drifted");
  }
  return *primary;
}

inline Intervention intervention_for(const Target& target,
                                     const Boundary& boundary) {
  Intervention intervention;
  intervention.kind =
      intervention_kind_for(target.kind_index);
  intervention.horizon = target.horizon;
  intervention.runtime_bag_id = target.runtime_bag_id;
  if (target.kind_index == 0) {
    intervention.peer_runtime_bag_id =
        target.peer_runtime_bag_id;
  } else if (target.kind_index == 1) {
    intervention.selected_next_node =
        target.selected_next_node;
  } else {
    intervention.selected_boolean = target.selected_boolean;
  }
  intervention.validate_against(boundary);
  if (target.deferred_address) {
    return intervention;
  }
  auto identity_intervention = intervention;
  identity_intervention.horizon = Horizon::kAffectedBag;
  if (target.descriptor_id !=
      identity_intervention.intervention_sha256(boundary)) {
    throw py::value_error(
        "descriptor_id does not bind the identical native H_bag action");
  }
  const auto sha = intervention.intervention_sha256(boundary);
  if (target.expected_intervention_sha256 != sha) {
    throw py::value_error(
        "intervention_sha256 does not bind the requested horizon/action");
  }
  return intervention;
}

inline std::vector<int> intended_affected_ids(
    const Target& target) {
  std::vector<int> ids{target.runtime_bag_id};
  if (target.kind_index == 0) {
    ids.push_back(target.peer_runtime_bag_id);
  }
  std::sort(ids.begin(), ids.end());
  ids.erase(std::unique(ids.begin(), ids.end()), ids.end());
  return ids;
}

inline std::vector<ics::G4IRSF15LocalActionSnapshot>
local_snapshots(const Runtime& runtime,
                const std::vector<int>& runtime_bag_ids) {
  std::vector<ics::G4IRSF15LocalActionSnapshot> rows;
  rows.reserve(runtime_bag_ids.size());
  for (const int id : runtime_bag_ids) {
    rows.push_back(runtime.g4irsf15_local_action_snapshot(id));
  }
  return rows;
}

inline const ics::G4IRSF15LocalActionSnapshot& snapshot_for(
    const std::vector<ics::G4IRSF15LocalActionSnapshot>& rows,
    int runtime_bag_id) {
  const auto found = std::find_if(
      rows.begin(), rows.end(), [&](const auto& row) {
        return row.runtime_bag_id == runtime_bag_id;
      });
  if (found == rows.end()) {
    throw std::logic_error("missing local action snapshot");
  }
  return *found;
}

inline bool same_local_action_snapshot(
    const ics::G4IRSF15LocalActionSnapshot& left,
    const ics::G4IRSF15LocalActionSnapshot& right) {
  return left.runtime_bag_id == right.runtime_bag_id &&
         left.known == right.known &&
         left.status == right.status &&
         left.current_node == right.current_node &&
         left.transit_from == right.transit_from &&
         left.transit_to == right.transit_to &&
         left.admitted_time == right.admitted_time &&
         left.decision_count == right.decision_count &&
         left.retry_count == right.retry_count &&
         left.pending_merge_request_id ==
             right.pending_merge_request_id &&
         left.pending_merge_lineage ==
             right.pending_merge_lineage &&
         left.pending_merge_upstream ==
             right.pending_merge_upstream &&
         left.pending_merge_destination ==
             right.pending_merge_destination &&
         left.queued_at_current_node ==
             right.queued_at_current_node &&
         left.source_queued_at_current_node ==
             right.source_queued_at_current_node &&
         left.junction_wakeup_pending ==
             right.junction_wakeup_pending &&
         left.junction_wakeup_generation ==
             right.junction_wakeup_generation &&
         left.junction_wakeup_time ==
             right.junction_wakeup_time;
}

inline bool same_local_action_snapshots(
    const std::vector<ics::G4IRSF15LocalActionSnapshot>& left,
    const std::vector<ics::G4IRSF15LocalActionSnapshot>& right) {
  return left.size() == right.size() &&
         std::equal(left.begin(), left.end(), right.begin(),
                    same_local_action_snapshot);
}

inline std::pair<std::string, int> committed_route_action(
    const ics::G4IRSF15LocalActionSnapshot& snapshot) {
  if (snapshot.pending_merge_request_id != 0U &&
      snapshot.pending_merge_destination >= 0) {
    return {"MERGE_REQUEST_ENQUEUED",
            snapshot.pending_merge_destination};
  }
  if (snapshot.transit_to >= 0) {
    return {"EDGE_COMMIT", snapshot.transit_to};
  }
  return {"NO_ROUTE_COMMIT", -1};
}

inline py::dict action_certificate(
    const Target& target,
    const Boundary& boundary,
    const ics::G4IRSF14CausalStepResult& treatment_step,
    const std::vector<ics::G4IRSF15LocalActionSnapshot>&
        baseline_pre_snapshots,
    const std::vector<ics::G4IRSF15LocalActionSnapshot>&
        baseline_snapshots,
    const std::vector<ics::G4IRSF15LocalActionSnapshot>&
        treatment_pre_snapshots,
    const std::vector<ics::G4IRSF15LocalActionSnapshot>&
        treatment_snapshots) {
  bool valid = false;
  std::string baseline_action;
  std::string treatment_action;
  std::string commit_type;
  if (target.kind_index == 0) {
    const auto& pre_winner =
        snapshot_for(baseline_pre_snapshots,
                     target.runtime_bag_id);
    const auto& pre_peer =
        snapshot_for(baseline_pre_snapshots,
                     target.peer_runtime_bag_id);
    const auto& baseline_winner =
        snapshot_for(baseline_snapshots, target.runtime_bag_id);
    const auto& baseline_peer =
        snapshot_for(baseline_snapshots,
                     target.peer_runtime_bag_id);
    const auto& treatment_winner =
        snapshot_for(treatment_snapshots, target.runtime_bag_id);
    const auto& treatment_peer =
        snapshot_for(treatment_snapshots,
                     target.peer_runtime_bag_id);
    baseline_action = i1_action(target.runtime_bag_id);
    treatment_action = i1_action(target.peer_runtime_bag_id);
    commit_type = "SOURCE_ADMIT";
    valid =
        treatment_step.application_reason ==
            "APPLIED_I1_SOURCE_ADMIT_COMMITTED_ONE_ACTION" &&
        pre_winner.admitted_time < 0.0 &&
        pre_peer.admitted_time < 0.0 &&
        pre_winner.source_queued_at_current_node &&
        pre_peer.source_queued_at_current_node &&
        pre_winner.current_node == pre_peer.current_node &&
        baseline_winner.admitted_time >= 0.0 &&
        baseline_peer.admitted_time < 0.0 &&
        treatment_winner.admitted_time < 0.0 &&
        treatment_peer.admitted_time >= 0.0;
  } else if (target.kind_index == 1) {
    const auto& pre =
        snapshot_for(baseline_pre_snapshots,
                     target.runtime_bag_id);
    const auto baseline =
        committed_route_action(snapshot_for(
            baseline_snapshots, target.runtime_bag_id));
    const auto treatment =
        committed_route_action(snapshot_for(
            treatment_snapshots, target.runtime_bag_id));
    baseline_action =
        baseline.first + ":NEXT_NODE=" +
        std::to_string(baseline.second);
    treatment_action =
        treatment.first + ":NEXT_NODE=" +
        std::to_string(treatment.second);
    commit_type = treatment.first;
    const bool reason_matches =
        (treatment.first == "EDGE_COMMIT" &&
         treatment_step.application_reason ==
             "APPLIED_I3_ONE_EDGE_COMMIT_ONE_ACTION") ||
        (treatment.first == "MERGE_REQUEST_ENQUEUED" &&
         treatment_step.application_reason ==
             "APPLIED_I3_MERGE_REQUEST_ENQUEUED_ONE_ACTION");
    valid = reason_matches &&
            pre.queued_at_current_node &&
            pre.status == "JUNCTION_QUEUE" &&
            pre.pending_merge_request_id == 0U &&
            baseline.second == boundary.baseline_next_node &&
            treatment.second == target.selected_next_node &&
            baseline.second != treatment.second;
  } else {
    const auto& pre =
        snapshot_for(baseline_pre_snapshots,
                     target.runtime_bag_id);
    const auto& baseline =
        snapshot_for(baseline_snapshots, target.runtime_bag_id);
    const auto& treatment =
        snapshot_for(treatment_snapshots, target.runtime_bag_id);
    const auto baseline_commit =
        committed_route_action(baseline);
    baseline_action =
        baseline_commit.first + ":NEXT_NODE=" +
        std::to_string(baseline_commit.second);
    treatment_action = "SAFE_HOLD";
    commit_type = "SAFE_HOLD";
    valid =
        treatment_step.application_reason ==
            "APPLIED_I4_SAFE_HOLD_UNTIL_NEXT_JUNCTION_SERVICE_OPPORTUNITY" &&
        pre.queued_at_current_node &&
        pre.status == "JUNCTION_QUEUE" &&
        pre.pending_merge_request_id == 0U &&
        pre.junction_wakeup_pending &&
        ics::event_runtime_detail::same_timestamp(
            pre.junction_wakeup_time, boundary.time) &&
        baseline_commit.first != "NO_ROUTE_COMMIT" &&
        treatment.queued_at_current_node &&
        treatment.junction_wakeup_pending &&
        treatment.junction_wakeup_generation >
            pre.junction_wakeup_generation &&
        treatment.junction_wakeup_time > boundary.time &&
        treatment.status == "JUNCTION_QUEUE" &&
        treatment.pending_merge_request_id == 0U;
  }
  const bool pre_action_snapshots_match =
      same_local_action_snapshots(
          baseline_pre_snapshots, treatment_pre_snapshots);
  valid = valid && pre_action_snapshots_match &&
          treatment_step.intervention_applied &&
          treatment_step.changed_action_count == 1 &&
          baseline_action != treatment_action;
  py::dict row;
  row["valid"] = valid;
  row["post_commit_verified"] = valid;
  row["pre_action_snapshots_match"] =
      pre_action_snapshots_match;
  row["changed_action_count"] =
      treatment_step.changed_action_count;
  row["baseline_action"] = baseline_action;
  row["treatment_action"] = treatment_action;
  row["committed_action_type"] = commit_type;
  row["application_reason"] =
      treatment_step.application_reason;
  py::list baseline_pre_rows;
  for (const auto& snapshot : baseline_pre_snapshots) {
    baseline_pre_rows.append(local_snapshot_row(snapshot));
  }
  py::list baseline_rows;
  for (const auto& snapshot : baseline_snapshots) {
    baseline_rows.append(local_snapshot_row(snapshot));
  }
  py::list treatment_pre_rows;
  for (const auto& snapshot : treatment_pre_snapshots) {
    treatment_pre_rows.append(local_snapshot_row(snapshot));
  }
  py::list treatment_rows;
  for (const auto& snapshot : treatment_snapshots) {
    treatment_rows.append(local_snapshot_row(snapshot));
  }
  row["baseline_pre_action_snapshots"] =
      std::move(baseline_pre_rows);
  row["baseline_post_action_snapshots"] =
      std::move(baseline_rows);
  row["treatment_pre_action_snapshots"] =
      std::move(treatment_pre_rows);
  row["treatment_post_action_snapshots"] =
      std::move(treatment_rows);
  return row;
}

struct BranchEvidence {
  bool finalized = false;
  bool horizon_complete = false;
  bool blocked = false;
  std::string stop_reason;
  std::uint64_t elapsed_event_count = 0;
  std::string terminal_state_sha256;
  std::string terminal_digest_kind;
  std::vector<ics::G4IRSF15CausalBagOutcome>
      affected_outcomes;
  std::vector<ics::G4IRSF15CausalBagOutcome>
      cohort_outcomes;
  InvariantEvidence invariants;
  std::optional<ics::G4IRSF14CloneReplayHashes> replay_hashes;
};

inline BranchEvidence drive_branch(
    Runtime& runtime,
    Horizon horizon,
    const std::vector<int>& affected_ids,
    const std::vector<int>& all_runtime_ids,
    int boundary_node,
    std::uint64_t start_event_count,
    bool protected_full_1x_shape,
    bool allow_lazy_stale_merge_wakeups) {
  BranchEvidence evidence;
  const auto& cohort =
      horizon == Horizon::kSelectedSystem
          ? all_runtime_ids
          : affected_ids;
  ics::G4IRSF14CausalHorizonStopState stop;
  if (horizon == Horizon::kSelectedSystem) {
    runtime.drain();
    runtime.finalize();
    evidence.finalized = true;
    stop = runtime.causal_horizon_stop_state(
        horizon, cohort, boundary_node, start_event_count, 1U);
    evidence.replay_hashes =
        runtime.deterministic_replay_hashes();
  } else {
    while (true) {
      stop = runtime.causal_horizon_stop_state(
          horizon, cohort, boundary_node, start_event_count, 1U);
      if (stop.should_stop) {
        break;
      }
      if (!runtime.process_one_event()) {
        stop = runtime.causal_horizon_stop_state(
            horizon, cohort, boundary_node,
            start_event_count, 1U);
        if (!stop.should_stop) {
          throw std::logic_error(
              "runtime stopped without a terminal causal horizon state");
        }
        break;
      }
    }
  }
  evidence.horizon_complete = stop.horizon_complete;
  evidence.blocked = stop.blocked;
  evidence.stop_reason = stop.stop_reason;
  evidence.elapsed_event_count = stop.elapsed_event_count;
  if (evidence.finalized) {
    evidence.terminal_state_sha256 =
        evidence.replay_hashes->deterministic_result_sha256;
    evidence.terminal_digest_kind =
        "FINALIZED_DETERMINISTIC_RESULT_SHA256";
  } else if (runtime.peek_safe_boundary().has_value()) {
    evidence.terminal_state_sha256 =
        runtime.deterministic_state_sha256();
    evidence.terminal_digest_kind =
        "LIVE_PREPOP_RUNTIME_STATE_SHA256";
  } else {
    if (runtime.phase() ==
        ics::EventDrivenJunctionRuntimePhase::kReady) {
      if (runtime.process_one_event()) {
        throw std::logic_error(
            "missing terminal safe boundary unexpectedly processed an event");
      }
    }
    runtime.finalize();
    evidence.finalized = true;
    evidence.replay_hashes =
        runtime.deterministic_replay_hashes();
    evidence.terminal_state_sha256 =
        evidence.replay_hashes->deterministic_result_sha256;
    evidence.terminal_digest_kind =
        "FINALIZED_DETERMINISTIC_RESULT_SHA256";
  }
  evidence.affected_outcomes.reserve(affected_ids.size());
  for (const int id : affected_ids) {
    evidence.affected_outcomes.push_back(
        runtime.g4irsf15_causal_bag_outcome(id));
  }
  evidence.cohort_outcomes.reserve(cohort.size());
  for (const int id : cohort) {
    evidence.cohort_outcomes.push_back(
        runtime.g4irsf15_causal_bag_outcome(id));
  }
  evidence.invariants = invariant_evidence(
      runtime.current_result().summary,
      horizon == Horizon::kSelectedSystem,
      protected_full_1x_shape,
      allow_lazy_stale_merge_wakeups);
  return evidence;
}

inline py::dict realized_outcome_delta_row(
    const ics::G4IRSF15CausalBagOutcome& baseline,
    const ics::G4IRSF15CausalBagOutcome& treatment) {
  if (baseline.runtime_bag_id != treatment.runtime_bag_id) {
    throw std::logic_error(
        "cannot build a delta for different runtime bags");
  }
  ics::g4irsf14_clone_detail::CanonicalFields digest;
  digest.string(
      "schema",
      "czr005.g4irsf15.realized_outcome_delta.v1");
  digest.string("baseline", causal_outcome_payload(baseline));
  digest.string("treatment", causal_outcome_payload(treatment));
  const auto delta_sha256 =
      ics::canonical_map2_detail::sha256_hex(digest.payload());
  py::dict row;
  row["runtime_bag_id"] = baseline.runtime_bag_id;
  row["task_id"] = baseline.task_id;
  row["segment_id"] = baseline.segment_id;
  row["baseline"] = outcome_row(baseline);
  row["treatment"] = outcome_row(treatment);
  row["completed_delta"] =
      static_cast<int>(treatment.completed) -
      static_cast<int>(baseline.completed);
  row["failed_delta"] =
      static_cast<int>(treatment.failed) -
      static_cast<int>(baseline.failed);
  row["status_changed"] =
      baseline.status != treatment.status;
  row["failure_reason_changed"] =
      baseline.failure_reason != treatment.failure_reason;
  row["finish_time_delta_seconds"] =
      treatment.finish_time - baseline.finish_time;
  row["completion_delta_seconds"] =
      treatment.completion_seconds -
      baseline.completion_seconds;
  row["source_wait_delta_seconds"] =
      treatment.source_wait_seconds -
      baseline.source_wait_seconds;
  row["total_local_wait_delta_seconds"] =
      treatment.total_local_wait_seconds -
      baseline.total_local_wait_seconds;
  row["junction_wait_delta_seconds"] =
      treatment.junction_wait_seconds -
      baseline.junction_wait_seconds;
  row["merge_wait_delta_seconds"] =
      treatment.merge_wait_seconds -
      baseline.merge_wait_seconds;
  row["edge_travel_delta_seconds"] =
      treatment.edge_travel_seconds -
      baseline.edge_travel_seconds;
  row["node_service_delta_seconds"] =
      treatment.node_service_seconds -
      baseline.node_service_seconds;
  row["loop_extra_delta_seconds"] =
      treatment.loop_extra_seconds -
      baseline.loop_extra_seconds;
  row["decision_count_delta"] =
      treatment.decision_count - baseline.decision_count;
  row["retry_count_delta"] =
      treatment.retry_count - baseline.retry_count;
  row["loop_count_delta"] =
      treatment.loop_count - baseline.loop_count;
  row["outcome_delta_sha256"] = delta_sha256;
  return row;
}

inline py::dict realized_externality_row(
    const BranchEvidence& baseline,
    const BranchEvidence& treatment,
    const std::vector<int>& direct_ids,
    Horizon horizon) {
  if (baseline.cohort_outcomes.size() !=
      treatment.cohort_outcomes.size()) {
    throw std::logic_error(
        "matched branches produced different cohort cardinalities");
  }
  std::set<int> direct(direct_ids.begin(), direct_ids.end());
  std::vector<int> realized;
  std::vector<int> realized_direct;
  std::vector<int> realized_external;
  std::vector<std::string> delta_sha256s;
  py::list delta_rows;
  for (std::size_t index = 0;
       index < baseline.cohort_outcomes.size(); ++index) {
    const auto& left = baseline.cohort_outcomes[index];
    const auto& right = treatment.cohort_outcomes[index];
    if (left.runtime_bag_id != right.runtime_bag_id) {
      throw std::logic_error(
          "matched cohort outcome ordering is not identical");
    }
    if (same_causal_outcome(left, right)) {
      continue;
    }
    realized.push_back(left.runtime_bag_id);
    if (direct.count(left.runtime_bag_id) != 0U) {
      realized_direct.push_back(left.runtime_bag_id);
    } else {
      realized_external.push_back(left.runtime_bag_id);
    }
    if (horizon == Horizon::kSelectedSystem) {
      auto delta = realized_outcome_delta_row(left, right);
      delta_sha256s.push_back(
          py::cast<std::string>(
              delta["outcome_delta_sha256"]));
      delta_rows.append(std::move(delta));
    }
  }
  if (horizon != Horizon::kSelectedSystem) {
    // H_bag deliberately stops once the directly affected local horizon
    // completes.  It cannot claim to have observed whole-system spillovers.
    realized_external.clear();
  }
  ics::g4irsf14_clone_detail::CanonicalFields sidecar;
  sidecar.string(
      "schema",
      "czr005.g4irsf15.realized_outcome_deltas.v1");
  sidecar.unsigned_integer(
      "row_count",
      static_cast<std::uint64_t>(delta_sha256s.size()));
  for (const auto& row_sha256 : delta_sha256s) {
    sidecar.string("row_sha256", row_sha256);
  }
  const auto sidecar_sha256 =
      ics::canonical_map2_detail::sha256_hex(
          sidecar.payload());
  ics::g4irsf14_clone_detail::CanonicalFields digest;
  digest.string("schema",
                "czr005.g4irsf15.realized_externality.v1");
  digest.integers("direct_runtime_bag_ids", direct_ids);
  digest.integers("realized_runtime_bag_ids", realized);
  digest.integers("realized_direct_runtime_bag_ids",
                  realized_direct);
  digest.integers("realized_external_runtime_bag_ids",
                  realized_external);
  digest.string("realized_outcome_deltas_sha256",
                sidecar_sha256);
  digest.string(
      "externality_observation_status",
      horizon == Horizon::kSelectedSystem
          ? "OBSERVED_AT_H_SYSTEM"
          : "NOT_OBSERVED_AT_H_BAG");
  py::dict row;
  row["direct_affected_runtime_bag_ids"] = direct_ids;
  row["direct_affected_count"] =
      static_cast<int>(direct_ids.size());
  row["realized_affected_runtime_bag_ids"] = realized;
  row["realized_affected_count"] =
      static_cast<int>(realized.size());
  row["realized_direct_runtime_bag_ids"] = realized_direct;
  row["realized_direct_count"] =
      static_cast<int>(realized_direct.size());
  row["realized_external_runtime_bag_ids"] =
      realized_external;
  row["realized_external_count"] =
      static_cast<int>(realized_external.size());
  row["externality_observation_status"] =
      horizon == Horizon::kSelectedSystem
          ? "OBSERVED_AT_H_SYSTEM"
          : "NOT_OBSERVED_AT_H_BAG";
  row["realized_affected_set_observable"] =
      horizon == Horizon::kSelectedSystem;
  row["realized_outcome_deltas"] =
      std::move(delta_rows);
  row["realized_outcome_deltas_sha256"] =
      sidecar_sha256;
  row["realized_externality_sha256"] =
      ics::canonical_map2_detail::sha256_hex(digest.payload());
  return row;
}

inline py::dict cohort_difference_sidecar_row(
    const BranchEvidence& baseline,
    const BranchEvidence& treatment) {
  if (baseline.cohort_outcomes.size() !=
      treatment.cohort_outcomes.size()) {
    throw std::logic_error(
        "cannot compare different system cohorts");
  }
  ics::g4irsf14_clone_detail::CanonicalFields digest;
  digest.string(
      "schema",
      "czr005.g4irsf15.full_cohort_outcome_difference.v1");
  digest.unsigned_integer(
      "row_count",
      static_cast<std::uint64_t>(
          baseline.cohort_outcomes.size()));
  py::list rows;
  int changed_count = 0;
  for (std::size_t index = 0;
       index < baseline.cohort_outcomes.size(); ++index) {
    const auto& left = baseline.cohort_outcomes[index];
    const auto& right = treatment.cohort_outcomes[index];
    if (left.runtime_bag_id != static_cast<int>(index) ||
        right.runtime_bag_id != static_cast<int>(index)) {
      throw std::logic_error(
          "full system cohort is not in runtime-id order");
    }
    const auto baseline_sha256 =
        causal_outcome_sha256(left);
    const auto treatment_sha256 =
        causal_outcome_sha256(right);
    const bool changed =
        !same_causal_outcome(left, right);
    if (changed !=
        (baseline_sha256 != treatment_sha256)) {
      throw std::logic_error(
          "canonical outcome hash/equality disagreement");
    }
    changed_count += changed ? 1 : 0;
    ics::g4irsf14_clone_detail::CanonicalFields item;
    item.integer("runtime_bag_id",
                 static_cast<int>(index));
    item.string("baseline_outcome_sha256",
                baseline_sha256);
    item.string("treatment_outcome_sha256",
                treatment_sha256);
    item.boolean("outcome_changed", changed);
    const auto item_sha256 =
        ics::canonical_map2_detail::sha256_hex(
            item.payload());
    digest.string("row_sha256", item_sha256);
    py::dict row;
    row["runtime_bag_id"] =
        static_cast<int>(index);
    row["baseline_outcome_sha256"] =
        baseline_sha256;
    row["treatment_outcome_sha256"] =
        treatment_sha256;
    row["outcome_changed"] = changed;
    row["row_sha256"] = item_sha256;
    rows.append(std::move(row));
  }
  digest.integer("changed_count", changed_count);
  py::dict sidecar;
  sidecar["schema"] =
      "czr005.g4irsf15.full_cohort_outcome_difference.v1";
  sidecar["row_count"] =
      static_cast<int>(baseline.cohort_outcomes.size());
  sidecar["changed_count"] = changed_count;
  sidecar["complete_coverage"] = true;
  sidecar["runtime_id_order"] =
      "CONTIGUOUS_ZERO_BASED_INPUT_ORDER";
  sidecar["rows"] = std::move(rows);
  sidecar["content_sha256"] =
      ics::canonical_map2_detail::sha256_hex(
          digest.payload());
  return sidecar;
}

inline py::dict branch_row(
    const BranchEvidence& evidence,
    const std::vector<ics::EventRuntimeBagRequest>& requests,
    const std::vector<double>& original_entry_times,
    bool compact_g4irsf20_h_system) {
  py::dict row;
  row["finalized"] = evidence.finalized;
  row["horizon_complete"] = evidence.horizon_complete;
  row["blocked"] = evidence.blocked;
  row["stop_reason"] = evidence.stop_reason;
  row["elapsed_event_count"] =
      py::int_(evidence.elapsed_event_count);
  row["terminal_state_sha256"] =
      evidence.terminal_state_sha256;
  row["terminal_digest_kind"] =
      evidence.terminal_digest_kind;
  py::list outcomes;
  for (const auto& outcome : evidence.affected_outcomes) {
    outcomes.append(outcome_row(outcome));
  }
  row["affected_bag_outcomes"] = std::move(outcomes);
  const auto segment_metrics =
      cohort_metrics_row(evidence.cohort_outcomes);
  row["cohort_metrics"] = segment_metrics;
  row["segment_cohort_metrics"] = segment_metrics;
  row["cohort_outcome_sha256"] =
      cohort_outcome_sha256(evidence.cohort_outcomes);
  row["cohort_outcomes_serialized"] = false;
  if (evidence.invariants.formal_hard_gate_evaluated) {
    row["raw_bag_cohort_metrics"] =
        raw_bag_cohort_metrics_row(
            evidence.cohort_outcomes, requests,
            original_entry_times);
    if (compact_g4irsf20_h_system) {
      row["raw_bag_sufficient_statistics_sidecar"] =
          py::none();
      row["raw_bag_sufficient_statistics_serialized"] =
          false;
      row["raw_bag_sufficient_statistics_omission_reason"] =
          "G4IRSF20_COMPACT_H_SYSTEM_OUTPUT";
      row["h_system_cohort_mapping_sha256"] = py::none();
      row["raw_bag_mapping_sha256"] = py::none();
      row["raw_bag_original_entry_mapping_sha256"] =
          py::none();
    } else {
      row["raw_bag_sufficient_statistics_sidecar"] =
          raw_bag_sufficient_statistics_sidecar_row(
              evidence.cohort_outcomes, requests,
              original_entry_times);
      row["raw_bag_sufficient_statistics_serialized"] =
          true;
      row["h_system_cohort_mapping_sha256"] =
          runtime_segment_mapping_sha256(requests);
      row["raw_bag_mapping_sha256"] =
          raw_bag_mapping_sha256(requests);
      row["raw_bag_original_entry_mapping_sha256"] =
          raw_bag_original_entry_mapping_sha256(
              requests, original_entry_times);
    }
  } else {
    row["raw_bag_cohort_metrics"] = py::none();
    row["raw_bag_sufficient_statistics_sidecar"] =
        py::none();
    row["raw_bag_sufficient_statistics_serialized"] =
        false;
    row["h_system_cohort_mapping_sha256"] = py::none();
    row["raw_bag_mapping_sha256"] = py::none();
    row["raw_bag_original_entry_mapping_sha256"] =
        py::none();
  }
  row["invariants"] = invariant_row(evidence.invariants);
  if (evidence.replay_hashes.has_value()) {
    row["replay_hashes"] =
        replay_hash_row(*evidence.replay_hashes);
  } else {
    row["replay_hashes"] = py::none();
  }
  return row;
}

inline py::dict step_row(
    const ics::G4IRSF14CausalStepResult& step) {
  py::dict row;
  row["event_processed"] = step.event_processed;
  row["treatment_requested"] = step.treatment_requested;
  row["target_opportunity_observed"] =
      step.target_opportunity_observed;
  row["intervention_applied"] = step.intervention_applied;
  row["changed_action_count"] = step.changed_action_count;
  row["source_state_sha256"] = step.source_state_sha256;
  row["requested_boundary_sha256"] =
      step.requested_boundary_sha256;
  row["requested_intervention_sha256"] =
      step.requested_intervention_sha256;
  row["application_reason"] = step.application_reason;
  row["affected_runtime_bag_ids"] =
      step.affected_runtime_bag_ids;
  return row;
}

}  // namespace detail

inline py::dict scan_causal_skeletons_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<EventRuntimeBagTuple>& bag_records,
    const std::vector<std::vector<double>>& scorer_w1,
    const std::vector<double>& scorer_b1,
    const std::vector<double>& scorer_w2,
    double scorer_b2,
    double scorer_risk_margin_threshold,
    double scorer_risk_bottleneck_threshold,
    const std::string& scorer_model_sha256,
    const std::vector<double>& original_entry_times,
    const std::string& research_profile) {
  const auto graph = detail::graph_from_records(
      node_records, edge_records, heuristic_time);
  const auto requests =
      detail::requests_from_records(bag_records);
  const auto protected_original_entry_times =
      detail::validated_original_entry_times(
          requests, original_entry_times);
  const auto raw_mapping =
      detail::raw_bag_runtime_mapping(requests);
  const bool protected_full_1x_shape =
      requests.size() == 43603U &&
      raw_mapping.size() == 28506U;
  const auto runtime_mapping_sha256 =
      detail::runtime_segment_mapping_sha256(requests);
  const auto raw_mapping_sha256 =
      detail::raw_bag_mapping_sha256(requests);
  const auto raw_original_entry_mapping_sha256 =
      detail::raw_bag_original_entry_mapping_sha256(
          requests, protected_original_entry_times);
  const auto config = detail::frozen_config(
      scorer_w1, scorer_b1, scorer_w2, scorer_b2,
      scorer_risk_margin_threshold,
      scorer_risk_bottleneck_threshold,
      scorer_model_sha256,
      research_profile);

  detail::Runtime source(graph, config);
  source.initialize(requests);
  std::array<detail::KindScanAccumulator, 3> accumulators;
  std::uint64_t event_ordinal = 0;
  std::uint64_t candidate_mask_event_count = 0;
  std::uint64_t false_positive_mask_event_count = 0;
  while (true) {
    const std::uint32_t mask =
        source.peek_causal_candidate_kind_mask() &
        (ics::kG4IRSF14CausalCandidateI1 |
         ics::kG4IRSF14CausalCandidateI3 |
         ics::kG4IRSF14CausalCandidateI4);
    if (mask == 0U) {
      if (!source.process_one_event()) {
        break;
      }
      ++event_ordinal;
      continue;
    }
    const auto probe =
        source.probe_one_event_for_causal_skeletons();
    if (!probe.event_processed) {
      if (probe.application_reason ==
          "SKELETON_PROBE_SKIPPED_RUNTIME_LIMIT") {
        break;
      }
      throw std::logic_error(
          "G4IRSF15 skeleton census stopped without a runtime limit");
    }
    if (probe.application_reason !=
        "SKELETON_PROBE_ONLY_NO_ACTION_CHANGED") {
      throw std::logic_error(
          "G4IRSF15 skeleton census changed a runtime action");
    }
    ++candidate_mask_event_count;
    for (int index = 0; index < 3; ++index) {
      if ((mask & detail::mask_for_index(index)) != 0U) {
        ++accumulators[static_cast<std::size_t>(index)]
              .mask_candidate_event_count;
      }
    }
    bool eligible_opportunity = false;
    for (const auto& skeleton : probe.observed_opportunities) {
      const int index = detail::kind_index(skeleton.kind);
      if (index < 0) {
        continue;
      }
      auto& accumulator =
          accumulators[static_cast<std::size_t>(index)];
      ++accumulator.observed_skeleton_count;
      const auto candidate =
          detail::primary_population_candidate(
              skeleton, probe.prepop, event_ordinal,
              probe.pibt_prefilter_candidate_event);
      if (!candidate.has_value()) {
        continue;
      }
      eligible_opportunity = true;
      if (!accumulator.population_group_ids.insert(
               candidate->population_group_sha256)
               .second) {
        ++accumulator.duplicate_population_group_count;
        continue;
      }
      accumulator.eligible_action_count +=
          static_cast<std::uint64_t>(
              candidate->candidate_action_count);
      accumulator.population.push_back(*candidate);
    }
    if (!eligible_opportunity) {
      ++false_positive_mask_event_count;
    }
    ++event_ordinal;
  }
  source.finalize();
  const auto terminal_replay_hashes =
      source.deterministic_replay_hashes();
  const auto terminal_invariants =
      detail::invariant_evidence(
          source.current_result().summary, true,
          protected_full_1x_shape,
          research_profile == "G20_S4_J2");
  const bool census_complete =
      terminal_invariants.formal_hard_gate_pass;

  py::dict counts;
  py::list skeleton_rows;
  std::uint64_t primary_population_count = 0;
  for (int index = 0; index < 3; ++index) {
    auto& accumulator =
        accumulators[static_cast<std::size_t>(index)];
    std::sort(
        accumulator.population.begin(),
        accumulator.population.end(),
        [](const detail::PopulationCandidate& left,
           const detail::PopulationCandidate& right) {
          if (left.population_selection_sha256 !=
              right.population_selection_sha256) {
            return left.population_selection_sha256 <
                   right.population_selection_sha256;
          }
          return left.event_ordinal < right.event_ordinal;
        });
    py::dict count;
    count["mask_candidate_event_count"] =
        py::int_(accumulator.mask_candidate_event_count);
    count["observed_skeleton_count"] =
        py::int_(accumulator.observed_skeleton_count);
    count["unique_population_group_count"] = py::int_(
        accumulator.population_group_ids.size());
    count["duplicate_population_group_count"] =
        py::int_(accumulator.duplicate_population_group_count);
    count["eligible_action_count"] =
        py::int_(accumulator.eligible_action_count);
    count["primary_population_count"] = py::int_(
        accumulator.population.size());
    counts[detail::kind_token(index)] = std::move(count);
    primary_population_count +=
        static_cast<std::uint64_t>(
            accumulator.population.size());
    for (const auto& candidate : accumulator.population) {
      if (research_profile == "G20_S4_J2") {
        if (index == 1) {
          skeleton_rows.append(
              detail::g4irsf20_route_census_row(candidate));
        }
      } else {
        skeleton_rows.append(
            detail::population_candidate_row(
                candidate, requests));
      }
    }
  }

  py::dict payload;
  payload["schema"] = kSkeletonScanSchema;
  payload["evidence_scope"] =
      "OUTCOME_FREE_NATIVE_PREPOP_SKELETON_CENSUS";
  payload["formal_pass_claimed"] = false;
  payload["census_complete"] = census_complete;
  payload["terminal_finalized"] = true;
  payload["protected_full_1x_shape"] =
      protected_full_1x_shape;
  payload["terminal_invariants"] =
      detail::invariant_row(terminal_invariants);
  payload["terminal_replay_hashes"] =
      detail::replay_hash_row(terminal_replay_hashes);
  payload["outcome_free"] = true;
  payload["sealed_descriptor_materialization_required"] = false;
  payload["target_address_frame_required"] = true;
  payload["full_state_seal_policy"] =
      "DEFERRED_TO_EXECUTED_PAIR";
  payload["frozen_controls"] =
      detail::frozen_controls_row(research_profile);
  payload["input_request_count"] =
      static_cast<int>(requests.size());
  payload["input_runtime_cohort_sha256"] =
      detail::workload_cohort_sha256(requests);
  payload["h_system_cohort_mapping_sha256"] =
      runtime_mapping_sha256;
  payload["raw_bag_mapping_sha256"] =
      raw_mapping_sha256;
  payload["raw_bag_original_entry_mapping_sha256"] =
      raw_original_entry_mapping_sha256;
  payload["raw_bag_count"] =
      static_cast<int>(raw_mapping.size());
  payload["processed_event_count"] =
      py::int_(event_ordinal);
  payload["candidate_mask_event_count"] =
      py::int_(candidate_mask_event_count);
  payload["false_positive_mask_event_count"] =
      py::int_(false_positive_mask_event_count);
  payload["primary_population_count"] =
      py::int_(primary_population_count);
  payload["sample_rule"] =
      "FULL_CENSUS_ONE_LOCAL_NUMERIC_PRIMARY_ACTION_PER_POPULATION_GROUP";
  payload["population_counts"] = std::move(counts);
  payload["skeletons"] = std::move(skeleton_rows);
  payload["skeleton_rows_scope"] =
      research_profile == "G20_S4_J2"
          ? "I3_COMPACT_CENSUS_ONLY"
          : "ALL_PRIMARY_KINDS";
  return payload;
}

inline py::dict materialize_causal_descriptors_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<EventRuntimeBagTuple>& bag_records,
    const std::vector<std::vector<double>>& scorer_w1,
    const std::vector<double>& scorer_b1,
    const std::vector<double>& scorer_w2,
    double scorer_b2,
    double scorer_risk_margin_threshold,
    double scorer_risk_bottleneck_threshold,
    const std::string& scorer_model_sha256,
    const std::vector<double>& original_entry_times,
    const py::sequence& selected_skeletons,
    const std::string& research_profile) {
  std::vector<detail::SelectedSkeleton> selected;
  selected.reserve(
      static_cast<std::size_t>(py::len(selected_skeletons)));
  for (const py::handle item : selected_skeletons) {
    if (!PyDict_Check(item.ptr())) {
      throw py::type_error(
          "every selected skeleton must be a dict");
    }
    selected.push_back(detail::parse_selected_skeleton(
        py::reinterpret_borrow<py::dict>(item)));
  }
  if (selected.empty()) {
    throw py::value_error(
        "descriptor materialization requires at least one skeleton");
  }
  std::sort(
      selected.begin(), selected.end(),
      [](const detail::SelectedSkeleton& left,
         const detail::SelectedSkeleton& right) {
        if (left.event_ordinal != right.event_ordinal) {
          return left.event_ordinal < right.event_ordinal;
        }
        return left.skeleton_id < right.skeleton_id;
      });
  std::set<std::string> skeleton_ids;
  std::set<std::pair<int, std::string>> population_groups;
  for (const auto& item : selected) {
    if (!skeleton_ids.insert(item.skeleton_id).second) {
      throw py::value_error(
          "duplicate skeleton_id in materialization batch");
    }
    if (!population_groups
             .emplace(item.kind_index,
                      item.population_group_sha256)
             .second) {
      throw py::value_error(
          "duplicate (kind, population_group_sha256) in "
          "materialization batch");
    }
  }

  const auto graph = detail::graph_from_records(
      node_records, edge_records, heuristic_time);
  const auto requests =
      detail::requests_from_records(bag_records);
  const auto protected_original_entry_times =
      detail::validated_original_entry_times(
          requests, original_entry_times);
  const auto config = detail::frozen_config(
      scorer_w1, scorer_b1, scorer_w2, scorer_b2,
      scorer_risk_margin_threshold,
      scorer_risk_bottleneck_threshold,
      scorer_model_sha256,
      research_profile);
  detail::Runtime source(graph, config);
  source.initialize(requests);

  py::list descriptors;
  std::set<std::pair<int, std::string>>
      materialized_clone_groups;
  std::uint64_t event_ordinal = 0;
  std::size_t cursor = 0;
  while (cursor < selected.size()) {
    const auto selected_ordinal =
        selected[cursor].event_ordinal;
    while (event_ordinal < selected_ordinal) {
      // The complete census already proved that the lightweight skeleton
      // probe and the ordinary committed transition have identical terminal
      // replay hashes.  Materialization needs a full opportunity probe only
      // at selected ordinals; rebuilding every discarded skeleton here made
      // a 6,144-target panel repeat almost the whole census data path.
      if (!source.process_one_event()) {
        throw py::value_error(
            "selected skeleton event_ordinal is after the "
            "last live event");
      }
      ++event_ordinal;
    }
    const auto strata =
        source.g4irsf15_causal_prepop_strata();
    const auto pibt_prefilter_before =
        source.current_result()
            .summary.g4irsf14_i5_prefilter_candidate_count;
    const auto probe =
        source.probe_one_event_for_causal_opportunities();
    const bool pibt_prefilter_candidate_event =
        source.current_result()
            .summary.g4irsf14_i5_prefilter_candidate_count >
        pibt_prefilter_before;
    if (!probe.event_processed ||
        probe.treatment_requested ||
        probe.changed_action_count != 0 ||
        probe.application_reason !=
            "PROBE_ONLY_NO_ACTION_CHANGED") {
      throw std::logic_error(
          "descriptor materialization changed a runtime action");
    }
    std::size_t group_end = cursor;
    while (group_end < selected.size() &&
           selected[group_end].event_ordinal ==
               selected_ordinal) {
      ++group_end;
    }
    for (std::size_t index = cursor;
         index < group_end; ++index) {
      const auto& requested = selected[index];
      std::optional<detail::PrimaryDescriptor> match;
      for (const auto& boundary : probe.observed_opportunities) {
        if (detail::kind_index(boundary.kind) !=
            requested.kind_index) {
          continue;
        }
        const auto candidate =
            detail::primary_population_candidate(
                detail::skeleton_from_boundary(boundary),
                strata, selected_ordinal,
                pibt_prefilter_candidate_event);
        if (!candidate.has_value() ||
            candidate->population_group_sha256 !=
                requested.population_group_sha256 ||
            candidate->population_selection_sha256 !=
                requested.skeleton_id) {
          continue;
        }
        if (match.has_value()) {
          throw std::logic_error(
              "one selected skeleton matched multiple native "
              "boundaries");
        }
        match = detail::seal_primary_descriptor(
            *candidate, boundary, strata,
            pibt_prefilter_candidate_event);
      }
      if (!match.has_value()) {
        throw py::value_error(
            "selected skeleton did not replay as the exact "
            "native primary opportunity");
      }
      const auto clone_key = std::make_pair(
          requested.kind_index,
          match->boundary.clone_group_id);
      if (!materialized_clone_groups.insert(clone_key).second) {
        throw py::value_error(
            "materialization produced duplicate "
            "(kind, clone_group_id)");
      }
      descriptors.append(detail::descriptor_row(*match));
    }
    ++event_ordinal;
    cursor = group_end;
  }

  py::dict payload;
  payload["schema"] = kMaterializationSchema;
  payload["evidence_scope"] =
      "SELECTED_NATIVE_PREPOP_BOUNDARY_MATERIALIZATION";
  payload["formal_pass_claimed"] = false;
  payload["frozen_controls"] =
      detail::frozen_controls_row(research_profile);
  payload["input_request_count"] =
      static_cast<int>(requests.size());
  payload["input_runtime_cohort_sha256"] =
      detail::workload_cohort_sha256(requests);
  payload["h_system_cohort_mapping_sha256"] =
      detail::runtime_segment_mapping_sha256(requests);
  payload["raw_bag_mapping_sha256"] =
      detail::raw_bag_mapping_sha256(requests);
  payload["raw_bag_original_entry_mapping_sha256"] =
      detail::raw_bag_original_entry_mapping_sha256(
          requests, protected_original_entry_times);
  payload["raw_bag_count"] = static_cast<int>(
      detail::raw_bag_runtime_mapping(requests).size());
  payload["selected_skeleton_count"] =
      static_cast<int>(selected.size());
  payload["materialized_descriptor_count"] =
      static_cast<int>(selected.size());
  payload["source_events_replayed"] =
      py::int_(event_ordinal);
  payload["descriptors"] = std::move(descriptors);
  return payload;
}

inline py::dict run_causal_target_pairs_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<EventRuntimeBagTuple>& bag_records,
    const std::vector<std::vector<double>>& scorer_w1,
    const std::vector<double>& scorer_b1,
    const std::vector<double>& scorer_w2,
    double scorer_b2,
    double scorer_risk_margin_threshold,
    double scorer_risk_bottleneck_threshold,
    const std::string& scorer_model_sha256,
    const std::vector<double>& original_entry_times,
    const py::sequence& target_descriptors,
    const std::string& research_profile) {
  std::vector<detail::Target> targets;
  targets.reserve(
      static_cast<std::size_t>(py::len(target_descriptors)));
  for (const py::handle item : target_descriptors) {
    if (!PyDict_Check(item.ptr())) {
      throw py::type_error(
          "every target descriptor must be a dict");
    }
    targets.push_back(detail::parse_target(
        py::reinterpret_borrow<py::dict>(item)));
  }
  if (targets.empty()) {
    throw py::value_error(
        "run_causal_target_pairs requires at least one target");
  }
  std::sort(targets.begin(), targets.end(),
            [](const detail::Target& left,
               const detail::Target& right) {
              if (left.event_ordinal != right.event_ordinal) {
                return left.event_ordinal < right.event_ordinal;
              }
              return left.descriptor_id < right.descriptor_id;
            });
  std::set<std::string> descriptor_ids;
  std::set<std::pair<int, std::string>> clone_groups;
  for (const auto& target : targets) {
    if (!descriptor_ids.insert(target.descriptor_id).second) {
      throw py::value_error(
          "duplicate descriptor_id in target batch");
    }
    const auto uniqueness_id = target.deferred_address
                                   ? target.descriptor_id
                                   : target.clone_group_id;
    if (!clone_groups
             .emplace(target.kind_index, uniqueness_id)
             .second) {
      throw py::value_error(
          "duplicate native target identity in target batch");
    }
  }

  const auto graph = detail::graph_from_records(
      node_records, edge_records, heuristic_time);
  const auto requests =
      detail::requests_from_records(bag_records);
  const auto input_runtime_cohort_sha256 =
      detail::workload_cohort_sha256(requests);
  for (const auto& target : targets) {
    if ((target.g4irsf20_route_target ||
         target.g4irsf21_route_action_target) &&
        research_profile != "G20_S4_J2") {
      throw py::value_error(
          "G20/G21 Route targets require research_profile G20_S4_J2");
    }
    if (target.deferred_address &&
        !target.g4irsf20_route_target &&
        !target.g4irsf21_route_action_target &&
        target.input_runtime_cohort_sha256 !=
            input_runtime_cohort_sha256) {
      throw py::value_error(
          "deferred target address input cohort drifted");
    }
  }
  const auto protected_original_entry_times =
      detail::validated_original_entry_times(
          requests, original_entry_times);
  const auto raw_mapping =
      detail::raw_bag_runtime_mapping(requests);
  const bool protected_full_1x_shape =
      requests.size() == 43603U &&
      raw_mapping.size() == 28506U;
  const auto runtime_mapping_sha256 =
      detail::runtime_segment_mapping_sha256(requests);
  const auto raw_mapping_sha256 =
      detail::raw_bag_mapping_sha256(requests);
  const auto raw_original_entry_mapping_sha256 =
      detail::raw_bag_original_entry_mapping_sha256(
          requests, protected_original_entry_times);
  const auto config = detail::frozen_config(
      scorer_w1, scorer_b1, scorer_w2, scorer_b2,
      scorer_risk_margin_threshold,
      scorer_risk_bottleneck_threshold,
      scorer_model_sha256,
      research_profile);
  std::vector<int> all_runtime_ids(requests.size());
  std::iota(all_runtime_ids.begin(), all_runtime_ids.end(), 0);

  detail::Runtime source(graph, config);
  source.initialize(requests);
  detail::Runtime branch(graph, config);
  py::list pairs;
  std::uint64_t source_event_ordinal = 0;
  std::size_t target_cursor = 0;
  int applied_action_changing_pair_count = 0;
  int complete_action_changing_h_bag_count = 0;
  int applied_action_changing_h_system_count = 0;
  int complete_h_system_hard_gate_pass_count = 0;
  int false_positive_pair_count = 0;
  while (target_cursor < targets.size()) {
    const auto target_ordinal =
        targets[target_cursor].event_ordinal;
    while (source_event_ordinal < target_ordinal) {
      // Target descriptors seal the ordinals that require the expensive
      // causal probe.  All intervening events use the equivalent ordinary
      // transition, avoiding a redundant full skeleton census in every
      // fresh pair worker.
      if (!source.process_one_event()) {
        throw py::value_error(
            "target event_ordinal is after the last live event");
      }
      ++source_event_ordinal;
    }
    const auto source_strata =
        source.g4irsf15_causal_prepop_strata();
    const auto pibt_prefilter_before =
        source.current_result()
            .summary.g4irsf14_i5_prefilter_candidate_count;
    const auto checkpoint = source.capture_state_checkpoint();
    const auto source_state_sha256 = checkpoint.state_sha256();
    std::size_t group_end = target_cursor;
    while (group_end < targets.size() &&
           targets[group_end].event_ordinal ==
               target_ordinal) {
      if (!targets[group_end].deferred_address &&
          targets[group_end].runtime_state_sha256 !=
              source_state_sha256) {
        throw py::value_error(
            "target runtime_state_sha256 does not match replayed "
            "pre-pop checkpoint");
      }
      ++group_end;
    }
    const auto source_probe =
        source.probe_one_event_for_causal_opportunities();
    const bool pibt_prefilter_candidate_event =
        source.current_result()
            .summary.g4irsf14_i5_prefilter_candidate_count >
        pibt_prefilter_before;
    if (!source_probe.event_processed ||
        source_probe.source_state_sha256 !=
            source_state_sha256) {
      throw std::logic_error(
          "source probe did not consume the checkpoint queue top");
    }
    ++source_event_ordinal;

    for (std::size_t index = target_cursor;
         index < group_end; ++index) {
      auto target = targets[index];
      auto found = source_probe.observed_opportunities.end();
      std::optional<detail::PopulationCandidate>
          requested_route_population;
      bool ambiguous_address = false;
      if (target.deferred_address) {
        for (auto candidate_boundary =
                 source_probe.observed_opportunities.begin();
             candidate_boundary !=
                 source_probe.observed_opportunities.end();
             ++candidate_boundary) {
          if (detail::kind_index(candidate_boundary->kind) !=
              target.kind_index) {
            continue;
          }
          const auto candidate =
              detail::primary_population_candidate(
                  detail::skeleton_from_boundary(*candidate_boundary),
                  source_strata, target.event_ordinal,
                  pibt_prefilter_candidate_event);
          if (!candidate.has_value() ||
              candidate->population_group_sha256 !=
                  target.population_group_sha256 ||
              candidate->population_selection_sha256 !=
                  target.skeleton_id) {
            continue;
          }
          if (found != source_probe.observed_opportunities.end()) {
            ambiguous_address = true;
            found = source_probe.observed_opportunities.end();
            break;
          }
          found = candidate_boundary;
        }
      } else {
        found = std::find_if(
            source_probe.observed_opportunities.begin(),
            source_probe.observed_opportunities.end(),
            [&](const detail::Boundary& boundary) {
              return boundary.boundary_sha256() ==
                     target.boundary_sha256;
            });
      }
      py::dict pair;
      pair["descriptor_id"] = target.descriptor_id;
      pair["target_address_id"] = target.descriptor_id;
      if (target.g4irsf20_route_target) {
        pair["target_schema"] = kG4IRSF20RouteTargetSchema;
        pair["population_group_id"] =
            target.population_group_sha256;
        pair["population_selection_id"] =
            target.population_selection_sha256;
      } else if (target.g4irsf21_route_action_target) {
        pair["target_schema"] =
            kG4IRSF21RouteActionTargetSchema;
        pair["population_group_id"] =
            target.population_group_sha256;
        pair["population_selection_id"] =
            target.population_selection_sha256;
        pair["target_action_id"] = target.descriptor_id;
        pair["action_kind"] = target.route_action_kind;
        if (target.route_action_kind == "NEXT_EDGE") {
          pair["requested_next_node"] =
              target.requested_route_next_node;
          pair["selected_next_node"] =
              target.requested_route_next_node;
        } else {
          pair["requested_next_node"] = py::none();
          pair["selected_next_node"] = py::none();
        }
      }
      pair["kind"] = detail::kind_token(target.kind_index);
      pair["event_ordinal"] =
          py::int_(target.event_ordinal);
      pair["horizon"] =
          target.horizon == detail::Horizon::kSelectedSystem
              ? "H_system"
              : "H_bag";
      pair["source_checkpoint_state_sha256"] =
          source_state_sha256;
      pair["protected_full_1x_shape"] =
          protected_full_1x_shape;
      pair["resolved_execution_descriptor"] = py::none();
      pair["same_state_start"] = false;
      pair["pair_status"] = "SCREENING_FALSE_POSITIVE";
      if (ambiguous_address) {
        pair["false_positive_reason"] =
            "TARGET_ADDRESS_MATCHED_MULTIPLE_NATIVE_BOUNDARIES";
        pair["source_probe"] = detail::step_row(source_probe);
        pairs.append(std::move(pair));
        ++false_positive_pair_count;
        continue;
      }
      if (found == source_probe.observed_opportunities.end()) {
        pair["false_positive_reason"] =
            "CONTENT_ADDRESSED_BOUNDARY_NOT_OBSERVED";
        pair["source_probe"] = detail::step_row(source_probe);
        pairs.append(std::move(pair));
        ++false_positive_pair_count;
        continue;
      }

      if (target.g4irsf20_route_target) {
        const auto resolved = detail::primary_population_candidate(
            detail::skeleton_from_boundary(*found),
            source_strata, target.event_ordinal,
            pibt_prefilter_candidate_event);
        if (!resolved.has_value() ||
            resolved->population_group_sha256 !=
                target.population_group_sha256 ||
            resolved->population_selection_sha256 !=
                target.population_selection_sha256) {
          throw std::logic_error(
              "matched G20 Route target did not reproduce its population IDs");
        }
        target.clone_group_id = found->clone_group_id;
        target.event_seq = found->event_seq;
        target.event_time_bits =
            ics::event_runtime_detail::timestamp_bits(found->time);
        target.node = found->node;
        target.runtime_bag_id = found->runtime_bag_id;
        target.peer_runtime_bag_id =
            resolved->peer_runtime_bag_id;
        target.baseline_next_node =
            found->baseline_next_node;
        target.selected_next_node =
            resolved->selected_next_node;
        target.baseline_release = found->baseline_release;
        target.selected_boolean = resolved->selected_boolean;
        target.source_ready_order = found->source_ready_order;
        target.legal_next_edges = found->legal_next_edges;
        target.baseline_action = resolved->baseline_action;
        target.intervention_action =
            resolved->intervention_action;
        target.expected_action_change_type =
            resolved->expected_action_change_type;
      } else if (target.g4irsf21_route_action_target) {
        const auto anchor = found;
        const auto anchor_population =
            detail::primary_population_candidate(
                detail::skeleton_from_boundary(*anchor),
                source_strata, target.event_ordinal,
                pibt_prefilter_candidate_event);
        if (!anchor_population.has_value() ||
            anchor_population->population_group_sha256 !=
                target.population_group_sha256 ||
            anchor_population->population_selection_sha256 !=
                target.population_selection_sha256) {
          throw std::logic_error(
              "matched G21 Route anchor did not reproduce its population IDs");
        }

        if (target.route_action_kind == "NEXT_EDGE") {
          requested_route_population =
              detail::route_action_population_candidate(
                  detail::skeleton_from_boundary(*anchor),
                  source_strata, target.event_ordinal,
                  pibt_prefilter_candidate_event,
                  target.route_action_kind,
                  target.requested_route_next_node);
          if (!requested_route_population.has_value()) {
            pair["false_positive_reason"] =
                "REQUESTED_NEXT_EDGE_NOT_LEGAL_AT_I3_BOUNDARY";
            pair["source_probe"] = detail::step_row(source_probe);
            pairs.append(std::move(pair));
            ++false_positive_pair_count;
            continue;
          }
        } else {
          auto wait_sibling =
              source_probe.observed_opportunities.end();
          bool ambiguous_wait_sibling = false;
          for (auto candidate_boundary =
                   source_probe.observed_opportunities.begin();
               candidate_boundary !=
                   source_probe.observed_opportunities.end();
               ++candidate_boundary) {
            if (detail::kind_index(candidate_boundary->kind) != 2 ||
                candidate_boundary->clone_group_id !=
                    anchor->clone_group_id ||
                candidate_boundary->event_seq != anchor->event_seq ||
                !ics::event_runtime_detail::same_timestamp(
                    candidate_boundary->time, anchor->time) ||
                candidate_boundary->node != anchor->node ||
                candidate_boundary->runtime_bag_id !=
                    anchor->runtime_bag_id ||
                candidate_boundary->baseline_next_node !=
                    anchor->baseline_next_node ||
                !candidate_boundary->baseline_release ||
                candidate_boundary->legal_next_edges !=
                    anchor->legal_next_edges) {
              continue;
            }
            if (wait_sibling !=
                source_probe.observed_opportunities.end()) {
              ambiguous_wait_sibling = true;
              wait_sibling =
                  source_probe.observed_opportunities.end();
              break;
            }
            wait_sibling = candidate_boundary;
          }
          if (ambiguous_wait_sibling ||
              wait_sibling ==
                  source_probe.observed_opportunities.end()) {
            pair["false_positive_reason"] =
                ambiguous_wait_sibling
                    ? "WAIT_ACTION_MATCHED_MULTIPLE_I4_SIBLINGS"
                    : "LEGAL_WAIT_I4_SIBLING_NOT_OBSERVED";
            pair["source_probe"] = detail::step_row(source_probe);
            pairs.append(std::move(pair));
            ++false_positive_pair_count;
            continue;
          }
          found = wait_sibling;
          target.kind_index = 2;
          requested_route_population =
              detail::route_action_population_candidate(
                  detail::skeleton_from_boundary(*found),
                  source_strata, target.event_ordinal,
                  pibt_prefilter_candidate_event,
                  target.route_action_kind, -1);
          if (!requested_route_population.has_value()) {
            throw std::logic_error(
                "matched G21 WAIT sibling is not a native legal hold action");
          }
        }

        const auto& resolved = *requested_route_population;
        target.clone_group_id = found->clone_group_id;
        target.event_seq = found->event_seq;
        target.event_time_bits =
            ics::event_runtime_detail::timestamp_bits(found->time);
        target.node = found->node;
        target.runtime_bag_id = found->runtime_bag_id;
        target.peer_runtime_bag_id =
            resolved.peer_runtime_bag_id;
        target.baseline_next_node = found->baseline_next_node;
        target.selected_next_node =
            resolved.selected_next_node;
        target.baseline_release = found->baseline_release;
        target.selected_boolean = resolved.selected_boolean;
        target.source_ready_order = found->source_ready_order;
        target.legal_next_edges = found->legal_next_edges;
        target.baseline_action = resolved.baseline_action;
        target.intervention_action = resolved.intervention_action;
        target.expected_action_change_type =
            resolved.expected_action_change_type;
        pair["kind"] = detail::kind_token(target.kind_index);
        pair["resolved_action_selection_id"] =
            resolved.population_selection_sha256;
      }

      detail::verify_target_boundary(target, *found);
      detail::PopulationCandidate resolved_population;
      detail::PrimaryDescriptor resolved_descriptor;
      if (target.g4irsf21_route_action_target) {
        resolved_population = *requested_route_population;
        resolved_descriptor =
            detail::seal_route_action_descriptor(
                resolved_population, *found, source_strata,
                pibt_prefilter_candidate_event,
                target.route_action_kind);
      } else {
        resolved_population = detail::verify_target_population(
            target, *found, source_strata,
            pibt_prefilter_candidate_event);
        resolved_descriptor =
            detail::seal_primary_descriptor(
                resolved_population, *found, source_strata,
                pibt_prefilter_candidate_event);
      }
      const auto intervention =
          detail::intervention_for(target, *found);
      pair["resolved_execution_descriptor"] =
          detail::descriptor_row(resolved_descriptor);
      py::object observation = py::none();
      if (target.kind_index == 0) {
        observation = detail::g4irsf17_i1_observation_pair_row(
            *found, target.peer_runtime_bag_id);
      } else if (target.kind_index == 1) {
        observation = detail::g4irsf20_route_observation_row(
            *found, target.selected_next_node);
      }
      pair["observation_pair"] = observation;
      pair["route_observation"] =
          target.kind_index == 1
              ? observation
              : py::object(py::none());
      pair["resolved_execution_runtime_state_sha256"] =
          found->runtime_state_sha256;
      pair["resolved_execution_boundary_sha256"] =
          found->boundary_sha256();
      pair["resolved_execution_intervention_sha256"] =
          intervention.intervention_sha256(*found);
      ics::G4IRSF14CausalInterventionDirective directive;
      directive.boundary = *found;
      directive.intervention = intervention;
      directive.validate();
      const auto intended_ids =
          detail::intended_affected_ids(target);

      branch.restore_state_checkpoint(checkpoint);
      const auto baseline_start_sha256 =
          branch.deterministic_state_sha256();
      const auto baseline_pre_action =
          detail::local_snapshots(branch, intended_ids);
      const auto baseline_step =
          branch.probe_one_event_for_causal_opportunities();
      const auto baseline_post_action =
          detail::local_snapshots(branch, intended_ids);
      const std::uint64_t baseline_start_event_count =
          static_cast<std::uint64_t>(
              std::max(0, branch.current_result().summary.event_count));

      branch.restore_state_checkpoint(checkpoint);
      const auto treatment_start_sha256 =
          branch.deterministic_state_sha256();
      const auto treatment_pre_action =
          detail::local_snapshots(branch, intended_ids);
      const auto treatment_step =
          branch.process_one_event_with_causal_intervention(
              directive);
      const auto treatment_post_action =
          detail::local_snapshots(branch, intended_ids);

      pair["baseline_start_state_sha256"] =
          baseline_start_sha256;
      pair["treatment_start_state_sha256"] =
          treatment_start_sha256;
      const bool same_state =
          baseline_start_sha256 == source_state_sha256 &&
          treatment_start_sha256 == source_state_sha256;
      pair["same_state_start"] = same_state;
      pair["baseline_step"] = detail::step_row(baseline_step);
      pair["treatment_step"] =
          detail::step_row(treatment_step);
      pair["affected_runtime_bag_ids"] =
          treatment_step.affected_runtime_bag_ids;

      const auto certificate = detail::action_certificate(
          target, *found, treatment_step,
          baseline_pre_action, baseline_post_action,
          treatment_pre_action, treatment_post_action);
      const bool certificate_valid =
          py::cast<bool>(certificate["valid"]);
      pair["committed_action_certificate"] = certificate;
      auto expected_affected = intended_ids;
      auto observed_affected =
          treatment_step.affected_runtime_bag_ids;
      std::sort(observed_affected.begin(),
                observed_affected.end());
      const bool applied =
          same_state &&
          treatment_step.target_opportunity_observed &&
          treatment_step.intervention_applied &&
          treatment_step.changed_action_count == 1 &&
          observed_affected == expected_affected &&
          certificate_valid;
      if (!applied) {
        pair["false_positive_reason"] =
            treatment_step.application_reason.empty()
                ? "POST_COMMIT_ACTION_CERTIFICATE_FAILED"
                : treatment_step.application_reason;
        pairs.append(std::move(pair));
        ++false_positive_pair_count;
        continue;
      }

      const std::uint64_t treatment_start_event_count =
          static_cast<std::uint64_t>(
              std::max(0, branch.current_result().summary.event_count));
      const auto treatment_evidence = detail::drive_branch(
          branch, target.horizon, intended_ids, all_runtime_ids,
          found->node, treatment_start_event_count,
          protected_full_1x_shape,
          research_profile == "G20_S4_J2");

      // Replaying one baseline event is much cheaper than retaining a second
      // full checkpoint while a possibly full-system treatment drains.
      branch.restore_state_checkpoint(checkpoint);
      if (branch.deterministic_state_sha256() !=
          baseline_start_sha256) {
        throw std::logic_error(
            "baseline replay did not restore the exact pair start state");
      }
      const auto replayed_baseline_pre_action =
          detail::local_snapshots(branch, intended_ids);
      const auto replayed_baseline_step =
          branch.probe_one_event_for_causal_opportunities();
      const auto replayed_baseline_post_action =
          detail::local_snapshots(branch, intended_ids);
      if (!detail::same_local_action_snapshots(
              baseline_pre_action,
              replayed_baseline_pre_action) ||
          !detail::same_local_action_snapshots(
              baseline_post_action,
              replayed_baseline_post_action) ||
          replayed_baseline_step.source_state_sha256 !=
              baseline_step.source_state_sha256 ||
          replayed_baseline_step.changed_action_count != 0) {
        throw std::logic_error(
            "baseline one-event replay is not deterministic");
      }
      const auto baseline_evidence = detail::drive_branch(
          branch, target.horizon, intended_ids, all_runtime_ids,
          found->node, baseline_start_event_count,
          protected_full_1x_shape,
          research_profile == "G20_S4_J2");
      const bool compact_g4irsf20_h_system =
          (target.g4irsf20_route_target ||
           target.g4irsf21_route_action_target) &&
          research_profile == "G20_S4_J2" &&
          target.horizon == detail::Horizon::kSelectedSystem;
      pair["baseline"] =
          detail::branch_row(
              baseline_evidence, requests,
              protected_original_entry_times,
              compact_g4irsf20_h_system);
      pair["treatment"] =
          detail::branch_row(
              treatment_evidence, requests,
              protected_original_entry_times,
              compact_g4irsf20_h_system);
      py::list affected_deltas;
      if (baseline_evidence.affected_outcomes.size() !=
          treatment_evidence.affected_outcomes.size()) {
        throw std::logic_error(
            "matched branches produced different affected cohorts");
      }
      for (std::size_t outcome_index = 0;
           outcome_index <
               baseline_evidence.affected_outcomes.size();
           ++outcome_index) {
        affected_deltas.append(
            detail::realized_outcome_delta_row(
                baseline_evidence
                    .affected_outcomes[outcome_index],
                treatment_evidence
                    .affected_outcomes[outcome_index]));
      }
      pair["affected_bag_deltas"] =
          std::move(affected_deltas);
      pair["direct_affected_runtime_bag_ids"] = intended_ids;
      if (compact_g4irsf20_h_system) {
        pair["realized_externality"] = py::none();
        pair["realized_affected_runtime_bag_ids"] = py::none();
        pair["externality_runtime_bag_ids"] = py::none();
        pair["externality_observation_status"] =
            "OMITTED_G4IRSF20_COMPACT_H_SYSTEM_OUTPUT";
        pair["realized_affected_set_observable"] = false;
        pair["realized_outcome_deltas"] = py::none();
        pair["realized_outcome_deltas_sha256"] = py::none();
      } else {
        const auto externality = detail::realized_externality_row(
            baseline_evidence, treatment_evidence, intended_ids,
            target.horizon);
        pair["realized_externality"] = externality;
        pair["realized_affected_runtime_bag_ids"] =
            externality["realized_affected_runtime_bag_ids"];
        pair["externality_runtime_bag_ids"] =
            externality["realized_external_runtime_bag_ids"];
        pair["externality_observation_status"] =
            externality["externality_observation_status"];
        pair["realized_affected_set_observable"] =
            externality["realized_affected_set_observable"];
        pair["realized_outcome_deltas"] =
            externality["realized_outcome_deltas"];
        pair["realized_outcome_deltas_sha256"] =
            externality["realized_outcome_deltas_sha256"];
      }
      if (target.horizon ==
              detail::Horizon::kSelectedSystem &&
          !compact_g4irsf20_h_system) {
        pair["cohort_difference_sidecar"] =
            detail::cohort_difference_sidecar_row(
                baseline_evidence, treatment_evidence);
        pair["cohort_difference_sidecar_serialized"] =
            true;
      } else {
        pair["cohort_difference_sidecar"] = py::none();
        pair["cohort_difference_sidecar_serialized"] =
            false;
      }
      if (compact_g4irsf20_h_system) {
        py::dict omissions;
        omissions["raw_bag_sufficient_statistics_sidecar"] = true;
        omissions["cohort_difference_sidecar"] = true;
        omissions["realized_externality_outcome_deltas"] = true;
        omissions["preserved_affected_bag_deltas"] = true;
        omissions["preserved_aggregate_cohort_metrics"] = true;
        omissions["preserved_hard_gates"] = true;
        omissions["preserved_route_observation"] = true;
        pair["g4irsf20_compact_h_system_output"] = true;
        pair["g4irsf20_compact_omissions"] =
            std::move(omissions);
      }
      const bool live_safety_pass =
          baseline_evidence.invariants.live_safety_pass &&
          treatment_evidence.invariants.live_safety_pass;
      const bool formal_hard_gate_evaluated =
          target.horizon ==
          detail::Horizon::kSelectedSystem;
      const bool formal_hard_gate_pass =
          formal_hard_gate_evaluated &&
          (baseline_evidence.invariants.formal_hard_gate_pass &&
           treatment_evidence.invariants.formal_hard_gate_pass);
      const bool horizon_complete =
          baseline_evidence.horizon_complete &&
          treatment_evidence.horizon_complete &&
          !baseline_evidence.blocked &&
          !treatment_evidence.blocked;
      const bool complete =
          horizon_complete && live_safety_pass &&
          (!formal_hard_gate_evaluated ||
           formal_hard_gate_pass);
      std::string pair_status;
      if (!horizon_complete) {
        pair_status = "ACTION_CHANGED_HORIZON_BLOCKED";
      } else if (!live_safety_pass ||
                 (formal_hard_gate_evaluated &&
                  !formal_hard_gate_pass)) {
        pair_status = "ACTION_CHANGED_HARD_GATE_FAILED";
      } else {
        pair_status = "ACTION_CHANGED_HORIZON_COMPLETE";
      }
      pair["pair_status"] = pair_status;
      pair["action_changed"] = true;
      pair["horizon_complete"] = horizon_complete;
      pair["pair_complete"] = complete;
      pair["live_safety_pass"] = live_safety_pass;
      pair["safety_equivalent"] = live_safety_pass;
      pair["formal_hard_gate_evaluated"] =
          formal_hard_gate_evaluated;
      pair["formal_hard_gate_pass"] =
          formal_hard_gate_pass;
      pair["hard_gate_pass"] =
          live_safety_pass &&
          (!formal_hard_gate_evaluated ||
           formal_hard_gate_pass);
      std::vector<std::string> pair_fail_reasons;
      for (const auto& reason :
           baseline_evidence.invariants
               .hard_gate_fail_reasons) {
        pair_fail_reasons.push_back(
            "BASELINE:" + reason);
      }
      for (const auto& reason :
           treatment_evidence.invariants
               .hard_gate_fail_reasons) {
        pair_fail_reasons.push_back(
            "TREATMENT:" + reason);
      }
      pair["hard_gate_fail_reasons"] =
          pair_fail_reasons;
      pair["h_system_cohort_is_all_input_runtime_ids"] =
          target.horizon ==
                  detail::Horizon::kSelectedSystem &&
          all_runtime_ids.size() == requests.size();
      pair["h_system_cohort_size"] =
          target.horizon == detail::Horizon::kSelectedSystem
              ? py::int_(all_runtime_ids.size())
              : py::int_(0);
      pair["h_system_cohort_mapping_sha256"] =
          target.horizon ==
                  detail::Horizon::kSelectedSystem
              ? py::object(py::str(runtime_mapping_sha256))
              : py::object(py::none());
      pair["raw_bag_mapping_sha256"] =
          target.horizon ==
                  detail::Horizon::kSelectedSystem
              ? py::object(py::str(raw_mapping_sha256))
              : py::object(py::none());
      pair["raw_bag_original_entry_mapping_sha256"] =
          target.horizon ==
                  detail::Horizon::kSelectedSystem
              ? py::object(py::str(
                    raw_original_entry_mapping_sha256))
              : py::object(py::none());
      pairs.append(std::move(pair));
      ++applied_action_changing_pair_count;
      if (target.horizon ==
          detail::Horizon::kSelectedSystem) {
        ++applied_action_changing_h_system_count;
        if (complete && formal_hard_gate_pass) {
          ++complete_h_system_hard_gate_pass_count;
        }
      } else if (complete) {
        ++complete_action_changing_h_bag_count;
      }
    }
    target_cursor = group_end;
  }

  py::dict payload;
  payload["schema"] = kPairRunSchema;
  payload["evidence_scope"] =
      "EXACT_NATIVE_SAME_STATE_ONE_SHOT_MATCHED_PAIRS";
  payload["formal_pass_claimed"] = false;
  payload["frozen_controls"] =
      detail::frozen_controls_row(research_profile);
  payload["input_request_count"] =
      static_cast<int>(requests.size());
  payload["input_runtime_cohort_sha256"] =
      detail::workload_cohort_sha256(requests);
  payload["target_count"] = static_cast<int>(targets.size());
  payload["action_changing_pair_count"] =
      applied_action_changing_pair_count;
  payload["applied_action_changing_pair_count"] =
      applied_action_changing_pair_count;
  payload["complete_action_changing_h_bag_count"] =
      complete_action_changing_h_bag_count;
  payload["applied_action_changing_h_system_count"] =
      applied_action_changing_h_system_count;
  payload["complete_h_system_hard_gate_pass_count"] =
      complete_h_system_hard_gate_pass_count;
  payload["false_positive_pair_count"] =
      false_positive_pair_count;
  payload["h_system_pair_count"] =
      complete_h_system_hard_gate_pass_count;
  payload["source_events_replayed"] =
      py::int_(source_event_ordinal);
  payload["h_system_cohort_policy"] =
      "ALL_INPUT_RUNTIME_IDS_IN_INPUT_ORDER";
  payload["protected_full_1x_shape"] =
      protected_full_1x_shape;
  payload["h_system_cohort_mapping_sha256"] =
      runtime_mapping_sha256;
  payload["raw_bag_mapping_sha256"] =
      raw_mapping_sha256;
  payload["raw_bag_original_entry_mapping_sha256"] =
      raw_original_entry_mapping_sha256;
  payload["raw_bag_count"] =
      static_cast<int>(raw_mapping.size());
  payload["pairs"] = std::move(pairs);
  return payload;
}

inline void register_causal_campaign_bindings(py::module_& module) {
  module.def(
      "g4irsf15_scan_causal_skeletons_from_records",
      &scan_causal_skeletons_from_records,
      py::arg("node_records"),
      py::arg("edge_records"),
      py::arg("heuristic_time"),
      py::arg("bag_records"),
      py::arg("scorer_w1"),
      py::arg("scorer_b1"),
      py::arg("scorer_w2"),
      py::arg("scorer_b2"),
      py::arg("scorer_risk_margin_threshold"),
      py::arg("scorer_risk_bottleneck_threshold"),
      py::arg("scorer_model_sha256"),
      py::arg("original_entry_times"),
      py::arg("research_profile") =
          std::string("G15_FROZEN"));
  module.def(
      "g4irsf15_materialize_causal_descriptors_from_records",
      &materialize_causal_descriptors_from_records,
      py::arg("node_records"),
      py::arg("edge_records"),
      py::arg("heuristic_time"),
      py::arg("bag_records"),
      py::arg("scorer_w1"),
      py::arg("scorer_b1"),
      py::arg("scorer_w2"),
      py::arg("scorer_b2"),
      py::arg("scorer_risk_margin_threshold"),
      py::arg("scorer_risk_bottleneck_threshold"),
      py::arg("scorer_model_sha256"),
      py::arg("original_entry_times"),
      py::arg("selected_skeletons"),
      py::arg("research_profile") =
          std::string("G15_FROZEN"));
  module.def(
      "g4irsf15_run_causal_target_pairs_from_records",
      &run_causal_target_pairs_from_records,
      py::arg("node_records"),
      py::arg("edge_records"),
      py::arg("heuristic_time"),
      py::arg("bag_records"),
      py::arg("scorer_w1"),
      py::arg("scorer_b1"),
      py::arg("scorer_w2"),
      py::arg("scorer_b2"),
      py::arg("scorer_risk_margin_threshold"),
      py::arg("scorer_risk_bottleneck_threshold"),
      py::arg("scorer_model_sha256"),
      py::arg("original_entry_times"),
      py::arg("target_descriptors"),
      py::arg("research_profile") =
          std::string("G15_FROZEN"));
}

}  // namespace czr005::bindings::g4irsf15
