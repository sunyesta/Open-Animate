#include "anim/bone_curve.hh"

#include <algorithm>
#include <cmath>

#include "anim/controller.hh"
#include "data/bones.hh"

namespace oanim {

static float wrap_angle(float a)
{
  return std::atan2(std::sin(a), std::cos(a));
}

/* Halfway between two directions, the short way round. */
static float halfway(float a1, float a2)
{
  return a1 + wrap_angle(a2 - a1) * 0.5f;
}

/* A handle turned past this from its bone would fold the curve back on itself. */
static float turn_clamp(float a)
{
  return std::clamp(a, -1.4f, 1.4f);
}

/* How long a handle is that makes a bone of `length`, turned `turn` at both ends the same way, a circular arc. */
static float arc_reach(float length, float turn)
{
  const float c = std::cos(turn * 0.5f);
  return length / (3.0f * c * c);
}

static float angle_of(float2 v)
{
  return std::atan2(v.y, v.x);
}

static float clamp01(float v)
{
  return std::clamp(v, 0.0f, 1.0f);
}

float bone_curve_channel_default(std::string_view name)
{
  return name == "curve_lined" || name == "curve_tail_lined" || name.ends_with("_reach") ? 1.0f : 0.0f;
}

bool bone_curve_channel_is_angle(std::string_view name)
{
  return name == "curve_turn" || name == "curve_head_angle" || name == "curve_parent_angle" ||
         name == "curve_tail_turn" || name == "curve_tail_angle";
}

void bone_curve_values_reset(Bone &bone)
{
  bone_curve_channels(bone, [](std::string_view name, float &value, Channel<float> &) {
    value = bone_curve_channel_default(name);
  });
}

bool bone_curve_has(const Bone &bone)
{
  return !bone_is_pin(bone) && !bone_is_controller(bone);
}

static int bone_index(const Layer &armature, uint64_t id)
{
  for (size_t i = 0; i < armature.bones.size(); i++) {
    if (armature.bones[i].id == id) {
      return int(i);
    }
  }
  return -1;
}

int bone_curve_parent(const Layer &armature, size_t i)
{
  const Bone &bone = armature.bones[i];
  if (!bone.connected || bone.parent == 0 || bone.outer_bone != 0 || !bone_curve_has(bone)) {
    return -1;
  }
  const int p = bone_index(armature, bone.parent);
  return p >= 0 && bone_curve_has(armature.bones[size_t(p)]) ? p : -1;
}

int bone_curve_kid(const Layer &armature, size_t i)
{
  const Bone &bone = armature.bones[i];
  if (!bone_curve_has(bone)) {
    return -1;
  }
  int kid = -1;
  for (size_t j = 0; j < armature.bones.size(); j++) {
    const Bone &b = armature.bones[j];
    if (b.parent == bone.id && b.connected && b.outer_bone == 0 && bone_curve_has(b)) {
      if (kid >= 0) {
        return -1;
      }
      kid = int(j);
    }
  }
  return kid;
}

namespace {
/* A bone's curve channels, as now or as they rest. */
struct CurveValues {
  float turn = 0.0f, lined = 1.0f, head_angle = 0.0f, parent_angle = 0.0f, head_reach = 1.0f, parent_reach = 1.0f;
  float tail_turn = 0.0f, tail_lined = 1.0f, tail_angle = 0.0f, tail_reach = 1.0f;
};
}  // namespace

/* As bones.cc's setup values: frame 0's key when animated; unkeyed, the value from before an edit not yet recorded, less
 * what action bone actions add now. On the setup frame the value itself. */
static float value_at(const Channel<float> &ch, float value, bool rest, bool setup_frame)
{
  if (!rest || setup_frame) {
    return value;
  }
  if (ch.animated()) {
    return ch.evaluate(0);
  }
  return (ch.has_last ? ch.last : value) - ch.from_action_bones;
}

static CurveValues curve_values(const Bone &b, bool rest, bool setup_frame)
{
  CurveValues v;
  v.turn = value_at(b.curve_turn_keys, b.curve_turn, rest, setup_frame);
  v.lined = clamp01(value_at(b.curve_lined_keys, b.curve_lined, rest, setup_frame));
  v.head_angle = value_at(b.curve_head_angle_keys, b.curve_head_angle, rest, setup_frame);
  v.parent_angle = value_at(b.curve_parent_angle_keys, b.curve_parent_angle, rest, setup_frame);
  v.head_reach = std::max(0.0f, value_at(b.curve_head_reach_keys, b.curve_head_reach, rest, setup_frame));
  v.parent_reach = std::max(0.0f, value_at(b.curve_parent_reach_keys, b.curve_parent_reach, rest, setup_frame));
  v.tail_turn = value_at(b.curve_tail_turn_keys, b.curve_tail_turn, rest, setup_frame);
  v.tail_lined = clamp01(value_at(b.curve_tail_lined_keys, b.curve_tail_lined, rest, setup_frame));
  v.tail_angle = value_at(b.curve_tail_angle_keys, b.curve_tail_angle, rest, setup_frame);
  v.tail_reach = std::max(0.0f, value_at(b.curve_tail_reach_keys, b.curve_tail_reach, rest, setup_frame));
  return v;
}

static float2 head_of(const std::vector<BonePose> &poses, size_t i, bool rest)
{
  return rest ? poses[i].setup_head : poses[i].head;
}

static float2 tail_of(const std::vector<BonePose> &poses, size_t i, bool rest)
{
  return rest ? poses[i].setup_tail : poses[i].tail;
}

static float2 way_of(const std::vector<BonePose> &poses, size_t i, bool rest)
{
  return tail_of(poses, i, rest) - head_of(poses, i, rest);
}

BoneCurveShape bone_curve_shape(const Layer &armature, const std::vector<BonePose> &poses, size_t i, bool rest,
                                bool setup_frame)
{
  BoneCurveShape s;
  if (i >= poses.size() || i >= armature.bones.size()) {
    return s;
  }
  const float2 v = way_of(poses, i, rest);
  s.angle = angle_of(v);
  s.length = length(v);
  const Bone &bone = armature.bones[i];
  if (!bone_curve_has(bone) || s.length < 1e-9f) {
    return s;
  }
  s.parent = bone_curve_parent(armature, i);
  s.kid = bone_curve_kid(armature, i);
  if (s.parent >= 0 && size_t(s.parent) >= poses.size()) {
    s.parent = -1;
  }
  if (s.kid >= 0 && size_t(s.kid) >= poses.size()) {
    s.kid = -1;
  }
  const CurveValues me = curve_values(bone, rest, setup_frame);
  const CurveValues kid = s.kid >= 0 ? curve_values(armature.bones[size_t(s.kid)], rest, setup_frame) : CurveValues();
  const float a = s.angle;
  /* At a joint between connected bones: lined up, both handles turned the same from halfway between the bones (so the
   * curve runs on smoothly through it); broken, each at its own angle to its own bone; blended between. */
  if (s.parent >= 0) {
    const float mid = halfway(angle_of(way_of(poses, size_t(s.parent), rest)), a);
    s.head_turn = turn_clamp(me.lined * wrap_angle(mid + me.turn - a) + (1.0f - me.lined) * me.head_angle);
  }
  if (s.kid >= 0) {
    const float mid = halfway(a, angle_of(way_of(poses, size_t(s.kid), rest)));
    s.tail_turn = turn_clamp(kid.lined * wrap_angle(mid + kid.turn - a) + (1.0f - kid.lined) * kid.parent_angle);
  }
  /* A free end mirrors the other: the bone one arc (turned by its own offset), not an S. */
  s.head_mirror = s.kid >= 0 ? -s.tail_turn : 0.0f;
  if (s.parent < 0) {
    s.head_turn = turn_clamp(me.lined * (s.head_mirror + me.turn) + (1.0f - me.lined) * me.head_angle);
  }
  s.tail_mirror = s.parent >= 0 ? -s.head_turn : 0.0f;
  if (s.kid < 0) {
    s.tail_turn = turn_clamp(me.tail_lined * (s.tail_mirror + me.tail_turn) + (1.0f - me.tail_lined) * me.tail_angle);
  }
  s.head_reach = me.head_reach;
  s.tail_reach = s.kid >= 0 ? kid.parent_reach : me.tail_reach;
  return s;
}

std::array<float2, 4> bone_curve_controls(const Layer &armature, const std::vector<BonePose> &poses, size_t i,
                                          bool rest, bool setup_frame)
{
  if (i >= poses.size()) {
    return {};
  }
  const float2 h = head_of(poses, i, rest), t = tail_of(poses, i, rest);
  const BoneCurveShape s = bone_curve_shape(armature, poses, i, rest, setup_frame);
  if (s.length < 1e-9f) {
    return {h, h, t, t};
  }
  const float2 u = (t - h) / s.length;
  return {h, h + rotate(u, s.head_turn) * (s.head_reach * arc_reach(s.length, s.head_turn)),
          t - rotate(u, s.tail_turn) * (s.tail_reach * arc_reach(s.length, s.tail_turn)), t};
}

bool bone_curve_bent(const Layer &armature, const std::vector<BonePose> &poses, size_t i)
{
  const BoneCurveShape s = bone_curve_shape(armature, poses, i, false);
  return std::abs(s.head_turn) > 1e-6f || std::abs(s.tail_turn) > 1e-6f;
}

static float2 bezier(const std::array<float2, 4> &p, float t)
{
  const float a = 1.0f - t;
  return p[0] * (a * a * a) + p[1] * (3.0f * a * a * t) + p[2] * (3.0f * a * t * t) + p[3] * (t * t * t);
}

/* The curve's direction at t; where a handle lies on its end (no length) the next control point gives it. */
static float2 bezier_tangent(const std::array<float2, 4> &p, float t)
{
  const float a = 1.0f - t;
  const float2 d = (p[1] - p[0]) * (a * a) + (p[2] - p[1]) * (2.0f * a * t) + (p[3] - p[2]) * (t * t);
  if (length(d) > 1e-9f) {
    return normalize(d);
  }
  const float2 f = t < 0.5f ? p[2] - p[0] : p[3] - p[1];
  return length(f) > 1e-12f ? normalize(f) : float2(1.0f, 0.0f);
}

/* Steps along each bone's curve. */
static constexpr int LINE_STEPS = 16;

BoneCurveLine bone_curve_line(const Layer &armature, const std::vector<BonePose> &poses,
                              const std::vector<size_t> &chain, bool rest, bool setup_frame)
{
  BoneCurveLine line;
  for (size_t j = 0; j < chain.size(); j++) {
    const std::array<float2, 4> p = bone_curve_controls(armature, poses, chain[j], rest, setup_frame);
    line.bone_starts.push_back(float(line.points.empty() ? 0 : line.points.size() - 1));
    for (int k = 0; k <= LINE_STEPS; k++) {
      const float t = float(k) / LINE_STEPS;
      const float2 tangent = bezier_tangent(p, t);
      if (j > 0 && k == 0) {
        /* The joint: one point, its direction between the two bones' there. */
        const float2 both = line.tangents.back() + tangent;
        line.tangents.back() = length(both) > 1e-9f ? normalize(both) : tangent;
        continue;
      }
      line.points.push_back(bezier(p, t));
      line.tangents.push_back(tangent);
    }
  }
  line.along.assign(line.points.size(), 0.0f);
  for (size_t k = 1; k < line.points.size(); k++) {
    line.along[k] = line.along[k - 1] + distance(line.points[k], line.points[k - 1]);
  }
  /* Point indices to how far along. */
  for (float &start : line.bone_starts) {
    start = line.along.empty() ? 0.0f : line.along[size_t(start)];
  }
  line.bone_starts.push_back(line.along.empty() ? 0.0f : line.along.back());
  return line;
}

namespace {
struct LinePlace {
  float2 at, tangent;
};
}  // namespace

/* The place `s` along the line, past either end carried on straight. */
static LinePlace line_place(const BoneCurveLine &line, float s)
{
  const size_t n = line.points.size();
  const float total = line.along.back();
  if (s <= 0.0f) {
    return {line.points.front() + line.tangents.front() * s, line.tangents.front()};
  }
  if (s >= total) {
    return {line.points.back() + line.tangents.back() * (s - total), line.tangents.back()};
  }
  const size_t i = std::min(size_t(std::upper_bound(line.along.begin(), line.along.end(), s) - line.along.begin()),
                            n - 1) -
                   1;
  const float span = line.along[i + 1] - line.along[i];
  const float u = span > 0.0f ? (s - line.along[i]) / span : 0.0f;
  const float2 t = lerp(line.tangents[i], line.tangents[i + 1], u);
  return {lerp(line.points[i], line.points[i + 1], u), length(t) > 1e-9f ? normalize(t) : line.tangents[i]};
}

/* How far along the line now a place `s` along it at rest is: as far along the same bone. */
static float line_remap(float s, const std::vector<float> &from, const std::vector<float> &to)
{
  if (s <= 0.0f || from.size() != to.size() || from.empty()) {
    return s;
  }
  const size_t m = from.size() - 1;
  if (s >= from[m]) {
    return to[m] + s - from[m];
  }
  size_t j = 0;
  while (j + 1 < m && from[j + 1] < s) {
    j++;
  }
  const float w = from[j + 1] - from[j];
  return to[j] + (w > 0.0f ? (s - from[j]) / w : 0.0f) * (to[j + 1] - to[j]);
}

Transform2D bone_curve_line_skin(const BoneCurveLine &rest, const BoneCurveLine &now, float2 q)
{
  if (rest.empty() || now.empty()) {
    return {};
  }
  /* Its nearest place on the rest line (the end pieces carried on past the ends). */
  const size_t m = rest.points.size();
  float best = 1e30f, s = 0.0f;
  for (size_t j = 0; j + 1 < m; j++) {
    const float2 a = rest.points[j], v = rest.points[j + 1] - a;
    const float vv = std::max(dot(v, v), 1e-18f);
    float u = dot(q - a, v) / vv;
    if (j > 0) {
      u = std::max(0.0f, u);
    }
    if (j + 2 < m) {
      u = std::min(1.0f, u);
    }
    const float d = distance(q, a + v * u);
    if (d < best) {
      best = d;
      s = rest.along[j] + u * std::sqrt(vv);
    }
  }
  const LinePlace was = line_place(rest, s);
  const float2 r = q - was.at;
  const float along = dot(r, was.tangent), across = dot(r, perpendicular(was.tangent));
  const LinePlace is = line_place(now, line_remap(s, rest.bone_starts, now.bone_starts));
  const float2 moved = is.at + is.tangent * along + perpendicular(is.tangent) * across;
  const float turn = std::atan2(cross(was.tangent, is.tangent), dot(was.tangent, is.tangent));
  return Transform2D::translate(moved) * Transform2D::rotate(turn) * Transform2D::translate(-q);
}

bool bone_curve_chain_reaches(const Layer &armature, uint64_t start, uint64_t end)
{
  int x = bone_index(armature, end);
  for (int guard = 0; x >= 0 && guard <= int(armature.bones.size()); guard++) {
    if (armature.bones[size_t(x)].id == start) {
      return true;
    }
    x = bone_curve_parent(armature, size_t(x));
  }
  return false;
}

std::vector<size_t> layer_curve_chain(const Layer &armature, const Layer &layer)
{
  if (!layer.points_follow_bone() || !layer.parent_bone_curve) {
    return {};
  }
  const int start = bone_index(armature, layer.parent_bone);
  if (start < 0 || !bone_curve_has(armature.bones[size_t(start)])) {
    return {};
  }
  std::vector<size_t> chain;
  int x = layer.parent_bone_chain_end != 0 ? bone_index(armature, layer.parent_bone_chain_end) : -1;
  for (int guard = 0; x >= 0 && guard <= int(armature.bones.size()); guard++) {
    chain.push_back(size_t(x));
    if (x == start) {
      std::reverse(chain.begin(), chain.end());
      return chain;
    }
    x = bone_curve_parent(armature, size_t(x));
  }
  return {size_t(start)};
}

/* --- Editing ------------------------------------------------------------------------------------------------ */

void bone_curve_handle_set(Layer &armature, const std::vector<BonePose> &poses, size_t i, bool head, float2 at,
                           bool alone)
{
  if (i >= armature.bones.size() || i >= poses.size() || !bone_curve_has(armature.bones[i])) {
    return;
  }
  const BoneCurveShape s = bone_curve_shape(armature, poses, i, false);
  if (s.length < 1e-9f) {
    return;
  }
  const float2 joint = head ? poses[i].head : poses[i].tail;
  const float2 w = head ? at - joint : joint - at;
  if (length(w) < 1e-12f) {
    /* On its joint: no direction to take, only the reach. */
    (head ? armature.bones[i].curve_head_reach
          : (s.kid >= 0 ? armature.bones[size_t(s.kid)].curve_parent_reach : armature.bones[i].curve_tail_reach)) =
        0.0f;
    return;
  }
  const float way = angle_of(w);
  const float dev = turn_clamp(wrap_angle(way - s.angle));
  const float reach = std::min(3.0f, length(w) / arc_reach(s.length, dev));
  Bone &b = armature.bones[i];
  if (head) {
    if (s.parent >= 0) {
      if (alone) {
        const float other = bone_curve_shape(armature, poses, size_t(s.parent), false).tail_turn;
        b.curve_parent_angle = other;
        b.curve_head_angle = dev;
        b.curve_lined = 0.0f;
      }
      else {
        b.curve_turn = wrap_angle(way - halfway(angle_of(way_of(poses, size_t(s.parent), false)), s.angle));
        b.curve_lined = 1.0f;
      }
    }
    else if (b.curve_lined < 0.5f) {
      b.curve_head_angle = dev;
      b.curve_lined = 0.0f;
    }
    else {
      b.curve_turn = wrap_angle(dev - s.head_mirror);
      b.curve_lined = 1.0f;
    }
    b.curve_head_reach = reach;
    return;
  }
  if (s.kid >= 0) {
    const float other = bone_curve_shape(armature, poses, size_t(s.kid), false).head_turn;
    Bone &k = armature.bones[size_t(s.kid)];
    if (alone) {
      k.curve_head_angle = other;
      k.curve_parent_angle = dev;
      k.curve_lined = 0.0f;
    }
    else {
      k.curve_turn = wrap_angle(way - halfway(s.angle, angle_of(way_of(poses, size_t(s.kid), false))));
      k.curve_lined = 1.0f;
    }
    k.curve_parent_reach = reach;
    return;
  }
  if (b.curve_tail_lined < 0.5f) {
    b.curve_tail_angle = dev;
    b.curve_tail_lined = 0.0f;
  }
  else {
    b.curve_tail_turn = wrap_angle(dev - s.tail_mirror);
    b.curve_tail_lined = 1.0f;
  }
  b.curve_tail_reach = reach;
}

void bone_curve_flatten(Layer &armature, const std::vector<BonePose> &poses, size_t i)
{
  if (i >= armature.bones.size() || !bone_curve_has(armature.bones[i])) {
    return;
  }
  const BoneCurveShape s = bone_curve_shape(armature, poses, i, false);
  /* The handles across its joints stay as they show. */
  const float parent_side = s.parent >= 0 ? bone_curve_shape(armature, poses, size_t(s.parent), false).tail_turn
                                          : 0.0f;
  const float kid_side = s.kid >= 0 ? bone_curve_shape(armature, poses, size_t(s.kid), false).head_turn : 0.0f;
  Bone &b = armature.bones[i];
  b.curve_lined = 0.0f;
  b.curve_head_angle = 0.0f;
  b.curve_parent_angle = parent_side;
  if (s.kid >= 0) {
    Bone &k = armature.bones[size_t(s.kid)];
    k.curve_lined = 0.0f;
    k.curve_head_angle = kid_side;
    k.curve_parent_angle = 0.0f;
  }
  else {
    b.curve_tail_lined = 0.0f;
    b.curve_tail_angle = 0.0f;
  }
}

void bone_curve_sharp_corner(Layer &armature, size_t i, bool head)
{
  if (i >= armature.bones.size() || !bone_curve_has(armature.bones[i])) {
    return;
  }
  Bone &b = armature.bones[i];
  if (head) {
    b.curve_lined = 0.0f;
    b.curve_head_angle = 0.0f;
    if (bone_curve_parent(armature, i) >= 0) {
      b.curve_parent_angle = 0.0f;
    }
    return;
  }
  const int kid = bone_curve_kid(armature, i);
  if (kid >= 0) {
    Bone &k = armature.bones[size_t(kid)];
    k.curve_lined = 0.0f;
    k.curve_head_angle = 0.0f;
    k.curve_parent_angle = 0.0f;
    return;
  }
  b.curve_tail_lined = 0.0f;
  b.curve_tail_angle = 0.0f;
}

void bone_curve_reset(Layer &armature, size_t i)
{
  if (i >= armature.bones.size()) {
    return;
  }
  bone_curve_values_reset(armature.bones[i]);
  const int kid = bone_curve_kid(armature, i);
  if (kid >= 0) {
    Bone &k = armature.bones[size_t(kid)];
    k.curve_turn = 0.0f;
    k.curve_lined = 1.0f;
    k.curve_head_angle = 0.0f;
    k.curve_parent_angle = 0.0f;
    k.curve_head_reach = 1.0f;
    k.curve_parent_reach = 1.0f;
  }
}

float2 bone_curve_handle_at(const Layer &armature, const std::vector<BonePose> &poses, size_t i, bool head)
{
  return bone_curve_controls(armature, poses, i, false)[head ? 1 : 2];
}

}  // namespace oanim
