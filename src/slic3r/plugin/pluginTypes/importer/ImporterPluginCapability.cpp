#include "ImporterPluginCapability.hpp"
#include "ImporterPluginCapabilityTrampoline.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <boost/log/trivial.hpp>

#include <memory>
#include <string>
#include <vector>

namespace py = pybind11;

namespace Slic3r {

void ImporterPluginCapability::RegisterBindings(pybind11::module_& module)
{
    BOOST_LOG_TRIVIAL(debug) << "Registering orca.importer bindings";

    // Fork-provisional contract: upstream reserves the "importer" capability slot but has
    // not designed its base yet; if their shape differs, this module is the reconciliation
    // seam (alias methods here, keep the enum/type strings identical).
    auto importer = module.def_submodule("importer",
        "Importer capability (fork-provisional): convert files the host has no built-in "
        "loader for into host-loadable mesh files.");

    py::class_<ImporterPluginCapability, PluginCapabilityInterface, PyImporterPluginCapabilityTrampoline,
               std::shared_ptr<ImporterPluginCapability>>(importer, "ImporterPluginCapabilityBase")
        .def(py::init<>())
        .def("get_type", &ImporterPluginCapability::get_type)
        .def("get_supported_extensions", &ImporterPluginCapability::get_supported_extensions,
             "Extensions this importer claims, as lower-case dot-prefixed strings "
             "([\".hul\", ...]). Resolved once at load; keep it static per capability.")
        .def("import_file", &ImporterPluginCapability::import_file, py::arg("path"),
             "Convert one file (synchronous; the host calls this on a worker thread). Write "
             "the converted, host-loadable mesh file(s) (.stl/.obj/.3mf) under "
             "orca.host.plugin.storage() and return ExecutionResult.success(data=json with "
             "{\"files\": [paths]}). Return .skipped(path) to decline; .failure(...) for "
             "errors. The input's folder is readable for this call (scoped read grant); "
             "reading anything else needs the plugin's own fs_read permission.");
}

} // namespace Slic3r
