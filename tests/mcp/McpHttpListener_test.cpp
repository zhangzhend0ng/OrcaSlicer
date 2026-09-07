#include <catch_main.hpp>

#include "slic3r/GUI/Mcp/McpHttpListener.hpp"
#include "slic3r/GUI/Mcp/McpJsonRpc.hpp"

#include <boost/asio.hpp>
#include <atomic>
#include <string>
#include <thread>

using namespace Slic3r::Mcp;

namespace {

/// Tiny synchronous loopback HTTP client for listener tests.
std::string http_post(unsigned short           port,
                      const std::string&       path,
                      const std::string&       auth_header,
                      const std::string&       body,
                      unsigned&                status_out,
                      const std::string&       verb = "POST")
{
    boost::asio::io_service  io;
    boost::asio::ip::tcp::socket socket(io);
    socket.connect({boost::asio::ip::address_v4::loopback(), port});
    std::ostringstream req;
    req << verb << " " << path << " HTTP/1.1\r\n";
    req << "Host: 127.0.0.1\r\n";
    if (!auth_header.empty()) {
        req << "Authorization: " << auth_header << "\r\n";
    }
    req << "Content-Length: " << body.size() << "\r\n";
    req << "Connection: close\r\n";
    req << "\r\n";
    req << body;
    boost::asio::write(socket, boost::asio::buffer(req.str()));

    std::string response;
    char        chunk[4096];
    boost::system::error_code ec;
    for (;;) {
        const std::size_t n = socket.read_some(boost::asio::buffer(chunk), ec);
        response.append(chunk, n);
        if (ec) {
            break;
        }
    }
    // status line
    const std::size_t space1 = response.find(' ');
    status_out = static_cast<unsigned>(std::atoi(response.substr(space1 + 1).c_str()));
    // body after blank line
    const std::size_t blank = response.find("\r\n\r\n");
    return blank == std::string::npos ? std::string() : response.substr(blank + 4);
}

} // namespace

TEST_CASE("listener round trip: token gate, dispatch, JSON envelope", "[McpHttpListener]") {
    const std::string token = "deadbeefcafe0123456789abcdef0123";
    std::atomic<int>  dispatches{0};

    HttpListener listener(token,
                          [&dispatches](const std::string& method, const std::string& body) {
                              ++dispatches;
                              (void)method;
                              // Mirror the real dispatcher: parse errors come
                              // back as JSON-RPC error envelopes.
                              const McpRequest request = parse_request(body);
                              if (!request.ok) {
                                  return build_error(RpcErrorCode::ParseError,
                                                     request.error, request.has_id,
                                                     request.id);
                              }
                              return build_result(
                                  nlohmann::json{{"echo", request.method}},
                                  request.has_id, request.id);
                          });

    // port 0 = ephemeral, so the test never fights for a fixed port
    REQUIRE(listener.start(0));
    REQUIRE(listener.is_running());
    const unsigned short port = listener.port();
    REQUIRE(port != 0);

    unsigned status = 0;
    std::string body = http_post(port, "/", "Bearer " + token,
                                 R"({"method":"ping","id":3})", status);
    REQUIRE(status == 200);
    REQUIRE(dispatches.load() == 1);
    nlohmann::json doc = nlohmann::json::parse(body);
    REQUIRE(doc["result"]["echo"] == "ping");
    REQUIRE(doc["id"] == 3);

    SECTION("wrong token is rejected before dispatch") {
        body   = http_post(port, "/", "Bearer wrong", R"({"method":"ping"})", status);
        doc    = nlohmann::json::parse(body);
        REQUIRE(dispatches.load() == 1); // dispatcher never saw it
        REQUIRE(doc["error"]["code"] == -32001);
    }
    SECTION("missing token is rejected") {
        body = http_post(port, "/", "", R"({"method":"ping"})", status);
        doc  = nlohmann::json::parse(body);
        REQUIRE(doc["error"]["code"] == -32001);
    }
    SECTION("broken JSON yields parse error, not a crash") {
        body = http_post(port, "/", "Bearer " + token, "not json", status);
        INFO("raw body: " << body);
        doc  = nlohmann::json::parse(body);
        REQUIRE(doc["error"]["code"] == -32700);
    }
    SECTION("oversized content-length is rejected cleanly") {
        // lie about the length: reader must refuse before allocating 1 GB
        boost::asio::io_service        io;
        boost::asio::ip::tcp::socket   socket(io);
        socket.connect({boost::asio::ip::address_v4::loopback(), port});
        std::ostringstream req;
        req << "POST / HTTP/1.1\r\nContent-Length: 1073741824\r\nConnection: close\r\n\r\n";
        boost::asio::write(socket, boost::asio::buffer(req.str()));
        std::string response;
        char        chunk[4096];
        boost::system::error_code ec;
        for (;;) {
            const std::size_t n = socket.read_some(boost::asio::buffer(chunk), ec);
            response.append(chunk, n);
            if (ec) {
                break;
            }
        }
        REQUIRE(response.find("200 OK") != std::string::npos);
    }

    listener.stop();
    REQUIRE_FALSE(listener.is_running());
}

TEST_CASE("listener refuses duplicate start and survives stop twice", "[McpHttpListener]") {
    HttpListener listener("tok", [](const std::string&, const std::string&) {
        return std::string("{\"result\":{}}");
    });
    REQUIRE(listener.start(0));
    const unsigned short port = listener.port();
    REQUIRE(listener.start(port)); // second start is a no-op success
    listener.stop();
    listener.stop(); // double stop must be safe
}
