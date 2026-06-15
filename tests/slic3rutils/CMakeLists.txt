get_filename_component(_TEST_NAME ${CMAKE_CURRENT_LIST_DIR} NAME)
add_executable(${_TEST_NAME}_tests
    ${_TEST_NAME}_tests_main.cpp
    )

if(TARGET libslic3r_gui)
    target_link_options(${_TEST_NAME}_tests PRIVATE "-Wl,--no-as-needed")
target_link_libraries(${_TEST_NAME}_tests test_common libslic3r_gui libslic3r boost_libs TBB::tbb)
else()
    target_link_options(${_TEST_NAME}_tests PRIVATE "-Wl,--no-as-needed")
target_link_libraries(${_TEST_NAME}_tests test_common libslic3r boost_libs TBB::tbb)
endif()
if (MSVC)
    target_link_libraries(${_TEST_NAME}_tests Setupapi.lib)
endif ()
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
# add_test(${_TEST_NAME}_tests ${_TEST_NAME}_tests "${CATCH_EXTRA_ARGS} exclude:[NotWorking]")
