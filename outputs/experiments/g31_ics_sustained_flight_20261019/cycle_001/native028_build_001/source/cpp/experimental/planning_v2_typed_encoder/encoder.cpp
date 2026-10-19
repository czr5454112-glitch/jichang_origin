// Experimental data-only encoder. Source draft: not built or runtime accepted.
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <climits>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include <limits>
#include <new>
#include <stdexcept>
#include <vector>

#if PY_VERSION_HEX != 0x030B09F0
#error "This prototype requires the pinned CPython3.11.9 headers."
#endif
static_assert(CHAR_BIT == 8 && sizeof(unsigned long long) == 8);
static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559);

namespace {
#define FIELDS(X) \
 X(schema) X(local_capture) X(extension) X(message_id) X(source_owner) X(target_owner) \
 X(publication_sequence) X(captured_at) X(valid_until) X(static_contract_sha256) \
 X(semantics) X(queue_discipline) X(resource_semantics) X(event_semantics) X(scorer_mode) \
 X(merge_grant_rule) X(merge_grant_timing_mode) X(minimum_service_seconds) X(jobs) \
 X(business_bag_id) X(origin) X(destination) X(arrival) X(deadline) X(storage_node) \
 X(storage_release_at) X(storage_min_dwell) X(load_seconds) X(unload_seconds) X(hold_seconds) \
 X(protected_service) X(allow_suffix_reroute) X(status) X(loaded_at) X(storage_entered_at) \
 X(storage_released_at) X(trays) X(tray_id) X(mode) X(ready_kind) X(node) X(edge_from) \
 X(edge_to) X(reception_node) X(generation) X(traversal_id) X(available_at) \
 X(service_ready_at) X(load_complete_at) X(service_ready_known) X(committed_prefix) \
 X(nodes) X(occupancy) X(actual_available) X(unrepresented_occupancy) X(known_faults) \
 X(from) X(to) X(active) X(received_at) X(coverage) X(scope) \
 X(complete_for_declared_local_scope) X(local_node_ids) X(tray_ids) X(business_bag_ids) \
 X(future_arrivals_included) X(terminal_receipts) X(receipt_id) X(source_local_sequence) \
 X(event) X(completed_at) X(completion_coverage) X(complete_for_declared_scope) X(through) \
 X(source_owned_destination_nodes) X(future_events_included) X(completed_business_bag_ids) \
 X(submitted_physical_actions) X(request_id) X(kind) X(last_delivered_ack) X(sequence) \
 X(delivered_at) X(action_coverage) X(includes_unsubmitted_python_plans) \
 X(uses_hidden_execution_truth) X(submitted_request_ids) X(unresolved_request_ids)
#define ENUM_FIELD(name) k_##name,
enum Key { FIELDS(ENUM_FIELD) k_count };
#undef ENUM_FIELD
#define NAME_FIELD(name) #name,
constexpr const char* names[] = { FIELDS(NAME_FIELD) };
#undef NAME_FIELD
#undef FIELDS
static_assert(sizeof(names) / sizeof(names[0]) == k_count);

struct State { PyObject* keys[k_count]; };
class Ref {
 public:
  explicit Ref(PyObject* p) noexcept : value_(p) {}
  ~Ref() { Py_XDECREF(value_); }
  Ref(const Ref&) = delete;
  Ref& operator=(const Ref&) = delete;
  PyObject* get() const noexcept { return value_; }
  explicit operator bool() const noexcept { return value_ != nullptr; }
 private:
  PyObject* value_;
};

class Writer {
 public:
  explicit Writer(State* state) : state_(state) {}
  bool unsupported = false;
  std::vector<unsigned char> bytes;

  bool unknown() noexcept { unsupported = true; return false; }
  bool append(const void* p, std::size_t count) {
    if (count > static_cast<std::size_t>(PY_SSIZE_T_MAX) - bytes.size()) {
      PyErr_SetString(PyExc_OverflowError, "typed_v2:buffer_size"); return false;
    }
    const auto* first = static_cast<const unsigned char*>(p);
    if (count != 0) bytes.insert(bytes.end(), first, first + count);
    return true;
  }
  bool u64(std::uint64_t value) {
    unsigned char scratch[8];
    for (unsigned i = 0; i != 8; ++i) scratch[i] = static_cast<unsigned char>(value >> (56 - 8 * i));
    return append(scratch, 8);
  }
  bool flag(bool value) {
    const unsigned char b = value ? 1 : 0; return append(&b, 1);
  }
  bool literal(const char* value) {
    const std::size_t count = std::strlen(value);
    return u64(static_cast<std::uint64_t>(count)) && append(value, count);
  }
  bool mapping(PyObject* value) {
    if (!PyDict_CheckExact(value)) return unknown();
    // Stored custom keys can run __eq__ during even an exact-dict lookup.
    // Inspect every key TYPE first, without hashing/comparing supplied objects.
    Py_ssize_t position = 0; PyObject* key = nullptr; PyObject* member = nullptr;
    while (PyDict_Next(value, &position, &key, &member))
      if (!PyUnicode_CheckExact(key)) return unknown();
    return true;
  }
  PyObject* field(PyObject* dictionary, Key key) {
    auto* value = PyDict_GetItemWithError(dictionary, state_->keys[key]);
    if (value == nullptr && !PyErr_Occurred()) unsupported = true;
    return value;  // borrowed; caller retains the complete stable input
  }
  PyObject* object(PyObject* dictionary, Key key) {
    auto* value = field(dictionary, key);
    return value != nullptr && mapping(value) ? value : nullptr;
  }
  PyObject* array(PyObject* dictionary, Key key) {
    auto* value = field(dictionary, key);
    if (value == nullptr) return nullptr;
    if (!PyList_CheckExact(value)) { unknown(); return nullptr; }
    return u64(static_cast<std::uint64_t>(PyList_GET_SIZE(value))) ? value : nullptr;
  }
  bool text(PyObject* value) {
    if (!PyUnicode_CheckExact(value)) return unknown();
    Ref encoded(PyUnicode_AsUTF8String(value));
    if (!encoded) return false;  // strict Unicode failure; NEVER fallback
    const Py_ssize_t count = PyBytes_GET_SIZE(encoded.get());
    return u64(static_cast<std::uint64_t>(count)) &&
      append(PyBytes_AS_STRING(encoded.get()), static_cast<std::size_t>(count));
  }
  bool integer(PyObject* value) {
    if (!PyLong_CheckExact(value) && !PyBool_Check(value)) return unknown();
    const auto number = PyLong_AsUnsignedLongLongMask(value);
    if (PyErr_Occurred()) return false;
    return u64(static_cast<std::uint64_t>(number));
  }
  bool floating(PyObject* value) {
    double number;
    if (PyFloat_CheckExact(value)) number = PyFloat_AS_DOUBLE(value);
    else if (PyBool_Check(value)) number = value == Py_True ? 1.0 : 0.0;
    else if (PyLong_CheckExact(value)) {
      int overflow = 0;
      (void)PyLong_AsLongLongAndOverflow(value, &overflow);
      if (PyErr_Occurred()) return false;
      if (overflow) return unknown();  // original struct decides huge-int error
      number = PyLong_AsDouble(value);
      if (PyErr_Occurred()) return false;
    } else return unknown();
    char scratch[8];
    // Same routine used by CPython3.11.9 _struct.bp_double (>d).
    if (PyFloat_Pack8(number, scratch, 0) < 0) return false;
    return append(scratch, 8);  // NaN, infinity and signed zero are not rejected
  }
  bool boolean(PyObject* value) {
    return PyBool_Check(value) ? flag(value == Py_True) : unknown();
  }
  using Primitive = bool (Writer::*)(PyObject*);
  bool fields(PyObject* dictionary, Primitive primitive, std::initializer_list<Key> keys) {
    for (Key key : keys) {
      auto* value = field(dictionary, key);
      if (value == nullptr || !(this->*primitive)(value)) return false;
    }
    return true;
  }
  bool list(PyObject* dictionary, Key key, Primitive primitive) {
    auto* values = array(dictionary, key);
    if (values == nullptr) return false;
    const Py_ssize_t size = PyList_GET_SIZE(values);
    for (Py_ssize_t i = 0; i != size; ++i)
      if (!(this->*primitive)(PyList_GET_ITEM(values, i))) return false;
    return true;
  }

  bool local(PyObject* body) {
    if (!mapping(body) || !fields(body, &Writer::text, {k_schema,k_message_id,k_source_owner,k_target_owner}) ||
        !fields(body, &Writer::integer, {k_publication_sequence}) ||
        !fields(body, &Writer::floating, {k_captured_at,k_valid_until}) ||
        !fields(body, &Writer::text, {k_static_contract_sha256})) return false;
    auto* semantics = object(body, k_semantics);
    if (semantics == nullptr || !fields(semantics, &Writer::text, {k_queue_discipline,k_resource_semantics,
        k_event_semantics,k_scorer_mode,k_merge_grant_rule,k_merge_grant_timing_mode}) ||
        !fields(semantics, &Writer::floating, {k_minimum_service_seconds})) return false;
    auto* jobs = array(body, k_jobs);
    if (jobs == nullptr) return false;
    for (Py_ssize_t i = 0, size = PyList_GET_SIZE(jobs); i != size; ++i) {
      auto* job = PyList_GET_ITEM(jobs, i);
      if (!mapping(job) || !fields(job, &Writer::text, {k_business_bag_id}) ||
          !fields(job, &Writer::integer, {k_origin,k_destination}) ||
          !fields(job, &Writer::floating, {k_arrival,k_deadline}) ||
          !fields(job, &Writer::integer, {k_storage_node}) ||
          !fields(job, &Writer::floating, {k_storage_release_at,k_storage_min_dwell,k_load_seconds,k_unload_seconds,k_hold_seconds}) ||
          !fields(job, &Writer::boolean, {k_protected_service,k_allow_suffix_reroute}) ||
          !fields(job, &Writer::text, {k_status}) ||
          !fields(job, &Writer::floating, {k_loaded_at,k_storage_entered_at,k_storage_released_at})) return false;
    }
    auto* trays = array(body, k_trays);
    if (trays == nullptr) return false;
    for (Py_ssize_t i = 0, size = PyList_GET_SIZE(trays); i != size; ++i) {
      auto* tray = PyList_GET_ITEM(trays, i);
      if (!mapping(tray) || !fields(tray, &Writer::text, {k_tray_id,k_business_bag_id,k_mode,k_ready_kind}) ||
          !fields(tray, &Writer::integer, {k_node,k_edge_from,k_edge_to,k_reception_node,k_generation,k_traversal_id}) ||
          !fields(tray, &Writer::floating, {k_available_at,k_service_ready_at,k_load_complete_at}) ||
          !fields(tray, &Writer::boolean, {k_service_ready_known}) ||
          !list(tray, k_committed_prefix, &Writer::integer)) return false;
    }
    auto* nodes = array(body, k_nodes);
    if (nodes == nullptr) return false;
    for (Py_ssize_t i = 0, size = PyList_GET_SIZE(nodes); i != size; ++i) {
      auto* node = PyList_GET_ITEM(nodes, i);
      if (!mapping(node) || !fields(node, &Writer::integer, {k_node,k_occupancy,k_actual_available,k_unrepresented_occupancy})) return false;
    }
    auto* faults = array(body, k_known_faults);
    if (faults == nullptr) return false;
    for (Py_ssize_t i = 0, size = PyList_GET_SIZE(faults); i != size; ++i) {
      auto* fault = PyList_GET_ITEM(faults, i);
      if (!mapping(fault) || !fields(fault, &Writer::integer, {k_from,k_to}) ||
          !fields(fault, &Writer::boolean, {k_active}) || !fields(fault, &Writer::floating, {k_received_at})) return false;
    }
    auto* coverage = object(body, k_coverage);
    return coverage != nullptr && fields(coverage, &Writer::text, {k_scope}) &&
      fields(coverage, &Writer::boolean, {k_complete_for_declared_local_scope}) &&
      list(coverage, k_local_node_ids, &Writer::integer) && list(coverage, k_tray_ids, &Writer::text) &&
      list(coverage, k_business_bag_ids, &Writer::text) &&
      fields(coverage, &Writer::integer, {k_unrepresented_occupancy}) &&
      fields(coverage, &Writer::boolean, {k_future_arrivals_included});
  }

  bool encode(PyObject* body) {
    if (!mapping(body) || !literal("czr005.g4irsf14.runtime-state-component.v2") ||
        !literal("g31.planning_capture_digest.v2") || !fields(body, &Writer::text, {k_schema})) return false;
    auto* captured = field(body, k_local_capture);
    if (captured == nullptr || !local(captured)) return false;
    auto* extension = object(body, k_extension);
    if (extension == nullptr || !fields(extension, &Writer::text, {k_schema,k_source_owner}) ||
        !fields(extension, &Writer::floating, {k_captured_at})) return false;
    auto* receipts = array(extension, k_terminal_receipts);
    if (receipts == nullptr) return false;
    for (Py_ssize_t i = 0, size = PyList_GET_SIZE(receipts); i != size; ++i) {
      auto* receipt = PyList_GET_ITEM(receipts, i);
      if (!mapping(receipt) || !fields(receipt, &Writer::text, {k_receipt_id}) ||
          !fields(receipt, &Writer::integer, {k_source_local_sequence}) ||
          !fields(receipt, &Writer::text, {k_source_owner,k_event,k_status,k_business_bag_id}) ||
          !fields(receipt, &Writer::integer, {k_destination}) ||
          !fields(receipt, &Writer::text, {k_tray_id}) || !fields(receipt, &Writer::floating, {k_completed_at})) return false;
    }
    auto* completion = object(extension, k_completion_coverage);
    if (completion == nullptr || !fields(completion, &Writer::text, {k_scope}) ||
        !fields(completion, &Writer::boolean, {k_complete_for_declared_scope}) ||
        !fields(completion, &Writer::floating, {k_through}) ||
        !list(completion, k_source_owned_destination_nodes, &Writer::integer) ||
        !fields(completion, &Writer::boolean, {k_future_events_included}) ||
        !list(completion, k_completed_business_bag_ids, &Writer::text)) return false;
    auto* actions = array(extension, k_submitted_physical_actions);
    if (actions == nullptr) return false;
    for (Py_ssize_t i = 0, size = PyList_GET_SIZE(actions); i != size; ++i) {
      auto* action = PyList_GET_ITEM(actions, i);
      if (!mapping(action) || !fields(action, &Writer::text, {k_request_id,k_kind,k_source_owner})) return false;
      auto* ack = field(action, k_last_delivered_ack);
      if (ack == nullptr || !flag(ack != Py_None)) return false;
      if (ack != Py_None && (!mapping(ack) || !fields(ack, &Writer::integer, {k_sequence}) ||
          !fields(ack, &Writer::floating, {k_delivered_at}) || !fields(ack, &Writer::text, {k_status}))) return false;
    }
    auto* coverage = object(extension, k_action_coverage);
    return coverage != nullptr && fields(coverage, &Writer::text, {k_scope}) &&
      fields(coverage, &Writer::floating, {k_through}) &&
      fields(coverage, &Writer::boolean, {k_complete_for_declared_scope,k_includes_unsubmitted_python_plans,k_uses_hidden_execution_truth}) &&
      list(coverage, k_submitted_request_ids, &Writer::text) && list(coverage, k_unresolved_request_ids, &Writer::text);
  }
 private:
  State* state_;
};

PyObject* try_typed_bytes(PyObject* module, PyObject* body) {
  try {
    Writer writer(static_cast<State*>(PyModule_GetState(module)));
    if (!writer.encode(body)) {
      if (writer.unsupported && !PyErr_Occurred()) Py_RETURN_NOTIMPLEMENTED;
      if (!PyErr_Occurred()) PyErr_SetString(PyExc_RuntimeError, "typed_v2:unclassified_failure");
      return nullptr;
    }
    return PyBytes_FromStringAndSize(reinterpret_cast<const char*>(writer.bytes.data()),
                                   static_cast<Py_ssize_t>(writer.bytes.size()));
  } catch (const std::bad_alloc&) {
    return PyErr_NoMemory();
  } catch (const std::length_error&) {
    PyErr_SetString(PyExc_OverflowError, "typed_v2:buffer_capacity"); return nullptr;
  } catch (...) {
    PyErr_SetString(PyExc_RuntimeError, "typed_v2:unexpected_C_exception"); return nullptr;
  }
}

PyObject* contract(PyObject*, PyObject*) {
  return Py_BuildValue("{s:s,s:s,s:s,s:i,s:O,s:O}",
    "schema", "g31.planning_v2.typed_encoder.candidate.v1",
    "headers_python", PY_VERSION,
    "original_writer_sha256", "01fc49cbded5ba70851f1294fce9f5aaa06b66e82bfb5b9862740c310faf9fd5",
    "uint64_bits", 64, "stable_input_required", Py_True,
    "native_simulation_authority", Py_False);
}
int traverse(PyObject* module, visitproc visit, void* arg) {
  auto* state = static_cast<State*>(PyModule_GetState(module));
  for (auto* key : state->keys) Py_VISIT(key);
  return 0;
}
int clear(PyObject* module) {
  auto* state = static_cast<State*>(PyModule_GetState(module));
  for (auto*& key : state->keys) Py_CLEAR(key);
  return 0;
}
void free_module(void* module) { (void)clear(static_cast<PyObject*>(module)); }
PyMethodDef methods[] = {
  {"try_typed_bytes", try_typed_bytes, METH_O, "Fresh exact typed bytes, or hook-free NotImplemented."},
  {"contract", contract, METH_NOARGS, "Data-only ABI/domain declaration, not runtime acceptance."},
  {nullptr, nullptr, 0, nullptr}};
PyModuleDef definition = {PyModuleDef_HEAD_INIT, "_g31_planning_v2_typed_encoder",
  "Independent data-only typed encoder.", sizeof(State), methods, nullptr, traverse, clear, free_module};
}  // namespace

PyMODINIT_FUNC PyInit__g31_planning_v2_typed_encoder() {
  auto* module = PyModule_Create(&definition);
  if (module == nullptr) return nullptr;
  auto* state = static_cast<State*>(PyModule_GetState(module));
  for (int i = 0; i != k_count; ++i) {
    state->keys[i] = PyUnicode_InternFromString(names[i]);
    if (state->keys[i] == nullptr) { Py_DECREF(module); return nullptr; }
  }
  return module;
}
