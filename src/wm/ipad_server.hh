#pragma once

/* Draw on iPad (Window > Draw on iPad...): a small web server on this computer's network that an iPad opens by
 * scanning a QR code. It serves the drawing page (scripts/ipad) and talks to it over a WebSocket, a JSON text message
 * at a time; what the messages do is oanim.ipad's (scripts/modules/oanim/ipad.py), run on the main loop.
 *
 * Unlike remote control (wm/remote.hh) it listens on the network, not only this computer, so the page's socket must
 * bring the one-time key the QR code holds (new each time the server starts); the page's own files are served to
 * anyone, as they hold nothing of the document. */

#include <string>
#include <vector>

namespace oanim {

/* Starts listening on `port` (any free one when it is taken, or 0), serving the page from `root` (a folder of
 * files). Returns the port, 0 if it could not start. */
int ipad_server_start(int port, const std::string &root);
void ipad_server_stop();
bool ipad_server_running();
int ipad_server_port();
/* The one-time key the page's socket must bring ("" when stopped). */
std::string ipad_server_token();
/* This computer's address on its network (the one its traffic goes out by), "127.0.0.1" with none. */
std::string ipad_server_host();
/* What the QR code holds: http://<host>:<port>/?k=<key>. */
std::string ipad_server_url();
/* Pages connected now. */
int ipad_server_clients();

/* A message from a page: its connection (1, 2, ...) and text. A page connecting or going is a message too:
 * {"t":"_open"} and {"t":"_close"}. */
struct IpadMessage {
  int client = 0;
  std::string text;
};
/* The messages come in since last taken, oldest first. */
std::vector<IpadMessage> ipad_server_take();
/* Sends a text message to one page, or to all (`client` 0). Queued: a page that has stopped reading never holds up
 * the caller. */
void ipad_server_send(int client, const std::string &text);

/* Helpers, here to be tested: the WebSocket handshake's Sec-WebSocket-Accept for a key, and a frame as the server
 * sends it (unmasked). */
std::string ipad_websocket_accept(const std::string &key);
std::string ipad_websocket_frame(const std::string &payload, int opcode = 1);
std::string ipad_base64(const unsigned char *data, size_t size);

}  // namespace oanim
