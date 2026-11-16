/* Winsock first, before windows.h (bcrypt.h needs it). */
#ifndef NOMINMAX
#  define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#  define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <bcrypt.h>

#include "wm/ipad_server.hh"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <random>
#include <sstream>
#include <thread>

#include "core/log.hh"

namespace oanim {

namespace {

/* A page's connection once its socket is open. */
struct Client {
  int id = 0;
  SOCKET socket = INVALID_SOCKET;
  std::mutex mutex;
  std::condition_variable wake;
  /* Frames waiting to go, sent in order by its writer. */
  std::deque<std::string> outbox;
  size_t outbox_bytes = 0;
  bool closing = false;
  std::thread writer;
};

struct Server {
  std::atomic<bool> running{false};
  SOCKET listener = INVALID_SOCKET;
  int port = 0;
  std::string token;
  std::string host;
  std::filesystem::path root;
  std::thread accept_thread;
  /* Connections being served (each by its own detached thread), counted to wait for them. */
  std::atomic<int> serving{0};
  std::mutex mutex;
  /* Every socket open (pages' files and pages' sockets), closed when stopping. */
  std::vector<SOCKET> sockets;
  std::map<int, std::shared_ptr<Client>> clients;
  int next_client = 1;
  std::deque<IpadMessage> inbox;
};
Server g_server;

/* A frame this big or a page's queue this full is a page gone wrong: it is dropped. */
constexpr uint64_t MAX_MESSAGE = 64ull << 20;
constexpr size_t MAX_OUTBOX = 256ull << 20;

bool send_all(SOCKET s, const char *data, size_t size)
{
  size_t sent = 0;
  while (sent < size) {
    const int n = send(s, data + sent, int(std::min<size_t>(size - sent, 1 << 20)), 0);
    if (n <= 0) {
      return false;
    }
    sent += size_t(n);
  }
  return true;
}

bool send_all(SOCKET s, const std::string &data)
{
  return send_all(s, data.data(), data.size());
}

bool recv_exact(SOCKET s, char *data, size_t size)
{
  size_t got = 0;
  while (got < size) {
    const int n = recv(s, data + got, int(std::min<size_t>(size - got, 1 << 20)), 0);
    if (n <= 0) {
      return false;
    }
    got += size_t(n);
  }
  return true;
}

void socket_forget(SOCKET s)
{
  std::lock_guard lock(g_server.mutex);
  auto &sockets = g_server.sockets;
  if (const auto it = std::find(sockets.begin(), sockets.end(), s); it != sockets.end()) {
    sockets.erase(it);
    closesocket(s);
  }
}

std::string base64_text(const unsigned char *data, size_t size)
{
  static const char table[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string out;
  out.reserve((size + 2) / 3 * 4);
  for (size_t i = 0; i < size; i += 3) {
    const uint32_t n = (uint32_t(data[i]) << 16) | (i + 1 < size ? uint32_t(data[i + 1]) << 8 : 0) |
                       (i + 2 < size ? uint32_t(data[i + 2]) : 0);
    out += table[(n >> 18) & 63];
    out += table[(n >> 12) & 63];
    out += i + 1 < size ? table[(n >> 6) & 63] : '=';
    out += i + 2 < size ? table[n & 63] : '=';
  }
  return out;
}

bool sha1(const std::string &text, unsigned char r_digest[20])
{
  BCRYPT_ALG_HANDLE alg = nullptr;
  if (BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA1_ALGORITHM, nullptr, 0) != 0) {
    return false;
  }
  BCRYPT_HASH_HANDLE hash = nullptr;
  bool ok = BCryptCreateHash(alg, &hash, nullptr, 0, nullptr, 0, 0) == 0;
  ok = ok && BCryptHashData(hash, reinterpret_cast<PUCHAR>(const_cast<char *>(text.data())), ULONG(text.size()), 0) == 0;
  ok = ok && BCryptFinishHash(hash, r_digest, 20, 0) == 0;
  if (hash) {
    BCryptDestroyHash(hash);
  }
  BCryptCloseAlgorithmProvider(alg, 0);
  return ok;
}

std::string lower(std::string text)
{
  for (char &c : text) {
    c = char(std::tolower(static_cast<unsigned char>(c)));
  }
  return text;
}

std::string trim(const std::string &text)
{
  const size_t a = text.find_first_not_of(" \t\r\n");
  const size_t b = text.find_last_not_of(" \t\r\n");
  return a == std::string::npos ? std::string() : text.substr(a, b - a + 1);
}

/* A query parameter's value ("" without it). The key is hex, so no decoding is needed. */
std::string query_value(const std::string &query, const std::string &name)
{
  std::stringstream items(query);
  std::string item;
  while (std::getline(items, item, '&')) {
    const size_t eq = item.find('=');
    if (eq != std::string::npos && item.substr(0, eq) == name) {
      return item.substr(eq + 1);
    }
  }
  return {};
}

std::string content_type(const std::string &name)
{
  const std::string ext = lower(std::filesystem::path(name).extension().string());
  return ext == ".html"                                ? "text/html; charset=utf-8"
         : ext == ".js"                                ? "text/javascript; charset=utf-8"
         : ext == ".css"                               ? "text/css; charset=utf-8"
         : ext == ".json" || ext == ".webmanifest"     ? "application/manifest+json"
         : ext == ".png"                               ? "image/png"
         : ext == ".svg"                               ? "image/svg+xml"
                                                       : "application/octet-stream";
}

std::string http_reply(int status, const std::string &reason, const std::string &type, const std::string &body)
{
  return "HTTP/1.1 " + std::to_string(status) + " " + reason + "\r\nContent-Type: " + type +
         "\r\nContent-Length: " + std::to_string(body.size()) +
         "\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n" + body;
}

/* One of the page's files: only names in the folder itself, nothing above or below it. */
std::string serve_file(const std::string &path)
{
  std::string name = path == "/" ? "index.html" : path.substr(1);
  const bool plain = !name.empty() && name.find("..") == std::string::npos &&
                     std::all_of(name.begin(), name.end(), [](char c) {
                       return std::isalnum(static_cast<unsigned char>(c)) || c == '.' || c == '-' || c == '_';
                     });
  if (plain) {
    std::ifstream file(g_server.root / name, std::ios::binary);
    if (file) {
      std::stringstream body;
      body << file.rdbuf();
      return http_reply(200, "OK", content_type(name), body.str());
    }
  }
  return http_reply(404, "Not Found", "text/plain", "Not found");
}

void client_writer(std::shared_ptr<Client> client)
{
  while (true) {
    std::string frame;
    {
      std::unique_lock lock(client->mutex);
      client->wake.wait(lock, [&]() { return client->closing || !client->outbox.empty(); });
      if (client->outbox.empty()) {
        return;
      }
      frame = std::move(client->outbox.front());
      client->outbox.pop_front();
      client->outbox_bytes -= frame.size();
    }
    if (!send_all(client->socket, frame)) {
      /* The reader finds the socket gone and ends the connection. */
      shutdown(client->socket, SD_BOTH);
      std::lock_guard lock(client->mutex);
      client->outbox.clear();
      client->outbox_bytes = 0;
      return;
    }
  }
}

void push_message(int client, std::string text)
{
  std::lock_guard lock(g_server.mutex);
  g_server.inbox.push_back({client, std::move(text)});
}

void client_queue(Client &client, std::string frame)
{
  {
    std::lock_guard lock(client.mutex);
    if (client.closing) {
      return;
    }
    if (client.outbox_bytes + frame.size() > MAX_OUTBOX) {
      /* Not reading: let it go rather than hold the memory. */
      client.outbox.clear();
      client.outbox_bytes = 0;
      shutdown(client.socket, SD_BOTH);
      return;
    }
    client.outbox_bytes += frame.size();
    client.outbox.push_back(std::move(frame));
  }
  client.wake.notify_one();
}

/* A page's socket, after the handshake: its frames read until it closes. */
void websocket_serve(SOCKET s)
{
  auto client = std::make_shared<Client>();
  client->socket = s;
  {
    std::lock_guard lock(g_server.mutex);
    client->id = g_server.next_client++;
    g_server.clients[client->id] = client;
  }
  client->writer = std::thread(client_writer, client);
  push_message(client->id, "{\"t\":\"_open\"}");
  std::string message;
  int message_opcode = 0;
  while (g_server.running) {
    unsigned char head[2];
    if (!recv_exact(s, reinterpret_cast<char *>(head), 2)) {
      break;
    }
    const bool fin = (head[0] & 0x80) != 0;
    const int opcode = head[0] & 0x0f;
    const bool masked = (head[1] & 0x80) != 0;
    uint64_t length = head[1] & 0x7f;
    if (length == 126) {
      unsigned char ext[2];
      if (!recv_exact(s, reinterpret_cast<char *>(ext), 2)) {
        break;
      }
      length = (uint64_t(ext[0]) << 8) | ext[1];
    }
    else if (length == 127) {
      unsigned char ext[8];
      if (!recv_exact(s, reinterpret_cast<char *>(ext), 8)) {
        break;
      }
      length = 0;
      for (int i = 0; i < 8; i++) {
        length = (length << 8) | ext[i];
      }
    }
    /* A browser always masks what it sends (RFC 6455); anything else isn't one. */
    if (!masked || length > MAX_MESSAGE || message.size() + length > MAX_MESSAGE) {
      break;
    }
    unsigned char mask[4];
    if (!recv_exact(s, reinterpret_cast<char *>(mask), 4)) {
      break;
    }
    std::string payload(size_t(length), '\0');
    if (length > 0 && !recv_exact(s, payload.data(), payload.size())) {
      break;
    }
    for (size_t i = 0; i < payload.size(); i++) {
      payload[i] = char(payload[i] ^ mask[i & 3]);
    }
    if (opcode == 8) {
      client_queue(*client, ipad_websocket_frame(payload.substr(0, 2), 8));
      break;
    }
    if (opcode == 9) {
      client_queue(*client, ipad_websocket_frame(payload, 10));
      continue;
    }
    if (opcode == 10) {
      continue;
    }
    if (opcode == 1 || opcode == 2) {
      message = std::move(payload);
      message_opcode = opcode;
    }
    else if (opcode == 0) {
      message += payload;
    }
    else {
      break;
    }
    if (fin) {
      if (message_opcode == 1) {
        push_message(client->id, std::move(message));
      }
      message.clear();
    }
  }
  {
    std::lock_guard lock(client->mutex);
    client->closing = true;
  }
  client->wake.notify_one();
  client->writer.join();
  {
    std::lock_guard lock(g_server.mutex);
    g_server.clients.erase(client->id);
  }
  push_message(client->id, "{\"t\":\"_close\"}");
}

/* One connection: an HTTP request for one of the page's files, or the page's socket. */
void serve(SOCKET s)
{
  std::string request;
  char chunk[4096];
  size_t end = std::string::npos;
  while (g_server.running && (end = request.find("\r\n\r\n")) == std::string::npos && request.size() < 65536) {
    const int n = recv(s, chunk, sizeof(chunk), 0);
    if (n <= 0) {
      break;
    }
    request.append(chunk, size_t(n));
  }
  if (end != std::string::npos) {
    std::stringstream lines(request.substr(0, end));
    std::string first, line;
    std::getline(lines, first);
    std::map<std::string, std::string> headers;
    while (std::getline(lines, line)) {
      const size_t colon = line.find(':');
      if (colon != std::string::npos) {
        headers[lower(trim(line.substr(0, colon)))] = trim(line.substr(colon + 1));
      }
    }
    std::stringstream parts(first);
    std::string method, target;
    parts >> method >> target;
    const size_t q = target.find('?');
    const std::string path = target.substr(0, q);
    const std::string query = q == std::string::npos ? std::string() : target.substr(q + 1);
    if (path == "/ws") {
      const bool upgrade = lower(headers["upgrade"]) == "websocket" && !headers["sec-websocket-key"].empty();
      if (!upgrade) {
        send_all(s, http_reply(400, "Bad Request", "text/plain", "A WebSocket only"));
      }
      else if (query_value(query, "k") != g_server.token) {
        send_all(s, http_reply(403, "Forbidden", "text/plain", "Wrong key: scan the QR code again"));
      }
      else {
        const std::string reply = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                                  "Sec-WebSocket-Accept: " +
                                  ipad_websocket_accept(headers["sec-websocket-key"]) + "\r\n\r\n";
        if (send_all(s, reply)) {
          /* Small messages (a stroke's samples) go at once rather than waiting to fill a packet. */
          BOOL no_delay = TRUE;
          setsockopt(s, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char *>(&no_delay), sizeof(no_delay));
          websocket_serve(s);
        }
      }
    }
    else if (method == "GET") {
      send_all(s, serve_file(path));
    }
    else {
      send_all(s, http_reply(405, "Method Not Allowed", "text/plain", "GET only"));
    }
  }
  socket_forget(s);
  g_server.serving--;
}

void accept_loop()
{
  while (g_server.running) {
    const SOCKET client = accept(g_server.listener, nullptr, nullptr);
    if (client == INVALID_SOCKET) {
      break;
    }
    std::lock_guard lock(g_server.mutex);
    if (!g_server.running) {
      closesocket(client);
      break;
    }
    g_server.sockets.push_back(client);
    g_server.serving++;
    std::thread(serve, client).detach();
  }
}

/* The address this computer's traffic goes out by: a UDP socket "connected" to an outside address sends nothing, but
 * is given the address it would send from. */
std::string lan_address()
{
  std::string host = "127.0.0.1";
  const SOCKET probe = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (probe == INVALID_SOCKET) {
    return host;
  }
  sockaddr_in outside{};
  outside.sin_family = AF_INET;
  outside.sin_port = htons(53);
  inet_pton(AF_INET, "8.8.8.8", &outside.sin_addr);
  if (connect(probe, reinterpret_cast<sockaddr *>(&outside), sizeof(outside)) == 0) {
    sockaddr_in local{};
    int length = sizeof(local);
    char text[INET_ADDRSTRLEN] = {};
    if (getsockname(probe, reinterpret_cast<sockaddr *>(&local), &length) == 0 &&
        inet_ntop(AF_INET, &local.sin_addr, text, sizeof(text)) && local.sin_addr.s_addr != 0)
    {
      host = text;
    }
  }
  closesocket(probe);
  return host;
}

}  // namespace

std::string ipad_websocket_accept(const std::string &key)
{
  unsigned char digest[20];
  if (!sha1(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11", digest)) {
    return {};
  }
  return base64_text(digest, 20);
}

std::string ipad_base64(const unsigned char *data, size_t size)
{
  return base64_text(data, size);
}

std::string ipad_websocket_frame(const std::string &payload, int opcode)
{
  std::string frame;
  frame += char(0x80 | (opcode & 0x0f));
  const uint64_t n = payload.size();
  if (n < 126) {
    frame += char(n);
  }
  else if (n < 65536) {
    frame += char(126);
    frame += char((n >> 8) & 0xff);
    frame += char(n & 0xff);
  }
  else {
    frame += char(127);
    for (int i = 7; i >= 0; i--) {
      frame += char((n >> (i * 8)) & 0xff);
    }
  }
  return frame + payload;
}

int ipad_server_start(int port, const std::string &root)
{
  if (g_server.running) {
    return g_server.port;
  }
  WSADATA wsa;
  if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
    report(ReportType::Error, "Draw on iPad: networking isn't available");
    return 0;
  }
  /* 128 random bits, new each time it starts: a page scanned before can't come back. */
  std::random_device random;
  char token[33];
  for (int i = 0; i < 4; i++) {
    std::snprintf(token + i * 8, 9, "%08x", unsigned(random()));
  }
  const SOCKET listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  sockaddr_in address{};
  address.sin_family = AF_INET;
  /* The network, so the iPad can reach it. */
  address.sin_addr.s_addr = htonl(INADDR_ANY);
  address.sin_port = htons(static_cast<u_short>(port));
  BOOL exclusive = TRUE;
  setsockopt(listener, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, reinterpret_cast<const char *>(&exclusive), sizeof(exclusive));
  bool bound = listener != INVALID_SOCKET && bind(listener, reinterpret_cast<sockaddr *>(&address), sizeof(address)) == 0;
  if (!bound && listener != INVALID_SOCKET && port != 0) {
    address.sin_port = 0;
    bound = bind(listener, reinterpret_cast<sockaddr *>(&address), sizeof(address)) == 0;
  }
  if (!bound || listen(listener, 8) != 0) {
    if (listener != INVALID_SOCKET) {
      closesocket(listener);
    }
    WSACleanup();
    report(ReportType::Error, "Draw on iPad: couldn't listen on the network");
    return 0;
  }
  int length = sizeof(address);
  getsockname(listener, reinterpret_cast<sockaddr *>(&address), &length);
  g_server.token = token;
  g_server.root = std::filesystem::path(reinterpret_cast<const char8_t *>(root.c_str()));
  g_server.host = lan_address();
  g_server.listener = listener;
  g_server.port = ntohs(address.sin_port);
  g_server.inbox.clear();
  g_server.running = true;
  g_server.accept_thread = std::thread(accept_loop);
  report(ReportType::Info, "Draw on iPad: open " + ipad_server_url(), false);
  return g_server.port;
}

void ipad_server_stop()
{
  if (!g_server.running) {
    return;
  }
  g_server.running = false;
  closesocket(g_server.listener);
  if (g_server.accept_thread.joinable()) {
    g_server.accept_thread.join();
  }
  {
    std::lock_guard lock(g_server.mutex);
    for (const SOCKET s : g_server.sockets) {
      /* Its reader and writer find it closed and end. */
      shutdown(s, SD_BOTH);
      closesocket(s);
    }
    g_server.sockets.clear();
  }
  for (int i = 0; i < 300 && g_server.serving > 0; i++) {
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  {
    std::lock_guard lock(g_server.mutex);
    g_server.clients.clear();
    g_server.inbox.clear();
  }
  g_server.port = 0;
  g_server.token.clear();
  WSACleanup();
}

bool ipad_server_running()
{
  return g_server.running;
}

int ipad_server_port()
{
  return g_server.running ? g_server.port : 0;
}

std::string ipad_server_token()
{
  return g_server.running ? g_server.token : std::string();
}

std::string ipad_server_host()
{
  return g_server.running ? g_server.host : std::string();
}

std::string ipad_server_url()
{
  if (!g_server.running) {
    return {};
  }
  return "http://" + g_server.host + ":" + std::to_string(g_server.port) + "/?k=" + g_server.token;
}

int ipad_server_clients()
{
  std::lock_guard lock(g_server.mutex);
  return int(g_server.clients.size());
}

std::vector<IpadMessage> ipad_server_take()
{
  std::lock_guard lock(g_server.mutex);
  std::vector<IpadMessage> out(std::make_move_iterator(g_server.inbox.begin()),
                               std::make_move_iterator(g_server.inbox.end()));
  g_server.inbox.clear();
  return out;
}

void ipad_server_send(int client, const std::string &text)
{
  std::vector<std::shared_ptr<Client>> to;
  {
    std::lock_guard lock(g_server.mutex);
    for (const auto &[id, c] : g_server.clients) {
      if (client == 0 || id == client) {
        to.push_back(c);
      }
    }
  }
  if (to.empty()) {
    return;
  }
  const std::string frame = ipad_websocket_frame(text);
  for (const auto &c : to) {
    client_queue(*c, frame);
  }
}

}  // namespace oanim
