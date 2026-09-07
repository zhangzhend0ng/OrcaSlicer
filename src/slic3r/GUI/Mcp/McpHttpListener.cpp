#include "McpHttpListener.hpp"
#include "McpJsonRpc.hpp"

#include "libslic3r/Thread.hpp"

#include <algorithm>
#include <atomic>
#include <istream>
#include <map>
#include <memory>
#include <mutex>
#include <sstream>
#include <vector>

#include <boost/algorithm/string.hpp>
#include <boost/asio.hpp>
#include <boost/beast/core.hpp>
#include <boost/log/trivial.hpp>
#include <boost/thread.hpp>

namespace Slic3r {
namespace Mcp {

namespace {

/// Cap for request bodies: state payloads and params stay far below this.
constexpr std::size_t kMaxBodyBytes = 32u << 20;

/**
 * One connection. Read flow mirrors HttpServer::session (request line ->
 * headers -> body), with a proper Content-Length body read; the base class
 * version discards bodies (HttpServer.cpp read_body).
 */
class HttpSession : public std::enable_shared_from_this<HttpSession>
{
public:
    HttpSession(boost::asio::ip::tcp::socket socket,
                const std::string&            token,
                const HttpDispatchFn&         dispatch)
        : m_socket(std::move(socket))
        , m_token(token)
        , m_dispatch(dispatch)
    {}

    void start() { read_request_line(); }

    void stop()
    {
        boost::system::error_code ignored_ec;
        m_socket.shutdown(boost::asio::socket_base::shutdown_both, ignored_ec);
        m_socket.close(ignored_ec);
    }

private:
    void read_request_line()
    {
        auto self = shared_from_this();
        boost::asio::async_read_until(
            m_socket, m_buffer, '\n',
            [this, self](const boost::beast::error_code& ec, std::size_t) {
                if (ec) {
                    return;
                }
                std::istringstream stream(extract_line());
                stream >> m_method >> m_url >> m_version;
                if (m_method.empty() || m_url.empty()) {
                    return;
                }
                read_header_line();
            });
    }

    std::string extract_line()
    {
        std::string  line;
        std::istream stream(&m_buffer);
        std::getline(stream, line, '\n');
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        return line;
    }

    void read_header_line()
    {
        auto self = shared_from_this();
        boost::asio::async_read_until(
            m_socket, m_buffer, '\n',
            [this, self](const boost::beast::error_code& ec, std::size_t) {
                if (ec) {
                    return;
                }
                const std::string line = extract_line();
                if (line.empty()) {
                    on_headers_complete();
                    return;
                }
                const std::size_t colon = line.find(':');
                if (colon != std::string::npos) {
                    std::string name  = line.substr(0, colon);
                    std::string value = line.substr(colon + 1);
                    boost::algorithm::trim(name);
                    boost::algorithm::trim(value);
                    boost::algorithm::to_lower(name);
                    m_headers[name] = value;
                }
                read_header_line();
            });
    }

    std::size_t content_length() const
    {
        auto it = m_headers.find("content-length");
        if (it == m_headers.end()) {
            return 0;
        }
        try {
            const unsigned long value = std::stoul(it->second);
            return (value > 0 && value <= kMaxBodyBytes) ? static_cast<std::size_t>(value) : 0;
        } catch (const std::exception&) {
            return 0;
        }
    }

    void on_headers_complete()
    {
        if (m_method != "POST") {
            // Private protocol: POST JSON-RPC only. No MCP concepts (SSE,
            // 405 semantics) and no static routes live here.
            write_response(build_error(RpcErrorCode::InvalidRequest,
                                       "only POST is supported", false, 0));
            return;
        }
        const std::size_t length = content_length();
        if (length == 0) {
            write_response(build_error(RpcErrorCode::InvalidRequest,
                                       "missing or oversized body", false, 0));
            return;
        }
        m_body.resize(length);
        // Body bytes may already sit in the stream buffer next to the
        // headers: consume them before waiting on the socket, or a single
        // write() from the client would deadlock both sides.
        const std::size_t buffered = std::min(m_buffer.size(), length);
        if (buffered > 0) {
            boost::asio::buffer_copy(boost::asio::buffer(&m_body[0], buffered),
                                     m_buffer.data(), buffered);
            m_buffer.consume(buffered);
        }
        if (buffered < length) {
            read_body(buffered);
        } else {
            on_body_complete();
        }
    }

    void read_body(std::size_t offset)
    {
        auto self = shared_from_this();
        boost::asio::async_read(
            m_socket,
            boost::asio::buffer(&m_body[offset], m_body.size() - offset),
            [this, self, offset](const boost::beast::error_code& ec, std::size_t transferred) {
                if (ec) {
                    return;
                }
                const std::size_t next = offset + transferred;
                if (next < m_body.size()) {
                    read_body(next);
                    return;
                }
                on_body_complete();
            });
    }

    void on_body_complete()
    {
        // Token check on EVERY request, before any dispatch work. This is
        // the actual defense against browser drive-by / DNS-rebinding
        // posts (integration plan section 5).
        const auto  auth     = m_headers.find("authorization");
        const bool  token_ok = auth != m_headers.end()
                             && auth->second == ("Bearer " + m_token);
        if (!token_ok) {
            write_response(build_error(RpcErrorCode::Unauthorized,
                                       "invalid or missing token", false, 0));
            return;
        }
        std::string response;
        try {
            response = m_dispatch(m_method, m_body);
        } catch (const std::exception& ex) {
            BOOST_LOG_TRIVIAL(error) << "McpListener dispatch failed: " << ex.what();
            response = build_error(RpcErrorCode::InternalError, "internal error", false, 0);
        }
        write_response(response);
    }

    void write_response(const std::string& body)
    {
        std::ostringstream out;
        out << "HTTP/1.1 200 OK\r\n";
        out << "Content-Type: application/json\r\n";
        out << "Content-Length: " << body.size() << "\r\n";
        // Intentionally NO CORS headers: this endpoint is not web-facing.
        out << "Connection: close\r\n";
        out << "\r\n";
        out << body;
        auto payload = std::make_shared<std::string>(out.str());
        auto self    = shared_from_this();
        boost::asio::async_write(
            m_socket, boost::asio::buffer(payload->data(), payload->size()),
            [self, payload](const boost::beast::error_code&, std::size_t) {
                // session release closes the socket; nothing more to do
            });
    }

    boost::asio::ip::tcp::socket       m_socket;
    const std::string&                 m_token;
    const HttpDispatchFn&              m_dispatch;
    boost::asio::streambuf             m_buffer;
    std::map<std::string, std::string> m_headers;
    std::string                        m_method;
    std::string                        m_url;
    std::string                        m_version;
    std::string                        m_body;
};

} // namespace

class HttpListener::Impl
{
public:
    Impl(const std::string& token_value, HttpDispatchFn dispatch_value)
        : token(token_value)
        , dispatch(std::move(dispatch_value))
        , work(io_service)
    {}

    /// Accept loop: each completed accept re-arms via do_accept() from the
    /// io_service thread (same pattern as HttpServer::IOServer::do_accept).
    void do_accept()
    {
        if (!running.load() || !acceptor) {
            return;
        }
        acceptor->async_accept([this](const boost::system::error_code& ec,
                                      boost::asio::ip::tcp::socket      socket) {
            if (!running.load()) {
                return;
            }
            if (!ec) {
                auto session = std::make_shared<HttpSession>(std::move(socket),
                                                             token, dispatch);
                {
                    std::lock_guard<std::mutex> lock(sessions_mutex);
                    sessions.emplace_back(session);
                }
                sessions.erase(
                    std::remove_if(sessions.begin(), sessions.end(),
                                   [](const std::weak_ptr<HttpSession>& weak) {
                                       return weak.expired();
                                   }),
                    sessions.end());
                session->start();
            }
            do_accept();
        });
    }

    void run_thread()
    {
        set_current_thread_name("mcp_server");
        try {
            io_service.run();
        } catch (const std::exception& ex) {
            BOOST_LOG_TRIVIAL(error) << "McpListener io_service failure: " << ex.what();
        }
        running = false;
    }

    boost::asio::io_service                        io_service;
    boost::asio::io_service::work                  work;
    std::unique_ptr<boost::asio::ip::tcp::acceptor> acceptor;
    std::string                                    token;
    HttpDispatchFn                                 dispatch;
    boost::thread                                  thread;
    std::mutex                                     sessions_mutex;
    std::vector<std::weak_ptr<HttpSession>>        sessions;
    std::atomic<bool>                              running{false};
    unsigned short                                 port = 0;
};

HttpListener::HttpListener(const std::string& token, HttpDispatchFn dispatch)
    : m_impl(std::make_unique<Impl>(token, std::move(dispatch)))
{}

HttpListener::~HttpListener()
{
    stop();
}

bool HttpListener::start(unsigned short port)
{
    if (m_impl->running.load()) {
        return true;
    }
    try {
        boost::asio::ip::tcp::endpoint endpoint(
            boost::asio::ip::address_v4::loopback(), port);
        auto acceptor = std::make_unique<boost::asio::ip::tcp::acceptor>(m_impl->io_service);
        acceptor->open(endpoint.protocol());
        acceptor->set_option(boost::asio::ip::tcp::acceptor::reuse_address(true));
        acceptor->bind(endpoint);
        acceptor->listen();
        // Resolve the actual port (port 0 = ephemeral; the service config
        // always uses the fixed port, tests may ask for 0).
        boost::system::error_code ec;
        const boost::asio::ip::tcp::endpoint local = acceptor->local_endpoint(ec);
        m_impl->port = ec ? port : local.port();
        m_impl->acceptor = std::move(acceptor);
    } catch (const boost::system::system_error& ex) {
        // No port drift on purpose: fail loudly instead of silently moving.
        BOOST_LOG_TRIVIAL(error)
            << "McpListener cannot bind 127.0.0.1:" << port << " (" << ex.what()
            << "); MCP interface stays disabled";
        return false;
    }
    // m_impl->port was resolved to the actual bound port above.
    m_impl->running = true;
    m_impl->thread  = boost::thread([impl = m_impl.get()]() { impl->run_thread(); });
    // Arm the first accept from the io_service thread.
    boost::asio::post(m_impl->io_service, [impl = m_impl.get()]() { impl->do_accept(); });
    BOOST_LOG_TRIVIAL(info) << "McpListener serving on 127.0.0.1:" << port;
    return true;
}

void HttpListener::stop()
{
    if (!m_impl) {
        return;
    }
    m_impl->running = false;
    if (m_impl->acceptor) {
        boost::system::error_code ignored_ec;
        m_impl->acceptor->close(ignored_ec);
    }
    {
        std::lock_guard<std::mutex> lock(m_impl->sessions_mutex);
        for (auto& weak : m_impl->sessions) {
            if (auto session = weak.lock()) {
                session->stop();
            }
        }
        m_impl->sessions.clear();
    }
    m_impl->io_service.stop();
    if (m_impl->thread.joinable()) {
        m_impl->thread.join();
    }
    m_impl->io_service.reset();
}

bool HttpListener::is_running() const
{
    return m_impl->running.load();
}

unsigned short HttpListener::port() const
{
    return m_impl->port;
}

} // namespace Mcp
} // namespace Slic3r
