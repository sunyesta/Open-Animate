#pragma once

/* Gradient layers' operators (layer.new_gradient, gradient.*), and the guard that keeps their points from being added
 * or taken away by anything else (data/gradient.hh). */

#include <cstdint>
#include <functional>
#include <vector>

#include "data/gradient.hh"
#include "data/vector.hh"

namespace oanim {

struct Document;

void gradient_operators_register();

/* Every gradient layer's drawing and stops before an edit, to put back those it left broken (a point added or taken
 * away, a shape drawn on it): gradients_restore says how many. */
struct GradientsKept {
  struct Item {
    uint64_t layer = 0;
    VectorDrawing drawing;
    GradientSettings settings;
  };
  std::vector<Item> items;
};
GradientsKept gradients_keep(const Document &doc);
int gradients_restore(Document &doc, const GradientsKept &kept);
/* At an undo push, the last guard: a gradient left broken goes back to how the last step held it (`was`, the document
 * then, on the same frame), or is repaired. How many were. */
int gradients_check(Document &doc, const std::function<const Document &()> &was);

}  // namespace oanim
