#pragma once

/* The box a drag draws to select (points, handles, bones, path dots, timeline keys): what it does, by the keys held as
 * in Blender's Select Box (none: a new selection; Shift: added to it; Ctrl: taken out of it), and how it shows that while
 * it is dragged, so the mode can be told before letting go. */

#include <imgui.h>

namespace oanim {

enum class SelectBoxKind { Set, Add, Remove };

/* Ctrl wins over Shift (both held takes out). `alt_removes`: where Alt takes out too (the Transform tool's box over
 * bones, which took Alt before Ctrl). */
SelectBoxKind select_box_kind(bool shift, bool ctrl, bool alt, bool alt_removes = false);

/* The keys held now. */
SelectBoxKind select_box_kind_now(bool alt_removes = false);

/* The box from `a` to `b`: white and faint for a new selection; with a "+" by the corner being dragged to add; red,
 * dashed, with a "-", to take out. */
void select_box_draw(ImDrawList *dl, ImVec2 a, ImVec2 b, SelectBoxKind kind);

}  // namespace oanim
