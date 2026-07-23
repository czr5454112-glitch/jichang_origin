cmake_minimum_required(VERSION 3.20)
project(czr005 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

enable_testing()

option(CZR005_BUILD_PYBIND "Build Python bindings with pybind11" ON)

add_library(ics_core INTERFACE)
target_include_directories(ics_core INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/cpp)

add_executable(test_cpp_core_smoke cpp/tests/test_cpp_core_smoke.cpp)
target_link_libraries(test_cpp_core_smoke PRIVATE ics_core)
target_compile_definitions(test_cpp_core_smoke PRIVATE CZR005_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")
add_test(NAME cpp_core_smoke COMMAND test_cpp_core_smoke)

add_executable(test_event_driven_junction cpp/tests/test_event_driven_junction.cpp)
target_link_libraries(test_event_driven_junction PRIVATE ics_core)
target_compile_definitions(test_event_driven_junction PRIVATE CZR005_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")
add_test(NAME event_driven_junction COMMAND test_event_driven_junction)

add_executable(test_g4irsf12_runtime_controls cpp/tests/test_g4irsf12_runtime_controls.cpp)
target_link_libraries(test_g4irsf12_runtime_controls PRIVATE ics_core)
target_compile_definitions(
  test_g4irsf12_runtime_controls
  PRIVATE CZR005_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")
add_test(NAME g4irsf12_runtime_controls COMMAND test_g4irsf12_runtime_controls)

add_executable(
  test_bounded_local_pibt_real_map
  cpp/tests/test_bounded_local_pibt_real_map.cpp)
target_link_libraries(test_bounded_local_pibt_real_map PRIVATE ics_core)
target_compile_definitions(
  test_bounded_local_pibt_real_map
  PRIVATE CZR005_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")
add_test(NAME bounded_local_pibt_real_map COMMAND test_bounded_local_pibt_real_map)

add_executable(
  test_event_runtime_bounded_local_pibt
  cpp/tests/test_event_runtime_bounded_local_pibt.cpp)
target_link_libraries(test_event_runtime_bounded_local_pibt PRIVATE ics_core)
target_compile_definitions(
  test_event_runtime_bounded_local_pibt
  PRIVATE CZR005_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")
add_test(
  NAME event_runtime_bounded_local_pibt
  COMMAND test_event_runtime_bounded_local_pibt)

add_executable(
  test_expiring_first_edge_credit_real_map
  cpp/tests/test_expiring_first_edge_credit_real_map.cpp)
target_link_libraries(test_expiring_first_edge_credit_real_map PRIVATE ics_core)
target_compile_definitions(
  test_expiring_first_edge_credit_real_map
  PRIVATE CZR005_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")
add_test(
  NAME expiring_first_edge_credit_real_map
  COMMAND test_expiring_first_edge_credit_real_map)

if(CZR005_BUILD_PYBIND)
  find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
  find_package(pybind11 CONFIG REQUIRED)

  pybind11_add_module(czr005_cpp cpp/ics_core/bindings/czr005_cpp.cpp)
  target_link_libraries(czr005_cpp PRIVATE ics_core)
  set_target_properties(
    czr005_cpp
    PROPERTIES
      LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/python
      RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/python
      ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/python)

  add_test(
    NAME pybind_smoke
    COMMAND
      ${CMAKE_COMMAND} -E env
      "PYTHONPATH=$<TARGET_FILE_DIR:czr005_cpp>"
      ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/cpp/tests/test_pybind_smoke.py)
  set_tests_properties(pybind_smoke PROPERTIES DEPENDS czr005_cpp)
endif()
