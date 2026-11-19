#include "data/bones.hh"

#include <algorithm>
#include <atomic>
#include <functional>
#include <cmath>
#include <limits>
#include <map>
#include <mutex>
#include <numbers>
#include <set>

#include "anim/controller.hh"
#include "data/document.hh"

namespace oanim {

static const char *const CONSTRAINT_IDS[BONE_CONSTRAINT_TYPES] = {
    "LIMIT_ANGLE", "INDEPENDENT_ANGLE", "MAINTAIN_VOLUME", "COPY_ANGLE", "COPY_POSITION",
    "COPY_SCALE",  "TRACK_TO",          "STRETCH_TO",     "IK",         "DYNAMICS", "LIMIT_SHAPE",
    "CHILD_OF",    "LOOK_AT",           "FOLLOW_POINT",   "IK_END",     "IK_BASE"};
static const char *const CONSTRAINT_NAMES[BONE_CONSTRAINT_TYPES] = {
    "Limit Angle", "Independent Angle", "Maintain Volume", "Copy Angle", "Copy Position",
    "Copy Scale",  "Track To",          "Stretch To",       "IK",         "Dynamics", "Limit to Shape",
    "Child Of",    "Look At",           "Follow Point",     "IK End",     "IK Base"};

const char *bone_constraint_identifier(BoneConstraintType type)
{
  return CONSTRAINT_IDS[int(type)];
}

const char *bone_constraint_name(BoneConstraintType type)
{
  return CONSTRAINT_NAMES[int(type)];
}

bool bone_constraint_from_identifier(const std::string &identifier, BoneConstraintType *r_type)
{
  /* Moho's Squash & Stretch, before it became Maintain Volume. */
  if (identifier == "SQUASH_STRETCH") {
    *r_type = BoneConstraintType::MaintainVolume;
    return true;
  }
  for (int i = 0; i < BONE_CONSTRAINT_TYPES; i++) {
    if (identifier == CONSTRAINT_IDS[i]) {
      *r_type = BoneConstraintType(i);
      return true;
    }
  }
  return false;
}

/* The setup value is the one at frame 0: the frame-0 key when animated, else the value (or,
 * away from frame 0, the value from before an edit not yet keyed). */
template<typename T> static T setup_value(const Channel<T> &ch, const T &value, bool setup_frame)
{
  if (ch.animated()) {
    return ch.evaluate(0);
  }
  /* Unkeyed, the plain value is the setup, less what action bone actions add to it now (they move the
   * bone away from its setup, so its points follow; left in, the setup would move with it). */
  return (!setup_frame && ch.has_last ? ch.last : value) - ch.from_action_bones;
}

float2 bone_setup_position(const Bone &bone)
{
  return bone.setup_position;
}

float bone_setup_angle(const Bone &bone)
{
  return bone.setup_angle;
}

float2 bone_transform_from_position(const Bone &bone, float2 position)
{
  return rotate(position - bone.setup_position, -bone.setup_angle);
}

float2 bone_position_from_transform(const Bone &bone, float2 transform)
{
  return bone.setup_position + rotate(transform, bone.setup_angle);
}

void bone_changes_from_values(Bone &bone)
{
  /* Only what moved since bone_values_from_changes: setup + change - setup isn't always the change
   * to the last bit, and a value that differs from its last recorded one is an edit (a stray key). */
  if (bone.position != bone_position_from_transform(bone, bone.transform)) {
    bone.transform = bone_transform_from_position(bone, bone.position);
  }
  if (bone.angle != bone.setup_angle + bone.turn) {
    bone.turn = bone.angle - bone.setup_angle;
  }
}

void bone_values_from_changes(Bone &bone)
{
  bone.position = bone_position_from_transform(bone, bone.transform);
  bone.angle = bone.setup_angle + bone.turn;
}

void bone_take_setup(Bone &bone)
{
  /* What action bone actions add is a Transform (along the rest axes): off before the setup moves. */
  bone.setup_position = bone.position - rotate(bone.position_keys.from_action_bones, bone.setup_angle);
  bone.setup_angle = bone.angle - bone.angle_keys.from_action_bones;
  bone_changes_from_values(bone);
}

float2 bone_position_at(const Bone &bone, int frame, bool without_action_bones)
{
  if (bone.position_keys.animated()) {
    return bone_position_from_transform(bone, bone.position_keys.evaluate(std::max(0, frame)));
  }
  return without_action_bones ? bone.position - rotate(bone.position_keys.from_action_bones, bone.setup_angle)
                              : bone.position;
}

float bone_angle_at(const Bone &bone, int frame, bool without_action_bones)
{
  if (bone.angle_keys.animated()) {
    return bone.setup_angle + bone.angle_keys.evaluate(std::max(0, frame));
  }
  return without_action_bones ? bone.angle - bone.angle_keys.from_action_bones : bone.angle;
}

/* The bone's frame lays it along x: its Y scale (length) goes on x, its X (thickness) on y. */
static Transform2D bone_local(float2 position, float angle, float2 scale)
{
  return Transform2D::translate(position) * Transform2D::rotate(angle) * Transform2D::scaling({scale.y, scale.x});
}

/* Whether bone index `j` sits below the bone `ancestor_id` (or is it). */
static bool bone_is_descendant_in(const std::vector<Bone> &bones, const std::map<uint64_t, int> &index,
                                  uint64_t ancestor_id, int j)
{
  for (int at = j, guard = 0; at >= 0 && guard < 256; guard++) {
    if (bones[at].id == ancestor_id) {
      return true;
    }
    const auto it = index.find(bones[at].parent);
    at = it == index.end() ? -1 : it->second;
  }
  return false;
}

/* --- Limit to Shape ------------------------------------------------------------------------------ */

static bool polygon_inside(const std::vector<float2> &poly, float2 p)
{
  bool in = false;
  for (size_t i = 0, j = poly.size() - 1; i < poly.size(); j = i++) {
    const float2 a = poly[i], b = poly[j];
    if ((a.y > p.y) != (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) {
      in = !in;
    }
  }
  return in;
}

static float2 polygon_nearest(const std::vector<float2> &poly, float2 p)
{
  float2 best = poly.front();
  float best_d = 1e30f;
  for (size_t i = 0, j = poly.size() - 1; i < poly.size(); j = i++) {
    const float2 a = poly[j], ab = poly[i] - a;
    const float len2 = dot(ab, ab);
    const float t = len2 > 1e-20f ? std::clamp(dot(p - a, ab) / len2, 0.0f, 1.0f) : 0.0f;
    const float2 q = a + ab * t;
    const float d = dot(q - p, q - p);
    if (d < best_d) {
      best_d = d;
      best = q;
    }
  }
  return best;
}

/* Where the head can go nearest `head` with every point of the footprint around it inside the shape:
 * pushed back in by the point furthest out, a few times (a collision's way out), then, if that didn't
 * get there, the furthest along the way from the shape's middle that fits. */
static float2 shape_fit_head(const std::vector<float2> &region, const std::vector<float2> &footprint, float2 head)
{
  const auto fits = [&](float2 p) {
    for (const float2 o : footprint) {
      if (!polygon_inside(region, p + o)) {
        return false;
      }
    }
    return true;
  };
  if (fits(head)) {
    return head;
  }
  float2 p = head;
  for (int step = 0; step < 24; step++) {
    float2 push;
    float worst = 0.0f;
    for (const float2 o : footprint) {
      const float2 q = p + o;
      if (!polygon_inside(region, q)) {
        const float2 in = polygon_nearest(region, q) - q;
        if (dot(in, in) > worst) {
          worst = dot(in, in);
          push = in;
        }
      }
    }
    if (worst == 0.0f) {
      return p;
    }
    p += push * 1.001f;
  }
  if (fits(p)) {
    return p;
  }
  float2 middle;
  for (const float2 q : region) {
    middle += q;
  }
  middle = middle / float(region.size());
  if (!fits(middle)) {
    return middle;
  }
  float lo = 0.0f, hi = 1.0f;
  for (int step = 0; step < 24; step++) {
    const float t = (lo + hi) * 0.5f;
    (fits(middle + (head - middle) * t) ? lo : hi) = t;
  }
  return middle + (head - middle) * lo;
}

float2 bone_look_gaze(float face, float2 eye, float2 target, float target_depth)
{
  /* Along the face's axes (the bone layer's, turned as the head has turned in the picture), the target
   * stands `target_depth` in front. */
  const float2 d = rotate(target - eye, -face);
  const float z = std::max(target_depth, 1e-4f);
  return {std::atan2(d.x, z), std::atan2(d.y, std::sqrt(d.x * d.x + z * z))};
}

static std::atomic<long long> g_shape_fits{0};

long long bone_shape_fits_count()
{
  return g_shape_fits;
}

void bone_shape_fits_count_clear()
{
  g_shape_fits = 0;
}

float2 bone_shape_limit(const BoneConstraint &c, float2 head)
{
  if (c.shape_region.size() < 3) {
    return head;
  }
  /* What may go past the edge: the footprint shrunk by Overlap. Softness keeps it that much further in,
   * and lets it run on past there ever slower, never reaching the edge. */
  const float keep = 1.0f - std::clamp(c.overlap, 0.0f, 1.0f);
  const float soft = std::max(c.softness, 0.0f);
  std::vector<float2> footprint;
  for (const float2 o : c.shape_footprint) {
    footprint.push_back(o * keep);
  }
  if (footprint.empty()) {
    footprint.push_back(float2());
  }
  if (soft > 0.0f) {
    const std::vector<float2> base = footprint;
    footprint.clear();
    for (const float2 o : base) {
      for (int k = 0; k < 8; k++) {
        const float a = float(k) * PI / 4.0f;
        footprint.push_back(o + float2{std::cos(a), std::sin(a)} * soft);
      }
    }
  }
  /* One frame poses the rig many times over (each layer it bends asks), with the same shape, footprint and head
   * each time: the fit, up to fifty passes over every footprint point against every edge, done once. Kept by
   * exact inputs, so what it gives is what working it out gives. (A pupil too big for its eye took the slow way
   * every time: seconds a frame.) */
  struct Fit {
    std::vector<float2> region, footprint;
    float2 head, held;
  };
  thread_local std::vector<Fit> fits;
  float2 held;
  bool found = false;
  for (const Fit &f : fits) {
    if (f.head == head && f.footprint == footprint && f.region == c.shape_region) {
      held = f.held;
      found = true;
      break;
    }
  }
  if (!found) {
    g_shape_fits.fetch_add(1, std::memory_order_relaxed);
    held = shape_fit_head(c.shape_region, footprint, head);
    if (fits.size() >= 8) {
      fits.erase(fits.begin());
    }
    fits.push_back({c.shape_region, footprint, head, held});
  }
  if (soft <= 0.0f) {
    return held;
  }
  const float2 past = head - held;
  const float d = length(past);
  return d > 1e-9f ? held + past * (soft * std::tanh(d / soft) / d) : held;
}

void bone_shape_limit_affect(const Layer &armature, Bone &bone)
{
  if (armature.pose_frame == 0 || bone.position == bone_position_from_transform(bone, bone.transform)) {
    return;
  }
  for (const BoneConstraint &c : bone.constraints) {
    const float w = std::clamp(c.influence, 0.0f, 1.0f);
    if (c.type != BoneConstraintType::LimitShape || !c.enabled || !c.affect_transform || w <= 0.0f ||
        c.shape_region.size() < 3)
    {
      continue;
    }
    const std::vector<BonePose> poses = armature_keyed_pose(armature, false);
    const BonePose *parent = bone_pose_find(poses, bone.parent);
    const Transform2D up = parent ? parent->pose : bone_outer_frame(bone, false);
    const float2 head = up.apply(bone.position);
    bone.position = up.inverted().apply(head + (bone_shape_limit(c, head) - head) * w);
  }
}

namespace {

/* What a pose takes besides the bones' own values. */
struct PoseExtras {
  /* The frame shown (for constraints' delays). */
  int frame = 0;
  /* Where dynamics put bones (bone layer space), by id. */
  const std::map<uint64_t, BoneDynamicsState> *dynamics = nullptr;
  /* IK's turn (radians) and stretch for each bone, by index. */
  const std::vector<float> *ik_angle = nullptr;
  const std::vector<float> *ik_stretch = nullptr;
};

}  // namespace

static float transform_angle(const Transform2D &t)
{
  return std::atan2(t.b, t.a);
}

static float wrap_pi(float a)
{
  return a - 2.0f * PI * std::round(a / (2.0f * PI));
}

static float direction_angle(float2 v)
{
  return std::atan2(v.y, v.x);
}

/* A value at `frame`: its key there when animated, else the plain value. */
template<typename T> static T value_at(const Channel<T> &ch, const T &value, int frame)
{
  return ch.animated() ? ch.evaluate(std::max(0, frame)) : value;
}

static Transform2D bone_local_xy(float2 position, float angle, float sx, float sy)
{
  return Transform2D::translate(position) * Transform2D::rotate(angle) * Transform2D::scaling({sx, sy});
}

/* Where a bone's own axes hang from its parent (Relations, linear part): the parent's axes now, or, for
 * a bone that doesn't take all of its parent's change from the setup pose (its turn, its size), the
 * parent's setup axes changed by what it takes. The setup frame always hangs from the parent as it is. */
static Transform2D bone_parent_axes(const Bone &b, const Transform2D &parent_now, const Transform2D &parent_setup,
                                    bool setup_frame)
{
  const Transform2D now{parent_now.a, parent_now.b, parent_now.c, parent_now.d, 0.0f, 0.0f};
  if (setup_frame || (b.inherit_rotation && b.inherit_scale == InheritScale::Full)) {
    return now;
  }
  const Transform2D rest{parent_setup.a, parent_setup.b, parent_setup.c, parent_setup.d, 0.0f, 0.0f};
  const Transform2D change = now * rest.inverted();
  const float turn = transform_angle(change);
  Transform2D taken = change;
  if (b.inherit_scale == InheritScale::Uniform) {
    const float s = std::sqrt(std::abs(change.a * change.d - change.b * change.c));
    taken = Transform2D::rotate(turn) * Transform2D::scaling({s, s});
  }
  else if (b.inherit_scale == InheritScale::None) {
    taken = Transform2D::rotate(turn);
  }
  if (!b.inherit_rotation) {
    taken = Transform2D::rotate(-turn) * taken;
  }
  return taken * rest;
}

float bone_parent_axes_angle(const Bone &bone, const BonePose *parent, bool setup_frame)
{
  if (!parent) {
    return 0.0f;
  }
  return transform_angle(bone_parent_axes(bone, parent->pose, parent->setup, setup_frame));
}

/* The bone's frame from its own values (`local`, in its parent's space): its head where the parent takes
 * it, its axes as bone_parent_axes hangs them. */
static Transform2D bone_on_parent(const Bone &b, const Transform2D &parent_now, const Transform2D &parent_setup,
                                  const Transform2D &local, bool setup_frame)
{
  const Transform2D axes = bone_parent_axes(b, parent_now, parent_setup, setup_frame);
  Transform2D out = axes * Transform2D{local.a, local.b, local.c, local.d, 0.0f, 0.0f};
  const float2 head = parent_now.apply({local.tx, local.ty});
  out.tx = head.x;
  out.ty = head.y;
  return out;
}

/* Follow Point's change of shape, `w` of the way from none. */
static Transform2D follow_shape_part(const Transform2D &k, float w)
{
  return {1.0f + (k.a - 1.0f) * w, k.b * w, k.c * w, 1.0f + (k.d - 1.0f) * w, 0.0f, 0.0f};
}

static std::vector<BonePose> bones_pose(const std::vector<Bone> &bones, bool setup_frame, const PoseExtras &extras)
{
  const size_t n = bones.size();
  std::vector<BonePose> poses(n);
  std::map<uint64_t, int> index;
  for (int i = 0; i < int(n); i++) {
    index[bones[i].id] = i;
  }
  /* 0 not yet, 1 being worked out, 2 done. */
  std::vector<int> state(n, 0);
  const auto find = [&](uint64_t id) {
    const auto it = index.find(id);
    return it == index.end() ? -1 : it->second;
  };
  /* Parents first, whatever order the bones are stored in (a cycle stops at its root). */
  const auto solve = [&](auto &&self, int i, int depth) -> void {
    if (state[i] != 0) {
      return;
    }
    state[i] = 1;
    const Bone &bone = bones[i];
    Transform2D parent_setup, parent_pose;
    const int pi = find(bone.parent);
    if (pi >= 0 && pi != i && depth < 256) {
      self(self, pi, depth + 1);
      parent_setup = poses[pi].setup;
      /* Hanging from a controller's knob (the bone's own pose for any other parent). */
      parent_pose = bone.follow_knob ? poses[pi].knob : poses[pi].pose;
    }
    else if (bone.outer_bone != 0) {
      parent_setup = bone.outer_setup;
      parent_pose = bone_outer_frame(bone, setup_frame);
    }
    BonePose &p = poses[i];
    p.id = bone.id;
    const float2 setup_position = bone.setup_position;
    const float setup_angle = bone.setup_angle;
    const float2 setup_scale = setup_value(bone.scale_keys, bone.scale, false);
    float2 position = bone.position;
    float angle = bone.angle;
    float2 scale = bone.scale;
    float sx = 1.0f, sy = 1.0f;
    /* A controller stays where it rests, on its parent: only its knob moves (its position keys hold frames). */
    const bool rests = !setup_frame && bone_is_controller(bone);
    /* Its knob's own turn, as a pin's. */
    float knob_turn = rests ? bone.angle - setup_angle : 0.0f;
    if (rests) {
      position = setup_position;
      angle = setup_angle;
      scale = setup_scale;
    }
    if (rests && bone.controller_knob_independent) {
      /* Riding its Knob Parent, worked out first (one hanging from this knob can't be: it would carry itself). */
      const int ki = find(bone.controller_knob_parent);
      if (ki >= 0 && ki != i && state[ki] != 1 && !bone_is_descendant_in(bones, index, bone.id, ki)) {
        self(self, ki, depth + 1);
        if (state[ki] == 2) {
          p.knob_parent_skin = poses[ki].skin;
        }
      }
    }
    /* A controller's constraints (never while one of its actions is edited, so that keys a clean pose) work on its
     * knob, standing where it is: what places a bone moves the knob, what turns one turns the box. */
    const bool knob_pulled = rests && !bone.controller_knob_editing && controller_constrained(bone);
    BonePose rest_box;
    float2 knob_base;
    const float knob_size = std::max(bone.controller_frame_size, 1e-6f);
    if (knob_pulled) {
      rest_box.setup = parent_setup * bone_local(setup_position, setup_angle, setup_scale);
      rest_box.pose = bone_on_parent(bone, parent_pose, parent_setup,
                                     bone_local_xy(setup_position, setup_angle, setup_scale.y, setup_scale.x), false);
      rest_box.skin = rest_box.box_skin = rest_box.pose * rest_box.setup.inverted();
      rest_box.head = rest_box.pose.apply({0, 0});
      rest_box.setup_head = rest_box.setup.apply({0, 0});
      rest_box.knob_parent_skin = p.knob_parent_skin;
      knob_base = controller_knob_place(bone, rest_box);
      position = parent_pose.inverted().apply(controller_box_point(bone, rest_box, knob_base));
    }
    /* Where Look At looks from, and how far the face it is on has turned: a pupil where it is rigged on its parent; a
     * knob riding its Knob Parent where it rests on that, since the eye it moves in rides there, not with the box. */
    float2 look_from = parent_pose.apply(setup_position);
    float look_face = transform_angle(parent_pose) - transform_angle(parent_setup);
    if (knob_pulled && bone.controller_knob_independent) {
      look_from = p.knob_parent_skin.apply(rest_box.setup_head);
      look_face = transform_angle(p.knob_parent_skin);
    }
    if (!setup_frame && (!rests || knob_pulled)) {
      if (extras.ik_angle && !rests) {
        angle += (*extras.ik_angle)[i];
      }
      for (const BoneConstraint &c : bone.constraints) {
        const float w = std::clamp(c.influence, 0.0f, 1.0f);
        if (!c.enabled || w <= 0.0f || (rests && !controller_constraint_works(c.type))) {
          continue;
        }
        const int ti = find(c.target);
        const Bone *t = ti >= 0 && ti != i ? &bones[ti] : nullptr;
        const int then = extras.frame - c.delay;
        switch (c.type) {
          case BoneConstraintType::LimitAngle: {
            const float lo = std::min(c.min_angle, c.max_angle), hi = std::max(c.min_angle, c.max_angle);
            const float turn = angle - setup_angle;
            angle += (std::clamp(turn, lo, hi) - turn) * w;
            break;
          }
          case BoneConstraintType::IndependentAngle:
            angle -= wrap_pi(transform_angle(parent_pose) - transform_angle(parent_setup)) * w;
            break;
          case BoneConstraintType::CopyAngle:
            if (t) {
              const float now = c.delay > 0 ? bone_angle_at(*t, then, false) : t->angle;
              angle += (now - t->setup_angle) * c.factor * w;
            }
            break;
          case BoneConstraintType::CopyPosition:
            /* A controller rests: its position keys are its knob's frames, no move to follow. */
            if (t && c.follow_move && !bone_is_controller(*t)) {
              const float2 now = c.delay > 0 ? bone_position_at(*t, then, false) : t->position;
              position += (now - t->setup_position) * (c.factor * w);
            }
            else if (t && !bone_is_descendant_in(bones, index, bone.id, ti)) {
              /* To where the target's base is now (or `delay` frames ago, its parent as it is now). */
              self(self, ti, depth + 1);
              if (state[ti] == 2) {
                float2 goal = poses[ti].head;
                if (c.delay > 0) {
                  const int tp = find(t->parent);
                  const Transform2D up = tp >= 0 && state[tp] == 2 ? poses[tp].pose : Transform2D();
                  goal = up.apply(bone_position_at(*t, then, false));
                }
                position += (parent_pose.inverted().apply(goal) - position) * (c.factor * w);
              }
            }
            break;
          case BoneConstraintType::FollowPoint: {
            /* On top of what its parent gives it (anim/follow_point.hh). Three points always turn it; one or two as
             * Rotation says (one turns as the shape does there). */
            const float turn = c.follow_rotation || c.follow_three ? c.follow_turn * w : 0.0f;
            const float grow = c.follow_two && !c.follow_three && c.follow_scale &&
                                       c.follow_scale_mode == FollowScaleMode::Uniform ?
                                   1.0f + (c.follow_stretch - 1.0f) * w :
                                   1.0f;
            /* The turn, scale and change of shape go round the first point where it rested, as Harmony's do round its
             * first pivot: a head away from it swings round it. The bone itself turns and scales round its head (the
             * shape last, below), so the head is carried here. */
            const Transform2D change = follow_shape_part(c.follow_shape, w) * Transform2D::rotate(turn) *
                                       Transform2D{grow, 0.0f, 0.0f, grow, 0.0f, 0.0f};
            const float2 around = parent_pose.apply(position) - c.follow_pivot;
            position += parent_pose.inverted().apply_vector(c.follow_offset * w + change.apply_vector(around) - around);
            angle += turn;
            scale = scale * grow;
            break;
          }
          case BoneConstraintType::ChildOf:
            if (t && !bone_is_descendant_in(bones, index, bone.id, ti)) {
              /* The target's change from its setup, carrying the bone as a parent would. */
              self(self, ti, depth + 1);
              if (state[ti] == 2) {
                const Transform2D &skin = poses[ti].skin;
                if (c.child_position) {
                  const float2 head = parent_pose.apply(position);
                  position += (parent_pose.inverted().apply(skin.apply(head)) - position) * w;
                }
                if (c.child_rotation) {
                  angle += transform_angle(skin) * w;
                }
                if (c.child_scale) {
                  const float s = std::sqrt(std::abs(skin.a * skin.d - skin.b * skin.c));
                  scale = scale * (1.0f + (s - 1.0f) * w);
                }
              }
            }
            break;
          case BoneConstraintType::LookAt:
            if (rests && (c.look_reach.x <= 0.0f || c.shape_region.size() < 3)) {
              /* A controller with no Eye Shape: its box is the eye, looking all the way to a side takes the knob to
               * that side's edge. With one, the knob looks as any pupil does (below). */
              if (t && !bone_is_descendant_in(bones, index, bone.id, ti)) {
                self(self, ti, depth + 1);
                if (state[ti] == 2) {
                  const float face = look_face;
                  const float2 gaze = bone_look_gaze(face, look_from, poses[ti].head, t->depth);
                  const float2 rest_gaze = bone_look_gaze(0.0f, parent_setup.apply(setup_position), poses[ti].setup_head,
                                                          setup_value(t->depth_keys, t->depth, setup_frame));
                  const float half_turn = 1.5707964f;
                  const float2 look = gaze - rest_gaze;
                  const float2 turn = {std::clamp(look.x, -half_turn, half_turn), std::clamp(look.y, -half_turn, half_turn)};
                  /* The look in the box's own frame (it turns with the face), out to its edges. */
                  const float2 along = rotate(rest_box.box_skin.inverted().apply_vector(
                                                  rotate(float2{std::sin(turn.x) * std::cos(turn.y), std::sin(turn.y)}, face)),
                                              -bone.controller_box_angle);
                  float2 lo, hi;
                  controller_box(bone, lo, hi);
                  const float2 frames = {along.x * (along.x >= 0.0f ? hi.x : -lo.x), along.y * (along.y >= 0.0f ? hi.y : -lo.y)};
                  position += parent_pose.inverted().apply_vector(
                      rest_box.box_skin.apply_vector(rotate(frames * (knob_size * w), bone.controller_box_angle)));
                }
              }
              break;
            }
            if (t && c.look_reach.x > 0.0f && c.shape_region.size() >= 3 && !bone_is_descendant_in(bones, index, bone.id, ti)) {
              self(self, ti, depth + 1);
              if (state[ti] == 2) {
                /* The eye a (stretched) ball as big as its Eye Shape, turning by how much the look at the
                 * target has turned from its rest (target where it rests, at its setup Depth: the eye looks
                 * as drawn), never past the side of the ball. The pupil a disc on the ball where it points,
                 * seen from the front: slid across, as drawn. */
                const float face = look_face;
                /* The pupil where it is rigged, carried by the eye's parent, and its own keys' move on top:
                 * they move the pupil on the ball, not the ball. */
                const float2 rigged = parent_pose.apply(bone.setup_position);
                const float2 keyed = parent_pose.apply_vector(position - bone.setup_position);
                const float2 gaze = bone_look_gaze(face, look_from, poses[ti].head, t->depth);
                const float2 rest_gaze = bone_look_gaze(0.0f, parent_setup.apply(bone.setup_position), poses[ti].setup_head,
                                                        setup_value(t->depth_keys, t->depth, setup_frame));
                const float half_turn = 1.5707964f;
                const float2 look = gaze - rest_gaze;
                const float2 turn = {std::clamp(look.x, -half_turn, half_turn), std::clamp(look.y, -half_turn, half_turn)};
                const float2 shift = rotate(
                    float2{c.look_reach.x * std::sin(turn.x) * std::cos(turn.y), c.look_reach.y * std::sin(turn.y)}, face);
                /* Where the pupil is (its own keys too) stays inside: Center its head, Whole Drawing what it
                 * carries about its head. */
                const float2 tested = rigged + keyed;
                position += parent_pose.inverted().apply_vector(bone_shape_limit(c, tested + shift) - tested) * w;
              }
            }
            break;
          case BoneConstraintType::CopyScale:
            if (t) {
              const float2 now = c.delay > 0 ? value_at(t->scale_keys, t->scale, then) : t->scale;
              const float2 base = setup_value(t->scale_keys, t->scale, false);
              if (std::abs(base.x) > 1e-6f) {
                scale.x *= 1.0f + (now.x / base.x - 1.0f) * c.factor * w;
              }
              if (std::abs(base.y) > 1e-6f) {
                scale.y *= 1.0f + (now.y / base.y - 1.0f) * c.factor * w;
              }
            }
            break;
          default:
            break;
        }
      }
      /* Dynamics: where the simulation has the bone, in place of where the keys and the constraints
       * above put it. Dynamics is last in the stack, so those shape what it aims at (a Limit Angle
       * limits the aim) but don't hold its swing, which can overshoot them. */
      if (extras.dynamics) {
        if (const auto it = extras.dynamics->find(bone.id); it != extras.dynamics->end()) {
          const BoneDynamicsState &d = it->second;
          if (d.angle_on && rests) {
            /* A controller's box rests: the swing turns its knob, as its keys do. */
            knob_turn += wrap_pi(d.angle - transform_angle(parent_pose) - angle);
          }
          else if (d.angle_on) {
            angle = d.angle - transform_angle(parent_pose);
          }
          if (d.position_on) {
            position = parent_pose.inverted().apply(d.head);
          }
          if (d.scale_on) {
            scale.y = d.scale;
          }
        }
      }
      /* Limit to Shape, after Dynamics too: wherever the keys, constraints or a jiggle put the head, it
       * stays inside its shape. */
      for (const BoneConstraint &c : bone.constraints) {
        const float w = std::clamp(c.influence, 0.0f, 1.0f);
        if (c.type != BoneConstraintType::LimitShape || !c.enabled || w <= 0.0f || c.shape_region.size() < 3) {
          continue;
        }
        const float2 head = parent_pose.apply(position);
        position = parent_pose.inverted().apply(head + (bone_shape_limit(c, head) - head) * w);
      }
      if (extras.ik_stretch && !rests) {
        sx *= (*extras.ik_stretch)[i];
      }
      if (knob_pulled) {
        /* Where they have the knob, as frames against the box at rest; the box itself stays (turned, maybe). */
        p.knob_pull = rotate(rest_box.box_skin.inverted().apply_vector(parent_pose.apply(position) - rest_box.head),
                             -bone.controller_box_angle) / knob_size -
                      knob_base;
        position = setup_position;
      }
    }
    p.pose = bone_on_parent(bone, parent_pose, parent_setup, bone_local_xy(position, angle, scale.y * sx, scale.x * sy), setup_frame);
    if (!setup_frame) {
      /* Pointing at another bone: after the rest, from where this bone has ended up. */
      for (const BoneConstraint &c : bone.constraints) {
        const float w = std::clamp(c.influence, 0.0f, 1.0f);
        const bool aims = c.type == BoneConstraintType::TrackTo || c.type == BoneConstraintType::StretchTo;
        const int ti = find(c.target);
        if (!aims || !c.enabled || w <= 0.0f || ti < 0 || ti == i || state[ti] == 1 ||
            (rests && (c.type == BoneConstraintType::StretchTo || bone.controller_knob_editing)) ||
            bone_is_descendant_in(bones, index, bone.id, ti))
        {
          continue;
        }
        self(self, ti, depth + 1);
        const float2 head = p.pose.apply({0, 0});
        const float2 goal = poses[ti].head;
        if (distance(head, goal) < 1e-7f) {
          continue;
        }
        angle += wrap_pi(direction_angle(goal - head) - transform_angle(p.pose)) * w;
        p.pose = bone_on_parent(bone, parent_pose, parent_setup, bone_local_xy(position, angle, scale.y * sx, scale.x * sy), setup_frame);
        if (c.type == BoneConstraintType::StretchTo) {
          const float reach = distance(p.pose.apply({bone.length, 0}), head);
          if (reach > 1e-7f) {
            sx *= 1.0f + (distance(goal, head) / reach - 1.0f) * w;
            p.pose = bone_on_parent(bone, parent_pose, parent_setup, bone_local_xy(position, angle, scale.y * sx, scale.x * sy), setup_frame);
          }
        }
      }
      /* Maintain Volume, last: the width follows the length however it got there, in place of
       * the bone's own X scale (at full amount), so the bone keeps its area. */
      for (const BoneConstraint &c : bone.constraints) {
        const float w = std::clamp(c.influence, 0.0f, 1.0f);
        if (c.type != BoneConstraintType::MaintainVolume || !c.enabled || w <= 0.0f || rests) {
          continue;
        }
        const float along = std::abs(setup_scale.y) > 1e-6f ? std::abs(scale.y * sx / setup_scale.y) : 1.0f;
        const float across = std::abs(setup_scale.x) > 1e-6f ? std::abs(scale.x / setup_scale.x) : 1.0f;
        if (along > 1e-6f && across > 1e-6f) {
          const float a = std::max(c.amount, 0.0f) * w;
          sy *= std::pow(across, -a) * std::pow(along, -a);
          p.pose = bone_on_parent(bone, parent_pose, parent_setup, bone_local_xy(position, angle, scale.y * sx, scale.x * sy), setup_frame);
        }
      }
    }
    /* Follow Point's change of shape (Along Line's stretch, three points' skew), last, around the head: a bone's own
     * move, turn and scale can't hold it, so what it carries takes it from its pose. */
    if (!setup_frame && !rests) {
      for (const BoneConstraint &c : bone.constraints) {
        const float w = std::clamp(c.influence, 0.0f, 1.0f);
        if (c.type != BoneConstraintType::FollowPoint || !c.enabled || w <= 0.0f || c.follow_shape == Transform2D()) {
          continue;
        }
        const float2 head = p.pose.apply({0, 0});
        p.pose = Transform2D::translate(head) * follow_shape_part(c.follow_shape, w) * Transform2D::translate(-head) *
                 p.pose;
      }
    }
    /* On frame 0 the bones are the setup pose, even mid-drag before the edit is recorded:
     * moving one there rigs, it doesn't move the artwork. */
    p.setup = setup_frame ? p.pose : parent_setup * bone_local(setup_position, setup_angle, setup_scale);
    p.skin = p.pose * p.setup.inverted();
    p.box_skin = p.skin;
    p.knob = p.pose;
    p.setup_head = p.setup.apply({0, 0});
    p.setup_tail = p.setup.apply({bone.length, 0});
    p.head = p.pose.apply({0, 0});
    p.tail = p.pose.apply({bone.length, 0});
    if (rests) {
      /* The knob moves and turns what hangs from it, as a pin would: the box stays. */
      float2 frames = bone.controller_knob_editing ? bone.controller_knob_edit_at :
                      bone.controller_contain_knob ? controller_knob_held(bone, p) :
                                                     controller_knob_place(bone, p);
      /* Moved in its side's own action and not yet keyed: where it is going. */
      if (bone.controller_knob_edit_side >= 0 && bone.position_keys.has_last) {
        const float2 now = controller_knob(bone), was = controller_frames_of(bone, bone.position_keys.last);
        if (std::hypot(now.x - was.x, now.y - was.y) > 1e-5f) {
          frames = controller_side_only(bone.controller_knob_edit_side, now);
        }
      }
      const float2 at = controller_box_point(bone, p, frames);
      /* Independent, it doesn't turn with the box either: with its Knob Parent, or as it rests. */
      const Transform2D carried = p.knob_parent_skin * p.setup;
      p.knob = bone.controller_knob_independent ?
                   Transform2D::translate(at - carried.apply({0, 0})) * carried * Transform2D::rotate(knob_turn) :
                   Transform2D::translate(at - p.head) * p.pose * Transform2D::rotate(knob_turn);
      p.skin = p.knob * p.setup.inverted();
    }
    state[i] = 2;
  };
  for (int i = 0; i < int(n); i++) {
    solve(solve, i, 0);
  }
  return poses;
}

/* Bones from `i` up its parents that an IK chain turns: up to `limit` bones (0: no limit), not
 * past a bone Ignored by IK. */
static std::vector<int> ik_chain(const std::vector<Bone> &bones, const std::map<uint64_t, int> &index, int i,
                                 int limit)
{
  std::vector<int> chain;
  for (int at = i, guard = 0; at >= 0 && guard < 256; guard++) {
    /* A pin has no length to turn toward the goal. */
    if (bones[at].ik_ignore || bones[at].type == BoneType::Pin || bones[at].type == BoneType::Controller2D ||
        (limit > 0 && int(chain.size()) >= limit))
    {
      break;
    }
    chain.push_back(at);
    const auto it = index.find(bones[at].parent);
    at = it == index.end() ? -1 : it->second;
  }
  return chain;
}

/* The axes a chain's base turns in (bone layer space, linear part): its parent's, as bone_on_parent hangs it from
 * them, an outer bone's for a bone group's root. */
static Transform2D ik_axes(const std::vector<Bone> &bones, const std::map<uint64_t, int> &index,
                           const std::vector<BonePose> &poses, int base)
{
  const Bone &b = bones[base];
  if (const auto it = index.find(b.parent); it != index.end() && it->second != base) {
    const BonePose &p = poses[it->second];
    return bone_parent_axes(b, b.follow_knob ? p.knob : p.pose, p.setup, false);
  }
  if (b.outer_bone != 0) {
    return bone_parent_axes(b, bone_outer_frame(b, false), b.outer_setup, false);
  }
  return Transform2D();
}

/* Turns a chain's bones so its last bone's tip reaches `goal`: cyclic coordinate descent, or, for
 * an arc, the even bend (with a turn at its base) that comes closest. `turn(j, radians)` turns
 * bone j and gives back how far it turned (less where a limit holds it); `pose()` works the bones out again; `tip()`
 * and `head(j)` read them. `axes`: what ik_axes gives for the chain's base. */
static void ik_solve(const std::vector<int> &chain, float2 goal_at, bool arc, const Transform2D &axes,
                     const std::function<float(int, float)> &turn, const std::function<void()> &pose,
                     const std::function<float2()> &tip_at, const std::function<float2(int)> &head_at)
{
  if (chain.empty()) {
    return;
  }
  /* Worked out in the base's parent's axes, where turning a bone turns it (and what hangs from it) as much: under a
   * parent flipped, or stretched one way, a turn in the layer goes the other way or bends (the chain missed, its
   * joint swung to the other side). */
  Transform2D to_axes;
  if (const float det = axes.a * axes.d - axes.b * axes.c; std::abs(det) > 1e-12f) {
    to_axes = Transform2D{axes.a, axes.b, axes.c, axes.d, 0.0f, 0.0f}.inverted();
  }
  const float2 goal = to_axes.apply(goal_at);
  const auto tip = [&] { return to_axes.apply(tip_at()); };
  const auto head = [&](int j) { return to_axes.apply(head_at(j)); };
  /* How the chain bends now, from its base to its tip: the turns from each bone to the next, added up (positive to
   * the left). A solve keeps this side, as a knee keeps bending the way it rests. */
  const auto bent_now = [&] {
    float sum = 0.0f;
    for (size_t k = chain.size(); k-- > 0;) {
      const float2 from = head(chain[k]);
      const float2 to = k > 0 ? head(chain[k - 1]) : tip();
      const float2 next = k > 1 ? head(chain[k - 2]) : tip();
      if (k > 0 && distance(to, from) > 1e-7f && distance(next, to) > 1e-7f) {
        sum += wrap_pi(direction_angle(next - to) - direction_angle(to - from));
      }
    }
    return sum;
  };
  const float rest_bend = bent_now();
  if (!arc && chain.size() == 2) {
    /* Two bones: the triangle their lengths and the goal make, solved outright, the joint on the side it bends
     * to now (stepping toward the goal one bone at a time ran out of steps on a deep bend, or swung the joint
     * through to the other side). Straight, it has no side: the steps below find one. */
    const int base = chain[1], end = chain[0];
    const float2 h = head(base), j = head(end);
    const float l1 = distance(j, h), l2 = distance(tip(), j);
    const float d = std::clamp(distance(goal, h), std::abs(l1 - l2), l1 + l2);
    if (l1 > 1e-7f && l2 > 1e-7f && d > 1e-7f && std::abs(rest_bend) > 1e-6f) {
      const float at_base = std::acos(std::clamp((l1 * l1 + d * d - l2 * l2) / (2.0f * l1 * d), -1.0f, 1.0f));
      const float want = direction_angle(goal - h) - (rest_bend > 0.0f ? at_base : -at_base);
      turn(base, wrap_pi(want - direction_angle(j - h)));
      pose();
      const float2 j2 = head(end);
      turn(end, wrap_pi(direction_angle(goal - j2) - direction_angle(tip() - j2)));
      pose();
    }
  }
  if (!arc || chain.size() < 2) {
    /* Stepping toward the goal one bone at a time, first on the chain as it stands (its heads and tip, each turn
     * carrying what hangs from the bone rigidly), until it reaches: as many steps as that takes cost little there,
     * where on the bones 24 left a long chain short of a goal in reach. Then the turns go on the bones, and steps on
     * the bones themselves take up what isn't rigid (a bone stretched one way, a limit). */
    if (const size_t n = chain.size(); distance(tip(), goal) > 1e-5f) {
      /* The chain as each bone's way and length (from its head to the next head, the last to the tip), in doubles and
       * worked out from its base each step: rotating points over and over stretched it a hair each time, enough over
       * thousands of steps to miss near full stretch. */
      std::vector<double> way(n), length(n), heads_x(n), heads_y(n);
      const float2 root = head(chain[n - 1]);
      for (size_t k = 0; k < n; k++) {
        const float2 v = (k > 0 ? head(chain[k - 1]) : tip()) - head(chain[k]);
        way[k] = std::atan2(double(v.y), double(v.x));
        length[k] = std::hypot(double(v.x), double(v.y));
      }
      const std::vector<double> way_from = way;
      double end_x = 0.0, end_y = 0.0;
      const auto place = [&] {
        double x = root.x, y = root.y;
        for (size_t k = n; k-- > 0;) {
          heads_x[k] = x;
          heads_y[k] = y;
          x += length[k] * std::cos(way[k]);
          y += length[k] * std::sin(way[k]);
        }
        end_x = x;
        end_y = y;
      };
      place();
      const double gx = goal.x, gy = goal.y;
      /* Three bones or more, resting bent: every joint's turn from the bone before it scaled alike, bent more or
       * straightened the least that reaches, then turned at the base to face the goal. One shape for each reach, so a
       * goal moving smoothly bends the chain smoothly, each joint the way it rests (stepped from the rest each frame,
       * it could flip to its mirror zig-zag between two frames). A goal nearer than that shape folds reaches is
       * stepped toward from it below. */
      std::vector<double> rest(n, 0.0);
      double most = 0.0;
      for (size_t k = 0; k + 1 < n; k++) {
        rest[k] = std::remainder(way[k] - way[k + 1], 2.0 * std::numbers::pi);
        most = std::max(most, std::abs(rest[k]));
      }
      if (n >= 3 && most > 1e-4) {
        const double want = std::hypot(gx - root.x, gy - root.y);
        const auto bend = [&](double s) {
          for (size_t k = n - 1; k-- > 0;) {
            way[k] = way[k + 1] + s * rest[k];
          }
          place();
          return std::hypot(end_x - root.x, end_y - root.y);
        };
        /* Up to half a turn at the joint bent most. */
        const double top = std::numbers::pi / most;
        double lo = 0.0, hi = -1.0, nearest = 0.0, nearest_miss = std::numeric_limits<double>::max();
        if (bend(0.0) > want) {
          for (int i = 1; i <= 256 && hi < 0.0; i++) {
            const double s = top * i / 256.0;
            const double reach = bend(s);
            if (std::abs(reach - want) < nearest_miss) {
              nearest_miss = std::abs(reach - want);
              nearest = s;
            }
            if (reach <= want) {
              hi = s;
            }
            else {
              lo = s;
            }
          }
        }
        double s = 0.0;
        if (hi >= 0.0) {
          for (int i = 0; i < 60; i++) {
            const double mid = 0.5 * (lo + hi);
            (bend(mid) > want ? lo : hi) = mid;
          }
          s = hi;
        }
        else if (bend(0.0) > want) {
          s = nearest;
        }
        bend(s);
        const double face = std::remainder(std::atan2(gy - root.y, gx - root.x) - std::atan2(end_y - root.y, end_x - root.x),
                                           2.0 * std::numbers::pi);
        for (double &w : way) {
          w += face;
        }
        place();
      }
      /* Until it reaches, or a pass gains nothing (out of reach, it points at the goal after a few). */
      double was = std::hypot(end_x - gx, end_y - gy);
      for (int iteration = 0; iteration < 2000 && was > 1e-7; iteration++) {
        for (size_t k = 0; k < n; k++) {
          const double hx = heads_x[k], hy = heads_y[k];
          if (std::hypot(end_x - hx, end_y - hy) < 1e-9 || std::hypot(gx - hx, gy - hy) < 1e-9) {
            continue;
          }
          const double a = std::remainder(std::atan2(gy - hy, gx - hx) - std::atan2(end_y - hy, end_x - hx),
                                          2.0 * std::numbers::pi);
          for (size_t m = 0; m <= k; m++) {
            way[m] += a;
          }
          place();
        }
        const double now = std::hypot(end_x - gx, end_y - gy);
        if (was - now < 1e-12) {
          break;
        }
        was = now;
      }
      /* Each bone turned by how far its way swung, less its parent's. */
      for (size_t k = 0; k < n; k++) {
        const double t = (way[k] - way_from[k]) - (k + 1 < n ? way[k + 1] - way_from[k + 1] : 0.0);
        if (const float d = wrap_pi(float(std::remainder(t, 2.0 * std::numbers::pi))); d != 0.0f) {
          turn(chain[k], d);
        }
      }
      pose();
    }
    for (int iteration = 0; iteration < 24 && distance(tip(), goal) > 1e-5f; iteration++) {
      for (const int j : chain) {
        const float2 h = head(j);
        const float2 e = tip();
        if (distance(e, h) < 1e-7f || distance(goal, h) < 1e-7f) {
          continue;
        }
        turn(j, wrap_pi(direction_angle(goal - h) - direction_angle(e - h)));
        pose();
      }
    }
    return;
  }
  /* The arc: every bone bends by the same k; the base turns the whole chain to face the goal. */
  const int base = chain.back();
  /* How far each bone has bent so far: a limit can hold one short of what it was asked (counted as asked, the
   * search read poses other than the ones it meant, and Auto IK missed inside the limits). */
  std::vector<float> bent(chain.size(), 0.0f);
  const auto bend = [&](float k) {
    for (size_t m = 0; m < chain.size(); m++) {
      if (chain[m] != base) {
        bent[m] += turn(chain[m], k - bent[m]);
      }
    }
    pose();
  };
  const auto miss = [&](float k) {
    bend(k);
    const float2 h = head(base);
    return std::abs(distance(tip(), h) - distance(goal, h));
  };
  /* The best bend each way (bending less than now, and more, up to half a turn: a deep knee bends further than a
   * quarter), each found coarsely and then finely. */
  const auto search = [&](float lo, float hi) {
    float best = 0.0f, best_miss = miss(0.0f);
    for (float k = lo; k <= hi + 1e-6f; k += 0.02f) {
      if (const float m = miss(k); m < best_miss) {
        best_miss = m;
        best = k;
      }
    }
    for (float k = best - 0.02f; k <= best + 0.02f; k += 0.0005f) {
      if (const float m = miss(k); m < best_miss) {
        best_miss = m;
        best = k;
      }
    }
    return std::pair(best, best_miss);
  };
  const auto [less, less_miss] = search(-3.1f, 0.0f);
  const auto [more, more_miss] = search(0.0f, 3.1f);
  float best = less_miss <= more_miss ? less : more;
  /* Of the two even bends that reach as far, the one curving the same way as the rest. */
  float length = 0.0f;
  for (size_t k = 0; k < chain.size(); k++) {
    length += distance(k > 0 ? head(chain[k - 1]) : tip(), head(chain[k]));
  }
  if (std::abs(rest_bend) > 1e-6f && std::abs(less_miss - more_miss) <= 1e-3f * std::max(length, 1e-6f)) {
    bend(less);
    const bool less_keeps = (bent_now() > 0.0f) == (rest_bend > 0.0f);
    bend(more);
    const bool more_keeps = (bent_now() > 0.0f) == (rest_bend > 0.0f);
    if (less_keeps != more_keeps) {
      best = less_keeps ? less : more;
    }
  }
  bend(best);
  const float2 h = head(base);
  turn(base, wrap_pi(direction_angle(goal - h) - direction_angle(tip() - h)));
  pose();
}

const BoneConstraint *bone_ik_end(const Bone &bone)
{
  for (const BoneConstraint &c : bone.constraints) {
    if (c.type == BoneConstraintType::IKEnd && c.enabled) {
      return &c;
    }
  }
  return nullptr;
}

const BoneConstraint *bone_ik_base(const Bone &bone)
{
  for (const BoneConstraint &c : bone.constraints) {
    if (c.type == BoneConstraintType::IKBase && c.enabled) {
      return &c;
    }
  }
  return nullptr;
}

/* The bone whose tail an IK End or IK Base on bone `i` puts its point at: the bone itself, or with Head its parent
 * (-1: none, a root's head). */
static int ik_point_bone(const std::vector<Bone> &bones, const std::map<uint64_t, int> &index, int i, bool head)
{
  if (!head) {
    return i;
  }
  const auto it = index.find(bones[i].parent);
  return it == index.end() || it->second == i ? -1 : it->second;
}

/* An IK End's or IK Base's chain, its point's bone first: up through the parents to the nearest IK Base (a base at the
 * head of a bone the chain is connected to takes that bone in, so a hip turns with its spine), not past a bone Ignored
 * by IK, a pin or a controller. */
static std::vector<int> ik_point_chain(const std::vector<Bone> &bones, const std::map<uint64_t, int> &index, int e)
{
  std::vector<int> chain;
  for (int b = e, guard = 0; b >= 0 && guard < 256; guard++) {
    const Bone &bone = bones[b];
    if (bone.ik_ignore || bone.type == BoneType::Pin || bone.type == BoneType::Controller2D) {
      break;
    }
    chain.push_back(b);
    const auto it = index.find(bone.parent);
    if (it == index.end() || it->second == b) {
      break;
    }
    const int p = it->second;
    if (const BoneConstraint *base = bone_ik_base(bones[p])) {
      if (base->ik_head && bone.connected && !bone_ik_end(bones[p]) && !bones[p].ik_ignore) {
        chain.push_back(p);
      }
      break;
    }
    b = p;
  }
  return chain;
}

static std::map<uint64_t, int> bones_index(const std::vector<Bone> &bones)
{
  std::map<uint64_t, int> index;
  for (int i = 0; i < int(bones.size()); i++) {
    index[bones[i].id] = i;
  }
  return index;
}

std::vector<size_t> armature_ik_chain(const Layer &armature, size_t i, BoneConstraintType type)
{
  std::vector<size_t> out;
  if (i >= armature.bones.size()) {
    return out;
  }
  const Bone &b = armature.bones[i];
  const BoneConstraint *c = type == BoneConstraintType::IKEnd ? bone_ik_end(b) : bone_ik_base(b);
  if (!c) {
    return out;
  }
  const std::map<uint64_t, int> index = bones_index(armature.bones);
  const int e = ik_point_bone(armature.bones, index, int(i), c->ik_head);
  if (e < 0) {
    return out;
  }
  for (const int j : ik_point_chain(armature.bones, index, e)) {
    out.push_back(size_t(j));
  }
  return out;
}

int armature_ik_point_bone(const Layer &armature, size_t i, bool head)
{
  if (i >= armature.bones.size()) {
    return -1;
  }
  return ik_point_bone(armature.bones, bones_index(armature.bones), int(i), head);
}

/* The frames a pinned point's stretches run between: the setup frame, its Pinned To keys and every key of the bones its
 * chain turns (so a point pinned with no keys stays where the setup frame has it). */
static std::vector<int> ik_pin_frames(const std::vector<Bone> &bones, const std::vector<int> &chain,
                                      const BoneConstraint &c)
{
  std::set<int> frames = {0};
  const auto add = [&](const auto &ch) {
    for (const auto &k : ch.keys) {
      frames.insert(k.frame);
    }
  };
  add(c.pin_keys);
  for (const int j : chain) {
    add(bones[j].position_keys);
    add(bones[j].angle_keys);
    add(bones[j].scale_keys);
  }
  return {frames.begin(), frames.end()};
}

/* How far along a stretch from key frame `k0` to `k1` frame `f` is, as the point's chain eases there: straight with
 * Linear keys, held with Step, else easing in and out. */
static float ik_pin_progress(const Bone &end, int k0, int k1, int f)
{
  const float u = k1 > k0 ? std::clamp(float(f - k0) / float(k1 - k0), 0.0f, 1.0f) : 0.0f;
  Interp interp = Interp::Smooth;
  for (const auto &k : end.angle_keys.keys) {
    if (k.frame == k0) {
      interp = k.interp;
    }
  }
  if (interp == Interp::Linear) {
    return u;
  }
  if (interp == Interp::Step) {
    return 0.0f;
  }
  return u * u * (3.0f - 2.0f * u);
}

float2 ik_bend_on(const BoneConstraint &c, int k0)
{
  for (const Key<float2> &k : c.bend_keys.keys) {
    if (k.frame == k0) {
      return k.value;
    }
  }
  return {};
}

/* The whole pose of some bones: constraints, dynamics and IK targets included. */
static std::vector<BonePose> bones_full_pose(const std::vector<Bone> &bones, bool setup_frame, int frame,
                                             const std::map<uint64_t, BoneDynamicsState> *dynamics, bool with_pins = true)
{
  struct {
    const std::vector<Bone> &bones;
  } armature{bones};
  PoseExtras extras;
  extras.frame = frame;
  extras.dynamics = dynamics;
  std::vector<BonePose> poses = bones_pose(armature.bones, setup_frame, extras);
  if (setup_frame) {
    return poses;
  }
  (void)frame;
  /* IK targets: the chains are turned (and stretched) after everything else. */
  const size_t n = armature.bones.size();
  std::map<uint64_t, int> index;
  for (int i = 0; i < int(n); i++) {
    index[armature.bones[i].id] = i;
  }
  std::vector<float> ik_angle(n, 0.0f), ik_stretch(n, 1.0f);
  bool any = false;
  for (int i = 0; i < int(n); i++) {
    for (const BoneConstraint &c : armature.bones[i].constraints) {
      const float w = std::clamp(c.influence, 0.0f, 1.0f);
      const auto target = index.find(c.target);
      if (c.type != BoneConstraintType::IK || !c.enabled || w <= 0.0f || target == index.end() ||
          target->second == i)
      {
        continue;
      }
      if (!any) {
        extras.ik_angle = &ik_angle;
        extras.ik_stretch = &ik_stretch;
        any = true;
      }
      const std::vector<int> chain = ik_chain(armature.bones, index, i, c.chain);
      const std::vector<float> before = ik_angle;
      const float2 goal = poses[target->second].head;
      const auto pose = [&] { poses = bones_pose(armature.bones, false, extras); };
      if (chain.empty()) {
        continue;
      }
      ik_solve(
          chain, goal, armature.bones[i].arc_ik, ik_axes(armature.bones, index, poses, chain.back()),
          [&](int j, float d) {
            ik_angle[j] += d;
            return d;
          },
          pose, [&] { return poses[i].tail; }, [&](int j) { return poses[j].head; });
      /* Out of reach: the chain may stretch, up to max_stretch. The stretch goes on the chain's
       * base (the bones above it stretch with it, along the chain) and is corrected until the tip
       * just reaches. */
      if (c.max_stretch > 1.0f && !chain.empty()) {
        const int root = chain.back();
        const float2 base = poses[root].head;
        const float start = ik_stretch[root];
        for (int pass = 0; pass < 6; pass++) {
          const float reach = distance(poses[i].tail, base);
          if (reach < 1e-6f) {
            break;
          }
          const float want = std::clamp(ik_stretch[root] / start * distance(goal, base) / reach, 1.0f, c.max_stretch);
          ik_stretch[root] = start * want;
          pose();
        }
      }
      /* Influence: part of the way. */
      if (w < 1.0f) {
        for (const int j : chain) {
          ik_angle[j] = before[j] + (ik_angle[j] - before[j]) * w;
          ik_stretch[j] = 1.0f + (ik_stretch[j] - 1.0f) * w;
        }
        pose();
      }
    }
  }
  if (!with_pins) {
    return poses;
  }
  /* Pinned IK Ends and IK Bases: between keys the point goes from where the key before has it to where the key after
   * has it (in the scene, or riding the bone it is pinned to), the chain turned to reach it each frame; on a key, and
   * unpinned, the keys' pose stands. Bases first (the higher the earlier), then ends, so an end below a base reaches
   * from where the base was put. */
  struct PinnedPoint {
    int bone = 0, end = 0;
    const BoneConstraint *c = nullptr;
    int depth = 0;
  };
  std::vector<PinnedPoint> pinned;
  for (int i = 0; i < int(n); i++) {
    for (const BoneConstraint &c : armature.bones[i].constraints) {
      if ((c.type != BoneConstraintType::IKEnd && c.type != BoneConstraintType::IKBase) || !c.enabled ||
          (!c.pin_keys.animated() && c.pin == IK_PIN_NONE && !c.bend_keys.animated()))
      {
        continue;
      }
      const int e = ik_point_bone(armature.bones, index, i, c.ik_head);
      if (e < 0) {
        continue;
      }
      int depth = 0;
      for (int at = e; at >= 0 && depth < 256; depth++) {
        const auto it = index.find(armature.bones[at].parent);
        at = it == index.end() || it->second == at ? -1 : it->second;
      }
      pinned.push_back({i, e, &c, (c.type == BoneConstraintType::IKBase ? 0 : 1000) + depth});
    }
  }
  std::stable_sort(pinned.begin(), pinned.end(), [](const auto &a, const auto &b) { return a.depth < b.depth; });
  std::map<int, std::vector<BonePose>> keyed_poses;
  const auto keyed_pose = [&](int k) -> const std::vector<BonePose> & {
    const auto it = keyed_poses.find(k);
    if (it != keyed_poses.end()) {
      return it->second;
    }
    std::vector<Bone> at = armature.bones;
    for (Bone &b : at) {
      b.position = bone_position_at(b, k, false);
      b.angle = bone_angle_at(b, k, false);
      if (b.scale_keys.animated()) {
        b.scale = b.scale_keys.evaluate(k);
      }
    }
    PoseExtras ek;
    ek.frame = k;
    return keyed_poses.emplace(k, bones_pose(at, false, ek)).first->second;
  };
  for (const PinnedPoint &pp : pinned) {
    const BoneConstraint &c = *pp.c;
    const std::vector<int> chain = ik_point_chain(armature.bones, index, pp.end);
    if (chain.empty()) {
      continue;
    }
    const std::vector<int> frames = ik_pin_frames(armature.bones, chain, c);
    int k0 = -1, k1 = -1;
    for (const int k : frames) {
      if (k <= frame) {
        k0 = k;
      }
      else if (k1 < 0) {
        k1 = k;
      }
    }
    if (k0 < 0 || k0 == frame) {
      continue;
    }
    const float pin = c.pin_keys.animated() ? c.pin_keys.evaluate(k0) : c.pin;
    /* A bent path: off the straight way by the bend kept on the key before, most at the middle. */
    const float2 bend = k1 >= 0 ? ik_bend_on(c, k0) : float2();
    const bool bent = bend.x != 0.0f || bend.y != 0.0f;
    if (pin == IK_PIN_NONE && !bent) {
      continue;
    }
    const float e = k1 >= 0 ? ik_pin_progress(armature.bones[pp.end], k0, k1, frame) : 0.0f;
    const float2 bump = bend * (2.0f * e * (1.0f - e));
    const std::vector<BonePose> &p0 = keyed_pose(k0);
    const std::vector<BonePose> &p1 = keyed_pose(k1 >= 0 ? k1 : k0);
    float2 goal = p0[pp.end].tail + (p1[pp.end].tail - p0[pp.end].tail) * e;
    if (pin == IK_PIN_NONE) {
      /* Unpinned: where the keys put it, bent. */
      goal = poses[pp.end].tail;
    }
    else if (pin > 0.0f) {
      const auto to = index.find(uint64_t(pin));
      const bool moved = to != index.end() &&
                         std::any_of(chain.begin(), chain.end(),
                                     [&](int j) { return bone_is_descendant_in(armature.bones, index, armature.bones[j].id, to->second); });
      if (to != index.end() && !moved) {
        const int b = to->second;
        const float2 l0 = p0[b].pose.inverted().apply(p0[pp.end].tail);
        const float2 l1 = p1[b].pose.inverted().apply(p1[pp.end].tail);
        goal = poses[b].pose.apply(l0 + (l1 - l0) * e);
      }
    }
    goal += bump;
    if (distance(goal, poses[pp.end].tail) < 1e-7f) {
      continue;
    }
    if (!any) {
      extras.ik_angle = &ik_angle;
      extras.ik_stretch = &ik_stretch;
      any = true;
    }
    /* Keep Angle: the end bone's children keep their angle in the scene. */
    std::vector<std::pair<int, float>> kept;
    if (c.type == BoneConstraintType::IKEnd && c.keep_angle) {
      for (int j = 0; j < int(n); j++) {
        const auto it = index.find(armature.bones[j].parent);
        if (it != index.end() && it->second == pp.end && j != pp.end) {
          kept.emplace_back(j, transform_angle(poses[j].pose));
        }
      }
    }
    const auto pose = [&] { poses = bones_pose(armature.bones, false, extras); };
    const bool arc = std::any_of(chain.begin(), chain.end(), [&](int j) { return armature.bones[j].arc_ik; });
    ik_solve(
        chain, goal, arc, ik_axes(armature.bones, index, poses, chain.back()),
        [&](int j, float d) {
          ik_angle[j] += d;
          return d;
        },
        pose, [&] { return poses[pp.end].tail; }, [&](int j) { return poses[j].head; });
    if (!kept.empty()) {
      for (const auto &[j, was] : kept) {
        ik_angle[j] += wrap_pi(was - transform_angle(poses[j].pose));
      }
      pose();
    }
  }
  return poses;
}

/* Shared by the threads a render bends its drawings on (SceneRenderer::render, which lends it to them): each pose is
 * worked out outside the lock, since working one out can ask for another's (a constraint's target), and the first one
 * kept wins. */
namespace {
struct PoseCache {
  std::mutex mutex;
  std::map<std::pair<const Layer *, bool>, std::vector<BonePose>> poses;
};
}  // namespace
static thread_local PoseCache *t_pose_cache = nullptr;

ArmaturePoseCacheScope::ArmaturePoseCacheScope()
{
  if (!t_pose_cache) {
    t_pose_cache = new PoseCache();
    owner_ = true;
  }
}

ArmaturePoseCacheScope::~ArmaturePoseCacheScope()
{
  if (owner_) {
    delete t_pose_cache;
    t_pose_cache = nullptr;
  }
}

const void *armature_pose_cache_current()
{
  return t_pose_cache;
}

ArmaturePoseCacheBorrow::ArmaturePoseCacheBorrow(const void *cache) : before_(t_pose_cache)
{
  t_pose_cache = static_cast<PoseCache *>(const_cast<void *>(cache));
}

ArmaturePoseCacheBorrow::~ArmaturePoseCacheBorrow()
{
  t_pose_cache = static_cast<PoseCache *>(const_cast<void *>(before_));
}

std::vector<BonePose> armature_pose(const Layer &armature, bool setup_frame)
{
  if (PoseCache *cache = t_pose_cache) {
    const auto key = std::make_pair(&armature, setup_frame);
    {
      const std::lock_guard lock(cache->mutex);
      if (auto it = cache->poses.find(key); it != cache->poses.end()) {
        return it->second;
      }
    }
    std::vector<BonePose> made = bones_full_pose(armature.bones, setup_frame, armature.pose_frame,
                                                 &armature.dynamics_now);
    const std::lock_guard lock(cache->mutex);
    return cache->poses.try_emplace(key, std::move(made)).first->second;
  }
  return bones_full_pose(armature.bones, setup_frame, armature.pose_frame, &armature.dynamics_now);
}

std::vector<BonePose> armature_pose_of(const Layer &armature, const std::vector<Bone> &bones, bool setup_frame)
{
  return bones_full_pose(bones, setup_frame, armature.pose_frame, &armature.dynamics_now);
}

std::vector<BonePose> armature_keyed_pose(const Layer &armature, bool setup_frame)
{
  return bones_full_pose(armature.bones, setup_frame, armature.pose_frame, nullptr);
}

bool armature_reach(Layer &armature, uint64_t bone_id, float2 goal)
{
  std::map<uint64_t, int> index;
  for (int i = 0; i < int(armature.bones.size()); i++) {
    index[armature.bones[i].id] = i;
  }
  const auto it = index.find(bone_id);
  if (it == index.end()) {
    return false;
  }
  const int i = it->second;
  const std::vector<int> chain = ik_chain(armature.bones, index, i, 0);
  if (chain.size() < 2) {
    return false;
  }
  /* A bone with Limit Angle stays inside it as the chain turns. */
  const auto clamp_limits = [&](Bone &b) {
    for (const BoneConstraint &c : b.constraints) {
      if (c.type == BoneConstraintType::LimitAngle && c.enabled && c.influence >= 1.0f) {
        b.angle = b.setup_angle + std::clamp(b.angle - b.setup_angle, std::min(c.min_angle, c.max_angle),
                                             std::max(c.min_angle, c.max_angle));
      }
    }
  };
  std::vector<BonePose> poses = armature_keyed_pose(armature, false);
  ik_solve(
      chain, goal, armature.bones[i].arc_ik, ik_axes(armature.bones, index, poses, chain.back()),
      [&](int j, float d) {
        const float was = armature.bones[j].angle;
        armature.bones[j].angle += d;
        clamp_limits(armature.bones[j]);
        return armature.bones[j].angle - was;
      },
      [&] { poses = armature_keyed_pose(armature, false); }, [&] { return poses[i].tail; },
      [&](int j) { return poses[j].head; });
  return true;
}


/* --- IK points moved by hand (the viewport's IK dots and rings, armature.ik_drag) ---------------------------------- */

/* A copy's pose without pinned points worked in: the keys' (forward) pose, which moving a point by hand turns. */
static std::vector<BonePose> ik_fk_pose(const Layer &armature)
{
  return bones_full_pose(armature.bones, false, armature.pose_frame, nullptr, false);
}

float2 armature_ik_point(const Layer &armature, const std::vector<BonePose> &poses, size_t i, BoneConstraintType type)
{
  if (i >= armature.bones.size() || i >= poses.size()) {
    return {};
  }
  const Bone &b = armature.bones[i];
  const BoneConstraint *c = type == BoneConstraintType::IKEnd ? bone_ik_end(b) : bone_ik_base(b);
  const int e = c ? armature_ik_point_bone(armature, i, c->ik_head) : int(i);
  return e < 0 ? poses[i].head : poses[size_t(e)].tail;
}

/* The chain a drag bends: the point's own, `more` bones longer up the parents (past its base, not past a bone Ignored
 * by IK, a pin or a controller) or shorter (one bone at least). */
static std::vector<int> ik_drag_chain(const std::vector<Bone> &bones, const std::map<uint64_t, int> &index, int e,
                                      int more)
{
  std::vector<int> chain = ik_point_chain(bones, index, e);
  if (chain.empty()) {
    return chain;
  }
  for (; more < 0 && chain.size() > 1; more++) {
    chain.pop_back();
  }
  for (; more > 0; more--) {
    const auto it = index.find(bones[chain.back()].parent);
    if (it == index.end() || it->second == chain.back()) {
      break;
    }
    const Bone &p = bones[it->second];
    if (p.ik_ignore || p.type == BoneType::Pin || p.type == BoneType::Controller2D) {
      break;
    }
    chain.push_back(it->second);
  }
  return chain;
}

int armature_ik_chain_size(const Layer &armature, size_t i, BoneConstraintType type, int more)
{
  if (i >= armature.bones.size()) {
    return 0;
  }
  const BoneConstraint *c = type == BoneConstraintType::IKEnd ? bone_ik_end(armature.bones[i]) : bone_ik_base(armature.bones[i]);
  const std::map<uint64_t, int> index = bones_index(armature.bones);
  const int e = c ? ik_point_bone(armature.bones, index, int(i), c->ik_head) : -1;
  return e < 0 ? 0 : int(ik_drag_chain(armature.bones, index, e, more).size());
}

/* Soft IK: a goal nearly out of reach is drawn in, the last tenth of the reach eased, so a leg straightens slowly
 * rather than snapping straight. */
static float2 ik_soft_goal(float2 base, float2 goal, float reach)
{
  const float d = distance(goal, base), soft = 0.1f * reach, start = reach - soft;
  if (soft <= 0.0f || d <= start || d < 1e-9f) {
    return goal;
  }
  const float eased = start + soft * (1.0f - std::exp(-(d - start) / soft));
  return base + (goal - base) * (eased / d);
}

bool armature_ik_reach(Layer &armature, size_t i, BoneConstraintType type, float2 goal, const IKReach &how)
{
  if (i >= armature.bones.size()) {
    return false;
  }
  const BoneConstraint *c = type == BoneConstraintType::IKEnd ? bone_ik_end(armature.bones[i]) : bone_ik_base(armature.bones[i]);
  if (!c) {
    return false;
  }
  const std::map<uint64_t, int> index = bones_index(armature.bones);
  const int e = ik_point_bone(armature.bones, index, int(i), c->ik_head);
  std::vector<BonePose> poses = ik_fk_pose(armature);
  if (e < 0) {
    /* A root's head: the root moves. */
    Bone &root = armature.bones[i];
    const BonePose *outer = bone_pose_find(poses, root.parent);
    const Transform2D to_parent = outer ? outer->pose.inverted() : bone_outer_frame(root, false).inverted();
    root.position += to_parent.apply_vector(goal - poses[i].head);
    return true;
  }
  const std::vector<int> chain = ik_drag_chain(armature.bones, index, e, how.more);
  if (chain.empty()) {
    return false;
  }
  float reach = 0.0f;
  for (const int j : chain) {
    reach += distance(poses[j].head, poses[j].tail);
  }
  const float2 base = poses[chain.back()].head;
  if (how.soft && c->soft && !how.stretch && type == BoneConstraintType::IKEnd) {
    goal = ik_soft_goal(base, goal, reach);
  }
  const auto clamp_limits = [&](Bone &b) {
    for (const BoneConstraint &l : b.constraints) {
      if (l.type == BoneConstraintType::LimitAngle && l.enabled && l.influence >= 1.0f) {
        b.angle = b.setup_angle + std::clamp(b.angle - b.setup_angle, std::min(l.min_angle, l.max_angle),
                                             std::max(l.min_angle, l.max_angle));
      }
    }
  };
  const auto pose = [&] { poses = ik_fk_pose(armature); };
  const auto turn = [&](int j, float d) {
    const float was = armature.bones[j].angle;
    armature.bones[j].angle += d;
    if (!how.free) {
      clamp_limits(armature.bones[j]);
    }
    return armature.bones[j].angle - was;
  };
  /* Keep Angle: the end bone's children keep their angle in the scene. */
  std::vector<std::pair<int, float>> kept;
  if (type == BoneConstraintType::IKEnd && c->keep_angle) {
    for (int j = 0; j < int(armature.bones.size()); j++) {
      const auto it = index.find(armature.bones[j].parent);
      if (it != index.end() && it->second == e && j != e) {
        kept.emplace_back(j, transform_angle(poses[j].pose));
      }
    }
  }
  const bool arc = std::any_of(chain.begin(), chain.end(), [&](int j) { return armature.bones[j].arc_ik; });
  ik_solve(chain, goal, arc, ik_axes(armature.bones, index, poses, chain.back()), turn, pose,
           [&] { return poses[e].tail; }, [&](int j) { return poses[j].head; });
  /* Alt: out of reach, the chain stretches (on its base bone, the bones above it stretching with it). */
  if (how.stretch) {
    Bone &root = armature.bones[chain.back()];
    for (int pass = 0; pass < 6; pass++) {
      const float now = distance(poses[e].tail, base);
      const float want = distance(goal, base);
      if (now < 1e-6f || want <= now + 1e-6f) {
        break;
      }
      root.scale.y *= want / now;
      pose();
    }
  }
  /* Flip: the bend the other way, the chain reflected across the line from its base to its point. */
  if (how.flip && chain.size() >= 2) {
    const float2 to = poses[e].tail - base;
    const float axis = std::atan2(to.y, to.x);
    std::vector<float> want(chain.size());
    for (size_t k = 0; k < chain.size(); k++) {
      const float2 d = poses[chain[k]].tail - poses[chain[k]].head;
      want[k] = 2.0f * axis - std::atan2(d.y, d.x);
    }
    /* From the base down, each bone turned to its reflected way (under a flipped parent a turn goes the other way:
     * tried, and turned back twice as far if it went wrong). */
    const auto off = [&](size_t k) {
      const float2 d = poses[chain[k]].tail - poses[chain[k]].head;
      return wrap_pi(want[k] - std::atan2(d.y, d.x));
    };
    for (size_t k = chain.size(); k-- > 0;) {
      const float d = off(k);
      armature.bones[chain[k]].angle += d;
      pose();
      if (std::abs(off(k)) > std::abs(d) * 0.5f) {
        armature.bones[chain[k]].angle -= 2.0f * d;
        pose();
      }
    }
  }
  if (!kept.empty()) {
    for (const auto &[j, was] : kept) {
      armature.bones[j].angle += wrap_pi(was - transform_angle(poses[j].pose));
    }
  }
  return true;
}

void armature_ik_hold(Layer &armature, const std::vector<Bone> &original, size_t skip, BoneConstraintType skip_type)
{
  if (armature.pose_frame == 0 || original.size() != armature.bones.size()) {
    return;
  }
  const size_t n = armature.bones.size();
  /* What the user moved: bones changed from how the edit began. */
  std::vector<bool> moved(n, false);
  for (size_t j = 0; j < n; j++) {
    const Bone &a = armature.bones[j], &b = original[j];
    moved[j] = a.position != b.position || a.angle != b.angle || a.scale != b.scale;
  }
  if (std::none_of(moved.begin(), moved.end(), [](bool m) { return m; })) {
    return;
  }
  const std::vector<BonePose> was = bones_full_pose(original, false, armature.pose_frame, nullptr);
  const std::map<uint64_t, int> index = bones_index(armature.bones);
  struct Held {
    size_t bone;
    BoneConstraintType type;
    int depth;
    float2 place;
    int on = -1;
    float2 local;
  };
  std::vector<Held> held;
  for (size_t i = 0; i < n; i++) {
    for (const BoneConstraint &c : armature.bones[i].constraints) {
      if ((c.type != BoneConstraintType::IKEnd && c.type != BoneConstraintType::IKBase) || !c.enabled ||
          c.pin == IK_PIN_NONE || (i == skip && c.type == skip_type))
      {
        continue;
      }
      if (c.type == BoneConstraintType::IKBase && !bone_find(armature, armature.bones[i].parent)) {
        continue;
      }
      const std::vector<size_t> chain = armature_ik_chain(armature, i, c.type);
      if (chain.empty() || std::any_of(chain.begin(), chain.end(), [&](size_t j) { return moved[j]; })) {
        continue;
      }
      int depth = 0;
      for (int at = int(i); at >= 0 && depth < 256; depth++) {
        const auto it = index.find(armature.bones[at].parent);
        at = it == index.end() || it->second == at ? -1 : it->second;
      }
      Held h{i, c.type, (c.type == BoneConstraintType::IKBase ? 0 : 1000) + depth,
             armature_ik_point(armature, was, i, c.type)};
      if (c.pin > 0.0f) {
        if (const auto it = index.find(uint64_t(c.pin)); it != index.end()) {
          h.on = it->second;
          h.local = was[size_t(h.on)].pose.inverted().apply(h.place);
        }
      }
      held.push_back(h);
    }
  }
  std::stable_sort(held.begin(), held.end(), [](const Held &a, const Held &b) { return a.depth < b.depth; });
  for (const Held &h : held) {
    float2 goal = h.place;
    if (h.on >= 0) {
      goal = ik_fk_pose(armature)[size_t(h.on)].pose.apply(h.local);
    }
    IKReach how;
    how.soft = false;
    armature_ik_reach(armature, h.bone, h.type, goal, how);
  }
}

/* Why IK End `end` (a bone) can't be pinned to bone `to` ("" when it can): a bone its chain moves would carry its own
 * goal, and one that already follows this end (through other ends pinned to bones) would chase it round. */
std::string armature_ik_pin_refusal(const Layer &armature, const Bone &end, const Bone &to)
{
  const auto index_of = [&](const Bone &b) { return size_t(&b - armature.bones.data()); };
  const auto moved_by = [&](const Bone &e) {
    std::vector<size_t> out;
    const BoneConstraint *c = bone_ik_end(e);
    const std::vector<size_t> chain = armature_ik_chain(armature, index_of(e),
                                                        c ? BoneConstraintType::IKEnd : BoneConstraintType::IKBase);
    if (chain.empty()) {
      return out;
    }
    const uint64_t top = armature.bones[chain.back()].id;
    for (size_t j = 0; j < armature.bones.size(); j++) {
      if (bone_is_descendant(armature, armature.bones[j].id, top)) {
        out.push_back(j);
      }
    }
    return out;
  };
  const auto moves = [&](const Bone &e, const Bone &b) {
    const std::vector<size_t> m = moved_by(e);
    return std::find(m.begin(), m.end(), index_of(b)) != m.end();
  };
  if (moves(end, to)) {
    return to.name + " moves with " + end.name + "'s chain";
  }
  std::set<uint64_t> seen;
  const std::function<bool(const Bone &)> follows = [&](const Bone &x) {
    for (const Bone &e2 : armature.bones) {
      const BoneConstraint *c2 = bone_ik_end(e2);
      if (!c2 || !moves(e2, x)) {
        continue;
      }
      if (&e2 == &end) {
        return true;
      }
      if (c2->pin > 0.0f && seen.insert(e2.id).second) {
        if (const Bone *t = bone_find(armature, uint64_t(c2->pin)); t && follows(*t)) {
          return true;
        }
      }
    }
    return false;
  };
  return follows(to) ? to.name + " already follows " + end.name : std::string();
}

std::vector<int> armature_ik_frames(const Layer &armature, size_t i)
{
  const BoneConstraint *c = i < armature.bones.size() ? bone_ik_end(armature.bones[i]) : nullptr;
  if (!c) {
    return {};
  }
  const std::map<uint64_t, int> index = bones_index(armature.bones);
  const int e = ik_point_bone(armature.bones, index, int(i), c->ik_head);
  if (e < 0) {
    return {};
  }
  return ik_pin_frames(armature.bones, ik_point_chain(armature.bones, index, e), *c);
}

bool armature_ik_stretch_at(const Layer &armature, size_t i, int frame, int &k0, int &k1)
{
  k0 = k1 = -1;
  for (const int k : armature_ik_frames(armature, i)) {
    if (k <= frame) {
      k0 = k;
    }
    else if (k1 < 0) {
      k1 = k;
    }
  }
  return k0 >= 0 && k1 >= 0;
}

float armature_ik_bend_weight(const Layer &armature, size_t i, int frame)
{
  int k0, k1;
  const BoneConstraint *c = i < armature.bones.size() ? bone_ik_end(armature.bones[i]) : nullptr;
  if (!c || !armature_ik_stretch_at(armature, i, frame, k0, k1)) {
    return 0.0f;
  }
  const int e = armature_ik_point_bone(armature, i, c->ik_head);
  const float u = ik_pin_progress(armature.bones[size_t(e < 0 ? int(i) : e)], k0, k1, frame);
  return 2.0f * u * (1.0f - u);
}

bool armature_ik_bend_set(Layer &armature, size_t i, int frame, float2 bend, int frame_shown)
{
  BoneConstraint *c = nullptr;
  if (i < armature.bones.size()) {
    for (BoneConstraint &x : armature.bones[i].constraints) {
      if (x.type == BoneConstraintType::IKEnd && !c) {
        c = &x;
      }
    }
  }
  int k0, k1;
  if (!c || !armature_ik_stretch_at(armature, i, frame, k0, k1)) {
    return false;
  }
  if (bend == ik_bend_on(*c, k0)) {
    return false;
  }
  /* Each stretch keeps its own on the key it leaves (a key put inside it later starts one unbent); straightened, it
   * has none. */
  if (bend == float2()) {
    c->bend_keys.remove_key(k0);
  }
  else {
    c->bend_keys.set_key(k0, bend);
  }
  /* As the keys have it now, so auto-key sees no edit to key on the frame shown. */
  c->bend = ik_bend_on(*c, frame_shown);
  c->bend_keys.last = c->bend;
  c->bend_keys.has_last = true;
  return true;
}

float2 armature_ik_point_at(const Layer &armature, size_t i, int frame)
{
  std::vector<Bone> at = armature.bones;
  for (Bone &b : at) {
    b.position = bone_position_at(b, frame, false);
    b.angle = bone_angle_at(b, frame, false);
    if (b.scale_keys.animated()) {
      b.scale = b.scale_keys.evaluate(frame);
    }
    for (BoneConstraint &c : b.constraints) {
      if (c.pin_keys.animated()) {
        c.pin = c.pin_keys.evaluate(frame);
      }
    }
  }
  Layer copy;
  copy.bones = std::move(at);
  const std::vector<BonePose> poses = bones_full_pose(copy.bones, frame == 0, frame, nullptr);
  return armature_ik_point(copy, poses, i, BoneConstraintType::IKEnd);
}

bool armature_ik_clear_scale(Layer &armature, size_t i)
{
  const std::vector<Bone> was = armature.bones;
  for (const size_t j : armature_ik_chain(armature, i, BoneConstraintType::IKEnd)) {
    Bone &x = armature.bones[j];
    x.scale = setup_value(x.scale_keys, x.scale, false) + x.scale_keys.from_action_bones;
  }
  armature_ik_hold(armature, was, i, BoneConstraintType::IKEnd);
  return !(armature.bones == was);
}

const BonePose *bone_pose_find(const std::vector<BonePose> &poses, uint64_t id)
{
  for (const BonePose &p : poses) {
    if (p.id == id) {
      return &p;
    }
  }
  return nullptr;
}

Bone *bone_find(Layer &armature, uint64_t id)
{
  for (Bone &b : armature.bones) {
    if (b.id == id && id != 0) {
      return &b;
    }
  }
  return nullptr;
}

const Bone *bone_find(const Layer &armature, uint64_t id)
{
  return bone_find(const_cast<Layer &>(armature), id);
}

const Bone *bone_find_by_name(const Layer &armature, const std::string &name)
{
  for (const Bone &b : armature.bones) {
    if (b.name == name) {
      return &b;
    }
  }
  return nullptr;
}

bool bone_is_descendant(const Layer &armature, uint64_t id, uint64_t ancestor)
{
  for (int depth = 0; id != 0 && depth < 256; depth++) {
    if (id == ancestor) {
      return true;
    }
    const Bone *b = bone_find(armature, id);
    id = b ? b->parent : 0;
  }
  return false;
}

void bone_select(Bone &bone, bool select)
{
  bone.selected = bone.select_head = bone.select_tail = select;
}

void armature_deselect_all(Layer &armature)
{
  for (Bone &b : armature.bones) {
    bone_select(b, false);
  }
}

/* The joint flags alone, without the body. */
static bool head_joint(const Layer &armature, const Bone &bone)
{
  if (bone.select_head) {
    return true;
  }
  const Bone *parent = bone.connected ? bone_find(armature, bone.parent) : nullptr;
  return parent && parent->select_tail;
}

static bool tail_joint(const Layer &armature, const Bone &bone)
{
  if (bone.select_tail) {
    return true;
  }
  for (const Bone &child : armature.bones) {
    if (child.connected && child.parent == bone.id && child.select_head) {
      return true;
    }
  }
  return false;
}

bool bone_head_selected(const Layer &armature, const Bone &bone)
{
  if (bone.type == BoneType::Pin) {
    /* One point: either end picked is the pin, which moves whole (its hidden tip with it). */
    return bone.selected || head_joint(armature, bone) || tail_joint(armature, bone);
  }
  const Bone *parent = bone.connected ? bone_find(armature, bone.parent) : nullptr;
  return bone.selected || head_joint(armature, bone) || (parent && parent->selected);
}

bool bone_tail_selected(const Layer &armature, const Bone &bone)
{
  if (bone.type == BoneType::Pin) {
    return bone_head_selected(armature, bone);
  }
  if (bone.selected || tail_joint(armature, bone)) {
    return true;
  }
  for (const Bone &child : armature.bones) {
    if (child.connected && child.parent == bone.id && child.selected) {
      return true;
    }
  }
  return false;
}

void armature_flush_selection(Layer &armature)
{
  std::vector<bool> both(armature.bones.size());
  for (size_t i = 0; i < armature.bones.size(); i++) {
    both[i] = head_joint(armature, armature.bones[i]) && tail_joint(armature, armature.bones[i]);
  }
  for (size_t i = 0; i < armature.bones.size(); i++) {
    armature.bones[i].selected = both[i];
  }
}

/* Parents before children (a cycle is cut where it closes). */
static std::vector<int> bones_parents_first(const Layer &armature)
{
  std::vector<int> order;
  std::vector<int> state(armature.bones.size(), 0);
  std::map<uint64_t, int> index;
  for (int i = 0; i < int(armature.bones.size()); i++) {
    index[armature.bones[i].id] = i;
  }
  const auto visit = [&](auto &&self, int i) -> void {
    if (state[i] != 0) {
      return;
    }
    state[i] = 1;
    if (auto it = index.find(armature.bones[i].parent); it != index.end()) {
      self(self, it->second);
    }
    state[i] = 2;
    order.push_back(i);
  };
  for (int i = 0; i < int(armature.bones.size()); i++) {
    visit(visit, i);
  }
  return order;
}

void armature_set_joints(Layer &armature, const std::map<uint64_t, std::pair<float2, float2>> &targets,
                         const std::map<uint64_t, float> *world_angles)
{
  const std::vector<BonePose> poses = armature_pose(armature);
  const size_t n = armature.bones.size();
  std::map<uint64_t, int> index;
  for (int i = 0; i < int(n); i++) {
    index[armature.bones[i].id] = i;
  }
  std::vector<float2> head(n), tail(n);
  std::vector<bool> changed(n, false);
  const std::vector<int> order = bones_parents_first(armature);
  for (const int i : order) {
    const Bone &b = armature.bones[i];
    const auto parent = index.find(b.parent);
    const bool has_parent = parent != index.end() && parent->second != i;
    head[i] = poses[i].head;
    tail[i] = poses[i].tail;
    if (auto it = targets.find(b.id); it != targets.end()) {
      head[i] = it->second.first;
      tail[i] = it->second.second;
      /* Only a bone that has somewhere else to be is rebuilt: one already there keeps its numbers
       * exactly (rebuilding would round them, and mirror editing would take that for a move). */
      const auto w = world_angles ? world_angles->find(b.id) : decltype(world_angles->end()){};
      const bool turns = world_angles && w != world_angles->end() &&
                         std::abs(wrap_pi(w->second - transform_angle(poses[i].pose))) > 1e-6f;
      changed[i] = distance(head[i], poses[i].head) > 1e-7f || distance(tail[i], poses[i].tail) > 1e-7f || turns;
    }
    if (b.connected && has_parent) {
      head[i] = tail[parent->second];
      changed[i] = changed[i] || distance(head[i], poses[i].head) > 1e-9f;
    }
  }
  /* Rebuild parents first: a bone below a changed one is measured again from its parent's new
   * frame, so it stays where it was. */
  std::vector<Transform2D> frame(n);
  std::vector<bool> redo(n, false);
  for (const int i : order) {
    Bone &b = armature.bones[i];
    const auto parent = index.find(b.parent);
    const bool has_parent = parent != index.end() && parent->second != i;
    const Transform2D parent_frame = has_parent ? frame[parent->second] : bone_outer_frame(b, true);
    redo[i] = changed[i] || (has_parent && redo[parent->second]);
    if (redo[i]) {
      const Transform2D to_parent = parent_frame.inverted();
      const float2 h = to_parent.apply(head[i]), t = to_parent.apply(tail[i]);
      b.position = h;
      if (distance(h, t) > 1e-7f) {
        /* Whole turns are kept: the nearest angle to the old one, so keys don't jump a turn. */
        float angle = std::atan2(t.y - h.y, t.x - h.x);
        angle += 2.0f * PI * std::round((b.angle - angle) / (2.0f * PI));
        b.angle = angle;
      }
      else if (const auto w = world_angles ? world_angles->find(b.id) : decltype(world_angles->end()){};
               world_angles && w != world_angles->end())
      {
        float angle = w->second - transform_angle(parent_frame);
        angle += 2.0f * PI * std::round((b.angle - angle) / (2.0f * PI));
        b.angle = angle;
      }
      b.length = distance(h, t) / std::max(std::abs(b.scale.y), 1e-6f);
    }
    frame[i] = parent_frame * bone_local(b.position, b.angle, b.scale);
  }
}

/* The setup frame edits the rig as Blender's edit mode: only the joints being moved move. After a
 * transform worked the bones out from `original` (carrying children along with their parents),
 * each bone end not in `moves` (head, tail) goes back where it was, and a connected bone's head
 * stays on its parent's tail. */
static void hold_still_joints(Layer &armature, const std::vector<Bone> &original,
                              const std::vector<std::pair<bool, bool>> &moves)
{
  if (original.size() != armature.bones.size() || moves.size() != original.size()) {
    return;
  }
  const std::vector<BonePose> now = armature_pose(armature, true);
  std::vector<Bone> moved = std::move(armature.bones);
  armature.bones = original;
  const std::vector<BonePose> was = armature_pose(armature, true);
  std::map<uint64_t, std::pair<float2, float2>> targets;
  std::map<uint64_t, float> angles;
  for (size_t i = 0; i < original.size(); i++) {
    const auto [head, tail] = moves[i];
    targets[original[i].id] = {head ? now[i].head : was[i].head, tail ? now[i].tail : was[i].tail};
    angles[original[i].id] = transform_angle(head || tail ? now[i].pose : was[i].pose);
  }
  armature.bones = std::move(moved);
  armature_set_joints(armature, targets, &angles);
}

/* The picked ends: a selected bone's both, else whichever joint is selected (a connected bone's
 * head is its parent's tail). */
static std::vector<std::pair<bool, bool>> picked_joints(const Layer &armature)
{
  std::vector<std::pair<bool, bool>> moves;
  for (const Bone &b : armature.bones) {
    moves.push_back({b.selected || bone_head_selected(armature, b), b.selected || bone_tail_selected(armature, b)});
  }
  return moves;
}

/* Whether the bone is picked for G as a whole (its body or its base), or by its tip alone. A
 * connected bone's base is its parent's tip, so picking it aims the parent instead; but posed, a controller's G
 * moves its knob, wherever its box sits. */
static bool grabs_whole(const Bone &b, bool setup_frame)
{
  return (b.selected || b.select_head) && (!b.connected || (!setup_frame && bone_is_controller(b)));
}

static bool grabs_tip(const Layer &armature, const Bone &b, bool setup_frame)
{
  if (grabs_whole(b, setup_frame)) {
    return false;
  }
  if (b.select_tail) {
    return true;
  }
  /* Posing, a connected bone can't leave its parent's tip: G turns it to follow the mouse instead.
   * On the setup frame, grabbing it drags the parent's tip. */
  if (!setup_frame) {
    return b.connected && (b.selected || b.select_head);
  }
  for (const Bone &child : armature.bones) {
    if (child.connected && child.parent == b.id && (child.selected || child.select_head)) {
      return true;
    }
  }
  return false;
}

static bool bone_picked(const Bone &b)
{
  return b.selected || b.select_head || b.select_tail;
}

/* True when an ancestor of the bone passes the test. */
/* What a move moves: what's picked, but for what comes along with a bone in a bone layer around it. */
static bool bone_moves(const Bone &b)
{
  return bone_picked(b) && !b.outer_carried;
}

template<typename F> static bool ancestor_is(const Layer &armature, const Bone &bone, F &&test)
{
  const Bone *p = bone_find(armature, bone.parent);
  for (int depth = 0; p && depth < 256; depth++) {
    if (test(*p)) {
      return true;
    }
    p = bone_find(armature, p->parent);
  }
  return false;
}

/* A connected child sits on its parent's tip, wherever that is now. */
static void seat_connected_children(Layer &armature)
{
  for (Bone &b : armature.bones) {
    if (const Bone *parent = b.connected ? bone_find(armature, b.parent) : nullptr) {
      b.position = {parent->length, 0.0f};
    }
  }
}

bool armature_clear_pose(Layer &armature, bool position, bool angle, bool scale)
{
  bool any = false;
  /* Back to the setup pose plus what action bone actions add now, so a bone an action bone moves goes back to
   * where that puts it (an action bone's own turn has no action bone part: it goes back to its rest). */
  for (Bone &b : armature.bones) {
    if (!bone_picked(b)) {
      continue;
    }
    if (position) {
      b.position = bone_position_from_transform(b, b.position_keys.from_action_bones);
    }
    if (angle) {
      b.angle = b.setup_angle + b.angle_keys.from_action_bones;
    }
    if (scale) {
      b.scale = setup_value(b.scale_keys, b.scale, false) + b.scale_keys.from_action_bones;
    }
    any = true;
  }
  return any;
}

bool armature_any_picked(const Layer &armature)
{
  return std::any_of(armature.bones.begin(), armature.bones.end(), bone_picked);
}

std::vector<float2> armature_picked_heads(const Layer &armature, bool setup_frame)
{
  const std::vector<BonePose> poses = armature_keyed_pose(armature, setup_frame);
  std::vector<float2> heads;
  for (size_t i = 0; i < armature.bones.size(); i++) {
    if (bone_picked(armature.bones[i])) {
      /* A controller's knob is what moves and turns. */
      heads.push_back(poses[i].knob.apply({0, 0}));
    }
  }
  return heads;
}

/* Each bone's angle as the last update of a drag left it (the start's when the bones aren't the
 * same ones): a turn picks its whole turns nearest to that, so dragging round past half a turn
 * from where the drag began keeps turning the same way instead of flipping back. */
static std::vector<float> turned_angles(const Layer &armature, const std::vector<Bone> &original)
{
  std::vector<float> angles(original.size());
  for (size_t i = 0; i < original.size(); i++) {
    const bool same = i < armature.bones.size() && armature.bones[i].id == original[i].id;
    angles[i] = same ? armature.bones[i].angle : original[i].angle;
  }
  return angles;
}

void armature_grab_selected(Layer &armature, const std::vector<Bone> &original, float2 delta, bool setup_frame,
                            bool auto_ik)
{
  const std::vector<float> was_turned = turned_angles(armature, original);
  armature.bones = original;
  const std::vector<BonePose> poses = armature_keyed_pose(armature, setup_frame);
  const auto moves = [&](const Bone &b) {
    return !b.outer_carried && (grabs_whole(b, setup_frame) || grabs_tip(armature, b, setup_frame));
  };
  std::vector<std::pair<size_t, bool>> todo;
  for (size_t i = 0; i < armature.bones.size(); i++) {
    const Bone &b = armature.bones[i];
    /* Children come along with a parent that moves or turns, as in Moho. */
    if (moves(b) && !ancestor_is(armature, b, moves)) {
      todo.push_back({i, grabs_whole(b, setup_frame)});
    }
  }
  for (const auto &[i, whole] : todo) {
    Bone &b = armature.bones[i];
    const BonePose *parent = bone_pose_find(poses, b.parent);
    const Transform2D to_parent = parent ? parent->pose.inverted() : bone_outer_frame(b, setup_frame).inverted();
    if (whole && bone_is_controller(b) && !setup_frame) {
      controller_knob_move(b, poses[i], delta);
      continue;
    }
    if (whole) {
      b.position += to_parent.apply_vector(delta);
      continue;
    }
    /* Posing by the tip with Auto IK: the chain above turns too, so the tip reaches the mouse
     * (Moho's IK). A connected bone grabbed by its body only turns itself. */
    if (!setup_frame && auto_ik && b.select_tail && !b.selected && armature_reach(armature, b.id, poses[i].tail + delta)) {
      continue;
    }
    /* The tip follows the mouse: the bone turns about its base, and on the setup frame it also
     * grows or shrinks (length isn't animated, so elsewhere it only turns). */
    const float2 tip = to_parent.apply(poses[i].tail + delta);
    const float2 d = tip - b.position;
    if (length(d) > 1e-7f) {
      float angle = std::atan2(d.y, d.x);
      angle += 2.0f * PI * std::round((was_turned[i] - angle) / (2.0f * PI));
      b.angle = angle;
    }
    if (setup_frame) {
      b.length = length(d) / std::max(std::abs(b.scale.y), 1e-6f);
    }
  }
  /* Auto IK turns its chains by the shortest way from the start: the same whole turns as before. */
  for (size_t i = 0; i < armature.bones.size() && i < was_turned.size(); i++) {
    float &angle = armature.bones[i].angle;
    angle += 2.0f * PI * std::round((was_turned[i] - angle) / (2.0f * PI));
  }
  if (setup_frame) {
    seat_connected_children(armature);
    hold_still_joints(armature, original, picked_joints(armature));
  }
  else {
    /* Pinned ends and bases the move left alone stay where they were. */
    armature_ik_hold(armature, original, armature.bones.size(), BoneConstraintType::IKEnd);
  }
}

void armature_rotate_selected(Layer &armature, const std::vector<Bone> &original, float angle, bool setup_frame)
{
  armature.bones = original;
  /* A picked group turns as one: a child already turns with a picked parent, so it isn't turned
   * again. */
  std::vector<bool> turns(armature.bones.size());
  for (size_t i = 0; i < armature.bones.size(); i++) {
    const Bone &b = armature.bones[i];
    /* A controller turns its knob (keyed, as a pin's angle); on the setup frame, the whole box with it. */
    turns[i] = bone_moves(b) && !ancestor_is(armature, b, bone_moves);
  }
  for (size_t i = 0; i < armature.bones.size(); i++) {
    if (turns[i]) {
      armature.bones[i].angle += angle;
      if (setup_frame && bone_is_controller(armature.bones[i])) {
        armature.bones[i].controller_box_angle += angle;
      }
    }
  }
  if (setup_frame) {
    hold_still_joints(armature, original, picked_joints(armature));
  }
  else {
    armature_ik_hold(armature, original, armature.bones.size(), BoneConstraintType::IKEnd);
  }
}

void armature_scale_selected(Layer &armature, const std::vector<Bone> &original, float factor, bool setup_frame,
                             int axis, bool squash)
{
  armature.bones = original;
  if (setup_frame) {
    /* Frame 0 changes sizes, not scale: the picked joints spread out or close in about the middle
     * of the picked bases, as Blender's edit mode scales, so bones get longer or shorter. */
    float2 sum;
    const std::vector<float2> heads = armature_picked_heads(armature, true);
    for (const float2 &h : heads) {
      sum += h;
    }
    const float2 pivot = sum / float(std::max<size_t>(heads.size(), 1));
    const Transform2D map = Transform2D::translate(pivot) * Transform2D::scaling({factor, factor}) *
                            Transform2D::translate(-pivot);
    armature_map_selected(armature, original, map, true);
    return;
  }
  /* Posing: each bone along its own axes. A child already grows with a picked parent; scaling
   * it too would grow it twice over. */
  float2 f(axis == 2 ? 1.0f : factor, axis == 1 ? 1.0f : factor);
  if (squash) {
    /* Longer and thinner (or shorter and fatter), keeping its area. */
    f = {1.0f / std::max(std::abs(factor), 1e-4f), factor};
  }
  std::vector<bool> scales(armature.bones.size());
  for (size_t i = 0; i < armature.bones.size(); i++) {
    const Bone &b = armature.bones[i];
    scales[i] = bone_moves(b) && !ancestor_is(armature, b, bone_moves) && !bone_is_controller(b);
  }
  for (size_t i = 0; i < armature.bones.size(); i++) {
    if (scales[i]) {
      armature.bones[i].scale = {armature.bones[i].scale.x * f.x, armature.bones[i].scale.y * f.y};
    }
  }
  armature_ik_hold(armature, original, armature.bones.size(), BoneConstraintType::IKEnd);
}

bool armature_picked_bounds(const Layer &armature, bool setup_frame, float2 &lo, float2 &hi)
{
  const std::vector<BonePose> poses = armature_keyed_pose(armature, setup_frame);
  bool any = false;
  for (size_t i = 0; i < armature.bones.size(); i++) {
    if (!bone_picked(armature.bones[i])) {
      continue;
    }
    for (const float2 p : {poses[i].head, poses[i].tail}) {
      lo = any ? float2(std::min(lo.x, p.x), std::min(lo.y, p.y)) : p;
      hi = any ? float2(std::max(hi.x, p.x), std::max(hi.y, p.y)) : p;
      any = true;
    }
  }
  if (any) {
    /* A flat selection still gets a box with some size, as in the Moho script. */
    const float min_size = 0.01f;
    const float2 c = (lo + hi) * 0.5f;
    if (hi.x - lo.x < min_size) {
      lo.x = c.x - min_size * 0.5f;
      hi.x = c.x + min_size * 0.5f;
    }
    if (hi.y - lo.y < min_size) {
      lo.y = c.y - min_size * 0.5f;
      hi.y = c.y + min_size * 0.5f;
    }
  }
  return any;
}

/* `map` sends places, `stretch_along(p, v)` what it does to a short step `v` from `p`. */
static void armature_map_selected_by(Layer &armature, const std::vector<Bone> &original,
                                     const std::function<float2(float2)> &map,
                                     const std::function<float2(float2, float2)> &stretch_along, bool setup_frame);

void armature_map_selected(Layer &armature, const std::vector<Bone> &original, const Transform2D &map,
                           bool setup_frame)
{
  armature_map_selected_by(
      armature, original, [&](float2 p) { return map.apply(p); },
      [&](float2, float2 v) { return map.apply_vector(v); }, setup_frame);
}

void armature_map_selected(Layer &armature, const std::vector<Bone> &original,
                           const std::function<float2(float2)> &map, bool setup_frame)
{
  armature_map_selected_by(
      armature, original, map,
      [&](float2 p, float2 v) {
        const float e = 1e-3f;
        return (map(p + v * e) - map(p - v * e)) / (2.0f * e);
      },
      setup_frame);
}

static void armature_map_selected_by(Layer &armature, const std::vector<Bone> &original,
                                     const std::function<float2(float2)> &map,
                                     const std::function<float2(float2, float2)> &stretch_along, bool setup_frame)
{
  const std::vector<float> was_turned = turned_angles(armature, original);
  armature.bones = original;
  const std::vector<BonePose> poses = armature_keyed_pose(armature, setup_frame);
  const size_t n = armature.bones.size();
  std::map<uint64_t, int> index;
  for (int i = 0; i < int(n); i++) {
    index[armature.bones[i].id] = i;
  }
  /* The map's average stretch at `p`, for bones with no length to measure. */
  const auto stretch = [&](float2 p) {
    return (length(stretch_along(p, {1, 0})) + length(stretch_along(p, {0, 1}))) * 0.5f;
  };
  /* Each bone's frame now and as it rests: a bone that doesn't take all of its parent's change hangs its
   * axes from the parent's rest (Relations). */
  std::vector<Transform2D> frame(n), rest(n);
  for (const int i : bones_parents_first(armature)) {
    Bone &b = armature.bones[i];
    const auto parent = index.find(b.parent);
    const bool has_parent = parent != index.end() && parent->second != i;
    const Transform2D parent_frame = has_parent ? frame[parent->second] : bone_outer_frame(b, setup_frame);
    const Transform2D parent_rest = has_parent ? rest[parent->second] : bone_outer_frame(b, true);
    rest[i] = parent_rest * bone_local(b.setup_position, b.setup_angle, setup_value(b.scale_keys, b.scale, false));
    const bool picked = bone_moves(original[i]);
    const bool child_of_picked = has_parent && bone_moves(original[parent->second]);
    /* A controller's position holds its knob while posing, and the box rides on its parent: a picked knob goes
     * where the map takes it, as G moves it. */
    if (picked && !setup_frame && bone_is_controller(b)) {
      const float2 at = poses[i].knob.apply({0, 0});
      controller_knob_move(b, poses[i], map(at) - at);
    }
    if ((picked || child_of_picked) && (setup_frame || !bone_is_controller(b))) {
      /* Where the base and a point along the bone go: through the map when picked; an unpicked
       * child of a picked bone stays where it was. */
      const float reach = b.length > 1e-4f ? b.length : 1.0f;
      const Transform2D &was = poses[i].pose;
      float2 head = was.apply({0, 0}), tip = was.apply({reach, 0});
      const float2 was_head = head;
      if (picked) {
        head = map(head);
        tip = map(tip);
      }
      const Transform2D to_parent = parent_frame.inverted();
      const Transform2D to_axes = bone_parent_axes(b, parent_frame, parent_rest, setup_frame).inverted();
      const float2 h = to_parent.apply(head), t = h + to_axes.apply_vector(tip - head);
      b.position = h;
      const float dist = distance(h, t);
      if (dist > 1e-9f) {
        float angle = std::atan2(t.y - h.y, t.x - h.x);
        angle += 2.0f * PI * std::round((was_turned[i] - angle) / (2.0f * PI));
        b.angle = angle;
      }
      if (b.length > 1e-4f) {
        /* The setup pose takes a new length; a pose (length isn't animated) takes a scale. */
        if (setup_frame) {
          b.length = dist / std::max(std::abs(b.scale.y), 1e-6f);
        }
        else {
          b.scale.y = dist / b.length;
          if (picked) {
            /* Across the bone: how much the map stretches that way. */
            const float2 across = normalize(was.apply_vector({0.0f, 1.0f}));
            b.scale.x = original[i].scale.x * length(stretch_along(was_head, across));
          }
        }
      }
      else if (!setup_frame) {
        b.scale = picked ? original[i].scale * stretch(was_head) : original[i].scale;
      }
    }
    frame[i] = bone_on_parent(b, parent_frame, parent_rest, bone_local(b.position, b.angle, b.scale), setup_frame);
  }
  if (setup_frame) {
    seat_connected_children(armature);
    hold_still_joints(armature, original, picked_joints(armature));
  }
}

void armature_keep_children(Layer &armature, const std::vector<Bone> &original, bool setup_frame)
{
  const size_t n = armature.bones.size();
  if (original.size() != n) {
    return;
  }
  const std::vector<BonePose> was = bones_full_pose(original, setup_frame, armature.pose_frame, nullptr);
  std::map<uint64_t, int> index;
  for (int i = 0; i < int(n); i++) {
    index[armature.bones[i].id] = i;
  }
  /* Picked to move: a connected bone's base is its parent's tip, so that alone doesn't pick it. */
  const auto moved = [](const Bone &b) {
    return !b.outer_carried && (b.selected || b.select_tail || (b.select_head && !b.connected));
  };
  std::vector<Transform2D> frame(n), rest(n);
  for (const int i : bones_parents_first(armature)) {
    Bone &b = armature.bones[i];
    const auto parent = index.find(b.parent);
    const bool has_parent = parent != index.end() && parent->second != i;
    const Transform2D parent_frame = has_parent ? frame[parent->second] : bone_outer_frame(b, setup_frame);
    const Transform2D parent_rest = has_parent ? rest[parent->second] : bone_outer_frame(b, true);
    rest[i] = parent_rest * bone_local(b.setup_position, b.setup_angle, setup_value(b.scale_keys, b.scale, false));
    /* A controller's box stays on its parent, its position holding its knob. */
    if (has_parent && !moved(original[i]) && moved(original[parent->second]) && !bone_is_controller(b)) {
      const float reach = b.length > 1e-4f ? b.length : 1.0f;
      const float2 head = was[i].pose.apply({0, 0}), tip = was[i].pose.apply({reach, 0});
      const Transform2D to_parent = parent_frame.inverted();
      const Transform2D to_axes = bone_parent_axes(b, parent_frame, parent_rest, setup_frame).inverted();
      float2 h = to_parent.apply(head);
      if (b.connected) {
        /* On the parent's tip as it is now, pointing the way it did, as long as it was. */
        h = b.position;
      }
      const float2 t = h + to_axes.apply_vector(tip - head);
      b.position = h;
      const float dist = distance(h, t);
      if (dist > 1e-9f) {
        float angle = std::atan2(t.y - h.y, t.x - h.x);
        angle += 2.0f * PI * std::round((original[i].angle - angle) / (2.0f * PI));
        b.angle = angle;
      }
      if (b.length > 1e-4f && dist > 1e-9f) {
        if (setup_frame) {
          b.length = dist / std::max(std::abs(b.scale.y), 1e-6f);
        }
        else {
          b.scale.y = dist / b.length;
        }
      }
    }
    frame[i] = bone_on_parent(b, parent_frame, parent_rest, bone_local(b.position, b.angle, b.scale), setup_frame);
  }
}

void armature_select_joints_in(Layer &armature, bool setup_frame, const std::function<bool(float2)> &inside,
                               bool extend, bool deselect, const std::vector<const Layer *> *panels)
{
  const std::vector<const Layer *> own{&armature};
  const std::vector<const Layer *> &through = panels ? *panels : own;
  const std::vector<BonePose> poses = armature_keyed_pose(armature, setup_frame);
  if (!extend && !deselect) {
    armature_deselect_all(armature);
  }
  uint64_t first = 0;
  for (size_t i = 0; i < armature.bones.size(); i++) {
    if (!bone_shown(through, armature.bones[i])) {
      continue;
    }
    Bone &b = armature.bones[i];
    bool h = inside(poses[i].head), t = inside(poses[i].tail);
    /* Posing, as Blender's pose mode: a bone either end of which is inside is picked whole. */
    if (!setup_frame && (h || t)) {
      h = t = true;
    }
    if (h) {
      b.select_head = !deselect;
      if (Bone *parent = b.connected && deselect ? bone_find(armature, b.parent) : nullptr) {
        parent->select_tail = false;
      }
    }
    if (t) {
      b.select_tail = !deselect;
      if (deselect) {
        for (Bone &child : armature.bones) {
          if (child.connected && child.parent == b.id) {
            child.select_head = false;
          }
        }
      }
    }
    if ((h || t) && !deselect && first == 0) {
      first = b.id;
    }
  }
  armature_flush_selection(armature);
  const Bone *active = bone_find(armature, armature.active_bone);
  if (first && (!active || !bone_picked(*active))) {
    armature.active_bone = first;
  }
}

void armature_select_bones_in(Layer &armature, bool setup_frame, const std::function<bool(float2)> &inside,
                              bool extend, bool deselect, const std::vector<const Layer *> *panels)
{
  const std::vector<const Layer *> own{&armature};
  const std::vector<const Layer *> &through = panels ? *panels : own;
  const std::vector<BonePose> poses = armature_keyed_pose(armature, setup_frame);
  if (!extend && !deselect) {
    armature_deselect_all(armature);
  }
  uint64_t first = 0;
  for (size_t i = 0; i < armature.bones.size(); i++) {
    if (!bone_shown(through, armature.bones[i])) {
      continue;
    }
    /* Any of eleven points along the bone, as Moho's gizmo tests. */
    bool hit = false;
    for (int j = 0; j <= 10 && !hit; j++) {
      hit = inside(poses[i].head + (poses[i].tail - poses[i].head) * (float(j) / 10.0f));
    }
    if (hit) {
      bone_select(armature.bones[i], !deselect);
      if (!deselect && first == 0) {
        first = armature.bones[i].id;
      }
    }
  }
  const Bone *active = bone_find(armature, armature.active_bone);
  if (first && (!active || !bone_picked(*active))) {
    armature.active_bone = first;
  }
}

void armature_mirror_edits(Layer &armature, const std::vector<Bone> &original, bool setup_frame)
{
  const std::vector<BonePose> before =
      bones_full_pose(original, setup_frame, armature.pose_frame, nullptr);
  const std::vector<BonePose> after = armature_keyed_pose(armature, setup_frame);
  const size_t n = armature.bones.size();
  if (before.size() != n) {
    return;
  }
  std::map<uint64_t, int> index;
  for (int i = 0; i < int(n); i++) {
    index[armature.bones[i].id] = i;
  }
  std::vector<bool> changed(n);
  for (size_t i = 0; i < n; i++) {
    /* Past rounding: a bone that was only rebuilt in place didn't move. */
    changed[i] = distance(before[i].head, after[i].head) > 1e-5f || distance(before[i].tail, after[i].tail) > 1e-5f;
  }
  /* Each bone that moved drives its other side, unless that side moved too (both picked). */
  std::vector<int> source(n, -1);
  for (size_t i = 0; i < n; i++) {
    if (!changed[i]) {
      continue;
    }
    const auto m = index.find(bone_mirror_id(armature, armature.bones[i].id));
    if (m != index.end() && m->second != int(i) && !changed[m->second]) {
      source[m->second] = int(i);
    }
  }
  const auto reflect = [](float2 p) { return float2(-p.x, p.y); };
  std::vector<Transform2D> frame(n), rest(n);
  for (const int i : bones_parents_first(armature)) {
    Bone &b = armature.bones[i];
    const auto parent = index.find(b.parent);
    const bool has_parent = parent != index.end() && parent->second != i;
    const Transform2D parent_frame = has_parent ? frame[parent->second] : bone_outer_frame(b, setup_frame);
    const Transform2D parent_rest = has_parent ? rest[parent->second] : bone_outer_frame(b, true);
    rest[i] = parent_rest * bone_local(b.setup_position, b.setup_angle, setup_value(b.scale_keys, b.scale, false));
    if (source[i] >= 0) {
      const Bone &src = armature.bones[source[i]];
      const Transform2D to_parent = parent_frame.inverted();
      const Transform2D to_axes = bone_parent_axes(b, parent_frame, parent_rest, setup_frame).inverted();
      const float2 h = to_parent.apply(reflect(after[source[i]].head));
      const float2 t = h + to_axes.apply_vector(reflect(after[source[i]].tail) - reflect(after[source[i]].head));
      b.position = h;
      if (distance(h, t) > 1e-7f) {
        float angle = std::atan2(t.y - h.y, t.x - h.x);
        angle += 2.0f * PI * std::round((b.angle - angle) / (2.0f * PI));
        b.angle = angle;
      }
      b.scale = src.scale;
      /* Length isn't animated: only the setup pose takes the other side's. */
      if (setup_frame) {
        b.length = src.length;
      }
    }
    frame[i] = bone_on_parent(b, parent_frame, parent_rest, bone_local(b.position, b.angle, b.scale), setup_frame);
  }
  if (setup_frame) {
    /* The other side's bones that followed move whole; what hangs from them stays, as on this side. */
    std::vector<std::pair<bool, bool>> moves = picked_joints(armature);
    for (size_t i = 0; i < n; i++) {
      if (source[i] >= 0) {
        moves[i] = {true, true};
      }
    }
    hold_still_joints(armature, original, moves);
  }
}

/* Left and Right anywhere in `name`, the first found swapped. */
static std::string side_words_flipped(const std::string &name)
{
  static const std::pair<const char *, const char *> words[] = {{"Left", "Right"}, {"left", "right"}, {"LEFT", "RIGHT"}};
  for (const auto &[l, r] : words) {
    for (const auto &[from, to] : {std::pair{l, r}, std::pair{r, l}}) {
      if (const size_t at = name.find(from); at != std::string::npos) {
        return name.substr(0, at) + to + name.substr(at + std::string(from).size());
      }
    }
  }
  return name;
}

std::string bone_mirror_name(const std::string &name)
{
  /* A number at the end stays there, after a dot (Blender's unique names), a space (Moho's copies) or
   * an underscore: "arm_L.001" <-> "arm_R.001", "Eye_Lash_L 2" <-> "Eye_Lash_R 2". */
  if (const size_t sep = name.find_last_of(". _"); sep != std::string::npos && sep > 0 && sep + 1 < name.size() &&
                                                    name.find_first_not_of("0123456789", sep + 1) == std::string::npos)
  {
    const std::string base = name.substr(0, sep);
    const std::string flipped = bone_mirror_name(base);
    if (flipped != base) {
      return flipped + name.substr(sep);
    }
  }
  /* Suffixes first (_L, .L, -L, " L", either case), then prefixes (L_, L., L-, "L ", either case), then
   * Left/Right anywhere. */
  static const std::pair<const char *, const char *> suffixes[] = {
      {"_L", "_R"}, {".L", ".R"}, {"-L", "-R"}, {" L", " R"}, {"_l", "_r"}, {".l", ".r"}, {"-l", "-r"}, {" l", " r"}};
  for (const auto &[l, r] : suffixes) {
    for (const auto &[from, to] : {std::pair{l, r}, std::pair{r, l}}) {
      const std::string f = from;
      if (name.size() > f.size() && name.compare(name.size() - f.size(), f.size(), f) == 0) {
        return name.substr(0, name.size() - f.size()) + to;
      }
    }
  }
  static const std::pair<const char *, const char *> prefixes[] = {
      {"L_", "R_"}, {"L.", "R."}, {"L-", "R-"}, {"L ", "R "}, {"l_", "r_"}, {"l.", "r."}, {"l-", "r-"}, {"l ", "r "}};
  for (const auto &[l, r] : prefixes) {
    for (const auto &[from, to] : {std::pair{l, r}, std::pair{r, l}}) {
      const std::string f = from;
      if (name.size() > f.size() && name.compare(0, f.size(), f) == 0) {
        return to + name.substr(f.size());
      }
    }
  }
  return side_words_flipped(name);
}

std::string action_mirror_name(const std::string &action, const std::string &bone)
{
  /* "Pupil_L Left" of bone Pupil_L: the bone's side and the way it goes both flip, "Pupil_R Right". Flipping only the
   * first side found would give "Pupil_L Right", the same bone's other action. */
  const std::string other = bone_mirror_name(bone);
  const size_t at = other != bone && !bone.empty() ? action.find(bone) : std::string::npos;
  if (at == std::string::npos) {
    return bone_mirror_name(action);
  }
  return side_words_flipped(action.substr(0, at)) + other + side_words_flipped(action.substr(at + bone.size()));
}

uint64_t bone_mirror_id(const Layer &armature, uint64_t id)
{
  const Bone *bone = bone_find(armature, id);
  if (!bone) {
    return id;
  }
  const std::string other = bone_mirror_name(bone->name);
  if (other == bone->name) {
    return id;
  }
  const Bone *mirror = bone_find_by_name(armature, other);
  return mirror ? mirror->id : id;
}

static const Layer *armature_in(const std::vector<Layer> &list, const Layer *armature, uint64_t id)
{
  for (const Layer &layer : list) {
    if (layer.id == id) {
      return armature;
    }
    if (const Layer *found = armature_in(layer.children, layer.is_bone_layer() ? &layer : armature, id)) {
      return found;
    }
  }
  return nullptr;
}

static Color hex_color(unsigned rgb)
{
  return {float((rgb >> 16) & 0xff) / 255.0f, float((rgb >> 8) & 0xff) / 255.0f, float(rgb & 0xff) / 255.0f, 1.0f};
}

/* Blender's default theme (release/datafiles/userdef/userdef_default_theme.c, `tarm`), and its
 * Default Colors as Open Animate draws bones. */
static const struct {
  const char *name;
  unsigned regular, select, active;
} BONE_COLOR_SETS[BONE_COLOR_THEME_SETS + 1] = {
    {"Default Colors", 0x9a9a9a, 0xff8c00, 0xffc050}, {"01 - Red", 0x9a0000, 0xbd1111, 0xf70a0a},
    {"02 - Orange", 0xf74018, 0xf66913, 0xfa9900},    {"03 - Green", 0x1e9109, 0x59b70b, 0x83ef1d},
    {"04 - Blue", 0x0a3694, 0x3667df, 0x5ec1ef},      {"05 - Pink", 0xa9294e, 0xc1416a, 0xf05d91},
    {"06 - Purple", 0x430c78, 0x543aa3, 0x8764d5},    {"07 - Teal", 0x24785a, 0x3c9579, 0x6fb6ab},
    {"08 - Slate", 0x4b707c, 0x6a8691, 0x9bc2cd},     {"09 - Yellow", 0xf4c90c, 0xeec236, 0xf3ff00},
    {"10 - Black", 0x1e2024, 0x484c56, 0xffffff},     {"11 - Magenta", 0x6f2f6a, 0x9845be, 0xd330d6},
    {"12 - Lime", 0x6c8e22, 0x7fb022, 0xbbef5b},      {"13 - Gray", 0x8d8d8d, 0xb0b0b0, 0xdedede},
    {"14 - Brown", 0x834326, 0x8b5811, 0xbd6a11},     {"15 - Dark Green", 0x08310e, 0x1c430b, 0x34622b}};

BoneColors bone_color_set(int set)
{
  const auto &s = BONE_COLOR_SETS[std::clamp(set, 0, BONE_COLOR_THEME_SETS)];
  return {hex_color(s.regular), hex_color(s.select), hex_color(s.active)};
}

const char *bone_color_set_name(int set)
{
  return set == BONE_COLOR_CUSTOM ? "Custom Color Set" : BONE_COLOR_SETS[std::clamp(set, 0, BONE_COLOR_THEME_SETS)].name;
}

std::string bone_color_set_identifier(int set)
{
  if (set == BONE_COLOR_CUSTOM) {
    return "CUSTOM";
  }
  if (set <= 0 || set > BONE_COLOR_THEME_SETS) {
    return "DEFAULT";
  }
  return std::string(set < 10 ? "THEME0" : "THEME") + std::to_string(set);
}

int bone_color_set_from_identifier(const std::string &identifier)
{
  for (int set = 0; set <= BONE_COLOR_CUSTOM; set++) {
    if (bone_color_set_identifier(set) == identifier) {
      return set;
    }
  }
  return -1;
}

BoneColors bone_colors(const Bone &bone)
{
  if (bone.color_set == BONE_COLOR_CUSTOM) {
    return {bone.custom_colors[0], bone.custom_colors[1], bone.custom_colors[2]};
  }
  return bone_color_set(bone.color_set);
}

void bone_set_color_set(Bone &bone, int set)
{
  if (set == BONE_COLOR_CUSTOM && bone.color_set != BONE_COLOR_CUSTOM) {
    const BoneColors from = bone_colors(bone);
    bone.custom_colors = {from.regular, from.select, from.active};
  }
  bone.color_set = std::clamp(set, 0, BONE_COLOR_CUSTOM);
}

BoneColors layer_colors(const Layer &layer)
{
  if (layer.color_set == BONE_COLOR_CUSTOM) {
    return {layer.custom_colors[0], layer.custom_colors[1], layer.custom_colors[2]};
  }
  return bone_color_set(layer.color_set);
}

void layer_set_color_set(Layer &layer, int set)
{
  if (set == BONE_COLOR_CUSTOM && layer.color_set != BONE_COLOR_CUSTOM) {
    const BoneColors from = layer_colors(layer);
    layer.custom_colors = {from.regular, from.select, from.active};
  }
  layer.color_set = std::clamp(set, 0, BONE_COLOR_CUSTOM);
}

Collection *collection_find(Document &doc, uint64_t id)
{
  for (Collection &c : doc.collections) {
    if (c.id == id && id != 0) {
      return &c;
    }
  }
  return nullptr;
}

const Collection *collection_find(const Document &doc, uint64_t id)
{
  return collection_find(const_cast<Document &>(doc), id);
}

Collection *collection_find_by_name(Document &doc, const std::string &name)
{
  for (Collection &c : doc.collections) {
    if (c.name == name) {
      return &c;
    }
  }
  return nullptr;
}

const Collection *collection_find_by_name(const Document &doc, const std::string &name)
{
  return collection_find_by_name(const_cast<Document &>(doc), name);
}

std::string collection_name(const Document &doc, uint64_t id)
{
  const Collection *c = collection_find(doc, id);
  return c ? c->name : std::string();
}

std::string collection_unique_name(const Document &doc, const std::string &name)
{
  const auto taken = [&](const std::string &n) {
    return n == BONE_COLLECTION_ALL || collection_find_by_name(doc, n) != nullptr;
  };
  const std::string base = name.empty() ? "Collection" : name;
  if (!taken(base)) {
    return base;
  }
  for (int i = 1;; i++) {
    char suffix[16];
    std::snprintf(suffix, sizeof(suffix), ".%03d", i);
    if (!taken(base + suffix)) {
      return base + suffix;
    }
  }
}

Collection &collection_new(Document &doc, const std::string &name)
{
  Collection c;
  c.id = doc.next_collection_id++;
  c.name = collection_unique_name(doc, name);
  doc.collections.push_back(std::move(c));
  return doc.collections.back();
}

Collection *collection_ensure(Document &doc, const std::string &name)
{
  if (name.empty() || name == BONE_COLLECTION_ALL) {
    return nullptr;
  }
  Collection *c = collection_find_by_name(doc, name);
  return c ? c : &collection_new(doc, name);
}

static void collection_drop(std::vector<Layer> &list, uint64_t id)
{
  for (Layer &l : list) {
    std::erase(l.collections, id);
    for (Bone &b : l.bones) {
      std::erase(b.collections, id);
    }
    bone_collection_remove(l, id);
    collection_drop(l.children, id);
  }
}

static int collection_empty(std::vector<Layer> &list, uint64_t id)
{
  int left = 0;
  for (Layer &l : list) {
    left += int(std::erase(l.collections, id));
    for (Bone &b : l.bones) {
      left += int(std::erase(b.collections, id));
    }
    left += collection_empty(l.children, id);
  }
  return left;
}

void collection_selected_change(Document &doc, Layer &armature, uint64_t id, bool assign, int *r_bones,
                                int *r_drawings)
{
  /* As armature.collection_assign and _unassign find them: what they would change. */
  const auto changes = [&](const std::vector<uint64_t> &ids) {
    return (std::find(ids.begin(), ids.end(), id) != ids.end()) != assign;
  };
  *r_bones = 0;
  *r_drawings = 0;
  for (const Bone &b : armature.bones) {
    *r_bones += (b.selected || b.select_head || b.select_tail) && changes(b.collections);
  }
  for (const Layer *d : collection_drawings(doc, armature)) {
    *r_drawings += changes(d->collections);
  }
}

std::string collection_change_text(int bones, int drawings)
{
  std::string text;
  if (bones > 0) {
    text = std::to_string(bones) + (bones == 1 ? " bone" : " bones");
  }
  if (drawings > 0) {
    text += (text.empty() ? "" : ", ") + std::to_string(drawings) + (drawings == 1 ? " drawing" : " drawings");
  }
  return text;
}

int collection_layers_change(Document &doc, uint64_t layer, uint64_t id, bool assign)
{
  /* As layer.collection_link with all: the layer and every picked one. */
  int n = 0;
  for (const Layer *l : document_layers_flat(doc)) {
    if ((l->selected || l->id == layer) &&
        (std::find(l->collections.begin(), l->collections.end(), id) != l->collections.end()) != assign)
    {
      n++;
    }
  }
  return n;
}

std::string collection_layers_change_text(int layers)
{
  return layers == 0 ? std::string() : std::to_string(layers) + (layers == 1 ? " layer" : " layers");
}

int collection_unassign_all(Document &doc, uint64_t id)
{
  return collection_empty(doc.layers, id);
}

void collection_delete(Document &doc, uint64_t id)
{
  std::erase_if(doc.collections, [&](const Collection &c) { return c.id == id; });
  collection_drop(doc.layers, id);
}

std::vector<std::string> collection_names(const Document &doc, const std::vector<uint64_t> &ids)
{
  std::vector<std::string> names;
  for (const uint64_t id : ids) {
    if (const Collection *c = collection_find(doc, id)) {
      names.push_back(c->name);
    }
  }
  return names;
}

BoneCollection *bone_collection_find(Layer &armature, uint64_t id)
{
  for (BoneCollection &c : armature.bone_collections) {
    if (c.id == id && id != 0) {
      return &c;
    }
  }
  return nullptr;
}

const BoneCollection *bone_collection_find(const Layer &armature, uint64_t id)
{
  return bone_collection_find(const_cast<Layer &>(armature), id);
}

BoneCollection *bone_collection_find_by_name(const Document &doc, Layer &armature, const std::string &name)
{
  const Collection *c = collection_find_by_name(doc, name);
  return c ? bone_collection_find(armature, c->id) : nullptr;
}

static bool any_solo(const Layer &armature)
{
  return armature.all_bones_solo || std::any_of(armature.bone_collections.begin(), armature.bone_collections.end(),
                                                [](const BoneCollection &c) { return c.solo; });
}

bool bone_collection_all_shown(const Layer &armature)
{
  return any_solo(armature) ? armature.all_bones_solo : armature.all_bones_visible;
}

bool bone_collection_shown(const Layer &armature, const BoneCollection &collection)
{
  return any_solo(armature) ? collection.solo : collection.visible;
}

bool bone_collections_show(const Layer &armature, const std::vector<uint64_t> &collections)
{
  /* As in Blender: shown while any collection holding it shows; All holds everything. One in none of the panel's
   * collections (in no collection at all, or, seen from a bone layer around its own, in none on this panel) has
   * nothing here to hide it, so it shows even with All hidden, as Blender shows bones in no collection. */
  if (bone_collection_all_shown(armature)) {
    return true;
  }
  bool held = false;
  for (const uint64_t id : collections) {
    if (const BoneCollection *c = bone_collection_find(armature, id)) {
      if (bone_collection_shown(armature, *c)) {
        return true;
      }
      held = true;
    }
  }
  return !held;
}

bool bone_shown(const Layer &armature, const Bone &bone)
{
  return bone_collections_show(armature, bone.collections);
}

std::vector<const Layer *> bone_panels(const Document &doc, const Layer &armature)
{
  const Layer *worked = layer_find(doc, doc.active_layer);
  if (!worked || worked == &armature || !worked->is_bone_layer() || !armature.sub_bone_group) {
    return {&armature};
  }
  /* Down from the bone layer worked in through the sub bone groups shown inside it, as editable_layers walks. */
  std::vector<const Layer *> path{worked};
  const auto find = [&](auto &&self, const Layer &parent) -> bool {
    for (const Layer &layer : parent.children) {
      if (!layer.is_bone_layer()) {
        if (self(self, layer)) {
          return true;
        }
      }
      else if (layer.sub_bone_group && layer.shown()) {
        path.push_back(&layer);
        if (&layer == &armature || self(self, layer)) {
          return true;
        }
        path.pop_back();
      }
    }
    return false;
  };
  return find(find, *worked) ? path : std::vector<const Layer *>{&armature};
}

bool bone_shown(const std::vector<const Layer *> &panels, const Bone &bone)
{
  return std::all_of(panels.begin(), panels.end(),
                     [&](const Layer *panel) { return bone_collections_show(*panel, bone.collections); });
}

bool layer_edited_with_bones(const Document &doc, const Layer &layer)
{
  const Layer *armature = layer.edit_with_bones && layer.type == LayerType::Vector ? layer_armature(doc, layer.id)
                                                                                    : nullptr;
  return armature && bone_collections_show(*armature, layer.collections);
}

BoneCollection &bone_collection_add(Layer &armature, uint64_t id)
{
  if (BoneCollection *had = bone_collection_find(armature, id)) {
    armature.active_collection = id;
    return *had;
  }
  BoneCollection c;
  c.id = id;
  /* After the active one (All, first of all, puts it at the top). */
  auto at = bone_collection_find(armature, armature.active_collection) ? armature.bone_collections.end()
                                                                         : armature.bone_collections.begin();
  for (auto it = armature.bone_collections.begin(); it != armature.bone_collections.end(); ++it) {
    if (it->id == armature.active_collection) {
      at = it + 1;
    }
  }
  at = armature.bone_collections.insert(at, std::move(c));
  armature.active_collection = at->id;
  return *at;
}

void bone_collection_ensure(Layer &armature, uint64_t id)
{
  if (id != 0 && !bone_collection_find(armature, id)) {
    BoneCollection c;
    c.id = id;
    armature.bone_collections.push_back(c);
  }
}

void bone_collection_remove(Layer &armature, uint64_t id)
{
  const auto it = std::find_if(armature.bone_collections.begin(), armature.bone_collections.end(),
                               [&](const BoneCollection &c) { return c.id == id; });
  if (it == armature.bone_collections.end()) {
    return;
  }
  const size_t at = size_t(it - armature.bone_collections.begin());
  armature.bone_collections.erase(it);
  if (armature.active_collection == id) {
    /* The one before it (All before the first). */
    armature.active_collection = at == 0 ? 0 : armature.bone_collections[at - 1].id;
  }
}

Layer *collection_armature(Document &doc)
{
  Layer *active = document_active_layer(doc);
  if (!active) {
    return nullptr;
  }
  if (active->is_bone_layer()) {
    return active;
  }
  return active->type == LayerType::Vector ? const_cast<Layer *>(layer_armature(doc, active->id)) : nullptr;
}

std::vector<Layer *> collection_drawings(Document &doc, const Layer &armature)
{
  std::vector<Layer *> drawings;
  for (const Layer *l : document_layers_flat(doc)) {
    /* Picked in the Layers editor, the active layer, or selected in the viewport: a drawing edited
     * along with the bones with some of its points (or handles) selected. */
    const auto points_picked = [&] {
      if (!layer_edited_with_bones(doc, *l)) {
        return false;
      }
      for (const MeshPoint &p : l->drawing.points) {
        if (p.selected) {
          return true;
        }
      }
      for (const Curve &curve : l->drawing.curves) {
        for (const CurvePoint &cp : curve.points) {
          if (cp.select_in || cp.select_out) {
            return true;
          }
        }
      }
      return false;
    };
    if (l->type != LayerType::Vector || !l->edit_with_bones ||
        !(l->selected || l->id == doc.active_layer || points_picked()))
    {
      continue;
    }
    if (const Layer *owner = layer_armature(doc, l->id); owner && owner->id == armature.id) {
      drawings.push_back(layer_find(doc, l->id));
    }
  }
  return drawings;
}

void collection_targets(Document &doc, bool in_layers, std::vector<Bone *> &r_bones, std::vector<Layer *> &r_layers)
{
  Layer *active = document_active_layer(doc);
  if (!in_layers && active && active->is_bone_layer()) {
    for (Bone &b : active->bones) {
      if (b.selected || b.select_head || b.select_tail) {
        r_bones.push_back(&b);
      }
    }
    r_layers = collection_drawings(doc, *active);
    return;
  }
  for (const Layer *l : document_layers_flat(doc)) {
    if (l->selected || l->id == doc.active_layer) {
      r_layers.push_back(layer_find(doc, l->id));
    }
  }
}

void armature_deselect_hidden(Layer &armature)
{
  for (Bone &b : armature.bones) {
    if (!bone_shown(armature, b)) {
      b.selected = b.select_head = b.select_tail = false;
    }
  }
}

const Layer *layer_armature(const Document &doc, uint64_t layer_id)
{
  /* By the index: the nearest bone layer above it. */
  if (layer_index_active(doc)) {
    Document &d = const_cast<Document &>(doc);
    if (!layer_find(d, layer_id)) {
      return nullptr;
    }
    for (const Layer *p = layer_parent(d, layer_id); p; p = layer_parent(d, p->id)) {
      if (p->is_bone_layer()) {
        return p;
      }
    }
    return nullptr;
  }
  return armature_in(doc.layers, nullptr, layer_id);
}

static const Layer *binding_group_in(const std::vector<Layer> &list, const Layer *group, uint64_t id)
{
  for (const Layer &layer : list) {
    if (layer.id == id) {
      return group;
    }
    /* A bone layer starts again: groups above it bind to another skeleton. */
    const Layer *inside = layer.is_bone_layer()                                 ? nullptr
                          : !group && layer.is_group() && layer.parent_bone != 0 ? &layer
                                                                                 : group;
    if (const Layer *found = binding_group_in(layer.children, inside, id)) {
      return found;
    }
  }
  return nullptr;
}

const Layer *layer_binding_group(const Document &doc, uint64_t layer_id)
{
  /* By the index: the layer's groups, from the top down, as binding_group_in passes them. */
  if (layer_index_active(doc)) {
    std::vector<const Layer *> above;
    for (const Layer *p = layer_parent(const_cast<Document &>(doc), layer_id); p;
         p = layer_parent(const_cast<Document &>(doc), p->id))
    {
      above.push_back(p);
    }
    const Layer *group = nullptr;
    for (auto it = above.rbegin(); it != above.rend(); ++it) {
      const Layer &layer = **it;
      group = layer.is_bone_layer() ? nullptr : !group && layer.is_group() && layer.parent_bone != 0 ? &layer : group;
    }
    return group;
  }
  return binding_group_in(doc.layers, nullptr, layer_id);
}

Transform2D bone_outer_frame(const Bone &bone, bool setup_frame)
{
  return bone.outer_bone == 0 ? Transform2D() : setup_frame ? bone.outer_setup : bone.outer_pose;
}

void bones_mark_carried(Document &doc, const std::vector<Layer *> &moving)
{
  const auto root_of = [](const Layer &rig, const Bone *b) {
    for (int guard = 0; guard < 256; guard++) {
      const Bone *up = bone_find(rig, b->parent);
      if (!up || up == b) {
        break;
      }
      b = up;
    }
    return b;
  };
  for (Layer *rig : moving) {
    for (Bone &b : rig->bones) {
      b.outer_carried = false;
      const Bone *root = root_of(*rig, &b);
      /* Up through the bone layers around it, as far as bones hang there. */
      for (int guard = 0; guard < 64 && root && root->outer_bone != 0 && !b.outer_carried; guard++) {
        const uint64_t id = root->outer_layer;
        const Layer *outer = std::find_if(moving.begin(), moving.end(), [&](const Layer *l) { return l->id == id; }) != moving.end()
                                 ? layer_find(doc, id)
                                 : nullptr;
        const Bone *parent = outer ? bone_find(*outer, root->outer_bone) : nullptr;
        for (const Bone *at = parent; at && !b.outer_carried; at = at->parent != at->id ? bone_find(*outer, at->parent) : nullptr) {
          b.outer_carried = bone_picked(*at);
        }
        root = parent ? root_of(*outer, parent) : nullptr;
      }
    }
  }
}

void bone_outer_parents_update(Document &doc)
{
  const bool setup_frame = doc.frame_current == 0;
  std::map<uint64_t, std::vector<BonePose>> poses;
  std::vector<const Layer *> around;
  const auto visit = [&](auto &&self, std::vector<Layer> &list) -> void {
    for (Layer &layer : list) {
      if (!layer.is_bone_layer()) {
        self(self, layer.children);
        continue;
      }
      for (Bone &b : layer.bones) {
        if (b.outer_bone == 0) {
          continue;
        }
        const auto outer = std::find_if(around.begin(), around.end(), [&](const Layer *l) { return l->id == b.outer_layer; });
        const BonePose *parent = nullptr;
        if (outer != around.end()) {
          const auto it = poses.find(b.outer_layer);
          parent = bone_pose_find(it != poses.end() ? it->second : (poses[b.outer_layer] = armature_pose(**outer, setup_frame)),
                                  b.outer_bone);
        }
        if (parent) {
          b.outer_setup = layer_setup_relative_transform(doc, layer.id, b.outer_layer) * parent->setup;
          b.outer_pose = layer_relative_transform(doc, layer.id, b.outer_layer) * parent->pose;
          continue;
        }
        const Transform2D rest = b.outer_setup * bone_local(b.setup_position, b.setup_angle, {1.0f, 1.0f});
        const float2 position = {rest.tx, rest.ty};
        const float angle = transform_angle(rest);
        b.position += position - b.setup_position;
        b.angle += angle - b.setup_angle;
        b.setup_position = position;
        b.setup_angle = angle;
        b.outer_layer = b.outer_bone = 0;
        b.outer_setup = b.outer_pose = Transform2D();
      }
      around.push_back(&layer);
      self(self, layer.children);
      around.pop_back();
      poses.erase(layer.id);
    }
  };
  visit(visit, doc.layers);
}

static bool sync_in(std::vector<Layer> &list, bool inside)
{
  bool changed = false;
  for (Layer &layer : list) {
    if (!layer.is_group()) {
      const auto is_armature = [](const Modifier &m) { return m.type == ModifierType::Armature; };
      const long count = long(std::count_if(layer.modifiers.begin(), layer.modifiers.end(), is_armature));
      if (inside && count != 1) {
        std::erase_if(layer.modifiers, is_armature);
        Modifier armature;
        armature.type = ModifierType::Armature;
        armature.name = "Armature";
        layer.modifiers.push_back(armature);
        changed = true;
      }
      else if (!inside && count > 0) {
        std::erase_if(layer.modifiers, is_armature);
        changed = true;
      }
    }
    changed |= sync_in(layer.children, inside || layer.is_bone_layer());
  }
  return changed;
}

bool document_sync_armature_modifiers(Document &doc)
{
  return sync_in(doc.layers, false);
}

}  // namespace oanim
