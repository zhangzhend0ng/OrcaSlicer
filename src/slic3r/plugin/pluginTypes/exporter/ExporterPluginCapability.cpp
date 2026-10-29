#include "ExporterPluginCapability.hpp"
#include "ExporterPluginCapabilityTrampoline.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <boost/log/trivial.hpp>

#include <memory>
#include <string>
#include <vector>

namespace py = pybind11;

namespace Slic3r {

void ExporterPluginCapability::RegisterBindings(pybind11::module_& module)
{
    BOOST_LOG_TRIVIAL(debug) << "Registering orca.exporter bindings";

    // Fork-provisional contract: upstream reserves the "exporter" capability slot but has
    // not designed its base yet; if their shape differs, this module is the reconciliation
    // seam (alias methods here, keep the enum/type strings identical).
    auto exporter = module.def_submodule("exporter",
        "Exporter capability (fork-provisional): write the current scene in formats the "
        "host has no built-in writer for.");

    py::class_<ExporterContext>(exporter, "ExporterContext")
        .def_readonly("orca_version", &ExporterContext::orca_version)
        .def_readonly("path", &ExporterContext::path,
            "Export target path; its folder is writable for this call (scoped grant). Write the "
            "file yourself so the write is attributed to your plugin.")
        .def_readonly("object_indices", &ExporterContext::object_indices,
            "Indices into ctx.model.objects() chosen for the export; empty means every object.")
        .def_property_readonly("model", [](const ExporterContext& ctx) -> py::object {
            if (ctx.model == nullptr)
                return py::none();
            // The orca.host.Model binding (PluginHostModel.cpp), handed out as a reference
            // into the host-side snapshot clone that lives for the whole call.
            return py::cast(const_cast<Model*>(ctx.model), py::return_value_policy::reference);
        }, "Read-only orca.host.Model snapshot of the scene. Pull meshes via "
           "model.object(i).volume(j).mesh().vertices()/triangles() (local mm coordinates; "
           "world = instance.matrix() @ volume.matrix() @ v). Valid only during this call.");

    py::class_<ExporterPluginCapability, PluginCapabilityInterface, PyExporterPluginCapabilityTrampoline,
               std::shared_ptr<ExporterPluginCapability>>(exporter, "ExporterPluginCapabilityBase")
        .def(py::init<>())
        .def("get_type", &ExporterPluginCapability::get_type)
        .def("get_supported_extensions", &ExporterPluginCapability::get_supported_extensions,
             "Extensions this exporter offers, as lower-case dot-prefixed strings "
             "([\".hul\", ...]). Resolved once at load; keep it static per capability.")
        .def("export_file", &ExporterPluginCapability::export_file, py::arg("ctx"),
             "Write the export (synchronous; the host calls this on a worker thread while the "
             "UI stays responsive). Read geometry from ctx (never orca.host.model()), write "
             "ctx.path yourself. Return ExecutionResult.success(message) or .failure(...). "
             "Params like unit conversion belong in the capability config, not the context.");
}

} // namespace Slic3r
