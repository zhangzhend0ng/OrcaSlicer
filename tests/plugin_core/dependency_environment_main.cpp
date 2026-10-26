// Driver for the absorbed dependency-environment contract (women 0aa325e101).
// women drives test_dependency_environment() from its 55-scenario main harness,
// which is not portable (texture scenarios); this driver keeps the contract body
// verbatim and supplies only the argv plumbing plus the isolated profile that
// the women harness provided (data_dir isolation: the contract writes the
// dependency policy and the shared package directory under data_dir).
#include "libslic3r/Utils.hpp"
#include <boost/log/core.hpp>
#include <boost/nowide/args.hpp>
#include <filesystem>
#include <iostream>

void test_dependency_environment(const std::filesystem::path& fixtures);

int main(int argc, char** argv)
{
    boost::nowide::args utf8_args(argc, argv);
    if (argc != 3)
        return 2;
    try {
        const auto profile = std::filesystem::u8path(argv[2]);
        std::filesystem::create_directories(profile);
        Slic3r::set_data_dir(profile.u8string());
        boost::log::core::get()->set_logging_enabled(false);
        test_dependency_environment(std::filesystem::u8path(argv[1]));
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
    std::cout << "PASS dependency environment\n";
    return 0;
}
