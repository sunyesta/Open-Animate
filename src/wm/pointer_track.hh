/* Which of the pen and the mouse is the pointer, so a pen stroke's end doesn't flash the cursor where the mouse was.
 *
 * The pen's own messages (WM_POINTER, read for its samples) never move the system cursor: it stays where the mouse
 * left it. When the pen lifts or leaves the window, Windows and SDL report that old place as the mouse moving there
 * (a WM_MOUSEMOVE, or ImGui's fallback reading the system cursor), and for a frame the cursor jumped back to it. While
 * the pen is the pointer, a mouse move to just where the cursor was left is that report, not the mouse: it is
 * dropped, and the pen's place kept. A mouse moved anywhere else is the mouse, and the pointer again. */

#pragma once

#include <cmath>

namespace oanim {

struct PointerTrack {
  /* The pen moved last (not the mouse since), at `pen_x`, `pen_y` (window units). */
  bool pen = false;
  float pen_x = 0.0f, pen_y = 0.0f;
  /* Where the system cursor was at the pen's last move: what a stray report gives (the mouse's old place, or the
   * pen's own where the cursor follows it). */
  float left_x = 0.0f, left_y = 0.0f;
};

/* How near a report must be to where the cursor was left (window units): a mouse moved less is still. */
constexpr float POINTER_STRAY_UNITS = 1.0f;

/* The pen moved to (x, y); `cursor_x`, `cursor_y`: where the system cursor is now (window units). */
inline void pointer_pen_moved(PointerTrack &t, float x, float y, float cursor_x, float cursor_y)
{
  t.left_x = cursor_x;
  t.left_y = cursor_y;
  t.pen = true;
  t.pen_x = x;
  t.pen_y = y;
}

/* Whether a mouse report at (x, y) is the cursor the pen left behind, not the mouse. */
inline bool pointer_stray(const PointerTrack &t, float x, float y)
{
  return t.pen && std::fabs(x - t.left_x) <= POINTER_STRAY_UNITS && std::fabs(y - t.left_y) <= POINTER_STRAY_UNITS;
}

/* The mouse reported at (x, y): false when it is the cursor left behind by the pen (drop it). */
inline bool pointer_mouse_moved(PointerTrack &t, float x, float y)
{
  if (pointer_stray(t, x, y)) {
    return false;
  }
  t.pen = false;
  return true;
}

}  // namespace oanim
