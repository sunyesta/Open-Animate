#include "anim/shape_tree.hh"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <limits>
#include <map>
#include <unordered_map>

#pragma warning(push, 0)
#include <clipper2/clipper.h>
#pragma warning(pop)

#include "core/profile.hh"
#include "data/document.hh"
#include "data/vector.hh"

namespace oanim {

namespace c2 = Clipper2Lib;

namespace {

/* Clipper works in fixed point: 5 decimals of a unit (the frame is 2 tall) is far finer than anything drawn. Samples
 * are put on that grid before they go in, so the ones the result keeps come out as they went in and are found again. */
constexpr int PRECISION = 5;
constexpr double GRID = 1e5;
/* Samples along each segment. */
constexpr int STEPS = 16;

using Bezier = std::array<float2, 4>;

/* One closed run of a shape's outline, its edges as they run, and the samples that went in for it. */
struct Loop {
  int shape = -1;
  std::vector<OrientedEdge> chain;
  std::vector<Bezier> beziers;
  /* Sample g (edge g / STEPS, step g % STEPS), on the grid. */
  std::vector<c2::PointD> samples;
  int size() const { return int(samples.size()); }
};

struct Tag {
  int loop = -1;
  int g = 0;
};

int64_t grid(double v)
{
  return int64_t(std::llround(v * GRID));
}

uint64_t grid_key(const c2::PointD &p)
{
  const uint64_t x = uint64_t(grid(p.x)), y = uint64_t(grid(p.y));
  uint64_t h = x * 0x9e3779b97f4a7c15ull;
  h ^= y + 0x632be59bd9b4e019ull + (h << 6) + (h >> 2);
  return h;
}

bool same_place(const c2::PointD &a, const c2::PointD &b)
{
  return grid(a.x) == grid(b.x) && grid(a.y) == grid(b.y);
}

float2 to_f2(const c2::PointD &p)
{
  return float2(float(p.x), float(p.y));
}

/* A cubic's derivative. */
float2 bezier_tangent(const Bezier &c, float t)
{
  const float s = 1.0f - t;
  return (c[1] - c[0]) * (3.0f * s * s) + (c[2] - c[1]) * (6.0f * s * t) + (c[3] - c[2]) * (3.0f * t * t);
}

float2 bezier_at(const Bezier &c, float t)
{
  return bezier_eval(c.data(), t);
}

/* The piece of a cubic from t = a to t = b (b < a: run backwards), exactly: its ends' tangents scaled to the piece. */
Bezier bezier_piece(const Bezier &c, float a, float b)
{
  const float2 pa = bezier_at(c, a), pb = bezier_at(c, b);
  const float k = (b - a) / 3.0f;
  return {pa, pa + bezier_tangent(c, a) * k, pb - bezier_tangent(c, b) * k, pb};
}

/* The place along a cubic nearest `p`, starting from t0 and staying within [lo, hi] (Newton steps). */
float bezier_nearest(const Bezier &c, float2 p, float t0, float lo, float hi)
{
  float t = std::clamp(t0, lo, hi);
  for (int i = 0; i < 8; i++) {
    const float2 d = bezier_at(c, t) - p;
    const float2 d1 = bezier_tangent(c, t);
    /* The second derivative. */
    const float s = 1.0f - t;
    const float2 d2 = (c[2] - c[1] * 2.0f + c[0]) * (6.0f * s) + (c[3] - c[2] * 2.0f + c[1]) * (6.0f * t);
    const float den = dot(d1, d1) + dot(d, d2);
    if (std::fabs(den) < 1e-20f) {
      break;
    }
    const float next = std::clamp(t - dot(d, d1) / den, lo, hi);
    if (std::fabs(next - t) < 1e-7f) {
      t = next;
      break;
    }
    t = next;
  }
  return t;
}

/* Where two cubics cross near ta, tb (Newton steps on A(ta) = B(tb)); false when it doesn't settle near them. */
bool bezier_cross(const Bezier &a, const Bezier &b, float *ta, float *tb)
{
  float s = *ta, t = *tb;
  for (int i = 0; i < 10; i++) {
    const float2 f = bezier_at(a, s) - bezier_at(b, t);
    const float2 ja = bezier_tangent(a, s), jb = bezier_tangent(b, t) * -1.0f;
    const float det = ja.x * jb.y - ja.y * jb.x;
    if (std::fabs(det) < 1e-20f) {
      return false;
    }
    const float ds = (f.x * jb.y - f.y * jb.x) / det, dt = (ja.x * f.y - ja.y * f.x) / det;
    s -= ds;
    t -= dt;
    if (std::fabs(ds) < 1e-7f && std::fabs(dt) < 1e-7f) {
      break;
    }
  }
  const float slack = 1.5f / float(STEPS);
  if (!(std::fabs(s - *ta) <= slack && std::fabs(t - *tb) <= slack) || s < 0.0f || s > 1.0f || t < 0.0f || t > 1.0f) {
    return false;
  }
  *ta = s;
  *tb = t;
  return true;
}

double distance_to_chord(const c2::PointD &p, const c2::PointD &a, const c2::PointD &b, double *r_along)
{
  const double dx = b.x - a.x, dy = b.y - a.y;
  const double len2 = dx * dx + dy * dy;
  double t = len2 > 0.0 ? ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2 : 0.0;
  t = std::clamp(t, 0.0, 1.0);
  if (r_along) {
    *r_along = t;
  }
  const double qx = a.x + dx * t - p.x, qy = a.y + dy * t - p.y;
  return std::sqrt(qx * qx + qy * qy);
}

/* What one solve reads: the loops of every shape in the tree, and where each of their samples is. */
struct Solve {
  const VectorDrawing *drawing = nullptr;
  std::vector<Loop> loops;
  std::unordered_map<uint64_t, Tag> tags;

  Tag tag_of(const c2::PointD &p) const
  {
    auto it = tags.find(grid_key(p));
    if (it == tags.end() || !same_place(loops[it->second.loop].samples[it->second.g], p)) {
      return {};
    }
    return it->second;
  }
};

/* A shape's own region (its loops filled by its fill rule), every sample tagged. */
c2::PathsD own_region(Solve &S, int s)
{
  const VectorDrawing &d = *S.drawing;
  const Shape &shape = d.shapes[s];
  c2::PathsD paths;
  std::vector<OrientedEdge> chain;
  for (const Shape &run : shape_runs(d, shape)) {
    bool closed = false;
    if (!shape_chain(d, run, chain, &closed) || !closed || chain.empty()) {
      continue;
    }
    Loop loop;
    loop.shape = s;
    loop.chain = chain;
    for (const OrientedEdge &oe : chain) {
      Bezier c;
      curve_segment_bezier(d, d.curves[oe.edge.curve], oe.edge.segment, c.data());
      if (oe.reversed) {
        std::swap(c[0], c[3]);
        std::swap(c[1], c[2]);
      }
      loop.beziers.push_back(c);
      for (int j = 0; j < STEPS; j++) {
        const float2 p = bezier_sample(c.data(), j, STEPS);
        loop.samples.push_back({double(grid(p.x)) / GRID, double(grid(p.y)) / GRID});
      }
    }
    const int index = int(S.loops.size());
    c2::PathD path;
    for (int g = 0; g < loop.size(); g++) {
      /* The first sample of a place wins: a point two loops share is the lower one's. */
      S.tags.emplace(grid_key(loop.samples[g]), Tag{index, g});
      if (path.empty() || !same_place(path.back(), loop.samples[g])) {
        path.push_back(loop.samples[g]);
      }
    }
    while (path.size() > 1 && same_place(path.front(), path.back())) {
      path.pop_back();
    }
    S.loops.push_back(std::move(loop));
    if (path.size() < 3) {
      continue;
    }
    /* Each loop filled on its own (Loops) or a loop inside another a hole (Even-Odd): the same way round, so they add.
     * Nonzero keeps the way each was drawn. */
    if (shape.fill_rule != FillRule::NonZero && c2::Area(path) < 0.0) {
      std::reverse(path.begin(), path.end());
    }
    paths.push_back(std::move(path));
  }
  return c2::Union(paths, shape.fill_rule == FillRule::EvenOdd ? c2::FillRule::EvenOdd : c2::FillRule::NonZero,
                   PRECISION);
}

double perimeter(const c2::PathsD &paths)
{
  double total = 0.0;
  for (const c2::PathD &p : paths) {
    for (size_t i = 0; i < p.size(); i++) {
      const c2::PointD &a = p[i], &b = p[(i + 1) % p.size()];
      total += std::hypot(b.x - a.x, b.y - a.y);
    }
  }
  return total;
}

float2 unit(const c2::PointD &from, const c2::PointD &to)
{
  const float2 d(float(to.x - from.x), float(to.y - from.y));
  const float len = length(d);
  return len > 1e-12f ? d / len : float2(0.0f, 0.0f);
}

/* The place `along` from ring vertex i, walking the ring (forward or back): the point, and the index of the ring
 * vertex it is past (the edge it is on starts there). */
c2::PointD ring_walk(const c2::PathD &ring, int i, int dir, double along, int *r_edge, float2 *r_dir)
{
  const int n = int(ring.size());
  int at = i;
  for (int step = 0; step < n; step++) {
    const int next = ((at + dir) % n + n) % n;
    const c2::PointD &p = ring[size_t(at)], &q = ring[size_t(next)];
    const double len = std::hypot(q.x - p.x, q.y - p.y);
    if (len >= along || step == n - 1) {
      const double f = len > 0.0 ? std::min(along / len, 1.0) : 0.0;
      *r_edge = dir > 0 ? at : next;
      *r_dir = unit(ring[size_t(dir > 0 ? at : next)], ring[size_t(dir > 0 ? next : at)]);
      return {p.x + (q.x - p.x) * f, p.y + (q.y - p.y) * f};
    }
    along -= len;
    at = next;
  }
  *r_edge = i;
  *r_dir = float2(0.0f, 0.0f);
  return ring[size_t(i)];
}

/* The way the ring runs at `at`, on its edge from vertex e: the drawing's curve's own direction there where the edge
 * runs between two samples next to each other on a loop, else the edge's. */
float2 ring_tangent(const Solve &S, const c2::PathD &ring, int e, const c2::PointD &at)
{
  const int n = int(ring.size());
  const c2::PointD &p = ring[size_t(e)], &q = ring[size_t((e + 1) % n)];
  const Tag ta = S.tag_of(p), tb = S.tag_of(q);
  if (ta.loop >= 0 && ta.loop == tb.loop) {
    const Loop &loop = S.loops[size_t(ta.loop)];
    const int m = loop.size();
    const int forward = ((tb.g - ta.g) % m + m) % m;
    if (forward == 1 || forward == m - 1) {
      const int g0 = forward == 1 ? ta.g : tb.g;
      const c2::PointD &s0 = loop.samples[size_t(g0)], &s1 = loop.samples[size_t((g0 + 1) % m)];
      double f = 0.0;
      distance_to_chord(at, s0, s1, &f);
      const int edge = g0 / STEPS;
      const float t = float((g0 - edge * STEPS + f) / STEPS);
      const float2 d = bezier_tangent(loop.beziers[size_t(edge)], std::clamp(t, 0.0f, 1.0f)) *
                       (forward == 1 ? 1.0f : -1.0f);
      if (length(d) > 1e-12f) {
        return normalize(d);
      }
    }
  }
  return unit(p, q);
}

/* One step of the tree: `b` acting on `a`. With Smoothing, each corner where the result's outline goes from one's
 * outline to the other's is rounded: the stretch either side of it, out to where a circle of the rounding's radius
 * would touch, becomes a circular arc (a cubic, sampled). The radius grows from nothing with how deep they overlap (so
 * a seam rounds in as they meet), is less where they cross at a shallow angle (a rounding there would reach far along
 * them: at most four Smoothings), and two near each other share the outline between them (half each). The arc keeps
 * the stretches either side on the loops' own samples, so the edges there are rebuilt from the drawing's curves.
 * `a_loops`, `b_loops`: the loops (of the solve) each side's samples come from, [0, a_loops) and [a_loops, b_loops). */
c2::PathsD combine(const Solve &S, const c2::PathsD &a, const c2::PathsD &b, ShapeOp op, double smoothing, int a_loops,
                   int b_loops)
{
  c2::PathsD r;
  switch (op) {
    case ShapeOp::Union:
      r = c2::Union(a, b, c2::FillRule::NonZero, PRECISION);
      break;
    case ShapeOp::Subtract:
      r = c2::Difference(a, b, c2::FillRule::NonZero, PRECISION);
      break;
    case ShapeOp::Intersect:
      r = c2::Intersect(a, b, c2::FillRule::NonZero, PRECISION);
      break;
    case ShapeOp::Exclude:
      r = c2::Xor(a, b, c2::FillRule::NonZero, PRECISION);
      break;
  }
  if (!(smoothing > 1e-6) || r.empty()) {
    return r;
  }
  const c2::PathsD both = c2::Intersect(a, b, c2::FillRule::NonZero, PRECISION);
  const double around = perimeter(both);
  double area = 0.0;
  for (const c2::PathD &p : both) {
    area += c2::Area(p);
  }
  /* How deep they overlap: about half the overlap's width (a lens of width w: 2 area / perimeter is 2/3 w). */
  const double depth = around > 0.0 ? 2.0 * std::fabs(area) / around : 0.0;
  const double k = std::min(smoothing, depth);
  if (!(k > 1e-6)) {
    return r;
  }
  /* Which side a ring vertex's sample came from: 0 a, 1 b, -1 neither (a crossing, a rounding). */
  const auto side = [&](const c2::PointD &p) {
    const Tag t = S.tag_of(p);
    return t.loop < 0 ? -1 : t.loop < a_loops ? 0 : t.loop < b_loops ? 1 : -1;
  };
  c2::PathsD out;
  for (const c2::PathD &ring : r) {
    const int n = int(ring.size());
    if (n < 4) {
      out.push_back(ring);
      continue;
    }
    std::vector<int> sides(static_cast<size_t>(n));
    for (int i = 0; i < n; i++) {
      sides[size_t(i)] = side(ring[size_t(i)]);
    }
    /* The corners: the vertices with one side's sample before and the other's after. */
    std::vector<int> corners;
    for (int i = 0; i < n; i++) {
      const int before = sides[size_t((i + n - 1) % n)], after = sides[size_t((i + 1) % n)];
      if (before >= 0 && after >= 0 && before != after) {
        corners.push_back(i);
      }
    }
    if (corners.empty()) {
      out.push_back(ring);
      continue;
    }
    /* Length along the ring from each vertex (for halving the outline between corners). */
    std::vector<double> at(static_cast<size_t>(n) + 1, 0.0);
    for (int i = 0; i < n; i++) {
      const c2::PointD &p = ring[size_t(i)], &q = ring[size_t((i + 1) % n)];
      at[size_t(i) + 1] = at[size_t(i)] + std::hypot(q.x - p.x, q.y - p.y);
    }
    const double total = at[size_t(n)];
    const auto gap = [&](int from, int to) {
      const double d = at[size_t(to)] - at[size_t(from)];
      return d > 0.0 ? d : d + total;
    };
    struct Cut {
      int corner, edge_in, edge_out;
      c2::PointD from, to;
      std::vector<c2::PointD> arc;
    };
    std::vector<Cut> cuts;
    const int count = int(corners.size());
    for (int c = 0; c < count; c++) {
      const int i = corners[size_t(c)];
      const c2::PointD &x = ring[size_t(i)];
      const float2 din = unit(ring[size_t((i + n - 1) % n)], x), dout = unit(x, ring[size_t((i + 1) % n)]);
      const float turn = std::acos(std::clamp(dot(din, dout), -1.0f, 1.0f));
      if (turn < 1e-3f) {
        continue;
      }
      /* A rounding of radius rr touches each outline rr tan(turn / 2) from the corner. */
      const double t = std::tan(std::min(double(turn), PI - 1e-3) * 0.5);
      const double room = count > 1 ? 0.5 * std::min(gap(corners[size_t((c + count - 1) % count)], i),
                                                      gap(i, corners[size_t((c + 1) % count)]))
                                    : 0.5 * total;
      const double reach = std::min({k * t, 4.0 * smoothing, room});
      if (!(reach > 1e-6)) {
        continue;
      }
      Cut cut;
      cut.corner = i;
      float2 tin, tout;
      cut.from = ring_walk(ring, i, -1, reach, &cut.edge_in, &tin);
      cut.to = ring_walk(ring, i, 1, reach, &cut.edge_out, &tout);
      tin = ring_tangent(S, ring, cut.edge_in, cut.from);
      tout = ring_tangent(S, ring, cut.edge_out, cut.to);
      /* A circular arc from one touch to the other (a cubic: handles 4/3 tan(a / 4) of its radius). */
      const float2 p0(float(cut.from.x), float(cut.from.y)), p3(float(cut.to.x), float(cut.to.y));
      const float bend = std::acos(std::clamp(dot(tin, tout), -1.0f, 1.0f));
      const float chord = distance(p0, p3);
      const float radius = bend > 1e-4f ? chord / (2.0f * std::sin(bend * 0.5f)) : chord;
      const float h = bend > 1e-4f ? 4.0f / 3.0f * std::tan(bend * 0.25f) * radius : chord / 3.0f;
      const Bezier arc = {p0, p0 + tin * h, p3 - tout * h, p3};
      constexpr int ARC_STEPS = 16;
      for (int j = 1; j < ARC_STEPS; j++) {
        const float2 q = bezier_at(arc, float(j) / ARC_STEPS);
        cut.arc.push_back({double(q.x), double(q.y)});
      }
      cuts.push_back(std::move(cut));
    }
    if (cuts.empty()) {
      out.push_back(ring);
      continue;
    }
    /* The ring again, each cut's stretch swapped for its arc. */
    std::vector<int> cut_at(static_cast<size_t>(n), -1);
    std::vector<bool> dropped(static_cast<size_t>(n), false);
    for (int c = 0; c < int(cuts.size()); c++) {
      const Cut &cut = cuts[size_t(c)];
      /* The vertices after the in touch's edge start, up to the out touch's edge start, go. */
      for (int j = (cut.edge_in + 1) % n;; j = (j + 1) % n) {
        dropped[size_t(j)] = true;
        if (j == cut.edge_out) {
          break;
        }
      }
      cut_at[size_t(cut.edge_in)] = c;
    }
    c2::PathD rounded;
    for (int i = 0; i < n; i++) {
      if (!dropped[size_t(i)]) {
        rounded.push_back(ring[size_t(i)]);
      }
      if (cut_at[size_t(i)] >= 0) {
        const Cut &cut = cuts[size_t(cut_at[size_t(i)])];
        rounded.push_back(cut.from);
        rounded.insert(rounded.end(), cut.arc.begin(), cut.arc.end());
        rounded.push_back(cut.to);
      }
    }
    out.push_back(std::move(rounded));
  }
  /* Tidied (and, were two roundings to cross, made a proper outline again). */
  return c2::Union(out, c2::FillRule::NonZero, PRECISION);
}

bool child_acts(const VectorDrawing &d, int c)
{
  return d.shapes[c].shown && shape_closed_all(d, d.shapes[c]);
}

/* What shape `s` is with its sub shapes acting on it, lowest first (up to `upto`, by index; -1 all). */
c2::PathsD tree_region(Solve &S, int s, int upto, int depth)
{
  const VectorDrawing &d = *S.drawing;
  c2::PathsD acc = own_region(S, s);
  if (depth > 32) {
    return acc;
  }
  for (const int c : shape_children(d, d.shapes[s].id)) {
    if (upto >= 0 && c > upto) {
      break;
    }
    if (!child_acts(d, c)) {
      continue;
    }
    const int a_loops = int(S.loops.size());
    const c2::PathsD sub = tree_region(S, c, -1, depth + 1);
    acc = combine(S, acc, sub, d.shapes[c].op,
                  std::clamp(double(d.shapes[c].smoothing), 0.0, double(SHAPE_SMOOTHING_MAX)), a_loops,
                  int(S.loops.size()));
  }
  return acc;
}

/* A stretch of a result ring along one loop: from sample place u0 to u1 (continuous, in samples), run forward (dir 1)
 * or back (-1) along the loop. */
struct Run {
  int loop = -1;
  int dir = 1;
  double u0 = 0.0, u1 = 0.0;
  /* The ring's vertices it covers. */
  int first = 0, last = 0;
};

/* Whether vertices i and j (next to each other on a result ring) run along a loop from one sample to the other: both
 * tagged on the same loop, a short way apart, every sample between them on the line between them (Clipper drops the
 * samples along a straight stretch). Returns the way they run (1, -1) or 0. */
int linked(const Solve &S, const Tag &a, const Tag &b, const c2::PointD &pa, const c2::PointD &pb)
{
  if (a.loop < 0 || a.loop != b.loop) {
    return 0;
  }
  const Loop &loop = S.loops[a.loop];
  const int m = loop.size();
  const int forward = ((b.g - a.g) % m + m) % m;
  if (forward == 0) {
    return 0;
  }
  const int dir = forward <= m / 2 ? 1 : -1;
  const int steps = dir > 0 ? forward : m - forward;
  for (int k = 1; k < steps; k++) {
    const c2::PointD &q = loop.samples[((a.g + dir * k) % m + m) % m];
    if (distance_to_chord(q, pa, pb, nullptr) > 2.0 / GRID) {
      return 0;
    }
  }
  return dir;
}

/* The loop's place (edge, t) at continuous sample place u. */
void loop_place(const Loop &loop, double u, int dir, int *r_edge, float *r_t)
{
  const int edges = int(loop.beziers.size());
  const double m = double(loop.size());
  u = std::fmod(std::fmod(u, m) + m, m);
  int edge = int(std::floor(u / STEPS));
  double t = (u - edge * STEPS) / STEPS;
  /* Run back, the place at an edge's start is the end of the edge before. */
  if (dir < 0 && t < 1e-9) {
    edge = edge - 1;
    t = 1.0;
  }
  *r_edge = ((edge % edges) + edges) % edges;
  *r_t = float(std::clamp(t, 0.0, 1.0));
}

/* The original point at the start of a loop's edge (as it runs), and its line, radius and opacity. */
int edge_start_point(const VectorDrawing &d, const OrientedEdge &oe)
{
  int a = 0, b = 0;
  curve_segment_points(d.curves[oe.edge.curve], oe.edge.segment, &a, &b);
  return oe.reversed ? b : a;
}
int edge_end_point(const VectorDrawing &d, const OrientedEdge &oe)
{
  int a = 0, b = 0;
  curve_segment_points(d.curves[oe.edge.curve], oe.edge.segment, &a, &b);
  return oe.reversed ? a : b;
}

/* A node part way along an edge (t as it runs): the line's width and opacity there, between its ends'. */
ShapeTreeNode node_on_edge(const VectorDrawing &d, const Loop &loop, int edge, float t)
{
  ShapeTreeNode n;
  const OrientedEdge &oe = loop.chain[size_t(edge)];
  const int a = edge_start_point(d, oe), b = edge_end_point(d, oe);
  n.pos = bezier_at(loop.beziers[size_t(edge)], t);
  n.shape = loop.shape;
  if (t <= 0.0f) {
    n.point = a;
  }
  else if (t >= 1.0f) {
    n.point = b;
  }
  const MeshPoint &pa = d.points[size_t(a)], &pb = d.points[size_t(b)];
  n.radius = pa.radius + (pb.radius - pa.radius) * t;
  n.opacity = pa.opacity + (pb.opacity - pa.opacity) * t;
  return n;
}

/* The result built up as segments, each starting at a node. */
struct Builder {
  std::vector<ShapeTreeNode> nodes;
  std::vector<Bezier> segs;

  void add(const ShapeTreeNode &start, const Bezier &c)
  {
    if (distance(c[0], c[3]) < 1e-7f && distance(c[1], c[0]) < 1e-7f && distance(c[2], c[3]) < 1e-7f) {
      return;
    }
    nodes.push_back(start);
    segs.push_back(c);
  }
};

/* A run of a loop from u0 to u1 as segments: whole edges as drawn, the ends' edges split exactly. */
void add_run(const Solve &S, const Run &run, Builder &out)
{
  const VectorDrawing &d = *S.drawing;
  const Loop &loop = S.loops[size_t(run.loop)];
  const double m = double(loop.size());
  double u = run.u0, end = run.u1;
  if (run.dir > 0) {
    while (end < u - 1e-9) {
      end += m;
    }
  }
  else {
    while (end > u + 1e-9) {
      end -= m;
    }
  }
  for (int guard = 0; guard < int(loop.beziers.size()) * 2 + 2 && std::fabs(end - u) > 1e-9; guard++) {
    /* The edge u is on, as the run goes, and how far along it the piece goes. */
    double edge_from, edge_to;
    if (run.dir > 0) {
      edge_from = std::floor(u / STEPS + 1e-9) * STEPS;
      edge_to = edge_from + STEPS;
    }
    else {
      edge_to = std::ceil(u / STEPS - 1e-9) * STEPS;
      edge_from = edge_to - STEPS;
    }
    const double next = run.dir > 0 ? std::min(edge_to, end) : std::max(edge_from, end);
    const int edges = int(loop.beziers.size());
    const int edge = ((int(std::llround(edge_from / STEPS)) % edges) + edges) % edges;
    const float t0 = float((u - edge_from) / STEPS), t1 = float((next - edge_from) / STEPS);
    ShapeTreeNode start = node_on_edge(d, loop, edge, std::clamp(t0, 0.0f, 1.0f));
    const OrientedEdge &oe = loop.chain[size_t(edge)];
    start.line_off = d.curves[oe.edge.curve].points[oe.edge.segment].edge_hidden;
    out.add(start, bezier_piece(loop.beziers[size_t(edge)], std::clamp(t0, 0.0f, 1.0f), std::clamp(t1, 0.0f, 1.0f)));
    u = next;
  }
}

/* Cubics from p to q through `d` (p and q included), leaving p along `tp` and reaching q along `tq` (both as the line
 * runs): one where it fits, split in the middle where not. */
void fit_rounding(const std::vector<float2> &d, float2 tp, float2 tq, int depth, const ShapeTreeNode &from,
                  const ShapeTreeNode &to, Builder &out)
{
  const float2 p = d.front(), q = d.back();
  float a1 = 0.0f, a2 = 0.0f;
  bezier_fit_handle_lengths(p, q, tp, tq * -1.0f, d, &a1, &a2);
  const Bezier c = {p, p + tp * a1, q - tq * a2, q};
  float worst = 0.0f;
  size_t at = d.size() / 2;
  for (size_t i = 1; i + 1 < d.size(); i++) {
    float best = std::numeric_limits<float>::max();
    float2 last = c[0];
    for (int k = 1; k <= 32; k++) {
      const float2 next = bezier_at(c, float(k) / 32.0f);
      best = std::min(best, distance_to_segment(d[i], last, next));
      last = next;
    }
    if (best > worst) {
      worst = best;
      at = i;
    }
  }
  const float chord = distance(p, q);
  if (worst <= std::max(chord * 0.008f, 2e-5f) || depth >= 3 || d.size() < 5) {
    ShapeTreeNode n = from;
    n.point = -1;
    n.shape = -1;
    n.line_off = false;
    n.pos = p;
    out.add(n, c);
    return;
  }
  at = std::clamp(at, size_t(2), d.size() - 3);
  const float2 tm = normalize(d[at + 1] - d[at - 1]);
  ShapeTreeNode mid = from;
  const float f = float(at) / float(d.size() - 1);
  mid.radius = from.radius + (to.radius - from.radius) * f;
  mid.opacity = from.opacity + (to.opacity - from.opacity) * f;
  fit_rounding(std::vector<float2>(d.begin(), d.begin() + std::ptrdiff_t(at) + 1), tp, tm, depth + 1, from, mid, out);
  fit_rounding(std::vector<float2>(d.begin() + std::ptrdiff_t(at), d.end()), tm, tq, depth + 1, mid, to, out);
}

/* How far a vertex may be from a loop's samples and still be on it (the boolean's own crossings are on the lines between
 * samples, a rounding's arcs that run along an outline a little off them). */
constexpr double ON_LOOP = 6e-5;

/* Pushes a run's end on (`at_end`) or its start back to vertex x, if x is on the loop just past it: returns whether it
 * did, `u` moved there. */
bool extend_to(const Solve &S, const Run &run, bool at_end, const c2::PointD &x, double *u)
{
  const Loop &loop = S.loops[size_t(run.loop)];
  const int m = loop.size();
  const int step = at_end ? run.dir : -run.dir;
  /* The sample at or behind u, as the run goes on. */
  int g = step > 0 ? int(std::floor(*u + 1e-9)) : int(std::ceil(*u - 1e-9));
  for (int tries = 0; tries < 2; tries++, g += step) {
    const c2::PointD &a = loop.samples[size_t(((g % m) + m) % m)];
    const c2::PointD &b = loop.samples[size_t((((g + step) % m) + m) % m)];
    double along = 0.0;
    const double off = distance_to_chord(x, a, b, &along);
    const double place = g + step * along;
    if (off <= ON_LOOP && (place - *u) * step >= -1e-9) {
      *u = place;
      return true;
    }
    if (along < 1.0 - 1e-9) {
      break;
    }
  }
  return false;
}

/* One ring of the result as nodes: runs along the loops as their edges are, the crossings found exactly, roundings
 * fitted. */
ShapeTreeLoop rebuild_ring(const Solve &S, const c2::PathD &ring)
{
  const VectorDrawing &d = *S.drawing;
  ShapeTreeLoop out;
  out.hole = c2::Area(ring) < 0.0;
  const int n = int(ring.size());
  std::vector<Tag> tags(static_cast<size_t>(n));
  for (int i = 0; i < n; i++) {
    tags[size_t(i)] = S.tag_of(ring[size_t(i)]);
  }
  /* link[i]: vertex i runs on to i + 1 along its loop, forward (1) or back (-1), or not (0). */
  std::vector<int> link(static_cast<size_t>(n));
  for (int i = 0; i < n; i++) {
    const int j = (i + 1) % n;
    link[size_t(i)] = linked(S, tags[size_t(i)], tags[size_t(j)], ring[size_t(i)], ring[size_t(j)]);
  }
  Builder b;
  int start = -1;
  for (int i = 0; i < n && start < 0; i++) {
    const int before = (i + n - 1) % n;
    if (tags[size_t(i)].loop < 0 || link[size_t(before)] == 0 ||
        (link[size_t(i)] != 0 && link[size_t(i)] != link[size_t(before)]))
    {
      start = i;
    }
  }
  if (start < 0) {
    /* Linked all the way round: a loop as drawn, from an edge's start so its edges go in whole. */
    const Tag &t = tags[0];
    Run run;
    run.loop = t.loop;
    run.dir = link[0];
    run.u0 = std::floor(double(t.g) / STEPS) * STEPS;
    run.u1 = run.u0 + run.dir * S.loops[size_t(t.loop)].size();
    add_run(S, run, b);
  }
  else {
    /* The ring from `start` as runs and the loose vertices between them. */
    struct Item {
      bool is_run = false;
      Run run;
      int vertex = 0;
      /* A loose vertex taken onto the end of the run before it, or the start of the run after it. */
      bool by_end = false, by_start = false;
    };
    std::vector<Item> items;
    for (int k = 0; k < n;) {
      const int i = (start + k) % n;
      const Tag &t = tags[size_t(i)];
      if (t.loop < 0) {
        Item item;
        item.vertex = i;
        items.push_back(item);
        k++;
        continue;
      }
      Run run;
      run.loop = t.loop;
      run.u0 = run.u1 = t.g;
      run.dir = link[size_t(i)] != 0 ? link[size_t(i)] : 1;
      int count = 1;
      while (k + count < n && link[size_t((start + k + count - 1) % n)] == run.dir) {
        run.u1 = tags[size_t((start + k + count) % n)].g;
        count++;
      }
      const double m = double(S.loops[size_t(t.loop)].size());
      while (run.dir > 0 && run.u1 < run.u0) {
        run.u1 += m;
      }
      while (run.dir < 0 && run.u1 > run.u0) {
        run.u1 -= m;
      }
      Item item;
      item.is_run = true;
      item.run = run;
      item.vertex = i;
      items.push_back(item);
      k += count;
    }
    const int count = int(items.size());
    std::vector<int> runs;
    for (int k = 0; k < count; k++) {
      if (items[size_t(k)].is_run) {
        runs.push_back(k);
      }
    }
    if (runs.empty()) {
      /* Nothing of the drawing's outlines: a smooth closed curve through what's left. */
      const c2::PathD path = c2::SimplifyPath(ring, 0.0005, true);
      const int m = int(path.size());
      for (int i = 0; m >= 3 && i < m; i++) {
        const float2 p = to_f2(path[size_t(i)]), prev = to_f2(path[size_t((i + m - 1) % m)]),
                     next = to_f2(path[size_t((i + 1) % m)]), after = to_f2(path[size_t((i + 2) % m)]);
        const float2 t0 = normalize(next - prev), t1 = normalize(after - p);
        const float len = distance(p, next) / 3.0f;
        ShapeTreeNode node;
        node.pos = p;
        b.add(node, {p, p + t0 * len, next - t1 * len, next});
      }
    }
    /* Each run reaching out over the loose vertices on its loop just past its ends. A run of one vertex goes whichever
     * way reaches. */
    for (const int k : runs) {
      Run &run = items[size_t(k)].run;
      const bool single = std::fabs(run.u1 - run.u0) < 1e-9;
      for (int attempt = 0; attempt < (single ? 2 : 1); attempt++) {
        if (attempt == 1) {
          run.dir = -run.dir;
        }
        bool reached = false;
        for (int j = (k + 1) % count; !items[size_t(j)].is_run; j = (j + 1) % count) {
          if (!extend_to(S, run, true, ring[size_t(items[size_t(j)].vertex)], &run.u1)) {
            break;
          }
          items[size_t(j)].by_end = reached = true;
        }
        for (int j = (k + count - 1) % count; !items[size_t(j)].is_run; j = (j + count - 1) % count) {
          if (!extend_to(S, run, false, ring[size_t(items[size_t(j)].vertex)], &run.u0)) {
            break;
          }
          items[size_t(j)].by_start = reached = true;
        }
        if (reached || !single) {
          break;
        }
      }
    }
    for (size_t r = 0; r < runs.size(); r++) {
      Run &run = items[size_t(runs[r])].run;
      Run &next = items[size_t(runs[(r + 1) % runs.size()])].run;
      const int k = runs[r], k_next = runs[(r + 1) % runs.size()];
      bool crossing = false;
      for (int j = (k + 1) % count; j != k_next; j = (j + 1) % count) {
        crossing |= items[size_t(j)].by_end && items[size_t(j)].by_start;
      }
      if (!crossing) {
        continue;
      }
      /* Where the two outlines cross, found exactly on both curves. */
      const Loop &la = S.loops[size_t(run.loop)], &lb = S.loops[size_t(next.loop)];
      int ea, eb;
      float ta, tb;
      loop_place(la, run.u1, -run.dir, &ea, &ta);
      loop_place(lb, next.u0, next.dir, &eb, &tb);
      float sa = ta, sb = tb;
      if (bezier_cross(la.beziers[size_t(ea)], lb.beziers[size_t(eb)], &sa, &sb)) {
        run.u1 += double(sa - ta) * STEPS;
        next.u0 += double(sb - tb) * STEPS;
      }
    }
    for (size_t r = 0; r < runs.size(); r++) {
      const Run &run = items[size_t(runs[r])].run;
      const Run &next = items[size_t(runs[(r + 1) % runs.size()])].run;
      const int k = runs[r], k_next = runs[(r + 1) % runs.size()];
      add_run(S, run, b);
      const Loop &la = S.loops[size_t(run.loop)], &lb = S.loops[size_t(next.loop)];
      int ea, eb;
      float ta, tb;
      loop_place(la, run.u1, -run.dir, &ea, &ta);
      loop_place(lb, next.u0, next.dir, &eb, &tb);
      const float2 p = bezier_at(la.beziers[size_t(ea)], ta), q = bezier_at(lb.beziers[size_t(eb)], tb);
      std::vector<float2> loose{p};
      for (int j = (k + 1) % count; j != k_next; j = (j + 1) % count) {
        if (!items[size_t(j)].by_end && !items[size_t(j)].by_start) {
          loose.push_back(to_f2(ring[size_t(items[size_t(j)].vertex)]));
        }
      }
      loose.push_back(q);
      if (loose.size() == 2 && distance(p, q) < 1e-4f) {
        continue;
      }
      ShapeTreeNode from = node_on_edge(d, la, ea, ta), to = node_on_edge(d, lb, eb, tb);
      if (loose.size() == 2) {
        /* Straight across (outlines meeting without a vertex between). */
        ShapeTreeNode node = from;
        node.point = -1;
        node.pos = p;
        b.add(node, {p, p + (q - p) / 3.0f, q - (q - p) / 3.0f, q});
        continue;
      }
      /* The rounding leaves one outline and joins the next as they run. */
      float2 tp = bezier_tangent(la.beziers[size_t(ea)], ta) * float(run.dir);
      float2 tq = bezier_tangent(lb.beziers[size_t(eb)], tb) * float(next.dir);
      tp = length(tp) > 1e-12f ? normalize(tp) : normalize(loose[1] - p);
      tq = length(tq) > 1e-12f ? normalize(tq) : normalize(q - loose[loose.size() - 2]);
      fit_rounding(loose, tp, tq, 0, from, to, b);
    }
  }
  /* Segments into nodes: each node's out handle from its segment, its in handle from the one before. */
  const size_t m = b.segs.size();
  if (m < 2) {
    return {};
  }
  for (size_t i = 0; i < m; i++) {
    ShapeTreeNode node = b.nodes[i];
    const Bezier &c = b.segs[i], &prev = b.segs[(i + m - 1) % m];
    node.pos = c[0];
    node.handle_out = c[1] - c[0];
    node.handle_in = prev[2] - node.pos;
    out.nodes.push_back(node);
  }
  return out;
}

uint64_t mix(uint64_t h, uint64_t v)
{
  h ^= v + 0x9e3779b97f4a7c15ull + (h << 6) + (h >> 2);
  return h * 0xff51afd7ed558ccdull;
}

uint64_t mix_float(uint64_t h, float v)
{
  uint32_t bits;
  std::memcpy(&bits, &v, sizeof(bits));
  return mix(h, bits);
}

/* Everything a tree's solve reads: its shapes' outlines (as Beziers), widths, lines off, operations and smoothing. */
uint64_t tree_hash(const VectorDrawing &d, int s, int upto)
{
  uint64_t h = mix(uint64_t(upto + 1), d.shapes.size());
  for (const int m : shape_tree_members(d, s)) {
    const Shape &shape = d.shapes[size_t(m)];
    h = mix(h, shape.id * 16 + uint64_t(shape.op) * 2 + uint64_t(shape.shown));
    h = mix(h, uint64_t(shape.fill_rule) + uint64_t(m) * 4 + (shape.parent << 8));
    h = mix_float(h, shape.smoothing);
    for (const ShapeEdge &e : shape.edges) {
      const Curve &curve = d.curves[size_t(e.curve)];
      float2 c[4];
      curve_segment_bezier(d, curve, e.segment, c);
      int a, b;
      curve_segment_points(curve, e.segment, &a, &b);
      h = mix(h, uint64_t(e.curve) << 32 | uint64_t(uint32_t(e.segment)));
      h = mix(h, uint64_t(a) << 32 | uint64_t(uint32_t(b)) | uint64_t(curve.points[size_t(e.segment)].edge_hidden) << 63);
      for (const float2 &p : c) {
        h = mix_float(mix_float(h, p.x), p.y);
      }
      h = mix_float(mix_float(h, d.points[size_t(a)].radius), d.points[size_t(a)].opacity);
    }
  }
  return h;
}

struct Solved {
  std::vector<ShapeTreeLoop> loops;
  bool empty = false;
};

Solved solve(const VectorDrawing &drawing, int s, int upto)
{
  OANIM_PROFILE("shape_tree_solve");
  Solve S;
  S.drawing = &drawing;
  const c2::PathsD region = tree_region(S, s, upto, 0);
  Solved out;
  double largest = 0.0;
  for (const c2::PathD &p : region) {
    largest = std::max(largest, std::fabs(c2::Area(p)));
  }
  for (const c2::PathD &ring : region) {
    /* A sliver the booleans leave where outlines run together. */
    if (ring.size() < 3 || std::fabs(c2::Area(ring)) <= std::max(1e-12, largest * 1e-5)) {
      continue;
    }
    ShapeTreeLoop loop = rebuild_ring(S, ring);
    if (loop.nodes.size() >= 2) {
      out.loops.push_back(std::move(loop));
    }
  }
  out.empty = out.loops.empty();
  return out;
}

}  // namespace

std::vector<ShapeTreeLoop> shape_tree_solve(const VectorDrawing &drawing, int s, int upto, bool *r_empty)
{
  Solved solved = solve(drawing, s, upto);
  if (r_empty) {
    *r_empty = solved.empty;
  }
  return std::move(solved.loops);
}

/* A shape with sub shapes that act on it (shown, closed), itself closed and shown. */
static bool tree_root(const VectorDrawing &d, int s)
{
  const Shape &shape = d.shapes[size_t(s)];
  if (shape.parent != 0 || !shape.shown) {
    return false;
  }
  const std::vector<int> children = shape_children(d, shape.id);
  return std::any_of(children.begin(), children.end(), [&](int c) { return child_acts(d, c); }) &&
         shape_closed_all(d, shape);
}

bool drawing_shape_tree_apply(VectorDrawing &drawing)
{
  if (!drawing_has_shape_tree(drawing)) {
    return false;
  }
  OANIM_PROFILE("shape_tree");
  /* Results first (they read the drawing's curves as they are), then put in. */
  std::vector<std::pair<int, Solved>> results;
  static thread_local std::map<uint64_t, Solved> cache;
  for (int s = 0; s < int(drawing.shapes.size()); s++) {
    if (!tree_root(drawing, s)) {
      continue;
    }
    const uint64_t key = tree_hash(drawing, s, -1);
    auto it = cache.find(key);
    if (it == cache.end()) {
      if (cache.size() > 64) {
        cache.clear();
      }
      it = cache.emplace(key, solve(drawing, s, -1)).first;
    }
    results.push_back({s, it->second});
  }
  for (Shape &shape : drawing.shapes) {
    if (!shape.shown) {
      shape.hidden = true;
    }
    /* A sub shape draws nothing of its own (its parent draws the result), but is still picked. */
    if (shape.parent != 0 && drawing_shape_index(drawing, shape.parent) >= 0) {
      shape.merged_fill = shape.merged_line = true;
    }
  }
  for (const auto &[s, solved] : results) {
    Shape &shape = drawing.shapes[size_t(s)];
    if (solved.empty) {
      shape.tree_empty = true;
      shape.merged_fill = shape.merged_line = true;
      continue;
    }
    shape.edges.clear();
    for (const ShapeTreeLoop &loop : solved.loops) {
      Curve curve;
      curve.closed = true;
      for (const ShapeTreeNode &node : loop.nodes) {
        MeshPoint point;
        point.pos = node.pos;
        point.setup_pos = node.pos;
        point.radius = node.radius;
        point.opacity = node.opacity;
        point.id = drawing.next_id++;
        drawing.points.push_back(point);
        CurvePoint cp;
        cp.point = int(drawing.points.size()) - 1;
        cp.handles_set = true;
        cp.handle_in = cp.setup_in = node.handle_in;
        cp.handle_out = cp.setup_out = node.handle_out;
        cp.edge_hidden = node.line_off;
        curve.points.push_back(cp);
      }
      drawing.curves.push_back(std::move(curve));
      const int c = int(drawing.curves.size()) - 1;
      for (int seg = 0; seg < int(loop.nodes.size()); seg++) {
        shape.edges.push_back({c, seg});
      }
    }
    if (solved.loops.size() > 1) {
      shape.fill_rule = FillRule::EvenOdd;
    }
    /* Its brush lays its stamps along the result as it is (it has no setup outline of its own). */
    shape.merge_made = true;
  }
  return true;
}

/* A new point's bone weights: the mean of the nearest points the outline kept, before and after it. */
static std::vector<BoneWeight> weights_between(const VectorDrawing &drawing, const ShapeTreeLoop &loop, int i)
{
  const int n = int(loop.nodes.size());
  std::vector<const MeshPoint *> sides;
  for (const int dir : {-1, 1}) {
    for (int step = 1; step < n; step++) {
      const int k = loop.nodes[size_t(((i + dir * step) % n + n) % n)].point;
      if (k >= 0 && k < int(drawing.points.size())) {
        sides.push_back(&drawing.points[size_t(k)]);
        break;
      }
    }
  }
  std::vector<BoneWeight> out;
  for (const MeshPoint *side : sides) {
    for (const BoneWeight &w : side->weights) {
      auto it = std::find_if(out.begin(), out.end(), [&](const BoneWeight &o) { return o.bone == w.bone; });
      if (it == out.end()) {
        out.push_back({w.bone, 0.0f});
        it = out.end() - 1;
      }
      it->weight += w.weight / float(sides.size());
    }
  }
  return out;
}

bool drawing_shape_apply(VectorDrawing &drawing, int s)
{
  if (s < 0 || s >= int(drawing.shapes.size()) || drawing.shapes[size_t(s)].parent == 0) {
    return false;
  }
  const int p = drawing_shape_index(drawing, drawing.shapes[size_t(s)].parent);
  if (p < 0 || !child_acts(drawing, s)) {
    return false;
  }
  /* What goes: the parent's sub shapes up to this one that act, each with its own tree (worked into it). */
  std::vector<int> applied;
  for (const int c : shape_children(drawing, drawing.shapes[size_t(p)].id)) {
    if (c <= s && child_acts(drawing, c)) {
      for (const int m : shape_tree_members(drawing, c)) {
        applied.push_back(m);
      }
    }
  }
  bool empty = false;
  const std::vector<ShapeTreeLoop> loops = shape_tree_solve(drawing, p, s, &empty);
  if (empty || loops.empty()) {
    return false;
  }
  /* The curves the parent and the applied shapes were drawn on. */
  std::vector<bool> old_curve(drawing.curves.size(), false);
  for (const ShapeEdge &e : drawing.shapes[size_t(p)].edges) {
    old_curve[size_t(e.curve)] = true;
  }
  for (const int m : applied) {
    for (const ShapeEdge &e : drawing.shapes[size_t(m)].edges) {
      old_curve[size_t(e.curve)] = true;
    }
  }

  /* The outline as curves of the parent's own: the points it still runs through (the same points), new ones where it
   * changed, each with the handles it has there and its line off where the edge's was. */
  std::vector<ShapeEdge> edges;
  for (const ShapeTreeLoop &loop : loops) {
    Curve curve;
    curve.closed = true;
    std::vector<int> used;
    for (int i = 0; i < int(loop.nodes.size()); i++) {
      const ShapeTreeNode &node = loop.nodes[size_t(i)];
      int point = node.point;
      if (point < 0 || point >= int(drawing.points.size()) ||
          std::find(used.begin(), used.end(), point) != used.end())
      {
        MeshPoint made;
        made.pos = node.pos;
        made.radius = node.radius;
        made.opacity = node.opacity;
        made.weights = weights_between(drawing, loop, i);
        drawing.points.push_back(std::move(made));
        point = int(drawing.points.size()) - 1;
      }
      used.push_back(point);
      CurvePoint cp;
      cp.point = point;
      cp.handle_in = node.handle_in;
      cp.handle_out = node.handle_out;
      cp.handles_set = true;
      cp.edge_hidden = node.line_off;
      curve.points.push_back(cp);
    }
    const int c = int(drawing.curves.size());
    drawing.curves.push_back(std::move(curve));
    for (int seg = 0; seg < int(loop.nodes.size()); seg++) {
      edges.push_back({c, seg});
    }
  }
  old_curve.resize(drawing.curves.size(), false);
  Shape &parent = drawing.shapes[size_t(p)];
  parent.edges = std::move(edges);
  if (loops.size() > 1) {
    parent.fill_rule = FillRule::EvenOdd;
  }
  /* The applied shapes go. */
  std::vector<uint64_t> gone;
  for (const int m : applied) {
    gone.push_back(drawing.shapes[size_t(m)].id);
  }
  std::erase_if(drawing.shapes, [&](const Shape &x) { return std::find(gone.begin(), gone.end(), x.id) != gone.end(); });
  /* Their curves and the parent's old ones, where no shape is on them any more, and the points left on no curve. */
  for (const Shape &x : drawing.shapes) {
    for (const ShapeEdge &e : x.edges) {
      old_curve[size_t(e.curve)] = false;
    }
  }
  std::vector<bool> on_old(drawing.points.size(), false);
  for (int c = 0; c < int(drawing.curves.size()); c++) {
    if (old_curve[size_t(c)]) {
      for (const CurvePoint &cp : drawing.curves[size_t(c)].points) {
        on_old[size_t(cp.point)] = true;
      }
    }
  }
  drawing_remove_curves(drawing, old_curve);
  for (const Curve &curve : drawing.curves) {
    for (const CurvePoint &cp : curve.points) {
      on_old[size_t(cp.point)] = false;
    }
  }
  if (std::find(on_old.begin(), on_old.end(), true) != on_old.end()) {
    drawing_remove_points(drawing, on_old);
  }
  drawing_ensure_ids(drawing);
  return true;
}

static void layers_mend(std::vector<Layer> &layers)
{
  for (Layer &layer : layers) {
    if (std::any_of(layer.drawing.shapes.begin(), layer.drawing.shapes.end(),
                    [](const Shape &s) { return s.parent != 0; }))
    {
      drawing_shape_tree_mend(layer.drawing);
    }
    layers_mend(layer.children);
  }
}

void document_shape_trees_mend(Document &doc)
{
  layers_mend(doc.layers);
}

}  // namespace oanim
