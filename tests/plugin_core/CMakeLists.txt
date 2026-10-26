# Engineering-axis regression runners absorbed from the women fork (0aa325e101):
# isolated processes exercising the real install/dependency transaction
# infrastructure (PluginFileLock / PluginDependencyInstaller / wheel cache).
# The C++ scenario runners are kept verbatim; the python orchestrators in
# scripts/ (test_plugin_*.py) drive them and build their own fixtures.
if (NOT SLIC3R_GUI)
    return()
endif()

# The lock contract is a plain standalone binary with no plugin runtime.
add_executable(orca_plugin_lock_test file_lock.cpp)
target_include_directories(orca_plugin_lock_test PRIVATE ${PROJECT_SOURCE_DIR}/src)
target_compile_features(orca_plugin_lock_test PRIVATE cxx_std_17)
set_property(TARGET orca_plugin_lock_test PROPERTY FOLDER "tests")

# libslic3r_gui references symbols implemented in the app DLL's private TUs;
# every runner that links it resolves them the same way slic3rutils_tests and
# orca_stubgen do (compile the defining sources straight in).
set(_plugin_core_private_tus
    ${PROJECT_SOURCE_DIR}/src/common_func/common_func.cpp
    ${PROJECT_SOURCE_DIR}/src/bury_cfg/bury_point.cpp
    ${PROJECT_SOURCE_DIR}/src/sentry_wrapper/SentryWrapper.cpp
    ${PROJECT_SOURCE_DIR}/src/dev-utils/BaseException.cpp
    ${PROJECT_SOURCE_DIR}/src/dev-utils/StackWalker.cpp
)

if (WIN32)
    # Fills the shared DLL pool at ${CMAKE_CURRENT_BINARY_DIR}/Release once at
    # configure time; the pinned per-runner directories pull it in via POST_BUILD.
    Snapmaker_Orca_copy_dlls(COPY_DLLS "Release" "" _plugin_core_dll_pool)
endif()

# Bundled python + uv laid out next to the runner exactly like the app layout
# (bundled_uv_path() probes <exe>/tools/uv, find_bundled_python_home() <exe>/python).
# Each runner gets its own output directory: the POST_BUILD staging below copies
# the python tree into the exe dir, and parallel builds of two runners into one
# shared directory race on those copies.
function(orca_plugin_core_runner_extras target)
    target_compile_definitions(${target} PRIVATE PYBIND11_SIMPLE_GIL_MANAGEMENT BURY_EXPORTS)
    target_include_directories(${target} PRIVATE
        ${PROJECT_SOURCE_DIR}/src
        ${PROJECT_SOURCE_DIR}/src/slic3r
        ${PROJECT_SOURCE_DIR}/src/sentry_wrapper
        # The wait/overlap/observer runners drive the real wx console queue
        # (<wx/app.h>); the others never include wx headers. Same two-part wx
        # include setup as tests/slic3rutils (setup.h lives under
        # LIB_DIR/CONFIGURATION, not the base include dir).
        ${wxWidgets_INCLUDE_DIRS}
    )
    if (WIN32 AND wxWidgets_LIB_DIR AND wxWidgets_CONFIGURATION)
        target_include_directories(${target} PRIVATE
            "${wxWidgets_LIB_DIR}/${wxWidgets_CONFIGURATION}")
    endif ()
    target_link_libraries(${target} PRIVATE libslic3r_gui pybind11::embed)
    # Pin every config variant: with only the plain property the VS multi-config
    # generator appends \Release under it while copy_dlls() stages into the plain
    # property, splitting the exe from its DLLs across two directories.
    set_target_properties(${target} PROPERTIES
        FOLDER "tests"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/${target}"
        RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_CURRENT_BINARY_DIR}/${target}"
        RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_BINARY_DIR}/${target}"
        RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL "${CMAKE_CURRENT_BINARY_DIR}/${target}"
        RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO "${CMAKE_CURRENT_BINARY_DIR}/${target}")
    if (WIN32)
        # Snapmaker_Orca_copy_dlls() always stages into <calling-dir>/<config>
        # (its first argument is a mode token, not a target name), so the DLL
        # pool lands in the shared Release/ below; each pinned runner directory
        # pulls the pool in via POST_BUILD before the python staging.
        add_custom_command(TARGET ${target} POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${CMAKE_CURRENT_BINARY_DIR}/Release" "$<TARGET_FILE_DIR:${target}>"
            COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:${target}>/python"
            COMMAND ${CMAKE_COMMAND} -E copy_directory "${CMAKE_PREFIX_PATH}/libpython" "$<TARGET_FILE_DIR:${target}>/python"
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${CMAKE_PREFIX_PATH}/libpython/python${_bundled_python_abi}.dll"
                "${CMAKE_PREFIX_PATH}/libpython/vcruntime140.dll"
                "${CMAKE_PREFIX_PATH}/libpython/vcruntime140_1.dll"
                "$<TARGET_FILE_DIR:${target}>"
            COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:${target}>/tools/uv"
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${ORCA_BUNDLED_UV_EXECUTABLE}" "$<TARGET_FILE_DIR:${target}>/tools/uv/${ORCA_BUNDLED_UV_FILENAME}"
            COMMENT "Copying Python runtime and uv for ${target}"
            VERBATIM
        )
    endif()
endfunction()

add_executable(orca_plugin_wheel_cache_recovery_test
    wheel_cache_recovery.cpp
    ${_plugin_core_private_tus})
orca_plugin_core_runner_extras(orca_plugin_wheel_cache_recovery_test)

add_executable(orca_plugin_dependency_environment_test
    dependency_environment.cpp
    dependency_environment_main.cpp
    ${_plugin_core_private_tus})
orca_plugin_core_runner_extras(orca_plugin_dependency_environment_test)

# Load-wait / unload-overlap / observer-order contract runners (women
# runtime_wait / unload_overlap / observer_queue, adapted to the key-based
# PluginManager API; see the file headers for the per-axis adaptations).
add_executable(orca_plugin_runtime_wait_test
    runtime_wait.cpp
    ${_plugin_core_private_tus})
orca_plugin_core_runner_extras(orca_plugin_runtime_wait_test)

add_executable(orca_plugin_unload_overlap_test
    unload_overlap.cpp
    ${_plugin_core_private_tus})
orca_plugin_core_runner_extras(orca_plugin_unload_overlap_test)

add_executable(orca_plugin_observer_queue_test
    observer_queue.cpp
    ${_plugin_core_private_tus})
orca_plugin_core_runner_extras(orca_plugin_observer_queue_test)

# The real-rename crash injector is macOS-only (dyld interposition), as in the
# women tree; the runner and fault library stay out of the default build.
if (APPLE)
    add_executable(orca_plugin_dependency_recovery_test EXCLUDE_FROM_ALL
        dependency_recovery.cpp
        ${_plugin_core_private_tus})
    orca_plugin_core_runner_extras(orca_plugin_dependency_recovery_test)
    add_library(orca_plugin_dependency_fault SHARED EXCLUDE_FROM_ALL
        dependency_crash_interpose.cpp)
    target_compile_features(orca_plugin_dependency_fault PRIVATE cxx_std_17)
    add_dependencies(orca_plugin_dependency_recovery_test orca_plugin_dependency_fault)
endif()

# Production-binding SDK exporter (women tools/plugin_sdk): runs the same
# embedded bindings without wxApp/plugins/real profile. Built on demand and
# driven by scripts/generate_plugin_sdk.py + verify_plugin_sdk.py.
add_executable(orca_plugin_sdk_export EXCLUDE_FROM_ALL
    ${PROJECT_SOURCE_DIR}/tools/plugin_sdk/main.cpp
    ${_plugin_core_private_tus})
orca_plugin_core_runner_extras(orca_plugin_sdk_export)

# ctest entries run the python orchestrators (they spawn the runner binaries in
# isolated temp profiles and assert cross-process behaviour).
find_package(Python3 COMPONENTS Interpreter)
if (Python3_Interpreter_FOUND)
    add_test(NAME plugin_core:file_lock
        COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/scripts/test_plugin_file_lock.py"
                --binary $<TARGET_FILE:orca_plugin_lock_test>)
    add_test(NAME plugin_core:wheel_cache_recovery
        COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/scripts/test_plugin_wheel_cache_recovery.py"
                --native $<TARGET_FILE:orca_plugin_wheel_cache_recovery_test>
                --output "${CMAKE_CURRENT_BINARY_DIR}/wheel_cache_recovery_report.json")
    add_test(NAME plugin_core:dependency_environment
        COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/scripts/test_plugin_dependency_environment.py"
                --binary $<TARGET_FILE:orca_plugin_dependency_environment_test>)
    add_test(NAME plugin_core:runtime_wait
        COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/scripts/test_plugin_runtime_wait.py"
                --binary $<TARGET_FILE:orca_plugin_runtime_wait_test>)
    add_test(NAME plugin_core:unload_overlap
        COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/scripts/test_plugin_unload_overlap.py"
                --binary $<TARGET_FILE:orca_plugin_unload_overlap_test>)
    add_test(NAME plugin_core:observer_queue
        COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/scripts/test_plugin_observer_queue.py"
                --binary $<TARGET_FILE:orca_plugin_observer_queue_test>)
    set_tests_properties(plugin_core:file_lock plugin_core:wheel_cache_recovery plugin_core:dependency_environment
        plugin_core:runtime_wait plugin_core:unload_overlap plugin_core:observer_queue
        PROPERTIES TIMEOUT 600)
endif()
