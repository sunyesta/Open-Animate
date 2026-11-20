#include "data/gradient.hh"

#include <algorithm>
#include <cmath>
#include <limits>
#include <cstring>

#include "core/parallel.hh"
#include "data/layer.hh"
#include "data/vector.hh"

namespace oanim {

const char *gradient_type_identifier(GradientType type)
{
  return type == GradientType::Radial ? "RADIAL" : "LINEAR";
}
const char *gradient_ends_identifier(GradientEnds ends)
{
  return ends == GradientEnds::Repeat ? "REPEAT" : ends == GradientEnds::Reflect ? "REFLECT" : "EXTEND";
}
const char *gradient_mix_identifier(GradientMix mix)
{
  return mix == GradientMix::RGB ? "RGB" : "PERCEPTUAL";
}
const char *gradient_falloff_identifier(GradientFalloff falloff)
{
  return falloff == GradientFalloff::Linear ? "LINEAR" : falloff == GradientFalloff::Hard ? "HARD" : "SMOOTH";
}

template<typename E> static bool from_identifier(const char *id, E *r, const char *(*name)(E), int count)
{
  for (int i = 0; i < count; i++) {
    if (std::strcmp(id, name(E(i))) == 0) {
      *r = E(i);
      return true;
    }
  }
  return false;
}
bool gradient_type_from_identifier(const char *id, GradientType *r)
{
  return from_identifier(id, r, gradient_type_identifier, 2);
}
bool gradient_ends_from_identifier(const char *id, GradientEnds *r)
{
  return from_identifier(id, r, gradient_ends_identifier, 3);
}
bool gradient_mix_from_identifier(const char *id, GradientMix *r)
{
  return from_identifier(id, r, gradient_mix_identifier, 2);
}
bool gradient_falloff_from_identifier(const char *id, GradientFalloff *r)
{
  return from_identifier(id, r, gradient_falloff_identifier, 3);
}

/* --- The layer's drawing ---------------------------------------------------------------------------------------- */

void gradient_layer_init(Layer &layer, float2 a, float2 b, Color from, Color to)
{
  VectorDrawing drawing;
  Curve curve;
  curve.closed = false;
  const float2 third = (b - a) * (1.0f / 3.0f);
  for (int i = 0; i < 2; i++) {
    MeshPoint p;
    p.pos = p.setup_pos = i == 0 ? a : b;
    p.id = drawing.next_id++;
    drawing.points.push_back(p);
    CurvePoint cp;
    cp.point = i;
    cp.handles_set = true;
    /* A straight path, its handles a third along it, ready to be pulled. */
    cp.handle_in = cp.setup_in = i == 0 ? float2(0.0f, 0.0f) - third : float2(0.0f, 0.0f) - third;
    cp.handle_out = cp.setup_out = third;
    cp.aligned = true;
    curve.points.push_back(cp);
  }
  drawing.curves.push_back(std::move(curve));
  layer.drawing = std::move(drawing);
  layer.gradient = GradientSettings();
  layer.gradient.on = true;
  layer.gradient.stops = {{layer.drawing.points[0].id, from}, {layer.drawing.points[1].id, to}};
}

bool gradient_layer_valid(const Layer &layer)
{
  const GradientSettings &g = layer.gradient;
  if (!g.on) {
    return true;
  }
  const VectorDrawing &d = layer.drawing;
  if (d.curves.size() != 1 || d.curves[0].closed || !d.shapes.empty()) {
    return false;
  }
  const Curve &c = d.curves[0];
  if (c.points.size() < 2 || c.points.size() != g.stops.size() || d.points.size() != g.stops.size()) {
    return false;
  }
  for (size_t i = 0; i < c.points.size(); i++) {
    const int p = c.points[i].point;
    if (p < 0 || p >= int(d.points.size()) || d.points[size_t(p)].id != g.stops[i].point) {
      return false;
    }
  }
  return true;
}

void gradient_layer_repair(Layer &layer)
{
  if (gradient_layer_valid(layer)) {
    return;
  }
  GradientSettings &g = layer.gradient;
  VectorDrawing &d = layer.drawing;
  drawing_ensure_ids(d);
  int keep = -1;
  for (int c = 0; c < int(d.curves.size()); c++) {
    if (d.curves[size_t(c)].points.size() >= 2) {
      keep = c;
      break;
    }
  }
  const Color first = g.stops.empty() ? Color{0, 0, 0, 1} : g.stops.front().color;
  const Color last = g.stops.empty() ? Color{1, 1, 1, 1} : g.stops.back().color;
  if (keep < 0) {
    const GradientSettings was = g;
    gradient_layer_init(layer, {-1.0f, 0.0f}, {1.0f, 0.0f}, first, last);
    layer.gradient.type = was.type;
    layer.gradient.ends = was.ends;
    layer.gradient.mix = was.mix;
    layer.gradient.squash = was.squash;
    return;
  }
  d.shapes.clear();
  std::vector<bool> remove(d.curves.size(), true);
  remove[size_t(keep)] = false;
  drawing_remove_curves(d, remove);
  d.curves[0].closed = false;
  drawing_remove_unused_points(d);
  drawing_groups_prune(d);
  std::vector<GradientStop> stops;
  for (const CurvePoint &cp : d.curves[0].points) {
    const uint64_t id = d.points[size_t(cp.point)].id;
    const auto had = std::find_if(g.stops.begin(), g.stops.end(), [&](const GradientStop &s) { return s.point == id; });
    if (had != g.stops.end()) {
      stops.push_back(*had);
    }
    else {
      GradientStop s;
      s.point = id;
      s.color = stops.empty() ? first : stops.back().color;
      stops.push_back(s);
    }
  }
  g.stops = std::move(stops);
  g.active_stop = std::clamp(g.active_stop, 0, int(g.stops.size()) - 1);
  g.active_span = std::clamp(g.active_span, 0, int(g.stops.size()) - 2);
}

/* --- Colours --------------------------------------------------------------------------------------------------- */

static float to_linear(float c)
{
  return c <= 0.04045f ? c / 12.92f : std::pow((c + 0.055f) / 1.055f, 2.4f);
}
static float to_gamma(float c)
{
  return c <= 0.0031308f ? 12.92f * c : 1.055f * std::pow(std::max(c, 0.0f), 1.0f / 2.4f) - 0.055f;
}
static std::array<float, 3> oklab_from_srgb(float r, float g, float b)
{
  r = to_linear(r);
  g = to_linear(g);
  b = to_linear(b);
  const float l = std::cbrt(0.4122214708f * r + 0.5363325363f * g + 0.0514459929f * b);
  const float m = std::cbrt(0.2119034982f * r + 0.6806995451f * g + 0.1073969566f * b);
  const float s = std::cbrt(0.0883024619f * r + 0.2817188376f * g + 0.6299787005f * b);
  return {0.2104542553f * l + 0.7936177850f * m - 0.0040720468f * s,
          1.9779984951f * l - 2.4285922050f * m + 0.4505937099f * s,
          0.0259040371f * l + 0.7827717662f * m - 0.8086757660f * s};
}
static std::array<float, 3> srgb_from_oklab(float L, float A, float B)
{
  const float l = L + 0.3963377774f * A + 0.2158037573f * B;
  const float m = L - 0.1055613458f * A - 0.0638541728f * B;
  const float s = L - 0.0894841775f * A - 1.2914855480f * B;
  const float l3 = l * l * l, m3 = m * m * m, s3 = s * s * s;
  return {to_gamma(4.0767416621f * l3 - 3.3077115913f * m3 + 0.2309699292f * s3),
          to_gamma(-1.2684380046f * l3 + 2.6097574011f * m3 - 0.3413193965f * s3),
          to_gamma(-0.0041960863f * l3 - 0.7034186147f * m3 + 1.7076147010f * s3)};
}

using Channels = std::array<float, 4>;

/* The colour `a` along the path (not folded), premultiplied sRGB: from the stops in the working space (`values`,
 * premultiplied) and how fast each channel changes as it passes each stop (`slopes`). */
static Channels color_unfolded(const GradientField &f, const GradientSettings &g, const std::vector<Channels> &values,
                               const std::vector<Channels> &slopes, float a)
{
  const int spans = int(values.size()) - 1;
  int k = 0;
  while (k < spans - 1 && a > f.stop_arc[size_t(k) + 1]) {
    k++;
  }
  const float s0 = f.stop_arc[size_t(k)];
  const float h = std::max(f.stop_arc[size_t(k) + 1] - s0, 1e-9f);
  const float t = std::clamp((a - s0) / h, 0.0f, 1.0f);
  const GradientStop &sp = g.stops[size_t(k)];
  const float m = std::clamp(sp.midpoint, 0.02f, 0.98f);
  /* The midpoint as a smooth remap of the span (half way at the tick, no corner there): u = t / (q (1 - t) + 1). */
  const float q = (2.0f * m - 1.0f) / (1.0f - m);
  const float u = t / (q * (1.0f - t) + 1.0f);
  const Channels &A = values[size_t(k)], &B = values[size_t(k) + 1];
  Channels v{};
  if (sp.falloff == GradientFalloff::Hard) {
    v = t < m ? A : B;
  }
  else if (sp.falloff == GradientFalloff::Linear) {
    for (int i = 0; i < 4; i++) {
      v[size_t(i)] = A[size_t(i)] + (B[size_t(i)] - A[size_t(i)]) * u;
    }
  }
  else {
    /* Hermite in u, its end rates the stops' rates along the path through the remap, held under three times the
     * span's change so the remap can't push it past a stop's colour. */
    const float u2 = u * u, u3 = u2 * u;
    const float h00 = 2 * u3 - 3 * u2 + 1, h10 = u3 - 2 * u2 + u, h01 = -2 * u3 + 3 * u2, h11 = u3 - u2;
    for (size_t i = 0; i < 4; i++) {
      const float d = B[i] - A[i], lim = 3.0f * std::fabs(d);
      const auto clamp_rate = [&](float r) {
        if (d == 0.0f) {
          return 0.0f;
        }
        const float sign = d > 0.0f ? 1.0f : -1.0f;
        return sign * std::clamp(r * sign, 0.0f, lim);
      };
      const float m0 = clamp_rate(slopes[size_t(k)][i] * h * (1.0f + q));
      const float m1 = clamp_rate(slopes[size_t(k) + 1][i] * h / (1.0f + q));
      v[i] = h00 * A[i] + h10 * m0 + h01 * B[i] + h11 * m1;
    }
  }
  const float alpha = std::clamp(v[3], 0.0f, 1.0f);
  if (alpha < 1e-6f) {
    return {0, 0, 0, 0};
  }
  std::array<float, 3> c{v[0] / v[3], v[1] / v[3], v[2] / v[3]};
  if (g.mix == GradientMix::Perceptual) {
    c = srgb_from_oklab(c[0], c[1], c[2]);
  }
  return {std::clamp(c[0], 0.0f, 1.0f) * alpha, std::clamp(c[1], 0.0f, 1.0f) * alpha,
          std::clamp(c[2], 0.0f, 1.0f) * alpha, alpha};
}

static void build_lut(GradientField &f, const GradientSettings &g)
{
  const size_t n = g.stops.size();
  std::vector<Channels> values(n);
  for (size_t k = 0; k < n; k++) {
    const Color &c = g.stops[k].color;
    const float a = std::clamp(c.a, 0.0f, 1.0f);
    const std::array<float, 3> w = g.mix == GradientMix::Perceptual ? oklab_from_srgb(c.r, c.g, c.b)
                                                                     : std::array<float, 3>{c.r, c.g, c.b};
    values[k] = {w[0] * a, w[1] * a, w[2] * a, a};
  }
  /* Monotone (Fritsch-Butland): a channel never overshoots between two stops; level at the two ends, where the end
   * colours carry on. */
  std::vector<Channels> slopes(n, Channels{});
  for (size_t k = 1; k + 1 < n; k++) {
    const float h0 = std::max(f.stop_arc[k] - f.stop_arc[k - 1], 1e-9f);
    const float h1 = std::max(f.stop_arc[k + 1] - f.stop_arc[k], 1e-9f);
    for (size_t i = 0; i < 4; i++) {
      const float a = (values[k][i] - values[k - 1][i]) / h0, b = (values[k + 1][i] - values[k][i]) / h1;
      slopes[k][i] = a * b <= 0.0f ? 0.0f : 3.0f * (h0 + h1) / ((2.0f * h1 + h0) / a + (h1 + 2.0f * h0) / b);
    }
  }
  f.lut.resize(GRADIENT_LUT_SIZE + 1);
  for (int i = 0; i <= GRADIENT_LUT_SIZE; i++) {
    f.lut[size_t(i)] = color_unfolded(f, g, values, slopes, f.total * float(i) / float(GRADIENT_LUT_SIZE));
  }
}

/* --- The path and its field ------------------------------------------------------------------------------------ */

GradientField gradient_field(const VectorDrawing &drawing, const GradientSettings &settings)
{
  GradientField f;
  f.type = settings.type;
  f.ends = settings.ends;
  f.squash = std::isfinite(settings.squash) ? std::clamp(settings.squash, 0.01f, 100.0f) : 1.0f;
  if (drawing.curves.empty() || drawing.curves[0].points.size() < 2 ||
      settings.stops.size() != drawing.curves[0].points.size())
  {
    return f;
  }
  const Curve &curve = drawing.curves[0];
  constexpr int STEPS = 48;
  float total = 0.0f;
  f.stop_arc.push_back(0.0f);
  for (int s = 0; s < curve.segment_count(); s++) {
    float2 ctrl[4];
    curve_segment_bezier(drawing, curve, s, ctrl);
    for (int j = s == 0 ? 0 : 1; j <= STEPS; j++) {
      const float t = float(j) / float(STEPS);
      const float2 q = bezier_eval(ctrl, t);
      if (!f.path.empty()) {
        total += distance(q, f.path.back());
      }
      f.path.push_back(q);
      f.arc.push_back(total);
      f.span_of.push_back(s);
      f.t_of.push_back(t);
    }
    f.stop_arc.push_back(total);
  }
  /* A place no number reaches (a script's NaN, a file's 1e39) leaves no path: nothing shows. */
  if (!std::isfinite(total)) {
    GradientField none;
    none.type = f.type;
    none.ends = f.ends;
    none.squash = f.squash;
    return none;
  }
  f.total = std::max(total, 1e-6f);
  f.start = f.path.front();
  /* From an end into the path: the first step that goes anywhere, so a handle of no length still points the way the
   * path leaves. */
  const auto inward = [&](bool from_start) {
    const size_t n = f.path.size();
    const float2 end = from_start ? f.path.front() : f.path.back();
    for (size_t k = 1; k < n; k++) {
      const float2 d = f.path[from_start ? k : n - 1 - k] - end;
      if (length(d) > 1e-7f) {
        return normalize(d);
      }
    }
    return float2(from_start ? 1.0f : -1.0f, 0.0f);
  };
  f.start_dir = inward(true);
  const float2 end_dir = inward(false) * -1.0f;

  /* The field's sources: the path in even steps, each worth its length; and the path carried on straight past both
   * ends, the steps growing as they matter less far out, each place knowing how far along it is (before the start,
   * less than none). */
  /* Sources: the path's chords, and the path carried on straight past both ends, each place on them knowing how far
   * along it is (before the start, less than none). The field adds each piece up exactly (gradient_along), so
   * nothing about it steps from one sample to the next. */
  const auto piece = [&](float2 from, float2 dir, float length, float at, float way) {
    f.px.push_back(from.x);
    f.py.push_back(from.y);
    f.ex.push_back(dir.x);
    f.ey.push_back(dir.y);
    f.len.push_back(length);
    f.along.push_back(at);
    f.way.push_back(way);
  };
  for (size_t j = 0; j + 1 < f.path.size(); j++) {
    const float l = f.arc[j + 1] - f.arc[j];
    if (l > 0.0f) {
      piece(f.path[j], (f.path[j + 1] - f.path[j]) * (1.0f / l), l, f.arc[j], 1.0f);
    }
  }
  const float inf = std::numeric_limits<float>::infinity();
  piece(f.path.front(), f.start_dir * -1.0f, inf, 0.0f, -1.0f);
  piece(f.path.back(), end_dir, inf, f.total, 1.0f);
  /* Right on the path its weight has no end: a place there takes the path's own along, softened over a 256th of
   * it so it isn't a point sharp. */
  const float step = f.total / 256.0f;
  f.soft = step * step;
  build_lut(f, settings);
  f.valid = true;
  return f;
}

float gradient_along(const GradientField &f, float2 p)
{
  if (!f.valid) {
    return 0.0f;
  }
  if (f.type == GradientType::Radial) {
    const float2 d = p - f.start;
    const float u = dot(d, f.start_dir), v = cross(f.start_dir, d);
    return std::hypot(u, v / f.squash);
  }
  /* How far along the path places are, averaged with weight 1 / distance^3 over every piece of line: what the even
   * sampling of the line tends to, worked out exactly. Along a piece from its foot by c, with v the distance from it
   * (softened), the weight sums to W = [c / (v^2 D)] and its first moment to M = [-1 / D], D = sqrt(c^2 + v^2),
   * taken between the piece's ends; written with R(c) = 1 / (D (D + |c|)) where both ends are on one side, as the two
   * near-equal halves cancel there. */
  double num = 0.0, den = 0.0;
  const size_t n = f.px.size();
  for (size_t j = 0; j < n; j++) {
    const double dx = double(p.x) - f.px[j], dy = double(p.y) - f.py[j];
    const double u = dx * f.ex[j] + dy * f.ey[j];
    const double v2 = std::max(dx * dx + dy * dy - u * u, 0.0) + double(f.soft);
    const bool open = std::isinf(f.len[j]);
    const double c0 = -u, c1 = open ? 0.0 : double(f.len[j]) - u;
    const double d0 = std::sqrt(c0 * c0 + v2), d1 = std::sqrt(c1 * c1 + v2);
    const double r0 = 1.0 / (d0 * (d0 + std::abs(c0)));
    const double r1 = open ? 0.0 : 1.0 / (d1 * (d1 + std::abs(c1)));
    double w;
    if (open) {
      w = c0 >= 0.0 ? r0 : 2.0 / v2 - r0;
    }
    else if (c0 >= 0.0) {
      w = r0 - r1;
    }
    else if (c1 <= 0.0) {
      w = r1 - r0;
    }
    else {
      w = 2.0 / v2 - r0 - r1;
    }
    const double m = 1.0 / d0 - (open ? 0.0 : 1.0 / d1);
    num += (double(f.along[j]) + double(f.way[j]) * u) * w + double(f.way[j]) * m;
    den += w;
  }
  return den > 0.0 ? float(num / den) : 0.0f;
}

std::array<float, 4> gradient_color_along(const GradientField &f, float a)
{
  if (!f.valid || f.lut.empty()) {
    return {0, 0, 0, 0};
  }
  const float L = f.total;
  if (f.ends == GradientEnds::Repeat) {
    a = std::fmod(a, L);
    a = a < 0.0f ? a + L : a;
  }
  else if (f.ends == GradientEnds::Reflect) {
    float m = std::fmod(a, 2.0f * L);
    m = m < 0.0f ? m + 2.0f * L : m;
    a = m <= L ? m : 2.0f * L - m;
  }
  /* NaN (a place no number reaches) takes the start, never an index past the table. */
  const float x = std::isnan(a) ? 0.0f : std::clamp(a / L, 0.0f, 1.0f) * float(GRADIENT_LUT_SIZE);
  const int i = std::min(int(x), GRADIENT_LUT_SIZE - 1);
  const float t = x - float(i);
  const Channels &c0 = f.lut[size_t(i)], &c1 = f.lut[size_t(i) + 1];
  return {c0[0] + (c1[0] - c0[0]) * t, c0[1] + (c1[1] - c0[1]) * t, c0[2] + (c1[2] - c0[2]) * t,
          c0[3] + (c1[3] - c0[3]) * t};
}

Color gradient_color_at(const GradientField &f, float2 p)
{
  const Channels c = gradient_color_along(f, gradient_along(f, p));
  if (c[3] < 1e-6f) {
    return {0, 0, 0, 0};
  }
  return {c[0] / c[3], c[1] / c[3], c[2] / c[3], c[3]};
}

float2 gradient_place_along(const GradientField &f, float a)
{
  if (f.path.empty()) {
    return {0.0f, 0.0f};
  }
  const auto it = std::lower_bound(f.arc.begin(), f.arc.end(), a);
  if (it == f.arc.begin()) {
    return f.path.front();
  }
  if (it == f.arc.end()) {
    return f.path.back();
  }
  const size_t j = size_t(it - f.arc.begin());
  const float len = f.arc[j] - f.arc[j - 1];
  const float t = len > 0.0f ? (a - f.arc[j - 1]) / len : 0.0f;
  return f.path[j - 1] + (f.path[j] - f.path[j - 1]) * t;
}

float gradient_span_fraction_nearest(const GradientField &f, int span, float2 p)
{
  if (span < 0 || span + 1 >= int(f.stop_arc.size())) {
    return 0.5f;
  }
  const float a0 = f.stop_arc[size_t(span)], a1 = f.stop_arc[size_t(span) + 1];
  float best = 1e30f, at = 0.5f * (a0 + a1);
  for (size_t j = 0; j + 1 < f.path.size(); j++) {
    if (f.arc[j + 1] < a0 - 1e-7f || f.arc[j] > a1 + 1e-7f) {
      continue;
    }
    float t = 0.0f;
    const float d = distance_to_segment(p, f.path[j], f.path[j + 1], &t);
    if (d < best) {
      best = d;
      at = f.arc[j] + (f.arc[j + 1] - f.arc[j]) * t;
    }
  }
  return std::clamp((at - a0) / std::max(a1 - a0, 1e-9f), 0.02f, 0.98f);
}

/* Triangular noise in -1..1 from a pixel's place: the same picture every time it is made. */
static float dither(int x, int y)
{
  uint32_t h = uint32_t(x) * 0x8da6b343u ^ uint32_t(y) * 0xd8163841u;
  h ^= h >> 13;
  h *= 0x5bd1e995u;
  h ^= h >> 15;
  const float a = float(h & 0xffffu) / 65535.0f, b = float(h >> 16) / 65535.0f;
  return a - b;
}

void gradient_image(const GradientField &f, const float2 corners[4], int width, int height, std::vector<uint8_t> &r_rgba)
{
  r_rgba.assign(size_t(std::max(width, 0)) * size_t(std::max(height, 0)) * 4, 0);
  if (width <= 0 || height <= 0 || !f.valid) {
    return;
  }
  const float2 o = corners[0], ex = corners[1] - corners[0], ey = corners[3] - corners[0];
  /* Pixel (x, y) from the top left, in pixels (continuous), to layer space. */
  const auto place = [&](float x, float y) {
    return o + ex * (x / float(width)) + ey * (1.0f - y / float(height));
  };
  /* Linear: how far along, worked out on a coarse grid and read between its nodes (it changes slowly); Radial: at each
   * pixel (cheap, and its point at the middle stays sharp). */
  constexpr int CELL = 6;
  const bool grid = f.type == GradientType::Linear;
  const int gw = width / CELL + 2, gh = height / CELL + 2;
  std::vector<float> along;
  if (grid) {
    along.resize(size_t(gw) * size_t(gh));
    parallel_for(size_t(gh), 2, [&](size_t begin, size_t end) {
      for (size_t gy = begin; gy < end; gy++) {
        for (int gx = 0; gx < gw; gx++) {
          along[gy * size_t(gw) + size_t(gx)] = gradient_along(f, place(float(gx * CELL), float(gy) * float(CELL)));
        }
      }
    });
  }
  parallel_for(size_t(height), 16, [&](size_t begin, size_t end) {
   for (int y = int(begin); y < int(end); y++) {
    uint8_t *out = r_rgba.data() + size_t(y) * size_t(width) * 4;
    const float py = float(y) + 0.5f;
    const float fy = py / float(CELL);
    const int gy = std::min(int(fy), gh - 2);
    const float ty = fy - float(gy);
    for (int x = 0; x < width; x++) {
      const float px = float(x) + 0.5f;
      float a;
      if (grid) {
        const float fx = px / float(CELL);
        const int gx = std::min(int(fx), gw - 2);
        const float tx = fx - float(gx);
        const float *r0 = &along[size_t(gy) * size_t(gw) + size_t(gx)];
        const float *r1 = r0 + gw;
        a = (r0[0] * (1.0f - tx) + r0[1] * tx) * (1.0f - ty) + (r1[0] * (1.0f - tx) + r1[1] * tx) * ty;
      }
      else {
        a = gradient_along(f, place(px, py));
      }
      const Channels c = gradient_color_along(f, a);
      const float n = dither(x, y);
      const int alpha = std::clamp(int(std::lround(c[3] * 255.0f + n)), 0, 255);
      for (int i = 0; i < 3; i++) {
        out[i] = uint8_t(std::clamp(int(std::lround(c[size_t(i)] * 255.0f + n)), 0, alpha));
      }
      out[3] = uint8_t(alpha);
      out += 4;
    }
   }
  });
}

/* --- Stops ------------------------------------------------------------------------------------------------------ */

int gradient_stop_add(Layer &layer, int span)
{
  GradientSettings &g = layer.gradient;
  if (!g.on || !gradient_layer_valid(layer) || span < 0 || span + 1 >= int(g.stops.size())) {
    return -1;
  }
  const GradientField f = gradient_field(layer.drawing, g);
  if (!f.valid) {
    return -1;
  }
  const float m = std::clamp(g.stops[size_t(span)].midpoint, 0.02f, 0.98f);
  const float target = f.stop_arc[size_t(span)] + (f.stop_arc[size_t(span) + 1] - f.stop_arc[size_t(span)]) * m;
  /* The Bezier t there. */
  float t = m;
  for (size_t j = 0; j + 1 < f.path.size(); j++) {
    if (f.span_of[j + 1] == span && f.arc[j + 1] >= target) {
      const float t0 = f.span_of[j] == span ? f.t_of[j] : 0.0f, t1 = f.t_of[j + 1];
      const float len = f.arc[j + 1] - f.arc[j];
      t = t0 + (t1 - t0) * (len > 0.0f ? (target - f.arc[j]) / len : 0.0f);
      break;
    }
  }
  /* Its colour as the path showed it there (the field is the path's own on the path). */
  const Channels shown = gradient_color_along(f, target);
  Color color{0.0f, 0.0f, 0.0f, 0.0f};
  if (shown[3] > 1e-6f) {
    color = {shown[0] / shown[3], shown[1] / shown[3], shown[2] / shown[3], shown[3]};
  }
  const int point = drawing_split_segment(layer.drawing, {0, span}, std::clamp(t, 0.001f, 0.999f));
  drawing_ensure_ids(layer.drawing);
  GradientStop stop;
  stop.point = layer.drawing.points[size_t(point)].id;
  stop.color = color;
  stop.falloff = g.stops[size_t(span)].falloff;
  g.stops[size_t(span)].midpoint = 0.5f;
  g.stops.insert(g.stops.begin() + span + 1, stop);
  g.active_stop = span + 1;
  g.active_span = std::min(span + 1, int(g.stops.size()) - 2);
  return span + 1;
}

bool gradient_stop_remove(Layer &layer, int stop)
{
  GradientSettings &g = layer.gradient;
  if (!g.on || !gradient_layer_valid(layer) || g.stops.size() <= 2 || stop < 0 || stop >= int(g.stops.size())) {
    return false;
  }
  const int point = drawing_point_index(layer.drawing, g.stops[size_t(stop)].point);
  if (point < 0) {
    return false;
  }
  drawing_dissolve_points(layer.drawing, {point});
  if (stop > 0 && stop + 1 < int(g.stops.size())) {
    /* The two spans either side are one now. */
    g.stops[size_t(stop) - 1].midpoint = 0.5f;
  }
  g.stops.erase(g.stops.begin() + stop);
  g.active_stop = std::clamp(stop, 0, int(g.stops.size()) - 1);
  g.active_span = std::clamp(std::min(stop, int(g.stops.size()) - 2), 0, int(g.stops.size()) - 2);
  if (!gradient_layer_valid(layer)) {
    gradient_layer_repair(layer);
  }
  return true;
}

}  // namespace oanim
