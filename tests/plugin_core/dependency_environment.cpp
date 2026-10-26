#include "slic3r/plugin/PluginDependencyInstaller.hpp"
#include "slic3r/plugin/PythonInterpreter.hpp"
#include <boost/nowide/cstdlib.hpp>
#include <filesystem>
#include <optional>
#include <stdexcept>
#include <string>

namespace {
void require(bool condition, const std::string& message)
{
    if (!condition)
        throw std::runtime_error(message);
}

class ScopedEnvironment
{
public:
    explicit ScopedEnvironment(const char* name) : m_name(name)
    {
        if (const char* value = boost::nowide::getenv(name))
            m_original = value;
        require(boost::nowide::setenv(name, sentinel(), 1) == 0, "Cannot set environment fixture");
    }
    ~ScopedEnvironment()
    {
        if (m_original)
            boost::nowide::setenv(m_name.c_str(), m_original->c_str(), 1);
        else
            boost::nowide::unsetenv(m_name.c_str());
    }
    void verify() const
    {
        const char* value = boost::nowide::getenv(m_name.c_str());
        require(value && value == std::string(sentinel()), "Dependency installer modified host variable " + m_name);
    }

private:
    static const char* sentinel() { return u8"host-only-中文-value"; }
    std::string m_name;
    std::optional<std::string> m_original;
};
} // namespace

// Run inside the ordinary isolated plugin test profile, after runtime initialization.
void test_dependency_environment(const std::filesystem::path& fixtures)
{
    namespace loader = Slic3r::plugin_loader;
#ifdef _WIN32
    // The mixed case must be removed too: Windows environment names ignore case.
    const ScopedEnvironment uv("uV_oFfLiNe");
#else
    const ScopedEnvironment uv("UV_OFFLINE");
#endif
    const ScopedEnvironment python("PYTHONHOME");
    const ScopedEnvironment pip("PIP_INDEX_URL");
    std::string error;
    require(loader::configure_dependency_install({true, fixtures.u8string()}, error), error);
    // UV_OFFLINE's intentionally invalid boolean also checks child-only cleanup.
    require(loader::install_packages_transactionally({"contract-dep==1.0.0"}, error), "Offline install: " + error);
    uv.verify();
    python.verify();
    pip.verify();
    const auto packages = std::filesystem::u8path(Slic3r::PythonInterpreter::shared_packages_dir());
    require(std::filesystem::is_regular_file(packages / "contract_dep/__init__.py"), "Installed dependency missing");
    require(!loader::install_packages_transactionally({"missing-environment-contract==1.0.0"}, error),
            "Missing offline package was accepted");
    uv.verify();
    python.verify();
    pip.verify();
    require(std::filesystem::is_regular_file(packages / "contract_dep/__init__.py"), "Failed install damaged previous package");
}
