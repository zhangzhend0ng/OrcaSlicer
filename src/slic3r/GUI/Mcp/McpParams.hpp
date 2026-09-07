/// Key-scope and value validation for MCP parameter writes. Pure logic,
/// deliberately free of wx so it stays unit-testable (tests/mcp).
#pragma once

#include <map>
#include <string>

#include "libslic3r/PrintConfig.hpp"

namespace Slic3r {
namespace Mcp {
namespace McpParams {

/// True if opt_key may be written to a per-object override. Mirrors the
/// object tabs: PrintObjectConfig + PrintRegionConfig scopes.
bool is_valid_object_param(const std::string& opt_key);

/// True if opt_key may be written to a per-plate override. Only the
/// plate-settings-dialog keys with dialog-free semantic setters
/// (PartPlate::set_bed_type / set_print_seq) are accepted; spiral_mode pops
/// a confirmation dialog on enable and print sequences are complex
/// multi-slot structures, so both stay out of scope.
bool is_valid_plate_param(const std::string& opt_key);

/// Deserialize every {key: value} entry into config via the typed config
/// definitions. All-or-nothing for the caller: on the first rejected entry
/// this returns its error text (entries applied before the failure stay in
/// the config, so call this on a scratch config and copy over on success).
/// Empty string means every entry deserialized.
std::string deserialize_all(DynamicPrintConfig& config,
                            const std::map<std::string, std::string>& params);

} // namespace McpParams
} // namespace Mcp
} // namespace Slic3r
