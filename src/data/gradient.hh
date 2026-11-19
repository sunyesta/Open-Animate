#pragma once

/* Gradient layers: a vector layer whose one open curve is a path of colour stops. Its points are the stops (dragged,
 * keyed, bent by bones as any drawing's points; their handles bend the path), never added or taken away but through
 * the Gradient tab. The colours run along the path and fill the whole camera frame (masks and Clip to Below trim
 * them). Ticks on the path, one between each two stops, slide where the colours meet half way.
 *
 * Where a place is along the path is a smooth field, not the nearest point on it (which jumps from one side of a bend
 * to the other and creases the bands there): an average of how far along every place on the path is, each counted by
 * one over its distance cubed, the path carried on straight past its ends (diffusion curves spread a curve's colours
 * so). By a straight path it is a classic linear gradient. Colours mix in OKLab (Perceptual) or plain RGB, premultiplied
 * so a stop fading to clear never greys; Smooth spans run a monotone curve through the stops with no jump in how fast
 * the colour changes, which the eye would see as a line (Mach bands). */

#include <array>
#include <cstdint>
#include <vector>

#include "core/math.hh"

namespace oanim {

struct Layer;
struct VectorDrawing;

/* Linear: bands across the path. Radial: rings round the first stop, squashed across the path by `squash`. */
enum class GradientType : uint8_t { Linear, Radial };
/* Past the last stop: its colour carries on, the stops repeat, or they run back and forth. */
enum class GradientEnds : uint8_t { Extend, Repeat, Reflect };
/* Perceptual: mixed in OKLab (as CSS gradients are), even in lightness; RGB: plain sRGB values. */
enum class GradientMix : uint8_t { Perceptual, RGB };
/* How a span goes from one stop's colour to the next: smoothly through the stops, evenly, or at once at its tick. */
enum class GradientFalloff : uint8_t { Smooth, Linear, Hard };

struct GradientStop {
  /* The drawing point it is (MeshPoint::id). */
  uint64_t point = 0;
  Color color = {0.0f, 0.0f, 0.0f, 1.0f};
  /* The span from this stop to the next (the last stop's unused): where along it, by length, the colours meet half
   * way (its tick), and how they go. */
  float midpoint = 0.5f;
  GradientFalloff falloff = GradientFalloff::Smooth;
  bool operator==(const GradientStop &) const = default;
};

struct GradientSettings {
  /* A gradient layer (a vector layer made one by layer.new_gradient). */
  bool on = false;
  GradientType type = GradientType::Linear;
  GradientEnds ends = GradientEnds::Extend;
  GradientMix mix = GradientMix::Perceptual;
  /* Radial: how far the rings reach across the path, as a share of along it. */
  float squash = 1.0f;
  /* In path order, one per curve point. */
  std::vector<GradientStop> stops;
  /* The stop and span picked in the Gradient tab (changing them is no undo step). */
  int active_stop = 0;
  int active_span = 0;
  bool operator==(const GradientSettings &) const = default;
};

const char *gradient_type_identifier(GradientType type);
const char *gradient_ends_identifier(GradientEnds ends);
const char *gradient_mix_identifier(GradientMix mix);
const char *gradient_falloff_identifier(GradientFalloff falloff);
bool gradient_type_from_identifier(const char *id, GradientType *r);
bool gradient_ends_from_identifier(const char *id, GradientEnds *r);
bool gradient_mix_from_identifier(const char *id, GradientMix *r);
bool gradient_falloff_from_identifier(const char *id, GradientFalloff *r);

/* Makes `layer` (a vector layer, its drawing replaced) a gradient from `a` to `b` (layer space), a straight path with
 * its handles a third along, coloured `from` to `to`. */
void gradient_layer_init(Layer &layer, float2 a, float2 b, Color from, Color to);
/* A gradient's drawing is one open curve of its stops' points in order, no shapes and no other points. */
bool gradient_layer_valid(const Layer &layer);
/* Made valid again with no earlier state to go back to: the first curve kept (and only its points), the stops
 * following its points (new ones coloured as the path showed there, or as their neighbour), at least two. */
void gradient_layer_repair(Layer &layer);

/* What a gradient is worked out from: its path (layer space) and colours. */
struct GradientField {
  bool valid = false;
  GradientType type = GradientType::Linear;
  GradientEnds ends = GradientEnds::Extend;
  float squash = 1.0f;
  /* The path as a line of samples, how far along each is, and where each stop is along it. */
  std::vector<float2> path;
  std::vector<float> arc;
  std::vector<float> stop_arc;
  /* Each sample's span and its Bezier t there. */
  std::vector<int> span_of;
  std::vector<float> t_of;
  float total = 0.0f;
  float2 start, start_dir;
  /* The field's sources: straight pieces of line, the path's chords and its carry-ons past both ends. Each starts at
   * (px, py) going (ex, ey) for len (infinite for a carry-on), and is `along` along at its start, `way` (1 or -1)
   * more each unit on. */
  std::vector<float> px, py, ex, ey, len, along, way;
  float soft = 0.0f;
  /* Colours along the path, premultiplied, sRGB: LUT_SIZE + 1 entries over [0, total]. */
  std::vector<std::array<float, 4>> lut;
};

inline constexpr int GRADIENT_LUT_SIZE = 2048;

/* `drawing`: the layer's drawing as shown (bones and modifiers worked out), in layer space. */
GradientField gradient_field(const VectorDrawing &drawing, const GradientSettings &settings);
/* How far along the path `p` (layer space) is. */
float gradient_along(const GradientField &field, float2 p);
/* The colour that far along, premultiplied. */
std::array<float, 4> gradient_color_along(const GradientField &field, float along);
/* The colour at `p`, straight (not premultiplied). */
Color gradient_color_at(const GradientField &field, float2 p);
/* The place `arc` along the path, and the fraction of span `span` (by length) nearest `p`. */
float2 gradient_place_along(const GradientField &field, float arc);
float gradient_span_fraction_nearest(const GradientField &field, int span, float2 p);
/* The picture over the parallelogram `corners` (layer space: bottom left, bottom right, top right, top left), `width`
 * by `height` pixels, rows from the top, premultiplied RGBA, dithered (so a slow gradient shows no steps). */
void gradient_image(const GradientField &field, const float2 corners[4], int width, int height,
                    std::vector<uint8_t> &r_rgba);

/* Adds a stop where span `span`'s tick is, the path keeping its shape and the colour there as it showed; its index. */
int gradient_stop_add(Layer &layer, int span);
/* Takes stop `stop` away (at least two stay), the spans either side made one. */
bool gradient_stop_remove(Layer &layer, int stop);

}  // namespace oanim
