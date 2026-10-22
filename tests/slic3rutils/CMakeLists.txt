# slic3rutils tests require libslic3r_gui (contains Http.cpp).
# Skip entirely when GUI is disabled.
if (NOT SLIC3R_GUI)
    return()
endif()

get_filename_component(_TEST_NAME ${CMAKE_CURRENT_LIST_DIR} NAME)
add_executable(${_TEST_NAME}_tests
    ${_TEST_NAME}_tests_main.cpp
    SnapLogClient_test.cpp
    test_action_source.cpp
    test_file_url.cpp
    test_plugin_host_api.cpp
    test_plugin_capability_config.cpp
    test_plugin_config.cpp
    test_plugin_capabilities_in_use.cpp
    test_plugin_install.cpp
    test_plugin_lifecycle.cpp
    test_plugin_resource_texture.cpp
    # TRIM: test_plugin_printer_agent.cpp / test_printhost.cpp from the upstream list not carried (fork has no such test files)
    test_slicing_pipeline_bindings.cpp
    test_slicing_pipeline_config.cpp
    test_plugin_sort.cpp
    test_plugin_cloud_metadata.cpp
    test_plugin_audit.cpp
    test_plugin_json_depth.cpp
    ../fff_print/test_helpers.cpp
    )

find_package(JPEG REQUIRED)
find_package(PNG REQUIRED)
find_package(ZLIB REQUIRED)
find_package(libnoise REQUIRED)
find_package(Qhull 7.2 QUIET)

if (SLIC3R_WX_STABLE)
    find_package(wxWidgets 3.0 REQUIRED COMPONENTS base core adv html gl aui net media webview)
else ()
    find_package(wxWidgets 3.1 REQUIRED COMPONENTS base core adv html gl aui net media webview)
endif ()
include(${wxWidgets_USE_FILE})
# Vendored WebP support libs required by wx 3.3's wxWEBPHandler (see src/CMakeLists.txt)
if (WIN32 AND wxWidgets_LIB_DIR)
    list(APPEND wxWidgets_LIBRARIES "${wxWidgets_LIB_DIR}/wxwebp.lib" "${wxWidgets_LIB_DIR}/wxwebpdemux.lib" "${wxWidgets_LIB_DIR}/wxsharpyuv.lib")
endif ()

if(UNIX AND NOT APPLE)
    target_link_options(${_TEST_NAME}_tests PRIVATE "-Wl,--no-as-needed")
endif()
# libslic3r_gui's BitmapCache.obj already compiles the nanoSVG rasterizer; the shared
# test_nanosvg_impl TU would collide with it at link time (mirrors upstream).
set(_slic3rutils_link_libs "${TEST_LINK_LIBS}")
list(REMOVE_ITEM _slic3rutils_link_libs test_nanosvg_impl)
if(TARGET libslic3r_gui)
    target_link_libraries(${_TEST_NAME}_tests PRIVATE libslic3r_gui ${_slic3rutils_link_libs} pybind11::embed)
else()
    target_link_libraries(${_TEST_NAME}_tests PRIVATE ${_slic3rutils_link_libs})
endif()
# libslic3r_gui references symbols implemented in the app DLL's private TUs
# (common_func, bury_cfg, SentryWrapper, BaseException); those symbols are not
# exported from the DLL, so compile the defining sources straight into the test
# (mirrors upstream).
target_sources(${_TEST_NAME}_tests PRIVATE
    ${PROJECT_SOURCE_DIR}/src/common_func/common_func.cpp
    ${PROJECT_SOURCE_DIR}/src/bury_cfg/bury_point.cpp
    ${PROJECT_SOURCE_DIR}/src/sentry_wrapper/SentryWrapper.cpp
    ${PROJECT_SOURCE_DIR}/src/dev-utils/BaseException.cpp
    ${PROJECT_SOURCE_DIR}/src/dev-utils/StackWalker.cpp
)
if (MSVC)
    target_link_libraries(${_TEST_NAME}_tests PRIVATE Setupapi.lib)
endif ()
set_property(TARGET ${_TEST_NAME}_tests PROPERTY FOLDER "tests")

add_executable(gateway_tests
    gateway_tests_main.cpp
    ConnectionProcessManager_test.cpp
    GatewayProtocol_test.cpp
    GatewayService_test.cpp
    GatewayDevice_test.cpp
    GatewayFlutterResources_test.cpp
    GatewayAccount_test.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/slic3r/Utils/ConnectionProcessManager.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/slic3r/Utils/GatewayProtocol.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/slic3r/Utils/GatewayService.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/slic3r/Utils/GatewayDevice.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/slic3r/Utils/GatewayAccount.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../src/slic3r/Utils/Http.cpp
    )
target_link_libraries(gateway_tests test_common libslic3r boost_libs libcurl OpenSSL::SSL OpenSSL::Crypto)
target_compile_definitions(gateway_tests PRIVATE GATEWAY_FLUTTER_BUNDLE="${CMAKE_CURRENT_SOURCE_DIR}/../../resources/web/flutter_web/main.dart.js")
if (MSVC)
    target_compile_definitions(gateway_tests PRIVATE _WIN32_WINNT=0x0601 NOMINMAX)
endif ()
set_property(TARGET gateway_tests PROPERTY FOLDER "tests")

if (WIN32)
    if ("${CMAKE_BUILD_TYPE}" STREQUAL "Debug")
        Snapmaker_Orca_copy_dlls(COPY_DLLS "Debug" "d" output_dlls_Debug)
    elseif("${CMAKE_BUILD_TYPE}" STREQUAL "RelWithDebInfo")
        Snapmaker_Orca_copy_dlls(COPY_DLLS "RelWithDebInfo" "" output_dlls_Release)
    else()
        Snapmaker_Orca_copy_dlls(COPY_DLLS "Release" "" output_dlls_Release)
    endif()
endif()

catch_discover_tests(${_TEST_NAME}_tests TEST_PREFIX "${_TEST_NAME}: " EXTRA_ARGS ${CATCH_EXTRA_ARGS})
catch_discover_tests(gateway_tests TEST_PREFIX "gateway: " EXTRA_ARGS ${CATCH_EXTRA_ARGS})
# add_test(${_TEST_NAME}_tests ${_TEST_NAME}_tests "${CATCH_EXTRA_ARGS} exclude:[NotWorking]")

set(_FILAMENT_TEST_NAME filament_dropdown_mapping)
add_executable(${_FILAMENT_TEST_NAME}_tests FilamentDropDown_test.cpp)
target_compile_definitions(${_FILAMENT_TEST_NAME}_tests PRIVATE wxDEBUG_LEVEL=0)
target_include_directories(${_FILAMENT_TEST_NAME}_tests PRIVATE
    ${PROJECT_SOURCE_DIR}/src
    ${PROJECT_SOURCE_DIR}/src/libslic3r
    ${PROJECT_SOURCE_DIR}/deps_src
    ${Boost_INCLUDE_DIR}
    ${wxWidgets_INCLUDE_DIRS})
if (WIN32 AND wxWidgets_LIB_DIR AND wxWidgets_CONFIGURATION)
    target_include_directories(${_FILAMENT_TEST_NAME}_tests PRIVATE
        "${wxWidgets_LIB_DIR}/${wxWidgets_CONFIGURATION}")
endif ()
target_link_libraries(${_FILAMENT_TEST_NAME}_tests PRIVATE
    Catch2::Catch2WithMain
    ${wxWidgets_LIBRARIES}
    JPEG::JPEG
    PNG::PNG
    ZLIB::ZLIB
    ${EXPAT_LIBRARIES})
set_property(TARGET ${_FILAMENT_TEST_NAME}_tests PROPERTY FOLDER "tests")
catch_discover_tests(${_FILAMENT_TEST_NAME}_tests TEST_PREFIX "${_FILAMENT_TEST_NAME}: " EXTRA_ARGS ${CATCH_EXTRA_ARGS})

set(_FILAMENT_SORT_TEST_NAME filament_sort)
# The shipped allow-list is a data contract with PresetUpdater (which deploys it) and with the
# loader under test, so the suite reads the real file instead of a copy that could drift from it.
set(_FILAMENT_ALLOW_LIST_FILE ${PROJECT_SOURCE_DIR}/resources/profiles/Snapmaker/filament/filament_allow_list.json)
file(TO_CMAKE_PATH "${_FILAMENT_ALLOW_LIST_FILE}" _FILAMENT_ALLOW_LIST_FILE)
add_executable(${_FILAMENT_SORT_TEST_NAME}_tests
    FilamentSort_test.cpp
    ${PROJECT_SOURCE_DIR}/src/slic3r/GUI/FilamentSort.cpp)
target_compile_definitions(${_FILAMENT_SORT_TEST_NAME}_tests PRIVATE
    wxDEBUG_LEVEL=0
    "FILAMENT_ALLOW_LIST_FILE=R\"(${_FILAMENT_ALLOW_LIST_FILE})\"")
target_include_directories(${_FILAMENT_SORT_TEST_NAME}_tests PRIVATE
    ${PROJECT_SOURCE_DIR}/src
    ${PROJECT_SOURCE_DIR}/src/libslic3r
    ${PROJECT_SOURCE_DIR}/deps_src
    ${Boost_INCLUDE_DIR}
    ${wxWidgets_INCLUDE_DIRS})
if (WIN32 AND wxWidgets_LIB_DIR AND wxWidgets_CONFIGURATION)
    target_include_directories(${_FILAMENT_SORT_TEST_NAME}_tests PRIVATE
        "${wxWidgets_LIB_DIR}/${wxWidgets_CONFIGURATION}")
endif ()
target_link_libraries(${_FILAMENT_SORT_TEST_NAME}_tests PRIVATE
    Catch2::Catch2WithMain
    ${wxWidgets_LIBRARIES})
set_property(TARGET ${_FILAMENT_SORT_TEST_NAME}_tests PROPERTY FOLDER "tests")
catch_discover_tests(${_FILAMENT_SORT_TEST_NAME}_tests TEST_PREFIX "${_FILAMENT_SORT_TEST_NAME}: " EXTRA_ARGS ${CATCH_EXTRA_ARGS})
if (WIN32)
    add_custom_command(TARGET ${_TEST_NAME}_tests POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:${_TEST_NAME}_tests>/python"
        COMMAND ${CMAKE_COMMAND} -E copy_directory "${CMAKE_PREFIX_PATH}/libpython" "$<TARGET_FILE_DIR:${_TEST_NAME}_tests>/python"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_PREFIX_PATH}/libpython/python${_bundled_python_abi}.dll"
            "${CMAKE_PREFIX_PATH}/libpython/vcruntime140.dll"
            "${CMAKE_PREFIX_PATH}/libpython/vcruntime140_1.dll"
            "$<TARGET_FILE_DIR:${_TEST_NAME}_tests>"
        COMMENT "Copying Python runtime for slic3rutils plugin host API tests"
        VERBATIM
    )
elseif (APPLE)
    target_link_options(${_TEST_NAME}_tests PRIVATE
        "LINKER:-rpath,@executable_path/python/lib")

    add_custom_command(TARGET ${_TEST_NAME}_tests POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E rm -rf
            "$<TARGET_FILE_DIR:${_TEST_NAME}_tests>/python"
        COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${CMAKE_PREFIX_PATH}/libpython"
            "$<TARGET_FILE_DIR:${_TEST_NAME}_tests>/python"
        COMMENT "Copying Python runtime for macOS plugin host API tests"
        VERBATIM
    )
endif()

# NOTE: slic3rutils_tests already registers via catch_discover_tests above; the
# upstream orcaslicer_discover_tests wrapper (88fb89b5eb) would register it twice.
