#include "editors/pose_thumbnails.hh"

#include <algorithm>
#include <bit>
#include <functional>
#include <map>
#include <memory>
#include <vector>

#include "imgui.h"
#include <SDL3/SDL_opengl.h>

#include "anim/controller_preview.hh"
#include "core/profile.hh"
#include "data/document.hh"
#include "gpu/scene_renderer.hh"
#include "media/media.hh"
#include "ops/pose_library.hh"

namespace oanim {

namespace {

struct Thumb {
  GLuint texture = 0;
  uint64_t stamp = 0;
  bool drawn = false;
};

/* By pose id. */
std::map<uint64_t, Thumb> g_thumbs;
std::unique_ptr<SceneRenderer> g_renderer;
int g_budget_frame = -1;
/* Seconds the document stays unchanged before pictures out of date are drawn again. */
constexpr double QUIET = 0.3;

uint64_t mix(uint64_t h, uint64_t v)
{
  return (h ^ v) * 0x100000001b3ull + 0x9e3779b97f4a7c15ull;
}

uint64_t stamp_of(const Document &doc, const PoseAsset &pose, int size)
{
  return mix(mix(mix(mix(controller_document_generation(), uint64_t(doc.frame_current)), uint64_t(size)),
                 media_generation()),
             mix(mix(mix(uint64_t(std::hash<std::string>{}(pose.pose)), uint64_t(std::bit_cast<uint32_t>(pose.frame_size))),
                     uint64_t(std::bit_cast<uint32_t>(pose.frame_center.x))),
                 uint64_t(std::bit_cast<uint32_t>(pose.frame_center.y))));
}

}  // namespace

unsigned int pose_thumbnail(Document &doc, const PoseAsset &pose, int size)
{
  OANIM_PROFILE("pose_thumbnail");
  Thumb &thumb = g_thumbs[pose.id];
  if (thumb.drawn && thumb.stamp == stamp_of(doc, pose, size)) {
    return thumb.texture;
  }
  /* Drawn again once the document has been still a moment: each is a copy of the document, posed. */
  static uint64_t last_generation = 0;
  static double changed_at = 0.0;
  const double now = ImGui::GetTime();
  if (const uint64_t generation = controller_document_generation(); generation != last_generation) {
    last_generation = generation;
    changed_at = now;
  }
  if (thumb.drawn && now - changed_at < QUIET) {
    return thumb.texture;
  }
  if (g_budget_frame == ImGui::GetFrameCount()) {
    return thumb.texture;
  }
  g_budget_frame = ImGui::GetFrameCount();
  Document posed;
  float2 lo, hi;
  std::vector<uint64_t> layers;
  const bool any = pose_posed_copy(doc, pose, posed, &lo, &hi, &layers);
  /* Its stamp as the document stands after it (making the copy isn't a change). */
  thumb.stamp = stamp_of(doc, pose, size);
  thumb.drawn = true;
  if (!any) {
    return thumb.texture;
  }
  /* Framed as Save Pose or Edit Frame left it, else on what it moves, with room around. */
  float2 center;
  float extent = 0.0f;
  pose_frame_choose(pose, lo, hi, &center, &extent);
  const float scale = float(size) / extent;
  const Transform2D to_pixels{scale, 0, 0, scale, float(size) * 0.5f - center.x * scale, float(size) * 0.5f - center.y * scale};
  if (!g_renderer) {
    g_renderer = std::make_unique<SceneRenderer>();
  }
  g_renderer->set_show_guides(false);
  g_renderer->set_local_view(posed, layers);
  const unsigned int rendered = g_renderer->render(posed, size, size, to_pixels, 8, 4);
  std::vector<uint8_t> rgba;
  int w = 0, h = 0;
  if (rendered == 0 || !g_renderer->read_pixels(rgba, &w, &h)) {
    return thumb.texture;
  }
  /* Straight alpha, as ImGui blends. */
  for (size_t i = 0; i + 3 < rgba.size(); i += 4) {
    const int a = rgba[i + 3];
    if (a > 0 && a < 255) {
      for (int k = 0; k < 3; k++) {
        rgba[i + size_t(k)] = uint8_t(std::min(255, rgba[i + size_t(k)] * 255 / a));
      }
    }
  }
  if (!thumb.texture) {
    glGenTextures(1, &thumb.texture);
  }
  glBindTexture(GL_TEXTURE_2D, thumb.texture);
  glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
  glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba.data());
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
  return thumb.texture;
}

}  // namespace oanim
