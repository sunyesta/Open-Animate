#include "anim/gradient_shown.hh"

#include <algorithm>
#include <cmath>

#include "anim/deform.hh"
#include "data/camera.hh"
#include "data/document.hh"
#include "data/layer.hh"

namespace oanim {

float gradient_handle_value(const Document &doc, const Layer &layer, int span, float2 at)
{
  const GradientShown shown = gradient_shown(doc, layer, false);
  const GradientField &f = shown.field;
  const GradientSettings &g = layer.gradient;
  if (span >= 0) {
    const float was = span + 1 < int(g.stops.size()) ? g.stops[size_t(span)].midpoint : 0.5f;
    if (!f.valid || span + 1 >= int(g.stops.size())) {
      return was;
    }
    /* A drag to a place no number reaches leaves it where it was. */
    const float v = gradient_span_fraction_nearest(f, span, shown.to_document.inverted().apply(at));
    return std::isfinite(v) ? v : was;
  }
  if (!f.valid) {
    return g.squash;
  }
  const float2 p = shown.to_document.inverted().apply(at);
  const float2 across(-f.start_dir.y, f.start_dir.x);
  const float v = dot(p - f.start, across) / f.total;
  return std::isfinite(v) ? std::clamp(v, 0.05f, 20.0f) : g.squash;
}

GradientShown gradient_shown(const Document &doc, const Layer &layer, bool render)
{
  GradientShown s;
  Transform2D rigid;
  const bool modified = layer_has_modifier_effect(doc, layer, render);
  const VectorDrawing evaluated = modified ? layer_evaluated_drawing(doc, layer, render, &rigid) : VectorDrawing();
  const VectorDrawing &drawing = modified ? evaluated : layer_drawing(doc, layer);
  s.to_document = layer_world_transform(doc, layer.id) * rigid;
  float2 corners[4];
  camera_frame_corners(doc, corners);
  const Transform2D to_space = s.to_document.inverted();
  for (int i = 0; i < 4; i++) {
    s.frame[i] = to_space.apply(corners[i]);
  }
  s.field = gradient_field(drawing, layer.gradient);
  return s;
}

}  // namespace oanim
