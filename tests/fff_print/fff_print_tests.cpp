#include <catch_main.hpp>

#include "libslic3r/libslic3r.h"
#include "libslic3r/Utils.hpp"

namespace {
struct TestResources {
    TestResources()
    {
        Slic3r::set_resources_dir(TEST_RESOURCES_DIR);
    }
};

TestResources test_resources;
}

#define NANOSVG_IMPLEMENTATION
#include "nanosvg/nanosvg.h"
#define NANOSVGRAST_IMPLEMENTATION
#include "nanosvg/nanosvgrast.h"
