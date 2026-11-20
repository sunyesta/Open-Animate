/* The Properties editor's Gradient tab: a gradient layer's shape, its stops and how each span blends. */

#include "editors/gradient_panel.hh"

#include <algorithm>
#include <cmath>
#include <string>

#include "imgui.h"

#include "anim/gradient_shown.hh"
#include "data/document.hh"
#include "data/gradient.hh"
#include "data/layer.hh"
#include "editors/ui.hh"
#include "ops/operator.hh"
#include "ops/undo.hh"
#include "rna/rna.hh"
#include "wm/context.hh"

namespace oanim {

/* The picked stop follows the points picked in the viewport: the first stop whose point is selected, when the picked
 * one's isn't. */
static void active_stop_follow_selection(Layer &layer)
{
  GradientSettings &g = layer.gradient;
  const int n = int(g.stops.size());
  const auto selected = [&](int i) {
    const int p = drawing_point_index(layer.drawing, g.stops[size_t(i)].point);
    return p >= 0 && layer.drawing.points[size_t(p)].selected;
  };
  g.active_stop = std::clamp(g.active_stop, 0, n - 1);
  g.active_span = std::clamp(g.active_span, 0, n - 2);
  if (selected(g.active_stop)) {
    return;
  }
  for (int i = 0; i < n; i++) {
    if (selected(i)) {
      g.active_stop = i;
      g.active_span = std::min(i, n - 2);
      return;
    }
  }
}

void properties_gradient_tab(Context &C)
{
  Document &doc = *C.document;
  Layer *found = document_active_layer(doc);
  if (!found || !found->is_gradient()) {
    ImGui::TextDisabled("Select a gradient layer.");
    return;
  }
  Layer &layer = *found;
  GradientSettings &g = layer.gradient;
  if (g.stops.size() < 2) {
    return;
  }
  active_stop_follow_selection(layer);
  const rna::PointerRNA ptr{&layer, &Layer::rna()};
  const char *path = "oanim.data.layers.active";
  const std::string id = std::to_string(layer.id);

  if (ui_panel_begin("Gradient")) {
    ui_prop(C, ptr, "gradient_type", path);
    ui_prop(C, ptr, "gradient_ends", path);
    ui_prop(C, ptr, "gradient_mix", path);
    if (g.type == GradientType::Radial) {
      ui_prop(C, ptr, "gradient_squash", path);
    }
    ui_panel_end();
  }

  if (ui_panel_begin("Stops")) {
    /* How far along the path each stop is, as the viewport shows it. */
    const GradientShown shown = gradient_shown(doc, layer, false);
    ImGui::TableNextRow();
    ImGui::TableSetColumnIndex(1);
    const float buttons = ImGui::GetFrameHeight();
    const float list_w = ImGui::GetContentRegionAvail().x - buttons - ImGui::GetStyle().ItemSpacing.x;
    ImGui::BeginGroup();
    for (int i = 0; i < int(g.stops.size()); i++) {
      const GradientStop &s = g.stops[size_t(i)];
      ImGui::PushID(i);
      const ImVec4 col(s.color.r, s.color.g, s.color.b, 0.25f + 0.75f * s.color.a);
      ImGui::ColorButton("##swatch", col, ImGuiColorEditFlags_NoTooltip | ImGuiColorEditFlags_NoDragDrop,
                         ImVec2(ImGui::GetFrameHeight(), ImGui::GetTextLineHeight()));
      ImGui::SameLine();
      const float at = shown.field.valid && size_t(i) < shown.field.stop_arc.size()
                           ? shown.field.stop_arc[size_t(i)] / shown.field.total
                           : 0.0f;
      const std::string label = "Stop " + std::to_string(i + 1);
      const float right = list_w - ImGui::GetCursorPosX() + ImGui::GetCursorStartPos().x;
      if (ImGui::Selectable(label.c_str(), i == g.active_stop, 0, ImVec2(std::max(right, 40.0f), 0))) {
        operator_call(C, "gradient.pick", {{"layer", id}, {"stop", std::to_string(i)}});
      }
      char pct[16];
      std::snprintf(pct, sizeof(pct), "%d%%", int(std::lround(at * 100.0f)));
      const ImVec2 pct_size = ImGui::CalcTextSize(pct);
      ImGui::SameLine(std::max(list_w - pct_size.x - ImGui::GetStyle().FramePadding.x, 0.0f));
      ImGui::TextDisabled("%s", pct);
      ImGui::PopID();
    }
    ImGui::EndGroup();
    ImGui::SameLine();
    ImGui::BeginGroup();
    if (ImGui::Button("+", ImVec2(buttons, buttons))) {
      operator_call(C, "gradient.stop_add", {{"layer", id}});
    }
    if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
      ImGui::SetTooltip("Add a stop at the picked span's tick, coloured as the gradient is there");
    }
    ImGui::BeginDisabled(g.stops.size() <= 2);
    if (ImGui::Button("-", ImVec2(buttons, buttons))) {
      operator_call(C, "gradient.stop_remove", {{"layer", id}});
    }
    if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal | ImGuiHoveredFlags_AllowWhenDisabled)) {
      ImGui::SetTooltip("Remove the picked stop (a gradient keeps at least two)");
    }
    ImGui::EndDisabled();
    ImGui::EndGroup();

    if (g.active_stop >= 0 && g.active_stop < int(g.stops.size())) {
      ui_group_gap();
      GradientStop &stop = g.stops[size_t(g.active_stop)];
      float rgba[4] = {stop.color.r, stop.color.g, stop.color.b, stop.color.a};
      if (ui_color(C, "Color", rgba, nullptr)) {
        stop.color = {rgba[0], rgba[1], rgba[2], rgba[3]};
      }
      if (ImGui::IsItemDeactivatedAfterEdit()) {
        C.undo->push("Gradient Stop Color", doc);
      }
      ui_row("Opacity", [&](float width) {
        float a = stop.color.a;
        ImGui::SetNextItemWidth(width);
        if (ui_drag_float("##stop_opacity", &a, 0.005f, 0.0f, 1.0f, "%.3f", 0, 0.0f, 1.0f)) {
          stop.color.a = std::clamp(a, 0.0f, 1.0f);
        }
        if (ImGui::IsItemDeactivatedAfterEdit()) {
          C.undo->push("Gradient Stop Opacity", doc);
        }
      });
    }
    ui_panel_end();
  }

  const int span = std::clamp(g.active_span, 0, int(g.stops.size()) - 2);
  const std::string span_title =
      "Blend: Stop " + std::to_string(span + 1) + " to Stop " + std::to_string(span + 2);
  if (ui_panel_begin("Blend", span_title, 0u)) {
    GradientStop &s = g.stops[size_t(span)];
    ui_row("Falloff", [&](float width) {
      static const char *const NAMES[] = {"Smooth", "Linear", "Hard"};
      static const char *const IDS[] = {"SMOOTH", "LINEAR", "HARD"};
      const float w = (width - ImGui::GetStyle().ItemSpacing.x * 2.0f) / 3.0f;
      for (int i = 0; i < 3; i++) {
        if (i > 0) {
          ImGui::SameLine();
        }
        const bool on = int(s.falloff) == i;
        if (on) {
          ImGui::PushStyleColor(ImGuiCol_Button, ImGui::GetStyleColorVec4(ImGuiCol_ButtonActive));
        }
        if (ImGui::Button(NAMES[i], ImVec2(w, 0)) && !on) {
          operator_call(C, "gradient.span_set", {{"layer", id}, {"span", std::to_string(span)}, {"falloff", IDS[i]}});
        }
        if (on) {
          ImGui::PopStyleColor();
        }
        if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
          ImGui::SetTooltip("%s", i == 0   ? "Smoothly through the stops, with no line where a stop is"
                                  : i == 1 ? "Evenly from one stop's colour to the next"
                                           : "At once, at the tick");
        }
      }
    });
    ui_row("Midpoint", [&](float width) {
      float pct = s.midpoint * 100.0f;
      ImGui::SetNextItemWidth(width);
      if (ui_drag_float("##midpoint", &pct, 0.25f, 2.0f, 98.0f, "%.0f%%", 0, 2.0f, 98.0f)) {
        s.midpoint = std::clamp(pct / 100.0f, 0.02f, 0.98f);
      }
      if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) {
        ImGui::SetTooltip("Where along the span its colours meet half way: its tick on the path");
      }
      if (ImGui::IsItemDeactivatedAfterEdit()) {
        C.undo->push("Gradient Midpoint", doc);
      }
    });
    ui_panel_end();
  }
}

}  // namespace oanim
