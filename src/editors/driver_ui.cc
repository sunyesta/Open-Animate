#define IMGUI_DEFINE_MATH_OPERATORS
/* Drivers in the UI (Blender's): a driven field is purple (red when its driver can't be worked out),
 * right-clicking a keyable field or a colour offers Add Driver..., Copy As New Driver, Copy Driver,
 * Edit Driver..., Delete Driver and Paste Driver, typing "#expression" into a number field drives it,
 * and the Driver window edits a field's drivers: type, expression, variables, remap. */

#include <algorithm>
#include <string>
#include <vector>

#include "imgui.h"
#include "imgui_internal.h"
#include "imgui_stdlib.h"

#include "anim/animation.hh"
#include "anim/drivers.hh"
#include "data/camera.hh"
#include "data/document.hh"
#include "editors/editors.hh"
#include "editors/ui.hh"
#include "ops/operator.hh"
#include "ops/undo.hh"
#include "wm/context.hh"

namespace oanim {

/* Blender's driven purple, and red for a driver that doesn't work. */
static const ImVec4 DRIVEN_BG(0.40f, 0.22f, 0.62f, 1.0f), DRIVEN_HOVER(0.47f, 0.27f, 0.71f, 1.0f);
static const ImVec4 BROKEN_BG(0.62f, 0.17f, 0.17f, 1.0f), BROKEN_HOVER(0.70f, 0.22f, 0.22f, 1.0f);

namespace {

struct Field {
  uint64_t layer = 0;
  std::string path;
  int component = -1;
  bool valid() const { return !path.empty(); }
};

/* The field a ui_driver_next asked for, for the next colour row. */
Field g_next;
/* The field each open field's menu belongs to (the menu is drawn by that field). */
int g_menu_frame = -1;
/* The Driver window: open on this field. */
struct EditorState {
  bool open = false;
  bool raise = false;
  Field field;
  /* Which of the field's numbers is shown (a colour's R G B A, a position's X Y). */
  int part = 0;
} g_editor;

std::vector<OpArgs> field_args(const Field &f)
{
  OpArgs args = {{"layer", std::to_string(f.layer)}, {"path", f.path}, {"component", std::to_string(f.component)}};
  /* A shape colour: every selected shape's, as the Material panel edits them. */
  const auto ends = [&](const char *end) {
    const size_t n = std::strlen(end);
    return f.path.size() >= n && f.path.compare(f.path.size() - n, n, end) == 0;
  };
  if (f.path.rfind("shapes[", 0) == 0 && (ends(".fill") || ends(".line"))) {
    args["selected_shapes"] = "1";
  }
  return {args};
}

/* 0: not driven; 1: driven (purple, a two-way link's driven side too); 2: a driver that doesn't work. `r_linked`: in a
 * two-way link, either side (the link icon in the field). */
int field_state(Document &doc, const Field &f, bool *r_linked = nullptr)
{
  int state = 0;
  bool linked = false;
  for (const DriverRef &r : driver_field_refs(doc, f.layer, f.path, f.component)) {
    if (const Driver *d = driver_find(doc, r)) {
      state = std::max(state, d->error.empty() ? 1 : 2);
    }
    linked = linked || driver_two_way_role(doc, r) != 0;
  }
  if (r_linked) {
    *r_linked = linked;
  }
  return state;
}

/* The other side of a field's two-way links, as words ("Dial: Rotation, factor -0.5"). */
std::string linked_text(Document &doc, const Field &f)
{
  std::string text;
  for (const DriverRef &r : driver_field_refs(doc, f.layer, f.path, f.component)) {
    for (const Driver &d : doc.drivers) {
      if (!d.two_way || d.vars.size() != 1) {
        continue;
      }
      char factor[32];
      std::snprintf(factor, sizeof(factor), "%g", double(d.flip ? -d.factor : d.factor));
      if (d.target == r) {
        text += (text.empty() ? "" : "\n") + std::string("2-Way Linked with ") + driver_ref_label(doc, d.vars.front().source) +
                ", factor " + factor + " (its keys are the ones kept)";
      }
      else if (d.vars.front().source == r) {
        text += (text.empty() ? "" : "\n") + std::string("2-Way Linked: ") + driver_ref_label(doc, d.target) +
                " follows it, factor " + factor + " (these keys are both's)";
      }
    }
  }
  return text;
}

/* What hovering a driven field says: its drivers and how they work. */
std::string field_tooltip(Document &doc, const Field &f)
{
  std::string text;
  const char *parts = "RGBA";
  const std::vector<DriverRef> refs = driver_field_refs(doc, f.layer, f.path, f.component);
  for (const DriverRef &r : refs) {
    const Driver *d = driver_find(doc, r);
    if (!d) {
      continue;
    }
    std::string line;
    if (refs.size() > 1) {
      line += refs.size() == 4 ? std::string(1, parts[r.component]) + ": " : std::string(r.component == 0 ? "X: " : "Y: ");
    }
    static const char *const TYPES[] = {"", "Average of ", "Sum of ", "Smallest of ", "Largest of "};
    line += d->type == DriverType::Expression ? d->expression : std::string(TYPES[int(d->type)]) + "variables";
    for (const DriverVar &v : d->vars) {
      line += "\n    " + v.name + " = " + driver_ref_label(doc, v.source);
    }
    if (d->remap) {
      char remap[96];
      std::snprintf(remap, sizeof(remap), "\n    mapped %g..%g to %g..%g", d->from_min, d->from_max, d->to_min, d->to_max);
      line += remap;
    }
    if (!d->error.empty()) {
      line += "\n    Not working: " + d->error;
    }
    text += (text.empty() ? "" : "\n") + line;
  }
  return "Driven: " + text + "\n\nRight-click to edit, copy or delete the driver";
}

/* "12.0°", "0.50", "(1.20, 3.00)": a value as its field shows it (angles in degrees). */
std::string affected_value(const std::string &path, float2 v, bool vector, int component)
{
  const bool angle = path == "rotation" || (path.size() >= 5 && path.compare(path.size() - 5, 5, "angle") == 0);
  const auto one = [&](float x) {
    char text[32];
    if (angle) {
      std::snprintf(text, sizeof(text), "%.1f\xC2\xB0", double(x) * 57.29577951308232);
    }
    else {
      std::snprintf(text, sizeof(text), "%.2f", double(x));
    }
    return std::string(text);
  };
  if (!vector) {
    return one(v.x);
  }
  if (component == 0 || component == 1) {
    return one(component == 0 ? v.x : v.y);
  }
  return one(v.x) + ", " + one(v.y);
}

/* A row's icon, left of its name: a bone, a knob in its box, a fix's line of poses, an action's play, a driver's
 * purple. */
void affected_icon(ImDrawList *dl, const std::string &kind, ImVec2 c, float s)
{
  const ImU32 col = ImGui::GetColorU32(ImGuiCol_Text);
  if (kind == "ACTION_BONE") {
    dl->AddQuad(ImVec2(c.x - s, c.y), ImVec2(c.x - s * 0.45f, c.y - s * 0.45f), ImVec2(c.x + s, c.y),
                ImVec2(c.x - s * 0.45f, c.y + s * 0.45f), col, 1.2f);
  }
  else if (kind == "KNOB") {
    dl->AddRect(c - ImVec2(s, s) * 0.85f, c + ImVec2(s, s) * 0.85f, col, 1.0f, 0, 1.2f);
    dl->AddCircleFilled(c + ImVec2(s * 0.3f, -s * 0.3f), s * 0.32f, col);
  }
  else if (kind == "FIX") {
    const ImVec2 a(c.x - s * 0.85f, c.y + s * 0.55f), b(c.x + s * 0.85f, c.y - s * 0.55f);
    dl->AddLine(a, b, col, 1.2f);
    dl->AddCircleFilled(a, s * 0.28f, col);
    dl->AddCircleFilled(c, s * 0.28f, col);
    dl->AddCircleFilled(b, s * 0.28f, col);
  }
  else if (kind == "ACTION") {
    dl->AddTriangleFilled(ImVec2(c.x - s * 0.5f, c.y - s * 0.7f), ImVec2(c.x + s * 0.7f, c.y),
                          ImVec2(c.x - s * 0.5f, c.y + s * 0.7f), col);
  }
  else if (kind == "DRIVER") {
    dl->AddCircleFilled(c, s * 0.6f, ImGui::GetColorU32(DRIVEN_HOVER));
  }
}

}  // namespace

std::vector<AffectedRow> ui_affected_rows(Document &doc, uint64_t layer_id, const std::string &path, int component)
{
  std::vector<AffectedRow> rows;
  Layer *layer = path.empty() ? nullptr : layer_find(doc, layer_id);
  if (!layer) {
    return rows;
  }
  const std::vector<ChannelSource> sources = layer_channel_sources(doc, *layer, path);
  float2 own, shown;
  bool vector = false;
  if (!sources.empty() && layer_channel_own_value(*layer, path, &own, &shown, &vector)) {
    AffectedRow row;
    row.kind = "OWN";
    row.name = "Own value " + affected_value(path, own, vector, component) + " \xE2\x86\x92 " +
               affected_value(path, shown, vector, component);
    rows.push_back(std::move(row));
  }
  const auto percent = [](float amount) { return std::to_string(int(std::lround(amount * 100.0f))) + "%"; };
  for (const ChannelSource &s : sources) {
    AffectedRow row;
    row.layer = s.owner;
    row.bone = s.bone;
    row.action = s.action;
    switch (s.kind) {
      case ChannelSourceKind::ActionBone:
      case ChannelSourceKind::Knob:
        row.kind = s.kind == ChannelSourceKind::Knob ? "KNOB" : "ACTION_BONE";
        row.name = s.bone;
        row.detail = s.action + " \xC2\xB7 " + percent(s.amount);
        break;
      case ChannelSourceKind::Fix:
        row.kind = "FIX";
        row.name = s.action;
        row.detail = "fix \xC2\xB7 " + percent(s.amount);
        break;
      case ChannelSourceKind::Action:
        row.kind = "ACTION";
        row.name = s.action;
        row.detail = "action \xC2\xB7 " + percent(s.amount);
        break;
    }
    rows.push_back(std::move(row));
  }
  /* Drivers, a two-way link's driven side's too (named by what it follows). */
  static const char *const TYPES[] = {"", "Average of variables", "Sum of variables", "Smallest of variables",
                                      "Largest of variables"};
  for (const DriverRef &r : driver_field_refs(doc, layer_id, path, component)) {
    const Driver *d = driver_find(doc, r);
    if (!d) {
      continue;
    }
    AffectedRow row;
    row.kind = "DRIVER";
    row.name = "Driver";
    row.detail = d->two_way && d->vars.size() == 1 ? "2-Way Linked with " + driver_ref_label(doc, d->vars.front().source)
                 : d->type == DriverType::Expression ? d->expression
                                                     : std::string(TYPES[int(d->type)]);
    row.layer = layer_id;
    rows.push_back(std::move(row));
  }
  return rows;
}

int ui_driver_field_look(Document &doc, uint64_t layer, const std::string &path, int component, bool *r_linked)
{
  return field_state(doc, {layer, path, component}, r_linked);
}

std::string ui_affected_summary(const std::vector<AffectedRow> &rows)
{
  static const std::pair<const char *, const char *> KINDS[] = {{"ACTION_BONE", "action bone"},
                                                                {"KNOB", "knob"},
                                                                {"FIX", "fix"},
                                                                {"ACTION", "action"},
                                                                {"DRIVER", "driver"}};
  std::string text;
  for (const auto &[kind, word] : KINDS) {
    const int n = int(std::count_if(rows.begin(), rows.end(), [&](const AffectedRow &r) { return r.kind == kind; }));
    if (n == 0) {
      continue;
    }
    std::string words = word;
    if (n > 1) {
      words += std::string(kind) == "FIX" ? "es" : "s";
    }
    text += (text.empty() ? "Moved by " : ", ") + std::to_string(n) + " " + words;
  }
  return text;
}

void ui_affected_go(Context &C, uint64_t layer, const std::string &path, int component, const AffectedRow &row)
{
  if (row.kind == "DRIVER") {
    g_editor = {true, true, Field{layer, path, component}, 0};
    return;
  }
  if (row.kind == "OWN" || !row.layer) {
    return;
  }
  operator_call(C, "armature.bone_go", {{"layer", std::to_string(row.layer)}, {"bone", row.bone}});
  properties_show_bone(C, row.layer, !row.bone.empty(), row.kind == "FIX" ? row.action : std::string());
}

bool ui_affected_available(Document &doc, uint64_t layer_id, const std::string &path)
{
  Layer *layer = path.empty() ? nullptr : layer_find(doc, layer_id);
  ChannelRef ref;
  return layer && layer_channel(*layer, path, &ref);
}

int ui_affected_count(const std::vector<AffectedRow> &rows)
{
  return int(std::count_if(rows.begin(), rows.end(), [](const AffectedRow &r) { return r.kind != "OWN"; }));
}

bool ui_affected_menu(Context &C, uint64_t layer, const std::string &path, int component)
{
  /* On every animatable property, empty when nothing moves it. */
  if (!C.document || !ui_affected_available(*C.document, layer, path)) {
    return false;
  }
  const std::vector<AffectedRow> rows = ui_affected_rows(*C.document, layer, path, component);
  /* How many move it, left of the arrow: measured on this menu before the submenu opens (then it is the current
   * window), the label's spaces keeping room for it however narrow the menu is. */
  ImGuiWindow *menu = ImGui::GetCurrentWindow();
  const float y = ImGui::GetCursorScreenPos().y;
  const bool open = ui_submenu_begin("Affected By      ###affected_by");
  const std::string count = std::to_string(ui_affected_count(rows));
  const ImGuiStyle &style = ImGui::GetStyle();
  const float right = menu->Pos.x + menu->Size.x - style.WindowPadding.x - ImGui::GetFontSize() * 1.25f;
  menu->DrawList->AddText(ImVec2(right - ImGui::CalcTextSize(count.c_str()).x, y),
                          ImGui::GetColorU32(ImGuiCol_TextDisabled), count.c_str());
  if (open) {
    const float s = ImGui::GetFontSize() * 0.36f;
    const float indent = ImGui::GetFontSize() * 1.4f;
    for (size_t i = 0; i < rows.size(); i++) {
      const AffectedRow &row = rows[i];
      if (row.kind == "OWN") {
        ImGui::TextDisabled("%s", row.name.c_str());
        ImGui::Separator();
        continue;
      }
      ImGui::PushID(int(i));
      const ImVec2 at = ImGui::GetCursorScreenPos();
      ImGui::SetCursorScreenPos(ImVec2(at.x + indent, at.y));
      const bool chosen = ImGui::MenuItem(row.name.c_str(), row.detail.c_str());
      const ImVec2 lo = ImGui::GetItemRectMin(), hi = ImGui::GetItemRectMax();
      affected_icon(ImGui::GetWindowDrawList(), row.kind, ImVec2(at.x + indent * 0.5f, (lo.y + hi.y) * 0.5f), s);
      if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
        ImGui::SetTooltip(row.kind == "DRIVER" ? "Open its Driver window"
                          : row.kind == "FIX"  ? "Select its bone and show the fix in the Bone tab"
                          : row.kind == "ACTION" ? "Show its bone layer's Actions"
                                                 : "Select it");
      }
      if (chosen) {
        ui_affected_go(C, layer, path, component, row);
      }
      ImGui::PopID();
    }
    ui_submenu_end();
  }
  return true;
}

void ui_driver_next(uint64_t layer, const std::string &path)
{
  g_next = {layer, path, -1};
}

bool ui_driver_next_take(uint64_t *r_layer, std::string *r_path)
{
  if (!g_next.valid()) {
    return false;
  }
  *r_layer = g_next.layer;
  *r_path = g_next.path;
  g_next = {};
  return true;
}

bool ui_driver_menu_opened_this_frame()
{
  return g_menu_frame == ImGui::GetFrameCount();
}

int ui_driver_field_begin(Context &C, uint64_t layer, const std::string &path, int component)
{
  ImGui::BeginGroup();
  if (!C.document || path.empty()) {
    return 0;
  }
  const int state = field_state(*C.document, {layer, path, component});
  if (state == 0) {
    return 0;
  }
  const ImVec4 bg = state == 2 ? BROKEN_BG : DRIVEN_BG;
  const ImVec4 hover = state == 2 ? BROKEN_HOVER : DRIVEN_HOVER;
  ImGui::PushStyleColor(ImGuiCol_FrameBg, bg);
  ImGui::PushStyleColor(ImGuiCol_FrameBgHovered, hover);
  ImGui::PushStyleColor(ImGuiCol_FrameBgActive, hover);
  ImGui::PushStyleColor(ImGuiCol_CheckboxSelectedBg, hover);
  return 4;
}

void ui_driver_field_end(Context &C, uint64_t layer, const std::string &path, int component, int pushed)
{
  ImGui::EndGroup();
  ImGui::PopStyleColor(pushed);
  if (!C.document || path.empty() || driver_ref_size(*C.document, layer, path) == 0) {
    return;
  }
  Document &doc = *C.document;
  const Field field{layer, path, component};
  const ImVec2 lo = ImGui::GetItemRectMin(), hi = ImGui::GetItemRectMax();
  const bool hovered = ImGui::IsWindowHovered(ImGuiHoveredFlags_AllowWhenBlockedByActiveItem) &&
                       ImGui::IsMouseHoveringRect(lo, hi);
  ImGui::PushID(path.c_str());
  ImGui::PushID(component);
  if (hovered && ImGui::IsMouseClicked(ImGuiMouseButton_Right)) {
    ImGui::OpenPopup("##driver_menu");
    g_menu_frame = ImGui::GetFrameCount();
  }
  bool linked = false;
  field_state(doc, field, &linked);
  if (linked) {
    /* Either side of a two-way link: the link icon at the field's right end. */
    const float h = hi.y - lo.y;
    ui_link_icon(ImGui::GetWindowDrawList(), ImVec2(hi.x - h * 0.55f, (lo.y + hi.y) * 0.5f), h * 0.28f,
                 ImGui::GetColorU32(ImGuiCol_Text));
  }
  if (!ImGui::IsAnyItemActive() && ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
    /* What else moves it, one line (its rows in the right-click menu's Affected By). */
    const std::vector<AffectedRow> rows = ui_affected_rows(doc, layer, path, component);
    std::string summary = ui_affected_summary(rows);
    if (pushed > 0 || linked) {
      /* A driver alone is what its purple and "Driven:" (or its link) already say. */
      if (std::all_of(rows.begin(), rows.end(), [](const AffectedRow &r) { return r.kind == "DRIVER"; })) {
        summary.clear();
      }
      const std::string link = linked_text(doc, field);
      ImGui::SetTooltip("%s%s%s", link.empty() ? field_tooltip(doc, field).c_str() : (link + "\nEdit either side").c_str(),
                        summary.empty() ? "" : "\n", summary.c_str());
    }
    else if (!summary.empty()) {
      /* Under the field's own tooltip, if it has one. */
      ImGui::BeginTooltip();
      ImGui::TextUnformatted(summary.c_str());
      ImGui::EndTooltip();
    }
  }
  if (ui_menu_begin("##driver_menu")) {
    if (ui_affected_menu(C, layer, path, component)) {
      ImGui::Separator();
    }
    const bool driven = field_state(doc, field) > 0;
    const std::vector<OpArgs> args = field_args(field);
    if (driven) {
      if (ui_menu_item("Edit Driver...")) {
        g_editor = {true, true, field, 0};
      }
      if (ui_menu_item("Copy Driver")) {
        operator_call(C, "anim.driver_copy", args[0]);
      }
    }
    else {
      if (ui_menu_item("Add Driver...")) {
        OpArgs add = args[0];
        operator_call(C, "anim.driver_add", add);
        g_editor = {true, true, field, 0};
      }
      if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
        ImGui::SetTooltip("Drive it with an expression or other values (tip: type #frame/10 into a number field)");
      }
      if (ui_menu_item("Copy As New Driver")) {
        operator_call(C, "anim.driver_copy_new", args[0]);
      }
      if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
        ImGui::SetTooltip("Copy a driver that reads this: Paste Driver on another field makes it follow this one");
      }
    }
    const size_t copied = driver_clipboard().size();
    const size_t size = driver_field_refs(doc, layer, path, component).size();
    if (copied > 1 && copied != size) {
      /* Several numbers copied (a Scale's X and Y) onto a field with another count (one number): one of
       * them, picked by what it reads. */
      for (size_t k = 0; k < copied; k++) {
        const Driver &d = driver_clipboard()[k];
        const std::string what = d.vars.empty() ? "Part " + std::to_string(k + 1) : driver_ref_label(doc, d.vars.front().source);
        if (ui_menu_item(("Paste Driver: " + what + "##paste" + std::to_string(k)).c_str())) {
          OpArgs paste = args[0];
          paste["part"] = std::to_string(k);
          operator_call(C, "anim.driver_paste", paste);
        }
      }
    }
    else {
      ImGui::BeginDisabled(copied == 0);
      if (ui_menu_item("Paste Driver")) {
        operator_call(C, "anim.driver_paste", args[0]);
      }
      ImGui::EndDisabled();
      if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal | ImGuiHoveredFlags_AllowWhenDisabled)) {
        ImGui::SetTooltip(copied == 0 ? "Nothing copied yet: right-click a field > Copy As New Driver"
                                      : "Drive this with the copied driver");
      }
    }
    if (!linked_text(doc, field).empty()) {
      ImGui::Separator();
      if (ui_menu_item("Select Linked")) {
        operator_call(C, "anim.driver_select_linked", args[0]);
      }
      bool is_target = false;
      for (const DriverRef &r : driver_field_refs(doc, layer, path, component)) {
        is_target = is_target || driver_two_way_role(doc, r) == 1;
      }
      if (is_target && ui_menu_item("Unlink")) {
        operator_call(C, "anim.driver_unlink", args[0]);
      }
      if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
        ImGui::SetTooltip("Take the link off: this gets keys of its own that move it as the link did");
      }
    }
    if (driven) {
      ImGui::Separator();
      if (ui_menu_item("Delete Driver")) {
        operator_call(C, "anim.driver_remove", args[0]);
      }
    }
    ui_menu_end();
  }
  ImGui::PopID();
  ImGui::PopID();
}

void ui_driver_typed(Context &C, uint64_t layer, const std::string &path, int component)
{
  /* "#expression" typed into a number field (Blender's). A number field typed into is a text field
   * for a while (ImGui's temp input) whose text it reads as a number and then lets go of, so the
   * text is kept here as it is typed, and used when the edit ends (not when it's cancelled). */
  static ImGuiID typing = 0;
  static std::string typed;
  if (!C.document || path.empty()) {
    return;
  }
  ImGuiContext &g = *GImGui;
  const ImGuiID id = ImGui::GetItemID();
  if (id == 0) {
    return;
  }
  if (g.InputTextState.ID == id && (g.ActiveId == id || ImGui::IsItemDeactivated())) {
    typing = id;
    typed.assign(g.InputTextState.TextA.Data ? g.InputTextState.TextA.Data : "", size_t(std::max(g.InputTextState.TextLen, 0)));
  }
  if (!ImGui::IsItemDeactivated() || typing != id) {
    return;
  }
  typing = 0;
  const std::string text = std::move(typed);
  typed.clear();
  if (ImGui::IsKeyDown(ImGuiKey_Escape) || ImGui::IsKeyPressed(ImGuiKey_Escape, false)) {
    return;
  }
  /* "#" and spaces before it allowed; the rest is the expression ("#frame / 10"). */
  const size_t hash = text.find_first_not_of(" 	");
  if (hash == std::string::npos || text[hash] != '#' || text.find_first_not_of(" 	", hash + 1) == std::string::npos) {
    return;
  }
  OpArgs args = field_args({layer, path, component})[0];
  args["expression"] = text.substr(hash + 1);
  operator_call(C, "anim.driver_add", args);
}

/* --- The Driver window --------------------------------------------------------------------------- */

/* The layers a variable can read: every layer, then the camera and the simulation. */
static std::vector<Layer *> source_layers(Document &doc)
{
  std::vector<Layer *> layers;
  for (const Layer *l : document_layers_flat(doc)) {
    layers.push_back(layer_find(doc, l->id));
  }
  layers.push_back(&document_camera(doc));
  layers.push_back(&document_simulation(doc));
  return layers;
}

/* A layer's channels a variable can read: its own and its bones' (not every point's). */
static std::vector<std::string> source_paths(Layer &layer)
{
  std::vector<std::string> paths;
  for (const ChannelRef &ref : layer_channels(layer, true)) {
    if (ref.path.rfind("points[", 0) != 0 && ref.path.rfind("curves[", 0) != 0) {
      paths.push_back(ref.path);
    }
  }
  return paths;
}

/* A variable's source, as three dropdowns: layer, value, and part (X / Y). True when changed. */
static bool source_editor(Document &doc, DriverRef &source)
{
  bool changed = false;
  Layer *current = layer_find(doc, source.layer);
  const float w = ImGui::GetContentRegionAvail().x;
  ImGui::SetNextItemWidth(w * 0.42f);
  /* Layer 0: the document's own (its background, a material), from Copy As New Driver. */
  const char *layer_name = current ? current->name.c_str() : source.layer == 0 && !source.path.empty() ? "Document"
                                                                                                        : "(pick a layer)";
  if (ImGui::BeginCombo("##layer", layer_name)) {
    for (Layer *l : source_layers(doc)) {
      ImGui::PushID(int(l->id & 0x7fffffff));
      if (ImGui::Selectable(l->name.c_str(), current == l)) {
        source.layer = l->id;
        const std::vector<std::string> paths = source_paths(*l);
        source.path = paths.empty() ? std::string() : paths.front();
        source.component = driver_ref_size(doc, l->id, source.path) == 2 ? 0 : -1;
        changed = true;
      }
      ImGui::PopID();
    }
    ImGui::EndCombo();
  }
  ImGui::SameLine();
  const int size = driver_ref_size(doc, source.layer, source.path);
  ImGui::SetNextItemWidth(size == 2 ? w * 0.36f : -FLT_MIN);
  ChannelRef channel;
  std::string shown = "(a value)";
  if (current && !source.path.empty() && layer_channel(*current, source.path, &channel)) {
    shown = channel_label(*current, source.path, false);
  }
  else if (!source.path.empty()) {
    /* A setting (Line Width, a mask row's Grow...): its label after the layer's name. */
    DriverRef whole = source;
    whole.component = -1;
    shown = driver_ref_label(doc, whole);
    const size_t colon = shown.rfind(": ");
    if (colon != std::string::npos && current && shown.rfind(current->name, 0) == 0) {
      shown = shown.substr(current->name.size() + 2);
    }
  }
  if (ImGui::BeginCombo("##path", shown.c_str())) {
    if (current) {
      for (const std::string &p : source_paths(*current)) {
        if (ImGui::Selectable(channel_label(*current, p, false).c_str(), p == source.path)) {
          source.path = p;
          source.component = driver_ref_size(doc, source.layer, p) == 2 ? 0 : -1;
          changed = true;
        }
      }
    }
    ImGui::EndCombo();
  }
  if (size == 2) {
    ImGui::SameLine();
    ImGui::SetNextItemWidth(-FLT_MIN);
    if (ImGui::BeginCombo("##part", source.component == 1 ? "Y" : "X")) {
      for (int c = 0; c < 2; c++) {
        if (ImGui::Selectable(c == 0 ? "X" : "Y", source.component == c)) {
          source.component = c;
          changed = true;
        }
      }
      ImGui::EndCombo();
    }
  }
  if (changed) {
    /* A new source: worked out afresh, not followed to where the old one went. */
    source.bone = 0;
    source.item = 0;
  }
  return changed;
}

void ui_driver_window_draw(Context &C)
{
  EditorState &e = g_editor;
  if (!e.open || !C.document) {
    return;
  }
  Document &doc = *C.document;
  const std::vector<DriverRef> refs = driver_field_refs(doc, e.field.layer, e.field.path, e.field.component);
  /* A fixed width, the height of what it shows. */
  const float width = ImGui::GetFontSize() * 26.0f;
  ImGui::SetNextWindowSizeConstraints(ImVec2(width, 0.0f), ImVec2(width, FLT_MAX));
  if (e.raise) {
    /* Beside the field it was opened from, on the side with room, inside the window. */
    const ImGuiViewport *view = ImGui::GetMainViewport();
    const ImVec2 mouse = ImGui::GetIO().MousePos;
    float x = mouse.x + 24.0f;
    if (x + width > view->WorkPos.x + view->WorkSize.x) {
      x = mouse.x - 24.0f - width;
    }
    const float y = std::clamp(mouse.y - 40.0f, view->WorkPos.y, view->WorkPos.y + view->WorkSize.y * 0.5f);
    ImGui::SetNextWindowPos(ImVec2(std::max(x, view->WorkPos.x), y), ImGuiCond_Always);
    ImGui::SetNextWindowFocus();
    e.raise = false;
  }
  if (!ImGui::Begin("Driver###oanim_driver", &e.open,
                    ImGuiWindowFlags_NoDocking | ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_AlwaysAutoResize))
  {
    ImGui::End();
    return;
  }
  if (refs.empty()) {
    ImGui::TextDisabled("What this drove is gone.");
    ImGui::End();
    return;
  }
  /* One of the field's numbers at a time: a colour's R G B A, a position's X Y. */
  e.part = std::clamp(e.part, 0, int(refs.size()) - 1);
  if (refs.size() > 1) {
    const char *names4[] = {"R", "G", "B", "A"}, *names2[] = {"X", "Y"};
    for (int i = 0; i < int(refs.size()); i++) {
      if (i > 0) {
        ImGui::SameLine(0, 2);
      }
      const bool on = e.part == i;
      const bool has = driver_find(doc, refs[size_t(i)]) != nullptr;
      if (on) {
        ImGui::PushStyleColor(ImGuiCol_Button, ImGui::GetStyleColorVec4(ImGuiCol_ButtonActive));
      }
      if (ImGui::Button((std::string(refs.size() == 4 ? names4[i] : names2[i]) + (has ? "" : " (none)")).c_str())) {
        e.part = i;
      }
      if (on) {
        ImGui::PopStyleColor();
      }
    }
  }
  const DriverRef target = refs[size_t(e.part)];
  ImGui::TextUnformatted(driver_ref_label(doc, target).c_str());
  Driver *d = driver_find(doc, target);
  if (!d) {
    ImGui::TextDisabled("Not driven.");
    if (ImGui::Button("Add Driver")) {
      operator_call(C, "anim.driver_add",
                    {{"layer", std::to_string(target.layer)}, {"path", target.path}, {"component", std::to_string(target.component)}});
    }
    ImGui::End();
    return;
  }
  bool done = false;
  ImGui::Separator();
  const OpArgs target_args = {{"layer", std::to_string(target.layer)}, {"path", target.path},
                              {"component", std::to_string(target.component)}};
  {
    /* 2-Way Linked: allowed only for a driver that can run backwards. */
    float factor = 1.0f;
    std::string why;
    const bool can = d->two_way || driver_two_way_factor(*d, &factor, &why);
    bool linked = d->two_way;
    ImGui::BeginDisabled(!can);
    if (ImGui::Checkbox("2-Way Linked", &linked)) {
      if (!linked) {
        operator_call(C, "anim.driver_two_way", [&] {
          OpArgs a = target_args;
          a["on"] = "0";
          return a;
        }());
      }
      else {
        Driver probe = *d;
        const int from_target = driver_two_way_drop_count(doc, probe, true);
        const int from_source = driver_two_way_drop_count(doc, probe, false);
        if (from_target > 0 && from_source > 0) {
          ImGui::OpenPopup("##keep_keys");
        }
        else {
          OpArgs a = target_args;
          a["keep"] = from_source > 0 ? "TARGET" : "SOURCE";
          operator_call(C, "anim.driver_two_way", a);
        }
      }
    }
    ImGui::EndDisabled();
    if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal | ImGuiHoveredFlags_AllowWhenDisabled)) {
      ImGui::SetTooltip(can ? "This and what its variable reads share one set of keys (the variable's), and either can\n"
                              "be edited: an edit here goes back into it. The expression becomes a Factor and a Flip"
                            : why.c_str());
    }
    if (ImGui::BeginPopup("##keep_keys")) {
      /* Both animated: whose keys stay (the others go). */
      Driver *now = driver_find(doc, target);
      if (now && now->vars.size() == 1) {
        ImGui::TextUnformatted("Both are keyed. Keep keys from:");
        const std::string source_label = driver_ref_label(doc, now->vars.front().source);
        const std::string target_label = driver_ref_label(doc, target);
        const int lose_target = driver_two_way_drop_count(doc, *now, false);
        const int lose_source = driver_two_way_drop_count(doc, *now, true);
        if (ImGui::Selectable((source_label + " (" + std::to_string(lose_target) + " keys of " + target_label + " go)").c_str())) {
          OpArgs a = target_args;
          a["keep"] = "SOURCE";
          operator_call(C, "anim.driver_two_way", a);
        }
        if (ImGui::Selectable((target_label + " (" + std::to_string(lose_source) + " keys of " + source_label + " go)").c_str())) {
          OpArgs a = target_args;
          a["keep"] = "TARGET";
          operator_call(C, "anim.driver_two_way", a);
        }
      }
      ImGui::EndPopup();
    }
    d = driver_find(doc, target);
    if (!d) {
      ImGui::End();
      return;
    }
  }
  if (d->two_way && d->vars.size() == 1) {
    /* Linked: the other side, a Factor and a Flip; Unlink. */
    if (ImGui::BeginTable("##link", 2, ImGuiTableFlags_SizingStretchProp)) {
      ImGui::TableSetupColumn("label", ImGuiTableColumnFlags_WidthFixed, 90.0f);
      ImGui::TableSetupColumn("value", ImGuiTableColumnFlags_WidthStretch);
      const auto row = [](const char *label) {
        ImGui::TableNextRow();
        ImGui::TableSetColumnIndex(0);
        ImGui::AlignTextToFramePadding();
        ImGui::TextUnformatted(label);
        ImGui::TableSetColumnIndex(1);
        ImGui::SetNextItemWidth(-FLT_MIN);
      };
      row("Linked With");
      ImGui::TextUnformatted(driver_ref_label(doc, d->vars.front().source).c_str());
      row("Factor");
      float factor = d->factor;
      if (ui_drag_float("##factor", &factor, 0.01f, 0.001f, 1000.0f, "%.3g") && factor > 1e-6f) {
        d->factor = factor;
      }
      done = done || ImGui::IsItemDeactivatedAfterEdit();
      if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
        ImGui::SetTooltip("How far this moves for each step the other side moves, from their rests (never 0)");
      }
      row("");
      if (ImGui::Checkbox("Flip", &d->flip)) {
        done = true;
      }
      if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
        ImGui::SetTooltip("Move the other way (mirrored partners: a left and right eyelid)");
      }
      row("Value");
      float value = 0.0f;
      driver_ref_read(doc, target, &value);
      ImGui::Text("%.4g", value);
      ImGui::EndTable();
    }
    if (ImGui::Button("Select Linked")) {
      operator_call(C, "anim.driver_select_linked", target_args);
    }
    ImGui::SameLine();
    if (ImGui::Button("Unlink")) {
      operator_call(C, "anim.driver_unlink", target_args);
      ImGui::End();
      return;
    }
    if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
      ImGui::SetTooltip("Take the link off: this gets keys of its own that move it as the link did");
    }
    ImGui::End();
    if (done) {
      drivers_evaluate(doc);
      C.undo->push("Change Driver", doc);
    }
    return;
  }
  if (ImGui::BeginTable("##driver", 2, ImGuiTableFlags_SizingStretchProp)) {
    ImGui::TableSetupColumn("label", ImGuiTableColumnFlags_WidthFixed, 90.0f);
    ImGui::TableSetupColumn("value", ImGuiTableColumnFlags_WidthStretch);
    const auto row = [](const char *label) {
      ImGui::TableNextRow();
      ImGui::TableSetColumnIndex(0);
      ImGui::AlignTextToFramePadding();
      ImGui::TextUnformatted(label);
      ImGui::TableSetColumnIndex(1);
      ImGui::SetNextItemWidth(-FLT_MIN);
    };
    row("Type");
    static const char *const TYPES[] = {"Expression", "Average", "Sum", "Min", "Max"};
    int type = int(d->type);
    if (ImGui::Combo("##type", &type, TYPES, 5)) {
      d->type = DriverType(type);
      done = true;
    }
    if (d->type == DriverType::Expression) {
      row("Expression");
      ImGui::InputText("##expression", &d->expression);
      done = done || ImGui::IsItemDeactivatedAfterEdit();
      if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
        ImGui::SetTooltip("Variables by name, frame, pi; + - * / %% ** ; comparisons, and/or/not, a if test else b;\n"
                          "sin cos tan asin acos atan atan2 sqrt abs sign floor ceil round fmod pow exp log\n"
                          "min max clamp(x, lo, hi) lerp(a, b, t) smoothstep(lo, hi, x) radians degrees");
      }
    }
    row("Value");
    float value = 0.0f;
    driver_ref_read(doc, target, &value);
    if (d->error.empty()) {
      ImGui::Text("%.4g", value);
    }
    else {
      ImGui::TextColored(ImVec4(1.0f, 0.45f, 0.4f, 1.0f), "Not working: %s", d->error.c_str());
    }
    ImGui::EndTable();
  }

  /* The variables. */
  ImGui::Spacing();
  ImGui::TextDisabled("Variables");
  int remove = -1;
  for (size_t i = 0; i < d->vars.size(); i++) {
    DriverVar &v = d->vars[i];
    ImGui::PushID(int(i));
    ImGui::SetNextItemWidth(70.0f);
    ImGui::InputText("##name", &v.name);
    done = done || ImGui::IsItemDeactivatedAfterEdit();
    ImGui::SameLine();
    /* The source's dropdowns fill a strip that leaves room for the remove button. */
    ImGui::BeginChild("##source", ImVec2(ImGui::GetContentRegionAvail().x - ImGui::GetFrameHeight() - 4.0f,
                                         ImGui::GetFrameHeight()),
                      ImGuiChildFlags_None, ImGuiWindowFlags_NoScrollbar | ImGuiWindowFlags_NoBackground);
    done = source_editor(doc, v.source) || done;
    ImGui::EndChild();
    ImGui::SameLine(0, 4.0f);
    if (ImGui::Button("-", ImVec2(ImGui::GetFrameHeight(), 0))) {
      remove = int(i);
    }
    if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
      ImGui::SetTooltip("Remove this variable");
    }
    ImGui::PopID();
  }
  if (remove >= 0) {
    d->vars.erase(d->vars.begin() + remove);
    done = true;
  }
  if (ImGui::Button("+ Add Variable")) {
    DriverVar v;
    v.name = d->vars.empty() ? "var" : "var" + std::to_string(d->vars.size() + 1);
    v.source = {CAMERA_LAYER_ID, "zoom", -1};
    if (Layer *l = layer_find(doc, doc.active_layer)) {
      v.source = {l->id, "rotation", -1};
    }
    d->vars.push_back(v);
    done = true;
  }
  ImGui::SameLine();
  const std::vector<Driver> &clip = driver_clipboard();
  const bool can_paste = clip.size() == 1 && clip[0].vars.size() == 1;
  ImGui::BeginDisabled(!can_paste);
  if (ImGui::Button("Paste as Variable")) {
    DriverVar v = clip[0].vars[0];
    v.name = d->vars.empty() ? "var" : "var" + std::to_string(d->vars.size() + 1);
    d->vars.push_back(v);
    done = true;
  }
  ImGui::EndDisabled();
  if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal | ImGuiHoveredFlags_AllowWhenDisabled)) {
    ImGui::SetTooltip("A variable reading the field you last used Copy As New Driver on");
  }

  /* Remap: a range of the result onto another. */
  ImGui::Spacing();
  if (ImGui::Checkbox("Remap", &d->remap)) {
    done = true;
  }
  if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
    ImGui::SetTooltip("Map a range of the result onto another: an angle of 0..90 onto an opacity of 1..0");
  }
  if (d->remap) {
    ImGui::SameLine();
    if (ImGui::Checkbox("Clamp", &d->clamp)) {
      done = true;
    }
    const float half = (ImGui::GetContentRegionAvail().x - 60.0f - ImGui::GetStyle().ItemSpacing.x) * 0.5f;
    const auto pair = [&](const char *label, float *a, float *b) {
      ImGui::AlignTextToFramePadding();
      ImGui::TextUnformatted(label);
      ImGui::SameLine(60.0f);
      ImGui::PushID(label);
      ImGui::SetNextItemWidth(half);
      ui_drag_float("##a", a, 0.01f, 0.0f, 0.0f, "%.3g");
      done = done || ImGui::IsItemDeactivatedAfterEdit();
      ImGui::SameLine();
      ImGui::SetNextItemWidth(half);
      ui_drag_float("##b", b, 0.01f, 0.0f, 0.0f, "%.3g");
      done = done || ImGui::IsItemDeactivatedAfterEdit();
      ImGui::PopID();
    };
    pair("From", &d->from_min, &d->from_max);
    pair("To", &d->to_min, &d->to_max);
  }
  ImGui::Separator();
  if (ImGui::Button("Delete Driver")) {
    operator_call(C, "anim.driver_remove",
                  {{"layer", std::to_string(target.layer)}, {"path", target.path}, {"component", std::to_string(target.component)}});
    done = false;
  }
  ImGui::End();
  if (done) {
    drivers_evaluate(doc);
    C.undo->push("Change Driver", doc);
  }
}

}  // namespace oanim
