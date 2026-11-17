#include "wm/ipad_link.hh"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <set>

#include <miniz.h>
#include <qrcodegen.hpp>

#include "imgui.h"

#include "anim/onion.hh"
#include "assets/brushes.hh"
#include "assets/draw_presets.hh"
#include "core/profile.hh"
#include "data/camera.hh"
#include "data/document.hh"
#include "data/ink_stroke.hh"
#include "editors/draw_tile.hh"
#include "gpu/brush_stroke.hh"
#include "io/svg_export.hh"
#include "io/vector_export.hh"
#include "ops/edit_ops.hh"
#include "ops/operator.hh"
#include "ops/undo.hh"
#include "python/py_runtime.hh"
#include "wm/context.hh"
#include "wm/ipad_server.hh"

namespace oanim {

namespace {

/* Numbers as the messages carry them: as many decimals as matter for pixels, and no more. */
void num(std::string &out, double v, int decimals = 2)
{
  if (!std::isfinite(v)) {
    v = 0.0;
  }
  char text[40];
  std::snprintf(text, sizeof(text), "%.*f", decimals, v);
  /* "1.50" -> "1.5", "2.00" -> "2". */
  char *end = text + std::strlen(text);
  if (std::strchr(text, '.')) {
    while (end > text && end[-1] == '0') {
      *--end = '\0';
    }
    if (end > text && end[-1] == '.') {
      *--end = '\0';
    }
  }
  if (std::strcmp(text, "-0") == 0) {
    out += '0';
    return;
  }
  out += text;
}

void color_json(std::string &out, const Color &c)
{
  out += '[';
  num(out, c.r, 3);
  out += ',';
  num(out, c.g, 3);
  out += ',';
  num(out, c.b, 3);
  out += ',';
  num(out, c.a, 3);
  out += ']';
}

std::string json_string(const std::string &text)
{
  std::string out = "\"";
  for (const char ch : text) {
    const unsigned char c = static_cast<unsigned char>(ch);
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\r':
        out += "\\r";
        break;
      case '\t':
        out += "\\t";
        break;
      default:
        if (c < 0x20) {
          char esc[8];
          std::snprintf(esc, sizeof(esc), "\\u%04x", c);
          out += esc;
        }
        else {
          out += ch;
        }
    }
  }
  return out + "\"";
}

/* A stroke being drawn on the iPad. */
struct Stroke {
  bool active = false;
  uint64_t layer = 0;
  DrawMode mode = DrawMode::Freehand;
  InkStroke ink;
  /* Canvas pixels to the layer's space, and back. */
  Transform2D to_layer, to_canvas;
  /* Layer units a canvas pixel. */
  float canvas_pixel = 1.0f;
  int shapes_before = 0;
  /* What the iPad has been sent of the line: a solid line's points ([x, y, half width, opacity]), or a brushed
   * line's dabs' vertices per image. */
  std::vector<float> sent_line;
  std::vector<std::vector<BrushVertex>> sent_dabs;
  std::vector<uint64_t> sent_images;
  bool sent_brushed = false;
};
Stroke g_stroke;
/* Brush images the pages have, by id. */
std::set<uint64_t> g_images_sent;

bool same_vertex(const BrushVertex &a, const BrushVertex &b)
{
  return a.x == b.x && a.y == b.y && a.u == b.u && a.v == b.v && a.r == b.r && a.g == b.g && a.b == b.b && a.a == b.a;
}

/* An image as a PNG (straight alpha: the page premultiplies it as it loads it), base64. */
std::string image_png(const BrushImage &image)
{
  std::vector<uint8_t> straight(image.rgba.size());
  for (size_t i = 0; i + 3 < image.rgba.size(); i += 4) {
    const uint8_t a = image.rgba[i + 3];
    for (int k = 0; k < 3; k++) {
      straight[i + k] = a > 0 ? uint8_t(std::min(255, int(image.rgba[i + k]) * 255 / a)) : 0;
    }
    straight[i + 3] = a;
  }
  size_t size = 0;
  void *png = tdefl_write_image_to_png_file_in_memory_ex(straight.data(), image.width, image.height, 4, &size,
                                                         MZ_DEFAULT_LEVEL, MZ_FALSE);
  if (!png) {
    return {};
  }
  const std::string out = ipad_base64(static_cast<const unsigned char *>(png), size);
  mz_free(png);
  return out;
}

/* A brushed line's dabs: laid out as the renderer lays a line's (layer space). Empty: no brush to stamp with. */
bool line_dabs(const Document &doc, uint64_t layer_id, const VectorDrawing &live, float pixel, BrushDabs &r_dabs,
               const std::vector<BrushImage> **r_images, bool *r_own_colors)
{
  const Shape &shape = live.shapes.back();
  const Brush *brush = brush_find(shape.style.brush.name);
  if (!brush) {
    return false;
  }
  const std::vector<BrushImage> &images = brush_tip_images(*brush, shape.style.brush);
  if (images.empty()) {
    return false;
  }
  std::vector<float> aspects;
  for (const BrushImage &image : images) {
    aspects.push_back(float(image.width) / float(std::max(image.height, 1)));
  }
  const BrushPath path = brush_path(live, shape, 0.0f);
  brush_stroke(path, path, shape.style.brush, shape.style.line, aspects, pixel * 0.5f,
               brush_seed(shape.style.brush, layer_id, int(live.shapes.size()) - 1, doc.frame_current), r_dabs, nullptr,
               true);
  *r_images = &images;
  *r_own_colors = brush->is_color && !shape.style.brush.tint;
  return true;
}

/* The body of a "live" message for a brushed line's dabs: what changed since `sent` (each image's vertices kept up
 * to "keep", then "add"ed), images the page lacks with them. */
std::string dabs_json(const BrushDabs &dabs, const std::vector<BrushImage> &images, bool own_colors,
                      const Transform2D &to_canvas, std::vector<std::vector<BrushVertex>> *sent,
                      std::vector<uint64_t> *sent_ids)
{
  std::string out = "\"kind\":\"dabs\",\"own\":";
  out += own_colors ? "true" : "false";
  /* The ids changed (another brush): everything goes again. */
  std::vector<uint64_t> ids;
  for (size_t i = 0; i < dabs.per_image.size(); i++) {
    ids.push_back(i < images.size() ? images[i].id : 0);
  }
  if (sent && *sent_ids != ids) {
    sent->clear();
    *sent_ids = ids;
  }
  std::string pictures;
  out += ",\"images\":[";
  for (size_t i = 0; i < dabs.per_image.size(); i++) {
    std::vector<BrushVertex> now;
    for (const BrushVertex &v : dabs.per_image[i]) {
      const float2 p = to_canvas.apply({v.x, v.y});
      now.push_back({p.x, p.y, v.u, v.v, v.r, v.g, v.b, v.a});
    }
    size_t keep = 0;
    if (sent) {
      if (sent->size() <= i) {
        sent->resize(i + 1);
      }
      const std::vector<BrushVertex> &before = (*sent)[i];
      while (keep < before.size() && keep < now.size() && same_vertex(before[keep], now[keep])) {
        keep++;
      }
      /* Whole dabs only (two triangles each). */
      keep -= keep % 6;
    }
    if (i > 0) {
      out += ',';
    }
    const uint64_t id = ids[i];
    out += "{\"id\":" + std::to_string(id) + ",\"keep\":" + std::to_string(keep) + ",\"add\":[";
    for (size_t k = keep; k < now.size(); k++) {
      const BrushVertex &v = now[k];
      if (k > keep) {
        out += ',';
      }
      num(out, v.x);
      out += ',';
      num(out, v.y);
      out += ',';
      num(out, v.u, 4);
      out += ',';
      num(out, v.v, 4);
      out += ',';
      num(out, v.r, 3);
      out += ',';
      num(out, v.g, 3);
      out += ',';
      num(out, v.b, 3);
      out += ',';
      num(out, v.a, 3);
    }
    out += "]}";
    if (sent) {
      (*sent)[i] = std::move(now);
    }
    if (i < images.size() && !g_images_sent.count(id)) {
      g_images_sent.insert(id);
      if (!pictures.empty()) {
        pictures += ',';
      }
      pictures += "\"" + std::to_string(id) + "\":\"" + image_png(images[i]) + "\"";
    }
  }
  out += "],\"pngs\":{" + pictures + "}";
  return out;
}

/* The body of a "live" message for a solid line through `line` (layer space): [x, y, half width, opacity] in canvas
 * pixels, kept up to "keep" numbers of what was sent. */
std::string line_json(const std::vector<InkPoint> &line, float half_width, const Transform2D &to_canvas, Color color,
                      std::vector<float> *sent)
{
  std::vector<float> now;
  const float scale = to_canvas.scale();
  for (const InkPoint &p : line) {
    const float2 at = to_canvas.apply(p.pos);
    now.push_back(std::round(at.x * 100.0f) / 100.0f);
    now.push_back(std::round(at.y * 100.0f) / 100.0f);
    now.push_back(std::round(std::max(p.radius * half_width * scale, 0.0f) * 100.0f) / 100.0f);
    now.push_back(std::round(std::clamp(p.opacity, 0.0f, 1.0f) * 1000.0f) / 1000.0f);
  }
  size_t keep = 0;
  if (sent) {
    while (keep < sent->size() && keep < now.size() && (*sent)[keep] == now[keep]) {
      keep++;
    }
    keep -= keep % 4;
  }
  std::string out = "\"kind\":\"line\",\"color\":";
  color_json(out, color);
  out += ",\"keep\":" + std::to_string(keep) + ",\"add\":[";
  for (size_t k = keep; k < now.size(); k++) {
    if (k > keep) {
      out += ',';
    }
    num(out, now[k], k % 4 == 3 ? 3 : 2);
  }
  out += "]";
  if (sent) {
    *sent = std::move(now);
  }
  return out;
}

std::vector<InkPoint> line_now(const InkStroke &ink)
{
  std::vector<InkPoint> line = ink.points();
  const std::vector<InkPoint> tail = ink.tail(ink.last_sample());
  line.insert(line.end(), tail.begin(), tail.end());
  ink_taper(line, ink.settings(), ink.view());
  return line;
}

}  // namespace

Transform2D ipad_canvas_transform(const Document &doc, int width, int height)
{
  /* As Render Frame and the SVG: the camera's frame, 2 units tall, fills the picture; y runs down. */
  const float scale = float(height) * 0.5f;
  return Transform2D{1, 0, 0, -1, 0, float(height)} *
         Transform2D{scale, 0, 0, scale, float(width) * 0.5f, float(height) * 0.5f} * camera_to_frame(doc);
}

/* The canvas's layers as last made, kept for the next (only the layers an edit changed are worked out again). */
static VectorSceneCache &canvas_cache()
{
  static VectorSceneCache cache;
  return cache;
}

void ipad_canvas_cache_counts(int *r_reused, int *r_made, int *r_lines_reused, int *r_lines_made)
{
  *r_reused = canvas_cache().reused;
  *r_made = canvas_cache().made;
  if (r_lines_reused) {
    *r_lines_reused = canvas_cache().lines_reused;
    *r_lines_made = canvas_cache().lines_made;
  }
}

std::string ipad_canvas_message(Context &C, int width, int height, bool cached)
{
  OANIM_PROFILE("ipad_canvas");
  const Document &doc = *C.document;
  SvgExport options;
  options.width = width;
  options.height = height;
  options.cache = cached ? &canvas_cache() : nullptr;
  /* The canvas the iPad draws over is the viewport's: reference pictures on guide layers show. */
  options.guides = true;
  std::string out = "{\"t\":\"canvas\",\"w\":" + std::to_string(width) + ",\"h\":" + std::to_string(height) +
                    ",\"frame\":" + std::to_string(doc.frame_current) + ",\"svg\":" + json_string(svg_frame(doc, options));
  out += ",\"onion\":[";
  const std::vector<uint64_t> layers = onion_layers(doc, editable_layers(C));
  const std::vector<OnionGhost> ghosts = onion_ghosts(doc, layers);
  std::vector<OnionWires> wires = onion_wires(doc, layers, ghosts);
  /* The furthest first, so the nearest show on top. */
  std::stable_sort(wires.begin(), wires.end(),
                   [](const OnionWires &a, const OnionWires &b) { return a.ghost.distance > b.ghost.distance; });
  const Transform2D to_canvas = ipad_canvas_transform(doc, width, height);
  bool first = true;
  for (const OnionWires &w : wires) {
    if (!first) {
      out += ',';
    }
    first = false;
    Color c = w.ghost.after ? doc.onion_color_after : doc.onion_color_before;
    c.a *= onion_ghost_alpha(doc, w.ghost);
    out += "{\"c\":";
    color_json(out, c);
    out += ",\"lines\":[";
    for (size_t l = 0; l < w.lines.size(); l++) {
      out += l ? ",[" : "[";
      for (size_t i = 0; i < w.lines[l].size(); i++) {
        const float2 p = to_canvas.apply(w.lines[l][i]);
        if (i) {
          out += ',';
        }
        num(out, p.x, 1);
        out += ',';
        num(out, p.y, 1);
      }
      out += ']';
    }
    out += "]}";
  }
  out += "]}";
  return out;
}

std::string ipad_draw_refused(Context &C)
{
  Document &doc = *C.document;
  const ToolSettings &ts = C.wm->tool_settings;
  if (ts.tool != Tool::Draw) {
    return "Switch to Draw in Open Animate";
  }
  if (doc.frame_current != 0) {
    return "Switch to Setup (frame 0) to draw";
  }
  if (ts.draw_mode == DrawMode::Pen) {
    return "The Bezier Pen draws in Open Animate: pick a pen that draws by dragging";
  }
  Layer *layer = document_active_layer(doc);
  const std::vector<Layer *> layers = editable_layers(C);
  if (!layer || std::find(layers.begin(), layers.end(), layer) == layers.end()) {
    return "Pick a drawing to draw on";
  }
  return {};
}

std::string ipad_stroke_begin(Context &C, int width, int height, float zoom, bool eraser)
{
  g_stroke = Stroke();
  if (std::string refused = ipad_draw_refused(C); !refused.empty()) {
    return refused;
  }
  if (width <= 0 || height <= 0 || !(zoom > 0.0f) || !std::isfinite(zoom)) {
    return "The canvas has no size";
  }
  Document &doc = *C.document;
  ToolSettings &ts = C.wm->tool_settings;
  Layer *layer = document_active_layer(doc);
  g_stroke.layer = layer->id;
  g_stroke.to_canvas = ipad_canvas_transform(doc, width, height) * layer_world_transform(doc, layer->id);
  g_stroke.to_layer = g_stroke.to_canvas.inverted();
  g_stroke.canvas_pixel = 1.0f / std::max(g_stroke.to_canvas.scale(), 1e-9f);
  g_stroke.shapes_before = int(layer->drawing.shapes.size());
  /* As the viewport's press: the eraser end erases with the pen's matching eraser. */
  g_stroke.mode = eraser && ts.draw_mode == DrawMode::FillPen    ? DrawMode::FillEraser
                  : eraser && ts.draw_mode == DrawMode::Freehand ? DrawMode::StrokeEraser
                                                                 : ts.draw_mode;
  InkSettings settings = ts.ink;
  settings.opacity_pressure = settings.opacity_pressure && g_stroke.mode == DrawMode::Freehand;
  /* A screen pixel is the iPad's. */
  const float pixel = g_stroke.canvas_pixel / zoom;
  g_stroke.ink.begin(settings, {pixel, draw_half_width(ts, g_stroke.mode, pixel), 2.0f / std::max(float(doc.height), 1.0f)});
  g_stroke.active = true;
  return {};
}

std::string ipad_stroke_add(Context &C, const std::vector<IpadSample> &samples)
{
  if (!g_stroke.active) {
    return {};
  }
  Document &doc = *C.document;
  const ToolSettings &ts = C.wm->tool_settings;
  for (const IpadSample &s : samples) {
    if (!std::isfinite(s.x) || !std::isfinite(s.y) || !std::isfinite(s.time)) {
      continue;
    }
    g_stroke.ink.add({g_stroke.to_layer.apply({s.x, s.y}), std::clamp(std::isfinite(s.pressure) ? s.pressure : 1.0f, 0.0f, 1.0f),
                      {std::isfinite(s.tilt_x) ? s.tilt_x : 0.0f, std::isfinite(s.tilt_y) ? s.tilt_y : 0.0f}, s.time});
  }
  if (g_stroke.ink.empty()) {
    return {};
  }
  /* A brushed line stamps as it goes, a solid one, a fill and an eraser show as the viewport's preview. */
  VectorDrawing live;
  if (g_stroke.mode == DrawMode::Freehand &&
      draw_live_line(ts, g_stroke.ink, g_stroke.ink.last_sample(), g_stroke.shapes_before, live))
  {
    BrushDabs dabs;
    const std::vector<BrushImage> *images = nullptr;
    bool own = false;
    if (line_dabs(doc, g_stroke.layer, live, g_stroke.canvas_pixel, dabs, &images, &own)) {
      g_stroke.sent_brushed = true;
      return "{\"t\":\"live\"," +
             dabs_json(dabs, *images, own, g_stroke.to_canvas, &g_stroke.sent_dabs, &g_stroke.sent_images) + "}";
    }
  }
  const Color color = draw_mode_cuts(g_stroke.mode)         ? Color{0.9f, 0.3f, 0.3f, 0.4f}
                      : g_stroke.mode == DrawMode::FillPen ? ts.style.fill
                                                           : ts.style.line;
  return "{\"t\":\"live\"," +
         line_json(line_now(g_stroke.ink), g_stroke.ink.view().half_width, g_stroke.to_canvas, color, &g_stroke.sent_line) +
         "}";
}

std::string ipad_stroke_end(Context &C)
{
  if (!g_stroke.active) {
    return {};
  }
  g_stroke.active = false;
  /* Undrawable since it began (a frame change, the layer gone): nothing. */
  if (!ipad_draw_refused(C).empty()) {
    return {};
  }
  Document &doc = *C.document;
  Layer *layer = document_active_layer(doc);
  if (!layer || layer->id != g_stroke.layer) {
    return {};
  }
  const DrawMode mode = g_stroke.mode;
  if (!draw_stroke_commit(C, *layer, g_stroke.ink, mode)) {
    return {};
  }
  const char *name = mode == DrawMode::FillEraser     ? "Erase Fill"
                     : mode == DrawMode::StrokeEraser ? "Erase Line"
                     : mode == DrawMode::Trimmer      ? "Trim Line"
                     : mode == DrawMode::FillPen      ? "Paint Fill"
                                                      : "Draw";
  C.undo->push(name, doc);
  return name;
}

void ipad_stroke_cancel()
{
  g_stroke = Stroke();
}

bool ipad_stroke_active()
{
  return g_stroke.active;
}

void ipad_images_reset()
{
  g_images_sent.clear();
}

std::string ipad_tiles_json(Context &C, float size)
{
  const ToolSettings &ts = C.wm->tool_settings;
  std::string out = "[";
  bool first = true;
  for (const DrawPreset &p : draw_presets()) {
    const TilePicture pic = draw_tile_picture(ts, p, size);
    if (!first) {
      out += ',';
    }
    first = false;
    out += "{\"name\":" + json_string(p.name) + ",\"rects\":[";
    for (size_t i = 0; i < pic.rects.size(); i++) {
      const TileRect &r = pic.rects[i];
      out += i ? ",{\"a\":[" : "{\"a\":[";
      num(out, r.a.x);
      out += ',';
      num(out, r.a.y);
      out += "],\"b\":[";
      num(out, r.b.x);
      out += ',';
      num(out, r.b.y);
      out += "],\"c\":";
      color_json(out, r.color);
      out += ",\"r\":";
      num(out, r.rounding);
      out += '}';
    }
    out += "],\"strokes\":[";
    for (size_t i = 0; i < pic.strokes.size(); i++) {
      const TileStroke &s = pic.strokes[i];
      out += i ? ",{\"plain\":" : "{\"plain\":";
      out += s.plain ? "true" : "false";
      out += ",\"c\":";
      color_json(out, s.color);
      out += ",\"p\":[";
      for (size_t k = 0; k < s.points.size(); k++) {
        if (k) {
          out += ',';
        }
        num(out, s.points[k].x);
        out += ',';
        num(out, s.points[k].y);
        out += ',';
        num(out, s.widths[k]);
        out += ',';
        num(out, s.opacity.empty() ? 1.0f : s.opacity[k], 3);
      }
      out += "]}";
    }
    out += "],\"dots\":[";
    for (size_t i = 0; i < pic.dots.size(); i++) {
      const TileDot &d = pic.dots[i];
      out += i ? ",{\"x\":" : "{\"x\":";
      num(out, d.c.x);
      out += ",\"y\":";
      num(out, d.c.y);
      out += ",\"r\":";
      num(out, d.r);
      out += ",\"square\":";
      out += d.square ? "true" : "false";
      out += ",\"c\":";
      color_json(out, d.color);
      out += '}';
    }
    out += "]}";
  }
  return out + "]";
}

std::string ipad_brush_preview_json(Context &C, float width, float height)
{
  const Document &doc = *C.document;
  ToolSettings ts = C.wm->tool_settings;
  /* The line across the button, in its pixels as a layer's units: a wave, pressing into its middle. A button is
   * small, so the line is drawn wider than true, as the shelf's tiles are. */
  const float half = std::clamp(ts.style.line_width * float(doc.height) * 0.25f * 3.0f, 0.75f, height * 0.3f);
  InkSettings ink = ts.ink;
  ink.stabilizer = InkStabilizer::Off;
  ink.taper_start = std::min(ink.taper_start, width * 0.3f);
  ink.taper_end = std::min(ink.taper_end, width * 0.3f);
  InkStroke stroke;
  stroke.begin(ink, {1.0f, half, 1.0f});
  static constexpr int STEPS = 40;
  for (int i = 0; i <= STEPS; i++) {
    const float u = float(i) / float(STEPS);
    stroke.add({{width * (0.08f + 0.84f * u), height * 0.5f - std::sin(u * 2.0f * PI) * height * 0.18f},
                0.3f + 0.7f * std::sin(u * PI),
                {},
                double(u) * 0.5});
  }
  stroke.finish();
  const Transform2D identity;
  VectorDrawing live;
  ts.style.line.a = 1.0f;
  if (draw_live_line(ts, stroke, stroke.last_sample(), 0, live)) {
    BrushDabs dabs;
    const std::vector<BrushImage> *images = nullptr;
    bool own = false;
    if (line_dabs(doc, 0, live, 1.0f, dabs, &images, &own)) {
      return "{" + dabs_json(dabs, *images, own, identity, nullptr, nullptr) + "}";
    }
  }
  std::vector<InkPoint> line = stroke.points();
  ink_taper(line, stroke.settings(), stroke.view());
  return "{" + line_json(line, half, identity, ts.style.line, nullptr) + "}";
}

void ipad_brush_shape_set(Context &C, const std::string &name)
{
  BrushSettings &brush = C.wm->tool_settings.style.brush;
  brush.name = name == "Round" ? BRUSH_ROUND_TIP : name;
  brush.preset.clear();
}

namespace {
bool g_window = false;
}

void ipad_operators_register()
{
  OperatorType start;
  start.idname = "wm.ipad_draw_start";
  start.name = "Draw on iPad";
  start.description = "Draw on an iPad with its Pencil: shows a QR code that opens the drawing page on the iPad, on the "
                      "same network as this computer";
  start.exec = [](Context &) {
    if (!ipad_server_running()) {
      const std::u8string root = (python::scripts_dir() / "ipad").u8string();
      if (ipad_server_start(IPAD_PORT, std::string(root.begin(), root.end())) == 0) {
        return OpStatus::Cancelled;
      }
    }
    g_window = true;
    return OpStatus::Finished;
  };
  operators().add(std::move(start));
  OperatorType stop;
  stop.idname = "wm.ipad_draw_stop";
  stop.name = "Stop Drawing on iPad";
  stop.description = "Stop the iPad's drawing page: it disconnects, and its QR code no longer works";
  stop.poll = [](Context &) { return ipad_server_running(); };
  stop.exec = [](Context &) {
    ipad_stroke_cancel();
    ipad_server_stop();
    g_window = false;
    return OpStatus::Finished;
  };
  operators().add(std::move(stop));
}

bool ipad_window_shown()
{
  return g_window;
}

void ipad_window_draw(Context &C)
{
  if (!g_window) {
    return;
  }
  if (!ipad_server_running()) {
    g_window = false;
    return;
  }
  const float h = ImGui::GetFrameHeight();
  ImGui::SetNextWindowSize(ImVec2(0, 0), ImGuiCond_Always);
  if (!ImGui::Begin("Draw on iPad", &g_window,
                    ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoDocking | ImGuiWindowFlags_AlwaysAutoResize))
  {
    ImGui::End();
    return;
  }
  const std::string url = ipad_server_url();
  /* Made again only when the address changes (a new key each start). */
  static std::string coded;
  static std::vector<bool> modules;
  static int size = 0;
  if (coded != url) {
    coded = url;
    const qrcodegen::QrCode qr = qrcodegen::QrCode::encodeText(url.c_str(), qrcodegen::QrCode::Ecc::MEDIUM);
    size = qr.getSize();
    modules.assign(size_t(size * size), false);
    for (int y = 0; y < size; y++) {
      for (int x = 0; x < size; x++) {
        modules[size_t(y * size + x)] = qr.getModule(x, y);
      }
    }
  }
  /* Black on white with a quiet zone four modules wide, as a scanner wants. */
  const float module = std::max(std::floor(h * 11.0f / float(size + 8)), 2.0f);
  const float side = module * float(size + 8);
  const ImVec2 at = ImGui::GetCursorScreenPos();
  ImDrawList *dl = ImGui::GetWindowDrawList();
  dl->AddRectFilled(at, ImVec2(at.x + side, at.y + side), IM_COL32_WHITE, 4.0f);
  for (int y = 0; y < size; y++) {
    for (int x = 0; x < size; x++) {
      if (modules[size_t(y * size + x)]) {
        const ImVec2 a(at.x + module * float(x + 4), at.y + module * float(y + 4));
        dl->AddRectFilled(a, ImVec2(a.x + module, a.y + module), IM_COL32_BLACK);
      }
    }
  }
  ImGui::Dummy(ImVec2(side, side));
  if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
    ImGui::SetTooltip("Scan with the iPad's camera; it must be on the same network as this computer");
  }
  const std::string address = "http://" + ipad_server_host() + ":" + std::to_string(ipad_server_port());
  ImGui::TextUnformatted(address.c_str());
  const int clients = ipad_server_clients();
  if (clients == 0) {
    ImGui::TextDisabled("Waiting for the iPad");
  }
  else {
    ImGui::TextColored(ImVec4(0.45f, 0.8f, 0.45f, 1.0f), clients == 1 ? "iPad connected" : "%d iPads connected", clients);
  }
  if (ImGui::Button("Stop", ImVec2(side, 0.0f))) {
    operator_call(C, "wm.ipad_draw_stop");
  }
  ImGui::End();
}

void ipad_process(Context &)
{
  if (!ipad_server_running()) {
    return;
  }
  OANIM_PROFILE("ipad");
  python::ipad_tick();
}

}  // namespace oanim
