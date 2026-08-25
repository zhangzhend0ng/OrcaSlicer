# wx_gui tests — validate wxUIActionSimulator driving a real wx dialog.
#
# Unlike the headless test targets (libslic3r/fff_print/...), these tests need
# a live wxWidgets build (SLIC3R_GUI=ON) because they #include <wx/uiaction.h>
# and drive the macOS Cocoa event loop via CGEventPost.
#
# Platform note: wxUIActionSimulator posts events to the login session's HID
# tap (kCGSessionEventTap / kCGHIDEventTap), so the test process must run in a
# GUI session with the dialog frontmost. These tests are NOT headless-safe —
# exclude them from headless CI (tag [gui]) and run locally on a desktop Mac.

# Skip entirely when GUI is disabled (no wx to link against).
if (NOT SLIC3R_GUI)
    return()
endif()

# Full-app mode: boot the REAL GUI_App (Orca itself) in wx_gui tests instead of
# the minimal PoCApp. Requires ORCA_GUI_TEST_MODE=1 at runtime to skip network/
# splash/registry side effects. Turn OFF for the fast EchoDialog-only smoke.
option(WX_GUI_FULL_APP "Boot the real GUI_App in wx_gui tests" ON)

get_filename_component(_TEST_NAME ${CMAKE_CURRENT_LIST_DIR} NAME)
add_executable(${_TEST_NAME}_tests
    ${_TEST_NAME}_tests_main.cpp
    wx_gui_app_tests.cpp
    wx_gui_business_tests.cpp
    )

if (WX_GUI_FULL_APP)
    target_compile_definitions(${_TEST_NAME}_tests PRIVATE ORCA_FULL_GUI_APP=1)
    # libslic3r_gui's BitmapCache already contains the nanoSVG implementation;
    # linking test_nanosvg_impl as well would duplicate every nsvg* symbol.
    list(REMOVE_ITEM TEST_LINK_LIBS test_nanosvg_impl)
    # Full-app mode pulls in the rest of libslic3r_gui, whose objects reference
    # the main-app utility sources (compiled directly into Snapmaker_Orca.exe):
    # crash/exception handling, sentry reporting, bury point, common helpers.
    target_sources(${_TEST_NAME}_tests PRIVATE
        ${CMAKE_SOURCE_DIR}/src/dev-utils/BaseException.cpp
        ${CMAKE_SOURCE_DIR}/src/dev-utils/StackWalker.cpp
        ${CMAKE_SOURCE_DIR}/src/sentry_wrapper/SentryWrapper.cpp
        ${CMAKE_SOURCE_DIR}/src/bury_cfg/bury_point.cpp
        ${CMAKE_SOURCE_DIR}/src/common_func/common_func.cpp
        )
endif()

# wx headers (e.g. <wx/uiaction.h>) are NOT propagated by libslic3r_gui:
# src/CMakeLists.txt adds wx include dirs via a directory-scope
# include(${wxWidgets_USE_FILE}), which does not enter the target's
# INTERFACE_INCLUDE_DIRECTORIES and is invisible to sibling tests/ subtrees.
# Re-resolve wx here with the same components as the main build so the headers
# and ABI match exactly (find_package is cached, so this is cheap/idempotent).
if (APPLE)
    find_package(wxWidgets 3.1 REQUIRED COMPONENTS html adv gl core base webview aui net media)
elseif (UNIX)
    find_package(wxWidgets 3.1 REQUIRED COMPONENTS base core adv html gl aui net media webview)
else()
    find_package(wxWidgets 3.1 REQUIRED COMPONENTS html adv gl core base webview aui net media)
endif()
include(${wxWidgets_USE_FILE})

# TEST_LINK_LIBS references these imported targets; each test subdirectory must
# find_package them itself (sibling dirs like slic3rutils/fff_print do the same).
find_package(JPEG REQUIRED)
find_package(PNG REQUIRED)
find_package(ZLIB REQUIRED)
find_package(libnoise REQUIRED)
# qhull is an in-tree INTERFACE target (deps_src/qhull, add_subdirectory'd
# by the top-level CMakeLists) and is NOT installed — do NOT find_package it.
# It is already pulled in via ${TEST_LINK_LIBS}.

if(TARGET libslic3r_gui)
    # libslic3r_gui links ${wxWidgets_LIBRARIES} (PUBLIC), so wx libs are
    # transitively available — no need to list them again here.
    target_link_libraries(${_TEST_NAME}_tests PRIVATE libslic3r_gui ${TEST_LINK_LIBS})
else()
    message(FATAL_ERROR "libslic3r_gui target not found — SLIC3R_GUI must be ON for wx_gui tests")
endif()

if (MSVC)
    target_link_libraries(${_TEST_NAME}_tests PRIVATE Setupapi.lib)
endif ()

# macOS: wxUIActionSimulator's CGEventPost needs the app to act like a GUI app.
set_target_properties(${_TEST_NAME}_tests PROPERTIES MACOSX_BUNDLE TRUE)

set_property(TARGET ${_TEST_NAME}_tests PROPERTY FOLDER "tests")

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
