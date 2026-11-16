/* The Draw tool's shelf: a strip along the bottom of the viewport while Draw is the tool, as Blender's asset
 * shelf shows brushes, and the same tiles in a popup (Shift Space, or the header's pen button) for anyone
 * who folds it. Each tile is a preset (assets/draw_presets.hh), its picture a sample line made by the engine
 * itself from the preset's settings, so a tile shows how the pen really draws. Clicking a tile picks it;
 * Mine's + tile saves the pen as it is now; right-clicking one puts it back or deletes it. Tabs with nothing
 * in them don't show. */

#define IMGUI_DEFINE_MATH_OPERATORS
#include "imgui.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <string>
#include <vector>

#include "assets/draw_presets.hh"
#include "data/ink_stroke.hh"
#include "editors/draw_tile.hh"
#include "editors/editors.hh"
#include "gpu/tessellate.hh"
#include "imgui_stdlib.h"
#include "ops/operator.hh"
#include "wm/context.hh"

namespace oanim {

static constexpr ImU32 COL_INK = IM_COL32(0x1e, 0x1e, 0x1e, 255);
static constexpr ImU32 COL_CHANGED = IM_COL32(0x47, 0x72, 0xb3, 255);
/* The sample line: this many document pixels across, in this long. */
static constexpr float SAMPLE_PIXELS = 400.0f;
static constexpr float SAMPLE_SECONDS = 0.7f;
/* Its line drawn this much wider than true, and a document this many pixels tall: a tile is small. */
static constexpr float SAMPLE_WIDEN = 3.0f;
static constexpr float SAMPLE_DOCUMENT_HEIGHT = 1080.0f;

enum { TAB_ALL, TAB_PENS, TAB_ERASERS, TAB_TRIM, TAB_MINE };

void ink_line_draw(ImDrawList *dl, const std::vector<float2> &points, const std::vector<float> &half_widths, Color color,
                   const std::vector<float> *opacity)
{
  std::vector<Vertex> vertices;
  tessellate_stroke(points, half_widths, false, color, 1.0f, vertices, nullptr, opacity);
  /* Triangles, a few at a time (a draw list's indices may be 16-bit). The tessellator's colours are
   * premultiplied, ImGui's not. */
  const ImVec2 uv = ImGui::GetFontTexUvWhitePixel();
  static constexpr size_t CHUNK = 3 * 10000;
  for (size_t from = 0; from < vertices.size(); from += CHUNK) {
    const size_t count = std::min(CHUNK, vertices.size() - from);
    dl->PrimReserve(int(count), int(count));
    for (size_t i = 0; i < count; i++) {
      const Vertex &v = vertices[from + i];
      const uint32_t a = v.rgba >> 24;
      const auto straight = [a](uint32_t c) { return a > 0 ? std::min<uint32_t>(c * 255 / a, 255) : 0; };
      const ImU32 col = IM_COL32(straight(v.rgba & 0xff), straight(v.rgba >> 8 & 0xff), straight(v.rgba >> 16 & 0xff), a);
      dl->PrimWriteIdx(ImDrawIdx(dl->_VtxCurrentIdx));
      dl->PrimWriteVtx(ImVec2(v.x, v.y), uv, col);
    }
  }
}

/* What a preset's tile shows: its settings as they are now (the active one as the header has them, another
 * as it was last changed to). */
static void preset_now(const ToolSettings &ts, const DrawPreset &p, InkSettings *r_ink, float *r_line_width)
{
  *r_ink = p.ink;
  *r_line_width = p.line_width;
  if (p.mode == DrawMode::Pen) {
    return;
  }
  if (ts.draw_preset == p.name) {
    *r_ink = ts.ink;
    *r_line_width = draw_mode_paints(p.mode) ? ts.fill_size : ts.style.line_width;
  }
  else if (const auto it = ts.draw_changes.find(p.name); it != ts.draw_changes.end()) {
    *r_ink = it->second.ink;
    *r_line_width = it->second.line_width;
  }
}

/* The sample line a pen with these settings makes: an S, pressing into its middle, leaning as it goes. Made
 * again only when the settings change. */
struct SampleLine {
  InkSettings ink;
  float line_width = -1.0f;
  std::vector<InkPoint> points;
};

static const std::vector<InkPoint> &sample_line(const std::string &name, const InkSettings &ink, float line_width)
{
  static std::map<std::string, SampleLine> lines;
  SampleLine &line = lines[name];
  if (line.line_width == line_width && line.ink == ink) {
    return line.points;
  }
  line.ink = ink;
  line.line_width = line_width;
  InkStroke stroke;
  stroke.begin(ink, {1.0f, line_width * SAMPLE_DOCUMENT_HEIGHT * 0.25f, 1.0f});
  static constexpr int STEPS = 84;
  for (int i = 0; i <= STEPS; i++) {
    const float u = float(i) / float(STEPS);
    const float y = std::sin(u * 2.0f * PI) * SAMPLE_PIXELS * 0.2f;
    stroke.add({{u * SAMPLE_PIXELS, y}, 0.2f + 0.8f * std::sin(u * PI), {u * 50.0f, 0.0f}, double(u * SAMPLE_SECONDS)});
  }
  stroke.finish();
  std::vector<InkPoint> points = stroke.points();
  ink_taper(points, ink, stroke.view());
  /* A tile has a few dozen pixels for it. */
  line.points.clear();
  for (const InkPoint &p : points) {
    if (line.points.empty() || distance(p.pos, line.points.back().pos) >= 6.0f) {
      line.points.push_back(p);
    }
  }
  if (distance(points.back().pos, line.points.back().pos) > 0.0f) {
    line.points.push_back(points.back());
  }
  return line.points;
}

/* A curve as a polyline of `steps` pieces, for a tile's picture. */
static std::vector<float2> bezier_points(float2 p0, float2 p1, float2 p2, float2 p3, int steps)
{
  std::vector<float2> out;
  for (int i = 0; i <= steps; i++) {
    const float t = float(i) / float(steps), u = 1.0f - t;
    out.push_back(p0 * (u * u * u) + p1 * (3.0f * u * u * t) + p2 * (3.0f * u * t * t) + p3 * (t * t * t));
  }
  return out;
}

static TileStroke plain_stroke(std::vector<float2> points, float width, Color color)
{
  TileStroke s;
  s.points = std::move(points);
  s.widths.assign(s.points.size(), width * 0.5f);
  s.color = color;
  s.plain = true;
  return s;
}

TilePicture draw_tile_picture(const ToolSettings &ts, const DrawPreset &p, float size)
{
  TilePicture pic;
  const float2 c{size * 0.5f, size * 0.5f};
  const Color ink_col{0x1e / 255.0f, 0x1e / 255.0f, 0x1e / 255.0f, 1.0f};
  if (p.mode == DrawMode::Pen) {
    /* A curve with its points and handles. */
    const float s = size * 0.32f, t = std::max(1.0f, size * 0.03f);
    const float2 p0 = c + float2{-s, s * 0.6f}, p1 = c + float2{s, -s * 0.6f};
    const float2 h0 = c + float2{-s * 0.3f, -s * 0.9f}, h1 = c + float2{s * 0.3f, s * 0.9f};
    pic.strokes.push_back(plain_stroke(bezier_points(p0, h0, h1, p1, 24), t, ink_col));
    const Color grey{0xa8 / 255.0f, 0xa8 / 255.0f, 0xa8 / 255.0f, 1.0f};
    pic.strokes.push_back(plain_stroke({p0, h0}, 1.0f, grey));
    pic.strokes.push_back(plain_stroke({p1, h1}, 1.0f, grey));
    const float r = size * 0.035f;
    const Color blue{0x47 / 255.0f, 0x72 / 255.0f, 0xb3 / 255.0f, 1.0f};
    pic.dots.push_back({h0, r, blue, false});
    pic.dots.push_back({h1, r, blue, false});
    pic.dots.push_back({p0, r, ink_col, true});
    pic.dots.push_back({p1, r, ink_col, true});
    return pic;
  }
  if (p.mode == DrawMode::StrokeEraser || p.mode == DrawMode::Trimmer) {
    const float s = size * 0.36f, t = std::max(1.5f, size * 0.05f);
    const Color gone{0xc8 / 255.0f, 0xc8 / 255.0f, 0xc8 / 255.0f, 1.0f};
    const auto line = [&](float2 a, float2 b, Color col) { pic.strokes.push_back(plain_stroke({a, b}, t, col)); };
    const auto curve = [&](float2 a, float2 b, float2 d, float2 e, Color col, int steps) {
      pic.strokes.push_back(plain_stroke(bezier_points(a, b, d, e, steps), t, col));
    };
    if (p.mode == DrawMode::Trimmer) {
      /* A line crossing two others, the piece between them gone. */
      for (const float x : {-0.5f, 0.5f}) {
        line(c + float2{x * s, -s}, c + float2{x * s, s}, ink_col);
      }
      line(c + float2{-s * 1.1f, 0.0f}, c + float2{-s * 0.5f, 0.0f}, ink_col);
      line(c + float2{s * 0.5f, 0.0f}, c + float2{s * 1.1f, 0.0f}, ink_col);
      line(c + float2{-s * 0.5f, 0.0f}, c + float2{s * 0.5f, 0.0f}, gone);
    }
    else if (p.ink.erase_whole) {
      /* Two lines, one of them gone. */
      curve(c + float2{-s, s * 0.6f}, c + float2{-s * 0.3f, -s * 0.1f}, c + float2{s * 0.3f, s * 1.1f},
            c + float2{s, s * 0.4f}, ink_col, 20);
      curve(c + float2{-s, -s * 0.4f}, c + float2{-s * 0.3f, -s * 1.1f}, c + float2{s * 0.3f, s * 0.1f},
            c + float2{s, -s * 0.6f}, gone, 20);
    }
    else {
      /* A line with a gap in it. */
      curve(c + float2{-s * 1.1f, s * 0.5f}, c + float2{-s * 0.8f, -s * 0.2f}, c + float2{-s * 0.5f, -s * 0.1f},
            c + float2{-s * 0.25f, s * 0.1f}, ink_col, 16);
      curve(c + float2{s * 0.25f, -s * 0.1f}, c + float2{s * 0.5f, s * 0.1f}, c + float2{s * 0.8f, s * 0.2f},
            c + float2{s * 1.1f, -s * 0.5f}, ink_col, 16);
      line(c + float2{-s * 0.25f, s * 0.1f}, c + float2{s * 0.25f, -s * 0.1f}, gone);
    }
    return pic;
  }
  InkSettings ink;
  float line_width = 0.0f;
  preset_now(ts, p, &ink, &line_width);
  const float scale = size * 0.8f / SAMPLE_PIXELS;
  const float half = line_width * SAMPLE_DOCUMENT_HEIGHT * 0.25f * scale * SAMPLE_WIDEN;
  TileStroke stroke;
  for (const InkPoint &point : sample_line(p.name, ink, line_width)) {
    stroke.points.push_back(c + float2{point.pos.x - SAMPLE_PIXELS * 0.5f, -point.pos.y} * scale);
    stroke.widths.push_back(std::min(point.radius * half, size * 0.1f));
    stroke.opacity.push_back(point.opacity);
  }
  if (stroke.points.size() < 2) {
    return pic;
  }
  if (p.mode == DrawMode::FillEraser) {
    /* A patch of fill, with the eraser's path cut out of it. */
    pic.rects.push_back({float2{size * 0.1f, size * 0.2f}, float2{size * 0.9f, size * 0.8f},
                         Color{0xd8 / 255.0f, 0x9a / 255.0f, 0x5c / 255.0f, 1.0f}, 3.0f});
    stroke.color = Color{0.95f, 0.95f, 0.95f, 1.0f};
    stroke.opacity.clear();
  }
  else {
    stroke.color = p.mode == DrawMode::FillPen ? Color{0.85f, 0.6f, 0.36f, 1.0f} : Color{0.12f, 0.12f, 0.12f, 1.0f};
    if (p.mode != DrawMode::Freehand) {
      stroke.opacity.clear();
    }
  }
  pic.strokes.push_back(std::move(stroke));
  return pic;
}

static ImU32 tile_color(Color c)
{
  return ImGui::ColorConvertFloat4ToU32(ImVec4(c.r, c.g, c.b, c.a));
}

static void tile_picture(ImDrawList *dl, const ToolSettings &ts, const DrawPreset &p, ImVec2 a, ImVec2 b)
{
  const TilePicture pic = draw_tile_picture(ts, p, b.x - a.x);
  const auto at = [&](float2 q) { return ImVec2(a.x + q.x, a.y + q.y); };
  for (const TileRect &r : pic.rects) {
    dl->AddRectFilled(at(r.a), at(r.b), tile_color(r.color), r.rounding);
  }
  for (const TileStroke &s : pic.strokes) {
    if (s.plain) {
      std::vector<ImVec2> points;
      for (const float2 q : s.points) {
        points.push_back(at(q));
      }
      dl->AddPolyline(points.data(), int(points.size()), tile_color(s.color), ImDrawFlags_None, s.widths[0] * 2.0f);
      continue;
    }
    std::vector<float2> points;
    for (const float2 q : s.points) {
      points.push_back({a.x + q.x, a.y + q.y});
    }
    ink_line_draw(dl, points, s.widths, s.color, s.opacity.empty() ? nullptr : &s.opacity);
  }
  for (const TileDot &d : pic.dots) {
    if (d.square) {
      dl->AddRectFilled(at(d.c) - ImVec2(d.r, d.r), at(d.c) + ImVec2(d.r, d.r), tile_color(d.color));
    }
    else {
      dl->AddCircleFilled(at(d.c), d.r, tile_color(d.color));
    }
  }
}

static bool in_tab(const DrawPreset &p, int tab)
{
  switch (tab) {
    case TAB_PENS:
      return p.category == DRAW_CATEGORY_PENS;
    case TAB_ERASERS:
      return p.category == DRAW_CATEGORY_ERASERS;
    case TAB_TRIM:
      return p.category == DRAW_CATEGORY_TRIM;
    case TAB_MINE:
      return p.category == DRAW_CATEGORY_MINE;
    default:
      return true;
  }
}

/* The tabs with something in them (Mine has its + tile), as Blender hides empty catalogs. */
static std::vector<ShelfTab> shown_tabs()
{
  std::vector<ShelfTab> tabs = {{TAB_ALL, "All"}, {TAB_PENS, "Pens"}};
  const auto any = [](const char *category) {
    const std::vector<DrawPreset> &all = draw_presets();
    return std::any_of(all.begin(), all.end(), [&](const DrawPreset &p) { return p.category == category; });
  };
  if (any(DRAW_CATEGORY_ERASERS)) {
    tabs.push_back({TAB_ERASERS, "Erasers"});
  }
  if (any(DRAW_CATEGORY_TRIM)) {
    tabs.push_back({TAB_TRIM, "Trim"});
  }
  tabs.push_back({TAB_MINE, "Mine"});
  return tabs;
}

static std::string tile_tooltip(const ToolSettings &ts, const DrawPreset &p)
{
  if (p.mode == DrawMode::Pen) {
    return p.name + "\nClick to add points along a curve, drag to place each";
  }
  if (p.mode == DrawMode::FillEraser) {
    return p.name + "\nCuts the brushed area out of fills; lines stay";
  }
  if (p.mode == DrawMode::StrokeEraser) {
    return p.name + (p.ink.erase_whole ? "\nTakes away every line it touches; fills stay" : "\nCuts lines where brushed; fills stay");
  }
  if (p.mode == DrawMode::Trimmer) {
    return p.name + "\nBrush across a line: the touched piece goes, out to the nearest crossings";
  }
  InkSettings ink;
  float line_width = 0.0f;
  preset_now(ts, p, &ink, &line_width);
  std::string text = p.name + "\n";
  text += p.mode == DrawMode::FillPen ? "Paints a fill, merging with one of the same colour it overlaps. " : "";
  text += ink.stabilizer == InkStabilizer::Off     ? "No smoothing"
          : ink.stabilizer == InkStabilizer::Smart ? "Smart smoothing"
                                                   : "Pulled String";
  text += ink.use_pressure ? ", width from pressure" : "";
  text += ink.speed_width > 0.0f ? ", width from speed" : "";
  text += ink.tilt_width > 0.0f ? ", width from tilt" : "";
  text += ink.taper_start > 0.0f || ink.taper_end > 0.0f ? ", tapered" : "";
  if (!(ink == p.ink) || line_width != p.line_width) {
    text += "\nChanged from its saved settings (right-click to put it back)";
  }
  return text;
}

/* The tiles, in rows of `width`, scrolling when they don't fit. True when one was picked. */
static bool preset_tiles(Context &C, ShelfState &shelf, float width)
{
  ToolSettings &ts = C.wm->tool_settings;
  bool picked = false;
  ImDrawList *dl = ImGui::GetWindowDrawList();
  const float size = shelf_tile_size(shelf), th = shelf_tile_height(shelf), gap = 8.0f;
  const ImVec2 start = ImGui::GetCursorScreenPos() + ImVec2(gap, 6.0f);
  const int per_row = std::max(1, int((width - gap) / (size + gap)));
  const std::string search = shelf_lower(shelf.search);
  std::vector<const DrawPreset *> shown;
  for (const DrawPreset &p : draw_presets()) {
    if (in_tab(p, shelf.tab) && (search.empty() || shelf_lower(p.name).find(search) != std::string::npos)) {
      shown.push_back(&p);
    }
  }
  /* Mine (and All) end with a + tile: save the pen as it is now. */
  const bool plus = shelf.tab == TAB_ALL || shelf.tab == TAB_MINE;
  const int count = int(shown.size()) + (plus ? 1 : 0);
  static std::string save_name;
  static std::string menu_preset;
  for (int k = 0; k < count; k++) {
    const ImVec2 at = start + ImVec2(float(k % per_row) * (size + gap), float(k / per_row) * (th + gap));
    ImGui::SetCursorScreenPos(at);
    ImGui::PushID(k);
    const bool clicked = ImGui::InvisibleButton("##tile", ImVec2(size, th));
    const bool hovered = ImGui::IsItemHovered();
    const ImVec2 a = at, b = at + ImVec2(size, size);
    if (k == int(shown.size())) {
      shelf_plus_tile(dl, a, b, hovered);
      if (hovered) {
        ImGui::SetTooltip("Save the pen as it is now to the asset library, under Mine");
      }
      if (clicked) {
        save_name = ts.draw_preset;
        ImGui::OpenPopup("##save_preset");
      }
      if (ImGui::BeginPopup("##save_preset")) {
        ImGui::TextUnformatted("Save Pen");
        if (ImGui::IsWindowAppearing()) {
          ImGui::SetKeyboardFocusHere();
        }
        ImGui::SetNextItemWidth(ImGui::GetFrameHeight() * 9.0f);
        const bool enter = ImGui::InputText("##name", &save_name, ImGuiInputTextFlags_EnterReturnsTrue);
        if (ImGui::Button("Save") || enter) {
          operator_call(C, "draw.preset_save", {{"name", save_name}});
          shelf.tab = TAB_MINE;
          ImGui::CloseCurrentPopup();
        }
        ImGui::SameLine();
        if (ImGui::Button("Cancel")) {
          ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
      }
      ImGui::PopID();
      continue;
    }
    const DrawPreset &p = *shown[size_t(k)];
    const bool active = ts.draw_mode == p.mode && (p.mode == DrawMode::Pen || ts.draw_preset == p.name);
    shelf_tile_box(dl, a, b, active, hovered);
    tile_picture(dl, ts, p, a, b);
    shelf_tile_name(dl, a, b, p.name, active);
    InkSettings ink;
    float line_width = 0.0f;
    preset_now(ts, p, &ink, &line_width);
    const bool changed = p.mode != DrawMode::Pen && (!(ink == p.ink) || line_width != p.line_width);
    if (changed) {
      dl->AddCircleFilled(ImVec2(b.x - size * 0.1f, a.y + size * 0.1f), size * 0.045f, COL_CHANGED);
    }
    if (hovered) {
      ImGui::SetTooltip("%s", tile_tooltip(ts, p).c_str());
    }
    if (clicked) {
      operator_call(C, "draw.preset_load", {{"name", p.name}});
      picked = true;
    }
    if ((changed || !p.builtin) && hovered && ImGui::IsMouseReleased(ImGuiMouseButton_Right)) {
      menu_preset = p.name;
      ImGui::OpenPopup("##tile_menu");
    }
    if (ImGui::BeginPopup("##tile_menu")) {
      const DrawPreset *menu = draw_preset_find(menu_preset);
      if (ImGui::MenuItem(("Put Back \"" + menu_preset + "\"").c_str())) {
        operator_call(C, "draw.preset_reset", {{"name", menu_preset}});
      }
      if (menu && !menu->builtin && ImGui::MenuItem(("Delete \"" + menu_preset + "\"").c_str())) {
        operator_call(C, "draw.preset_remove", {{"name", menu_preset}});
      }
      ImGui::EndPopup();
    }
    ImGui::PopID();
  }
  if (count == 0) {
    ImGui::SetCursorScreenPos(start);
    ImGui::TextDisabled("No pens match");
  }
  /* Room for the rows, so the shelf scrolls. */
  const int rows = (count + per_row - 1) / per_row;
  ImGui::SetCursorScreenPos(start + ImVec2(0, float(std::max(rows, 1)) * (th + gap)));
  ImGui::Dummy(ImVec2(1, 1));
  return picked;
}

float draw_shelf_height(const Context &C, const Area &area)
{
  return C.wm->tool_settings.tool == Tool::Draw ? shelf_height(area.draw_shelf) : 0.0f;
}

void draw_shelf_draw(Context &C, Area &area, ImVec2 min, ImVec2 size)
{
  if (size.y <= 0.0f) {
    return;
  }
  ImGui::PushID("##draw_shelf");
  if (shelf_frame(area.draw_shelf, shown_tabs(), min, size)) {
    const ImVec2 body = ImGui::GetCursorScreenPos();
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(0, 0));
    ImGui::PushStyleColor(ImGuiCol_ChildBg, IM_COL32(0, 0, 0, 0));
    if (ImGui::BeginChild("##tiles", ImVec2(size.x, min.y + size.y - body.y), ImGuiChildFlags_None)) {
      preset_tiles(C, area.draw_shelf, size.x);
    }
    ImGui::EndChild();
    ImGui::PopStyleColor();
    ImGui::PopStyleVar();
  }
  ImGui::PopID();
}

void draw_presets_popup(Context &C)
{
  static ShelfState popup;
  ImGui::SetNextWindowSize(ImVec2(ImGui::GetFrameHeight() * 24.0f, 0.0f));
  if (!ImGui::BeginPopup("##draw_presets")) {
    return;
  }
  if (ImGui::IsKeyPressed(ImGuiKey_Escape)) {
    ImGui::CloseCurrentPopup();
  }
  shelf_tabs(popup, shown_tabs());
  const float rows = std::min(3.0f, std::ceil(float(draw_presets().size() + 1) /
                                              std::max(std::floor(ImGui::GetContentRegionAvail().x /
                                                                  (shelf_tile_size(popup) + 8.0f)),
                                                       1.0f)));
  const float height = rows * (shelf_tile_height(popup) + 8.0f) + 8.0f;
  ImGui::PushStyleColor(ImGuiCol_ChildBg, IM_COL32(0x2b, 0x2b, 0x2b, 255));
  if (ImGui::BeginChild("##tiles", ImVec2(0.0f, height), ImGuiChildFlags_None)) {
    if (preset_tiles(C, popup, ImGui::GetContentRegionAvail().x)) {
      ImGui::CloseCurrentPopup();
    }
  }
  ImGui::EndChild();
  ImGui::PopStyleColor();
  ImGui::EndPopup();
}

}  // namespace oanim
