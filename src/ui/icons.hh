#pragma once

/* The interface's icons: SVG files in scripts/icons on a 16 x 16 grid, white where they draw and
 * black where they cut out what was drawn before them. Each is drawn into a texture at the size it
 * is shown (as Blender draws its SVG icons at the interface's scale), so it stays sharp and centred
 * at every size, and is tinted as it is drawn. */

#include "imgui.h"

namespace oanim {

/* Icon colours, Blender's (its theme's icon_scene, icon_object, icon_object_data). */
inline constexpr ImU32 ICON_COL_DOCUMENT = IM_COL32(0xcc, 0xcc, 0xcc, 255);
inline constexpr ImU32 ICON_COL_LAYER = IM_COL32(0x74, 0xa2, 0xff, 255);
inline constexpr ImU32 ICON_COL_DATA = IM_COL32(0x00, 0xd4, 0xa3, 255);

/* Draws icon `name` (scripts/icons/<name>.svg) filling the square of `size` pixels at `min`, in `col`.
 * The square is put on whole pixels. False when there is no such icon (nothing is drawn). */
bool ui_icon(ImDrawList *dl, const char *name, ImVec2 min, float size, ImU32 col);
/* The same, centred on `center`. */
bool ui_icon_centered(ImDrawList *dl, const char *name, ImVec2 center, float size, ImU32 col);

}  // namespace oanim
