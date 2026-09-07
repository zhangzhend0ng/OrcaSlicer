#include <catch_main.hpp>

#include "slic3r/GUI/Mcp/McpJsonRpc.hpp"

#include <string>

using namespace Slic3r::Mcp;

TEST_CASE("parse_request accepts valid envelopes", "[McpJsonRpc]") {
    auto req = parse_request(R"({"method":"get_state","params":{},"id":7})");
    REQUIRE(req.ok);
    REQUIRE(req.method == "get_state");
    REQUIRE(req.has_id);
    REQUIRE(req.id == 7);
    REQUIRE(req.params.is_object());
}

TEST_CASE("parse_request tolerates missing id and params", "[McpJsonRpc]") {
    auto req = parse_request(R"({"method":"ping"})");
    REQUIRE(req.ok);
    REQUIRE(req.method == "ping");
    REQUIRE_FALSE(req.has_id);
    REQUIRE(req.params.is_object());
}

TEST_CASE("parse_request rejects malformed bodies without throwing", "[McpJsonRpc]") {
    auto not_json = parse_request("this is not json");
    REQUIRE_FALSE(not_json.ok);
    REQUIRE_FALSE(not_json.error.empty());

    auto array_body = parse_request("[1,2,3]");
    REQUIRE_FALSE(array_body.ok);

    auto no_method = parse_request(R"({"params":{},"id":1})");
    REQUIRE_FALSE(no_method.ok);

    auto empty_body = parse_request("");
    REQUIRE_FALSE(empty_body.ok);
}

TEST_CASE("result envelope round trips id", "[McpJsonRpc]") {
    const std::string body = build_result(nlohmann::json{{"value", 3}}, true, 42);
    nlohmann::json doc = nlohmann::json::parse(body);
    REQUIRE(doc["result"]["value"] == 3);
    REQUIRE(doc["id"] == 42);
    REQUIRE_FALSE(doc.contains("error"));
}

TEST_CASE("result envelope omits id when absent", "[McpJsonRpc]") {
    const std::string body = build_result(nlohmann::json{{"pong", true}}, false, 0);
    nlohmann::json doc = nlohmann::json::parse(body);
    REQUIRE(doc["result"]["pong"] == true);
    REQUIRE_FALSE(doc.contains("id"));
}

TEST_CASE("error envelope carries code and message", "[McpJsonRpc]") {
    const std::string body = build_error(RpcErrorCode::Unauthorized, "no token", true, 5);
    nlohmann::json doc = nlohmann::json::parse(body);
    REQUIRE(doc["error"]["code"] == -32001);
    REQUIRE(doc["error"]["message"] == "no token");
    REQUIRE(doc["id"] == 5);
}
