/* The Draw tool's operators (data/ink_stroke.hh, data/fill_paint.hh, assets/draw_presets.hh): a scripted stroke, picking,
 * saving, putting back and deleting presets, the presets popup, and F / Shift F to size the line. */

#include <algorithm>
#include <cmath>
#include <sstream>
#include <string>
#include <vector>

#include "assets/brushes.hh"
#include "assets/draw_presets.hh"
#include "core/log.hh"
#include "data/document.hh"
#include "data/fill_paint.hh"
#include "data/line_cut.hh"
#include "data/quick_shape.hh"
#include "ops/edit_ops.hh"
#include "ops/operator.hh"
#include "wm/context.hh"

namespace oanim {

/* How near (screen pixels) a stroke's end welds to a point, and how long an end past a crossing counts as
 * overshooting it. */
static constexpr float WELD_PIXELS = 8.0f;
static constexpr float OVERSHOOT_PIXELS = 30.0f;

/* Picks a preset, as clicking it on the shelf does: the pen going keeps what it was changed to (for coming back
 * to), and the one coming takes what it was last changed to, else its saved settings. Clicking a pen always
 * makes Draw the tool, as a brush in Blender's shelf does. */
static void preset_apply(ToolSettings &ts, const DrawPreset &p)
{
  ts.tool = Tool::Draw;
  if (p.mode == DrawMode::Pen) {
    ts.draw_mode = DrawMode::Pen;
    return;
  }
  const DrawPreset *going = draw_preset_find(ts.draw_preset);
  ts.draw_changes[ts.draw_preset] = {ts.ink, draw_width(ts, going ? going->mode : DrawMode::Freehand)};
  ts.draw_mode = p.mode;
  ts.draw_preset = p.name;
  ts.draw_kind_preset[int(p.mode)] = p.name;
  ts.ink = p.ink;
  draw_width(ts, p.mode) = p.line_width;
  if (const auto it = ts.draw_changes.find(p.name); it != ts.draw_changes.end()) {
    ts.ink = it->second.ink;
    draw_width(ts, p.mode) = it->second.line_width;
  }
}

void draw_mode_set(ToolSettings &ts, DrawMode mode)
{
  if (mode == DrawMode::Pen) {
    ts.tool = Tool::Draw;
    ts.draw_mode = mode;
    return;
  }
  const auto last = ts.draw_kind_preset.find(int(mode));
  const char *first = mode == DrawMode::FillPen        ? "Fill Pen"
                      : mode == DrawMode::FillEraser   ? "Fill Eraser"
                      : mode == DrawMode::StrokeEraser ? "Stroke Eraser"
                      : mode == DrawMode::Trimmer      ? "Vector Trimmer"
                                                       : "Ink";
  const DrawPreset *p = draw_preset_find(last != ts.draw_kind_preset.end() ? last->second : first);
  /* The kind it is already on keeps its pen. */
  const DrawPreset *now = draw_preset_find(ts.draw_preset);
  if (now && now->mode == mode) {
    p = now;
  }
  if (p) {
    preset_apply(ts, *p);
  }
}

/* A line through `knots` on `drawing`, `line_width` wide (document units), its ends welded and overshoots trimmed as
 * the Draw tool's options say (unless `closes`). Filled if closed and `fill`. */
static bool line_add(Context &C, VectorDrawing &drawing, const std::vector<InkKnot> &knots, bool closes, bool fill,
                     float line_width, float pixel)
{
  ToolSettings &ts = C.wm->tool_settings;
  if (knots.size() < 2) {
    return false;
  }
  /* Before the stroke's own points are in, so it can't weld to itself. */
  int weld_first = -1, weld_last = -1;
  if (ts.draw_weld && !closes) {
    weld_first = drawing_pick_point(drawing, knots.front().pos, WELD_PIXELS * pixel);
    weld_last = drawing_pick_point(drawing, knots.back().pos, WELD_PIXELS * pixel);
    /* A point can't be both ends of an open line. */
    if (weld_last == weld_first) {
      weld_last = -1;
    }
  }
  Curve curve;
  for (MeshPoint &p : drawing.points) {
    p.selected = false;
  }
  drawing_deselect_handles(drawing);
  for (size_t i = 0; i < knots.size(); i++) {
    const InkKnot &knot = knots[i];
    int p = i == 0 ? weld_first : i + 1 == knots.size() ? weld_last : -1;
    if (p < 0) {
      p = drawing_add_point(drawing, knot.pos);
      drawing.points[p].radius = knot.radius;
      drawing.points[p].opacity = std::clamp(knot.opacity, 0.0f, 1.0f);
    }
    CurvePoint cp{p};
    cp.curvature = knot.corner ? CURVATURE_PEAKED : CURVATURE_SMOOTH;
    cp.aligned = !knot.corner;
    curve_point_set_handles(cp, knot.handle_in, knot.handle_out);
    curve.points.push_back(cp);
  }
  curve.closed = closes && curve.points.size() >= 3;
  drawing.curves.push_back(curve);
  Shape shape;
  shape.style = ts.style;
  shape.style.line_width = line_width;
  shape.has_fill = curve.closed && fill;
  shape.name = "Stroke " + std::to_string(drawing.shapes.size() + 1);
  for (int s = 0; s < drawing.curves.back().segment_count(); s++) {
    shape.edges.push_back({int(drawing.curves.size()) - 1, s});
  }
  drawing.shapes.push_back(std::move(shape));
  if (ts.draw_trim && !closes) {
    drawing_trim_overshoots(drawing, int(drawing.curves.size()) - 1, OVERSHOOT_PIXELS * pixel, pixel);
  }
  return true;
}

/* A stroke pen's line on the active drawing. */
static bool stroke_line(Context &C, VectorDrawing &drawing, const InkStroke &ink)
{
  ToolSettings &ts = C.wm->tool_settings;
  const std::vector<InkPoint> &stroke = ink.points();
  const float pixel = ink.view().pixel;
  const bool closes = ts.draw_fill && stroke.size() > 8 && distance(stroke.front().pos, stroke.back().pos) < pixel * 14.0f;
  const std::vector<InkKnot> knots = ink_fit(stroke, ink.settings(), ink.view(), closes);
  C.wm->draw_last_closed = closes;
  /* The width it was drawn at: with Size Unit View, what it was on screen. */
  return line_add(C, drawing, knots, closes, true, ink.view().half_width * 2.0f, pixel);
}

bool draw_live_line(const ToolSettings &ts, const InkStroke &ink, float2 tip, int shapes_before,
                    VectorDrawing &r_drawing, bool open_end)
{
  const Brush *brush = brush_find(ts.style.brush.name);
  if (ink.empty() || !brush || brush_tip_images(*brush, ts.style.brush).empty()) {
    return false;
  }
  std::vector<InkPoint> line = ink.points();
  const std::vector<InkPoint> tail = ink.tail(tip);
  line.insert(line.end(), tail.begin(), tail.end());
  InkSettings taper = ink.settings();
  if (open_end) {
    taper.taper_end = 0.0f;
  }
  ink_taper(line, taper, ink.view());
  if (line.size() < 2) {
    return false;
  }
  r_drawing = VectorDrawing();
  /* Placeholders: the seed is the shape's place in its drawing. */
  r_drawing.shapes.resize(size_t(std::max(shapes_before, 0)));
  /* Every sample a point, smooth through its neighbours (not fitted: a fit of a growing line would move the dabs
   * already down each time it changes). */
  Curve curve;
  const int n = int(line.size());
  for (int i = 0; i < n; i++) {
    const int p = drawing_add_point(r_drawing, line[size_t(i)].pos);
    r_drawing.points[size_t(p)].radius = line[size_t(i)].radius;
    r_drawing.points[size_t(p)].opacity = std::clamp(line[size_t(i)].opacity, 0.0f, 1.0f);
    const float2 before = line[size_t(std::max(i - 1, 0))].pos, after = line[size_t(std::min(i + 1, n - 1))].pos;
    const float2 handle = (after - before) / (i == 0 || i == n - 1 ? 3.0f : 6.0f);
    CurvePoint cp{p};
    cp.curvature = CURVATURE_SMOOTH;
    cp.aligned = true;
    curve_point_set_handles(cp, handle * -1.0f, handle);
    curve.points.push_back(cp);
  }
  r_drawing.curves.push_back(std::move(curve));
  Shape shape;
  shape.style = ts.style;
  shape.style.line_width = ink.view().half_width * 2.0f;
  if (open_end) {
    shape.style.brush.size_fade_out = 0;
    shape.style.brush.opacity_fade_out = 0;
  }
  for (int s = 0; s < r_drawing.curves.back().segment_count(); s++) {
    shape.edges.push_back({0, s});
  }
  r_drawing.shapes.push_back(std::move(shape));
  return true;
}

/* "x,y" as a place; false when it isn't one. */
static bool parse_pair(const std::string &text, float2 *r)
{
  std::stringstream row(text);
  char comma = 0;
  float x = 0.0f, y = 0.0f;
  /* Within what op_arg_float takes: a shape miles across would make an outline of inf and nan. */
  if (!(row >> x >> comma >> y) || comma != ',' || !std::isfinite(x) || !std::isfinite(y) || std::abs(x) > 1e7f ||
      std::abs(y) > 1e7f)
  {
    return false;
  }
  *r = {x, y};
  return true;
}

/* Hold to Shape's line or ellipse (data/quick_shape.hh), on the active drawing. */
static OpStatus quick_shape_exec(Context &C)
{
  Document &doc = *C.document;
  ToolSettings &ts = C.wm->tool_settings;
  Layer *layer = document_active_layer(doc);
  std::vector<Layer *> layers = editable_layers(C);
  if (doc.frame_current != 0 || !layer || std::find(layers.begin(), layers.end(), layer) == layers.end()) {
    report(ReportType::Error, "draw.quick_shape draws on the active drawing, on the setup frame");
    return OpStatus::Cancelled;
  }
  QuickShape shape;
  const std::string kind = op_arg(C, "shape", "LINE");
  bool ok = true;
  if (kind == "ELLIPSE") {
    shape.kind = QuickShape::Kind::Ellipse;
    ok = parse_pair(op_arg(C, "center"), &shape.center) && parse_pair(op_arg(C, "radii"), &shape.radii);
    shape.radii = {std::abs(shape.radii.x), std::abs(shape.radii.y)};
    shape.angle = op_arg_float(C, "angle", 0.0f) * PI / 180.0f;
    shape.circle = op_arg_bool(C, "circle");
    ok = ok && quick_shape_radii(shape).x > 0.0f && quick_shape_radii(shape).y > 0.0f;
  }
  else if (kind == "LINE") {
    ok = parse_pair(op_arg(C, "a"), &shape.a) && parse_pair(op_arg(C, "b"), &shape.b) && shape.a != shape.b;
  }
  else {
    ok = false;
  }
  if (!ok) {
    report(ReportType::Error, "draw.quick_shape takes shape=LINE with a=\"x,y\" b=\"x,y\", or shape=ELLIPSE with "
                              "center=\"x,y\" radii=\"rx,ry\" angle= (degrees) circle=0|1");
    return OpStatus::Cancelled;
  }
  const float pixel = op_arg_float(C, "pixel", 2.0f / std::max(float(doc.height), 1.0f));
  const float width = std::max(op_arg_float(C, "line_width", ts.style.line_width), 0.0f);
  const float radius = std::clamp(op_arg_float(C, "radius", 1.0f), 0.0f, 1.0f);
  const float opacity = std::clamp(op_arg_float(C, "opacity", 1.0f), 0.0f, 1.0f);
  const bool closed = shape.kind == QuickShape::Kind::Ellipse;
  std::vector<InkKnot> knots = quick_shape_knots(shape, radius);
  for (InkKnot &k : knots) {
    k.opacity = opacity;
  }
  if (!line_add(C, layer->drawing, knots, closed, ts.draw_fill, width, pixel)) {
    return OpStatus::Cancelled;
  }
  draw_brush_used(ts);
  op_note(closed ? (shape.circle ? "A circle" : "An ellipse") : "A straight line");
  return OpStatus::Finished;
}

/* The Stroke Eraser's or Trimmer's stroke, on the active drawing or every one being edited. */
static bool stroke_cut_lines(Context &C, Layer &layer, const InkStroke &ink, DrawMode mode)
{
  Document &doc = *C.document;
  const ToolSettings &ts = C.wm->tool_settings;
  const float pixel = ink.view().pixel;
  std::vector<Layer *> layers = {&layer};
  if (ts.draw_erase_all_layers) {
    layers = editable_layers(C);
  }
  const InkSweep sweep = ink_sweep(ink.points(), ink.settings(), ink.view());
  /* All the lines as they were, for crossings: one layer's cut isn't another's. */
  std::vector<std::vector<std::vector<float2>>> paths;
  for (Layer *other : layers) {
    paths.push_back(mode == DrawMode::Trimmer ? drawing_line_paths(other->drawing, pixel) : std::vector<std::vector<float2>>());
  }
  const Transform2D from = layer_world_transform(doc, layer.id);
  bool cut = false;
  for (size_t i = 0; i < layers.size(); i++) {
    Layer *other = layers[i];
    const Transform2D to_other = layer_world_transform(doc, other->id).inverted();
    const Transform2D to = to_other * from;
    InkSweep moved = sweep;
    for (float2 &c : moved.centers) {
      c = to.apply(c);
    }
    for (float &r : moved.radii) {
      r *= to.scale();
    }
    const float other_pixel = pixel * to.scale();
    if (mode == DrawMode::StrokeEraser) {
      cut |= drawing_lines_erase(other->drawing, moved, other_pixel, ink.settings().erase_whole, ts.draw_erase_selected);
      continue;
    }
    std::vector<std::vector<float2>> others;
    for (size_t j = 0; j < layers.size(); j++) {
      if (j != i) {
        const Transform2D across = to_other * layer_world_transform(doc, layers[j]->id);
        for (std::vector<float2> path : paths[j]) {
          for (float2 &p : path) {
            p = across.apply(p);
          }
          others.push_back(std::move(path));
        }
      }
    }
    cut |= drawing_lines_trim(other->drawing, moved, others, other_pixel, ts.draw_erase_selected);
  }
  return cut;
}

/* The pieces moved by `t`. */
static std::vector<FillPiece> pieces_moved(std::vector<FillPiece> pieces, const Transform2D &t)
{
  for (FillPiece &piece : pieces) {
    for (std::vector<float2> &ring : piece.rings) {
      for (float2 &p : ring) {
        p = t.apply(p);
      }
    }
  }
  return pieces;
}

/* The Fill Eraser's stroke, on the active drawing or every one being edited. */
static bool stroke_erase(Context &C, Layer &layer, const std::vector<FillPiece> &area, float pixel, float tolerance,
                         bool quiet = false)
{
  Document &doc = *C.document;
  const ToolSettings &ts = C.wm->tool_settings;
  std::vector<Layer *> layers = {&layer};
  if (ts.draw_erase_all_layers) {
    layers = editable_layers(C);
  }
  bool cut = false;
  int skipped = 0;
  const Transform2D from = layer_world_transform(doc, layer.id);
  for (Layer *other : layers) {
    const Transform2D to = layer_world_transform(doc, other->id).inverted() * from;
    cut |= drawing_fill_erase(other->drawing, other == &layer ? area : pieces_moved(area, to), pixel / to.scale(), tolerance,
                              ts.draw_erase_selected, &skipped);
  }
  if (skipped > 0 && !quiet) {
    report(ReportType::Info, skipped == 1 ? "A shape with keys wasn't cut: cutting rebuilds its points" :
                                            std::to_string(skipped) + " shapes with keys weren't cut: cutting rebuilds their points");
  }
  return cut;
}

/* How many line brushes the brush button's Recently Used keeps. */
static constexpr size_t BRUSH_RECENT_MAX = 8;

void draw_brush_used(ToolSettings &ts)
{
  const BrushSettings used = brush_settings_unnamed(ts.style.brush);
  std::erase_if(ts.brush_recent, [&](const BrushSettings &b) { return brush_settings_unnamed(b) == used; });
  ts.brush_recent.insert(ts.brush_recent.begin(), ts.style.brush);
  if (ts.brush_recent.size() > BRUSH_RECENT_MAX) {
    ts.brush_recent.resize(BRUSH_RECENT_MAX);
  }
}

bool draw_stroke_commit(Context &C, Layer &layer, InkStroke &ink, DrawMode mode)
{
  ToolSettings &ts = C.wm->tool_settings;
  if (ink.empty()) {
    return false;
  }
  ink.finish();
  C.wm->draw_last = ink;
  C.wm->draw_last_closed = false;
  if (!draw_mode_paints(mode)) {
    if (!stroke_line(C, layer.drawing, ink)) {
      return false;
    }
    draw_brush_used(ts);
    return true;
  }
  if (mode == DrawMode::StrokeEraser || mode == DrawMode::Trimmer) {
    return stroke_cut_lines(C, layer, ink, mode);
  }
  const float pixel = ink.view().pixel;
  /* A little closer than a line's: a blob is fitted again each time it grows. */
  const float tolerance = ink_tolerance(ink.settings().fidelity) * 0.6f;
  const std::vector<FillPiece> area = ink_area(ink.points(), ink.settings(), ink.view());
  if (area.empty()) {
    return false;
  }
  if (mode == DrawMode::FillEraser) {
    return stroke_erase(C, layer, area, pixel, tolerance);
  }
  drawing_fill_paint(layer.drawing, area, ts.style, pixel, tolerance);
  return true;
}

bool draw_stroke_cut_so_far(Context &C, Layer &layer, InkStroke ink, DrawMode mode)
{
  if (ink.empty() || !draw_mode_cuts(mode)) {
    return false;
  }
  ink.finish();
  if (mode == DrawMode::StrokeEraser || mode == DrawMode::Trimmer) {
    return stroke_cut_lines(C, layer, ink, mode);
  }
  const float tolerance = ink_tolerance(ink.settings().fidelity) * 0.6f;
  const std::vector<FillPiece> area = ink_area(ink.points(), ink.settings(), ink.view());
  return !area.empty() && stroke_erase(C, layer, area, ink.view().pixel, tolerance, true);
}

/* "x,y,pressure,seconds;...": the stroke's samples in the active layer's space. */
static std::vector<InkSample> parse_samples(const std::string &text)
{
  std::vector<InkSample> samples;
  std::stringstream items(text);
  std::string item;
  while (std::getline(items, item, ';')) {
    InkSample s;
    char comma = 0;
    std::stringstream row(item);
    if (row >> s.pos.x >> comma >> s.pos.y >> comma >> s.pressure >> comma >> s.time) {
      samples.push_back(s);
    }
  }
  return samples;
}

static OpStatus stroke_exec(Context &C)
{
  Document &doc = *C.document;
  ToolSettings &ts = C.wm->tool_settings;
  Layer *layer = document_active_layer(doc);
  std::vector<Layer *> layers = editable_layers(C);
  if (doc.frame_current != 0 || !layer || std::find(layers.begin(), layers.end(), layer) == layers.end()) {
    report(ReportType::Error, "draw.stroke draws on the active drawing, on the setup frame");
    return OpStatus::Cancelled;
  }
  const float pixel = op_arg_float(C, "pixel", 2.0f / std::max(float(doc.height), 1.0f));
  InkStroke ink;
  if (ts.draw_mode == DrawMode::Pen) {
    report(ReportType::Error, "draw.stroke needs a pen that draws by dragging, not the Bezier Pen");
    return OpStatus::Cancelled;
  }
  ink.begin(ts.ink, {pixel, draw_half_width(ts, ts.draw_mode, pixel), 2.0f / std::max(float(doc.height), 1.0f)});
  for (const InkSample &sample : parse_samples(op_arg(C, "samples"))) {
    ink.add(sample);
  }
  const bool erase = op_arg_bool(C, "erase");
  const DrawMode mode = erase && ts.draw_mode == DrawMode::FillPen    ? DrawMode::FillEraser
                        : erase && ts.draw_mode == DrawMode::Freehand ? DrawMode::StrokeEraser
                                                                      : ts.draw_mode;
  return draw_stroke_commit(C, *layer, ink, mode) ? OpStatus::Finished : OpStatus::Cancelled;
}

void draw_operators_register()
{
  const auto add = [](const char *idname, const char *name, const char *description, unsigned flag,
                      std::function<bool(Context &)> poll, std::function<OpStatus(Context &)> exec) {
    OperatorType ot;
    ot.idname = idname;
    ot.name = name;
    ot.description = description;
    ot.flag = flag;
    ot.poll = std::move(poll);
    ot.exec = std::move(exec);
    operators().add(std::move(ot));
  };
  const auto draw_tool = [](Context &C) { return C.wm->tool_settings.tool == Tool::Draw; };
  const auto drags = [](Context &C) {
    const ToolSettings &ts = C.wm->tool_settings;
    return ts.tool == Tool::Draw && ts.draw_mode != DrawMode::Pen;
  };
  const auto has_opacity = [](Context &C) {
    const ToolSettings &ts = C.wm->tool_settings;
    return ts.tool == Tool::Draw && ts.draw_mode != DrawMode::Pen && !draw_mode_cuts(ts.draw_mode);
  };

  add("draw.stroke", "Draw",
      "A stroke through the Stroke Pen's engine with the Draw tool's settings, on the active drawing: samples=\"x,y,"
      "pressure,seconds;...\" in the layer's space, pixel= the layer units a screen pixel stands for, erase=1 (Ctrl) "
      "with the Stroke Pen or Fill Pen erases instead",
      OPTYPE_UNDO, [](Context &C) { return C.document != nullptr; }, stroke_exec);
  add("draw.preset_load", "Load Draw Preset", "Pick the pen named name= (as clicking it on the shelf)", 0, nullptr,
      [](Context &C) {
        const DrawPreset *p = draw_preset_find(op_arg(C, "name"));
        if (!p) {
          report(ReportType::Error, "No pen named \"" + op_arg(C, "name") + "\"");
          return OpStatus::Cancelled;
        }
        preset_apply(C.wm->tool_settings, *p);
        return OpStatus::Finished;
      });
  add("draw.preset_save", "Save Draw Preset",
      "Save the Draw tool's pen and settings to the asset library as name= (made unique), shown under Mine",
      OPTYPE_REGISTER, nullptr, [](Context &C) {
        ToolSettings &ts = C.wm->tool_settings;
        DrawPreset p;
        p.name = op_arg(C, "name", ts.draw_preset);
        p.mode = ts.draw_mode == DrawMode::Pen ? DrawMode::Freehand : ts.draw_mode;
        p.ink = ts.ink;
        p.line_width = draw_width(ts, p.mode);
        std::string error;
        const std::string saved = draw_preset_save(p, &error);
        if (saved.empty()) {
          report(ReportType::Error, error);
          return OpStatus::Cancelled;
        }
        ts.draw_preset = saved;
        ts.draw_kind_preset[int(p.mode)] = saved;
        /* Saved as it is: nothing changed from that. */
        ts.draw_changes.erase(saved);
        report(ReportType::Info, "Saved pen \"" + saved + "\"");
        return OpStatus::Finished;
      });
  add("draw.preset_reset", "Put Back Draw Preset", "Put the pen named name= back to its saved settings", 0, nullptr,
      [](Context &C) {
        ToolSettings &ts = C.wm->tool_settings;
        const DrawPreset *p = draw_preset_find(op_arg(C, "name"));
        if (!p) {
          report(ReportType::Error, "No pen named \"" + op_arg(C, "name") + "\"");
          return OpStatus::Cancelled;
        }
        ts.draw_changes.erase(p->name);
        if (ts.draw_preset == p->name) {
          ts.ink = p->ink;
          draw_width(ts, p->mode) = p->line_width;
        }
        return OpStatus::Finished;
      });
  add("draw.preset_remove", "Delete Draw Preset", "Delete the saved pen named name= from the asset library",
      OPTYPE_REGISTER, nullptr, [](Context &C) {
        std::string error;
        if (!draw_preset_remove(op_arg(C, "name"), &error)) {
          report(ReportType::Error, error);
          return OpStatus::Cancelled;
        }
        C.wm->tool_settings.draw_changes.erase(op_arg(C, "name"));
        return OpStatus::Finished;
      });
  {
    OperatorType ot;
    ot.idname = "draw.quick_shape";
    ot.name = "Hold to Shape";
    ot.description = "A straight line (shape=LINE, a= and b= its ends, \"x,y\" in the active layer's space) or an ellipse "
                     "(shape=ELLIPSE, center=, radii=\"rx,ry\", angle= degrees, circle=1 for a circle) on the active "
                     "drawing, as a freehand line held still at its end becomes one: line_width= (document units), "
                     "radius= (its width, 0-1), pixel= (layer units a screen pixel stands for)";
    ot.flag = OPTYPE_REGISTER | OPTYPE_UNDO;
    ot.poll = [](Context &C) { return C.document != nullptr; };
    ot.exec = quick_shape_exec;
    OpProperty round;
    round.name = "circle";
    round.label = "Shape";
    round.description = "An ellipse as it was drawn, or a circle of their mean radius";
    round.kind = OpProperty::Kind::Enum;
    round.items = {{"0", "Ellipse"}, {"1", "Circle"}};
    round.fallback = "0";
    round.expand = true;
    round.item_descriptions = {"The ellipse that fits the loop drawn", "A circle, the ellipse's two radii made their mean"};
    round.visible = [](const OpArgs &args) {
      const auto it = args.find("shape");
      return it != args.end() && it->second == "ELLIPSE";
    };
    ot.props.push_back(round);
    operators().add(std::move(ot));
  }
  add("brush.recent_pick", "Pick Recent Brush",
      "Draw with the line brush index= in the brush button's Recently Used (0 the latest)", OPTYPE_REGISTER, nullptr,
      [](Context &C) {
        ToolSettings &ts = C.wm->tool_settings;
        const int index = op_arg_int(C, "index", -1);
        if (index < 0 || index >= int(ts.brush_recent.size())) {
          report(ReportType::Error, "No recent brush " + op_arg(C, "index"));
          return OpStatus::Cancelled;
        }
        ts.style.brush = ts.brush_recent[size_t(index)];
        return OpStatus::Finished;
      });
  add("draw.presets_popup", "Pens", "Show the Draw tool's pens at the mouse (Shift Space)", 0, draw_tool, [](Context &C) {
    C.wm->draw_popup_request = true;
    return OpStatus::Finished;
  });
  add("draw.width_adjust", "Adjust Line Width", "Size the line with the mouse (F); click to keep it", 0, drags,
      [](Context &C) {
        C.wm->draw_adjust_request = 'R';
        return OpStatus::Finished;
      });
  add("draw.opacity_adjust", "Adjust Line Opacity", "Set the line's opacity with the mouse (Shift F); click to keep it",
      0, has_opacity, [](Context &C) {
        C.wm->draw_adjust_request = 'S';
        return OpStatus::Finished;
      });
}

}  // namespace oanim
