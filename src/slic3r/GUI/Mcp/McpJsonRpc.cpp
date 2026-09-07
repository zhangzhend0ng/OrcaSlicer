#include "McpJsonRpc.hpp"

#include <sstream>

namespace Slic3r {
namespace Mcp {

McpRequest parse_request(const std::string& body)
{
    McpRequest req;
    nlohmann::json doc;
    try {
        doc = nlohmann::json::parse(body);
    } catch (const std::exception&) {
        req.error = "request body is not valid JSON";
        return req;
    }
    if (!doc.is_object()) {
        req.error = "request must be a JSON object";
        return req;
    }
    auto method_it = doc.find("method");
    if (method_it == doc.end() || !method_it->is_string()) {
        req.error = "missing string field: method";
        return req;
    }
    req.method = method_it->get<std::string>();
    if (req.method.empty()) {
        req.error = "method must not be empty";
        return req;
    }
    auto id_it = doc.find("id");
    if (id_it != doc.end() && id_it->is_number_integer()) {
        req.has_id = true;
        req.id     = id_it->get<int>();
    }
    auto params_it = doc.find("params");
    if (params_it != doc.end() && params_it->is_object()) {
        req.params = *params_it;
    }
    req.ok = true;
    return req;
}

std::string build_result(const nlohmann::json& result, bool has_id, int id)
{
    nlohmann::json doc    = nlohmann::json::object();
    doc["result"]         = result;
    if (has_id) {
        doc["id"] = id;
    }
    try {
        return doc.dump();
    } catch (const std::exception&) {
        return "{\"error\":{\"code\":-32603,\"message\":\"response serialization failed\"}}";
    }
}

std::string build_error(RpcErrorCode code, const std::string& message, bool has_id, int id)
{
    nlohmann::json doc  = nlohmann::json::object();
    nlohmann::json err  = nlohmann::json::object();
    err["code"]         = static_cast<int>(code);
    err["message"]      = message;
    doc["error"]        = err;
    if (has_id) {
        doc["id"] = id;
    }
    try {
        return doc.dump();
    } catch (const std::exception&) {
        return "{\"error\":{\"code\":-32603,\"message\":\"response serialization failed\"}}";
    }
}

} // namespace Mcp
} // namespace Slic3r
