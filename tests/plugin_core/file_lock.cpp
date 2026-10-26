#include "slic3r/plugin/PluginFileLock.hpp"
#include <iostream>
#include <string>
int run(const std::filesystem::path& path, bool hold)
{
    try {
        Slic3r::PluginFileLock lock(path);
        std::cout << "locked" << std::endl;
        if (hold) {
            std::string line;
            std::getline(std::cin, line);
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv)
{
    if (argc != 3) return 2;
    return run(std::filesystem::path(argv[1]), std::wstring(argv[2]) == L"hold");
}
#else
int main(int argc, char** argv)
{
    if (argc != 3) return 2;
    return run(std::filesystem::u8path(argv[1]), std::string(argv[2]) == "hold");
}
#endif
