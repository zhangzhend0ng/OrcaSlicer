// Test-only dyld library; never included in the application or release package.
#include <filesystem>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>
namespace fs = std::filesystem;
static void fault_rename(const fs::path& source, const fs::path& destination, std::error_code* error)
{
    fs::__rename(source, destination, error);
    if (error && *error) return;
    const char* expected = std::getenv("ORCA_DEP_TEST_SOURCE");
    const char* target = std::getenv("ORCA_DEP_TEST_DESTINATION");
    const char* record = std::getenv("ORCA_DEP_TEST_RECORD");
    const char* prefix = std::getenv("ORCA_DEP_TEST_PREFIX");
    if (!expected || !target || !record || !prefix) return;
    const auto from = source.native();
    const bool matches = *prefix == '1' ? from.rfind(expected, 0) == 0 : from == expected;
    if (!matches || destination.native() != target) return;
    if (FILE* file = std::fopen(record, "w")) {
        std::fputs("{\"real_std_filesystem_rename_completed\":true,\"forced_process_exit\":86}\n", file);
        std::fflush(file);
        std::fclose(file);
    }
    ::_exit(86);
}
__attribute__((used)) static struct { const void* replacement; const void* original; }
interpose __attribute__((section("__DATA,__interpose"))) = {
    reinterpret_cast<const void*>(&fault_rename), reinterpret_cast<const void*>(&fs::__rename)};
