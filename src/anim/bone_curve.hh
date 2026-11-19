#pragma once

/* Bendy bones: each bone bends along a cubic curve from its head to its tail, shaped by a handle at each end (the curve
 * channels on Bone). At a joint between connected bones there are two handles, the parent's tail's and the child's
 * head's, kept on the child; at a free end, one. A joint left alone is lined up and carries the curve through it
 * smoothly; an end left alone mirrors the other end, so the bone is an arc. Drawings whose Parent Bone has Deform: Curve
 * bend along the curve of their bone, or of a chain of connected bones (Layer::parent_bone_chain_end). */

#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

#include "core/math.hh"
#include "data/layer.hh"

namespace oanim {

struct BonePose;

/* Calls f(name, value, keys) for each of a bone's curve channels (`bone` a Bone or const Bone). */
template<typename B, typename F> void bone_curve_channels(B &bone, F &&f)
{
  f(std::string_view("curve_turn"), bone.curve_turn, bone.curve_turn_keys);
  f(std::string_view("curve_lined"), bone.curve_lined, bone.curve_lined_keys);
  f(std::string_view("curve_head_angle"), bone.curve_head_angle, bone.curve_head_angle_keys);
  f(std::string_view("curve_parent_angle"), bone.curve_parent_angle, bone.curve_parent_angle_keys);
  f(std::string_view("curve_head_reach"), bone.curve_head_reach, bone.curve_head_reach_keys);
  f(std::string_view("curve_parent_reach"), bone.curve_parent_reach, bone.curve_parent_reach_keys);
  f(std::string_view("curve_tail_turn"), bone.curve_tail_turn, bone.curve_tail_turn_keys);
  f(std::string_view("curve_tail_lined"), bone.curve_tail_lined, bone.curve_tail_lined_keys);
  f(std::string_view("curve_tail_angle"), bone.curve_tail_angle, bone.curve_tail_angle_keys);
  f(std::string_view("curve_tail_reach"), bone.curve_tail_reach, bone.curve_tail_reach_keys);
}
/* A curve channel's value as it rests (lined and reach 1, the rest 0). */
float bone_curve_channel_default(std::string_view name);
/* Whether a curve channel is an angle (mirroring a bone turns it the other way). */
bool bone_curve_channel_is_angle(std::string_view name);
/* Puts every curve channel of `bone` (not its keys) back to rest. */
void bone_curve_values_reset(Bone &bone);

/* Whether a bone has a curve: a regular bone (a pin or a 2 Axis Controller is straight, and bends nothing). */
bool bone_curve_has(const Bone &bone);
/* The connected parent a bone's head joint is shared with (its index; -1: none, its head is an end). */
int bone_curve_parent(const Layer &armature, size_t i);
/* The one connected child a bone's tail joint is shared with (its index; -1: none, or several, its tail an end). */
int bone_curve_kid(const Layer &armature, size_t i);

/* How a bone's curve leaves its two ends: each handle's angle to the bone (head: from the head toward the tail; tail:
 * arriving at the tail) and its reach (1: an arc's). */
struct BoneCurveShape {
  float angle = 0.0f, length = 0.0f;
  int parent = -1, kid = -1;
  float head_turn = 0.0f, tail_turn = 0.0f;
  /* What a free end mirrors: the other end's turn, mirrored (0 with both ends free). */
  float head_mirror = 0.0f, tail_mirror = 0.0f;
  float head_reach = 1.0f, tail_reach = 1.0f;
};
/* `rest`: as the bones rest (frame 0's channels, the setup pose), else as they are now. `setup_frame`: the document is
 * on frame 0, where an edit not yet recorded is the rest. */
BoneCurveShape bone_curve_shape(const Layer &armature, const std::vector<BonePose> &poses, size_t i, bool rest,
                                bool setup_frame = false);
/* The curve's four control points (bone layer space): head, head handle, tail handle, tail. */
std::array<float2, 4> bone_curve_controls(const Layer &armature, const std::vector<BonePose> &poses, size_t i,
                                          bool rest, bool setup_frame = false);
/* Whether the bone bends now (a handle off its line). */
bool bone_curve_bent(const Layer &armature, const std::vector<BonePose> &poses, size_t i);

/* A run of connected bones' curves as a line: points along it with their directions and how far along each is. */
struct BoneCurveLine {
  std::vector<float2> points, tangents;
  std::vector<float> along;
  /* How far along each bone starts, and the end. */
  std::vector<float> bone_starts;
  bool empty() const { return points.size() < 2; }
};
BoneCurveLine bone_curve_line(const Layer &armature, const std::vector<BonePose> &poses,
                              const std::vector<size_t> &chain, bool rest, bool setup_frame = false);
/* What carries a point at `q` (bone layer space) bound to the line as it rests, onto the line now: a turn and a move,
 * the point's nearest place on the rest line going where that place goes (past either end, the line carried straight
 * on), as far along each bone as it was. */
Transform2D bone_curve_line_skin(const BoneCurveLine &rest, const BoneCurveLine &now, float2 q);

/* The bones a drawing's Parent Bone bends it along (indices, head to tail): the Parent Bone and on through its connected
 * children to the chain's end; the Parent Bone alone if the end isn't reached that way. Empty: no curve (Deform isn't
 * Curve, or no such bone). */
std::vector<size_t> layer_curve_chain(const Layer &armature, const Layer &layer);
/* Whether `end` can end a chain from `start`: it is `start` or hangs from it through connected bones. */
bool bone_curve_chain_reaches(const Layer &armature, uint64_t start, uint64_t end);

/* --- Editing (the channels as now: on frame 0, the rest) ------------------------------------------------------- */

/* Drags the handle at bone i's head (`head`) or tail to `at` (bone layer space): its direction and reach. A joint
 * between connected bones lines its handles up again, both turning, unless `alone`, which breaks them (each then keeps
 * its angle to its own bone). An end keeps whether it is lined up or broken. */
void bone_curve_handle_set(Layer &armature, const std::vector<BonePose> &poses, size_t i, bool head, float2 at,
                           bool alone);
/* Flatten Both to Bone: both of bone i's handles along it, the bone straight; the handles across its joints stay where
 * they are (broken), so the bones beside it keep their curves. */
void bone_curve_flatten(Layer &armature, const std::vector<BonePose> &poses, size_t i);
/* Sharp Corner at the joint at bone i's head or tail: its handles along their bones (broken), the bones meeting in a
 * corner however they turn. */
void bone_curve_sharp_corner(Layer &armature, size_t i, bool head);
/* Reset Curve: both of bone i's ends as they rest (lined up, reach 1). */
void bone_curve_reset(Layer &armature, size_t i);
/* Where a handle is now (bone layer space). */
float2 bone_curve_handle_at(const Layer &armature, const std::vector<BonePose> &poses, size_t i, bool head);

}  // namespace oanim
