/* The shape tree: shapes under shapes, after Moho's Liquid Shapes and Figma's boolean groups. A sub shape
 * (Shape::parent) has no look of its own: its Operation (Union, Subtract, Intersect, Exclude) acts on what its parent
 * is so far, the lowest sub shape first, and its Smoothing rounds the corners where their outlines cross. The parent's
 * look covers the result.
 *
 * The result keeps the drawing's curves: Clipper2 works out what is left on fine samples of the outlines, each sample
 * tagged with the edge and place along it it came from, and every edge of the result is rebuilt from the original
 * Bezier, split where the outlines cross (found by Newton steps); roundings are cubics fitted in at the crossings. */

#pragma once

#include <cstdint>
#include <vector>

#include "core/math.hh"

namespace oanim {

struct Document;
struct VectorDrawing;

/* One place on a result outline, and the segment from it to the next. */
struct ShapeTreeNode {
  float2 pos;
  /* Its handles, as offsets from it. */
  float2 handle_in, handle_out;
  float radius = 1.0f, opacity = 1.0f;
  /* The drawing's point this is (an original point the outline still runs through), or -1 for a new place (where
   * outlines cross, or along a rounding); and the shape whose outline it is on (-1 along a rounding). */
  int point = -1;
  int shape = -1;
  /* The segment from here to the next node has its line off (the edge it came from had). */
  bool line_off = false;
};

struct ShapeTreeLoop {
  std::vector<ShapeTreeNode> nodes;
  /* Runs the other way round: a hole in the loop round it. */
  bool hole = false;
};

/* What shape `s` and the sub shapes under it leave (`upto`: only its sub shapes up to and including that one, by
 * index; -1 all). `r_empty` (optional) says nothing is left. Works on the drawing as it is (posed or setup). */
std::vector<ShapeTreeLoop> shape_tree_solve(const VectorDrawing &drawing, int s, int upto = -1,
                                            bool *r_empty = nullptr);

/* Works the shape tree out in an evaluated drawing: each shape with sub shapes takes the outline they leave as new
 * curves (its look kept), sub shapes are not drawn (still picked), shapes with their eye closed are hidden, and a
 * shape left with nothing is marked (Shape::tree_empty) and not drawn. Returns true if anything changed. Safe on
 * several threads at once (its cache is each thread's own). */
bool drawing_shape_tree_apply(VectorDrawing &drawing);

/* Apply: bakes sub shape `s` and the ones below it into their parent. The parent's points the outline still runs
 * through stay (the same points, with their keys and weights), new points go in only where it changed, a hole or an
 * island comes in as a loop of its own, and a line off along an edge stays off. The sub shapes applied go, with their
 * points. Works from the setup pose. Returns false (nothing changed) when `s` is no sub shape. */
bool drawing_shape_apply(VectorDrawing &drawing, int s);

/* drawing_shape_tree_mend on every drawing of the document. */
void document_shape_trees_mend(Document &doc);

}  // namespace oanim
