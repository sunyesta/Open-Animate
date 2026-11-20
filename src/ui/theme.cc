#include "ui/theme.hh"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <string>

#include <SDL3/SDL_filesystem.h>

#include "imgui.h"

/* Blender's text shadow, drawn by ImGui's text (patched in cmake/Dependencies.cmake): this much of the text's
 * opacity in black, this far under it. */
extern float GOAnimTextShadowAlpha;
extern float GOAnimTextShadowOffset;

namespace oanim {

static ImVec4 rgb(uint32_t hex, float alpha = 1.0f)
{
  return ImVec4(float((hex >> 16) & 0xff) / 255.0f, float((hex >> 8) & 0xff) / 255.0f, float(hex & 0xff) / 255.0f,
                alpha);
}

static ImFont *g_font_mono = nullptr;
static ImFont *g_font_bold = nullptr;

/* A font of data/fonts: next to the executable in a build (copied there), else in the source tree. */
static std::string font_file(const char *name)
{
  if (const char *base = SDL_GetBasePath()) {
    const std::filesystem::path next = std::filesystem::path(reinterpret_cast<const char8_t *>(base)) / "fonts" / name;
    if (std::filesystem::exists(next)) {
      return next.string();
    }
  }
  return (std::filesystem::path(reinterpret_cast<const char8_t *>(OANIM_FONTS_DIR)) / name).string();
}

static ImFont *font_add(const std::string &path, ImFont *fallback)
{
  return std::filesystem::exists(path) ? ImGui::GetIO().Fonts->AddFontFromFileTTF(path.c_str(), UI_FONT_SIZE)
                                       : fallback;
}

void theme_load_fonts()
{
  ImGuiIO &io = ImGui::GetIO();
  /* Blender's interface font, Inter (data/fonts, from its own release: Blender ships it as .woff2, which ImGui
   * can't read). Segoe UI where it's missing. The first font added is the default. */
  ImFont *ui_font = font_add(font_file("Inter-Regular.ttf"), nullptr);
  if (!ui_font) {
    ui_font = font_add("C:/Windows/Fonts/segoeui.ttf", nullptr);
  }
  if (!ui_font) {
    ui_font = io.Fonts->AddFontDefault();
  }
  g_font_mono = font_add("C:/Windows/Fonts/consola.ttf", ui_font);
  g_font_bold = font_add(font_file("Inter-Bold.ttf"), ui_font);
}

ImFont *theme_font_mono()
{
  return g_font_mono;
}

ImFont *theme_font_bold()
{
  return g_font_bold;
}

void theme_apply_blender(float ui_scale)
{
  /* Blender's widget text: its shadow black at half the text's opacity, a pixel under it (shadow 1, shady -1). */
  GOAnimTextShadowAlpha = 0.5f;
  GOAnimTextShadowOffset = std::max(1.0f, std::round(ui_scale));
  ImGuiStyle style;
  ImVec4 *c = style.Colors;

  /* Blender's selection blue (wcol_regular.inner_sel). */
  const ImVec4 blue = rgb(0x4772b3);

  c[ImGuiCol_Text] = rgb(0xe6e6e6);
  c[ImGuiCol_TextDisabled] = rgb(0x8c8c8c);
  c[ImGuiCol_WindowBg] = rgb(0x303030);
  c[ImGuiCol_ChildBg] = rgb(0x303030, 0.0f);
  c[ImGuiCol_PopupBg] = rgb(0x181818, 0.97f);
  c[ImGuiCol_Border] = rgb(0x242424);
  c[ImGuiCol_BorderShadow] = rgb(0x000000, 0.0f);
  c[ImGuiCol_FrameBg] = rgb(0x545454);
  c[ImGuiCol_FrameBgHovered] = rgb(0x656565);
  c[ImGuiCol_FrameBgActive] = rgb(0x222222);
  c[ImGuiCol_TitleBg] = rgb(0x1d1d1d);
  c[ImGuiCol_TitleBgActive] = rgb(0x1d1d1d);
  c[ImGuiCol_TitleBgCollapsed] = rgb(0x1d1d1d);
  c[ImGuiCol_MenuBarBg] = rgb(0x1d1d1d);
  c[ImGuiCol_ScrollbarBg] = rgb(0x303030, 0.0f);
  c[ImGuiCol_ScrollbarGrab] = rgb(0x545454);
  c[ImGuiCol_ScrollbarGrabHovered] = rgb(0x656565);
  c[ImGuiCol_ScrollbarGrabActive] = rgb(0x767676);
  c[ImGuiCol_CheckMark] = rgb(0xffffff);
  c[ImGuiCol_SliderGrab] = blue;
  c[ImGuiCol_SliderGrabActive] = rgb(0x5680c2);
  c[ImGuiCol_Button] = rgb(0x545454);
  c[ImGuiCol_ButtonHovered] = rgb(0x656565);
  c[ImGuiCol_ButtonActive] = blue;
  /* Panel headers and selectable rows. */
  c[ImGuiCol_Header] = rgb(0x3d3d3d);
  c[ImGuiCol_HeaderHovered] = rgb(0x474747);
  c[ImGuiCol_HeaderActive] = blue;
  c[ImGuiCol_Separator] = rgb(0x242424);
  c[ImGuiCol_SeparatorHovered] = blue;
  c[ImGuiCol_SeparatorActive] = blue;
  c[ImGuiCol_ResizeGrip] = rgb(0x000000, 0.0f);
  c[ImGuiCol_ResizeGripHovered] = rgb(0x4772b3, 0.5f);
  c[ImGuiCol_ResizeGripActive] = blue;
  /* Area tabs (wcol_tab). */
  c[ImGuiCol_Tab] = rgb(0x1d1d1d);
  c[ImGuiCol_TabHovered] = rgb(0x3d3d3d);
  c[ImGuiCol_TabSelected] = rgb(0x303030);
  c[ImGuiCol_TabSelectedOverline] = rgb(0x303030);
  c[ImGuiCol_TabDimmed] = rgb(0x1d1d1d);
  c[ImGuiCol_TabDimmedSelected] = rgb(0x303030);
  c[ImGuiCol_TabDimmedSelectedOverline] = rgb(0x303030);
  c[ImGuiCol_DockingPreview] = rgb(0x4772b3, 0.5f);
  /* The dark gap between areas. */
  c[ImGuiCol_DockingEmptyBg] = rgb(0x161616);
  c[ImGuiCol_TableHeaderBg] = rgb(0x3d3d3d);
  c[ImGuiCol_TableBorderStrong] = rgb(0x242424);
  c[ImGuiCol_TableBorderLight] = rgb(0x242424);
  c[ImGuiCol_TableRowBg] = rgb(0x000000, 0.0f);
  c[ImGuiCol_TableRowBgAlt] = rgb(0xffffff, 0.03f);
  c[ImGuiCol_TextSelectedBg] = rgb(0x4772b3, 0.6f);
  c[ImGuiCol_ModalWindowDimBg] = rgb(0x000000, 0.4f);

  /* Blender widgets: roundness 0.2 of a ~20 px widget, tight spacing, no window borders. */
  style.WindowRounding = 0.0f;
  style.ChildRounding = 0.0f;
  style.FrameRounding = 4.0f;
  style.PopupRounding = 4.0f;
  style.GrabRounding = 4.0f;
  style.TabRounding = 4.0f;
  style.ScrollbarRounding = 8.0f;
  style.WindowBorderSize = 0.0f;
  style.FrameBorderSize = 0.0f;
  style.PopupBorderSize = 1.0f;
  style.WindowPadding = ImVec2(8, 8);
  style.FramePadding = ImVec2(6, 3);
  style.ItemSpacing = ImVec2(6, 4);
  style.ItemInnerSpacing = ImVec2(4, 4);
  style.IndentSpacing = 14.0f;
  style.ScrollbarSize = 10.0f;
  style.GrabMinSize = 8.0f;
  style.WindowMenuButtonPosition = ImGuiDir_None;

  style.ScaleAllSizes(ui_scale);
  /* Rows UI_FRAME_HEIGHT tall whatever the font's size (set after the scaling, which rounds paddings down). */
  style.FramePadding.y = (UI_FRAME_HEIGHT - UI_FONT_SIZE) * 0.5f * ui_scale;
  style.FontSizeBase = UI_FONT_SIZE;
  style.FontScaleDpi = ui_scale;

  ImGui::GetStyle() = style;
}

}  // namespace oanim
