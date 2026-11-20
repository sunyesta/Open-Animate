#pragma once

/* Blender's default theme applied to Dear ImGui. Colours come from Blender's
 * release/datafiles/userdef/userdef_default_theme.c. */

struct ImFont;

namespace oanim {

/* Base font size in pixels at 100% interface scale, as ImGui measures it (ascent to descent): Inter's, whose
 * em is then 11 pixels, as Blender's widget text (11 points at 72 dpi). */
inline constexpr float UI_FONT_SIZE = 11.0f * (1984.0f + 494.0f) / 2048.0f;
/* A field's height (the font and its frame padding), kept from the Segoe UI days so rows don't move. */
inline constexpr float UI_FRAME_HEIGHT = 21.0f;

/* Loads the interface and monospace fonts. Call once after creating the ImGui context. */
void theme_load_fonts();
/* Monospace font for the text editor and console (Blender uses DejaVu Sans Mono). */
ImFont *theme_font_mono();
/* The UI font in bold (Segoe UI Bold), for a title line. */
ImFont *theme_font_bold();
/* Resets the ImGui style to the Blender theme at the given interface scale. */
void theme_apply_blender(float ui_scale);

}  // namespace oanim
