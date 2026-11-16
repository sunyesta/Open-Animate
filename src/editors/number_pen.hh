#pragma once

/* A number field scrubbed with a pen (editors/number_field.cc). The mouse's scrub hides the cursor and reads only how
 * far the mouse moves, then puts the cursor back where the drag began; a pen can't be read that way (it says where it
 * is on the tablet, and never moves the system cursor), so a pen's scrub follows the pen with the cursor shown. Shift
 * is awkward with a pen in hand: moving the pen up or down off the field's row makes each pixel across count for less.
 * The tablet runs out sooner than a mouse pad, so lifting the pen and putting it back on the same field at once carries
 * on the same drag, one undo step. */

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace oanim {

/* How far a pen goes before a press becomes a drag (UI units): more than the mouse's 3, as a pen's tip wobbles a few
 * pixels as it touches down, so a tap to type never nudges the value first. */
inline float number_pen_threshold(float field_height)
{
  return std::max(6.0f, field_height * 0.3f);
}

/* How much of each pixel across counts, from how far the pen is above or below the row the drag began on (`dy`, UI
 * units): all of it on the row, half two field heights off it, a quarter at six, a tenth at most (as Shift). */
inline double number_pen_fineness(float dy, float field_height)
{
  const float h = std::max(field_height, 1.0f);
  const float off = std::max(std::fabs(dy) - h * 0.5f, 0.0f);
  return std::max(1.0 / (1.0 + double(off) / (2.0 * double(h))), 0.1);
}

/* The pen put back on the field within this long of lifting off it mid-drag carries on that drag. */
constexpr double NUMBER_PEN_CLUTCH_SECONDS = 0.5;

/* The field a pen was last lifted off mid-drag (0: none), and when (seconds). */
struct NumberClutch {
  uint32_t id = 0;
  double lifted = 0.0;
};

/* Whether a pen press on field `id` at `now` carries on the drag it was lifted from. */
inline bool number_clutch_resumes(const NumberClutch &c, uint32_t id, double now)
{
  return c.id != 0 && c.id == id && now >= c.lifted && now - c.lifted <= NUMBER_PEN_CLUTCH_SECONDS;
}

}  // namespace oanim
