// Independent CPython3.11.9 data helper. No simulation/state/policy API.
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <cmath>
#include <cstddef>

#if PY_VERSION_HEX != 0x030B09F0
#error "This reviewed prototype is bound to CPython3.11.9 headers."
#endif

namespace {
constexpr Py_ssize_t max_depth = 64;
constexpr Py_ssize_t max_nodes = 2000000;
constexpr Py_ssize_t scan_limit = max_nodes;

class Ref {
 public:
  explicit Ref(PyObject* p = nullptr) noexcept : p_(p) {}
  ~Ref() { Py_XDECREF(p_); }
  Ref(const Ref&) = delete;
  Ref& operator=(const Ref&) = delete;
  PyObject* get() const noexcept { return p_; }
  PyObject* release() noexcept { auto* p = p_; p_ = nullptr; return p; }
  explicit operator bool() const noexcept { return p_ != nullptr; }
 private:
  PyObject* p_;
};

struct ModuleState {
  PyObject* status;
  PyObject* marker;
  PyObject* contract;
  PyObject* resources;
  PyObject* node;
  PyObject* items;
  PyObject* zero;
};

struct Walk {
  ModuleState* constants;
  Py_ssize_t nodes = 0;
  Py_ssize_t scanned_keys = 0;
  PyObject* active[max_depth + 1] = {};
  Py_ssize_t active_size = 0;
  bool unsupported = false;
};

class Active {
 public:
  Active(Walk& walk, PyObject* item) noexcept : walk_(walk) {
    walk_.active[walk_.active_size++] = item;
  }
  ~Active() { --walk_.active_size; }
  Active(const Active&) = delete;
  Active& operator=(const Active&) = delete;
 private:
  Walk& walk_;
};

PyObject* error(const char* reason) {
  PyErr_SetString(PyExc_ValueError, reason);
  return nullptr;
}

PyObject* unsupported(Walk& walk) noexcept {
  walk.unsupported = true;
  return nullptr;
}

bool scalar(PyObject* value) noexcept {
  return PyUnicode_CheckExact(value) || PyLong_CheckExact(value) ||
         PyBool_Check(value) || value == Py_None || PyFloat_CheckExact(value);
}

bool builtin(PyObject* value) noexcept {
  return scalar(value) || PyDict_CheckExact(value) || PyList_CheckExact(value) ||
         PyTuple_CheckExact(value);
}

// No equality/hash/conversion hook on supplied objects is invoked here.
// A bounded extra key inspection is charged to this call. If uncertain, the
// wrapper retries the original normalizer from the untouched input exactly once.
bool safe_keys(Walk& walk, PyObject* dictionary, bool resource_map) {
  Py_ssize_t position = 0;
  PyObject* key = nullptr;
  PyObject* value = nullptr;
  PyTypeObject* first_type = nullptr;
  bool safe = true;
  bool mixed = false;
  while (PyDict_Next(dictionary, &position, &key, &value)) {
    if (++walk.scanned_keys > scan_limit) {
      unsupported(walk);
      return false;
    }
    if (resource_map) {
      if (first_type == nullptr) first_type = Py_TYPE(key);
      else if (first_type != Py_TYPE(key)) mixed = true;
    }
    if (!PyUnicode_CheckExact(key) && !PyLong_CheckExact(key)) safe = false;
  }
  // Original builds the entire set of key TYPES before testing its length.
  // A custom key's metaclass can run __hash__/__eq__ in that set. Even if
  // builtin mixed types occurred first, do not suppress a later custom hook.
  if (!safe) { unsupported(walk); return false; }
  if (mixed) { error("initial_json_v3:mixed_resource_keys"); return false; }
  return true;
}

// Call only after safe_keys. Exact unicode/int keys have no supplied hooks.
PyObject* get(PyObject* dictionary, PyObject* key) {
  return PyDict_GetItemWithError(dictionary, key);  // borrowed, may be absent
}

int same_string(PyObject* a, PyObject* b) {
  const int compared = PyUnicode_Compare(a, b);
  return PyErr_Occurred() ? -1 : compared == 0;
}

bool ascii_decimal(PyObject* value) {
  if (PyUnicode_READY(value) < 0) return false;
  if (!PyUnicode_IS_ASCII(value)) return false;
  const Py_ssize_t length = PyUnicode_GET_LENGTH(value);
  if (length == 0) return false;
  const auto* data = PyUnicode_1BYTE_DATA(value);
  for (Py_ssize_t n = 0; n < length; ++n) {
    if (data[n] < '0' || data[n] > '9') return false;
  }
  return true;
}

PyObject* emitted_resource_key(Walk& walk, PyObject* key) {
  if (PyLong_CheckExact(key)) {
    const int nonnegative = PyObject_RichCompareBool(key, walk.constants->zero, Py_GE);
    if (nonnegative < 0) return nullptr;
    if (!nonnegative) return error("initial_json_v3:resource_key");
    return PyObject_Str(key);  // preserves the configured int-string limit
  }
  if (PyUnicode_CheckExact(key)) {
    if (!ascii_decimal(key)) {
      if (PyErr_Occurred()) return nullptr;
      return error("initial_json_v3:resource_key");
    }
    Ref number(PyLong_FromUnicodeObject(key, 10));
    if (!number) return nullptr;
    Ref canonical(PyObject_Str(number.get()));
    if (!canonical) return nullptr;
    const int same = same_string(canonical.get(), key);
    if (same < 0) return nullptr;
    if (same) return Py_NewRef(key);
  }
  return error("initial_json_v3:resource_key");
}

PyObject* walk_value(Walk& walk, PyObject* item, Py_ssize_t depth, bool resources = false) {
  ++walk.nodes;
  if (depth > max_depth || walk.nodes > max_nodes) return error("initial_json_v3:tree_limit");
  if (PyUnicode_CheckExact(item) || PyLong_CheckExact(item) || PyBool_Check(item) || item == Py_None)
    return Py_NewRef(item);
  if (PyFloat_CheckExact(item)) {
    if (!std::isfinite(PyFloat_AS_DOUBLE(item))) return error("initial_json_v3:nonfinite");
    return Py_NewRef(item);
  }
  // Even the original 'kind in (...)' can invoke a custom metaclass equality
  // hook. All non-exact value types therefore fall back before such a hook.
  if (!PyDict_CheckExact(item) && !PyList_CheckExact(item) && !PyTuple_CheckExact(item))
    return unsupported(walk);
  for (Py_ssize_t i = 0; i < walk.active_size; ++i)
    if (walk.active[i] == item) return error("initial_json_v3:cycle");
  Active active(walk, item);

  if (!PyDict_CheckExact(item)) {
    Ref result(PyList_New(0));
    if (!result) return nullptr;
    Ref iterator(PyObject_GetIter(item));  // exact list/tuple builtin iterator
    if (!iterator) return nullptr;
    while (true) {
      Ref member(PyIter_Next(iterator.get()));
      if (!member) {
        if (PyErr_Occurred()) return nullptr;
        return result.release();
      }
      Ref child(walk_value(walk, member.get(), depth + 1));
      if (!child || PyList_Append(result.get(), child.get()) < 0) return nullptr;
    }
  }

  Ref result(PyDict_New());
  if (!result || !safe_keys(walk, item, resources)) return nullptr;
  auto* status = get(item, walk.constants->status);
  if (PyErr_Occurred()) return nullptr;
  // The Python original compares status BEFORE recursively checking its type.
  // Never execute custom __eq__ then run it again through fallback.
  if (status != nullptr && !builtin(status)) return unsupported(walk);
  bool model_bundle = false;
  if (status != nullptr && PyUnicode_CheckExact(status)) {
    const int is_marker = same_string(status, walk.constants->marker);
    if (is_marker < 0) return nullptr;
    if (is_marker) {
      auto* contract = get(item, walk.constants->contract);
      if (PyErr_Occurred()) return nullptr;
      if (contract != nullptr && PyDict_CheckExact(contract)) {
        auto* map = get(item, walk.constants->resources);
        if (PyErr_Occurred()) return nullptr;
        model_bundle = map != nullptr && PyDict_CheckExact(map);
      }
    }
  }
  Ref items(PyObject_CallMethodNoArgs(item, walk.constants->items));
  if (!items) return nullptr;
  Ref iterator(PyObject_GetIter(items.get()));  // original dict.items order/mutation guard
  if (!iterator) return nullptr;
  while (true) {
    Ref pair(PyIter_Next(iterator.get()));
    if (!pair) {
      if (PyErr_Occurred()) return nullptr;
      return result.release();
    }
    auto* key = PyTuple_GET_ITEM(pair.get(), 0);
    auto* member = PyTuple_GET_ITEM(pair.get(), 1);
    Ref emitted(resources ? emitted_resource_key(walk, key) :
        PyUnicode_CheckExact(key) ? Py_NewRef(key) : error("initial_json_v3:non_string_key"));
    if (!emitted) return nullptr;
    if (resources) {
      if (!PyDict_CheckExact(member)) return error("initial_json_v3:resource_identity");
      if (!safe_keys(walk, member, false)) return nullptr;
      auto* node = get(member, walk.constants->node);
      if (PyErr_Occurred()) return nullptr;
      if (node == nullptr || !PyLong_CheckExact(node)) return error("initial_json_v3:resource_identity");
      Ref identity(PyLong_FromUnicodeObject(emitted.get(), 10));
      if (!identity) return nullptr;
      const int same = PyObject_RichCompareBool(node, identity.get(), Py_EQ);
      if (same < 0) return nullptr;
      if (!same) return error("initial_json_v3:resource_identity");
    }
    const int duplicate = PyDict_Contains(result.get(), emitted.get());
    if (duplicate < 0) return nullptr;
    if (duplicate) return error("initial_json_v3:key_collision");
    Ref counted_key(walk_value(walk, emitted.get(), depth + 1));
    if (!counted_key) return nullptr;
    bool nested_resources = false;
    if (model_bundle && PyUnicode_CheckExact(key)) {
      const int matched = same_string(key, walk.constants->resources);
      if (matched < 0) return nullptr;
      nested_resources = matched != 0;
    }
    Ref child(walk_value(walk, member, depth + 1, nested_resources));
    if (!child || PyDict_SetItem(result.get(), emitted.get(), child.get()) < 0) return nullptr;
  }
}

PyObject* try_normalize(PyObject* module, PyObject* value) {
  // This non-limited-ABI prototype is pinned to the inspected3.11.9 struct.
  // Under recursion pressure use the original Python path, not a new extended
  // recursion domain. No request object is inspected before this decision.
  if (PyThreadState_Get()->recursion_remaining < 4 * max_depth + 64) Py_RETURN_NOTIMPLEMENTED;
  Walk walk{static_cast<ModuleState*>(PyModule_GetState(module))};
  auto* result = walk_value(walk, value, 0);
  if (walk.unsupported && !PyErr_Occurred()) Py_RETURN_NOTIMPLEMENTED;
  return result;
}

PyObject* contract(PyObject*, PyObject*) {
  return Py_BuildValue("{s:s,s:i,s:i,s:i,s:s,s:O}",
      "schema", "g31.complete_tree_normalizer.candidate.v1",
      "max_depth", static_cast<int>(max_depth), "max_nodes", static_cast<int>(max_nodes),
      "key_scan_limit", static_cast<int>(scan_limit), "headers_python", PY_VERSION,
      "native_simulation_authority", Py_False);
}

int traverse(PyObject* module, visitproc visit, void* arg) {
  auto* state = static_cast<ModuleState*>(PyModule_GetState(module));
  Py_VISIT(state->status); Py_VISIT(state->marker); Py_VISIT(state->contract);
  Py_VISIT(state->resources); Py_VISIT(state->node); Py_VISIT(state->items); Py_VISIT(state->zero);
  return 0;
}

int clear(PyObject* module) {
  auto* state = static_cast<ModuleState*>(PyModule_GetState(module));
  Py_CLEAR(state->status); Py_CLEAR(state->marker); Py_CLEAR(state->contract);
  Py_CLEAR(state->resources); Py_CLEAR(state->node); Py_CLEAR(state->items); Py_CLEAR(state->zero);
  return 0;
}

void free_module(void* module) { (void)clear(static_cast<PyObject*>(module)); }

PyMethodDef methods[] = {
    {"try_normalize", try_normalize, METH_O, "Fresh exact builtin tree, or NotImplemented before supplied hooks."},
    {"contract", contract, METH_NOARGS, "Return data-only ABI/domain metadata; not runtime acceptance."},
    {nullptr, nullptr, 0, nullptr}};

PyModuleDef definition = {PyModuleDef_HEAD_INIT, "_g31_complete_tree_normalizer",
    "Independent data-only normalization prototype.", sizeof(ModuleState), methods,
    nullptr, traverse, clear, free_module};
}  // namespace

PyMODINIT_FUNC PyInit__g31_complete_tree_normalizer() {
  Ref module(PyModule_Create(&definition));
  if (!module) return nullptr;
  auto* state = static_cast<ModuleState*>(PyModule_GetState(module.get()));
  state->status = PyUnicode_InternFromString("status");
  state->marker = PyUnicode_InternFromString("conditional_model_input");
  state->contract = PyUnicode_InternFromString("contract");
  state->resources = PyUnicode_InternFromString("resources");
  state->node = PyUnicode_InternFromString("node");
  state->items = PyUnicode_InternFromString("items");
  state->zero = PyLong_FromLong(0);
  if (!state->status || !state->marker || !state->contract || !state->resources ||
      !state->node || !state->items || !state->zero) return nullptr;
  return module.release();
}
