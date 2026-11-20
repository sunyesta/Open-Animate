/* The shape tree's operators (anim/shape_tree.hh): making a shape a sub shape of another (a drop onto its row in the
 * Shapes list) and taking it out again, its Operation, Smoothing and eye, and Apply. */

#include "ops/shape_tree_ops.hh"

#include <algorithm>
#include <cstdlib>
#include <string>

#include "anim/animation.hh"
#include "anim/shape_tree.hh"
#include "core/log.hh"
#include "data/document.hh"
#include "data/layer.hh"
#include "ops/edit_ops.hh"
#include "ops/operator.hh"
#include "ops/undo.hh"
#include "wm/context.hh"

namespace oanim {

static constexpr unsigned UNDO = OPTYPE_REGISTER | OPTYPE_UNDO;

/* The layer an operator works on (layer=, else the active one), if it has a drawing of its own. */
static Layer *tree_layer(Context &C)
{
  Document &doc = *C.document;
  Layer *layer = op_has_arg(C, "layer") ? layer_by_name_or_id(doc, op_arg(C, "layer")) : document_active_layer(doc);
  if (!layer || !layer->has_drawing()) {
    report(ReportType::Error, "No layer with a drawing");
    return nullptr;
  }
  if (layer->is_reference()) {
    report(ReportType::Warning, "A copy (reference layer) keeps its original's shapes: Break Reference to change them");
    return nullptr;
  }
  if (layer->is_gradient()) {
    report(ReportType::Warning, "A gradient's one path is its colour stops");
    return nullptr;
  }
  return layer;
}

/* A shape named by name, id, or (from the active one) nothing: its index, or -1. */
static int shape_named(const Document &doc, const Layer &layer, const std::string &text)
{
  const VectorDrawing &d = layer.drawing;
  if (text.empty()) {
    return doc.active_shape_layer == layer.id ? drawing_shape_index(d, doc.active_shape) : -1;
  }
  for (int s = 0; s < int(d.shapes.size()); s++) {
    if (d.shapes[s].name == text) {
      return s;
    }
  }
  char *end = nullptr;
  const unsigned long long id = std::strtoull(text.c_str(), &end, 10);
  return end && *end == '\0' ? drawing_shape_index(d, uint64_t(id)) : -1;
}

static int shape_arg(Context &C, const Layer &layer, const char *key)
{
  const int s = shape_named(*C.document, layer, op_arg(C, key, ""));
  if (s < 0) {
    report(ReportType::Error, op_arg(C, key, "").empty() ? "No active shape" : layer.name + " has no shape \"" +
                                                                                    op_arg(C, key, "") + "\"");
  }
  return s;
}

/* Moves the shapes at `members` (a tree, keeping its order) to stand together just above index `above` (one not among
 * them; -1: at the bottom). */
static void shapes_move_together(VectorDrawing &d, std::vector<int> members, int above)
{
  std::sort(members.begin(), members.end());
  std::vector<Shape> moved;
  for (const int m : members) {
    moved.push_back(d.shapes[size_t(m)]);
  }
  const uint64_t anchor = above >= 0 ? d.shapes[size_t(above)].id : 0;
  for (auto it = members.rbegin(); it != members.rend(); ++it) {
    d.shapes.erase(d.shapes.begin() + *it);
  }
  const int at = anchor != 0 ? drawing_shape_index(d, anchor) + 1 : 0;
  d.shapes.insert(d.shapes.begin() + at, moved.begin(), moved.end());
}

/* Puts shape `s` (with its own tree) under shape `p` as its sub shape, on top of the ones already there. */
static OpStatus make_sub_shape(Context &C, VectorDrawing &d, int s, int p)
{
  if (p == s || shape_is_under(d, p, d.shapes[size_t(s)].id)) {
    report(ReportType::Error, "A shape can't go under itself or one of its own sub shapes");
    return OpStatus::Cancelled;
  }
  if (!shape_closed_all(d, d.shapes[size_t(s)]) || !shape_closed_all(d, d.shapes[size_t(p)])) {
    report(ReportType::Error, "Only closed shapes can be sub shapes or have them");
    return OpStatus::Cancelled;
  }
  if (d.shapes[size_t(s)].parent == d.shapes[size_t(p)].id) {
    return OpStatus::Cancelled;
  }
  const std::vector<int> members = shape_tree_members(d, s);
  /* On top of the parent's tree (as it is before this joins it): the last to act on it. A shape already under it
   * moves up too. */
  int top = p;
  for (const int m : shape_tree_members(d, p)) {
    if (std::find(members.begin(), members.end(), m) == members.end()) {
      top = std::max(top, m);
    }
  }
  Shape &shape = d.shapes[size_t(s)];
  shape.parent = d.shapes[size_t(p)].id;
  shape.op = ShapeOp::Union;
  shapes_move_together(d, members, top);
  C.undo_name = "Make Sub Shape";
  return OpStatus::Finished;
}

static bool shape_op_from(const std::string &text, ShapeOp *r_op)
{
  static const std::pair<const char *, ShapeOp> NAMES[] = {
      {"UNION", ShapeOp::Union}, {"SUBTRACT", ShapeOp::Subtract}, {"INTERSECT", ShapeOp::Intersect},
      {"EXCLUDE", ShapeOp::Exclude}};
  for (const auto &[name, op] : NAMES) {
    if (text == name) {
      *r_op = op;
      return true;
    }
  }
  return false;
}

static void tree_operator(const char *idname, const char *name, const char *description,
                          std::function<OpStatus(Context &)> exec, std::vector<OpProperty> props = {})
{
  OperatorType ot;
  ot.idname = idname;
  ot.name = name;
  ot.description = description;
  ot.flag = UNDO;
  ot.poll = [](Context &C) { return C.document != nullptr; };
  ot.exec = std::move(exec);
  ot.props = std::move(props);
  operators().add(std::move(ot));
}

void shape_tree_operators_register()
{
  tree_operator(
      "mesh.shape_parent_set", "Make Sub Shape",
      "Put a closed shape (shape=, by name or id; else the active one) under another closed shape (parent=) as its "
      "sub shape, Union until changed; with no parent, take it out into the list again with its own look",
      [](Context &C) {
        Layer *layer = tree_layer(C);
        if (!layer) {
          return OpStatus::Cancelled;
        }
        VectorDrawing &d = layer->drawing;
        const int s = shape_arg(C, *layer, "shape");
        if (s < 0) {
          return OpStatus::Cancelled;
        }
        const std::string parent_text = op_arg(C, "parent", "");
        if (parent_text.empty()) {
          /* Take Out of Parent: just above the tree it was in, with the look it kept. */
          if (d.shapes[size_t(s)].parent == 0) {
            return OpStatus::Cancelled;
          }
          const std::vector<int> members = shape_tree_members(d, s);
          /* The top of the tree it leaves, not counting what goes with it. */
          int top = shape_tree_root(d, s);
          for (const int m : shape_tree_members(d, top)) {
            if (std::find(members.begin(), members.end(), m) == members.end()) {
              top = std::max(top, m);
            }
          }
          d.shapes[size_t(s)].parent = 0;
          shapes_move_together(d, members, top);
          C.undo_name = "Take Out of Parent";
          return OpStatus::Finished;
        }
        const int p = shape_named(*C.document, *layer, parent_text);
        if (p < 0) {
          report(ReportType::Error, layer->name + " has no shape \"" + parent_text + "\"");
          return OpStatus::Cancelled;
        }
        return make_sub_shape(C, d, s, p);
      });

  tree_operator(
      "mesh.shape_move", "Move Shape",
      "Move a shape (shape=), with its sub shapes, in the stacking order: place=ABOVE or BELOW another (target=), "
      "beside it under the shape it is under, or INTO it as its sub shape",
      [](Context &C) {
        Layer *layer = tree_layer(C);
        if (!layer) {
          return OpStatus::Cancelled;
        }
        VectorDrawing &d = layer->drawing;
        const int s = shape_arg(C, *layer, "shape");
        const int t = s >= 0 ? shape_named(*C.document, *layer, op_arg(C, "target", "")) : -1;
        if (s < 0 || t < 0) {
          if (s >= 0) {
            report(ReportType::Error, layer->name + " has no shape \"" + op_arg(C, "target", "") + "\"");
          }
          return OpStatus::Cancelled;
        }
        const std::string place = op_arg(C, "place", "ABOVE");
        if (place == "INTO") {
          return make_sub_shape(C, d, s, t);
        }
        if (place != "ABOVE" && place != "BELOW") {
          report(ReportType::Error, "place is ABOVE, BELOW or INTO");
          return OpStatus::Cancelled;
        }
        if (t == s || shape_is_under(d, t, d.shapes[size_t(s)].id)) {
          return OpStatus::Cancelled;
        }
        const uint64_t parent = d.shapes[size_t(t)].parent;
        if (parent != 0 && !shape_closed_all(d, d.shapes[size_t(s)])) {
          report(ReportType::Error, "Only closed shapes can be sub shapes");
          return OpStatus::Cancelled;
        }
        std::vector<std::pair<uint64_t, uint64_t>> before;
        for (const Shape &x : d.shapes) {
          before.emplace_back(x.id, x.parent);
        }
        const std::vector<int> members = shape_tree_members(d, s);
        const auto moving = [&](int i) { return std::find(members.begin(), members.end(), i) != members.end(); };
        /* Above: over the target's whole tree. Below: under the target itself (the lowest of its tree), so beside
         * it among the sub shapes of the one it is under. */
        int anchor = -1;
        if (place == "ABOVE") {
          anchor = t;
          for (const int m : shape_tree_members(d, t)) {
            if (!moving(m)) {
              anchor = std::max(anchor, m);
            }
          }
        }
        else {
          for (int i = t - 1; i >= 0; i--) {
            if (!moving(i)) {
              anchor = i;
              break;
            }
          }
        }
        Shape &shape = d.shapes[size_t(s)];
        if (shape.parent == 0 && parent != 0) {
          shape.op = ShapeOp::Union;
        }
        shape.parent = parent;
        shapes_move_together(d, members, anchor);
        std::vector<std::pair<uint64_t, uint64_t>> after;
        for (const Shape &x : d.shapes) {
          after.emplace_back(x.id, x.parent);
        }
        if (after == before) {
          return OpStatus::Cancelled;
        }
        return OpStatus::Finished;
      });

  tree_operator(
      "mesh.shape_op_set", "Set Operation",
      "What a sub shape (shape=) does to the shape it is under: op=UNION, SUBTRACT, INTERSECT or EXCLUDE",
      [](Context &C) {
        Layer *layer = tree_layer(C);
        if (!layer) {
          return OpStatus::Cancelled;
        }
        const int s = shape_arg(C, *layer, "shape");
        ShapeOp op = ShapeOp::Union;
        if (s < 0 || !shape_op_from(op_arg(C, "op", ""), &op)) {
          if (s >= 0) {
            report(ReportType::Error, "op is UNION, SUBTRACT, INTERSECT or EXCLUDE");
          }
          return OpStatus::Cancelled;
        }
        Shape &shape = layer->drawing.shapes[size_t(s)];
        if (shape.parent == 0) {
          report(ReportType::Error, "Only a sub shape has an Operation");
          return OpStatus::Cancelled;
        }
        if (shape.op == op) {
          return OpStatus::Cancelled;
        }
        shape.op = op;
        return OpStatus::Finished;
      });

  tree_operator(
      "mesh.shape_smoothing_set", "Set Smoothing",
      "How far a sub shape (shape=) rounds the corners where its outline crosses its parent's (value=, drawing units)",
      [](Context &C) {
        Layer *layer = tree_layer(C);
        if (!layer) {
          return OpStatus::Cancelled;
        }
        const int s = shape_arg(C, *layer, "shape");
        if (s < 0) {
          return OpStatus::Cancelled;
        }
        Shape &shape = layer->drawing.shapes[size_t(s)];
        if (shape.parent == 0) {
          report(ReportType::Error, "Only a sub shape has a Smoothing");
          return OpStatus::Cancelled;
        }
        const float value = std::clamp(op_arg_float(C, "value", shape.smoothing), 0.0f, SHAPE_SMOOTHING_MAX);
        if (value == shape.smoothing) {
          return OpStatus::Cancelled;
        }
        /* Edits not yet recorded belong to the frame they were made at. */
        animation_record(*C.document);
        shape.smoothing = value;
        return OpStatus::Finished;
      });

  tree_operator(
      "mesh.shape_show_set", "Show Shape",
      "Open or close a shape's eye (shape=; show=TRUE, FALSE or TOGGLE): closed, it isn't drawn, picked, or (a sub "
      "shape) acting on its parent",
      [](Context &C) {
        Layer *layer = tree_layer(C);
        if (!layer) {
          return OpStatus::Cancelled;
        }
        const int s = shape_arg(C, *layer, "shape");
        if (s < 0) {
          return OpStatus::Cancelled;
        }
        Shape &shape = layer->drawing.shapes[size_t(s)];
        const std::string show = op_arg(C, "show", "TOGGLE");
        const bool on = show == "TOGGLE" ? !shape.shown : show == "TRUE";
        if (show != "TOGGLE" && show != "TRUE" && show != "FALSE") {
          report(ReportType::Error, "show is TRUE, FALSE or TOGGLE");
          return OpStatus::Cancelled;
        }
        if (on == shape.shown) {
          return OpStatus::Cancelled;
        }
        shape.shown = on;
        C.undo_name = on ? "Show Shape" : "Hide Shape";
        return OpStatus::Finished;
      });

  tree_operator(
      "mesh.shape_apply", "Apply Sub Shape",
      "Bake a sub shape (shape=; else the active one) and the ones below it into the shape they are under: its points "
      "the outline still runs through stay, new points go in only where it changed",
      [](Context &C) {
        Layer *layer = tree_layer(C);
        if (!layer) {
          return OpStatus::Cancelled;
        }
        const int s = shape_arg(C, *layer, "shape");
        if (s < 0) {
          return OpStatus::Cancelled;
        }
        if (layer->drawing.shapes[size_t(s)].parent == 0) {
          report(ReportType::Error, "Only a sub shape can be applied");
          return OpStatus::Cancelled;
        }
        if (C.document->frame_current != 0) {
          report(ReportType::Warning, "Apply works on Setup (frame 0)");
          return OpStatus::Cancelled;
        }
        animation_record(*C.document);
        if (!drawing_shape_apply(layer->drawing, s)) {
          report(ReportType::Warning, "Nothing to apply: it is hidden, open, or leaves nothing");
          return OpStatus::Cancelled;
        }
        layer_touch(*layer);
        return OpStatus::Finished;
      });
}

}  // namespace oanim
