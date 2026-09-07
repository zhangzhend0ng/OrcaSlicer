#pragma once
/**
 * @brief Minimal JSON-RPC request/response helpers for the private MCP
 *        listener protocol.
 *
 * This is a PRIVATE protocol (POST JSON-RPC) deliberately unrelated to the
 * MCP specification; all MCP compliance lives in the external bridge
 * process (docs/mcp-integration-plan-2026-09-07.md section 2.2).
 *
 * Error handling: nlohmann throws on malformed input; that is contained
 * here and reported via the `error` field of McpRequest / a code -32700
 * error envelope, never propagated to callers.
 */

#include <nlohmann/json.hpp>
#include <string>

namespace Slic3r {
namespace Mcp {

/// JSON-RPC error codes used by the listener.
enum class RpcErrorCode {
    ParseError     = -32700,
    InvalidRequest = -32600,
    MethodNotFound = -32601,
    InvalidParams  = -32602,
    InternalError  = -32603,
    Unauthorized   = -32001,
    UiBusy         = -32002,
    UnknownJob     = -32003,
};

/// Parsed incoming request. When `ok` is false, `error` holds the reason.
struct McpRequest
{
    bool             ok       = false;
    bool             has_id   = false;
    int              id       = 0;
    std::string      method;
    nlohmann::json   params   = nlohmann::json::object();
    std::string      error;
};

/// Parse a request body. Never throws.
McpRequest parse_request(const std::string& body);

/// Build a successful response envelope. Never throws.
std::string build_result(const nlohmann::json& result, bool has_id, int id);

/// Build an error response envelope. Never throws.
std::string build_error(RpcErrorCode code, const std::string& message, bool has_id, int id);

} // namespace Mcp
} // namespace Slic3r
