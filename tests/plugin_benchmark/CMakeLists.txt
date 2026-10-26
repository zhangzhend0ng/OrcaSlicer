# Bounded NumPy bulk / sustained-lifecycle benchmark, absorbed from the women
# fork (tests/plugin_benchmark @0aa325e101). Only the self-contained bulk
# target is taken; women's main.cpp harness (TextureDisplacementConsumer
# fixture) is not (ledger). The target is EXCLUDE_FROM_ALL exactly as in the
# women tree: a benchmark binary must be built and invoked on demand through
# scripts/benchmark_plugin_bulk.py, which also requires an offline wheelhouse
# holding numpy-2.2.6 — it is deliberately NOT part of the default gates.
if (NOT SLIC3R_GUI)
    return()
endif()

add_executable(orca_plugin_bulk_benchmark EXCLUDE_FROM_ALL
    bulk_main.cpp
    ${PROJECT_SOURCE_DIR}/src/common_func/common_func.cpp
    ${PROJECT_SOURCE_DIR}/src/bury_cfg/bury_point.cpp
    ${PROJECT_SOURCE_DIR}/src/sentry_wrapper/SentryWrapper.cpp
    ${PROJECT_SOURCE_DIR}/src/dev-utils/BaseException.cpp
    ${PROJECT_SOURCE_DIR}/src/dev-utils/StackWalker.cpp)
target_compile_definitions(orca_plugin_bulk_benchmark PRIVATE PYBIND11_SIMPLE_GIL_MANAGEMENT BURY_EXPORTS)
target_include_directories(orca_plugin_bulk_benchmark PRIVATE
    ${PROJECT_SOURCE_DIR}/src
    ${PROJECT_SOURCE_DIR}/src/slic3r
    ${PROJECT_SOURCE_DIR}/src/sentry_wrapper
    ${wxWidgets_INCLUDE_DIRS})
if (WIN32 AND wxWidgets_LIB_DIR AND wxWidgets_CONFIGURATION)
    target_include_directories(orca_plugin_bulk_benchmark PRIVATE
        "${wxWidgets_LIB_DIR}/${wxWidgets_CONFIGURATION}")
endif ()
target_link_libraries(orca_plugin_bulk_benchmark PRIVATE libslic3r_gui pybind11::embed)
target_compile_features(orca_plugin_bulk_benchmark PRIVATE cxx_std_17)
set_property(TARGET orca_plugin_bulk_benchmark PROPERTY FOLDER "tests")
if (WIN32)
    target_link_libraries(orca_plugin_bulk_benchmark PRIVATE Psapi)
    # Same per-target staging as orca_plugin_core_runner_extras (kept local here
    # to avoid moving the shared function out of the green plugin_core suite):
    # pinned output directory, DLL pool, bundled python + uv.
    set_target_properties(orca_plugin_bulk_benchmark PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/orca_plugin_bulk_benchmark"
        RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_CURRENT_BINARY_DIR}/orca_plugin_bulk_benchmark"
        RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_BINARY_DIR}/orca_plugin_bulk_benchmark"
        RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL "${CMAKE_CURRENT_BINARY_DIR}/orca_plugin_bulk_benchmark"
        RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO "${CMAKE_CURRENT_BINARY_DIR}/orca_plugin_bulk_benchmark")
    add_custom_command(TARGET orca_plugin_bulk_benchmark POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${CMAKE_CURRENT_BINARY_DIR}/../plugin_core/Release" "$<TARGET_FILE_DIR:orca_plugin_bulk_benchmark>"
        COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:orca_plugin_bulk_benchmark>/python"
        COMMAND ${CMAKE_COMMAND} -E copy_directory "${CMAKE_PREFIX_PATH}/libpython" "$<TARGET_FILE_DIR:orca_plugin_bulk_benchmark>/python"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_PREFIX_PATH}/libpython/python${_bundled_python_abi}.dll"
            "${CMAKE_PREFIX_PATH}/libpython/vcruntime140.dll"
            "${CMAKE_PREFIX_PATH}/libpython/vcruntime140_1.dll"
            "$<TARGET_FILE_DIR:orca_plugin_bulk_benchmark>"
        COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:orca_plugin_bulk_benchmark>/tools/uv"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${ORCA_BUNDLED_UV_EXECUTABLE}" "$<TARGET_FILE_DIR:orca_plugin_bulk_benchmark>/tools/uv/${ORCA_BUNDLED_UV_FILENAME}"
        COMMENT "Copying Python runtime and uv for orca_plugin_bulk_benchmark"
        VERBATIM)
endif()

# The pure-python driver contracts (wheel determinism, RECORD checksums,
# aggregation invariants) run without the native host or numpy.
find_package(Python3 COMPONENTS Interpreter)
if (Python3_Interpreter_FOUND)
    add_test(NAME plugin_benchmark:bulk_tools
        COMMAND ${Python3_EXECUTABLE} -m unittest discover -s "${PROJECT_SOURCE_DIR}/scripts" -p "test_plugin_bulk_tools.py" -t "${PROJECT_SOURCE_DIR}/scripts")
    set_tests_properties(plugin_benchmark:bulk_tools PROPERTIES TIMEOUT 120)
endif()
