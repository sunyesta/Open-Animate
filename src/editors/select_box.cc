#include "editors/select_box.hh"

#include <algorithm>
#include <cmath>

namespace oanim {

SelectBoxKind select_box_kind(bool shift, bool ctrl, bool alt, bool alt_removes)
{
  if (ctrl || (alt && alt_removes)) {
    return SelectBoxKind::Remove;
  }
  return shift ? SelectBoxKind::Add : SelectBoxKind::Set;
}

SelectBoxKind select_box_kind_now(bool alt_removes)
{
  const ImGuiIO &io = ImGui::GetIO();
  return select_box_kind(io.KeyShift, io.KeyCtrl, io.KeyAlt, alt_removes);
}

/* A dashed line: dashes of 5 pixels, gaps of 4. */
static void dashed_line(ImDrawList *dl, ImVec2 p, ImVec2 q, ImU32 color)
{
  const float dx = q.x - p.x, dy = q.y - p.y;
  const float length = std::sqrt(dx * dx + dy * dy);
  if (length < 1e-3f) {
    return;
  }
  const float ux = dx / length, uy = dy / length;
  for (float s = 0.0f; s < length; s += 9.0f) {
    const float e = std::min(s + 5.0f, length);
    dl->AddLine(ImVec2(p.x + ux * s, p.y + uy * s), ImVec2(p.x + ux * e, p.y + uy * e), color);
  }
}

void select_box_draw(ImDrawList *dl, ImVec2 a, ImVec2 b, SelectBoxKind kind)
{
  const ImVec2 lo(std::min(a.x, b.x), std::min(a.y, b.y)), hi(std::max(a.x, b.x), std::max(a.y, b.y));
  if (kind == SelectBoxKind::Remove) {
    const ImU32 line = IM_COL32(0xff, 0x8c, 0x8c, 0xd8);
    dl->AddRectFilled(lo, hi, IM_COL32(0xff, 0x50, 0x50, 26));
    dashed_line(dl, lo, ImVec2(hi.x, lo.y), line);
    dashed_line(dl, ImVec2(hi.x, lo.y), hi, line);
    dashed_line(dl, hi, ImVec2(lo.x, hi.y), line);
    dashed_line(dl, ImVec2(lo.x, hi.y), lo, line);
  }
  else {
    dl->AddRectFilled(lo, hi, IM_COL32(0xff, 0xff, 0xff, 20));
    dl->AddRect(lo, hi, IM_COL32(0xff, 0xff, 0xff, 160));
  }
  if (kind == SelectBoxKind::Set) {
    return;
  }
  /* A small tag past the corner the mouse holds, clear of the cursor: a sign drawn in lines (a text "-" is a speck). */
  const ImVec2 at(b.x + 12.0f, b.y + 12.0f);
  const float size = 14.0f, half = size * 0.5f, arm = 4.0f;
  dl->AddRectFilled(at, ImVec2(at.x + size, at.y + size),
                    kind == SelectBoxKind::Add ? IM_COL32(0x47, 0x72, 0xb3, 0xff) : IM_COL32(0xaa, 0x33, 0x33, 0xff), 3.0f);
  const ImVec2 c(at.x + half, at.y + half);
  const ImU32 white = IM_COL32(0xff, 0xff, 0xff, 0xff);
  dl->AddLine(ImVec2(c.x - arm, c.y), ImVec2(c.x + arm + 1.0f, c.y), white, 2.0f);
  if (kind == SelectBoxKind::Add) {
    dl->AddLine(ImVec2(c.x, c.y - arm), ImVec2(c.x, c.y + arm + 1.0f), white, 2.0f);
  }
}

}  // namespace oanim
