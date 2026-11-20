#include "data/fill_paint.hh"

#include <algorithm>
#include <cfloat>

#include "anim/shape_tree.hh"

#include "data/ink_stroke.hh"

namespace oanim {

/* What a shape's fill covers. */
static std::vector<FillPiece> shape_area(const VectorDrawing &drawing, const Shape &shape, float pixel)
{
  return fill_area(shape_fill_loops(drawing, shape, 12, pixel * 0.1f), shape.fill_rule);
}

/* The pieces as shapes on new curves, each like `like`, filled and without an outline. */
static std::vector<Shape> pieces_to_shapes(VectorDrawing &drawing, const std::vector<FillPiece> &pieces, const Shape &like,
                                           float pixel, float tolerance)
{
  std::vector<Shape> shapes;
  for (const FillPiece &piece : pieces) {
    Shape shape = like;
    shape.edges.clear();
    shape.id = 0;
    shape.has_fill = true;
    shape.has_outline = false;
    shape.fill_rule = piece.rings.size() > 1 ? FillRule::EvenOdd : FillRule::Loops;
    for (const std::vector<float2> &ring : piece.rings) {
      const std::vector<InkKnot> knots = ink_fit_ring(ring, tolerance, pixel);
      if (knots.size() < 3) {
        continue;
      }
      Curve curve;
      curve.closed = true;
      for (const InkKnot &knot : knots) {
        CurvePoint cp{drawing_add_point(drawing, knot.pos)};
        cp.curvature = knot.corner ? CURVATURE_PEAKED : CURVATURE_SMOOTH;
        cp.aligned = !knot.corner;
        curve_point_set_handles(cp, knot.handle_in, knot.handle_out);
        curve.points.push_back(cp);
      }
      drawing.curves.push_back(std::move(curve));
      for (int s = 0; s < drawing.curves.back().segment_count(); s++) {
        shape.edges.push_back({int(drawing.curves.size()) - 1, s});
      }
    }
    if (!shape.edges.empty()) {
      shapes.push_back(std::move(shape));
    }
  }
  return shapes;
}

/* Takes away the curves the shapes in `was` ran along that no shape runs along now, and their points. */
static void remove_curves_left(VectorDrawing &drawing, const std::vector<Shape> &was)
{
  std::vector<bool> used(drawing.curves.size(), false), remove(drawing.curves.size(), false);
  for (const Shape &shape : drawing.shapes) {
    for (const ShapeEdge &edge : shape.edges) {
      used[edge.curve] = true;
    }
  }
  for (const Shape &shape : was) {
    for (const ShapeEdge &edge : shape.edges) {
      remove[edge.curve] = !used[edge.curve];
    }
  }
  drawing_remove_curves(drawing, remove);
  drawing_remove_unused_points(drawing);
}

/* How far `p` is from a shape's outline, and whether it is inside one of its loops. */
static float outline_distance(const VectorDrawing &drawing, const Shape &shape, float2 p)
{
  float best = FLT_MAX;
  std::vector<float2> outline;
  for (const Shape &run : shape_runs(drawing, shape)) {
    bool closed = false;
    shape_outline(drawing, run, 12, outline, nullptr, &closed);
    const size_t n = outline.size();
    for (size_t i = 0; i + 1 < n + (closed ? 1 : 0); i++) {
      const float2 a = outline[i], b = outline[(i + 1) % n];
      const float2 ab = b - a;
      const float len2 = dot(ab, ab);
      const float t = len2 > 0.0f ? std::clamp(dot(p - a, ab) / len2, 0.0f, 1.0f) : 0.0f;
      best = std::min(best, length(p - (a + ab * t)));
    }
    if (n == 1) {
      best = std::min(best, length(p - outline[0]));
    }
  }
  return best;
}

int drawing_fill_start_shape(const VectorDrawing &drawing, float2 start, float reach)
{
  for (int s = int(drawing.shapes.size()) - 1; s >= 0; s--) {
    const Shape &shape = drawing.shapes[size_t(s)];
    if (shape.hidden || !shape.shown || shape.edges.empty()) {
      continue;
    }
    if (shape_fill_contains(drawing, shape, start)) {
      return s;
    }
    if (shape.has_outline && outline_distance(drawing, shape, start) <= std::max(reach, shape.style.line_width * 0.5f)) {
      return s;
    }
  }
  return -1;
}

/* Works `area` into shape `s` as a sub shape of it doing `op`, applied: its points stay where its outline doesn't
 * change, new ones going in where it does. False when that can't be done (it doesn't go round, or nothing is left:
 * `r_empty`), the drawing left as it was. */
static bool shape_work_in(VectorDrawing &drawing, int s, const std::vector<FillPiece> &area, ShapeOp op, float pixel,
                          float tolerance, bool *r_empty)
{
  *r_empty = false;
  if (!shape_closed_all(drawing, drawing.shapes[size_t(s)])) {
    return false;
  }
  const VectorDrawing was = drawing;
  Shape like;
  like.name = "Fill";
  std::vector<Shape> made = pieces_to_shapes(drawing, area, like, pixel, tolerance);
  if (made.empty()) {
    drawing = was;
    return false;
  }
  /* Its lowest sub shapes, so they act first and only they are applied. */
  for (Shape &m : made) {
    m.parent = drawing.shapes[size_t(s)].id;
    m.op = op;
  }
  const int n = int(made.size());
  drawing.shapes.insert(drawing.shapes.begin() + s + 1, made.begin(), made.end());
  drawing_ensure_ids(drawing);
  bool empty = false;
  shape_tree_solve(drawing, s, s + n, &empty);
  if (empty || !drawing_shape_apply(drawing, s + n)) {
    drawing = was;
    *r_empty = empty;
    return false;
  }
  return true;
}

void drawing_fill_paint(VectorDrawing &drawing, const std::vector<FillPiece> &area, const Style &style, float pixel,
                        float tolerance, float2 start)
{
  const int s = drawing_fill_start_shape(drawing, start, pixel * 4.0f);
  if (s >= 0) {
    bool empty = false;
    if (shape_work_in(drawing, s, area, ShapeOp::Union, pixel, tolerance, &empty)) {
      Shape &grown = drawing.shapes[size_t(s)];
      if (!grown.has_fill) {
        grown.has_fill = true;
        grown.style.fill = style.fill;
      }
      return;
    }
    /* A line that doesn't go round: the area is a loop of its own in it, filled in the pen's colour (its line going
     * round that too). */
    Shape like;
    std::vector<Shape> made = pieces_to_shapes(drawing, area, like, pixel, tolerance);
    Shape &line = drawing.shapes[size_t(s)];
    for (const Shape &m : made) {
      line.edges.insert(line.edges.end(), m.edges.begin(), m.edges.end());
    }
    if (!made.empty() && !line.has_fill) {
      line.has_fill = true;
      line.style.fill = style.fill;
    }
    return;
  }
  /* Started on nothing: a new shape on top. */
  Shape like;
  like.style = style;
  like.name = "Fill " + std::to_string(drawing.shapes.size() + 1);
  std::vector<Shape> made = pieces_to_shapes(drawing, area, like, pixel, tolerance);
  drawing.shapes.insert(drawing.shapes.end(), made.begin(), made.end());
  drawing_ensure_ids(drawing);
}

bool drawing_fill_erase(VectorDrawing &drawing, const std::vector<FillPiece> &area, float pixel, float tolerance,
                        float2 start, bool selected_only)
{
  const int s = drawing_fill_start_shape(drawing, start, pixel * 4.0f);
  if (s < 0 || !drawing.shapes[size_t(s)].has_fill ||
      (selected_only && !drawing_selected_shapes(drawing)[size_t(s)]))
  {
    return false;
  }
  if (!fill_overlap(shape_area(drawing, drawing.shapes[size_t(s)], pixel), area)) {
    return false;
  }
  bool empty = false;
  if (shape_work_in(drawing, s, area, ShapeOp::Subtract, pixel, tolerance, &empty)) {
    return true;
  }
  if (!empty) {
    return false;
  }
  /* All of it erased: it goes (its sub shapes back into the list, under its parent). */
  const Shape gone = drawing.shapes[size_t(s)];
  for (Shape &other : drawing.shapes) {
    if (other.parent == gone.id) {
      other.parent = gone.parent;
    }
  }
  drawing.shapes.erase(drawing.shapes.begin() + s);
  remove_curves_left(drawing, {gone});
  drawing_shape_tree_mend(drawing);
  return true;
}

}  // namespace oanim
