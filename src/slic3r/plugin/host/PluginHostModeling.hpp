#ifndef slic3r_PluginHostModeling_hpp_
#define slic3r_PluginHostModeling_hpp_

#pragma once

// Internal to plugin/host/: the modeling-domain Plater methods (primitives,
// plane cut, text/SVG volumes), implemented in PluginHostModeling.cpp. The
// Plater py::class_ itself is registered by register_app (PluginHostApp.cpp);
// this extends that binding with the modeling methods, so it must be called
// from register_app after its own .def() chain.

#include <pybind11/pybind11.h>

#include <slic3r/GUI/Plater.hpp>

namespace Slic3r::host_bindings {

void register_modeling_methods(pybind11::class_<GUI::Plater, std::unique_ptr<GUI::Plater, pybind11::nodelete>>& plater);

} // namespace Slic3r::host_bindings

#endif /* slic3r_PluginHostModeling_hpp_ */
