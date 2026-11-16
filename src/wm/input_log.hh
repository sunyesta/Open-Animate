#pragma once

/* A log of the window's mouse and pen input, off unless asked for (oanim.wm.input_log): Windows' own messages as the
 * window gets them, with the mark Windows puts on mouse messages a pen or touch made (GetMessageExtraInfo), and the
 * events SDL makes of them. For finding out what a tablet's driver sends: a mouse move that is the pen but not marked
 * as it makes the mouse the pointer (wm/pointer_track.hh) and the pressure full. */

#include <cstdint>
#include <string>
#include <vector>

namespace oanim {

struct InputLogEntry {
  /* Seconds, on the pen's clock (pen_now). */
  double time = 0.0;
  /* "WM_MOUSEMOVE", "SDL_MOUSE_MOTION", ... */
  std::string what;
  /* SDL's mouse or pen id; for a Windows message, its pointer id (pointer messages) or 0. */
  uint64_t which = 0;
  /* Window units for SDL's events, client pixels for Windows'. */
  float x = 0.0f, y = 0.0f;
  /* A button (SDL: 1 left, 3 right), or a pointer message's input type (2 touch, 3 pen, 4 mouse). */
  int button = 0;
  /* Windows' mark on a mouse message (0xFF515700 in its top 24 bits: made by a pen or touch, bit 7 touch), or
   * an event's own flag (an SDL pen event's pen state; SDL_EVENT_MOUSE_MOTION's button state). */
  uint32_t extra = 0;
  /* Dropped before ImGui saw it (a stray cursor report, a release held back while the pen is down). */
  bool dropped = false;
};

/* Starts (clearing what was logged) or stops logging. */
void input_log_set(bool on);
bool input_log_on();
void input_log_add(const char *what, uint64_t which, float x, float y, int button, uint32_t extra, bool dropped = false);
/* What has been logged since last taken, oldest first, and clears it. At most 500000 kept (the oldest go). */
std::vector<InputLogEntry> input_log_take();

}  // namespace oanim
