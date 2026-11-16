#include "data/quick_shape.hh"

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace oanim {

/* A quarter of a circle as one Bezier: its handles this much of the radius long. */
static constexpr float QUARTER_HANDLE = 0.5522847f;

bool quick_shape_fit(const std::vector<float2> &points, float2 end, float pixel, QuickShape *r_shape)
{
  if (points.size() < 2 || !(pixel > 0.0f)) {
    return false;
  }
  float2 lo = points.front(), hi = points.front();
  float along = 0.0f;
  for (size_t i = 0; i < points.size(); i++) {
    lo = {std::min(lo.x, points[i].x), std::min(lo.y, points[i].y)};
    hi = {std::max(hi.x, points[i].x), std::max(hi.y, points[i].y)};
    if (i > 0) {
      along += distance(points[i - 1], points[i]);
    }
  }
  const float size = distance(lo, hi);
  if (size < pixel * 12.0f) {
    return false;
  }
  QuickShape shape;
  /* Round to near its start, having gone some way: a loop. */
  const float gap = distance(points.front(), points.back());
  if (gap < std::max(pixel * 20.0f, size * 0.22f) && along > size * 1.8f && points.size() >= 8) {
    /* The ellipse with the line's spread: the mean and covariance over its length (so where the pen went slowly,
     * dense with points, counts no more), closed back to its start. Along an ellipse's axis the spread is half
     * the radius squared. */
    float total = 0.0f;
    float2 mean;
    const size_t n = points.size();
    for (size_t i = 0; i < n; i++) {
      const float2 p = points[i], q = points[(i + 1) % n];
      const float w = distance(p, q);
      mean += (p + q) * (0.5f * w);
      total += w;
    }
    if (!(total > 0.0f)) {
      return false;
    }
    mean = mean / total;
    float sxx = 0.0f, sxy = 0.0f, syy = 0.0f;
    for (size_t i = 0; i < n; i++) {
      const float2 p = points[i], q = points[(i + 1) % n];
      const float w = distance(p, q);
      /* The segment's own spread as well as its middle's, so a few long sides still give the right size. */
      const float2 d0 = p - mean, d1 = q - mean;
      sxx += w * (d0.x * d0.x + d0.x * d1.x + d1.x * d1.x) / 3.0f;
      sxy += w * (2.0f * d0.x * d0.y + d0.x * d1.y + d1.x * d0.y + 2.0f * d1.x * d1.y) / 6.0f;
      syy += w * (d0.y * d0.y + d0.y * d1.y + d1.y * d1.y) / 3.0f;
    }
    sxx /= total;
    sxy /= total;
    syy /= total;
    const float half_sum = 0.5f * (sxx + syy), half_diff = 0.5f * (sxx - syy);
    const float root = std::sqrt(half_diff * half_diff + sxy * sxy);
    shape.kind = QuickShape::Kind::Ellipse;
    shape.center = mean;
    shape.angle = 0.5f * std::atan2(2.0f * sxy, sxx - syy);
    shape.radii = {std::sqrt(std::max(2.0f * (half_sum + root), 0.0f)), std::sqrt(std::max(2.0f * (half_sum - root), 0.0f))};
    /* The spread over its length is round only for a circle (a long ellipse's flat sides weigh more): the radii are
     * the least squares fit of x^2 A + y^2 B = 1 along its axes, the spread's if that fails. */
    double s_xx = 0.0, s_xy = 0.0, s_yy = 0.0, s_x = 0.0, s_y = 0.0;
    for (size_t i = 0; i < n; i++) {
      const float w = distance(points[i], points[(i + 1) % n]);
      const float2 d = rotate(lerp(points[i], points[(i + 1) % n], 0.5f) - mean, -shape.angle);
      const double x2 = double(d.x) * d.x, y2 = double(d.y) * d.y;
      s_xx += w * x2 * x2;
      s_xy += w * x2 * y2;
      s_yy += w * y2 * y2;
      s_x += w * x2;
      s_y += w * y2;
    }
    const double det = s_xx * s_yy - s_xy * s_xy;
    if (std::abs(det) > 1e-30) {
      const double fa = (s_x * s_yy - s_y * s_xy) / det, fb = (s_y * s_xx - s_x * s_xy) / det;
      if (fa > 0.0 && fb > 0.0) {
        shape.radii = {float(1.0 / std::sqrt(fa)), float(1.0 / std::sqrt(fb))};
      }
    }
    shape.radii.y = std::max(shape.radii.y, pixel);
    shape.radii.x = std::max(shape.radii.x, pixel);
  }
  else {
    shape.kind = QuickShape::Kind::Line;
    shape.a = points.front();
    shape.b = end;
    if (distance(shape.a, shape.b) < pixel * 2.0f) {
      return false;
    }
  }
  *r_shape = shape;
  return true;
}

float2 quick_shape_radii(const QuickShape &shape)
{
  if (shape.circle) {
    const float r = 0.5f * (shape.radii.x + shape.radii.y);
    return {r, r};
  }
  return shape.radii;
}

/* A place on the ellipse at `t` radians round from its first radius, and the way it goes there per radian. */
static void ellipse_at(const QuickShape &shape, float t, float2 *r_pos, float2 *r_way)
{
  const float2 radii = quick_shape_radii(shape);
  *r_pos = shape.center + rotate({radii.x * std::cos(t), radii.y * std::sin(t)}, shape.angle);
  *r_way = rotate({-radii.x * std::sin(t), radii.y * std::cos(t)}, shape.angle);
}

std::vector<InkKnot> quick_shape_knots(const QuickShape &shape, float radius)
{
  std::vector<InkKnot> knots;
  if (shape.kind == QuickShape::Kind::Line) {
    for (const float2 p : {shape.a, shape.b}) {
      InkKnot k;
      k.pos = p;
      k.radius = radius;
      k.corner = true;
      knots.push_back(k);
    }
    return knots;
  }
  for (int i = 0; i < 4; i++) {
    float2 pos, way;
    ellipse_at(shape, float(i) * 0.5f * PI, &pos, &way);
    InkKnot k;
    k.pos = pos;
    k.radius = radius;
    k.handle_out = way * QUARTER_HANDLE;
    k.handle_in = -k.handle_out;
    knots.push_back(k);
  }
  return knots;
}

std::vector<float2> quick_shape_outline(const QuickShape &shape, int steps)
{
  if (shape.kind == QuickShape::Kind::Line) {
    return {shape.a, shape.b};
  }
  std::vector<float2> out;
  steps = std::max(steps, 8);
  for (int i = 0; i < steps; i++) {
    float2 pos, way;
    ellipse_at(shape, 2.0f * PI * float(i) / float(steps), &pos, &way);
    out.push_back(pos);
  }
  return out;
}

std::vector<float2> quick_shape_handles(const QuickShape &shape)
{
  if (shape.kind == QuickShape::Kind::Line) {
    return {shape.a, shape.b, lerp(shape.a, shape.b, 0.5f)};
  }
  std::vector<float2> out;
  for (int i = 0; i < 4; i++) {
    float2 pos, way;
    ellipse_at(shape, float(i) * 0.5f * PI, &pos, &way);
    out.push_back(pos);
  }
  out.push_back(shape.center);
  return out;
}

QuickShape quick_shape_handle_moved(const QuickShape &shape, int handle, float2 p)
{
  QuickShape out = shape;
  if (shape.kind == QuickShape::Kind::Line) {
    if (handle == 0) {
      out.a = p;
    }
    else if (handle == 1) {
      out.b = p;
    }
    else if (handle == 2) {
      const float2 by = p - lerp(shape.a, shape.b, 0.5f);
      out.a += by;
      out.b += by;
    }
    return out;
  }
  if (handle == 4) {
    out.center = p;
    return out;
  }
  if (handle < 0 || handle > 3) {
    return out;
  }
  const float2 to = p - shape.center;
  const float reach = length(to);
  if (reach < 1e-6f) {
    return out;
  }
  /* The handle points along its radius: the ellipse turns so it points at the pen. */
  out.angle = std::atan2(to.y, to.x) - float(handle) * 0.5f * PI;
  if (shape.circle) {
    out.radii = {reach, reach};
  }
  else if (handle % 2 == 0) {
    out.radii.x = reach;
  }
  else {
    out.radii.y = reach;
  }
  return out;
}

QuickShape quick_shape_held(const QuickShape &snapped, float2 from, float2 pen, bool snap)
{
  QuickShape out = snapped;
  if (snapped.kind == QuickShape::Kind::Line) {
    out.b = pen;
    if (snap) {
      const float2 to = pen - snapped.a;
      const float step = PI / 12.0f;
      const float angle = std::round(std::atan2(to.y, to.x) / step) * step;
      out.b = snapped.a + float2(std::cos(angle), std::sin(angle)) * length(to);
    }
    return out;
  }
  const float2 was = from - snapped.center, now = pen - snapped.center;
  if (length(was) > 1e-6f && length(now) > 1e-6f) {
    out.radii = snapped.radii * (length(now) / length(was));
    out.angle = snapped.angle + std::atan2(cross(was, now), dot(was, now));
  }
  out.circle = snapped.circle || snap;
  return out;
}

void quick_shape_args(const QuickShape &shape, std::vector<std::pair<std::string, std::string>> &r_args)
{
  const auto pair = [](float2 v) {
    char text[64];
    std::snprintf(text, sizeof(text), "%.9g,%.9g", double(v.x), double(v.y));
    return std::string(text);
  };
  const auto number = [](float v) {
    char text[32];
    std::snprintf(text, sizeof(text), "%.9g", double(v));
    return std::string(text);
  };
  if (shape.kind == QuickShape::Kind::Line) {
    r_args.push_back({"shape", "LINE"});
    r_args.push_back({"a", pair(shape.a)});
    r_args.push_back({"b", pair(shape.b)});
    return;
  }
  r_args.push_back({"shape", "ELLIPSE"});
  r_args.push_back({"center", pair(shape.center)});
  r_args.push_back({"radii", pair(shape.radii)});
  r_args.push_back({"angle", number(shape.angle * 180.0f / PI)});
  r_args.push_back({"circle", shape.circle ? "1" : "0"});
}

}  // namespace oanim
