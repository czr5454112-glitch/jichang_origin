cmake_minimum_required(VERSION 3.20)
project(g31_complete_tree_normalizer LANGUAGES CXX)

# Independent data-only extension. Do not add_subdirectory this from the
# simulation project and do not link either native circulation library.
find_package(Python3 3.11.9 EXACT COMPONENTS Interpreter Development.Module REQUIRED)
Python3_add_library(_g31_complete_tree_normalizer MODULE WITH_SOABI normalizer.cpp)
target_compile_features(_g31_complete_tree_normalizer PRIVATE cxx_std_17)
set_target_properties(_g31_complete_tree_normalizer PROPERTIES
  CXX_EXTENSIONS OFF
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/python"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/python")
if(MSVC)
  target_compile_options(_g31_complete_tree_normalizer PRIVATE /W4 /WX /Brepro)
  target_link_options(_g31_complete_tree_normalizer PRIVATE /Brepro)
else()
  target_compile_options(_g31_complete_tree_normalizer PRIVATE -Wall -Wextra -Werror)
endif()
