#pragma once

/* Hold to Shape, as Procreate's QuickShape: a freehand line held still at its end for a moment becomes a straight line
 * from its start to the pen, or, if it came round to near where it started, the ellipse that fits it best. While the
 * pen stays down it moves the line's end, or scales and turns the ellipse about its centre; once lifted the shape keeps
 * handles until the next stroke (editors/viewport.cc, draw.quick_shape in ops/draw_ops.cc). Nothing here knows about
 * the window. */

#include <string>
#include <vector>

#include "core/math.hh"
#include "data/ink_stroke.hh"

namespace oanim {

/* How long (seconds) the pen holds still, within QUICK_SHAPE_STILL_PIXELS, before the line snaps. */
inline constexpr double QUICK_SHAPE_HOLD_SECONDS = 0.55;
inline constexpr float QUICK_SHAPE_STILL_PIXELS = 4.0f;

struct QuickShape {
  enum class Kind { Line, Ellipse };
  Kind kind = Kind::Line;
  /* A line's ends (layer space). */
  float2 a, b;
  /* An ellipse's centre, its two radii, and the way its first one points (radians, anticlockwise from across);
   * as a circle both radii are their mean. */
  float2 center;
  float2 radii;
  float angle = 0.0f;
  bool circle = false;
};

/* What a line of `points` (layer space) held at `end` becomes; `pixel`: layer units a screen pixel stands for. False
 * when it is too short to be a shape. */
bool quick_shape_fit(const std::vector<float2> &points, float2 end, float pixel, QuickShape *r_shape);
/* The ellipse's radii as drawn (a circle's both their mean). */
float2 quick_shape_radii(const QuickShape &shape);
/* Its Bezier points, each `radius` wide (a fraction of the line's width): two corners for a line, four smooth
 * points round an ellipse (closed). */
std::vector<InkKnot> quick_shape_knots(const QuickShape &shape, float radius);
/* Places along it, for drawing it while the pen is down (closed for an ellipse). */
std::vector<float2> quick_shape_outline(const QuickShape &shape, int steps = 72);
/* Where its handles are: a line's two ends and its middle; an ellipse's four axis ends (first radius, second, then
 * their opposites) and its centre, last. */
std::vector<float2> quick_shape_handles(const QuickShape &shape);
/* `shape` with handle `handle` (as quick_shape_handles orders them) dragged to `p`: a line's end moves, its middle
 * moves it all; an ellipse's axis end sets that radius and turns it (a circle's sets both), its centre moves it. */
QuickShape quick_shape_handle_moved(const QuickShape &shape, int handle, float2 p);
/* While still held: a line's end at `pen`, Shift (`snap`) keeping its angle to 15 degree steps; an ellipse scaled
 * and turned about its centre as the pen goes from `from` to `pen`, Shift making it a circle. */
QuickShape quick_shape_held(const QuickShape &snapped, float2 from, float2 pen, bool snap);

/* As the operator's options, and back. */
void quick_shape_args(const QuickShape &shape, std::vector<std::pair<std::string, std::string>> &r_args);

}  // namespace oanim
