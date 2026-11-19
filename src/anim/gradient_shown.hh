#pragma once

/* A gradient layer as it shows now: its path with the bones and modifiers worked out, and the camera frame it fills,
 * both in the space it is drawn in. The renderer, the viewport's ticks and Python's samples all read it from here, so
 * they agree. */

#include "core/math.hh"
#include "data/gradient.hh"

namespace oanim {

struct Document;
struct Layer;

struct GradientShown {
  GradientField field;
  /* The space the field is in to document space. */
  Transform2D to_document;
  /* The camera frame in that space: bottom left, bottom right, top right, top left. */
  float2 frame[4];
};

GradientShown gradient_shown(const Document &doc, const Layer &layer, bool render);
/* A tick (`span` >= 0: that span's midpoint) or the Squash handle (`span` -1) dragged to `at` (document space): the
 * value it takes, the place on the span nearest `at` or how far across the path `at` is. */
float gradient_handle_value(const Document &doc, const Layer &layer, int span, float2 at);

}  // namespace oanim
