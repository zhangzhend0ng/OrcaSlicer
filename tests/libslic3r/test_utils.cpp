// Only the tests for the helpers this fork shares with upstream live here (is_absolute_path_
// within_root, is_safe_to_open_file_name from upstream 203bc63f35); upstream's test_utils.cpp
// additionally covers per-user temp-dir helpers this fork does not carry.
#include <catch2/catch_all.hpp>

#include "libslic3r/Utils.hpp"

#include "test_utils.hpp"

#include <boost/filesystem.hpp>

#include <fstream>
#include <string>

using namespace Slic3r;

TEST_CASE("is_absolute_path_within_root accepts only entries inside the root", "[utils]") {
    namespace fs = boost::filesystem;
    ScopedTemporaryDir outer;
    const fs::path root = outer.path() / "Auxiliaries";
    fs::create_directories(root / "Others");
    const fs::path inside = root / "Others" / "note.txt";
    const fs::path outside = outer.path() / "secret.txt";
    std::ofstream(inside.string()) << "inside";
    std::ofstream(outside.string()) << "outside";

    SECTION("a file inside the root") {
        REQUIRE(is_absolute_path_within_root(inside, root));
    }
    SECTION("a path inside the root whose file does not exist yet") {
        REQUIRE(is_absolute_path_within_root(root / "Others" / "missing.txt", root));
    }
    SECTION("the root itself") {
        REQUIRE_FALSE(is_absolute_path_within_root(root, root));
    }
    SECTION("a parent-directory escape spelled under the root") {
        REQUIRE_FALSE(is_absolute_path_within_root(root / "Others" / ".." / ".." / "secret.txt", root));
    }
    SECTION("an absolute path elsewhere") {
        REQUIRE_FALSE(is_absolute_path_within_root(outside, root));
    }
    SECTION("a sibling directory sharing the root's name as a prefix") {
        const fs::path sibling = outer.path() / "Auxiliaries2" / "note.txt";
        REQUIRE_FALSE(is_absolute_path_within_root(sibling, root));
    }
    SECTION("a relative path") {
        REQUIRE_FALSE(is_absolute_path_within_root(fs::path("Others") / "note.txt", root));
    }
    SECTION("an empty path") {
        REQUIRE_FALSE(is_absolute_path_within_root(fs::path(), root));
    }
#ifndef _WIN32
    // Creating symlinks on Windows needs elevated rights or developer mode.
    SECTION("a symlink inside the root that points outside") {
        const fs::path link = root / "Others" / "link.txt";
        fs::create_symlink(outside, link);
        REQUIRE_FALSE(is_absolute_path_within_root(link, root));
    }
#endif
}

TEST_CASE("is_safe_to_open_file_name accepts plain documents, images and models", "[utils]") {
    const std::string safe = GENERATE(as<std::string>{},
        "Manual.pdf", "BOM.xlsx", "BOM.csv", "guide.docx", "notes.txt", "README.md", "photo.JPG", "render.png",
        "assembly.step", "part.stl", "project.3mf", "drawing.dxf", "build.mp4", "setup.exe.pdf", ".pdf");
    INFO(safe);
    CHECK(is_safe_to_open_file_name(safe));
}

TEST_CASE("is_safe_to_open_file_name rejects programs and anything it does not know", "[utils]") {
    const std::string unsafe = GENERATE(as<std::string>{},
        "setup.exe", "SETUP.EXE", "Manual.pdf.exe", "run.bat", "shortcut.lnk", "site.url", "script.ps1", "help.chm",
        "tool.jar", "script.py", "Install.command", "install.sh", "launcher.desktop", "Printer.AppImage",
        // Documents that can carry macros or scripts.
        "BOM.xls", "BOM.xlsm", "guide.doc", "guide.docm", "sheet.ods", "page.html", "logo.svg", "bundle.zip",
        // No extension, an unknown one, or a name the desktop would read differently.
        "readme", "pdf", "data.xyz", "", "...", "Manual.pdf.", "Manual.pdf ", "setup.exe:note.txt", "dir.pdf/readme");
    INFO(unsafe);
    CHECK_FALSE(is_safe_to_open_file_name(unsafe));
}
