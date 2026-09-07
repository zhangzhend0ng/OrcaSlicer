#pragma once
/**
 * @brief Loopback-only HTTP listener hosting the private MCP JSON-RPC
 *        protocol.
 *
 * Deliberately separate from the existing HttpServer instance and port
 * (13619 flutter service): the request parsing flow mirrors the
 * HttpServer::session read loop (request line, headers, then a body sized
 * by Content-Length - HttpServer.cpp itself discards bodies, so the body
 * read is extended here per the integration plan section 2.2).
 *
 * Security posture:
 *  - binds 127.0.0.1 only, never a wildcard address;
 *  - verifies the shared token on EVERY request before dispatch;
 *  - bind failure surfaces as a `false` return from start() - the port is
 *    never drifted to +N like the legacy server does (HttpServer.cpp:491).
 *
 * Threading: a dedicated boost::thread runs the asio io_service; handlers
 * are invoked on that thread and must never block on the UI thread.
 */

#include <functional>
#include <memory>
#include <string>

namespace Slic3r {
namespace Mcp {

/// Invoked with (method, body) after token validation; returns the full
/// JSON response body. Runs on the listener worker thread.
using HttpDispatchFn = std::function<std::string(const std::string& method, const std::string& body)>;

class HttpListener
{
public:
    HttpListener(const std::string& token, HttpDispatchFn dispatch);
    ~HttpListener();

    HttpListener(const HttpListener&)            = delete;
    HttpListener& operator=(const HttpListener&) = delete;

    /// Bind 127.0.0.1:`port` and start serving on a worker thread.
    /// Returns false when the port cannot be bound (logged, never drifted).
    bool start(unsigned short port);

    /// Stop accepting, close sessions, join the worker thread.
    void stop();

    bool is_running() const;
    unsigned short port() const;

private:
    class Impl;
    std::unique_ptr<Impl> m_impl;
};

} // namespace Mcp
} // namespace Slic3r
