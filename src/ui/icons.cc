#include "ui/icons.hh"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include <SDL3/SDL_opengl.h>

#include "python/py_runtime.hh"

/* NanoSVG is someone else's code, compiled here: not held to /W4. */
#pragma warning(push, 0)
#define NANOSVG_IMPLEMENTATION
#define NANOSVGRAST_IMPLEMENTATION
#include <cstdio>
#include <cstring>
#include "nanosvg.h"
#include "nanosvgrast.h"
#pragma warning(pop)

namespace oanim {

namespace {

struct ImageDelete {
  void operator()(NSVGimage *image) const { nsvgDelete(image); }
};
using ImagePtr = std::unique_ptr<NSVGimage, ImageDelete>;

/* Each icon read once (null when there is no such file or it can't be read). */
NSVGimage *icon_image(const std::string &name)
{
  static std::map<std::string, ImagePtr> images;
  auto it = images.find(name);
  if (it == images.end()) {
    ImagePtr image;
    std::ifstream file(python::scripts_dir() / "icons" / (name + ".svg"), std::ios::binary);
    if (file) {
      std::stringstream text;
      text << file.rdbuf();
      std::string svg = text.str();
      image.reset(nsvgParse(svg.data(), "px", 96.0f));
      if (image && (image->width <= 0.0f || !image->shapes)) {
        image.reset();
      }
    }
    it = images.emplace(name, std::move(image)).first;
  }
  return it->second.get();
}

bool paint_black(const NSVGpaint &paint)
{
  return paint.type == NSVG_PAINT_COLOR && (paint.color & 0x00ffffffu) == 0;
}

/* A shape drawn in black cuts out: its fill, or its line when it has no fill. */
bool shape_cuts(const NSVGshape &shape)
{
  return shape.fill.type == NSVG_PAINT_NONE ? paint_black(shape.stroke) : paint_black(shape.fill);
}

/* The icon's coverage at `px` pixels square: shape by shape, so black shapes take away what is under them
 * (NanoSVG would paint them black). */
std::vector<float> icon_coverage(NSVGimage &image, int px)
{
  static NSVGrasterizer *rasterizer = nsvgCreateRasterizer();
  std::vector<float> cover(size_t(px) * size_t(px), 0.0f);
  std::vector<unsigned char> shape_rgba(cover.size() * 4);
  const float scale = float(px) / image.width;
  NSVGshape *all = image.shapes;
  for (NSVGshape *shape = all; shape; shape = shape->next) {
    NSVGshape *next = shape->next;
    shape->next = nullptr;
    image.shapes = shape;
    nsvgRasterize(rasterizer, &image, 0.0f, 0.0f, scale, shape_rgba.data(), px, px, px * 4);
    shape->next = next;
    const bool cuts = shape_cuts(*shape);
    for (size_t i = 0; i < cover.size(); i++) {
      const float a = float(shape_rgba[i * 4 + 3]) / 255.0f;
      cover[i] = cuts ? cover[i] * (1.0f - a) : a + cover[i] * (1.0f - a);
    }
  }
  image.shapes = all;
  return cover;
}

/* The icon's texture at `px` pixels: white, its shape in the alpha, so drawing it tints it. */
GLuint icon_texture(const std::string &name, int px)
{
  static std::map<std::pair<std::string, int>, GLuint> textures;
  const auto key = std::make_pair(name, px);
  if (const auto it = textures.find(key); it != textures.end()) {
    return it->second;
  }
  GLuint texture = 0;
  if (NSVGimage *image = icon_image(name); image && px > 0 && px <= 512) {
    const std::vector<float> cover = icon_coverage(*image, px);
    std::vector<uint8_t> rgba(cover.size() * 4, 255);
    for (size_t i = 0; i < cover.size(); i++) {
      rgba[i * 4 + 3] = uint8_t(std::lround(std::clamp(cover[i], 0.0f, 1.0f) * 255.0f));
    }
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, px, px, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba.data());
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
  }
  textures.emplace(key, texture);
  return texture;
}

}  // namespace

bool ui_icon(ImDrawList *dl, const char *name, ImVec2 min, float size, ImU32 col)
{
  /* Pixel for pixel: the texture is made at the size shown and put on whole pixels. */
  const int px = int(std::lround(size));
  const GLuint texture = icon_texture(name, px);
  if (!texture) {
    return false;
  }
  const ImVec2 at(std::round(min.x), std::round(min.y));
  dl->AddImage(ImTextureRef(ImTextureID(intptr_t(texture))), at, ImVec2(at.x + float(px), at.y + float(px)),
               ImVec2(0, 0), ImVec2(1, 1), col);
  return true;
}

bool ui_icon_centered(ImDrawList *dl, const char *name, ImVec2 center, float size, ImU32 col)
{
  const float px = std::round(size);
  return ui_icon(dl, name, ImVec2(center.x - px * 0.5f, center.y - px * 0.5f), px, col);
}

}  // namespace oanim
