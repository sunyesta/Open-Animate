#include "ops/gradient_ops.hh"

#include <algorithm>
#include <cstdlib>
#include <sstream>
#include <string>

#include "anim/gradient_shown.hh"
#include "core/log.hh"
#include "data/camera.hh"
#include "data/document.hh"
#include "data/layer.hh"
#include "ops/edit_ops.hh"
#include "ops/operator.hh"
#include "ops/undo.hh"
#include "wm/context.hh"

namespace oanim {

static const char *const GRADIENT_FIXED = "A gradient's points are its stops: add or remove them in its Gradient tab";

/* The stops as they were, each with what the edit set on it (a colour, a span's blend) where its point is still
 * there: putting the points back keeps the rest of the edit. */
static std::vector<GradientStop> stops_merged(const std::vector<GradientStop> &had, const std::vector<GradientStop> &now)
{
  std::vector<GradientStop> stops = had;
  for (GradientStop &s : stops) {
    const auto it = std::find_if(now.begin(), now.end(), [&](const GradientStop &n) { return n.point == s.point; });
    if (it != now.end()) {
      s = *it;
    }
  }
  return stops;
}

GradientsKept gradients_keep(const Document &doc)
{
  GradientsKept kept;
  for (const Layer *l : document_layers_flat(doc)) {
    /* One already broken (by a script's data edit) is left to the undo push's check, which has its last step. */
    if (l->is_gradient() && gradient_layer_valid(*l)) {
      kept.items.push_back({l->id, l->drawing, l->gradient});
    }
  }
  return kept;
}

int gradients_restore(Document &doc, const GradientsKept &kept)
{
  int restored = 0;
  for (const GradientsKept::Item &item : kept.items) {
    Layer *layer = layer_find(doc, item.layer);
    if (!layer || !layer->is_gradient() || gradient_layer_valid(*layer)) {
      continue;
    }
    layer->drawing = item.drawing;
    /* Its picks and settings as the edit left them; the stops as they were. */
    layer->gradient.stops = stops_merged(item.settings.stops, layer->gradient.stops);
    layer->gradient.active_stop = std::clamp(layer->gradient.active_stop, 0, int(item.settings.stops.size()) - 1);
    layer->gradient.active_span = std::clamp(layer->gradient.active_span, 0, int(item.settings.stops.size()) - 2);
    restored++;
  }
  if (restored > 0) {
    report(ReportType::Warning, GRADIENT_FIXED);
  }
  return restored;
}

int gradients_check(Document &doc, const std::function<const Document &()> &was)
{
  int fixed = 0;
  for (const Layer *flat : document_layers_flat(doc)) {
    if (!flat->is_gradient() || gradient_layer_valid(*flat)) {
      continue;
    }
    Layer &layer = *layer_find(doc, flat->id);
    const Document &before = was();
    const Layer *had = layer_find(before, layer.id);
    if (had && had->is_gradient() && gradient_layer_valid(*had) && before.frame_current == doc.frame_current) {
      layer.drawing = had->drawing;
      layer.gradient.stops = stops_merged(had->gradient.stops, layer.gradient.stops);
    }
    gradient_layer_repair(layer);
    fixed++;
  }
  if (fixed > 0) {
    report(ReportType::Warning, GRADIENT_FIXED);
  }
  return fixed;
}

static void add_operator(const char *idname, const char *name, const char *description,
                         std::function<bool(Context &)> poll, std::function<OpStatus(Context &)> exec,
                         int flag = OPTYPE_REGISTER | OPTYPE_UNDO)
{
  OperatorType ot;
  ot.idname = idname;
  ot.name = name;
  ot.description = description;
  ot.flag = flag;
  ot.poll = std::move(poll);
  ot.exec = std::move(exec);
  operators().add(std::move(ot));
}

/* The gradient named by layer= (its id or name), else the active layer if it is one. */
static Layer *gradient_layer(Context &C)
{
  if (!C.document) {
    return nullptr;
  }
  Layer *layer = op_has_arg(C, "layer") ? layer_by_name_or_id(*C.document, op_arg(C, "layer"))
                                        : document_active_layer(*C.document);
  return layer && layer->is_gradient() ? layer : nullptr;
}

/* "#rrggbb", "#rrggbbaa" or "r, g, b[, a]" (0-1). */
static bool parse_color(const std::string &text, Color *r_color)
{
  if (!text.empty() && text[0] == '#' && (text.size() == 7 || text.size() == 9)) {
    char *end = nullptr;
    const unsigned long v = std::strtoul(text.c_str() + 1, &end, 16);
    if (!end || *end != '\0') {
      return false;
    }
    const bool alpha = text.size() == 9;
    const unsigned long rgb = alpha ? v >> 8 : v;
    *r_color = {float((rgb >> 16) & 0xff) / 255.0f, float((rgb >> 8) & 0xff) / 255.0f, float(rgb & 0xff) / 255.0f,
                alpha ? float(v & 0xff) / 255.0f : r_color->a};
    return true;
  }
  std::string spaced = text;
  std::replace(spaced.begin(), spaced.end(), ',', ' ');
  std::istringstream in(spaced);
  float c[4] = {r_color->r, r_color->g, r_color->b, r_color->a};
  int n = 0;
  while (n < 4 && in >> c[n]) {
    n++;
  }
  if (n < 3) {
    return false;
  }
  *r_color = {std::clamp(c[0], 0.0f, 1.0f), std::clamp(c[1], 0.0f, 1.0f), std::clamp(c[2], 0.0f, 1.0f),
              std::clamp(c[3], 0.0f, 1.0f)};
  return true;
}

/* The picked stop's point, alone selected in its drawing. */
static void select_stop(Layer &layer, int stop)
{
  for (MeshPoint &p : layer.drawing.points) {
    p.selected = false;
  }
  for (Curve &c : layer.drawing.curves) {
    for (CurvePoint &cp : c.points) {
      cp.select_in = cp.select_out = false;
    }
  }
  if (stop >= 0 && stop < int(layer.gradient.stops.size())) {
    const int p = drawing_point_index(layer.drawing, layer.gradient.stops[size_t(stop)].point);
    if (p >= 0) {
      layer.drawing.points[size_t(p)].selected = true;
    }
  }
}

void gradient_operators_register()
{
  add_operator(
      "layer.new_gradient", "New Gradient",
      "Add a gradient layer above the active layer: colours running along a path of two stops (more in its Gradient "
      "tab), filling the whole camera frame (mask it to fill less). From x1=, y1= to x2=, y2= (document space; "
      "across the middle of the frame), coloured color1= to color2= (\"#rrggbb[aa]\" or \"r, g, b[, a]\"; black to "
      "white)",
      [](Context &C) { return C.document != nullptr; },
      [](Context &C) {
        Document &doc = *C.document;
        float2 corners[4];
        camera_frame_corners(doc, corners);
        const float2 middle = (corners[0] + corners[2]) * 0.5f;
        const float2 across = (corners[1] - corners[0]) * 0.5f * 0.75f;
        const float2 a(op_arg_float(C, "x1", (middle - across).x), op_arg_float(C, "y1", (middle - across).y));
        const float2 b(op_arg_float(C, "x2", (middle + across).x), op_arg_float(C, "y2", (middle + across).y));
        Color from{0.0f, 0.0f, 0.0f, 1.0f}, to{1.0f, 1.0f, 1.0f, 1.0f};
        if (op_has_arg(C, "color1") && !parse_color(op_arg(C, "color1"), &from)) {
          report(ReportType::Error, "color1 is \"#rrggbb[aa]\" or \"r, g, b[, a]\"");
          return OpStatus::Cancelled;
        }
        if (op_has_arg(C, "color2") && !parse_color(op_arg(C, "color2"), &to)) {
          report(ReportType::Error, "color2 is \"#rrggbb[aa]\" or \"r, g, b[, a]\"");
          return OpStatus::Cancelled;
        }
        Layer &layer = document_add_layer(doc, LayerType::Vector, document_layer_unique_name(doc, "Gradient"));
        const Transform2D to_layer = layer_world_transform(doc, layer.id).inverted();
        gradient_layer_init(layer, to_layer.apply(a), to_layer.apply(b), from, to);
        return OpStatus::Finished;
      });

  add_operator(
      "gradient.stop_add", "Add Gradient Stop",
      "Add a stop to a gradient (layer=, else the active layer) at span span='s tick (the picked span), the path "
      "keeping its shape and the colour there as it showed",
      [](Context &C) { return gradient_layer(C) != nullptr; },
      [](Context &C) {
        Layer &layer = *gradient_layer(C);
        const int span = op_arg_int(C, "span", layer.gradient.active_span);
        const int stop = gradient_stop_add(layer, span);
        if (stop < 0) {
          report(ReportType::Warning, "No such span in the gradient");
          return OpStatus::Cancelled;
        }
        select_stop(layer, stop);
        return OpStatus::Finished;
      });

  add_operator(
      "gradient.stop_remove", "Remove Gradient Stop",
      "Take stop stop= (the picked stop) away from a gradient (layer=, else the active layer), the spans either side "
      "made one; at least two stay",
      [](Context &C) { return gradient_layer(C) != nullptr; },
      [](Context &C) {
        Layer &layer = *gradient_layer(C);
        if (layer.gradient.stops.size() <= 2) {
          report(ReportType::Warning, "A gradient keeps at least two stops");
          return OpStatus::Cancelled;
        }
        if (!gradient_stop_remove(layer, op_arg_int(C, "stop", layer.gradient.active_stop))) {
          report(ReportType::Warning, "No such stop in the gradient");
          return OpStatus::Cancelled;
        }
        select_stop(layer, layer.gradient.active_stop);
        return OpStatus::Finished;
      });

  add_operator(
      "gradient.stop_set", "Set Gradient Stop",
      "Set stop stop= (the picked stop) of a gradient (layer=, else the active layer): color= (\"#rrggbb[aa]\" or "
      "\"r, g, b[, a]\"), opacity= (0-1)",
      [](Context &C) { return gradient_layer(C) != nullptr; },
      [](Context &C) {
        Layer &layer = *gradient_layer(C);
        const int stop = op_arg_int(C, "stop", layer.gradient.active_stop);
        if (stop < 0 || stop >= int(layer.gradient.stops.size())) {
          report(ReportType::Warning, "No such stop in the gradient");
          return OpStatus::Cancelled;
        }
        Color &color = layer.gradient.stops[size_t(stop)].color;
        if (op_has_arg(C, "color") && !parse_color(op_arg(C, "color"), &color)) {
          report(ReportType::Error, "color is \"#rrggbb[aa]\" or \"r, g, b[, a]\"");
          return OpStatus::Cancelled;
        }
        if (op_has_arg(C, "opacity")) {
          color.a = std::clamp(op_arg_float(C, "opacity", color.a), 0.0f, 1.0f);
        }
        return OpStatus::Finished;
      });

  add_operator(
      "gradient.span_set", "Set Gradient Span",
      "Set span span= (the picked span: from that stop to the next) of a gradient (layer=, else the active layer): "
      "midpoint= (where along it, by length, its colours meet half way, its tick; 0.02-0.98), falloff= (SMOOTH, "
      "LINEAR or HARD)",
      [](Context &C) { return gradient_layer(C) != nullptr; },
      [](Context &C) {
        Layer &layer = *gradient_layer(C);
        const int span = op_arg_int(C, "span", layer.gradient.active_span);
        if (span < 0 || span + 1 >= int(layer.gradient.stops.size())) {
          report(ReportType::Warning, "No such span in the gradient");
          return OpStatus::Cancelled;
        }
        GradientStop &s = layer.gradient.stops[size_t(span)];
        if (op_has_arg(C, "midpoint")) {
          s.midpoint = std::clamp(op_arg_float(C, "midpoint", s.midpoint), 0.02f, 0.98f);
        }
        if (op_has_arg(C, "falloff") && !gradient_falloff_from_identifier(op_arg(C, "falloff").c_str(), &s.falloff)) {
          report(ReportType::Error, "falloff is SMOOTH, LINEAR or HARD");
          return OpStatus::Cancelled;
        }
        return OpStatus::Finished;
      });

  add_operator(
      "gradient.pick", "Pick Gradient Stop",
      "Pick stop stop= of a gradient (layer=, else the active layer), its point alone selected, and the span after it "
      "(the span before the last stop); or span span= alone. What the Gradient tab edits",
      [](Context &C) { return gradient_layer(C) != nullptr; },
      [](Context &C) {
        Layer &layer = *gradient_layer(C);
        GradientSettings &g = layer.gradient;
        const int n = int(g.stops.size());
        if (op_has_arg(C, "stop")) {
          const int stop = op_arg_int(C, "stop", 0);
          if (stop < 0 || stop >= n) {
            return OpStatus::Cancelled;
          }
          g.active_stop = stop;
          g.active_span = std::min(stop, n - 2);
          select_stop(layer, stop);
        }
        if (op_has_arg(C, "span")) {
          const int span = op_arg_int(C, "span", 0);
          if (span < 0 || span >= n - 1) {
            return OpStatus::Cancelled;
          }
          g.active_span = span;
        }
        if (C.undo) {
          C.undo->mark_selection_changed();
        }
        return OpStatus::Finished;
      },
      OPTYPE_REGISTER);
}

}  // namespace oanim
