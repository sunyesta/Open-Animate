#pragma once

/* A frame as vectors, for the SVG and PDF exports: what Render Frame draws, through the camera, as a tree of
 * paths, groups, pictures and masks, in pixels (y down, the picture's top left at 0, 0). Fills are their Bezier
 * outlines; a line is the outline of what the renderer draws for it (its width at every point, its joins and
 * ends), one path filled; a brushed line is a picture of its stamps; masks are luminance masks painted as the
 * cards paint theirs (Start With, Add and Subtract, Invert, Union, Difference and Intersection, Grow and Shrink,
 * Extend, Fills or Strokes Only, Inside the Stroke, Clip to Below); faded groups and see-through layers are groups
 * with an opacity; media pictures are pictures. */

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "core/math.hh"

namespace oanim {

struct Document;

/* Path data: each op takes its points in turn (Move and Line one, Cubic three: two handles and the end; Close
 * none). */
struct VectorPath {
  enum Op : uint8_t { Move, Line, Cubic, Close };
  std::vector<Op> ops;
  std::vector<float2> points;
  bool empty() const { return ops.empty(); }
};

struct VectorNode {
  enum Kind : uint8_t { Group, Path, Picture } kind = Group;
  /* Path: filled in `color` (its own alpha times `alpha`), Even-Odd or Nonzero. */
  VectorPath path;
  Color color;
  float alpha = 1.0f;
  bool even_odd = false;
  /* Picture: VectorScene::pictures[picture], the unit square (0, 0 its top left) placed by `place`. */
  int picture = -1;
  Transform2D place;
  /* Group: drawn together, faded by `opacity` as one. */
  std::vector<VectorNode> children;
  float opacity = 1.0f;
  /* Shown only where VectorScene::masks[mask] is light (-1: everywhere). */
  int mask = -1;
  /* The layer a group draws (0: none), and whether it shows in renders (a hidden layer or a guide doesn't). */
  uint64_t layer = 0;
  bool layer_shown = true;
};

/* Straight (not premultiplied) RGBA, rows top first. */
struct VectorPicture {
  int width = 0, height = 0;
  std::vector<uint8_t> rgba;
};

/* A luminance mask: its nodes painted on black (white shows). */
struct VectorMask {
  std::vector<VectorNode> content;
};

struct VectorScene {
  int width = 0, height = 0;
  std::vector<VectorNode> nodes;
  std::vector<VectorMask> masks;
  std::vector<VectorPicture> pictures;
  /* What it holds, for the report. */
  int fills = 0, lines = 0, brushed = 0;
};

/* What vector_scene keeps between calls (VectorSceneOptions::cache), so a layer drawn as last time (its drawing as
 * evaluated, where it goes, what its shapes are drawn as) isn't worked out again: the iPad's canvas, made after every
 * edit. Layers with brushed lines or lines cut by other layers are always worked out. One caller at a time. */
class VectorSceneCache {
 public:
  VectorSceneCache();
  ~VectorSceneCache();
  VectorSceneCache(const VectorSceneCache &) = delete;
  VectorSceneCache &operator=(const VectorSceneCache &) = delete;
  struct Impl;
  std::unique_ptr<Impl> impl;
  /* In the last scene: layers' shapes taken from it, and worked out. */
  int reused = 0, made = 0;
};

struct VectorSceneOptions {
  /* The picture's size in pixels (0: the document's). */
  int width = 0, height = 0;
  /* No background: clear where nothing is drawn. */
  bool transparent = false;
  /* Hidden layers and guides too, each in a group saying so (a PDF's layers switched off), as they would draw shown. */
  bool hidden_layers = false;
  /* Guides too (layers the viewport shows but renders leave out, as a reference picture often is), drawn as shown. */
  bool guides = false;
  /* Brushed lines' pictures at this many pixels a pixel. */
  float picture_scale = 2.0f;
  /* Layers drawn as in the last scene made with it taken from it (null: everything worked out). */
  VectorSceneCache *cache = nullptr;
};

/* The document's current frame. */
VectorScene vector_scene(const Document &doc, const VectorSceneOptions &options);

/* A number as the files write it: two decimals at most, no trailing zeros. */
std::string vector_number(float v);
/* The same, added to `out`. */
void vector_number_append(std::string &out, float v);

}  // namespace oanim
