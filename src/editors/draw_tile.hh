#pragma once

/* A Draw shelf tile's picture as data (editors/draw_shelf.cc draws it; the iPad's shelf, wm/ipad_link.cc, draws
 * the same): its sample line made by the engine from the pen's settings, or a drawing of what an eraser does. */

#include <vector>

#include "core/math.hh"

namespace oanim {

struct DrawPreset;
struct ToolSettings;

/* A line through `points` (tile pixels, y down), `widths` its half width at each; `opacity` (empty: solid) fades it
 * point by point. A plain one is one width throughout, drawn as an ordinary polyline. */
struct TileStroke {
  std::vector<float2> points;
  std::vector<float> widths;
  std::vector<float> opacity;
  Color color;
  bool plain = false;
};
struct TileRect {
  float2 a, b;
  Color color;
  float rounding = 0.0f;
};
/* A point (a square) or a handle (a circle). */
struct TileDot {
  float2 c;
  float r = 1.0f;
  Color color;
  bool square = false;
};
struct TilePicture {
  std::vector<TileRect> rects;
  std::vector<TileStroke> strokes;
  std::vector<TileDot> dots;
};

/* Pen `p`'s tile picture, `size` pixels square: its settings as they are now (the active one's as the header has
 * them, another's as last changed to). */
TilePicture draw_tile_picture(const ToolSettings &ts, const DrawPreset &p, float size);

}  // namespace oanim
