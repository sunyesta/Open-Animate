#include "anim/animation.hh"

#include "anim/drivers.hh"

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <functional>
#include <list>
#include <string_view>
#include <cstdlib>
#include <cmath>
#include <climits>
#include <memory>
#include <charconv>
#include <set>
#include <tuple>
#include <type_traits>
#include <typeinfo>
#include <unordered_set>
#include <variant>

#include "anim/action_mirror.hh"
#include "anim/bone_curve.hh"
#include "anim/controller.hh"
#include "anim/deform.hh"
#include "core/log.hh"
#include "core/parallel.hh"
#include "anim/dynamics.hh"
#include "anim/follow_point.hh"
#include "anim/motion_path.hh"
#include "anim/shape_limit.hh"
#include "anim/reference.hh"
#include "anim/switch.hh"
#include "data/bones.hh"
#include "data/camera.hh"
#include "data/document.hh"
#include "core/profile.hh"

namespace oanim {

/* A bone's channels besides its Transform and Angle (which are changes from its setup pose, worked out around them). */
template<typename F> static void bone_other_channels(Bone &bone, F &&f)
{
  f(bone.scale_keys, bone.scale);
  f(bone.depth_keys, bone.depth);
  bone_curve_channels(bone, [&](std::string_view, float &value, Channel<float> &keys) { f(keys, value); });
  for (BoneConstraint &c : bone.constraints) {
    f(c.influence_keys, c.influence);
    f(c.pin_keys, c.pin);
    f(c.follow_shift_keys, c.follow_shift);
    f(c.follow_shift2_keys, c.follow_shift2);
    f(c.follow_shift3_keys, c.follow_shift3);
    f(c.weight_keys, c.weight);
    f(c.wind_catch_keys, c.wind_catch);
    f(c.gravity_keys, c.gravity);
    f(c.wind_keys, c.wind);
    f(c.wind_direction_keys, c.wind_direction);
    f(c.wind_gusts_keys, c.wind_gusts);
    f(c.wind_gust_speed_keys, c.wind_gust_speed);
    f(c.wind_turbulence_keys, c.wind_turbulence);
    for (BoneSpring *s : {&c.angle_spring, &c.position_spring, &c.scale_spring}) {
      f(s->settle_speed_keys, s->settle_speed);
      f(s->bounce_keys, s->bounce);
      f(s->inertia_keys, s->inertia);
      f(s->stretch_keys, s->stretch);
      f(s->limit_keys, s->limit);
      f(s->squash_limit_keys, s->squash_limit);
    }
  }
}

/* Calls f(channel, value) for every channel of a layer (not its children). Without `sync` the
 * values aren't worked out (the points' and bones' changes from their setup): for reading keys only,
 * which the timeline does every frame. */
template<bool sync = true, typename F> static void layer_for_each_channel(Layer &layer, F &&f)
{
  for (CustomChannel &c : layer.custom_channels) {
    f(c.keys, c.value);
  }
  for (ActionPlay &a : layer.action_plays) {
    f(a.frame_keys, a.frame);
  }
  /* Visibility is a stepped number beside the plain `visible` flag. */
  if constexpr (sync) {
    layer.visible_value = layer.visible ? 1.0f : 0.0f;
  }
  f(layer.visible_keys, layer.visible_value);
  if constexpr (sync) {
    layer.visible = layer.visible_value > 0.5f;
    /* Keys pasted or opened from a file hold too. */
    for (Key<float> &k : layer.visible_keys.keys) {
      k.interp = Interp::Step;
    }
  }
  f(layer.draw_order_keys, layer.draw_order);
  if constexpr (sync) {
    for (Key<float> &k : layer.draw_order_keys.keys) {
      k.interp = Interp::Step;
    }
  }
  if (layer.is_switch()) {
    f(layer.switch_keys, layer.switch_value);
    if constexpr (sync) {
      for (Key<float> &k : layer.switch_keys.keys) {
        k.interp = Interp::Step;
      }
    }
  }
  f(layer.position_keys, layer.position);
  f(layer.rotation_keys, layer.rotation);
  f(layer.scale_keys, layer.scale);
  f(layer.shear_keys, layer.shear);
  f(layer.opacity_keys, layer.opacity);
  /* Before any bone's channels are touched: taking action bone actions off goes bone by bone, and a limit read halfway
   * would
   * see the bone's parent without what they add, the shape with it. */
  if constexpr (sync) {
    for (Bone &bone : layer.bones) {
      bone_shape_limit_affect(layer, bone);
    }
  }
  for (Bone &bone : layer.bones) {
    /* A bone's keys are its Transform and Angle: the change from its setup pose. */
    if constexpr (sync) {
      bone_changes_from_values(bone);
    }
    f(bone.position_keys, bone.transform);
    f(bone.angle_keys, bone.turn);
    if constexpr (sync) {
      bone_values_from_changes(bone);
    }
    bone_other_channels(bone, f);
  }
  for (LayerMask &m : layer.masks) {
    f(m.line_reach_keys, m.line_reach);
  }
  for (Modifier &m : layer.modifiers) {
    if (m.type == ModifierType::Boolean) {
      f(m.merge_smoothing_keys, m.merge_smoothing);
    }
    if (m.type == ModifierType::Bevel) {
      f(m.bevel_amount_keys, m.bevel_amount);
    }
    if (modifier_is_deform(m.type)) {
      f(m.deform_strength_keys, m.deform_strength);
    }
    if (m.type == ModifierType::FollowDeform) {
      f(m.deform_shift_keys, m.deform_shift);
      f(m.deform_shift2_keys, m.deform_shift2);
    }
  }
  /* A reference's drawing is built from its original's: its own channels are its offsets. */
  for (auto &[id, o] : layer.reference.points) {
    f(o.offset_keys, o.offset);
  }
  for (auto &[key, o] : layer.reference.handles) {
    f(o.offset_keys, o.offset);
  }
  if (layer.is_reference()) {
    return;
  }
  /* A point's keys are its Transform and a handle's its Angle and Length: the change from the setup
   * pose. */
  if constexpr (sync) {
    drawing_changes_from_values(layer.drawing);
  }
  for (MeshPoint &p : layer.drawing.points) {
    f(p.pos_keys, p.transform);
    f(p.radius_keys, p.radius);
  }
  for (Curve &curve : layer.drawing.curves) {
    for (CurvePoint &cp : curve.points) {
      f(cp.curvature_keys, cp.curvature);
      f(cp.handle_in_keys, cp.change_in);
      f(cp.handle_out_keys, cp.change_out);
    }
  }
  if constexpr (sync) {
    drawing_values_from_changes(layer.drawing);
  }
}

template<typename F> static void layers_for_each_channel(std::vector<Layer> &layers, F &&f)
{
  for (Layer &layer : layers) {
    layer_for_each_channel(layer, f);
    layers_for_each_channel(layer.children, f);
  }
}

/* While action bone actions are worked out again (animation_refresh_action_bones), the layers with any action bone
 * action data, found once: the rest are passed over without a look. (Each thread's: copies of the document are worked
 * out side by side, motion paths' places.) */
static thread_local const std::unordered_set<const Layer *> *g_action_bone_layers = nullptr;

/* As layers_for_each_channel, but only on the layers having a channel `wanted` says yes to. Looking costs
 * little; the walk itself turns every drawing's points into their changes from the setup pose and back,
 * which on a big rig is most of what action bone actions cost each time an action bone turns. */
template<typename P, typename F> static void layers_for_each_channel_if(std::vector<Layer> &layers, P &&wanted, F &&f)
{
  for (Layer &layer : layers) {
    if (g_action_bone_layers && !g_action_bone_layers->contains(&layer)) {
      layers_for_each_channel_if(layer.children, wanted, f);
      continue;
    }
    bool any = false;
    layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) { any = any || wanted(ch); });
    if (any) {
      layer_for_each_channel(layer, f);
    }
    layers_for_each_channel_if(layer.children, wanted, f);
  }
}

/* A channel with something an action bone action added to take off (or marked as played into). */
static constexpr auto action_bones_added = [](const auto &ch) {
  return ch.action_bone_live || ch.action_played.on || ch.action_slope.known ||
         !(ch.from_action_bones == std::decay_t<decltype(ch.from_action_bones)>{});
};

/* Adds to an unkeyed channel's slope (Channel::ActionSlope) what one action or fix does, `delta_at(setup)` being what it
 * adds from that setup: only where an edit not yet recorded sits on it. */
template<typename T, typename F>
static void action_slope_add(Channel<T> &ch, const T &value, const T &setup, const T &delta, F &&delta_at)
{
  if (ch.animated() || ch.constant || !ch.has_last || value == ch.last) {
    return;
  }
  T unit{};
  if constexpr (std::is_same_v<T, float>) {
    unit = 1.0f;
  }
  else {
    unit.x = 1.0f;
  }
  const T step = delta_at(setup + unit) - delta;
  if constexpr (std::is_same_v<T, float>) {
    ch.action_slope.slope += step;
  }
  else {
    ch.action_slope.slope += step.x;
  }
  ch.action_slope.known = true;
}

/* The layers with action bone action data: something added to take off, or keys in an action. An action bone being
 * turned has its actions worked out again every update, and a big rig's thousands of other layers have
 * nothing to do with them. */
static void find_action_bone_layers(std::vector<Layer> &layers, std::unordered_set<const Layer *> &r_found)
{
  for (Layer &layer : layers) {
    bool any = false;
    layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) {
      any = any || action_bones_added(ch) || !ch.actions.empty();
    });
    if (any) {
      r_found.insert(&layer);
    }
    find_action_bone_layers(layer.children, r_found);
  }
}

static void find_action_bone_layers(Document &doc, std::unordered_set<const Layer *> &r_found)
{
  find_action_bone_layers(doc.layers, r_found);
}

/* While a bone drag runs (animation_action_bone_drag_begin): its document and the layers found as it began. The
 * drag works action bone actions out again itself every update, its layers staying where they are. */
static const Document *g_drag_doc = nullptr;
static std::unordered_set<const Layer *> g_drag_layers;

/* Drawings a switch hides that come out the same on every frame (still): no keys, no action data, nothing action bone
 * actions added, no edit waiting, nothing in them worked out from elsewhere (bones, references, drivers, media,
 * switches). Found after a frame is evaluated, and kept while the edits the app can see coming (its stamp) and the
 * keys stay as they were: a frame change of the main loop's (playing) then neither records nor evaluates them,
 * and one shows on any frame as it is. On the 360 rig most of the document is such drawings. */
struct StillDrawings {
  const Document *doc = nullptr;
  uint64_t stamp = 0;
  bool valid = false;
  std::unordered_set<uint64_t> ids;
};
static StillDrawings g_still;
/* While a frame change of the main loop's is recorded and evaluated: the still drawings to leave as they are. */
static thread_local const std::unordered_set<uint64_t> *g_still_skip = nullptr;

/* A still drawing hidden now (in renders and the viewport alike): left as it is. */
static bool still_skipped(const Layer &layer)
{
  return g_still_skip && layer.switched_out && layer.edit_out && g_still_skip->contains(layer.id);
}

static bool layer_still(const Layer &layer, const std::unordered_set<uint64_t> &driven)
{
  if (layer.is_bone_layer() || layer.is_reference() || layer.is_media() || layer.is_switch() ||
      driven.contains(layer.id))
  {
    return false;
  }
  bool still = true;
  layer_for_each_channel<false>(const_cast<Layer &>(layer), [&](auto &ch, auto &value) {
    still = still && !ch.animated() && ch.actions.empty() && !action_bones_added(ch) && ch.has_last && ch.last == value;
  });
  if (!still) {
    return false;
  }
  return std::all_of(layer.children.begin(), layer.children.end(),
                     [&](const Layer &child) { return layer_still(child, driven); });
}

static void find_still_drawings(const Document &doc, std::unordered_set<uint64_t> &r_ids)
{
  std::unordered_set<uint64_t> driven;
  for (const Driver &d : doc.drivers) {
    driven.insert(d.target.layer);
  }
  const auto walk = [&](auto &&self, const std::vector<Layer> &layers) -> void {
    for (const Layer &layer : layers) {
      if (layer.is_switch()) {
        for (const Layer &child : layer.children) {
          if (layer_still(child, driven)) {
            r_ids.insert(child.id);
          }
        }
      }
      self(self, layer.children);
    }
  };
  walk(walk, doc.layers);
}

/* Whether the stretch from `a` to `b` is shaped on its motion path in a way no key put inside would make: control
 * points, Custom speeds, or path handles of their own at either end (dragged or set by type: Auto ones would take
 * new slopes from a new neighbour). */
template<typename K> static bool stretch_on_path(const K &a, const K &b)
{
  return !b.path_controls.empty() || b.interp == Interp::Custom || a.path_handles != PathHandles::Auto ||
         b.path_handles != PathHandles::Auto;
}

/* `ch`'s key on `frame` holding `base`. A new one inside a position's stretch shaped on its motion path (control
 * points, Custom speeds or path handles, which no key would make) goes in where its dot is first, the stretch keeping its way,
 * control points and timing (key_add_in_place), then takes the value, as a key moved there: so keying a frame
 * doesn't reshape the rest of the stretch. Elsewhere it is a key as any other, its neighbours' Auto handles taking
 * it in as Moho's do. */
template<typename T> static Key<T> &key_put(Channel<T> &ch, int frame, const T &base)
{
  if constexpr (std::is_same_v<T, float2>) {
    if (frame > 0 && ch.keys.size() >= 2 && !ch.key_at(frame)) {
      const auto b = std::find_if(ch.keys.begin(), ch.keys.end(), [&](const auto &k) { return k.frame > frame; });
      if (b != ch.keys.begin() && b != ch.keys.end() && stretch_on_path(*(b - 1), *b)) {
        key_add_in_place(ch, frame);
      }
    }
  }
  return ch.set_key(frame, base);
}

/* Key Together: before `ch` is keyed on `frame`, the filler keys at the poses either side (its keys before and after
 * the frame) become its own, holding what they showed, so the edit changes it only between those poses. A filler
 * inside motion, or after the channel's last key of its own, shapes nothing (Channel::evaluate): left so, the new key's
 * curve would run through it and move the pose there. Kept when Key Together is turned off. */
template<typename T> static void fillers_hold_around(Channel<T> &ch, int frame)
{
  Key<T> *before = nullptr, *after = nullptr;
  for (Key<T> &k : ch.keys) {
    if (k.frame < frame) {
      before = &k;
    }
    else if (k.frame > frame && !after) {
      after = &k;
    }
  }
  /* Both worked out before either changes. */
  const T held_before = before ? ch.evaluate(before->frame) : T{};
  const T held_after = after ? ch.evaluate(after->frame) : T{};
  const auto hold = [](Key<T> *k, const T &held) {
    if (k && k->filler) {
      k->value = held;
      k->filler = false;
      k->filler_inside = false;
    }
  };
  hold(before, held_before);
  hold(after, held_after);
}

/* A key on `frame` (none there yet) holding `held`, put in as the stretch it splits plays: arriving as that stretch
 * did, playing on as the key before did, with what is left of its hold, on its interval, a breakdown inside a span
 * across breakdowns (scalar_key_add_in_place's way; a stretch shaped on the motion path, key_add_in_place's). */
template<typename T> static void hold_key_put(Channel<T> &ch, int frame, const T &held)
{
  const auto b = std::find_if(ch.keys.begin(), ch.keys.end(), [&](const Key<T> &k) { return k.frame > frame; });
  if (b == ch.keys.begin() || b == ch.keys.end()) {
    ch.set_key(frame, held);
    return;
  }
  if constexpr (std::is_same_v<T, float2>) {
    if (stretch_on_path(*(b - 1), *b)) {
      key_add_in_place(ch, frame);
      return;
    }
  }
  const Key<T> &a = *(b - 1);
  const KeySettings arriving = key_settings(*b);
  const int interval = a.interval;
  const int start = std::min(a.frame + std::max(a.hold, 0), b->frame);
  const bool span = a.type == KeyType::Breakdown || b->type == KeyType::Breakdown;
  Key<T> &k = ch.set_key(frame, held);
  key_settings_apply(k, arriving);
  k.hold = std::max(start - frame, 0);
  k.interval = interval;
  k.type = span ? KeyType::Breakdown : KeyType::Key;
}

/* Auto-Freeze Keys: before `ch` is keyed on `frame`, a key at its layer's pose either side (`poses`) holding what it
 * shows there, unless it has one, so the edit changes it only between those poses. The frame keyed is a pose from
 * then on, which later edits nearby hold in turn: the poses stay without every channel keyed on every one. What each
 * pose shows is worked out first (hold_plan), before anything on the channel changes, then the nearest held
 * (hold_apply) and, once the key is in, any further out it still reaches (hold_reach). */
template<typename T> struct HoldPlan {
  int frames[2] = {INT32_MIN, INT32_MIN};
  T held[2] = {};
  /* Every pose but the frame keyed, with what it shows. */
  std::vector<std::pair<int, T>> all;
};

static bool hold_same(float a, float b)
{
  return std::abs(a - b) <= 1e-6f * std::max(1.0f, std::abs(a));
}

static bool hold_same(const float2 &a, const float2 &b)
{
  return hold_same(a.x, b.x) && hold_same(a.y, b.y);
}

template<typename T> static HoldPlan<T> hold_plan(const Channel<T> &ch, const std::vector<int> *poses, int frame)
{
  HoldPlan<T> plan;
  if (!poses) {
    return plan;
  }
  const auto after = std::upper_bound(poses->begin(), poses->end(), frame);
  const auto before = std::lower_bound(poses->begin(), poses->end(), frame);
  plan.frames[0] = before != poses->begin() ? *std::prev(before) : INT32_MIN;
  plan.frames[1] = after != poses->end() ? *after : INT32_MIN;
  for (int i = 0; i < 2; i++) {
    if (plan.frames[i] != INT32_MIN) {
      plan.held[i] = ch.evaluate(plan.frames[i]);
    }
  }
  plan.all.reserve(poses->size());
  for (const int pose : *poses) {
    if (pose != frame) {
      plan.all.push_back({pose, ch.evaluate(pose)});
    }
  }
  return plan;
}

template<typename T> static void hold_apply(Channel<T> &ch, const HoldPlan<T> &plan)
{
  for (int i = 0; i < 2; i++) {
    if (plan.frames[i] != INT32_MIN && !ch.key_at(plan.frames[i])) {
      hold_key_put(ch, plan.frames[i], plan.held[i]);
    }
  }
}

/* A Smooth key leans on its neighbours (key_slope), so the edit's key and the holds bend the stretches past the held
 * poses too: the moved pose nearest the edit on each side is held as well (a filler there made the channel's own), and
 * so on out until none moves. Linear and Step stretches need none. */
template<typename T> static void hold_reach(Channel<T> &ch, const HoldPlan<T> &plan, int frame)
{
  for (size_t round = 0; round < plan.all.size(); round++) {
    int nearest[2] = {-1, -1};
    for (size_t i = 0; i < plan.all.size(); i++) {
      const auto &[pose, held] = plan.all[i];
      const Key<T> *k = ch.key_at(pose);
      if ((k && !k->filler) || hold_same(ch.evaluate(pose), held)) {
        continue;
      }
      const int side = pose > frame ? 1 : 0;
      if (nearest[side] < 0 || std::abs(pose - frame) < std::abs(plan.all[size_t(nearest[side])].first - frame)) {
        nearest[side] = int(i);
      }
    }
    if (nearest[0] < 0 && nearest[1] < 0) {
      return;
    }
    for (const int i : nearest) {
      if (i < 0) {
        continue;
      }
      const auto &[pose, held] = plan.all[size_t(i)];
      if (Key<T> *k = ch.key_at(pose)) {
        k->value = held;
        k->filler = false;
        k->filler_inside = false;
      }
      else {
        hold_key_put(ch, pose, held);
      }
    }
  }
}

/* Turns a change to `ch` since it was last evaluated into a key at `frame` (auto-key on). Replace
 * (Blender's auto-keying mode) only changes a key already on the frame. `poses()` gives the layer's poses for
 * Auto-Freeze Keys to hold either side (hold_plan), or null. Returns whether it keyed. */
template<typename T, typename Poses>
static bool record_with(Channel<T> &ch, const T &value, int frame, bool auto_key, bool replace, Poses &&poses)
{
  if (!ch.has_last) {
    /* New data (a point just drawn): it is simply there, on every frame. */
    ch.last = value;
    ch.has_last = true;
    return false;
  }
  if (value == ch.last) {
    return false;
  }
  if (ch.keyed_by_hand && !ch.animated()) {
    /* Not keyed yet: the change is just there; `last` keeps the value from before it, for the
     * setup key if it gets keyed by hand now. */
    return false;
  }
  /* Keys hold the value without what action bone actions add. */
  const T base = value - ch.from_action_bones;
  if (frame == 0) {
    /* The setup frame: the frame-0 key, or the value itself while it isn't animated. */
    if (ch.animated()) {
      ch.set_key(0, base);
    }
  }
  else if (auto_key && (ch.animated() || !ch.keyed_by_hand) && (!replace || ch.key_at(frame))) {
    if (!ch.animated()) {
      ch.set_key(0, ch.last - ch.from_action_bones);
    }
    /* What the poses either side show, before a filler there becomes its own or anything goes in. */
    HoldPlan<T> plan = hold_plan(ch, poses(), frame);
    if (plan.all.empty()) {
      /* Key Together without Auto-Freeze: its fillers are the poses its Smooth curve mustn't bend past either. */
      for (const Key<T> &f : ch.keys) {
        if (f.filler && f.frame != frame) {
          plan.all.push_back({f.frame, ch.evaluate(f.frame)});
        }
      }
    }
    fillers_hold_around(ch, frame);
    hold_apply(ch, plan);
    /* On Path: a key past its first or last holds where it is, as they do, with what the actions added there; one
     * between, what they added there as its neighbours had it. */
    T put = base;
    [[maybe_unused]] T offset{};
    if constexpr (std::is_same_v<T, float2>) {
      if (channel_on_path(ch)) {
        offset = channel_on_path_at(ch, frame) ? channel_path_offset_at(ch, frame) : ch.from_action_bones;
        if (!channel_on_path_at(ch, frame)) {
          put = value;
        }
      }
    }
    /* The channel's own, even over a filler not taken yet (just opened: fillers_check can't tell it was edited). */
    Key<T> &k = key_put(ch, frame, put);
    if constexpr (std::is_same_v<T, float2>) {
      if (ch.on_path) {
        k.path_offset = offset;
      }
    }
    k.filler = false;
    k.filler_inside = false;
    if (!plan.all.empty()) {
      hold_reach(ch, plan, frame);
    }
    ch.last = value;
    return true;
  }
  /* Unkeyed, the edit goes into the setup, which the actions blend from: by as much more as keeps it where it was put
   * (none more where the actions take it whole). */
  /* Held still by one counts as much as moved: it blends from the setup either way. */
  if (frame != 0 && !ch.animated() && ch.action_slope.known && ch.action_played.on) {
    const float keep = 1.0f + ch.action_slope.slope;
    if (keep > 0.05f && keep < 0.999f) {
      ch.from_action_bones += (value - ch.last) * (1.0f - 1.0f / keep);
    }
  }
  ch.action_slope = {};
  ch.last = value;
  return false;
}

template<typename T> static bool record(Channel<T> &ch, const T &value, int frame, bool auto_key, bool replace = false)
{
  return record_with(ch, value, frame, auto_key, replace, [] { return static_cast<const std::vector<int> *>(nullptr); });
}

/* A layer's poses: the frames keyed anywhere on it (its own channels, its bones', its drawing's points'), sorted. */
static std::vector<int> layer_pose_frames(Layer &layer)
{
  std::set<int> frames;
  layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) {
    for (const auto &k : ch.keys) {
      frames.insert(k.frame);
    }
  });
  return {frames.begin(), frames.end()};
}

static bool action_moves_bone(const Bone &bone, const std::string &action);

/* Auto-Freeze Keys' poses for each bone of a layer: the layer's poses, less the frames only a 2 Axis Controller's knob
 * is keyed on whose actions don't move the bone (a head turn's knob keyed on 28 held a pupil the turn holds still
 * there, putting a key in the middle of its own move). Every other bone's keys still hold it, pose to pose. */
struct BonePoses {
  std::vector<int> all;
  std::set<int> base;
  std::vector<std::pair<const Bone *, std::vector<int>>> knobs;
  /* A list: what bone_poses_of hands out stays where it is as more are added. */
  std::list<std::pair<const Bone *, std::vector<int>>> per_bone;
};

static void bone_poses_make(Layer &layer, BonePoses &out)
{
  out.all = layer_pose_frames(layer);
  std::set<const void *> knob_channels;
  for (const Bone &k : layer.bones) {
    if (bone_is_controller(k) && !k.position_keys.keys.empty()) {
      knob_channels.insert(&k.position_keys);
      std::vector<int> frames;
      for (const auto &key : k.position_keys.keys) {
        frames.push_back(key.frame);
      }
      out.knobs.push_back({&k, std::move(frames)});
    }
  }
  if (out.knobs.empty()) {
    return;
  }
  layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) {
    if (knob_channels.count(&ch)) {
      return;
    }
    for (const auto &k : ch.keys) {
      out.base.insert(k.frame);
    }
  });
}

static const std::vector<int> &bone_poses_of(BonePoses &poses, const Bone &bone)
{
  if (poses.knobs.empty()) {
    return poses.all;
  }
  for (const auto &[b, frames] : poses.per_bone) {
    if (b == &bone) {
      return frames;
    }
  }
  std::set<int> frames = poses.base;
  for (const auto &[knob, knob_frames] : poses.knobs) {
    const bool moves = knob == &bone || std::any_of(knob->controller_actions.begin(), knob->controller_actions.end(),
                                                    [&](const std::string &a) {
                                                      return !a.empty() && action_moves_bone(bone, a);
                                                    });
    if (moves) {
      frames.insert(knob_frames.begin(), knob_frames.end());
    }
  }
  poses.per_bone.push_back({&bone, std::vector<int>(frames.begin(), frames.end())});
  return poses.per_bone.back().second;
}

/* The bone a channel of `layer` belongs to (its keys are a member of it), or null. */
static const Bone *channel_bone(const Layer &layer, const void *ch)
{
  const char *at = static_cast<const char *>(ch);
  for (const Bone &b : layer.bones) {
    if (at >= reinterpret_cast<const char *>(&b) && at < reinterpret_cast<const char *>(&b + 1)) {
      return &b;
    }
  }
  return nullptr;
}


template<typename T> static void evaluate(Channel<T> &ch, T &value, int frame)
{
  if (ch.animated()) {
    value = ch.evaluate(frame);
  }
  else {
    /* Unkeyed, the plain value is the data: take off what action bone actions added last time. */
    value -= ch.from_action_bones;
  }
  ch.from_action_bones = T{};
  ch.action_bone_live = false;
  ch.action_played = {};
  ch.action_slope = {};
  ch.last = value;
  ch.has_last = true;
}

static void apply_action_bone_actions(Document &doc, int frame);
static void controllers_rest(Document &doc);

/* --- The document's Simulation settings, animatable --------------------------------------------- */

static const std::pair<const char *, float Document::*> SIMULATION_PROPS[] = {
    {"gravity", &Document::gravity},
    {"wind", &Document::wind},
    {"wind_direction", &Document::wind_direction},
    {"wind_gusts", &Document::wind_gusts},
    {"wind_gust_speed", &Document::wind_gust_speed},
    {"wind_turbulence", &Document::wind_turbulence},
};

Layer &document_simulation(Document &doc)
{
  Layer &sim = doc.simulation;
  sim.id = SIMULATION_LAYER_ID;
  sim.name = "Simulation";
  sim.type = LayerType::Group;
  for (const auto &[path, field] : SIMULATION_PROPS) {
    const auto it = std::find_if(sim.custom_channels.begin(), sim.custom_channels.end(),
                                 [&](const CustomChannel &c) { return c.path == path; });
    if (it == sim.custom_channels.end()) {
      sim.custom_channels.push_back({path, doc.*field, doc.*field, Channel<float>::by_hand()});
    }
  }
  return sim;
}

bool simulation_path(const std::string &path)
{
  for (const auto &[name, field] : SIMULATION_PROPS) {
    if (path == name) {
      return true;
    }
  }
  return false;
}

/* The settings and their channels made to agree: a setting edited since they last did goes into
 * its channel (to be recorded); a channel changed since (its keys removed, say) goes into the
 * setting. */
static void simulation_in(Document &doc)
{
  for (CustomChannel &c : document_simulation(doc).custom_channels) {
    for (const auto &[name, field] : SIMULATION_PROPS) {
      if (c.path != name) {
        continue;
      }
      if (doc.*field != c.synced) {
        c.value = doc.*field;
      }
      else {
        doc.*field = c.value;
      }
      c.synced = c.value;
    }
  }
}

/* The channels' values for the frame into the settings (after evaluating). */
static void simulation_out(Document &doc)
{
  for (CustomChannel &c : doc.simulation.custom_channels) {
    for (const auto &[name, field] : SIMULATION_PROPS) {
      if (c.path == name) {
        doc.*field = c.value;
        c.synced = c.value;
      }
    }
  }
}

void simulation_values_out(Document &doc)
{
  simulation_out(doc);
}

float simulation_value_at(const Document &doc, const char *path, float plain, int frame)
{
  for (const CustomChannel &c : doc.simulation.custom_channels) {
    if (c.path == path && c.keys.animated()) {
      return c.keys.evaluate(std::max(frame, 0));
    }
  }
  return plain;
}

/* The channels of a drawing's shape, with the values recording keys (changes from the setup pose). */
template<typename F> static void drawing_shape_channels(VectorDrawing &drawing, F &&f)
{
  /* Detail points (data/detail.hh) ride their segments: no keys of their own. */
  for (MeshPoint &p : drawing.points) {
    if (p.detail.level > 0) {
      continue;
    }
    f(p.pos_keys, p.transform);
    f(p.radius_keys, p.radius);
  }
  for (Curve &curve : drawing.curves) {
    for (CurvePoint &cp : curve.points) {
      if (cp.point >= 0 && size_t(cp.point) < drawing.points.size() && drawing.points[size_t(cp.point)].detail.level > 0) {
        continue;
      }
      f(cp.curvature_keys, cp.curvature);
      f(cp.handle_in_keys, cp.change_in);
      f(cp.handle_out_keys, cp.change_out);
    }
  }
}

/* A key's timing (all but its value, path handles, colour and selection). */
struct KeyTiming {
  Interp interp = Interp::Smooth;
  KeyType type = KeyType::Key;
  int hold = 0, interval = 1;
  Ease ease = Ease::Quad;
  float overshoot = 0.0f, elastic_amplitude = 0.0f, elastic_period = 0.0f, noise_amplitude = 0.0f,
        noise_frequency = 0.0f;
  int cycle_back = 0, cycle_frame = 0;
  bool cycle_absolute = false;
  TimingCurve timing;
  BezierHandles bezier = BEZIER_DEFAULT;
  bool operator==(const KeyTiming &) const = default;
};

template<typename T> static KeyTiming key_timing(const Key<T> &k)
{
  return {k.interp,         k.type,           k.hold,            k.interval,      k.ease,
          k.overshoot,      k.elastic_amplitude, k.elastic_period, k.noise_amplitude, k.noise_frequency,
          k.cycle_back,     k.cycle_frame,    k.cycle_absolute,  k.timing,          k.bezier};
}

template<typename T> static void key_timing_set(Key<T> &k, const KeyTiming &t)
{
  k.interp = t.interp;
  k.type = k.frame == 0 ? KeyType::Key : t.type;
  k.hold = t.hold;
  k.interval = t.interval;
  k.ease = t.ease;
  k.overshoot = t.overshoot;
  k.elastic_amplitude = t.elastic_amplitude;
  k.elastic_period = t.elastic_period;
  k.noise_amplitude = t.noise_amplitude;
  k.noise_frequency = t.noise_frequency;
  k.cycle_back = t.cycle_back;
  k.cycle_frame = t.cycle_frame;
  k.cycle_absolute = t.cycle_absolute;
  k.timing = t.timing;
  k.bezier = t.bezier;
}

/* A key's value and timing (with_value) or its timing alone, as a number: a filler key edited since it was added no
 * longer has the one it was given (Key::filler_self, filler_out). */
static uint32_t sig_add(uint32_t h, const void *data, size_t size)
{
  const auto *b = static_cast<const unsigned char *>(data);
  for (size_t i = 0; i < size; i++) {
    h = (h ^ b[i]) * 16777619u;
  }
  return h;
}

template<typename T> static uint32_t key_sig(const Key<T> &k, bool with_value)
{
  uint32_t h = 2166136261u;
  if (with_value) {
    h = sig_add(h, &k.value, sizeof(T));
  }
  const int ints[] = {int(k.interp), k.hold, k.interval, int(k.ease), k.cycle_back, k.cycle_frame, k.cycle_absolute,
                      int(k.type)};
  const float floats[] = {k.overshoot, k.elastic_amplitude, k.elastic_period, k.noise_amplitude, k.noise_frequency};
  h = sig_add(h, ints, sizeof(ints));
  h = sig_add(h, floats, sizeof(floats));
  h = sig_add(h, k.bezier.data(), sizeof(k.bezier));
  for (const TimingPoint &p : k.timing.points) {
    const float v[] = {p.co.x, p.co.y, p.in.x, p.in.y, p.out.x, p.out.y, p.aligned ? 1.0f : 0.0f};
    h = sig_add(h, v, sizeof(v));
  }
  return h;
}

/* Filler keys edited since they were added (their value or timing, or the timing of the stretch after them while the
 * key after is the same) become the channel's own. */
template<typename K> static void fillers_check(std::vector<K> &keys)
{
  for (size_t i = 0; i < keys.size(); i++) {
    auto &k = keys[i];
    /* Not taken yet (just opened): as it is now. */
    if (!k.filler || k.filler_self == 0) {
      continue;
    }
    const bool next = i + 1 < keys.size();
    const int next_frame = next ? keys[i + 1].frame : INT32_MIN;
    if (key_sig(k, true) != k.filler_self ||
        (next_frame == k.filler_next && next && key_sig(keys[i + 1], false) != k.filler_out))
    {
      k.filler = false;
      k.filler_edited = true;
    }
  }
}

/* What each filler key is now, to tell later whether it was edited. */
template<typename C> static void fillers_mark(C &ch)
{
  for (size_t i = 0; i < ch.keys.size(); i++) {
    auto &k = ch.keys[i];
    if (!k.filler) {
      continue;
    }
    const bool next = i + 1 < ch.keys.size();
    k.filler_self = std::max(1u, key_sig(k, true));
    k.filler_next = next ? ch.keys[i + 1].frame : INT32_MIN;
    k.filler_out = next ? key_sig(ch.keys[i + 1], false) : 0;
  }
}

/* Keys a set of channels as one (Key Whole Drawing: a drawing's shape; Key Together: everything in a group): every
 * channel keyed on every frame any is, each new key holding what the channel has there and taking the timing most keys
 * on that frame have; with `settle` (as it is turned on), the keys already there take that timing too. A frame keyed
 * last time (`owner`'s frames, in the same action) that a channel there then (Channel::synced) misses now had its
 * key deleted: it goes from them all. Channels gone (a point deleted) and new ones (an eraser's cut ends) say
 * nothing. `visit(f)` calls f(channel, value, unit) for each channel; `changes(true)` turns the
 * values into the changes keys hold, `changes(false)` back. With `fillers`, the keys added are fillers
 * (Key::filler). Returns how many keys already there had their timing changed. */
template<typename Visit, typename Changes>
static int keys_together_sync(Layer &owner, Visit &&visit, Changes &&changes, bool settle, const std::string &action,
                              bool fillers, bool *r_keys_went = nullptr)
{
  /* Each frame keyed anywhere: how many channels have it, and the timings its keys have there (how many of each, in
   * the order first met). */
  struct Frame {
    int count = 0;
    std::vector<std::pair<KeyTiming, int>> votes;
  };
  std::map<int, Frame> frames;
  bool all_alike = true;
  size_t keyed_count = 0, channels = 0;
  /* Frames from another action's channels (or none yet) say nothing about what was deleted here. */
  static const std::set<int> none;
  std::string &owner_action = fillers ? owner.key_together_action : owner.key_whole_action;
  if (fillers && settle) {
    /* Turned on: what it keyed before it was last turned off says nothing now. */
    owner.key_together_frames.clear();
  }
  std::set<int> &owner_frames = fillers ? owner.key_together_frames[action] : owner.key_whole_frames;
  const std::set<int> &before = settle || (!fillers && owner_action != action) ? none : owner_frames;
  std::set<int> deleted_set;
  visit([&](auto &ch, auto & /*value*/, const void * /*unit*/) {
    if (fillers) {
      fillers_check(ch.keys);
    }
    channels++;
    keyed_count += ch.keys.size();
    /* Keyed when they last agreed: each of that time's frames it misses now was deleted (frame 0, the setup, never). */
    if (!before.empty() && (fillers ? ch.together_synced : ch.synced)) {
      for (const int frame : before) {
        if (frame != 0 && !ch.key_at(frame)) {
          deleted_set.insert(frame);
        }
      }
    }
    for (const auto &k : ch.keys) {
      Frame &f = frames[k.frame];
      f.count++;
      const KeyTiming t = key_timing(k);
      auto it = std::find_if(f.votes.begin(), f.votes.end(), [&](const auto &v) { return v.first == t; });
      if (it == f.votes.end()) {
        f.votes.push_back({t, 1});
        all_alike = all_alike && f.votes.size() == 1;
      }
      else {
        it->second++;
      }
    }
  });
  const auto remember = [&] {
    owner_action = action;
    owner_frames.clear();
    visit([&](auto &ch, auto & /*value*/, const void * /*unit*/) {
      if (fillers) {
        fillers_mark(ch);
      }
      for (const auto &k : ch.keys) {
        owner_frames.insert(k.frame);
      }
      (fillers ? ch.together_synced : ch.synced) = true;
    });
  };
  /* Nothing keyed, or every channel already keyed on every frame alike: nothing to do (the usual case, kept cheap). */
  if (frames.empty() || (all_alike && keyed_count == frames.size() * channels)) {
    remember();
    return 0;
  }
  const std::vector<int> deleted(deleted_set.begin(), deleted_set.end());
  if (r_keys_went && !deleted.empty()) {
    *r_keys_went = true;
  }
  for (const int frame : deleted) {
    frames.erase(frame);
  }
  std::map<int, const KeyTiming *> most;
  for (const auto &[frame, f] : frames) {
    const auto best = std::max_element(f.votes.begin(), f.votes.end(),
                                       [](const auto &a, const auto &b) { return a.second < b.second; });
    most[frame] = &best->first;
  }
  int settled = 0;
  changes(true);
  visit([&](auto &ch, auto &value, const void * /*unit*/) {
    for (const int frame : deleted) {
      channel_delete_key(ch, value, frame);
    }
    const bool was_animated = ch.animated();
    /* As it played before the settle: a filler inside a stretch it retimes holds what showed there. */
    using C = std::decay_t<decltype(ch)>;
    const std::optional<C> before = settle ? std::optional<C>(ch) : std::nullopt;
    const int settled_before = settled;
    /* Its last key of its own: a filler before it is inside motion it already has. */
    int own_last = INT32_MIN;
    for (const auto &k : ch.keys) {
      if (!k.filler) {
        own_last = std::max(own_last, k.frame);
      }
    }
    for (const auto &[frame, timing] : most) {
      if (auto *k = ch.key_at(frame)) {
        if (settle && key_timing(*k) != *timing) {
          key_timing_set(*k, *timing);
          settled++;
        }
        continue;
      }
      /* Inside a stretch shaped on its motion path (Custom timing, control points, path handles: no other key's
       * timing would make it), a key of its own (Key Whole Drawing's) goes in where its dot is, the stretch keeping its way and timing
       * (key_add_in_place), so nothing the channel does changes. A filler doesn't split it: inside motion the channel
       * already has, it is worked out without (Key::filler_inside), so the stretch stays whole, and letting it go
       * leaves nothing to join. */
      using T = std::decay_t<decltype(ch.keys[0].value)>;
      if constexpr (std::is_same_v<T, float2> || std::is_same_v<T, float>) {
        const auto b = std::find_if(ch.keys.begin(), ch.keys.end(), [&](const auto &k) { return k.frame > frame; });
        if (!fillers && was_animated && b != ch.keys.begin() && b != ch.keys.end() &&
            (b->interp == Interp::Custom || !b->path_controls.empty() ||
             (std::is_same_v<T, float2> && stretch_on_path(*(b - 1), *b))))
        {
          if constexpr (std::is_same_v<T, float2>) {
            key_add_in_place(ch, frame);
          }
          else {
            scalar_key_add_in_place(ch, frame);
          }
          continue;
        }
      }
      /* What it has there now: between its keys, or (not keyed) the value it holds everywhere. */
      const auto held = was_animated ? ch.evaluate(frame) : value - ch.from_action_bones;
      if (!fillers) {
        /* A key of its own (Key Whole Drawing's) in a group keying together: the fillers either side hold, as
         * record_with's do, or its curve would run past them and move the poses there. */
        fillers_hold_around(ch, frame);
      }
      auto &k = ch.set_key(frame, held);
      key_timing_set(k, *timing);
      k.filler = fillers;
      k.filler_inside = fillers && was_animated && frame < own_last;
    }
    /* Its timing settled, a stretch plays otherwise, and a filler inside it (worked out without) would leave its pose
     * there: it keeps what showed there and shapes the stretch, so every pose stays as it was. */
    if (before && settled != settled_before) {
      for (auto &k : ch.keys) {
        if (!k.filler_inside) {
          continue;
        }
        const auto was = before->evaluate(k.frame), now = ch.evaluate(k.frame);
        const auto gap = was - now;
        float off = 0.0f;
        if constexpr (std::is_same_v<std::decay_t<decltype(gap)>, float2>) {
          off = std::max(std::abs(gap.x), std::abs(gap.y));
        }
        else {
          off = std::abs(float(gap));
        }
        if (off > 1e-6f) {
          k.value = was;
          k.filler_inside = false;
        }
      }
    }
  });
  changes(false);
  remember();
  return settled;
}

/* Whether the channel plays the same on every frame without its key on `frame`. */
template<typename K> static bool key_shapes_nothing(const std::vector<K> &keys, int frame)
{
  using T = std::decay_t<decltype(keys[0].value)>;
  Channel<T> with, without;
  with.keys = keys;
  without.keys = keys;
  std::erase_if(without.keys, [&](const auto &k) { return k.frame == frame; });
  if (without.keys.empty()) {
    return false;
  }
  for (int f = keys.front().frame; f <= keys.back().frame + 1; f++) {
    const T a = with.evaluate(f), b = without.evaluate(f);
    if constexpr (std::is_same_v<T, float2>) {
      if (std::abs(a.x - b.x) > 1e-6f || std::abs(a.y - b.y) > 1e-6f) {
        return false;
      }
    }
    else if (std::abs(a - b) > 1e-6f) {
      return false;
    }
  }
  return true;
}

/* Key Together turned off: the filler keys never edited go (a unit's keys on a frame stay together: a whole drawing's
 * stay if any of them is its own), and the rest become the channels' own. Those in actions not being edited (kept in
 * Channel::actions) go too. Returns how many went, and how many fillers stayed. */
template<typename Visit, typename Changes>
static std::pair<int, int> keys_together_release(Visit &&visit, Changes &&changes)
{
  std::set<std::pair<const void *, int>> own;
  /* The same in each action put away: (unit, action, frame). */
  std::set<std::tuple<const void *, std::string, int>> own_away;
  int fillers = 0;
  visit([&](auto &ch, auto & /*value*/, const void *unit) {
    fillers_check(ch.keys);
    for (const auto &k : ch.keys) {
      fillers += k.filler || k.filler_edited ? 1 : 0;
      if (!k.filler && !k.filler_edited) {
        own.insert({unit, k.frame});
      }
    }
    for (auto &[name, keys] : ch.actions) {
      fillers_check(keys);
      for (const auto &k : keys) {
        fillers += k.filler || k.filler_edited ? 1 : 0;
        if (!k.filler && !k.filler_edited) {
          own_away.insert({unit, name, k.frame});
        }
      }
    }
    /* Edited fillers that shape something (the channel plays otherwise without them), each unit's frame kept whole:
     * a drawing's keys on a frame stay together. */
    for (const auto &k : ch.keys) {
      if (k.filler_edited && !k.filler && k.frame != 0 && !key_shapes_nothing(ch.keys, k.frame)) {
        own.insert({unit, k.frame});
      }
    }
    for (auto &[name, keys] : ch.actions) {
      for (const auto &k : keys) {
        if (k.filler_edited && !k.filler && k.frame != 0 && !key_shapes_nothing(keys, k.frame)) {
          own_away.insert({unit, name, k.frame});
        }
      }
    }
  });
  int removed = 0;
  bool away_changed = false;
  visit([&](auto &ch, auto & /*value*/, const void *unit) {
    for (auto it = ch.actions.begin(); it != ch.actions.end();) {
      auto &keys = it->second;
      const size_t before = keys.size();
      /* An edited one on frame 0 only when nothing else is left (a channel keyed holds a key there). */
      std::erase_if(keys, [&](const auto &k) {
        return (k.filler || (k.filler_edited && k.frame != 0)) && !own_away.count({unit, it->first, k.frame});
      });
      if (keys.size() == 1 && keys[0].filler_edited && !own_away.count({unit, it->first, keys[0].frame})) {
        keys.clear();
      }
      removed += int(before - keys.size());
      away_changed = away_changed || keys.size() != before;
      for (auto &k : keys) {
        k.filler = false;
        k.filler_edited = false;
      }
      it = keys.empty() ? ch.actions.erase(it) : std::next(it);
    }
  });
  if (away_changed) {
    channel_keys_changed();
  }
  changes(true);
  visit([&](auto &ch, auto &value, const void *unit) {
    std::vector<int> go;
    for (const auto &k : ch.keys) {
      if ((k.filler || k.filler_edited) && !own.count({unit, k.frame})) {
        go.push_back(k.frame);
      }
    }
    /* Frame 0 last, and only when nothing else is left: a channel keyed holds a key there. */
    for (auto it = go.rbegin(); it != go.rend(); ++it) {
      if (*it != 0 || ch.keys.size() == 1) {
        ch.remove_key(*it);
        removed++;
      }
    }
    if (!ch.animated() && ch.keys.size() <= 1) {
      if (const auto *k = ch.key_at(0); k && k->filler) {
        value = k->value + ch.from_action_bones;
        ch.remove_key(0);
        removed++;
      }
    }
    for (auto &k : ch.keys) {
      k.filler = false;
      k.filler_edited = false;
    }
  });
  changes(false);
  /* Out of the group: new to any it joins. */
  visit([&](auto &ch, auto & /*value*/, const void * /*unit*/) { ch.together_synced = false; });
  return {removed, std::max(0, fillers - removed)};
}

int drawing_key_whole(Layer &layer, bool settle, const std::string &action, bool *r_keys_went)
{
  if (!layer.has_drawing() || layer.is_reference()) {
    return 0;
  }
  VectorDrawing &drawing = layer.drawing;
  return keys_together_sync(
      layer,
      [&](auto &&f) { drawing_shape_channels(drawing, [&](auto &ch, auto &value) { f(ch, value, &ch); }); },
      [&](bool to_changes) {
        if (to_changes) {
          drawing_changes_from_values(drawing);
        }
        else {
          drawing_values_from_changes(drawing);
        }
      },
      settle, action, false, r_keys_went);
}

/* Key Whole Drawing turned on, in the timeline being edited (`current`, an action's name or "" for the mainline):
 * the keys of every other timeline the drawing has (put away in each channel's `actions`) are made to agree as well,
 * so going into one later adds no keys with no edit. Each is brought out as going into it would (an action's frame 0
 * the setup pose), keyed as one with its timing settled, and put away again; the values shown stay. Returns how many
 * keys already there had their timing changed. */
static int drawing_key_whole_away(Layer &layer, const std::string &current)
{
  if (!layer.has_drawing() || layer.is_reference()) {
    return 0;
  }
  VectorDrawing &drawing = layer.drawing;
  std::set<std::string> names;
  /* What each channel holds where it has no keys of a timeline: the setup pose (its value, as the sync reads it). */
  std::vector<float2> held2;
  std::vector<float> held1;
  drawing_shape_channels(drawing, [&](auto &ch, auto &value) {
    for (const auto &[name, keys] : ch.actions) {
      if (name != current && !keys.empty()) {
        names.insert(name);
      }
    }
    using T = std::decay_t<decltype(value)>;
    const T setup = ch.animated() ? ch.evaluate(0) : value - ch.from_action_bones;
    if constexpr (std::is_same_v<T, float2>) {
      held2.push_back(setup + ch.from_action_bones);
    }
    else {
      held1.push_back(setup + ch.from_action_bones);
    }
  });
  if (names.empty()) {
    return 0;
  }
  /* The sync remembers the frames it keyed, for the timeline being edited: kept as they were. */
  const std::string was_action = layer.key_whole_action;
  const std::set<int> was_frames = layer.key_whole_frames;
  int settled = 0;
  for (const std::string &name : names) {
    /* The timeline being edited, set aside meanwhile. */
    std::vector<std::vector<Key<float2>>> stash2;
    std::vector<std::vector<Key<float>>> stash1;
    drawing_shape_channels(drawing, [&](auto &ch, auto & /*value*/) {
      using T = std::decay_t<decltype(ch.keys[0].value)>;
      if constexpr (std::is_same_v<T, float2>) {
        stash2.push_back(std::move(ch.keys));
      }
      else {
        stash1.push_back(std::move(ch.keys));
      }
      ch.keys.clear();
      if (auto it = ch.actions.find(name); it != ch.actions.end()) {
        ch.keys = std::move(it->second);
        ch.actions.erase(it);
      }
    });
    /* An action's keys start after frame 0, the setup pose: given it, as going into the action does. */
    if (!name.empty()) {
      size_t i2 = 0, i1 = 0;
      drawing_shape_channels(drawing, [&](auto &ch, auto & /*value*/) {
        using T = std::decay_t<decltype(ch.keys[0].value)>;
        T held;
        if constexpr (std::is_same_v<T, float2>) {
          held = held2[i2++];
        }
        else {
          held = held1[i1++];
        }
        if (ch.keys.empty() || ch.key_at(0)) {
          return;
        }
        Key<T> &k = ch.set_key(0, held - ch.from_action_bones);
        if constexpr (std::is_same_v<T, float2>) {
          if (auto it = ch.action_setup.find(name); it != ch.action_setup.end()) {
            k.path_handles = it->second.path_handles;
            k.path_in = it->second.path_in;
            k.path_out = it->second.path_out;
          }
        }
      });
    }
    settled += keys_together_sync(
        layer,
        [&](auto &&f) {
          size_t i2 = 0, i1 = 0;
          drawing_shape_channels(drawing, [&](auto &ch, auto & /*value*/) {
            using T = std::decay_t<decltype(ch.keys[0].value)>;
            if constexpr (std::is_same_v<T, float2>) {
              f(ch, held2[i2++], &ch);
            }
            else {
              f(ch, held1[i1++], &ch);
            }
          });
        },
        [](bool /*to_changes*/) {}, true, name, false);
    size_t s2 = 0, s1 = 0;
    drawing_shape_channels(drawing, [&](auto &ch, auto & /*value*/) {
      using T = std::decay_t<decltype(ch.keys[0].value)>;
      auto keys = std::move(ch.keys);
      if constexpr (std::is_same_v<T, float2>) {
        ch.keys = std::move(stash2[s2++]);
      }
      else {
        ch.keys = std::move(stash1[s1++]);
      }
      if (!name.empty()) {
        std::erase_if(keys, [](const auto &k) { return k.frame == 0; });
      }
      if (!keys.empty()) {
        ch.actions[name] = std::move(keys);
      }
    });
  }
  layer.key_whole_action = was_action;
  layer.key_whole_frames = was_frames;
  return settled;
}

bool key_together_allowed(const Layer &layer)
{
  /* A vector layer alone: its move, turn, size, opacity and drawing keyed as one. */
  return layer.type == LayerType::Group || layer.type == LayerType::Bone || layer.type == LayerType::Vector;
}

Layer *key_together_group(Document &doc, uint64_t layer_id)
{
  Layer *found = nullptr;
  for (Layer *l = layer_find(doc, layer_id); l; l = layer_parent(doc, l->id)) {
    if (l->key_together && key_together_allowed(*l)) {
      found = l;
    }
  }
  return found;
}

std::vector<Layer *> key_together_layers(Document &doc, Layer &group)
{
  /* The group and everything inside it, in the document's order. Only its own subtree is walked: every vector layer
   * keys together on its own, and searching the whole document for each made a frame change in a big one slow. */
  std::vector<Layer *> out;
  if (layer_find(doc, group.id) != &group) {
    return out;
  }
  const auto walk = [&](auto &&self, Layer &l) -> void {
    out.push_back(&l);
    for (Layer &child : l.children) {
      self(self, child);
    }
  };
  walk(walk, group);
  return out;
}

/* Calls f(channel, value, unit) for each channel a Key Together group keys as one: each layer's turn, move, size and
 * opacity, its bones', and its drawing's shape (a whole drawing's channels one unit). */
/* The channels of one layer that Key Together keys (see together_channels). */
template<typename F>
static void layer_together_channels(Layer &l, std::set<const void *> &seen, F &&f)
{
  KeyFilter filter;
  filter.kinds = KEY_LAYER_ANGLE | KEY_LAYER_TRANSFORM | KEY_OPACITY | KEY_BONE_ANGLE | KEY_BONE_TRANSFORM;
  for (const ChannelRef &ref : layer_filtered_channels(l, filter)) {
    if (ref.scalar && ref.scalar_value && seen.insert(ref.scalar).second) {
      f(*ref.scalar, *ref.scalar_value, static_cast<const void *>(ref.scalar));
    }
    if (ref.vector && ref.vector_value && seen.insert(ref.vector).second) {
      f(*ref.vector, *ref.vector_value, static_cast<const void *>(ref.vector));
    }
  }
  if (l.type == LayerType::Vector && l.has_drawing() && !l.is_reference()) {
    const void *whole = l.key_whole_drawing ? static_cast<const void *>(&l) : nullptr;
    drawing_shape_channels(l.drawing, [&](auto &ch, auto &value) {
      f(ch, value, whole ? whole : static_cast<const void *>(&ch));
    });
  }
}

template<typename F> static void together_channels(Document &doc, Layer &group, F &&f)
{
  std::set<const void *> seen;
  for (Layer *l : key_together_layers(doc, group)) {
    layer_together_channels(*l, seen, f);
  }
}

static void layers_changes(const std::vector<Layer *> &layers, bool to_changes)
{
  for (Layer *l : layers) {
    if (l->type == LayerType::Vector && l->has_drawing() && !l->is_reference()) {
      if (to_changes) {
        drawing_changes_from_values(l->drawing);
      }
      else {
        drawing_values_from_changes(l->drawing);
      }
    }
  }
}

static void together_changes(Document &doc, Layer &group, bool to_changes)
{
  layers_changes(key_together_layers(doc, group), to_changes);
}

std::vector<ChannelRef> key_together_channels(Document &doc, Layer &group)
{
  std::vector<ChannelRef> out;
  together_channels(doc, group, [&](auto &ch, auto &value, const void * /*unit*/) {
    ChannelRef ref;
    if constexpr (std::is_same_v<std::decay_t<decltype(value)>, float>) {
      ref.scalar = &ch;
      ref.scalar_value = &value;
    }
    else {
      ref.vector = &ch;
      ref.vector_value = &value;
    }
    out.push_back(ref);
  });
  return out;
}

int key_together_sync(Document &doc, Layer &group, bool settle, bool *r_keys_went)
{
  /* A layer new to the group (moved in, made or pasted inside it) misses its frames without any being deleted: its
   * channels aren't Channel::together_synced yet. */
  const std::vector<Layer *> inside = key_together_layers(doc, group);
  const int changed = keys_together_sync(
      group, [&](auto &&f) { together_channels(doc, group, f); },
      [&](bool to_changes) { together_changes(doc, group, to_changes); }, settle,
      doc.action.empty() ? std::string() : std::to_string(doc.action_layer) + "/" + doc.action, true, r_keys_went);
  group.key_together_members.clear();
  group.key_together_members_of = group.id;
  for (const Layer *l : inside) {
    group.key_together_members.insert(l->id);
  }
  return changed;
}

/* Layers moved out of the group (still in the document, the layers inside one going with it): the fillers they were
 * given and never edited go, as when the group is turned off; their own keys stay. */
static std::pair<int, int> key_together_leavers_release(Document &doc, Layer &group)
{
  if (group.key_together_members_of != group.id) {
    group.key_together_members.clear();
    return {0, 0};
  }
  const std::vector<Layer *> inside = key_together_layers(doc, group);
  std::vector<uint64_t> gone;
  std::vector<Layer *> left;
  for (const uint64_t id : group.key_together_members) {
    if (Layer *l = layer_find(doc, id); !l || std::find(inside.begin(), inside.end(), l) == inside.end()) {
      gone.push_back(id);
      if (l) {
        left.push_back(l);
      }
    }
  }
  for (const uint64_t id : gone) {
    group.key_together_members.erase(id);
  }
  if (left.empty()) {
    return {0, 0};
  }
  return keys_together_release(
      [&](auto &&f) {
        std::set<const void *> seen;
        for (Layer *l : left) {
          layer_together_channels(*l, seen, f);
        }
      },
      [&](bool to_changes) { layers_changes(left, to_changes); });
}

void auto_freeze_hold(Document &doc, Layer &layer, Channel<float> &ch, int frame)
{
  if (!doc.auto_key || !doc.auto_freeze_keys || doc.auto_key_mode == AutoKeyMode::Replace || frame == 0 ||
      ch.key_at(frame))
  {
    return;
  }
  const std::vector<int> poses = layer_pose_frames(layer);
  hold_apply(ch, hold_plan(ch, &poses, frame));
}

std::pair<int, int> key_together_release(Document &doc, Layer &group)
{
  group.key_together_members.clear();
  return keys_together_release([&](auto &&f) { together_channels(doc, group, f); },
                               [&](bool to_changes) { together_changes(doc, group, to_changes); });
}

template<typename F> static void owner_for_each_channel(Layer &owner, F &&f);

/* An aligned point's two handle keys on one frame play alike (interpolation, hold, interval...): played apart, the
 * handles turn apart between keys and the point bends by itself. `way(in, out)`: 1 for the in handle's key to give
 * its settings to the out handle's, -1 the other way, 0 neither. */
template<typename Way> static void aligned_handle_keys_match(CurvePoint &p, Way &&way)
{
  for (Key<float2> &ki : p.handle_in_keys.keys) {
    Key<float2> *ko = p.handle_out_keys.key_at(ki.frame);
    if (!ko || key_settings(ki) == key_settings(*ko)) {
      continue;
    }
    const int w = way(ki, *ko);
    if (w > 0) {
      key_settings_apply(*ko, key_settings(ki));
    }
    else if (w < 0) {
      key_settings_apply(ki, key_settings(*ko));
    }
  }
}

void animation_record(Document &doc)
{
  OANIM_PROFILE("animation_record");
  /* Switches linked by name: new same-named switches join, renames reach partners. */
  for (const std::string &text : switch_links_update(doc)) {
    report(ReportType::Info, text);
  }
  if (doc.evaluated_frame < 0) {
    /* Nothing evaluated yet: the plain values are where everything starts. */
    animation_evaluate(doc, doc.frame_current);
    return;
  }
  /* A driven value is the driver's: an edit to it isn't kept (nor keyed). Worked out for the frame
   * being recorded, not the one being gone to (frame 0 would otherwise take another frame's pose
   * as the setup). */
  {
    const int now = doc.frame_current;
    doc.frame_current = doc.evaluated_frame;
    drivers_evaluate(doc);
    doc.frame_current = now;
  }
  /* An edit not yet recorded on an unkeyed value the actions move, and no refresh since it: what they do as its setup
   * changes (Channel::ActionSlope) is worked out now, for it to land where it was put. */
  if (doc.evaluated_frame != 0) {
    bool unknown = false;
    layers_for_each_channel_if(doc.layers, action_bones_added, [&](auto &ch, auto &value) {
      unknown = unknown || (!ch.animated() && !ch.constant && ch.has_last && ch.action_played.on &&
                            !ch.action_slope.known && !(value == ch.last));
    });
    if (unknown) {
      const int now = doc.frame_current;
      doc.frame_current = doc.evaluated_frame;
      animation_refresh_action_bones(doc);
      doc.frame_current = now;
    }
  }
  const int frame = doc.evaluated_frame;
  const bool auto_key = doc.auto_key;
  /* New points get their weights, so they follow the bones like their neighbours. */
  document_weight_new_points(doc, false, still_skipped);
  /* Every layer, children too: the passes below work on each on its own, over the CPU's cores (a big document has
   * thousands). */
  std::vector<Layer *> flat;
  const auto gather = [&](auto &&self, std::vector<Layer> &layers) -> void {
    for (Layer &layer : layers) {
      if (still_skipped(layer)) {
        continue;
      }
      flat.push_back(&layer);
      self(self, layer.children);
    }
  };
  gather(gather, doc.layers);
  /* New points get their handles now, from the setup pose, before anything counts as an edit. */
  parallel_for(flat.size(), 16, [&](size_t begin, size_t end) {
    for (size_t i = begin; i < end; i++) {
      if (!flat[i]->is_reference()) {
        drawing_init_handles(flat[i]->drawing);
      }
    }
  });
  /* Every point and shape has its id; edits on references become their overrides (their offsets are
   * then keyed below like any edit). */
  const auto ids = [](auto &&self, std::vector<Layer> &layers) -> void {
    for (Layer &layer : layers) {
      if (still_skipped(layer)) {
        continue;
      }
      if (!layer.is_reference()) {
        drawing_ensure_ids(layer.drawing);
      }
      self(self, layer.children);
    }
  };
  ids(ids, doc.layers);
  references_capture(doc);
  /* Points added to an animated curve take their neighbours' motion. Frame 0 is the setup pose:
   * bones, points and handles moved there move their setup, and every pose with it. */
  parallel_for(flat.size(), 16, [&](size_t begin, size_t end) {
    for (size_t i = begin; i < end; i++) {
      Layer &layer = *flat[i];
      if (!layer.is_reference()) {
        drawing_new_points_follow(layer.drawing, frame);
      }
      if (frame == 0) {
        for (Bone &bone : layer.bones) {
          bone_take_setup(bone);
        }
        if (!layer.is_reference()) {
          drawing_take_setup(layer.drawing);
        }
      }
    }
  });
  const bool replace = doc.auto_key_mode == AutoKeyMode::Replace;
  /* Auto-Freeze Keys: a channel keyed holds at its layer's poses either side first (hold_poses_around). Not in
   * Replace, which adds no keys, nor on the setup frame. */
  const bool freezing = auto_key && doc.auto_freeze_keys && !replace && frame != 0;
  /* A media or text layer with Don't Auto Key on is changed but never auto-keyed. Each layer's channels on their
   * own. */
  /* Which layers this keyed (Key Together fills an action's timeline once something in it is keyed). */
  std::vector<char> keyed_here(flat.size(), 0);
  parallel_for(flat.size(), 16, [&](size_t begin, size_t end) {
    for (size_t i = begin; i < end; i++) {
      Layer &layer = *flat[i];
      const bool keys = auto_key && !(layer.is_media() && layer.media.no_auto_key) &&
                        !(layer.is_text() && layer.text.no_auto_key);
      /* The layer's poses, worked out once something on it is keyed (most layers have no edit). Keys put on the
       * frame meanwhile don't change which poses lie either side of it. */
      BonePoses poses;
      bool poses_known = false;
      layer_for_each_channel(layer, [&](auto &ch, auto &value) {
        const bool keyed = record_with(ch, value, frame, keys, replace, [&]() -> const std::vector<int> * {
          if (!freezing) {
            return nullptr;
          }
          if (!poses_known) {
            bone_poses_make(layer, poses);
            poses_known = true;
          }
          const Bone *bone = layer.bones.empty() ? nullptr : channel_bone(layer, &ch);
          return bone ? &bone_poses_of(poses, *bone) : &poses.all;
        });
        keyed_here[i] = keyed_here[i] || keyed;
      });
    }
  });
  /* Key Whole Drawing: a point keyed here keys every point here; turned on, the keys agree from then on (their
   * timing once). */
  std::vector<int> settled(flat.size(), 0);
  /* A frame deleted from one channel and taken from the rest by Key Whole Drawing or Key Together: the frame shown is
   * worked out again at the end, or it would show the keys gone until the playhead moved (and the step store it). */
  std::vector<char> keys_went(flat.size(), 0);
  /* Which action: two bone layers' actions can share a name. */
  const std::string action_key = doc.action.empty() ? std::string() :
                                                      std::to_string(doc.action_layer) + "/" + doc.action;
  parallel_for(flat.size(), 16, [&](size_t begin, size_t end) {
    for (size_t i = begin; i < end; i++) {
      Layer &layer = *flat[i];
      if (!layer.key_whole_drawing || layer.type != LayerType::Vector) {
        layer.key_whole_settled = false;
        continue;
      }
      bool went = false;
      const bool settle = !layer.key_whole_settled;
      settled[i] = drawing_key_whole(layer, settle, action_key, &went);
      if (settle) {
        settled[i] += drawing_key_whole_away(layer, doc.action);
      }
      keys_went[i] = went;
      layer.key_whole_settled = true;
    }
  });
  /* Keys given another timing change the frame shown between them: it is worked out again at the end too. */
  bool retimed = false;
  for (size_t i = 0; i < flat.size(); i++) {
    if (settled[i] > 0) {
      retimed = true;
      report(ReportType::Info, flat[i]->name + ": Key Whole Drawing gave " + std::to_string(settled[i]) +
                                   " keys the timing most of its points have on their frame");
    }
  }
  /* Key Together: everything in the group keyed as one (a group inside one that is, by the outer one); turned off,
   * the keys added only to hold a layer in place go. Those turned off first (a group inside one turned on among
   * them), so no group lets go of fillers another just added. */
  std::vector<Layer *> together_on;
  for (Layer *group : flat) {
    if (!key_together_allowed(*group)) {
      /* No longer a kind that keys together (a group made a switch): off, its fillers let go. */
      if (group->key_together_settled) {
        group->key_together = false;
        group->key_together_settled = false;
        key_together_release(doc, *group);
      }
      continue;
    }
    const Layer *parent = layer_parent(doc, group->id);
    const bool inside = parent && key_together_group(doc, parent->id);
    if (group->key_together && !inside) {
      together_on.push_back(group);
    }
    else if (group->key_together_settled) {
      group->key_together_settled = false;
      if (group->key_together) {
        /* On inside one turned on: handed over. Its fillers hold its layers where they were and stay, the outer
         * group's now (it lets them go when turned off), so turning the outer one on moves nothing. Its layers are new
         * to the outer one, which reads no frame they miss as deleted. */
        group->key_together_members.clear();
        together_channels(doc, *group, [](auto &ch, auto & /*value*/, const void * /*unit*/) {
          ch.together_synced = false;
        });
        continue;
      }
      const auto [removed, kept] = key_together_release(doc, *group);
      if (removed + kept > 0) {
        report(ReportType::Info, group->name + ": Key Together off: removed " + std::to_string(removed) +
                                     " filler keys" +
                                     (kept > 0 ? ", kept " + std::to_string(kept) + " you edited" : std::string()));
      }
    }
  }
  /* Layers moved out of a group let go first, before any group (the one they joined, say) syncs. */
  for (Layer *group : together_on) {
    const auto [removed, kept] = key_together_leavers_release(doc, *group);
    if (removed + kept > 0) {
      report(ReportType::Info, group->name + ": layers moved out: removed " + std::to_string(removed) +
                                   " filler keys" +
                                   (kept > 0 ? ", kept " + std::to_string(kept) + " you edited" : std::string()));
    }
  }
  std::set<const Layer *> keyed_layers;
  for (size_t i = 0; i < flat.size(); i++) {
    if (keyed_here[i]) {
      keyed_layers.insert(flat[i]);
    }
  }
  const std::string timeline = doc.action.empty() ? std::string() :
                                                    std::to_string(doc.action_layer) + "/" + doc.action;
  bool together_went = false;
  for (Layer *group : together_on) {
    if (group->key_together_settled && group->key_together_action != timeline &&
        !group->key_together_frames.count(timeline))
    {
      /* Another timeline than it last keyed together (an action entered) and not one it keyed together in before:
       * filled once something in it is keyed, so entering an action and leaving (as Keep Poses does to see each)
       * changes nothing. */
      const std::vector<Layer *> inside = key_together_layers(doc, *group);
      if (std::none_of(inside.begin(), inside.end(), [&](const Layer *l) { return keyed_layers.count(l) > 0; })) {
        continue;
      }
    }
    bool went = false;
    const int changed = key_together_sync(doc, *group, !group->key_together_settled, &went);
    together_went = together_went || went;
    group->key_together_settled = true;
    if (changed > 0) {
      retimed = true;
      report(ReportType::Info, group->name + ": Key Together gave " + std::to_string(changed) +
                                   " keys the timing most of its layers have on their frame");
    }
  }
  simulation_in(doc);
  layer_for_each_channel(doc.simulation, [&](auto &ch, auto &value) { record(ch, value, frame, auto_key, replace); });
  layer_for_each_channel(document_camera(doc),
                         [&](auto &ch, auto &value) { record(ch, value, frame, auto_key, replace); });
  const bool keys_put = std::any_of(keyed_here.begin(), keyed_here.end(), [](char w) { return w != 0; });
  const bool keys_gone = std::any_of(keys_went.begin(), keys_went.end(), [](char w) { return w != 0; });
  /* In a fix that follows bones, which starts on frame 1: a channel first keyed later starts from its setup there, a
   * key of it, so what shows while it is edited is what plays. */
  bool starts = false;
  if (keys_put && frame > 1 && !doc.action.empty()) {
    if (Layer *owner = layer_find(doc, doc.action_layer); owner && bone_fix_find(*owner, doc.action)) {
      owner_for_each_channel(*owner, [&](auto &ch, auto & /*value*/) {
        if (!ch.animated() || ch.key_at(1)) {
          return;
        }
        const auto first = std::find_if(ch.keys.begin(), ch.keys.end(), [](const auto &k) { return k.frame >= 1; });
        if (first == ch.keys.end()) {
          return;
        }
        const auto setup = ch.evaluate(0);
        ch.set_key(1, setup);
        starts = true;
      });
    }
  }
  if (together_went || keys_gone || starts || retimed) {
    animation_evaluate(doc, frame);
  }
}

/* Every layer's channels evaluated on `frame`. Just after animation_record (`recorded`: every value is as the
 * edits left it, and recorded), a layer it would change nothing on is left as it is: no keys, nothing an action bone
 * action added, each channel's value its last recorded one. Most of a big rig's layers are like that, and
 * evaluating one turns its drawing's points into their changes from the setup pose and back. Bone layers always,
 * as evaluating also settles their bones. Otherwise every layer: evaluating also drops edits not recorded. */
static void evaluate_layers(std::vector<Layer> &layers, int frame, bool recorded,
                            std::unordered_set<const Layer *> *r_action_bones)
{
  for (Layer &layer : layers) {
    if (recorded && still_skipped(layer)) {
      continue;
    }
    bool needed = !recorded || layer.is_bone_layer();
    bool actions = false;
    if (!needed || r_action_bones) {
      layer_for_each_channel<false>(layer, [&](auto &ch, auto &value) {
        needed = needed || ch.animated() || action_bones_added(ch) || !ch.has_last || !(ch.last == value);
        actions = actions || !ch.actions.empty();
      });
    }
    if (needed) {
      layer_for_each_channel(layer, [&](auto &ch, auto &value) { evaluate(ch, value, frame); });
    }
    /* What action bone actions play into, found on the way (evaluating took off what they had added). */
    if (r_action_bones && actions) {
      r_action_bones->insert(&layer);
    }
    evaluate_layers(layer.children, frame, recorded, r_action_bones);
  }
}

static void evaluate_frame(Document &doc, int frame, bool recorded);

void animation_evaluate(Document &doc, int frame)
{
  OANIM_PROFILE("animation_evaluate");
  evaluate_frame(doc, frame, false);
}

/* A bone posed after action bone actions are played (Follow Point, Limit to Shape, Look At, an outer parent): what
 * those actions read may change once it is. */
static bool posed_after_action_bones(const Document &doc)
{
  for (const Layer *flat : document_layers_flat(doc)) {
    if (!flat->is_bone_layer()) {
      continue;
    }
    for (const Bone &b : flat->bones) {
      if (b.outer_bone != 0) {
        return true;
      }
      for (const BoneConstraint &c : b.constraints) {
        if (c.type == BoneConstraintType::FollowPoint || c.type == BoneConstraintType::LimitShape ||
            c.type == BoneConstraintType::LookAt)
        {
          return true;
        }
      }
    }
  }
  return false;
}

static uint64_t posed_after_reads(const Document &doc);

/* Action bone actions played again from where the bones posed after them went, until what those read stops changing
 * (see evaluate_frame). */
static void action_bones_settle(Document &doc)
{
  if (!doc.action_bones_applied || !posed_after_action_bones(doc)) {
    return;
  }
  for (int round = 0; round < 4; round++) {
    const uint64_t read = posed_after_reads(doc);
    animation_refresh_action_bones(doc);
    bone_outer_parents_update(doc);
    follow_points_update(doc);
    shape_limits_update(doc);
    if (posed_after_reads(doc) == read) {
      break;
    }
  }
}

/* What the bones posed after action bone actions read from the frame, as one number: each Limit to Shape's and Look
 * At's shape, each Follow Point's place, each outer parent's pose (to a millionth: rounding may never settle). */
static uint64_t posed_after_reads(const Document &doc)
{
  uint64_t h = 0xcbf29ce484222325ull;
  const auto mix = [&](float v) {
    h = (h ^ uint64_t(std::isfinite(v) ? std::llround(double(v) * 1e6) : 0)) * 0x100000001b3ull;
  };
  const auto mix2 = [&](float2 v) {
    mix(v.x);
    mix(v.y);
  };
  const auto mix_t = [&](const Transform2D &t) {
    for (const float v : {t.a, t.b, t.c, t.d, t.tx, t.ty}) {
      mix(v);
    }
  };
  for (const Layer *flat : document_layers_flat(doc)) {
    if (!flat->is_bone_layer()) {
      continue;
    }
    for (const Bone &b : flat->bones) {
      if (b.outer_bone != 0) {
        mix_t(b.outer_pose);
      }
      for (const BoneConstraint &c : b.constraints) {
        for (const float2 p : c.shape_region) {
          mix2(p);
        }
        for (const float2 p : c.shape_footprint) {
          mix2(p);
        }
        mix2(c.look_reach);
        mix2(c.follow_now);
        mix(c.follow_turn);
        mix(c.follow_stretch);
        mix_t(c.follow_shape);
      }
    }
  }
  return h;
}

static thread_local bool t_values_only = false;

AnimationValuesOnly::AnimationValuesOnly() : was(t_values_only)
{
  t_values_only = true;
}

AnimationValuesOnly::~AnimationValuesOnly()
{
  t_values_only = was;
}

static void evaluate_frame(Document &doc, int frame, bool recorded)
{
  std::unordered_set<const Layer *> action_bone_layers;
  {
    OANIM_PROFILE("eval_layers");
    evaluate_layers(doc.layers, frame, recorded, recorded ? &action_bone_layers : nullptr);
  }
  if (frame == 0) {
    controllers_rest(doc);
  }
  simulation_in(doc);
  layer_for_each_channel(doc.simulation, [&](auto &ch, auto &value) { evaluate(ch, value, frame); });
  simulation_out(doc);
  layer_for_each_channel(document_camera(doc), [&](auto &ch, auto &value) { evaluate(ch, value, frame); });
  doc.action_bones_applied = false;
  g_action_bone_layers = recorded ? &action_bone_layers : nullptr;
  {
    OANIM_PROFILE("eval_action_bones");
    apply_action_bone_actions(doc, frame);
  }
  g_action_bone_layers = nullptr;
  /* Drivers on top of keys and action bone actions, before references copy their originals. A driven
   * action bone plays its action bone action, and drivers reading what that moves see it. */
  if (drivers_evaluate(doc)) {
    animation_refresh_action_bones(doc);
    drivers_evaluate(doc);
  }
  /* References show their originals as they now are. */
  {
    OANIM_PROFILE("eval_references");
    references_build(doc);
  }
  /* Bone dynamics swing from the pose the keys and action bone actions give (and set each bone layer's
   * shown frame, for constraints' delays). */
  if (t_values_only) {
    doc.evaluated_frame = frame;
    return;
  }
  const int shown = doc.frame_current;
  doc.frame_current = frame;
  OANIM_PROFILE("eval_after");
  bone_outer_parents_update(doc);
  dynamics_update(doc);
  /* Follow Point and Limit to Shape read what's drawn now, dynamics included. */
  follow_points_update(doc);
  shape_limits_update(doc);
  /* Action bone actions played from bones those then move (a rig whose drawing moves the bone that poses it) are
   * worked out again from where the bones went: else the frame showed what they read on the frame shown before. Until
   * what they read stops changing, as a chain needs (a head turn moves the eye a pupil's knob looks inside, and the
   * knob plays the pupil's actions): once more only, the frame would still show some of the frame before. A few
   * rounds at most, for a rig whose drawing moves the very bone that poses it, which may never settle. */
  action_bones_settle(doc);
  doc.frame_current = shown;
  doc.evaluated_frame = frame;
}

bool animation_inputs_only(Document &doc)
{
  bool taken_in = true;
  const auto plain = [](auto &ch, auto &value) {
    using T = std::decay_t<decltype(value)>;
    if (ch.animated()) {
      value = T{};
    }
    else {
      value -= ch.from_action_bones;
    }
    ch.from_action_bones = T{};
    ch.last = T{};
    ch.has_last = false;
    ch.action_bone_live = false;
    ch.action_played = {};
  };
  const auto one = [&](Layer &l) {
    for (const Bone &b : l.bones) {
      taken_in = taken_in && b.position == bone_position_from_transform(b, b.transform) &&
                 b.angle == b.setup_angle + b.turn;
    }
    for (const MeshPoint &p : l.drawing.points) {
      taken_in = taken_in && p.pos == p.setup_pos + p.transform &&
                 (p.detail.level == 0 || p.detail.pos == p.detail.setup_pos + p.transform);
    }
    for (const Curve &c : l.drawing.curves) {
      for (const CurvePoint &cp : c.points) {
        const PointDetail &dt = l.drawing.points[size_t(cp.point)].detail;
        taken_in = taken_in && (dt.level > 0 ? dt.in == dt.setup_in + cp.change_in && dt.out == dt.setup_out + cp.change_out :
                                               cp.handle_in == handle_from_change(cp.setup_in, cp.change_in, true) &&
                                                   cp.handle_out == handle_from_change(cp.setup_out, cp.change_out, false));
      }
    }
    layer_for_each_channel<false>(l, plain);
    if (l.visible_keys.animated()) {
      l.visible = true;
    }
    /* Set for the frame shown whenever one is worked out (dynamics_update). */
    l.pose_frame = 0;
    l.dynamics_now.clear();
    for (Bone &b : l.bones) {
      b.position = {};
      b.angle = 0.0f;
      b.outer_pose = Transform2D();
      b.controller_knob_pull_now = {};
      b.controller_frames_to_keys = Transform2D();
      for (BoneConstraint &c : b.constraints) {
        c.look_reach = {};
        c.shape_region.clear();
        c.shape_footprint.clear();
        c.shape_error.clear();
        c.follow_offset = {};
        c.follow_now = c.follow_now2 = c.follow_now3 = {};
        c.follow_error.clear();
        c.follow_turn = 0.0f;
        c.follow_stretch = 1.0f;
        c.follow_shape = Transform2D();
      }
    }
    for (MeshPoint &p : l.drawing.points) {
      p.pos = {};
      p.detail.pos = p.detail.in = p.detail.out = {};
      p.detail.built_pos = p.detail.built_in = p.detail.built_out = {};
      p.detail.built = false;
    }
    for (Curve &c : l.drawing.curves) {
      for (CurvePoint &cp : c.points) {
        cp.handle_in = cp.handle_out = {};
      }
    }
  };
  const auto all = [&](auto &&self, std::vector<Layer> &layers) -> void {
    for (Layer &l : layers) {
      one(l);
      self(self, l.children);
    }
  };
  all(all, doc.layers);
  one(doc.simulation);
  one(document_camera(doc));
  /* The frame shown is not one: each frame is worked out on its own. */
  doc.frame_current = 0;
  doc.evaluated_frame = -1;
  doc.action_bones_applied = false;
  return taken_in;
}

void layer_actions_rename(Layer &layer, const std::function<std::optional<std::string>(const std::string &)> &rename)
{
  layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) {
    if (ch.actions.empty() && ch.action_setup.empty()) {
      return;
    }
    std::remove_reference_t<decltype(ch.actions)> actions;
    for (auto &[name, keys] : ch.actions) {
      if (const std::optional<std::string> to = rename(name)) {
        actions[*to] = std::move(keys);
      }
    }
    ch.actions = std::move(actions);
    std::remove_reference_t<decltype(ch.action_setup)> setup;
    for (auto &[name, key] : ch.action_setup) {
      if (const std::optional<std::string> to = rename(name)) {
        setup[*to] = std::move(key);
      }
    }
    ch.action_setup = std::move(setup);
  });
}

void layer_strip_keys(Layer &layer, bool from_now, bool keep_actions)
{
  layer_for_each_channel(layer, [&](auto &ch, auto &value) {
    using T = std::decay_t<decltype(value)>;
    value -= ch.from_action_bones;
    if (ch.animated() && !from_now) {
      value = ch.evaluate(0);
    }
    ch.keys.clear();
    if (!keep_actions) {
      ch.actions.clear();
    }
    ch.from_action_bones = T{};
    ch.action_bone_live = false;
    ch.action_played = {};
    ch.last = value;
    ch.has_last = true;
  });
  if (from_now) {
    /* The pose now becomes the setup: the points' changes from it are 0, and recording must see
     * that as how they were, not as an edit. */
    drawing_take_setup(layer.drawing);
    layer_for_each_channel(layer, [](auto &ch, auto &value) {
      ch.last = value;
      ch.has_last = true;
    });
  }
  for (Layer &child : layer.children) {
    layer_strip_keys(child, from_now, keep_actions);
  }
}

void bone_strip_keys(Bone &bone)
{
  /* As layer_strip_keys: each channel at its setup value (frame 0), with no keys on any timeline. */
  const auto strip = [](auto &ch, auto &value) {
    using T = std::decay_t<decltype(value)>;
    value -= ch.from_action_bones;
    if (ch.animated()) {
      value = ch.evaluate(0);
    }
    ch.keys.clear();
    ch.actions.clear();
    ch.action_setup.clear();
    ch.from_action_bones = T{};
    ch.action_bone_live = false;
    ch.action_played = {};
    ch.last = value;
    ch.has_last = true;
  };
  bone_changes_from_values(bone);
  strip(bone.position_keys, bone.transform);
  strip(bone.angle_keys, bone.turn);
  bone_values_from_changes(bone);
  bone_other_channels(bone, strip);
}

void animation_strip_action_bones(Document &doc)
{
  layers_for_each_channel_if(doc.layers, action_bones_added, [&](auto &ch, auto &value) {
    value -= ch.from_action_bones;
    ch.last -= ch.from_action_bones;
    ch.from_action_bones = {};
    ch.action_bone_live = false;
    ch.action_played = {};
    ch.action_slope = {};
  });
  doc.action_bones_applied = false;
}

static uint64_t g_frame_changes = 0;

/* What action bone actions are worked out from, as one number: the frame, the timeline being edited, each layer as it
 * is (its revision: an edit the app can't follow touches every layer), the action bones' angles and what moves the
 * controllers' knobs. */
static uint64_t action_bone_inputs(const Document &doc)
{
  uint64_t h = 0xcbf29ce484222325ull;
  const auto mix = [&](uint64_t v) { h = (h ^ v) * 0x100000001b3ull; };
  mix(uint64_t(reinterpret_cast<uintptr_t>(&doc)));
  mix(uint64_t(uint32_t(doc.frame_current)));
  mix(std::hash<std::string>()(doc.action));
  mix(doc.action_layer);
  mix(doc.action_bones_applied ? 1 : 2);
  const auto walk = [&](auto &&self, const std::vector<Layer> &layers) -> void {
    for (const Layer &layer : layers) {
      mix(layer.id);
      mix(layer.revision.value);
      if (layer.is_bone_layer()) {
        for (const std::string &name : layer.actions) {
          if (const Bone *b = action_bone_of(layer, name)) {
            mix(uint64_t(std::bit_cast<uint32_t>(b->angle)));
            mix(uint64_t(std::bit_cast<uint32_t>(b->turn)));
          }
        }
        const auto mix_bone = [&](const Bone &b) {
          for (const float v : {b.position.x, b.position.y, b.angle, b.scale.x, b.scale.y, b.depth}) {
            mix(uint64_t(std::bit_cast<uint32_t>(v)));
          }
        };
        for (const Bone &b : layer.bones) {
          if (bone_is_controller(b)) {
            mix(uint64_t(std::bit_cast<uint32_t>(b.position.x)));
            mix(uint64_t(std::bit_cast<uint32_t>(b.position.y)));
            /* What moves its knob: its constraints' targets and the bones they hang from (a look target moved by
             * the Bone panel's fields moves the knob as surely as a knob dragged). */
            for (const BoneConstraint &c : b.constraints) {
              int guard = 0;
              for (const Bone *t = c.target ? bone_find(layer, c.target) : nullptr; t && guard++ < 64;
                   t = t->parent ? bone_find(layer, t->parent) : nullptr)
              {
                mix_bone(*t);
              }
            }
          }
        }
      }
      self(self, layer.children);
    }
  };
  walk(walk, doc.layers);
  return h;
}

void animation_sync(Document &doc)
{
  OANIM_PROFILE("animation_sync");
  if (doc.evaluated_frame == doc.frame_current) {
    /* Same frame, but bones may have turned: action bone actions and dynamics follow at once (and a
     * setting whose keys just went shows its value). Not when nothing they are worked out from has
     * changed since: on a big rig that is most of what an idle frame costs. */
    simulation_in(doc);
    static uint64_t refreshed = 0;
    if (g_drag_doc == &doc) {
      /* A bone drag works them out itself, every update. */
      refreshed = 0;
    }
    else if (const uint64_t inputs = action_bone_inputs(doc); inputs != refreshed) {
      animation_refresh_action_bones(doc);
      refreshed = action_bone_inputs(doc);
    }
    /* Drivers follow what they read at once (a bone turned on this frame), and action bone actions what
     * they pose. */
    if (drivers_evaluate(doc)) {
      animation_refresh_action_bones(doc);
      drivers_evaluate(doc);
    }
    /* Switches follow children added, removed or picked at once. */
    switches_resolve(doc, doc.frame_current);
    /* References follow edits to their originals at once, and edits to them become theirs. */
    references_capture(doc);
    bone_outer_parents_update(doc);
    dynamics_update(doc);
    follow_points_update(doc);
    shape_limits_update(doc);
    return;
  }
  const bool recorded = doc.evaluated_frame >= 0;
  if (recorded) {
    animation_record(doc);
    g_frame_changes++;
  }
  evaluate_frame(doc, doc.frame_current, recorded);
}

void animation_sync_playing(Document &doc, uint64_t edits)
{
  OANIM_PROFILE("animation_sync_playing");
  if (doc.evaluated_frame == doc.frame_current) {
    animation_sync(doc);
    return;
  }
  const auto stamp_now = [&]() {
    uint64_t h = 0xcbf29ce484222325ull;
    for (const uint64_t v : {uint64_t(reinterpret_cast<uintptr_t>(&doc)), edits, channel_keys_generation()}) {
      h = (h ^ v) * 0x100000001b3ull;
    }
    return h;
  };
  const bool kept = g_still.valid && g_still.doc == &doc && g_still.stamp == stamp_now();
  g_still_skip = kept ? &g_still.ids : nullptr;
  animation_sync(doc);
  g_still_skip = nullptr;
  if (!kept) {
    /* Just evaluated in full: which hidden drawings are still, as of now. */
    g_still.ids.clear();
    find_still_drawings(doc, g_still.ids);
    g_still.doc = &doc;
    g_still.stamp = stamp_now();
    g_still.valid = true;
  }
}

/* --- Recording while playing ------------------------------------------------------------------ */

namespace {

struct FollowedChannel {
  void *channel;
  void *value;
  const std::type_info *type;
};

template<typename Walk> std::vector<FollowedChannel> followed_channels(Walk &&walk)
{
  std::vector<FollowedChannel> refs;
  walk([&](auto &ch, auto &value) { refs.push_back({&ch, &value, &typeid(value)}); });
  return refs;
}

/* See animation_follow_playback. */
template<typename Walk> bool follow_playback(Walk &&start, Walk &&dragged, Walk &&now, std::vector<char> &held)
{
  const std::vector<FollowedChannel> s = followed_channels(start), d = followed_channels(dragged), n = followed_channels(now);
  if (s.size() != d.size() || s.size() != n.size()) {
    return false;
  }
  for (size_t i = 0; i < s.size(); i++) {
    if (*s[i].type != *d[i].type || *s[i].type != *n[i].type) {
      return false;
    }
  }
  if (held.size() != s.size()) {
    held.assign(s.size(), 0);
  }
  size_t i = 0;
  start([&](auto &ch, auto &value) {
    using C = std::remove_reference_t<decltype(ch)>;
    using V = std::remove_reference_t<decltype(value)>;
    const C &d_ch = *static_cast<const C *>(d[i].channel);
    const V &d_value = *static_cast<const V *>(d[i].value);
    const C &n_ch = *static_cast<const C *>(n[i].channel);
    const V &n_value = *static_cast<const V *>(n[i].value);
    /* Held by the drag: changed from what the frame just left had it at, now or before. */
    held[i] = held[i] || !d_ch.has_last || !(d_value == d_ch.last);
    ch = n_ch;
    if (!held[i]) {
      value = n_value;
    }
    i++;
  });
  return true;
}

}  // namespace

bool animation_follow_playback(Document &start, Document &dragged, Document &now, std::vector<char> &held)
{
  const auto walk = [](Document &doc) {
    return [&doc](auto &&f) {
      layers_for_each_channel(doc.layers, f);
      layer_for_each_channel(document_camera(doc), f);
    };
  };
  if (!follow_playback(walk(start), walk(dragged), walk(now), held)) {
    return false;
  }
  /* It is now on the new frame: an edit made from it (the drag confirmed) is that frame's, not the
   * one the drag began on. */
  start.frame_current = now.frame_current;
  start.evaluated_frame = now.evaluated_frame;
  start.action_bones_applied = now.action_bones_applied;
  return true;
}

bool animation_follow_playback(std::vector<Bone> &start, std::vector<Bone> &dragged, std::vector<Bone> &now,
                               std::vector<char> &held)
{
  /* Bone layers to walk, holding the bones for the while. */
  Layer s, d, n;
  s.bones = std::move(start);
  d.bones = std::move(dragged);
  n.bones = std::move(now);
  const auto walk = [](Layer &layer) { return [&layer](auto &&f) { layer_for_each_channel(layer, f); }; };
  const bool done = follow_playback(walk(s), walk(d), walk(n), held);
  start = std::move(s.bones);
  dragged = std::move(d.bones);
  now = std::move(n.bones);
  return done;
}

uint64_t animation_frame_changes()
{
  return g_frame_changes;
}

/* --- Actions ----------------------------------------------------------------------------------- */

Layer *action_owner(Document &doc, uint64_t layer_id)
{
  Layer *layer = layer_find(doc, layer_id);
  if (!layer) {
    return nullptr;
  }
  if (layer->is_bone_layer()) {
    return layer;
  }
  const Layer *armature = layer_armature(doc, layer_id);
  return armature ? layer_find(doc, armature->id) : nullptr;
}

std::vector<Layer *> action_owners(Document &doc, uint64_t layer_id)
{
  std::vector<Layer *> owners;
  for (Layer *owner = action_owner(doc, layer_id); owner;) {
    owners.push_back(owner);
    const Layer *around = layer_armature(doc, owner->id);
    owner = around ? layer_find(doc, around->id) : nullptr;
  }
  return owners;
}

/* Calls f(channel, value) for every channel of a bone layer and everything inside it. */
template<typename F> static void owner_for_each_channel(Layer &owner, F &&f)
{
  layer_for_each_channel(owner, f);
  layers_for_each_channel(owner.children, f);
}

/* As owner_for_each_channel, on the layers with keys in action `action` only (the rest have nothing to play). */
template<typename F> static void owner_for_each_channel_with(Layer &owner, const std::string &action, F &&f)
{
  const auto in_action = [&](const auto &ch) { return ch.actions.find(action) != ch.actions.end(); };
  bool any = false;
  layer_for_each_channel<false>(owner, [&](auto &ch, auto & /*value*/) { any = any || in_action(ch); });
  if (any) {
    layer_for_each_channel(owner, f);
  }
  layers_for_each_channel_if(owner.children, in_action, f);
}

/* Puts the timeline being edited away under `from` and brings out `to` ("" = mainline). */
template<typename T> static void swap_timeline(Channel<T> &ch, T &value, const std::string &from, const std::string &to)
{
  if (from == to) {
    return;
  }
  /* The setup pose as it is now (frame 0 of what's being edited). */
  const T setup = ch.animated() ? ch.evaluate(0) : value;
  std::vector<Key<T>> away = std::move(ch.keys);
  ch.keys.clear();
  const bool mainline_animated = from.empty() && !away.empty();
  if (!from.empty()) {
    /* An action keeps its keys after frame 0; frame 0 belongs to the setup pose, all but its path handles, which are
     * the action's own. */
    ch.action_setup.erase(from);
    if constexpr (std::is_same_v<T, float2>) {
      for (const Key<T> &k : away) {
        if (k.frame == 0 && k.path_handles != PathHandles::Auto) {
          ch.action_setup[from] = k;
        }
      }
    }
    std::erase_if(away, [](const Key<T> &k) { return k.frame == 0; });
  }
  if (!away.empty()) {
    ch.actions[from] = std::move(away);
  }
  else {
    ch.actions.erase(from);
  }
  if (auto it = ch.actions.find(to); it != ch.actions.end()) {
    ch.keys = std::move(it->second);
    ch.actions.erase(it);
  }
  if (to.empty()) {
    /* Back on the mainline: setup edits made in the action land on its frame 0. */
    if (ch.animated()) {
      if (Key<T> *k = ch.key_at(0)) {
        k->value = setup;
      }
      else {
        ch.set_key(0, setup);
      }
    }
  }
  else if ((ch.animated() || mainline_animated) && !ch.key_at(0)) {
    /* An action starts from the setup pose: frame 0 shows the setup keys of everything animated,
     * as on the mainline. */
    Key<T> &k = ch.set_key(0, setup);
    if constexpr (std::is_same_v<T, float2>) {
      if (auto it = ch.action_setup.find(to); it != ch.action_setup.end()) {
        k.path_handles = it->second.path_handles;
        k.path_in = it->second.path_in;
        k.path_out = it->second.path_out;
      }
    }
  }
  if (!to.empty()) {
    ch.action_setup.erase(to);
  }
  value = setup;
}

void drawing_timeline_swap(VectorDrawing &drawing, const std::string &from, const std::string &to)
{
  Layer holder;
  holder.type = LayerType::Vector;
  holder.drawing = std::move(drawing);
  layer_for_each_channel(holder, [&](auto &ch, auto &value) { swap_timeline(ch, value, from, to); });
  drawing = std::move(holder.drawing);
}

static std::string bone_fix_unique(const Layer &owner, const std::string &base, const std::string &self = {});

bool document_set_action(Document &doc, uint64_t owner_id, const std::string &name)
{
  Layer *owner = name.empty() ? nullptr : layer_find(doc, owner_id);
  if (!name.empty() && (!owner || std::find(owner->actions.begin(), owner->actions.end(), name) == owner->actions.end()))
  {
    return false;
  }
  if (doc.action == name && (name.empty() || doc.action_layer == owner_id)) {
    return true;
  }
  const int frame = doc.frame_current;
  animation_record(doc);
  /* Swap on the setup pose, where action bone actions add nothing. */
  animation_evaluate(doc, 0);
  /* Leave the action being edited (back to the mainline), then go into the new one. */
  if (!doc.action.empty()) {
    if (Layer *from = layer_find(doc, doc.action_layer)) {
      const std::string from_name = doc.action;
      owner_for_each_channel(*from, [&](auto &ch, auto &value) { swap_timeline(ch, value, from_name, ""); });
    }
  }
  const uint64_t left_layer = doc.action_layer;
  const std::string left = doc.action;
  doc.action.clear();
  doc.action_layer = 0;
  /* A fix that follows bones, left: named after the actions playing where it now ends (unless renamed by hand). */
  if (Layer *from = left.empty() ? nullptr : layer_find(doc, left_layer)) {
    if (const BoneFix *fix = bone_fix_find(*from, left); fix && fix->auto_name && left != name) {
      const std::string renamed = bone_fix_unique(*from, bone_fix_name(*from, *fix), left);
      if (renamed != left) {
        document_action_rename(doc, left_layer, left, renamed);
      }
    }
  }
  if (owner) {
    owner_for_each_channel(*owner, [&](auto &ch, auto &value) { swap_timeline(ch, value, "", name); });
    doc.action = name;
    doc.action_layer = owner->id;
  }
  animation_evaluate(doc, frame);
  return true;
}

bool document_set_action_by_name(Document &doc, const std::string &name)
{
  if (name.empty()) {
    return document_set_action(doc, 0, "");
  }
  for (Layer *owner : action_owners(doc, doc.active_layer)) {
    if (std::find(owner->actions.begin(), owner->actions.end(), name) != owner->actions.end()) {
      return document_set_action(doc, owner->id, name);
    }
  }
  for (const Layer *layer : document_layers_flat(doc)) {
    if (layer->is_bone_layer() && std::find(layer->actions.begin(), layer->actions.end(), name) != layer->actions.end()) {
      return document_set_action(doc, layer->id, name);
    }
  }
  return false;
}

/* Calls f(channel) for every channel of a bone layer and the layers inside it, keys only (no values worked out). */
template<typename F> static void owner_for_each_channel_keys(Layer &layer, F &&f)
{
  layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) { f(ch); });
  for (Layer &child : layer.children) {
    owner_for_each_channel_keys(child, f);
  }
}

EditedAction edited_action_save(Document &doc)
{
  EditedAction saved;
  saved.name = doc.action;
  saved.owner = doc.action.empty() ? 0 : doc.action_layer;
  if (Layer *owner = saved.name.empty() ? nullptr : layer_find(doc, saved.owner)) {
    owner_for_each_channel_keys(*owner, [&](auto &ch) {
      using K = std::remove_cvref_t<decltype(ch.keys.front())>;
      const K *k = ch.key_at(0);
      saved.setup_keys.push_back(k ? std::make_shared<K>(*k) : nullptr);
    });
  }
  return saved;
}

void edited_action_restore(Document &doc, const EditedAction &saved)
{
  if (doc.action != saved.name || (!saved.name.empty() && doc.action_layer != saved.owner)) {
    document_set_action(doc, saved.owner, saved.name);
  }
  Layer *owner = saved.name.empty() || doc.action != saved.name ? nullptr : layer_find(doc, saved.owner);
  if (!owner) {
    return;
  }
  /* Only onto the same channels (nothing on the way adds or takes away points or bones). */
  size_t count = 0;
  owner_for_each_channel_keys(*owner, [&](auto & /*ch*/) { count++; });
  if (count != saved.setup_keys.size()) {
    return;
  }
  size_t i = 0;
  owner_for_each_channel_keys(*owner, [&](auto &ch) {
    using K = std::remove_cvref_t<decltype(ch.keys.front())>;
    const std::shared_ptr<void> &kept = saved.setup_keys[i++];
    if (!kept) {
      return;
    }
    const K &was = *static_cast<const K *>(kept.get());
    K *now = ch.key_at(0);
    if (!now) {
      now = &ch.set_key(0, was.value);
    }
    *now = was;
  });
}

bool document_action_delete(Document &doc, uint64_t owner_id, const std::string &name)
{
  Layer *owner = layer_find(doc, owner_id);
  if (!owner || name.empty() || std::find(owner->actions.begin(), owner->actions.end(), name) == owner->actions.end()) {
    return false;
  }
  if (doc.action == name && doc.action_layer == owner_id) {
    document_set_action(doc, 0, "");
  }
  std::erase(owner->actions, name);
  std::erase_if(owner->bone_fixes, [&](const BoneFix &f) { return f.name == name; });
  std::erase_if(owner->action_plays, [&](const ActionPlay &a) { return a.name == name; });
  for (Bone &bone : owner->bones) {
    std::replace(bone.controller_actions.begin(), bone.controller_actions.end(), name, std::string());
  }
  owner_for_each_channel(*owner, [&](auto &ch, auto & /*value*/) {
    ch.actions.erase(name);
    ch.action_setup.erase(name);
  });
  animation_evaluate(doc, doc.frame_current);
  return true;
}

std::string document_action_new(Document &doc, uint64_t owner_id, const std::string &name)
{
  Layer *owner = layer_find(doc, owner_id);
  if (!owner || !owner->is_bone_layer()) {
    return {};
  }
  const std::string base = name.empty() ? "Action" : name;
  std::string unique = base;
  for (int i = 1; std::find(owner->actions.begin(), owner->actions.end(), unique) != owner->actions.end(); i++) {
    char suffix[16];
    std::snprintf(suffix, sizeof(suffix), ".%03d", i);
    unique = base + suffix;
  }
  owner->actions.push_back(unique);
  document_set_action(doc, owner_id, unique);
  return unique;
}

/* --- Action bone actions (Moho's smart bones) ------------------------------------------------------- */

const Bone *action_bone_of(const Layer &owner, const std::string &action)
{
  if (const Bone *dial = controller_dial_of_action(owner, action)) {
    return dial;
  }
  return controller_of_action(owner, action);
}

/* A channel's timeline in action `name` with its setup value at frame 0, sampled at a fractional
 * frame (between the whole frames either side). */
template<typename T>
static T action_bone_sample(const std::vector<Key<T>> &keys, const T &setup, float t, bool constant = false)
{
  const ChannelKeysQuiet scratch;
  Channel<T> c;
  c.keys = keys;
  /* A yes/no channel (visibility, Draw Order) holds each key until the next, between frames too: the
   * bone turning past a key's frame switches it, never a blend of the two. */
  c.constant = constant;
  c.set_key(0, setup);
  /* A frame worked out a hair short of a whole one (a knob at its box's edge, through its timing's sums) is that frame:
   * else a Step key there, such as a layer hidden at a blink's end, never comes. */
  if (const float whole = std::round(t); std::abs(t - whole) < 1e-3f) {
    t = whole;
  }
  const int f0 = int(std::floor(t));
  const float frac = t - float(f0);
  const T a = c.evaluate(f0);
  if (frac <= 0.0f || constant) {
    return a;
  }
  /* A Step key waits for its frame, between frames too: a bone turning past it jumps, never a blend of the two. */
  if (const Key<T> *next = c.key_at(f0 + 1); next && next->interp == Interp::Step) {
    return a;
  }
  const T b = c.evaluate(f0 + 1);
  return a + (b - a) * frac;
}

/* The action frame where the driving bone's keyed angle reaches `angle`: from frame 0 (its setup
 * angle) along its keys; the last frame past the end; 0 on the other side of the setup. */
static float action_bone_frame(const std::vector<Key<float>> &keys, float setup, float angle)
{
  if (keys.empty()) {
    return 0.0f;
  }
  const float last = float(keys.back().frame);
  const float step = 0.25f;
  float prev = action_bone_sample(keys, setup, 0.0f);
  for (float s = step; s <= last + 1e-4f; s += step) {
    const float now = action_bone_sample(keys, setup, s);
    if ((prev - angle) * (now - angle) <= 0.0f && now != prev) {
      return s - step + step * (angle - prev) / (now - prev);
    }
    prev = now;
  }
  const float end = action_bone_sample(keys, setup, last);
  const bool same_side = (end - setup) * (angle - setup) > 0.0f;
  return same_side && std::abs(angle - setup) > std::abs(end - setup) ? last : 0.0f;
}

/* Moho's 360 action bone: an action whose driving bone's last key is exactly one whole turn from its setup
 * angle (either way) goes round and round: the bone's turn counts modulo a whole turn, so turning on past
 * the end starts it over and turning back past the setup plays it from the end (a 360 head turn on a dial).
 * Whole turns are within a tenth of a degree. */
static bool action_bone_keys_full_turn(const std::vector<Key<float>> &keys)
{
  return !keys.empty() && std::fabs(std::fabs(keys.back().value) - 2.0f * PI) < 0.1f * PI / 180.0f;
}

static float action_bone_turn_wrapped(const std::vector<Key<float>> &keys, float turn, bool loops)
{
  if (!loops || keys.empty() || std::fabs(keys.back().value) < 1e-6f) {
    return turn;
  }
  if (!action_bone_keys_full_turn(keys)) {
    /* Looped by hand: turned on past its end it starts over, never 0 (the end pose, not the setup). */
    const float along = turn / keys.back().value;
    return along <= 1.0f ? turn : turn - keys.back().value * std::ceil(along - 1.0f);
  }
  const float full = 2.0f * PI;
  /* Into [0, a turn) for an action keyed the positive way, (-a turn, 0] for one keyed the other. */
  return keys.back().value > 0.0f ? turn - std::floor(turn / full) * full : turn - std::ceil(turn / full) * full;
}

bool action_bone_action_full_turn(const Layer &owner, const std::string &name)
{
  const Bone *driver = action_bone_of(owner, name);
  if (!driver) {
    return false;
  }
  const auto it = driver->angle_keys.actions.find(name);
  return it != driver->angle_keys.actions.end() && action_bone_keys_full_turn(it->second);
}

const std::vector<Key<float>> *bone_turn_keys(const Document &doc, const Layer &owner, const Bone &bone,
                                              const std::string &name)
{
  if (doc.action == name && doc.action_layer == owner.id) {
    return &bone.angle_keys.keys;
  }
  const auto it = bone.angle_keys.actions.find(name);
  return it != bone.angle_keys.actions.end() ? &it->second : nullptr;
}

BoneTurnSlots bone_turn_slots(const Document &doc, const Layer &owner, const Bone &bone)
{
  BoneTurnSlots slots;
  if (bone_is_controller(bone)) {
    return slots;
  }
  /* Its two names, each with the way its last key turns the bone (0 not keyed). */
  std::array<std::pair<std::string, int>, 2> own;
  int count = 0;
  for (const std::string &name : {bone.name, bone.name + " 2"}) {
    if (std::find(owner.actions.begin(), owner.actions.end(), name) == owner.actions.end() ||
        controller_dial_of_action(owner, name) != &bone)
    {
      continue;
    }
    const std::vector<Key<float>> *keys = bone_turn_keys(doc, owner, bone, name);
    const float last = keys && !keys->empty() ? keys->back().value : 0.0f;
    const int way = last > 1e-6f ? 1 : last < -1e-6f ? -1 : 0;
    if (keys && !keys->empty() && std::fabs(std::fabs(last) - 2.0f * PI) < 0.1f * PI / 180.0f) {
      slots.full_turn = true;
    }
    own[size_t(count++)] = {name, way};
  }
  slots.full_turn = slots.full_turn || bone.full_turn;
  const auto place = [&](const std::string &name, int want) {
    const int slot = slots.action[size_t(want)].empty() ? want : 1 - want;
    if (slots.action[size_t(slot)].empty()) {
      slots.action[size_t(slot)] = name;
    }
  };
  /* Keyed ones first, so one not keyed yet takes what is left. */
  for (int i = 0; i < count; i++) {
    if (own[size_t(i)].second != 0) {
      place(own[size_t(i)].first, own[size_t(i)].second > 0 ? 0 : 1);
    }
  }
  for (int i = 0; i < count; i++) {
    if (own[size_t(i)].second == 0) {
      place(own[size_t(i)].first, own[size_t(i)].first == bone.name ? 0 : 1);
    }
  }
  /* A whole turn plays from the first slot. */
  if (slots.full_turn && slots.action[0].empty()) {
    std::swap(slots.action[0], slots.action[1]);
  }
  return slots;
}

/* What each action bone action's bone picks: its frame for the bone's turn in `turns` (owner's bones, in order), or a
 * controller's for where its knob is in `knobs` (frames). */
static std::vector<std::pair<std::string, float>> action_bone_frames_for(const Layer &owner,
                                                                         const std::vector<float> &turns,
                                                                         const std::vector<float2> &knobs,
                                                                         bool with_muted = false)
{
  std::vector<std::pair<std::string, float>> frames;
  for (const std::string &name : owner.actions) {
    const Bone *driver = action_bone_of(owner, name);
    if (!driver || (!with_muted && action_muted(owner, name))) {
      continue;
    }
    if (bone_is_controller(*driver)) {
      int side = 0;
      controller_of_action(owner, name, &side);
      const float2 knob = knobs[size_t(driver - owner.bones.data())];
      const float along = (controller_side_axis(side) == 0 ? knob.x : knob.y) * controller_side_sign(side);
      /* Through the side's timing: how far out the knob is picks the frame. */
      if (const float t = controller_side_frame(*driver, side, along); t > 0.0f) {
        frames.push_back({name, t});
      }
      continue;
    }
    const auto it = driver->angle_keys.actions.find(name);
    if (it == driver->angle_keys.actions.end()) {
      continue;
    }
    const float turn = turns[size_t(driver - owner.bones.data())];
    /* The driving bone's keys are its Angle (the turn from its setup pose), so its action starts at
     * 0 and the bone's turn now picks the frame; turning an unkeyed bone plays it at once. */
    const float t = action_bone_frame(it->second, 0.0f,
                                      action_bone_turn_wrapped(it->second, turn, action_loops(owner, name)));
    if (t > 0.0f) {
      frames.push_back({name, t});
    }
  }
  return frames;
}

std::vector<std::pair<std::string, float>> action_bone_actions_playing(const Layer &owner)
{
  std::vector<float> turns;
  std::vector<float2> knobs;
  for (const Bone &b : owner.bones) {
    turns.push_back(b.angle - b.setup_angle);
    knobs.push_back(controller_knob_played(owner, b));
  }
  return action_bone_frames_for(owner, turns, knobs);
}

/* Whether action bone action `by` turns the bone of action bone action `name`. Actions key every bone, most held
 * still. A fix that follows bones is one too: it waits for what moves its bones, and what it moves waits for it. */
static bool action_bone_action_turns(const Layer &owner, const std::string &by, const std::string &name)
{
  /* A fix's keys on the bones it follows are its line: they never move them. */
  const BoneFix *by_fix = bone_fix_find(owner, by);
  const auto traced = [&](const Bone &b) {
    return by_fix && std::find(by_fix->follows.begin(), by_fix->follows.end(), b.id) != by_fix->follows.end();
  };
  if (const BoneFix *fix = bone_fix_find(owner, name)) {
    if (by == name) {
      return false;
    }
    for (const uint64_t id : fix->follows) {
      const Bone *b = bone_find(owner, id);
      if (!b || traced(*b)) {
        continue;
      }
      /* What moves a knob, or turns a bone, moves the bone's actions: asked of them. */
      for (const std::string &action : owner.actions) {
        if (action != by && action_bone_of(owner, action) == b && !bone_fix_find(owner, action) &&
            action_bone_action_turns(owner, by, action))
        {
          return true;
        }
      }
      if (!bone_is_controller(*b)) {
        const auto it = b->angle_keys.actions.find(by);
        if (it != b->angle_keys.actions.end() &&
            std::any_of(it->second.begin(), it->second.end(), [](const Key<float> &k) { return std::abs(k.value) > 1e-6f; }))
        {
          return true;
        }
      }
    }
    return false;
  }
  /* An action played at its own Frame: `by` keys that Frame (one action playing another). */
  if (by != name && action_frame_by(owner, name) == ActionFrameBy::Own) {
    const ActionPlay *a = action_play_find(owner, name);
    if (!a) {
      return false;
    }
    const auto it = a->frame_keys.actions.find(by);
    return it != a->frame_keys.actions.end() &&
           std::any_of(it->second.begin(), it->second.end(), [](const Key<float> &k) { return std::abs(k.value) > 1e-6f; });
  }
  const Bone *bone = action_bone_of(owner, name);
  if (!bone || by == name) {
    return false;
  }
  const auto moves_knob = [&](const Bone &knob) {
    const auto it = knob.position_keys.actions.find(by);
    return !traced(knob) && it != knob.position_keys.actions.end() &&
           std::any_of(it->second.begin(), it->second.end(), [](const Key<float2> &k) {
             return std::abs(k.value.x) > 1e-6f || std::abs(k.value.y) > 1e-6f;
           });
  };
  if (bone_is_controller(*bone)) {
    /* Its own sides' actions key its timing, not a move. */
    if (std::find(bone->controller_actions.begin(), bone->controller_actions.end(), by) == bone->controller_actions.end() &&
        moves_knob(*bone))
    {
      return true;
    }
    /* An independent knob plays where it sits in its box: an action moving the box or its Knob Parent (or what either
     * hangs from) moves it there, so it plays first (a head turn before the eyes riding it). */
    std::vector<const std::string *> movers = {&by};
    const auto moves = [&](const Bone &b) {
      return !traced(b) && std::any_of(movers.begin(), movers.end(), [&](const std::string *action) {
        const auto pos = b.position_keys.actions.find(*action);
        const auto ang = b.angle_keys.actions.find(*action);
        return (pos != b.position_keys.actions.end() &&
                std::any_of(pos->second.begin(), pos->second.end(), [](const Key<float2> &k) {
                  return std::abs(k.value.x) > 1e-6f || std::abs(k.value.y) > 1e-6f;
                })) ||
               (ang != b.angle_keys.actions.end() && std::any_of(ang->second.begin(), ang->second.end(), [](const Key<float> &k) {
                  return std::abs(k.value) > 1e-6f;
                }));
      });
    };
    const auto moves_from = [&](uint64_t id) {
      for (int depth = 0; id != 0 && depth < 256; depth++) {
        const Bone *up = bone_find(owner, id);
        if (!up) {
          return false;
        }
        if (moves(*up)) {
          return true;
        }
        id = up->parent;
      }
      return false;
    };
    if (bone->controller_knob_independent && (moves_from(bone->parent) || moves_from(bone->controller_knob_parent))) {
      return true;
    }
    /* Its constraints move it too: an action moving one's target (or what it hangs from) plays first. */
    for (const BoneConstraint &c : bone->constraints) {
      if (c.enabled && c.influence > 0.0f && controller_constraint_works(c.type) && c.target != 0 && moves_from(c.target)) {
        return true;
      }
    }
    return false;
  }
  const auto it = bone->angle_keys.actions.find(by);
  return !traced(*bone) && it != bone->angle_keys.actions.end() &&
         std::any_of(it->second.begin(), it->second.end(), [](const Key<float> &k) { return std::abs(k.value) > 1e-6f; });
}

/* Plays the action bone actions `frames_now` says are playing, an action bone action that turns another's bone (a dial
 * made of two
 * head turns) before that one, which then picks its frame by the turn it was given. Actions turning each other play as
 * they are, each once. Returns them all with their frames, as played. */
template<typename Frames, typename Play>
static std::vector<std::pair<std::string, float>> action_bone_actions_in_order(const Layer &owner, Frames &&frames_now,
                                                                               Play &&play)
{
  std::vector<std::pair<std::string, float>> played;
  bool nested = false;
  for (const std::string &a : owner.actions) {
    for (const std::string &b : owner.actions) {
      nested = nested || action_bone_action_turns(owner, a, b);
    }
  }
  const auto done = [&](const std::string &name) {
    return std::any_of(played.begin(), played.end(), [&](const auto &p) { return p.first == name; });
  };
  for (size_t round = 0; round <= owner.actions.size(); round++) {
    std::vector<std::pair<std::string, float>> ready = frames_now();
    std::erase_if(ready, [&](const auto &p) { return done(p.first); });
    std::vector<std::pair<std::string, float>> now;
    for (const auto &candidate : ready) {
      const bool waits = std::any_of(ready.begin(), ready.end(), [&](const auto &other) {
        return action_bone_action_turns(owner, other.first, candidate.first);
      });
      if (!waits) {
        now.push_back(candidate);
      }
    }
    for (const auto &[name, t] : now.empty() ? ready : now) {
      play(name, t);
      played.push_back({name, t});
    }
    if (ready.empty() || !nested) {
      break;
    }
  }
  return played;
}

float action_bone_action_length(const Layer &owner, const std::string &name)
{
  const Bone *driver = action_bone_of(owner, name);
  if (!driver) {
    return 0.0f;
  }
  if (bone_is_controller(*driver)) {
    int side = 0;
    controller_of_action(owner, name, &side);
    return controller_side_frames(*driver, side);
  }
  if (const auto it = driver->angle_keys.actions.find(name); it != driver->angle_keys.actions.end() && !it->second.empty()) {
    return float(it->second.back().frame);
  }
  /* Being edited: its keys are the bone's own. */
  return driver->angle_keys.keys.empty() ? 0.0f : float(driver->angle_keys.keys.back().frame);
}

/* --- The Actions panel ------------------------------------------------------------------------------------------ */

std::string action_frame_path(const std::string &name)
{
  return "actions[\"" + name + "\"].frame";
}

const ActionPlay *action_play_find(const Layer &owner, const std::string &name)
{
  for (const ActionPlay &a : owner.action_plays) {
    if (a.name == name) {
      return &a;
    }
  }
  return nullptr;
}

ActionPlay *action_play_find(Layer &owner, const std::string &name)
{
  return const_cast<ActionPlay *>(action_play_find(std::as_const(owner), name));
}

ActionPlay &action_play_ensure(Layer &owner, const std::string &name)
{
  if (ActionPlay *a = action_play_find(owner, name)) {
    return *a;
  }
  ActionPlay &a = owner.action_plays.emplace_back();
  a.name = name;
  /* At rest until now: setting its Frame is an edit to record (a key with auto-keying), not new data. */
  a.frame_keys.last = 0.0f;
  a.frame_keys.has_last = true;
  return a;
}

ActionFrameBy action_frame_by(const Layer &owner, const std::string &name, const Bone **r_holder)
{
  const Bone *holder = nullptr;
  ActionFrameBy by = ActionFrameBy::Own;
  if (bone_fix_find(owner, name)) {
    by = ActionFrameBy::Fix;
  }
  else if ((holder = controller_of_action(owner, name))) {
    by = ActionFrameBy::Knob;
  }
  else if ((holder = controller_dial_of_action(owner, name))) {
    by = ActionFrameBy::Bone;
  }
  if (r_holder) {
    *r_holder = holder;
  }
  return by;
}

bool action_muted(const Layer &owner, const std::string &name)
{
  const ActionPlay *a = action_play_find(owner, name);
  return a && a->mute;
}

bool action_loops(const Layer &owner, const std::string &name)
{
  if (const ActionPlay *a = action_play_find(owner, name); a && a->loop != ActionLoop::Auto) {
    return a->loop == ActionLoop::On;
  }
  return action_bone_action_full_turn(owner, name);
}

float action_length(const Layer &owner, const std::string &name, bool edited)
{
  if (const ActionFrameBy by = action_frame_by(owner, name); by == ActionFrameBy::Bone || by == ActionFrameBy::Knob) {
    return action_bone_action_length(owner, name);
  }
  int last = 0;
  owner_for_each_channel(const_cast<Layer &>(owner), [&](auto &ch, auto & /*value*/) {
    if (edited) {
      last = ch.keys.empty() ? last : std::max(last, ch.keys.back().frame);
    }
    else if (const auto it = ch.actions.find(name); it != ch.actions.end() && !it->second.empty()) {
      last = std::max(last, it->second.back().frame);
    }
  });
  return float(last);
}

/* The frame of its action an own Frame plays: past the end the last frame, or looped round (never 0, the end pose). */
static float action_own_frame(float frame, float length, bool loops)
{
  if (frame <= 0.0f || length <= 0.0f) {
    return std::max(frame, 0.0f);
  }
  return !loops ? std::min(frame, length) : frame - length * std::ceil(frame / length - 1.0f);
}

/* The lengths of the actions playing at their own Frame, found in one pass over the bone layer when first asked for
 * (a big rig's channels are many, and the actions are played in rounds). */
struct ActionOwnLengths {
  bool found = false;
  std::map<std::string, float> of;
};

/* The actions playing at their own Frame, as action_bone_frames_for gives action bone actions: `at` a frame to work
 * their Frame out on (dynamics), -1 for the value it has now. */
static void action_own_frames(const Layer &owner, int at, ActionOwnLengths &lengths,
                              std::vector<std::pair<std::string, float>> &r_frames)
{
  for (const ActionPlay &a : owner.action_plays) {
    if (a.mute || action_frame_by(owner, a.name) != ActionFrameBy::Own ||
        std::find(owner.actions.begin(), owner.actions.end(), a.name) == owner.actions.end())
    {
      continue;
    }
    const float frame = at >= 0 && a.frame_keys.animated() ? a.frame_keys.evaluate(at) : a.frame;
    if (frame <= 0.0f) {
      continue;
    }
    if (!lengths.found) {
      lengths.found = true;
      owner_for_each_channel(const_cast<Layer &>(owner), [&](auto &ch, auto & /*value*/) {
        for (const auto &[name, keys] : ch.actions) {
          if (!keys.empty()) {
            float &last = lengths.of[name];
            last = std::max(last, float(keys.back().frame));
          }
        }
      });
    }
    const auto it = lengths.of.find(a.name);
    r_frames.push_back({a.name, action_own_frame(frame, it == lengths.of.end() ? 0.0f : it->second, action_loops(owner, a.name))});
  }
}

float action_frame_shown(const Layer &owner, const std::string &name)
{
  switch (action_frame_by(owner, name)) {
    case ActionFrameBy::Own: {
      const ActionPlay *a = action_play_find(owner, name);
      return a ? a->frame : 0.0f;
    }
    case ActionFrameBy::Fix:
      return bone_fix_play(owner, *bone_fix_find(owner, name)).strength;
    default: {
      /* Where its bone or knob has it, muted or not. */
      std::vector<float> turns;
      std::vector<float2> knobs;
      for (const Bone &b : owner.bones) {
        turns.push_back(b.angle - b.setup_angle);
        knobs.push_back(controller_knob_played(owner, b));
      }
      for (const auto &[n, t] : action_bone_frames_for(owner, turns, knobs, true)) {
        if (n == name) {
          return t;
        }
      }
      return 0.0f;
    }
  }
}

bool action_frame_set(Layer &owner, const std::string &name, float frame)
{
  frame = std::max(frame, 0.0f);
  const Bone *holder = nullptr;
  switch (action_frame_by(owner, name, &holder)) {
    case ActionFrameBy::Fix:
      return false;
    case ActionFrameBy::Own:
      action_play_ensure(owner, name).frame = frame;
      return true;
    case ActionFrameBy::Knob: {
      /* Along its side, the other axis left where it is (the knob keeps inside its box). */
      Bone &knob = const_cast<Bone &>(*holder);
      int side = 0;
      controller_of_action(owner, name, &side);
      float2 at = controller_knob_seen(knob);
      (controller_side_axis(side) == 0 ? at.x : at.y) = controller_side_reach(knob, side, frame) * controller_side_sign(side);
      controller_knob_put(knob, at);
      return true;
    }
    case ActionFrameBy::Bone: {
      /* The turn its keys have on that frame. */
      Bone &bone = const_cast<Bone &>(*holder);
      const auto it = bone.angle_keys.actions.find(name);
      if (it == bone.angle_keys.actions.end() || it->second.empty()) {
        return false;
      }
      const float t = action_own_frame(frame, float(it->second.back().frame), action_loops(owner, name));
      bone.angle = bone.setup_angle + action_bone_sample(it->second, 0.0f, t);
      return true;
    }
  }
  return false;
}

std::string action_frame_text(float frame)
{
  char text[32];
  if (std::fabs(frame - std::round(frame)) < 0.05f) {
    std::snprintf(text, sizeof(text), "%d", int(std::lround(frame)));
  }
  else {
    std::snprintf(text, sizeof(text), "%.1f", frame);
  }
  return text;
}

bool action_adds(const Layer &owner, const std::string &name)
{
  return action_bone_of(owner, name);
}

/* Each channel's setup, as apply_action_bone_actions takes it: its key on frame 0, or (unkeyed) its value less
 * what action bone actions add now. */
template<typename C, typename V> static auto channel_setup(const C &ch, const V &value)
{
  return ch.animated() ? ch.evaluate(0) : (ch.has_last ? ch.last : value) - ch.from_action_bones;
}

/* Whether action `action`'s keys on `bone` move it (keys hold the change from the setup, its channel's own on frame 0):
 * a head turn's actions key every bone they hold still. */
static bool action_moves_bone(const Bone &bone, const std::string &action)
{
  const auto moves = [&](const auto &ch, const auto value, auto distance) {
    const auto it = ch.actions.find(action);
    if (it == ch.actions.end()) {
      return false;
    }
    const auto setup = channel_setup(ch, value);
    return std::any_of(it->second.begin(), it->second.end(),
                       [&](const auto &k) { return k.frame > 0 && distance(k.value, setup) > 1e-5f; });
  };
  const auto apart2 = [](const float2 a, const float2 b) { return length(a - b); };
  const auto apart1 = [](const float a, const float b) { return std::abs(a - b); };
  return moves(bone.position_keys, bone.transform, apart2) || moves(bone.angle_keys, bone.turn, apart1) ||
         moves(bone.scale_keys, bone.scale, apart2);
}

void bone_fixes_tidy(Document &doc)
{
  /* A fix that follows a bone deleted follows the rest. */
  for (const Layer *flat : document_layers_flat(doc)) {
    if (flat->is_bone_layer() && !flat->bone_fixes.empty()) {
      Layer &owner = *layer_find(doc, flat->id);
      for (BoneFix &fix : owner.bone_fixes) {
        std::erase_if(fix.follows, [&](uint64_t id) { return bone_find(owner, id) == nullptr; });
      }
    }
  }
  /* Fixes named after their bones' actions take their names as they are now: an action or bone deleted (or any edit
   * that changes what the name says) renames them at once, as opening the file would, so saving and opening changes
   * nothing. */
  bone_fix_names_follow(doc);
}

int controller_spots_tidy(Document &doc)
{
  /* The box as the keys have it now. */
  controllers_update(doc);
  int removed = 0;
  for (const Layer *flat : document_layers_flat(doc)) {
    if (!flat->is_bone_layer()) {
      continue;
    }
    Layer &owner = *layer_find(doc, flat->id);
    for (Bone &knob : owner.bones) {
      if (!bone_is_controller(knob) || knob.controller_spots.empty()) {
        continue;
      }
      float2 lo, hi;
      controller_box(knob, lo, hi);
      /* A little slack: spots are stored as placed, a hair off an edge. */
      constexpr float SLACK = 1e-3f;
      removed += int(std::erase_if(knob.controller_spots, [&](const ControllerSpot &spot) {
        return !(spot.at.x >= lo.x - SLACK && spot.at.x <= hi.x + SLACK && spot.at.y >= lo.y - SLACK &&
                 spot.at.y <= hi.y + SLACK);
      }));
    }
  }
  return removed;
}

bool document_action_rename(Document &doc, uint64_t owner_id, const std::string &from, const std::string &to)
{
  Layer *owner = layer_find(doc, owner_id);
  if (!owner || from.empty() || to.empty() || from == to ||
      std::find(owner->actions.begin(), owner->actions.end(), from) == owner->actions.end() ||
      std::find(owner->actions.begin(), owner->actions.end(), to) != owner->actions.end())
  {
    return false;
  }
  std::replace(owner->actions.begin(), owner->actions.end(), from, to);
  for (Bone &bone : owner->bones) {
    std::replace(bone.controller_actions.begin(), bone.controller_actions.end(), from, to);
  }
  for (ActionPlay &a : owner->action_plays) {
    a.name = a.name == from ? to : a.name;
  }
  for (BoneFix &f : owner->bone_fixes) {
    f.name = f.name == from ? to : f.name;
  }
  owner_for_each_channel(*owner, [&](auto &ch, auto & /*value*/) {
    if (auto it = ch.actions.find(from); it != ch.actions.end()) {
      auto keys = std::move(it->second);
      ch.actions.erase(it);
      ch.actions[to] = std::move(keys);
    }
    if (auto it = ch.action_setup.find(from); it != ch.action_setup.end()) {
      auto key = std::move(it->second);
      ch.action_setup.erase(it);
      ch.action_setup[to] = std::move(key);
    }
  });
  if (doc.action == from && doc.action_layer == owner_id) {
    doc.action = to;
  }
  return true;
}

void armature_bone_renamed(Document &doc, uint64_t owner_id, const std::string &from, const std::string &to)
{
  if (from == to) {
    return;
  }
  for (const char *other : {"", " 2"}) {
    document_action_rename(doc, owner_id, from + other, to + other);
  }
  /* A knob's sides named after it ("Jaw Right") take its new name. */
  Layer *owner = layer_find(doc, owner_id);
  const Bone *knob = owner ? bone_find_by_name(*owner, to) : nullptr;
  if (!knob || !bone_is_controller(*knob)) {
    return;
  }
  const std::array<std::string, CONTROLLER_SIDES> sides = knob->controller_actions;
  for (const std::string &action : sides) {
    if (action.size() > from.size() && action.compare(0, from.size() + 1, from + " ") == 0) {
      document_action_rename(doc, owner_id, action, controller_action_name_free(*owner, to + action.substr(from.size())));
    }
  }
}

/* --- Fix actions that follow bones (BoneFix) ------------------------------------------------------------------ */

const BoneFix *bone_fix_find(const Layer &owner, const std::string &name)
{
  for (const BoneFix &f : owner.bone_fixes) {
    if (f.name == name) {
      return &f;
    }
  }
  return nullptr;
}

int bone_fix_ways(const Bone &bone)
{
  return bone_is_controller(bone) ? 2 : 1;
}

/* What traces a followed bone's line: a knob's place (frames), any other bone's turn. */
static bool bone_fix_traces(const Bone &bone, const void *ch)
{
  return bone_is_controller(bone) ? ch == &bone.position_keys : ch == &bone.angle_keys;
}

/* A channel's keys in action `name`: in the channel itself while that is the timeline edited. */
template<typename C> static const auto *bone_fix_keys(const C &ch, const std::string &name, bool edited)
{
  if (edited) {
    return &ch.keys;
  }
  const auto it = ch.actions.find(name);
  return it == ch.actions.end() ? nullptr : &it->second;
}

/* Samples keys (frame 0 the setup) at fractional frames, the channel made once. */
template<typename T> struct BoneFixSampler {
  Channel<T> c;
  BoneFixSampler(const std::vector<Key<T>> *keys, const T &setup)
  {
    const ChannelKeysQuiet scratch;
    if (keys) {
      c.keys = *keys;
    }
    c.set_key(0, setup);
  }
  T at(float t) const
  {
    const int f0 = int(std::floor(t));
    const float frac = t - float(f0);
    const T a = c.evaluate(f0);
    return frac <= 0.0f ? a : a + (c.evaluate(f0 + 1) - a) * frac;
  }
};

static constexpr float BONE_FIX_STEP = 0.25f;
/* How far off its line a fix whose bones go more than one way along it reaches: it fades to nothing half its length
 * away (each way measured against how far it goes along the line). */
static constexpr float BONE_FIX_REACH = 0.5f;
/* What share of how far out a way is it can change along the line and still count as staying put. */
static constexpr float BONE_FIX_STILL = 0.05f;

/* A share (0 to 1) of a fix as `fade` shapes it. */
static float bone_fix_faded(float share, BoneFixFade fade)
{
  share = std::clamp(share, 0.0f, 1.0f);
  return fade == BoneFixFade::Smooth ? share * share * (3.0f - 2.0f * share) : share;
}

/* `now(i, axis)`: where bone `i` of `owner` is (its turn from its setup; a knob's frames on that axis). */
template<typename NowFn>
static BoneFixPlay bone_fix_play_with(const Layer &owner, const BoneFix &fix, bool edited, NowFn now)
{
  BoneFixPlay play;
  /* One way the bones go: on each sample of the line, where it is now, and what counts as no change. */
  struct Way {
    std::vector<float> line;
    float now = 0.0f, eps = 1e-3f;
  };
  std::vector<Way> ways;
  float end = 1.0f;
  std::vector<size_t> found;
  for (const uint64_t id : fix.follows) {
    for (size_t i = 0; i < owner.bones.size(); i++) {
      const Bone &b = owner.bones[i];
      if (b.id != id) {
        continue;
      }
      if (bone_is_controller(b)) {
        if (const auto *keys = bone_fix_keys(b.position_keys, fix.name, edited); keys && !keys->empty()) {
          end = std::max(end, float(keys->back().frame));
        }
      }
      else if (const auto *keys = bone_fix_keys(b.angle_keys, fix.name, edited); keys && !keys->empty()) {
        end = std::max(end, float(keys->back().frame));
      }
      found.push_back(i);
    }
  }
  play.end = end;
  if (end <= play.start || found.empty()) {
    return play;
  }
  const int samples = int(std::ceil((end - play.start) / BONE_FIX_STEP)) + 1;
  const auto t_of = [&](int s) { return std::min(play.start + float(s) * BONE_FIX_STEP, end); };
  for (const size_t i : found) {
    const Bone &b = owner.bones[i];
    if (bone_is_controller(b)) {
      const BoneFixSampler<float2> line(bone_fix_keys(b.position_keys, fix.name, edited),
                                        channel_setup(b.position_keys, b.transform));
      Way x, y;
      x.eps = y.eps = 1e-2f;
      x.now = now(i, 0);
      y.now = now(i, 1);
      for (int s = 0; s < samples; s++) {
        const float2 at = controller_frames_of(b, line.at(t_of(s)));
        x.line.push_back(at.x);
        y.line.push_back(at.y);
      }
      ways.push_back(std::move(x));
      ways.push_back(std::move(y));
    }
    else {
      const float setup = channel_setup(b.angle_keys, b.turn);
      const BoneFixSampler<float> line(bone_fix_keys(b.angle_keys, fix.name, edited), setup);
      Way w;
      w.now = now(i, 0);
      for (int s = 0; s < samples; s++) {
        w.line.push_back(line.at(t_of(s)) - setup);
      }
      ways.push_back(std::move(w));
    }
  }
  /* What stays put on the line, away from rest, says how much plays; what changes, where on it. */
  play.strength = 1.0f;
  std::vector<std::pair<const Way *, float>> moving;
  for (const Way &w : ways) {
    const auto [lo, hi] = std::minmax_element(w.line.begin(), w.line.end());
    /* A way barely changing next to how far it is out (Up held at 20, drifting to 20.3) stays put: measured as a move,
     * against its own small span, the least step off it would take the fix away. */
    const float out = std::max(std::abs(*lo), std::abs(*hi));
    if (*hi - *lo > std::max(w.eps, BONE_FIX_STILL * out)) {
      moving.push_back({&w, *hi - *lo});
    }
    else if (std::abs(w.line.front()) > w.eps) {
      play.strength *= bone_fix_faded(w.now / w.line.front(), fix.fade);
    }
  }
  if (moving.empty()) {
    play.frame = end;
    return play;
  }
  /* The nearest point of the line, each way measured against how far it goes along it. */
  float best = std::numeric_limits<float>::max();
  for (int s = 0; s + 1 < samples || s == 0; s++) {
    const int n = std::min(s + 1, samples - 1);
    float along = 0.0f, length = 0.0f;
    for (const auto &[w, span] : moving) {
      const float a = w->line[size_t(s)], d = w->line[size_t(n)] - a;
      along += (w->now - a) * d / (span * span);
      length += d * d / (span * span);
    }
    const float u = length > 1e-12f ? std::clamp(along / length, 0.0f, 1.0f) : 0.0f;
    float off = 0.0f;
    for (const auto &[w, span] : moving) {
      const float a = w->line[size_t(s)], d = w->line[size_t(n)] - a;
      const float gap = (w->now - (a + d * u)) / span;
      off += gap * gap;
    }
    if (off < best - 1e-9f) {
      best = off;
      play.frame = t_of(s) + (t_of(n) - t_of(s)) * u;
    }
  }
  /* Going more than one way along it, the bones can leave the line: it fades as they go (a diagonal across a knob's box
   * would otherwise play all of it anywhere in the box). */
  if (moving.size() >= 2) {
    play.strength *= bone_fix_faded(1.0f - std::sqrt(best) / BONE_FIX_REACH, fix.fade);
  }
  return play;
}

BoneFixPlay bone_fix_play(const Layer &owner, const BoneFix &fix, bool edited)
{
  return bone_fix_play_with(owner, fix, edited, [&](size_t i, int axis) {
    const Bone &b = owner.bones[i];
    if (bone_is_controller(b)) {
      const float2 at = controller_knob_played(owner, b);
      return axis == 0 ? at.x : at.y;
    }
    return b.turn - channel_setup(b.angle_keys, b.turn);
  });
}

/* Whether channel `ch` of `owner` moves one of the bones `fix` follows (its place, turn or size: the one tracing its
 * line and the rest), which the fix never moves; keys of theirs in it play only where it is edited. */
static bool bone_fix_tracing(const Layer &owner, const BoneFix &fix, const void *ch)
{
  for (const Bone &b : owner.bones) {
    if (std::find(fix.follows.begin(), fix.follows.end(), b.id) != fix.follows.end() &&
        (ch == &b.position_keys || ch == &b.angle_keys || ch == &b.scale_keys))
    {
      return true;
    }
  }
  return false;
}

bool bone_fix_line_of(const Layer &owner, const std::string &name, const Bone &bone, const void *ch)
{
  const BoneFix *fix = bone_fix_find(owner, name);
  return fix && std::find(fix->follows.begin(), fix->follows.end(), bone.id) != fix->follows.end() &&
         bone_fix_traces(bone, ch);
}

/* What a fix adds to a channel playing `play`: its key there less the setup, times how much plays (a yes/no channel
 * takes it whole once half there). The fix starts on frame 1: a channel first keyed later starts from its setup there,
 * not on frame 0. */
template<typename T>
static bool bone_fix_delta(const std::vector<Key<T>> &keys, const T &setup, const BoneFixPlay &play, bool constant,
                           T &r_delta)
{
  r_delta = setup - setup;
  if (keys.empty() || play.strength <= 0.0f || (constant && play.strength < 0.5f)) {
    return false;
  }
  const auto first = std::find_if(keys.begin(), keys.end(), [](const Key<T> &k) { return k.frame >= 1; });
  T d = setup - setup;
  if (first != keys.end() && first->frame > 1) {
    std::vector<Key<T>> held = keys;
    Key<T> start = *first;
    start.frame = 1;
    start.value = setup;
    held.insert(held.begin() + (first - keys.begin()), start);
    d = action_bone_sample(held, setup, play.frame, constant) - setup;
  }
  else {
    d = action_bone_sample(keys, setup, play.frame, constant) - setup;
  }
  r_delta = constant ? d : d * play.strength;
  return true;
}

std::string bone_fix_name(const Layer &owner, const BoneFix &fix, bool edited, int frame)
{
  std::vector<std::string> names;
  std::vector<std::string> bones;
  for (const uint64_t id : fix.follows) {
    const Bone *b = nullptr;
    for (const Bone &o : owner.bones) {
      b = o.id == id ? &o : b;
    }
    if (!b) {
      continue;
    }
    bones.push_back(b->name);
    if (bone_is_controller(*b)) {
      const auto *keys = bone_fix_keys(b->position_keys, fix.name, edited);
      if (!keys || keys->empty()) {
        continue;
      }
      const BoneFixSampler<float2> line(keys, channel_setup(b->position_keys, b->transform));
      const float2 at = controller_frames_of(*b, line.at(float(frame >= 0 ? frame : keys->back().frame)));
      /* Up or Down first, as said aloud ("up and right"). */
      for (const auto &[v, plus, minus] : {std::tuple(at.y, CONTROLLER_UP, CONTROLLER_DOWN),
                                           std::tuple(at.x, CONTROLLER_RIGHT, CONTROLLER_LEFT)})
      {
        const int side = v > 1e-2f ? plus : v < -1e-2f ? minus : -1;
        if (side >= 0 && size_t(side) < b->controller_actions.size() && !b->controller_actions[size_t(side)].empty()) {
          names.push_back(b->controller_actions[size_t(side)]);
        }
      }
    }
    else {
      const auto *keys = bone_fix_keys(b->angle_keys, fix.name, edited);
      if (!keys || keys->empty()) {
        continue;
      }
      const float setup = channel_setup(b->angle_keys, b->turn);
      const BoneFixSampler<float> line(keys, setup);
      const float turn = line.at(float(frame >= 0 ? frame : keys->back().frame)) - setup;
      if (std::abs(turn) > 1e-3f) {
        /* The action turning it that way. */
        for (const std::string &a : owner.actions) {
          if (controller_dial_of_action(owner, a) != b) {
            continue;
          }
          const auto *ak = b->angle_keys.actions.count(a) ? &b->angle_keys.actions.at(a) : nullptr;
          if (ak && !ak->empty() && (ak->back().value - ak->front().value) * turn > 0.0f) {
            names.push_back(a);
            break;
          }
        }
      }
    }
  }
  if (names.empty()) {
    std::string out;
    for (const std::string &n : bones) {
      out += (out.empty() ? "" : " and ") + n;
    }
    return (out.empty() ? std::string("Bone") : out) + " Fix";
  }
  /* "Bone Up and Right": a later name sharing the first's first word drops it. */
  const std::string first_word = names[0].substr(0, names[0].find(' '));
  std::string out = names[0];
  for (size_t k = 1; k < names.size(); k++) {
    std::string n = names[k];
    if (n.size() > first_word.size() + 1 && n.compare(0, first_word.size() + 1, first_word + " ") == 0) {
      n = n.substr(first_word.size() + 1);
    }
    out += " and " + n;
  }
  return out;
}

/* Where followed bone `b` is on `frame` of `fix`: a knob's frames, or {turn from setup, 0}. */
static float2 bone_fix_at(const Bone &b, const BoneFix &fix, bool edited, float frame)
{
  if (bone_is_controller(b)) {
    return controller_frames_of(b, BoneFixSampler<float2>(bone_fix_keys(b.position_keys, fix.name, edited),
                                                          channel_setup(b.position_keys, b.transform))
                                       .at(frame));
  }
  const float setup = channel_setup(b.angle_keys, b.turn);
  return {BoneFixSampler<float>(bone_fix_keys(b.angle_keys, fix.name, edited), setup).at(frame) - setup, 0.0f};
}

std::vector<BoneFixKnobLine> bone_fix_knob_lines(const Document &doc, const Layer &owner, const Bone &knob)
{
  std::vector<BoneFixKnobLine> out;
  if (!bone_is_controller(knob)) {
    return out;
  }
  for (const BoneFix &fix : owner.bone_fixes) {
    if (std::find(fix.follows.begin(), fix.follows.end(), knob.id) == fix.follows.end()) {
      continue;
    }
    BoneFixKnobLine line;
    line.name = fix.name;
    line.edited = owner.id == doc.action_layer && doc.action == fix.name;
    const BoneFixPlay play = bone_fix_play(owner, fix, line.edited);
    for (float t = play.start;; t = std::min(t + BONE_FIX_STEP, play.end)) {
      line.points.push_back(bone_fix_at(knob, fix, line.edited, t));
      if (t >= play.end) {
        break;
      }
    }
    line.now = bone_fix_at(knob, fix, line.edited, play.frame);
    line.strength = action_muted(owner, fix.name) ? 0.0f : play.strength;
    out.push_back(std::move(line));
  }
  return out;
}

std::string bone_fix_pose_label(const Layer &owner, const BoneFix &fix, bool edited, float frame)
{
  std::string out;
  const auto add = [&](const std::string &part) { out += (out.empty() ? "" : " \xC2\xB7 ") + part; };
  for (const uint64_t id : fix.follows) {
    const Bone *b = nullptr;
    for (const Bone &o : owner.bones) {
      b = o.id == id ? &o : b;
    }
    if (!b) {
      continue;
    }
    const std::string who = fix.follows.size() > 1 ? b->name + " " : std::string();
    const float2 at = bone_fix_at(*b, fix, edited, frame);
    if (bone_is_controller(*b)) {
      add(who + (at.y < -1e-2f ? "Down " : "Up ") + std::to_string(int(std::lround(std::abs(at.y)))));
      add(std::string(at.x < -1e-2f ? "Left " : "Right ") + std::to_string(int(std::lround(std::abs(at.x)))));
    }
    else {
      add(who + std::to_string(int(std::lround(at.x * 180.0f / PI))) + "\xC2\xB0");
    }
  }
  return out;
}

std::string bone_fix_bone_ways(const Layer &owner, const BoneFix &fix, uint64_t bone, bool edited)
{
  const Bone *b = nullptr;
  for (const Bone &o : owner.bones) {
    b = o.id == bone ? &o : b;
  }
  if (!b) {
    return {};
  }
  const BoneFixPlay play = bone_fix_play(owner, fix, edited);
  const float2 at = bone_fix_at(*b, fix, edited, play.end);
  std::string out;
  const auto add = [&](const char *part) { out += (out.empty() ? "" : " \xC2\xB7 ") + std::string(part); };
  if (bone_is_controller(*b)) {
    if (std::abs(at.y) > 1e-2f) {
      add(at.y > 0.0f ? "Up" : "Down");
    }
    if (std::abs(at.x) > 1e-2f) {
      add(at.x > 0.0f ? "Right" : "Left");
    }
  }
  else if (std::abs(at.x) > 1e-3f) {
    add(at.x > 0.0f ? "Counterclockwise" : "Clockwise");
  }
  return out;
}

/* `base`, or with " 2", " 3", ... where taken by another action of `owner` (not `self`). */
static std::string bone_fix_unique(const Layer &owner, const std::string &base, const std::string &self)
{
  /* Nor a bone's name, or its name and " 2": those name the bone's own actions (its turns). */
  const auto turn_name = [&](const std::string &n) {
    return bone_find_by_name(owner, n) ||
           (n.size() > 2 && n.compare(n.size() - 2, 2, " 2") == 0 && bone_find_by_name(owner, n.substr(0, n.size() - 2)));
  };
  const auto taken = [&](const std::string &n) {
    return turn_name(n) || (n != self && std::find(owner.actions.begin(), owner.actions.end(), n) != owner.actions.end());
  };
  std::string name = base;
  for (int i = 2; taken(name); i++) {
    name = base + " " + std::to_string(i);
  }
  return name;
}

std::string document_bone_fix_new(Document &doc, uint64_t owner_id, const std::vector<uint64_t> &follows)
{
  Layer *owner = layer_find(doc, owner_id);
  if (!owner || !owner->is_bone_layer()) {
    return {};
  }
  BoneFix fix;
  for (const uint64_t id : follows) {
    if (bone_find(*owner, id) && std::find(fix.follows.begin(), fix.follows.end(), id) == fix.follows.end()) {
      fix.follows.push_back(id);
    }
  }
  if (fix.follows.empty()) {
    return {};
  }
  /* Made from the mainline: back there first, so the bones are where it shows them. */
  document_set_action(doc, 0, "");
  animation_record(doc);
  owner = layer_find(doc, owner_id);
  fix.name = " new fix";
  /* Its line starts where the bones are now: keyed on frame 1, their setup on 0. */
  for (const uint64_t id : fix.follows) {
    Bone &b = *bone_find(*owner, id);
    const auto start = [&](auto &ch, const auto &value) {
      const ChannelKeysQuiet scratch;
      std::decay_t<decltype(ch)> c;
      c.set_key(0, channel_setup(ch, value));
      c.set_key(1, value - ch.from_action_bones);
      ch.actions[fix.name] = c.keys;
    };
    if (bone_is_controller(b)) {
      /* A knob where its actions play: an independent one rides its Knob Parent, as the fix will measure it. */
      const ChannelKeysQuiet scratch;
      Channel<float2> c;
      c.set_key(0, channel_setup(b.position_keys, b.transform));
      c.set_key(1, controller_transform_of(b, controller_knob_played(*owner, b)));
      b.position_keys.actions[fix.name] = c.keys;
    }
    else {
      start(b.angle_keys, b.turn);
    }
  }
  const std::string name = bone_fix_unique(*owner, bone_fix_name(*owner, fix, false, 1));
  owner_for_each_channel(*owner, [&](auto &ch, auto & /*value*/) {
    if (auto it = ch.actions.find(fix.name); it != ch.actions.end()) {
      auto keys = std::move(it->second);
      ch.actions.erase(it);
      ch.actions[name] = std::move(keys);
    }
  });
  fix.name = name;
  owner->actions.push_back(name);
  owner->bone_fixes.push_back(fix);
  document_set_action(doc, owner_id, name);
  doc.frame_current = 1;
  animation_evaluate(doc, doc.frame_current);
  return name;
}

std::string document_bone_fix_mirror(Document &doc, uint64_t owner_id, const std::string &name, bool *r_replaced)
{
  if (r_replaced) {
    *r_replaced = false;
  }
  Layer *owner = layer_find(doc, owner_id);
  const BoneFix *found = owner ? bone_fix_find(*owner, name) : nullptr;
  if (!found) {
    return {};
  }
  const BoneFix fix = *found;
  BoneFix mirrored = fix;
  bool sided = false;
  for (uint64_t &id : mirrored.follows) {
    const uint64_t other = bone_mirror_id(*owner, id);
    sided = sided || other != id;
    id = other;
  }
  if (!sided) {
    return {};
  }
  const auto as_set = [](std::vector<uint64_t> ids) {
    std::sort(ids.begin(), ids.end());
    return ids;
  };
  std::string was;
  for (const BoneFix &f : owner->bone_fixes) {
    if (f.name != fix.name && as_set(f.follows) == as_set(mirrored.follows)) {
      was = f.name;
    }
  }
  if (!was.empty()) {
    document_action_delete(doc, owner_id, was);
    if (r_replaced) {
      *r_replaced = true;
    }
  }
  const std::string made = bone_fix_unique(*layer_find(doc, owner_id), " mirrored fix");
  document_action_mirror(doc, owner_id, fix.name, made);
  owner = layer_find(doc, owner_id);
  mirrored.name = made;
  owner->bone_fixes.push_back(mirrored);
  std::string named = bone_fix_name(*owner, owner->bone_fixes.back());
  if (!fix.auto_name) {
    const Bone *first = bone_find(*owner, fix.follows.front());
    named = action_mirror_name(fix.name, first ? first->name : std::string());
    named = named == fix.name ? fix.name + " Mirrored" : named;
  }
  named = bone_fix_unique(*owner, named, made);
  document_action_rename(doc, owner_id, made, named);
  animation_evaluate(doc, doc.frame_current);
  return named;
}

bool document_bone_fix_follow(Document &doc, uint64_t owner_id, const std::string &name, uint64_t bone, bool follow)
{
  Layer *owner = layer_find(doc, owner_id);
  BoneFix *fix = owner ? const_cast<BoneFix *>(bone_fix_find(*owner, name)) : nullptr;
  Bone *b = owner ? bone_find(*owner, bone) : nullptr;
  if (!fix || !b) {
    return false;
  }
  const auto at = std::find(fix->follows.begin(), fix->follows.end(), bone);
  if (follow == (at != fix->follows.end())) {
    return false;
  }
  if (follow) {
    fix->follows.push_back(bone);
    return true;
  }
  fix->follows.erase(at);
  /* Its line's keys would play as the fix. */
  const bool edited = doc.action == name && doc.action_layer == owner_id;
  const auto drop = [&](auto &ch) {
    if (edited) {
      ch.keys.clear();
    }
    else {
      ch.actions.erase(name);
    }
  };
  if (bone_is_controller(*b)) {
    drop(b->position_keys);
  }
  else {
    drop(b->angle_keys);
  }
  animation_evaluate(doc, doc.frame_current);
  return true;
}

void action_bone_actions_add_at(const Layer &owner, int frame, std::vector<Bone> &bones)
{
  if (frame == 0 || owner.actions.empty() || bones.size() != owner.bones.size()) {
    return;
  }
  /* Every driving bone's angle on that frame picks its action's frame first, as on the frame shown. */
  ActionOwnLengths lengths;
  const auto playing_now = [&] {
    std::vector<float> turns;
    std::vector<float2> knobs;
    for (size_t i = 0; i < bones.size(); i++) {
      turns.push_back(bones[i].angle - owner.bones[i].setup_angle);
      knobs.push_back(bone_transform_from_position(owner.bones[i], bones[i].position));
    }
    std::vector<std::pair<std::string, float>> now = action_bone_frames_for(owner, turns, knobs);
    action_own_frames(owner, frame, lengths, now);
    return now;
  };
  const auto setup_of = [](const auto &ch, const auto &value) { return channel_setup(ch, value); };
  /* The action bones' own angles: they pick the frames, so nothing else moves them. */
  std::set<const void *> driving, action_bones;
  for (const std::string &name : owner.actions) {
    if (const Bone *b = action_bone_of(owner, name)) {
      driving.insert(&b->angle_keys);
      action_bones.insert({&b->position_keys, &b->angle_keys, &b->scale_keys});
    }
  }
  /* A fix never moves an action bone (its keys of one show only while it is edited), nor a bone it follows. */
  const auto fix_leaves = [&](const BoneFix &fix, const void *ch) {
    return action_bones.count(ch) > 0 || bone_fix_tracing(owner, fix, ch);
  };
  /* A fix that follows bones, from where they are on that frame by then. */
  const auto play_fix = [&](const BoneFix &fix) {
    const BoneFixPlay at = bone_fix_play_with(owner, fix, false, [&](size_t i, int axis) {
      if (bone_is_controller(owner.bones[i])) {
        const float2 k = controller_frames_of(owner.bones[i], bone_transform_from_position(owner.bones[i], bones[i].position));
        return axis == 0 ? k.x : k.y;
      }
      return bones[i].angle - owner.bones[i].setup_angle;
    });
    if (at.strength <= 0.0f) {
      return;
    }
    for (size_t j = 0; j < bones.size(); j++) {
      const Bone &src = owner.bones[j];
      Bone &b = bones[j];
      if (const auto it = src.position_keys.actions.find(fix.name);
          it != src.position_keys.actions.end() && !fix_leaves(fix, &src.position_keys))
      {
        float2 d;
        if (bone_fix_delta(it->second, setup_of(src.position_keys, src.transform), at, false, d)) {
          b.position += rotate(d, src.setup_angle);
        }
      }
      if (!fix_leaves(fix, &src.angle_keys)) {
        if (const auto it = src.angle_keys.actions.find(fix.name); it != src.angle_keys.actions.end()) {
          float d;
          if (bone_fix_delta(it->second, setup_of(src.angle_keys, src.turn), at, false, d)) {
            b.angle += d;
          }
        }
      }
      if (const auto it = src.scale_keys.actions.find(fix.name);
          it != src.scale_keys.actions.end() && !fix_leaves(fix, &src.scale_keys))
      {
        float2 d;
        if (bone_fix_delta(it->second, setup_of(src.scale_keys, src.scale), at, false, d)) {
          b.scale += d;
        }
      }
    }
  };
  const auto playing_and_fixes = [&] {
    std::vector<std::pair<std::string, float>> now = playing_now();
    for (const BoneFix &fix : owner.bone_fixes) {
      if (!action_muted(owner, fix.name)) {
        now.push_back({fix.name, 0.0f});
      }
    }
    return now;
  };
  action_bone_actions_in_order(owner, playing_and_fixes, [&](const std::string &name, float t) {
    if (const BoneFix *fix = bone_fix_find(owner, name)) {
      play_fix(*fix);
      return;
    }
    const Bone *by = action_bone_of(owner, name);
    const Channel<float> *driver = by ? &by->angle_keys : nullptr;
    for (size_t j = 0; j < bones.size(); j++) {
      const Bone &src = owner.bones[j];
      Bone &b = bones[j];
      if (const auto it = src.position_keys.actions.find(name); it != src.position_keys.actions.end()) {
        const float2 setup = setup_of(src.position_keys, src.transform);
        b.position += rotate(action_bone_sample(it->second, setup, t) - setup, src.setup_angle);
      }
      if (&src.angle_keys != driver) {
        if (const auto it = src.angle_keys.actions.find(name); it != src.angle_keys.actions.end()) {
          const float setup = setup_of(src.angle_keys, src.turn);
          b.angle += action_bone_sample(it->second, setup, t) - setup;
        }
      }
      if (const auto it = src.scale_keys.actions.find(name); it != src.scale_keys.actions.end()) {
        const float2 setup = setup_of(src.scale_keys, src.scale);
        b.scale += action_bone_sample(it->second, setup, t) - setup;
      }
    }
  });
}

static bool has_action_bone_actions(const Document &doc)
{
  for (const Layer *layer : document_layers_flat(doc)) {
    if (layer->is_bone_layer() && (!layer->action_plays.empty() || !layer->bone_fixes.empty()) &&
        !layer->actions.empty())
    {
      return true;
    }
    for (const std::string &name : layer->actions) {
      if (layer->is_bone_layer() && action_bone_of(*layer, name)) {
        return true;
      }
    }
  }
  return false;
}

void animation_refresh_action_bones(Document &doc)
{
  OANIM_PROFILE("animation_refresh_action_bones");
  if (!doc.action_bones_applied && !has_action_bone_actions(doc)) {
    return;
  }
  /* Take off what was added (from the value and its recorded value alike), then work it out again
   * from the bones as they are now. Always, whatever `action_bones_applied` says: a drag puts the bones
   * back as they were when it began every update, their action bone offsets with them (an action bone
   * turned past its action's end and then back the other way kept the end pose). Only the few layers
   * with action bone action data are looked at: found now, or kept by a bone drag. */
  std::unordered_set<const Layer *> involved;
  if (g_drag_doc == &doc) {
    g_action_bone_layers = &g_drag_layers;
  }
  else {
    find_action_bone_layers(doc, involved);
    g_action_bone_layers = &involved;
  }
  layers_for_each_channel_if(doc.layers, action_bones_added, [&](auto &ch, auto &value) {
    value -= ch.from_action_bones;
    ch.last -= ch.from_action_bones;
    ch.from_action_bones = {};
    ch.action_bone_live = false;
    ch.action_played = {};
    ch.action_slope = {};
  });
  doc.action_bones_applied = false;
  apply_action_bone_actions(doc, doc.frame_current);
  g_action_bone_layers = nullptr;
}

void animation_drag_refresh(Document &doc)
{
  animation_refresh_action_bones(doc);
  bone_outer_parents_update(doc);
  follow_points_update(doc);
  shape_limits_update(doc);
  /* As a frame shown settles them: else a drag drew what the pose read an update before (a head turn moving the eye a
   * pupil's knob looks in), right only once dropped. */
  action_bones_settle(doc);
}

void animation_action_bone_drag_begin(Document &doc)
{
  g_drag_layers.clear();
  find_action_bone_layers(doc, g_drag_layers);
  g_drag_doc = &doc;
}

std::unordered_set<uint64_t> animation_action_bone_drag_layers()
{
  std::unordered_set<uint64_t> ids;
  for (const Layer *l : g_drag_layers) {
    ids.insert(l->id);
  }
  return ids;
}

void animation_action_bone_drag_end()
{
  g_drag_doc = nullptr;
  g_drag_layers.clear();
}

static void apply_action_bone_actions_playing(Document &doc, int frame);

static void switches_clear_rig(std::vector<Layer> &layers)
{
  for (Layer &layer : layers) {
    layer.switch_rig_set = false;
    switches_clear_rig(layer.children);
  }
}

/* Action bone actions, then who wins on every switch (anim/switch.hh): a switch's pick is never added. */
static void apply_action_bone_actions(Document &doc, int frame)
{
  /* Keys can't change while a bone is dragged. */
  if (g_drag_doc != &doc) {
    controllers_update(doc);
  }
  switches_clear_rig(doc.layers);
  /* Each action plays into the layers with action bone action data only, found once for them all. */
  std::unordered_set<const Layer *> involved;
  const bool own = g_action_bone_layers == nullptr;
  if (own) {
    find_action_bone_layers(doc, involved);
    g_action_bone_layers = &involved;
  }
  apply_action_bone_actions_playing(doc, frame);
  if (own) {
    g_action_bone_layers = nullptr;
  }
  switches_resolve(doc, frame);
}

static void apply_action_bone_actions_playing(Document &doc, int frame)
{
  /* The setup frame (0) is the rig at rest: turning an action bone there sets its rest angle and plays
   * nothing, as in Moho (and bones don't bend the drawing there either). `frame`: the one evaluated
   * (switching timelines evaluates frame 0 while another is shown). */
  if (frame == 0) {
    return;
  }
  /* Editing an action bone action, the others play under it, for it to key their bones. */
  for (const Layer *flat : document_layers_flat(doc)) {
    if (!flat->is_bone_layer() || flat->actions.empty()) {
      continue;
    }
    Layer &owner = *layer_find(doc, flat->id);
    /* Every driving bone's angle picks its frame first, before any action moves bones (but those that
     * turn it: see action_bone_actions_in_order). */
    std::vector<std::pair<std::string, float>> frames;
    ActionOwnLengths lengths;
    const auto playing_now = [&] {
      std::vector<std::pair<std::string, float>> now;
      std::vector<std::pair<std::string, float>> all = action_bone_actions_playing(owner);
      action_own_frames(owner, -1, lengths, all);
      for (const auto &[name, t] : all) {
        if (!(name == doc.action && owner.id == doc.action_layer)) {
          now.push_back({name, t});
        }
      }
      return now;
    };
    /* The action bones' own angles: they pick the frames, so nothing else moves them (shown turned only
     * while a fix is edited, its drivers held). */
    std::set<const void *> driving, action_bones;
    for (const std::string &name : owner.actions) {
      if (const Bone *b = action_bone_of(owner, name)) {
        driving.insert(&b->angle_keys);
        action_bones.insert({&b->position_keys, &b->angle_keys, &b->scale_keys});
      }
    }
    /* Switches pick rather than add: an action has a say once its bone has turned past one of its
     * switch keys, and the first listed with a say wins. */
    std::map<const void *, Layer *> switches;
    const auto gather_switches = [&](auto &&self, std::vector<Layer> &layers) -> void {
      for (Layer &l : layers) {
        if (l.is_switch()) {
          switches[&l.switch_keys] = &l;
        }
        self(self, l.children);
      }
    };
    gather_switches(gather_switches, owner.children);
    /* Action `name` at frame `t` has its say on switch `sw` once it has passed one of its switch keys. */
    const auto switch_say = [&](Channel<float> &ch, Layer &sw, const std::string &name, float t) {
      const auto it = ch.actions.find(name);
      if (it == ch.actions.end() || sw.switch_rig_set) {
        return;
      }
      const Key<float> *passed = nullptr;
      for (const Key<float> &k : it->second) {
        if (float(k.frame) > t + 1e-4f) {
          break;
        }
        if (k.frame > 0) {
          passed = &k;
        }
      }
      if (passed && passed->value > SWITCH_RIG + 0.5f) {
        sw.switch_rig = passed->value;
        sw.switch_rig_set = true;
        ch.action_bone_live = true;
      }
    };
    const auto play = [&](const std::string &name, float t, const void *skip, bool skip_driving) {
      /* A side's action keys its own knob's timing (how far out each frame plays): never a move of the knob. */
      const Bone *by_knob = controller_of_action(owner, name, nullptr);
      const void *timing = by_knob ? static_cast<const void *>(&by_knob->position_keys) : nullptr;
      owner_for_each_channel_with(owner, name, [&](auto &ch, auto &value) {
        if (static_cast<const void *>(&ch) == skip || static_cast<const void *>(&ch) == timing ||
            (skip_driving && driving.count(static_cast<const void *>(&ch))))
        {
          return;
        }
        if (const auto sw = switches.find(static_cast<const void *>(&ch)); sw != switches.end()) {
          if constexpr (std::is_same_v<std::decay_t<decltype(ch)>, Channel<float>>) {
            switch_say(ch, *sw->second, name, t);
          }
          return;
        }
        const auto it = ch.actions.find(name);
        if (it == ch.actions.end()) {
          return;
        }
        /* Unkeyed, the setup is the value as last recorded, not as it is now: an edit not yet
         * recorded (a bone being dragged) stays on top instead of being taken into the offset. */
        const auto setup = ch.animated() ? ch.evaluate(0) : (ch.has_last ? ch.last : value) - ch.from_action_bones;
        const auto delta = action_bone_sample(it->second, setup, t, ch.constant) - setup;
        action_slope_add(ch, value, setup, delta,
                         [&](const auto &s) { return action_bone_sample(it->second, s, t, ch.constant) - s; });
        /* The value and what it was last recorded as both move, so an edit stays an edit. */
        value += delta;
        ch.last += delta;
        ch.from_action_bones += delta;
        ch.action_played.on = true;
        /* Pink only where the action moves it somewhere: an action keys every bone, most held still. */
        ch.action_bone_live = ch.action_bone_live ||
                              std::any_of(it->second.begin(), it->second.end(), [&](const auto &k) {
          const auto off = k.value - setup;
          if constexpr (std::is_same_v<std::decay_t<decltype(off)>, float>) {
            return std::abs(off) > 1e-6f;
          }
          else {
            return std::abs(off.x) > 1e-6f || std::abs(off.y) > 1e-6f;
          }
        });
        doc.action_bones_applied = true;
      });
    };
    /* The fixes that follow bones, each from where what plays before it has put its bones (a bone another bone's action
     * moves too), and before what they move picks its frames (an independent knob riding a head a fix turns). Not the
     * one edited (its keys are the timeline). */
    const auto play_fix = [&](const BoneFix &fix) {
      const BoneFixPlay at = bone_fix_play(owner, fix);
      if (at.strength <= 0.0f) {
        return;
      }
      owner_for_each_channel_with(owner, fix.name, [&](auto &ch, auto &value) {
        const void *key = static_cast<const void *>(&ch);
        /* A switch picks, it can't blend: the fix's pick where it plays, once more than half of it does. */
        if (const auto sw = switches.find(key); sw != switches.end()) {
          if constexpr (std::is_same_v<std::decay_t<decltype(ch)>, Channel<float>>) {
            if (at.strength >= 0.5f) {
              switch_say(ch, *sw->second, fix.name, at.frame);
            }
          }
          return;
        }
        /* Nor an action bone: its keys in a fix show only while the fix is edited. */
        if (action_bones.count(key) || bone_fix_tracing(owner, fix, key)) {
          return;
        }
        const auto it = ch.actions.find(fix.name);
        if (it == ch.actions.end()) {
          return;
        }
        const auto setup = channel_setup(ch, value);
        auto delta = setup - setup;
        if (!bone_fix_delta(it->second, setup, at, ch.constant, delta)) {
          return;
        }
        action_slope_add(ch, value, setup, delta, [&](const auto &s) {
          auto d = s - s;
          bone_fix_delta(it->second, s, at, ch.constant, d);
          return d;
        });
        value += delta;
        ch.last += delta;
        ch.from_action_bones += delta;
        ch.action_bone_live = ch.action_bone_live || !(delta == setup - setup);
        ch.action_played.on = true;
        doc.action_bones_applied = true;
      });
    };
    const auto playing_and_fixes = [&] {
      std::vector<std::pair<std::string, float>> now = playing_now();
      for (const BoneFix &fix : owner.bone_fixes) {
        if (!(fix.name == doc.action && owner.id == doc.action_layer) && !action_muted(owner, fix.name)) {
          now.push_back({fix.name, 0.0f});
        }
      }
      return now;
    };
    /* An action bone action never moves its own bone (the bone picks its frame). */
    frames = action_bone_actions_in_order(owner, playing_and_fixes, [&](const std::string &name, float t) {
      const Bone *by = action_bone_of(owner, name);
      if (const BoneFix *fix = bone_fix_find(owner, name)) {
        play_fix(*fix);
      }
      else {
        play(name, t, by ? static_cast<const void *>(&by->angle_keys) : nullptr, false);
      }
    });
    /* A bone's position On Path (Channel::on_path) is where its keys hold from its first to its last: what the
     * actions added is left out there (its value and what it was recorded as alike, so an edit stays an edit). Not
     * while the layer's action is edited: its keys are the action's then. */
    if (!(owner.id == doc.action_layer && !doc.action.empty())) {
      for (Bone &b : owner.bones) {
        Channel<float2> &ch = b.position_keys;
        if (channel_on_path_at(ch, frame) && !(ch.from_action_bones == float2{0.0f, 0.0f})) {
          /* Its position with it, where that was taken from its Transform: else that reads as an edit. */
          const bool derived = b.position == bone_position_from_transform(b, b.transform);
          b.transform -= ch.from_action_bones;
          if (derived) {
            b.position = bone_position_from_transform(b, b.transform);
          }
          ch.last -= ch.from_action_bones;
          ch.from_action_bones = float2{0.0f, 0.0f};
        }
      }
    }
  }
}

/* --- 2 Axis Controllers (anim/controller.hh) ------------------------------------------------------- */

/* A channel's keys go through `map` onto another, whatever else the key says kept, the key at frame 0 left to the
 * setup. Returns how many. */
template<typename From, typename To, typename Map>
static int controller_keys_copy(const std::vector<Key<From>> &keys, Channel<To> &to, Map &&map)
{
  int count = 0;
  for (const Key<From> &k : keys) {
    if (k.frame == 0) {
      continue;
    }
    if (!to.animated()) {
      to.set_key(0, To{});
    }
    to.set_key(k.frame, map(k.frame, k.value));
    if (Key<To> *made = to.key_at(k.frame)) {
      made->interp = k.interp;
      made->hold = k.hold;
      made->interval = k.interval;
      made->ease = k.ease;
      made->overshoot = k.overshoot;
      made->elastic_amplitude = k.elastic_amplitude;
      made->elastic_period = k.elastic_period;
      made->bezier = k.bezier;
    }
    count++;
  }
  return count;
}

void controllers_update(Document &doc)
{
  for (const Layer *flat : document_layers_flat(doc)) {
    if (!flat->is_bone_layer() ||
        std::none_of(flat->bones.begin(), flat->bones.end(), [](const Bone &b) { return bone_is_controller(b); }))
    {
      continue;
    }
    Layer &owner = *layer_find(doc, flat->id);
    std::map<std::string, std::vector<int>> found;
    for (const Bone &knob : owner.bones) {
      for (const std::string &action : knob.controller_actions) {
        if (!action.empty()) {
          found[action];
        }
      }
    }
    /* Being edited, an action's keys are the channels' own. */
    const bool edited = !doc.action.empty() && doc.action_layer == owner.id && found.count(doc.action);
    const auto gather = [&](auto &&self, Layer &layer) -> void {
      layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) {
        if (edited) {
          for (const auto &k : ch.keys) {
            found[doc.action].push_back(k.frame);
          }
        }
        for (auto &[action, frames] : found) {
          if (const auto it = ch.actions.find(action); it != ch.actions.end()) {
            for (const auto &k : it->second) {
              frames.push_back(k.frame);
            }
          }
        }
      });
      for (Layer &child : layer.children) {
        self(self, child);
      }
    };
    gather(gather, owner);
    for (Bone &knob : owner.bones) {
      if (!bone_is_controller(knob)) {
        continue;
      }
      for (int side = 0; side < CONTROLLER_SIDES; side++) {
        std::vector<int> &keys = knob.controller_keys[side];
        keys.clear();
        const std::string &action = knob.controller_actions[side];
        if (action.empty()) {
          continue;
        }
        keys = found[action];
        std::erase(keys, 0);
        std::sort(keys.begin(), keys.end());
        keys.erase(std::unique(keys.begin(), keys.end()), keys.end());
      }
      /* Its timing: its own keys in each side's action, how far out each frame plays (being edited, the action's keys
       * are the channel's own). A key at the rest point or going back is held where the one before was. */
      for (int side = 0; side < CONTROLLER_SIDES; side++) {
        std::vector<float2> &timing = knob.controller_timing[side];
        timing.clear();
        const std::string &action = knob.controller_actions[side];
        if (action.empty()) {
          continue;
        }
        const bool own = doc.action == action && doc.action_layer == owner.id;
        const auto it = knob.position_keys.actions.find(action);
        const std::vector<Key<float2>> *keys = own ? &knob.position_keys.keys :
                                               it != knob.position_keys.actions.end() ? &it->second : nullptr;
        float most = 0.0f;
        for (size_t k = 0; keys && k < keys->size(); k++) {
          const Key<float2> &key = (*keys)[k];
          const float2 frames = controller_frames_of(knob, key.value);
          const float along = (controller_side_axis(side) == 0 ? frames.x : frames.y) * controller_side_sign(side);
          if (key.frame <= 0) {
            continue;
          }
          most = std::max(most, along);
          timing.push_back({float(key.frame), most});
        }
        /* Keyed only at rest it has no length: as not keyed. */
        if (most <= 1e-6f) {
          timing.clear();
        }
      }
      /* The box comes from where the knob is keyed in its sides' actions: fitted to their lengths only while no side
       * is keyed, so picking another action never moves an edge the knob was keyed to. */
      const bool sides_keyed = std::any_of(knob.controller_timing.begin(), knob.controller_timing.end(),
                                           [](const std::vector<float2> &t) { return !t.empty(); });
      if (knob.controller_size_auto && !sides_keyed) {
        controller_frame_size_set(knob, controller_fitted_size(knob));
      }
      /* A side not keyed yet is as long as the opposite side is keyed (its own action's length when that isn't), its
       * frames even along it, until its knob is keyed. */
      const std::array<std::vector<float2>, CONTROLLER_SIDES> own_timing = knob.controller_timing;
      for (int side = 0; side < CONTROLLER_SIDES; side++) {
        const std::vector<float2> &across = own_timing[controller_side_opposite(side)];
        if (!knob.controller_actions[side].empty() && own_timing[side].empty() && !across.empty()) {
          knob.controller_timing[side] = {{controller_side_frames(knob, side), across.back().y}};
        }
      }
      /* Editing one of its actions, the knob sits at its frame (what hangs from it with it); in a side's own action
       * it moves along that side, keying its timing. */
      int edit_side = -1;
      for (int side = 0; side < CONTROLLER_SIDES && doc.action_layer == owner.id; side++) {
        if (!doc.action.empty() && knob.controller_actions[side] == doc.action) {
          edit_side = side;
        }
      }
      const bool editing = doc.action_layer == owner.id && edit_side >= 0;
      knob.controller_knob_edit_side = edit_side;
      knob.controller_knob_editing = editing;
      knob.controller_knob_edit_at = editing ? controller_knob_shown(doc, owner, knob) : float2();
      /* Auto keying in a side's own action, the frame a move keys on (see controller_knob_set). */
      knob.controller_knob_edit_frame = edit_side >= 0 && doc.auto_key ? doc.frame_current : 0;
      /* From a place seen in the box to its keys, and its constraints' pull (see controller_knob_put). */
      knob.controller_frames_to_keys = Transform2D();
      knob.controller_knob_pull_now = float2();
      if (doc.frame_current != 0 && (knob.controller_knob_independent || controller_constrained(knob))) {
        const std::vector<BonePose> poses = armature_pose(owner, false);
        if (const BonePose *p = bone_pose_find(poses, knob.id)) {
          knob.controller_knob_pull_now = p->knob_pull;
          if (knob.controller_knob_independent) {
            const float size = std::max(knob.controller_frame_size, 1e-6f);
            const auto keyed = [&](float2 to) {
              return rotate(p->knob_parent_skin.inverted().apply(controller_box_point(knob, *p, to)) - p->setup_head,
                            -knob.controller_box_angle) / size;
            };
            const float2 o = keyed({0, 0}), x = keyed({1, 0}), y = keyed({0, 1});
            knob.controller_frames_to_keys = {x.x - o.x, x.y - o.y, y.x - o.x, y.y - o.y, o.x, o.y};
          }
        }
      }
    }
  }
}

/* Frame 0 is the rig at rest: no knob away from its rest point, unkeyed or not. */
static void controllers_rest(Document &doc)
{
  for (const Layer *flat : document_layers_flat(doc)) {
    if (!flat->is_bone_layer()) {
      continue;
    }
    Layer &owner = *layer_find(doc, flat->id);
    for (Bone &knob : owner.bones) {
      if (!bone_is_controller(knob)) {
        continue;
      }
      if (!knob.position_keys.animated()) {
        knob.transform = {};
        knob.position = knob.setup_position;
        knob.position_keys.last = {};
      }
    }
  }
}

float2 controller_knob_shown(const Document &doc, const Layer &owner, const Bone &knob)
{
  /* In another action (an ordinary one, a fix) it is wherever that has it, as on the mainline. */
  const bool own_side = std::find(knob.controller_actions.begin(), knob.controller_actions.end(), doc.action) !=
                        knob.controller_actions.end();
  if (doc.action.empty() || doc.action_layer != owner.id || !own_side) {
    /* Staying in place, where it sits in the box as that has moved. */
    return doc.frame_current != 0 ? controller_knob_played(owner, knob) : controller_knob(knob);
  }
  float2 at;
  const auto put = [&](int side, float frames) {
    (controller_side_axis(side) == 0 ? at.x : at.y) = controller_side_reach(knob, side, frames) * controller_side_sign(side);
  };
  for (int side = 0; side < CONTROLLER_SIDES; side++) {
    /* At rest until its first key there: it moves only where keyed (with none, the mainline still plays frame N N
     * frames out), or evenly out to the opposite side's length when only that is keyed. */
    if (knob.controller_actions[side] == doc.action && !knob.controller_timing[side].empty()) {
      put(side, std::min(float(doc.frame_current), controller_side_frames(knob, side)));
    }
  }
  return at;
}

void armature_knob_snap(const Layer & /*armature*/, Bone &knob)
{
  controller_knob_snap(knob);
}

/* A bone's own action bone actions, the one that turns it the plain way first. */
static std::array<std::string, 2> own_actions(const Layer &owner, const Bone &bone)
{
  std::array<std::string, 2> own;
  const auto has = [&](const std::string &name) {
    return std::find(owner.actions.begin(), owner.actions.end(), name) != owner.actions.end();
  };
  if (has(bone.name)) {
    own[0] = bone.name;
  }
  if (has(bone.name + " 2")) {
    own[1] = bone.name + " 2";
  }
  return own;
}

/* A bone converted: its keys in `ch` in the fixes that follow it, their line, go (as the other type they would move it). */
template<typename C> static void bone_fix_lines_drop(const Layer &owner, const Bone &bone, C &ch)
{
  for (const BoneFix &fix : owner.bone_fixes) {
    if (std::find(fix.follows.begin(), fix.follows.end(), bone.id) != fix.follows.end()) {
      ch.actions.erase(fix.name);
    }
  }
}

std::string bone_convert_to_controller(Document &doc, uint64_t owner_id, uint64_t bone_id)
{
  Layer *owner = layer_find(doc, owner_id);
  Bone *bone = owner ? bone_find(*owner, bone_id) : nullptr;
  if (!bone || bone_is_controller(*bone)) {
    return "";
  }
  std::string note;
  const std::array<std::string, 2> own = own_actions(*owner, *bone);
  /* Actions that turn it have nothing left to turn. */
  for (const auto &[action, keys] : bone->angle_keys.actions) {
    if (action != own[0] && action != own[1] &&
        std::any_of(keys.begin(), keys.end(), [](const Key<float> &k) { return std::abs(k.value) > 1e-6f; }))
    {
      note = action + " turns " + bone->name + ", and it can't turn a controller. Add a new bone for the controller "
             "instead and it goes on working.";
    }
  }
  /* Nothing connects to its knob: children on its tip hang from the knob with an offset, where they are (the knob
   * rests on the setup frame); so does any other child. */
  for (Bone &child : owner->bones) {
    if (child.parent == bone_id) {
      child.connected = false;
      child.follow_knob = true;
    }
  }
  bone = bone_find(*owner, bone_id);
  /* Moves in its own actions would be its sides' timing now: they go (the knob doesn't move in them). Its turns in the
   * fixes that follow it were their line: a knob's is its place. */
  for (const std::string &action : own) {
    if (!action.empty()) {
      bone->position_keys.actions.erase(action);
    }
  }
  bone_fix_lines_drop(*owner, *bone, bone->angle_keys);
  std::vector<Key<float>> angle_keys = std::move(bone->angle_keys.keys);
  bone->angle_keys.keys.clear();
  /* A pin turned controller is a box like any other. */
  bone->type = BoneType::Controller2D;
  bone->controller_actions = {};
  bone->controller_actions[CONTROLLER_RIGHT] = own[0];
  bone->controller_actions[CONTROLLER_LEFT] = own[1];
  bone->controller_size_auto = true;
  bone->controller_box_angle = 0.0f;
  controller_fit_size(*bone);
  if (!own[0].empty() || !own[1].empty()) {
    /* Its turns on the mainline are the knob's now. */
    bone->position_keys.keys.clear();
    const auto frame_of = [&](const std::string &action, float turn) {
      const auto it = bone->angle_keys.actions.find(action);
      return it == bone->angle_keys.actions.end()
                 ? 0.0f
                 : action_bone_frame(it->second, 0.0f,
                                     action_bone_turn_wrapped(it->second, turn, action_bone_keys_full_turn(it->second)));
    };
    controller_keys_copy(angle_keys, bone->position_keys, [&](int, float turn) {
      const float right = frame_of(own[0], turn);
      return controller_transform_of(*bone, float2(right > 0.0f ? right : -frame_of(own[1], turn), 0.0f));
    });
    /* Its moves in other actions are the knob's now, as far. */
  }
  else {
    /* Moves it was keyed with stay, as far (in every action too), and come back the same: its size stays as it is
     * for that. */
    bone->angle_keys.keys = std::move(angle_keys);
    bone->controller_size_auto = bone->position_keys.keys.empty() &&
                                 std::all_of(bone->position_keys.actions.begin(), bone->position_keys.actions.end(),
                                             [](const auto &a) { return a.second.empty(); });
  }
  bone->angle = bone->setup_angle;
  bone->turn = 0.0f;
  bone->angle_keys.last = 0.0f;
  animation_evaluate(doc, doc.frame_current);
  return note;
}

std::string bone_convert_to_regular(Document &doc, uint64_t owner_id, uint64_t bone_id)
{
  Layer *owner = layer_find(doc, owner_id);
  Bone *bone = owner ? bone_find(*owner, bone_id) : nullptr;
  if (bone && bone_is_pin(*bone)) {
    /* Its length was kept: the bone it was. */
    bone->type = BoneType::Regular;
    return "";
  }
  if (!bone || !bone_is_controller(*bone)) {
    return "";
  }
  const std::array<std::string, 2> own = own_actions(*owner, *bone);
  const bool own_right = !own[0].empty() && bone->controller_actions[CONTROLLER_RIGHT] == own[0];
  const bool own_left = !own[1].empty() && bone->controller_actions[CONTROLLER_LEFT] == own[1];
  if (own_right || own_left) {
    /* Back into the turns they came from. */
    const auto turn_at = [&](const std::string &action, float t) {
      const auto it = bone->angle_keys.actions.find(action);
      return it == bone->angle_keys.actions.end() ? 0.0f : action_bone_sample(it->second, 0.0f, t);
    };
    bone->angle_keys.keys.clear();
    controller_keys_copy(bone->position_keys.keys, bone->angle_keys, [&](int, float2 at) {
      /* How far out is a frame through the side's timing. */
      const float x = controller_frames_of(*bone, at).x;
      return x > 0.0f ? turn_at(own[0], controller_side_frame(*bone, CONTROLLER_RIGHT, x)) :
                        turn_at(own[1], controller_side_frame(*bone, CONTROLLER_LEFT, -x));
    });
    bone->position_keys.keys.clear();
  }
  /* Its keys in its sides' actions were their timing, never a move: as a bone they'd move it. So were its keys in the
   * fixes that follow it (their line). */
  for (const std::string &action : bone->controller_actions) {
    if (!action.empty()) {
      bone->position_keys.actions.erase(action);
    }
  }
  bone_fix_lines_drop(*owner, *bone, bone->position_keys);
  /* The knob's keys stay, as moves (they are distances already): the mainline's where it had no sides of its own, every
   * other action's always. */
  bone->type = BoneType::Regular;
  bone->controller_actions = {};
  bone->controller_keys = {};
  bone->controller_timing = {};
  bone->controller_knob_editing = false;
  bone->controller_knob_edit_side = -1;
  bone->controller_knob_edit_frame = 0;
  bone->controller_knob_edit_at = {};
  bone->position = bone->setup_position;
  bone->transform = {};
  bone->position_keys.last = {};
  animation_evaluate(doc, doc.frame_current);
  return "";
}

std::string bone_convert_to_pin(Document &doc, uint64_t owner_id, uint64_t bone_id)
{
  Layer *owner = layer_find(doc, owner_id);
  Bone *bone = owner ? bone_find(*owner, bone_id) : nullptr;
  if (!bone || bone_is_pin(*bone)) {
    return "";
  }
  std::string note;
  if (bone_is_controller(*bone)) {
    note = bone_convert_to_regular(doc, owner_id, bone_id);
    bone = bone_find(*owner, bone_id);
  }
  /* Children on its tip hang with an offset instead, right where they are (the tip is kept, hidden). */
  for (Bone &child : owner->bones) {
    if (child.parent == bone_id && child.connected) {
      child.connected = false;
    }
  }
  bone = bone_find(*owner, bone_id);
  bone->type = BoneType::Pin;
  animation_evaluate(doc, doc.frame_current);
  return note;
}

bool controller_side_set(Document &doc, uint64_t owner_id, uint64_t knob_id, int side, const std::string &action,
                         std::string *r_why)
{
  Layer *owner = layer_find(doc, owner_id);
  Bone *knob = owner ? bone_find(*owner, knob_id) : nullptr;
  if (!knob || !bone_is_controller(*knob) || side < 0 || side >= CONTROLLER_SIDES) {
    *r_why = "That isn't a side of a controller";
    return false;
  }
  if (!doc.action.empty()) {
    *r_why = "Go back to the mainline to pick a controller's actions";
    return false;
  }
  if (knob->controller_actions[side] == action) {
    return true;
  }
  if (!action.empty()) {
    if (std::find(owner->actions.begin(), owner->actions.end(), action) == owner->actions.end()) {
      *r_why = "There is no action \"" + action + "\"";
      return false;
    }
    if (std::string why = controller_side_refusal(*owner, knob->name, side, action); !why.empty()) {
      *r_why = std::move(why);
      return false;
    }
  }
  knob->controller_actions[side] = action;
  /* Fixes following the knob are named after the actions its sides play. */
  bone_fix_names_follow(doc, owner->id);
  controllers_update(doc);
  animation_evaluate(doc, doc.frame_current);
  return true;
}

int controller_links_undo(Document &doc)
{
  const auto linked = [](const Layer &owner) {
    return std::any_of(owner.bones.begin(), owner.bones.end(), [&](const Bone &knob) {
      return bone_is_controller(knob) &&
             std::any_of(knob.controller_actions.begin(), knob.controller_actions.end(), [&](const std::string &a) {
               return !a.empty() && controller_dial_of_action(owner, a);
             });
    });
  };
  const std::vector<const Layer *> flat = document_layers_flat(doc);
  if (std::none_of(flat.begin(), flat.end(), [&](const Layer *l) { return l->is_bone_layer() && linked(*l); })) {
    return 0;
  }
  /* The keys moved are the actions' as stored: an open action goes away while they move, and comes back. */
  const std::string open = doc.action;
  const uint64_t open_layer = doc.action_layer;
  if (!open.empty()) {
    document_set_action(doc, open_layer, "");
  }
  int count = 0;
  for (const Layer *f : document_layers_flat(doc)) {
    if (!f->is_bone_layer()) {
      continue;
    }
    Layer &owner = *layer_find(doc, f->id);
    for (Bone &knob : owner.bones) {
      for (int side = 0; side < CONTROLLER_SIDES && bone_is_controller(knob); side++) {
        const std::string old = knob.controller_actions[side];
        Bone *dial = old.empty() ? nullptr : controller_dial_of_action(owner, old);
        if (!dial) {
          continue;
        }
        /* Never a bone's name either, or the new action would be a bone's own again, and converted on every open. */
        const std::string name = controller_action_name_free(owner, knob.name + " " + controller_side_name(side));
        owner.actions.push_back(name);
        /* The new action turns the dial as its own action did, so the dial goes on playing that by its turn. */
        if (const auto it = dial->angle_keys.actions.find(old); it != dial->angle_keys.actions.end()) {
          std::vector<Key<float>> turns = it->second;
          dial->angle_keys.actions[name] = std::move(turns);
        }
        /* The knob's timing on that side moves with the side. */
        if (const auto it = knob.position_keys.actions.find(old); it != knob.position_keys.actions.end()) {
          std::vector<Key<float2>> timing = std::move(it->second);
          knob.position_keys.actions.erase(it);
          knob.position_keys.actions[name] = std::move(timing);
        }
        knob.controller_actions[side] = name;
        count++;
      }
    }
  }
  if (!open.empty()) {
    document_set_action(doc, open_layer, open);
  }
  controllers_update(doc);
  return count;
}

int bone_fix_names_follow(Document &doc, uint64_t owner_id)
{
  int count = 0;
  for (const Layer *f : document_layers_flat(doc)) {
    if (!f->is_bone_layer() || (owner_id && f->id != owner_id)) {
      continue;
    }
    Layer &owner = *layer_find(doc, f->id);
    /* Each renamed before the next is named: two wanting the same name (a knob's sides gone, both now "JawDown Down")
     * were both given the same free one, the second refused, and it kept its old name until the file was opened. */
    for (size_t i = 0; i < owner.bone_fixes.size(); i++) {
      const BoneFix &fix = owner.bone_fixes[i];
      /* The fix being edited has its keys out in the channels: it is named as it is left. */
      if (!fix.auto_name || (doc.action == fix.name && doc.action_layer == owner.id)) {
        continue;
      }
      const std::string from = fix.name;
      const std::string renamed = bone_fix_unique(owner, bone_fix_name(owner, fix), from);
      if (renamed != from) {
        count += document_action_rename(doc, owner.id, from, renamed) ? 1 : 0;
      }
    }
  }
  return count;
}

/* --- Duplicate's and Paste's Actions: the bones' own actions copied for their copies ---------------------------- */

std::vector<std::string> bones_own_actions(const Layer &owner, const std::set<uint64_t> &bones)
{
  std::vector<std::string> own;
  for (const std::string &action : owner.actions) {
    bool mine = false;
    for (const Bone &b : owner.bones) {
      if (!bones.count(b.id)) {
        continue;
      }
      if (bone_is_controller(b)) {
        mine = mine || std::find(b.controller_actions.begin(), b.controller_actions.end(), action) !=
                           b.controller_actions.end();
      }
      else if ((action == b.name || action == b.name + " 2") && controller_dial_of_action(owner, action) == &b) {
        mine = true;
      }
    }
    if (const BoneFix *fix = bone_fix_find(owner, action)) {
      mine = mine || std::any_of(fix->follows.begin(), fix->follows.end(), [&](uint64_t id) { return bones.count(id); });
    }
    if (mine) {
      own.push_back(action);
    }
  }
  return own;
}

Layer bones_actions_source(const Document &doc, const Layer &owner, const std::vector<std::string> &names)
{
  Layer source = owner;
  /* The action being edited has its keys out in the channels: away under its name first, as on leaving it. */
  if (!doc.action.empty() && doc.action_layer == owner.id) {
    owner_for_each_channel(source, [&](auto &ch, auto &value) { swap_timeline(ch, value, doc.action, std::string()); });
  }
  const std::set<std::string> kept(names.begin(), names.end());
  const auto keep = [&](const std::string &name) -> std::optional<std::string> {
    return kept.count(name) ? std::optional<std::string>(name) : std::nullopt;
  };
  const auto tidy = [&](auto &self, Layer &l) -> void {
    layer_actions_rename(l, keep);
    std::erase_if(l.action_plays, [&](const ActionPlay &a) { return !kept.count(a.name); });
    std::erase_if(l.key_together_frames, [&](const auto &f) { return !kept.count(f.first); });
    for (Layer &c : l.children) {
      self(self, c);
    }
  };
  tidy(tidy, source);
  std::erase_if(source.actions, [&](const std::string &a) { return !kept.count(a); });
  std::erase_if(source.bone_fixes, [&](const BoneFix &f) { return !kept.count(f.name); });
  return source;
}

using ChannelPtr = std::variant<Channel<float> *, Channel<float2> *>;

static void bone_channel_list(Bone &bone, std::vector<ChannelPtr> &out)
{
  const auto add = [&](auto &ch, auto & /*value*/) { out.push_back(&ch); };
  add(bone.position_keys, bone.transform);
  add(bone.angle_keys, bone.turn);
  bone_other_channels(bone, add);
}

/* A layer's channels besides its bones', in the order layer_for_each_channel walks them. */
static void layer_channel_list(Layer &layer, std::vector<ChannelPtr> &out)
{
  std::set<const void *> of_bones;
  for (Bone &b : layer.bones) {
    std::vector<ChannelPtr> list;
    bone_channel_list(b, list);
    for (const ChannelPtr &c : list) {
      std::visit([&](auto *ch) { of_bones.insert(ch); }, c);
    }
  }
  layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) {
    if (!of_bones.count(&ch)) {
      out.push_back(&ch);
    }
  });
}

/* Each of `names`' keys (first: the source's name, second: the copy's) from channel i of `from` onto channel i of `to`;
 * nothing unless the two are alike channel for channel. */
static void channels_actions_copy(const std::vector<ChannelPtr> &from, const std::vector<ChannelPtr> &to,
                                  const std::vector<std::pair<std::string, std::string>> &names)
{
  if (from.size() != to.size()) {
    return;
  }
  for (size_t i = 0; i < from.size(); i++) {
    std::visit(
        [&](auto *s) {
          using C = std::remove_pointer_t<decltype(s)>;
          C *const *t = std::get_if<C *>(&to[i]);
          if (!t) {
            return;
          }
          for (const auto &[a, b] : names) {
            if (const auto it = s->actions.find(a); it != s->actions.end()) {
              auto keys = it->second;
              (*t)->actions[b] = std::move(keys);
            }
            if (const auto it = s->action_setup.find(a); it != s->action_setup.end()) {
              auto key = it->second;
              (*t)->action_setup[b] = std::move(key);
            }
          }
        },
        from[i]);
  }
}

static void layer_tree(Layer &layer, std::vector<Layer *> &out)
{
  for (Layer &c : layer.children) {
    out.push_back(&c);
    layer_tree(c, out);
  }
}

/* Two drawings alike point for point (the same layer in another file, or one of its name drawn the same). */
static bool layers_alike(const Layer &a, const Layer &b)
{
  if (a.type != b.type || a.drawing.points.size() != b.drawing.points.size() ||
      a.drawing.curves.size() != b.drawing.curves.size() || a.bones.size() != b.bones.size())
  {
    return false;
  }
  for (size_t i = 0; i < a.drawing.points.size(); i++) {
    if (a.drawing.points[i].id != b.drawing.points[i].id) {
      return false;
    }
  }
  return true;
}

int bones_actions_copy(Document &doc, Layer &target, Layer &source, const std::map<uint64_t, uint64_t> &copies,
                       const std::vector<std::string> &wanted)
{
  if (wanted.empty() || copies.empty()) {
    return 0;
  }
  /* Made on the mainline: the action being edited is put away and brought back after. */
  const std::string open = doc.action_layer == target.id ? doc.action : std::string();
  if (!open.empty()) {
    document_set_action(doc, target.id, "");
  }
  std::map<uint64_t, uint64_t> back; /* a copy's id here: the source bone it copies */
  for (const auto &[from, to] : copies) {
    back[to] = from;
  }
  /* The bone here a source bone is: its copy, else (not copied) the bone of its name. */
  const auto here = [&](uint64_t id) -> const Bone * {
    if (const auto it = copies.find(id); it != copies.end()) {
      return bone_find(target, it->second);
    }
    const Bone *was = bone_find(source, id);
    return was ? bone_find_by_name(target, was->name) : nullptr;
  };
  /* Each action's copy, named after the copy of the bone it is named after, else numbered. */
  std::vector<std::pair<std::string, std::string>> names;
  for (const std::string &action : wanted) {
    const BoneFix *fix = bone_fix_find(source, action);
    if (fix && std::any_of(fix->follows.begin(), fix->follows.end(), [&](uint64_t id) { return !here(id); })) {
      continue; /* it follows a bone this bone layer hasn't */
    }
    std::string name = action;
    bool turn = false;
    for (const auto &[from, to] : copies) {
      const Bone *b = bone_find(source, from);
      const Bone *c = bone_find(target, to);
      if (!b || !c) {
        continue;
      }
      const bool side = bone_is_controller(*b) && std::find(b->controller_actions.begin(), b->controller_actions.end(),
                                                            action) != b->controller_actions.end();
      turn = !bone_is_controller(*b) && (action == b->name || action == b->name + " 2");
      if (side || turn) {
        if (const size_t at = action.find(b->name); at != std::string::npos) {
          name = action.substr(0, at) + c->name + action.substr(at + b->name.size());
        }
        break;
      }
    }
    const bool taken = std::find(target.actions.begin(), target.actions.end(), name) != target.actions.end();
    if (!turn || taken) {
      name = controller_action_name_free(target, name);
    }
    target.actions.push_back(name);
    names.push_back({action, name});
  }
  /* The keys: a copied bone's onto its copy (the bone copied gets none), every other bone's and layer's onto itself. */
  std::set<uint64_t> copied;
  for (const auto &[from, to] : copies) {
    copied.insert(from);
  }
  for (Bone &t : target.bones) {
    Bone *s = nullptr;
    if (const auto it = back.find(t.id); it != back.end()) {
      s = bone_find(source, it->second);
    }
    else {
      for (Bone &b : source.bones) {
        s = !copied.count(b.id) && b.name == t.name ? &b : s;
      }
    }
    if (s) {
      std::vector<ChannelPtr> from, to;
      bone_channel_list(*s, from);
      bone_channel_list(t, to);
      channels_actions_copy(from, to, names);
    }
  }
  std::vector<std::pair<Layer *, Layer *>> layers = {{&source, &target}};
  {
    std::vector<Layer *> ours, theirs;
    layer_tree(target, ours);
    layer_tree(source, theirs);
    std::set<const Layer *> used;
    for (Layer *t : ours) {
      Layer *match = nullptr;
      for (Layer *s : theirs) {
        match = !match && s->id == t->id ? s : match;
      }
      for (Layer *s : theirs) {
        match = !match && !used.count(s) && s->name == t->name ? s : match;
      }
      if (match && layers_alike(*match, *t)) {
        used.insert(match);
        layers.push_back({match, t});
      }
    }
  }
  for (const auto &[s, t] : layers) {
    std::vector<ChannelPtr> from, to;
    layer_channel_list(*s, from);
    layer_channel_list(*t, to);
    channels_actions_copy(from, to, names);
    for (const auto &[a, b] : names) {
      if (const auto it = s->key_together_frames.find(a); it != s->key_together_frames.end()) {
        auto frames = it->second;
        t->key_together_frames[b] = std::move(frames);
      }
    }
    if (s != &source) {
      for (Bone &tb : t->bones) {
        for (Bone &sb : s->bones) {
          if (sb.name == tb.name) {
            std::vector<ChannelPtr> bf, bt;
            bone_channel_list(sb, bf);
            bone_channel_list(tb, bt);
            channels_actions_copy(bf, bt, names);
          }
        }
      }
    }
  }
  /* How each plays, the copied knobs' sides and the fixes, following the copies. */
  for (const auto &[a, b] : names) {
    for (const ActionPlay &p : source.action_plays) {
      if (p.name == a) {
        ActionPlay play = p;
        play.name = b;
        target.action_plays.push_back(std::move(play));
      }
    }
    if (const BoneFix *fix = bone_fix_find(source, a)) {
      BoneFix made = *fix;
      made.name = b;
      for (uint64_t &id : made.follows) {
        id = here(id)->id;
      }
      target.bone_fixes.push_back(std::move(made));
    }
  }
  for (const auto &[from, to] : copies) {
    const Bone *b = bone_find(source, from);
    Bone *c = bone_find(target, to);
    if (!b || !c || !bone_is_controller(*b)) {
      continue;
    }
    for (int side = 0; side < CONTROLLER_SIDES; side++) {
      for (const auto &[a, n] : names) {
        if (!a.empty() && b->controller_actions[size_t(side)] == a) {
          c->controller_actions[size_t(side)] = n;
        }
      }
    }
  }
  bone_fix_names_follow(doc, target.id);
  controllers_update(doc);
  if (!open.empty()) {
    document_set_action(doc, target.id, open);
  }
  return int(names.size());
}

std::vector<std::pair<Layer *, std::string>> layers_keyed_at(const std::vector<Layer *> &layers,
                                                             const KeyFilter &filter, int frame)
{
  std::vector<std::pair<Layer *, std::string>> keyed;
  for (Layer *layer : layers) {
    for (const ChannelRef &ref : layer_filtered_channels(*layer, filter)) {
      if (ref.scalar ? ref.scalar->key_at(frame) != nullptr : ref.vector->key_at(frame) != nullptr) {
        keyed.push_back({layer, ref.path});
      }
    }
  }
  return keyed;
}

std::vector<ChannelRef> layer_channels(Layer &layer, bool drawing)
{
  std::vector<ChannelRef> refs;
  const auto add = [&](std::string path, auto &ch, auto &value) {
    ChannelRef ref;
    ref.path = std::move(path);
    if constexpr (std::is_same_v<std::decay_t<decltype(value)>, float>) {
      ref.scalar = &ch;
      ref.scalar_value = &value;
    }
    else {
      ref.vector = &ch;
      ref.vector_value = &value;
    }
    refs.push_back(std::move(ref));
  };
  add("position", layer.position_keys, layer.position);
  add("rotation", layer.rotation_keys, layer.rotation);
  add("scale", layer.scale_keys, layer.scale);
  add("shear", layer.shear_keys, layer.shear);
  add("opacity", layer.opacity_keys, layer.opacity);
  add("visible", layer.visible_keys, layer.visible_value);
  add("draw_order", layer.draw_order_keys, layer.draw_order);
  if (layer.is_switch()) {
    add("switch", layer.switch_keys, layer.switch_value);
  }
  for (Bone &bone : layer.bones) {
    const std::string base = "bones[\"" + bone.name + "\"].";
    /* Its keys hold Transform and Angle (see layer_for_each_channel); a change made through them
     * goes back with bone_values_from_changes. */
    bone_changes_from_values(bone);
    add(base + "position", bone.position_keys, bone.transform);
    add(base + "angle", bone.angle_keys, bone.turn);
    add(base + "scale", bone.scale_keys, bone.scale);
    add(base + "depth", bone.depth_keys, bone.depth);
    bone_curve_channels(bone, [&](std::string_view name, float &value, Channel<float> &keys) {
      add(base + std::string(name), keys, value);
    });
    for (size_t i = 0; i < bone.constraints.size(); i++) {
      BoneConstraint &c = bone.constraints[i];
      const std::string cb = base + "constraints[" + std::to_string(i) + "].";
      add(cb + "influence", c.influence_keys, c.influence);
      if (c.type == BoneConstraintType::IKEnd || c.type == BoneConstraintType::IKBase) {
        add(cb + "pin", c.pin_keys, c.pin);
      }
      if (c.type == BoneConstraintType::FollowPoint) {
        add(cb + "follow_shift", c.follow_shift_keys, c.follow_shift);
        add(cb + "follow_shift2", c.follow_shift2_keys, c.follow_shift2);
        add(cb + "follow_shift3", c.follow_shift3_keys, c.follow_shift3);
      }
      add(cb + "weight", c.weight_keys, c.weight);
      add(cb + "wind_catch", c.wind_catch_keys, c.wind_catch);
      add(cb + "gravity", c.gravity_keys, c.gravity);
      add(cb + "wind", c.wind_keys, c.wind);
      add(cb + "wind_direction", c.wind_direction_keys, c.wind_direction);
      add(cb + "wind_gusts", c.wind_gusts_keys, c.wind_gusts);
      add(cb + "wind_gust_speed", c.wind_gust_speed_keys, c.wind_gust_speed);
      add(cb + "wind_turbulence", c.wind_turbulence_keys, c.wind_turbulence);
      for (const auto &[name, s] : {std::pair<const char *, BoneSpring *>{"angle_spring.", &c.angle_spring},
                                    {"position_spring.", &c.position_spring},
                                    {"scale_spring.", &c.scale_spring}})
      {
        add(cb + name + "settle_speed", s->settle_speed_keys, s->settle_speed);
        add(cb + name + "bounce", s->bounce_keys, s->bounce);
        add(cb + name + "inertia", s->inertia_keys, s->inertia);
        add(cb + name + "stretch", s->stretch_keys, s->stretch);
        add(cb + name + "limit", s->limit_keys, s->limit);
        if (s == &c.scale_spring) {
          add(cb + name + "squash_limit", s->squash_limit_keys, s->squash_limit);
        }
      }
    }
  }
  for (CustomChannel &c : layer.custom_channels) {
    add(c.path, c.keys, c.value);
  }
  for (ActionPlay &a : layer.action_plays) {
    add(action_frame_path(a.name), a.frame_keys, a.frame);
  }
  /* A mask row's End Lines at Edge Reach. */
  for (size_t i = 0; i < layer.masks.size(); i++) {
    add("masks[" + std::to_string(i) + "].reach", layer.masks[i].line_reach_keys, layer.masks[i].line_reach);
  }
  /* A Boolean modifier's Smoothing. */
  for (size_t i = 0; i < layer.modifiers.size(); i++) {
    if (layer.modifiers[i].type == ModifierType::Boolean) {
      add("modifiers[" + std::to_string(i) + "].smoothing", layer.modifiers[i].merge_smoothing_keys,
          layer.modifiers[i].merge_smoothing);
    }
    if (layer.modifiers[i].type == ModifierType::Bevel) {
      add("modifiers[" + std::to_string(i) + "].amount", layer.modifiers[i].bevel_amount_keys,
          layer.modifiers[i].bevel_amount);
    }
    if (modifier_is_deform(layer.modifiers[i].type)) {
      add("modifiers[" + std::to_string(i) + "].strength", layer.modifiers[i].deform_strength_keys,
          layer.modifiers[i].deform_strength);
    }
    if (layer.modifiers[i].type == ModifierType::FollowDeform) {
      add("modifiers[" + std::to_string(i) + "].shift", layer.modifiers[i].deform_shift_keys, layer.modifiers[i].deform_shift);
      add("modifiers[" + std::to_string(i) + "].shift2", layer.modifiers[i].deform_shift2_keys, layer.modifiers[i].deform_shift2);
    }
  }
  if (!drawing) {
    return refs;
  }
  if (layer.is_reference()) {
    /* A reference's points move by its own offsets (by the point's place in its drawing). */
    for (size_t i = 0; i < layer.drawing.points.size(); i++) {
      if (auto it = layer.reference.points.find(layer.drawing.points[i].id); it != layer.reference.points.end()) {
        add("points[" + std::to_string(i) + "].offset", it->second.offset_keys, it->second.offset);
      }
    }
    /* And its handles' offsets, by the handle's place in its drawing. */
    const VectorDrawing &d = layer.drawing;
    for (size_t c = 0; c < d.curves.size(); c++) {
      const Curve &curve = d.curves[c];
      const int n = int(curve.points.size());
      for (int i = 0; i < n; i++) {
        for (const bool in : {true, false}) {
          const int j = in ? (i > 0 ? i - 1 : (curve.closed ? n - 1 : -1)) : (i + 1 < n ? i + 1 : (curve.closed ? 0 : -1));
          const ReferenceHandleKey key{d.points[curve.points[i].point].id,
                                       j >= 0 && j != i ? d.points[curve.points[j].point].id : 0, in};
          if (auto it = layer.reference.handles.find(key); it != layer.reference.handles.end()) {
            add("curves[" + std::to_string(c) + "].points[" + std::to_string(i) + "]." +
                    (in ? "handle_in_offset" : "handle_out_offset"),
                it->second.offset_keys, it->second.offset);
          }
        }
      }
    }
    return refs;
  }
  /* Their keys hold the Transform and the handles' Angle and Length (see layer_for_each_channel); a
   * change made through them goes back with drawing_values_from_changes. */
  drawing_changes_from_values(layer.drawing);
  for (size_t i = 0; i < layer.drawing.points.size(); i++) {
    MeshPoint &p = layer.drawing.points[i];
    const std::string base = "points[" + std::to_string(i) + "].";
    add(base + "pos", p.pos_keys, p.transform);
    add(base + "radius", p.radius_keys, p.radius);
  }
  for (size_t c = 0; c < layer.drawing.curves.size(); c++) {
    Curve &curve = layer.drawing.curves[c];
    for (size_t i = 0; i < curve.points.size(); i++) {
      CurvePoint &cp = curve.points[i];
      const std::string base = "curves[" + std::to_string(c) + "].points[" + std::to_string(i) + "].";
      add(base + "curvature", cp.curvature_keys, cp.curvature);
      add(base + "handle_in", cp.handle_in_keys, cp.change_in);
      add(base + "handle_out", cp.handle_out_keys, cp.change_out);
    }
  }
  return refs;
}

/* layer_channel for the channels drivers name most (the layer's own, a bone's and its constraints',
 * custom ones), found by their path without listing every channel of the layer: a rig with many
 * drivers asks for them many times a frame (their settings, which aren't channels, too). False when
 * it isn't a channel; `r_final` says whether that's the answer (any bone's path: the full list has no
 * other bone channels) or the full list should be looked through. */
static bool layer_channel_direct(Layer &layer, const std::string &path, ChannelRef *r_ref, bool *r_final)
{
  *r_final = true;
  const auto take = [&](auto &ch, auto &value) {
    *r_ref = ChannelRef();
    r_ref->path = path;
    if constexpr (std::is_same_v<std::decay_t<decltype(value)>, float>) {
      r_ref->scalar = &ch;
      r_ref->scalar_value = &value;
    }
    else {
      r_ref->vector = &ch;
      r_ref->vector_value = &value;
    }
    return true;
  };
  if (path == "position") return take(layer.position_keys, layer.position);
  if (path == "rotation") return take(layer.rotation_keys, layer.rotation);
  if (path == "scale") return take(layer.scale_keys, layer.scale);
  if (path == "shear") return take(layer.shear_keys, layer.shear);
  if (path == "opacity") return take(layer.opacity_keys, layer.opacity);
  if (path == "visible") return take(layer.visible_keys, layer.visible_value);
  if (path == "draw_order") return take(layer.draw_order_keys, layer.draw_order);
  if (path == "switch" && layer.is_switch()) return take(layer.switch_keys, layer.switch_value);
  if (path.rfind("bones[\"", 0) == 0) {
    const size_t end = path.find("\"].", 7);
    if (end == std::string::npos) {
      return false;
    }
    const std::string_view name(path.data() + 7, end - 7);
    Bone *bone = nullptr;
    for (Bone &b : layer.bones) {
      if (b.name == name) {
        bone = &b;
        break;
      }
    }
    if (!bone) {
      return false;
    }
    const std::string_view rest(path.data() + end + 3, path.size() - end - 3);
    /* Its keys hold Transform and Angle, as layer_channels has them. */
    bone_changes_from_values(*bone);
    if (rest == "position") return take(bone->position_keys, bone->transform);
    if (rest == "angle") return take(bone->angle_keys, bone->turn);
    if (rest == "scale") return take(bone->scale_keys, bone->scale);
    if (rest == "depth") return take(bone->depth_keys, bone->depth);
    bool curve = false, curve_taken = false;
    bone_curve_channels(*bone, [&](std::string_view name, float &value, Channel<float> &keys) {
      if (!curve && rest == name) {
        curve = true;
        curve_taken = take(keys, value);
      }
    });
    if (curve) {
      return curve_taken;
    }
    constexpr std::string_view prefix = "constraints[";
    if (rest.substr(0, prefix.size()) != prefix) {
      return false;
    }
    const size_t close = rest.find("].");
    if (close == std::string_view::npos) {
      return false;
    }
    const size_t i = size_t(std::strtoull(std::string(rest.substr(prefix.size(), close - prefix.size())).c_str(), nullptr, 10));
    if (i >= bone->constraints.size()) {
      return false;
    }
    BoneConstraint &c = bone->constraints[i];
    const std::string_view field = rest.substr(close + 2);
    if (field == "influence") return take(c.influence_keys, c.influence);
    if (field == "pin") return take(c.pin_keys, c.pin);
    if (field == "follow_shift") return take(c.follow_shift_keys, c.follow_shift);
    if (field == "follow_shift2") return take(c.follow_shift2_keys, c.follow_shift2);
    if (field == "follow_shift3") return take(c.follow_shift3_keys, c.follow_shift3);
    if (field == "weight") return take(c.weight_keys, c.weight);
    if (field == "wind_catch") return take(c.wind_catch_keys, c.wind_catch);
    if (field == "gravity") return take(c.gravity_keys, c.gravity);
    if (field == "wind") return take(c.wind_keys, c.wind);
    if (field == "wind_direction") return take(c.wind_direction_keys, c.wind_direction);
    if (field == "wind_gusts") return take(c.wind_gusts_keys, c.wind_gusts);
    if (field == "wind_gust_speed") return take(c.wind_gust_speed_keys, c.wind_gust_speed);
    if (field == "wind_turbulence") return take(c.wind_turbulence_keys, c.wind_turbulence);
    for (const auto &[spring_name, spring] : {std::pair<std::string_view, BoneSpring *>{"angle_spring.", &c.angle_spring},
                                              {"position_spring.", &c.position_spring},
                                              {"scale_spring.", &c.scale_spring}})
    {
      if (field.substr(0, spring_name.size()) != spring_name) {
        continue;
      }
      const std::string_view what = field.substr(spring_name.size());
      if (what == "settle_speed") return take(spring->settle_speed_keys, spring->settle_speed);
      if (what == "bounce") return take(spring->bounce_keys, spring->bounce);
      if (what == "inertia") return take(spring->inertia_keys, spring->inertia);
      if (what == "stretch") return take(spring->stretch_keys, spring->stretch);
      if (what == "limit") return take(spring->limit_keys, spring->limit);
      if (what == "squash_limit") return take(spring->squash_limit_keys, spring->squash_limit);
    }
    return false;
  }
  for (CustomChannel &c : layer.custom_channels) {
    if (c.path == path) {
      return take(c.keys, c.value);
    }
  }
  *r_final = false;
  return false;
}

bool layer_channel(Layer &layer, const std::string &path, ChannelRef *r_ref)
{
  bool final = false;
  if (layer_channel_direct(layer, path, r_ref, &final)) {
    return true;
  }
  if (final) {
    return false;
  }
  /* Only a point's or curve's channel needs the drawing's (which works out every point's change). */
  const bool drawing = path.rfind("points[", 0) == 0 || path.rfind("curves[", 0) == 0;
  for (ChannelRef &ref : layer_channels(layer, drawing)) {
    if (ref.path == path) {
      *r_ref = ref;
      return true;
    }
  }
  return false;
}

int layer_insert_keys(Layer &layer, int frame)
{
  int count = 0;
  layer_for_each_channel(layer, [&](auto &ch, auto &value) {
    if (ch.keyed_by_hand && !ch.animated()) {
      return;
    }
    /* Keys hold the value without what action bone actions add. */
    const auto base = value - ch.from_action_bones;
    if (!ch.animated() && frame != 0) {
      ch.set_key(0, ch.has_last ? ch.last - ch.from_action_bones : base);
    }
    key_put(ch, frame, base);
    ch.last = value;
    ch.has_last = true;
    count++;
  });
  return count;
}

int layer_insert_filtered_keys(Layer &layer, const KeyFilter &filter, int frame)
{
  int count = 0;
  const auto key = [&](auto &ch, auto &value) {
    /* As layer_insert_keys: a setting keyed only by hand (a mask's Reach) waits to be keyed so. */
    if (ch.keyed_by_hand && !ch.animated()) {
      return;
    }
    const auto base = value - ch.from_action_bones;
    if (!ch.animated() && frame != 0) {
      ch.set_key(0, ch.has_last ? ch.last - ch.from_action_bones : base);
    }
    key_put(ch, frame, base);
    ch.last = value;
    ch.has_last = true;
    count++;
  };
  for (const ChannelRef &ref : layer_filtered_channels(layer, filter)) {
    if (ref.scalar) {
      key(*ref.scalar, *ref.scalar_value);
    }
    else if (ref.vector) {
      key(*ref.vector, *ref.vector_value);
    }
  }
  return count;
}

/* As in Blender, a property with no keys left isn't animated: once only the setup key (frame 0)
 * is left, it goes too, and the value stays what frame 0 had. */
template<typename T> static void drop_lone_setup_key(Channel<T> &ch, T &value)
{
  if (ch.keys.size() == 1 && ch.keys.front().frame == 0) {
    value = ch.keys.front().value + ch.from_action_bones;
    ch.last = value;
    ch.keys.clear();
  }
}

template<typename T> static bool delete_key(Channel<T> &ch, T &value, int frame)
{
  if (frame == 0 && ch.keys.size() > 1) {
    return false;
  }
  const KeyEnds ends = key_ends(ch);
  const bool removed = ch.remove_key(frame);
  /* Only what this took away can leave the setup key alone (one already alone is kept: nothing was deleted). */
  if (removed) {
    keys_ends_release(ch, ends);
    drop_lone_setup_key(ch, value);
  }
  return removed;
}

bool channel_delete_key(Channel<float> &ch, float &value, int frame)
{
  return delete_key(ch, value, frame);
}

bool channel_delete_key(Channel<float2> &ch, float2 &value, int frame)
{
  return delete_key(ch, value, frame);
}

int layer_toggle_keys(Layer &layer, const std::vector<std::string> &paths, int frame, int mode)
{
  std::vector<ChannelRef> refs;
  for (const std::string &path : paths) {
    ChannelRef ref;
    if (layer_channel(layer, path, &ref)) {
      refs.push_back(ref);
    }
  }
  bool keyed = false;
  for (const ChannelRef &ref : refs) {
    keyed |= ref.scalar ? ref.scalar->key_at(frame) != nullptr : ref.vector->key_at(frame) != nullptr;
  }
  if (mode != 0) {
    keyed = mode < 0;
  }
  int count = 0;
  const auto toggle = [&](auto &ch, auto &value) {
    if (keyed) {
      count += delete_key(ch, value, frame) ? 1 : 0;
      return;
    }
    const auto base = value - ch.from_action_bones;
    if (!ch.animated() && frame != 0) {
      /* The setup key takes the value from before an edit not yet keyed. */
      ch.set_key(0, ch.has_last ? ch.last - ch.from_action_bones : base);
    }
    key_put(ch, frame, base);
    ch.last = value;
    ch.has_last = true;
    count++;
  };
  for (const ChannelRef &ref : refs) {
    if (ref.scalar) {
      toggle(*ref.scalar, *ref.scalar_value);
    }
    else {
      toggle(*ref.vector, *ref.vector_value);
    }
  }
  for (Bone &bone : layer.bones) {
    bone_values_from_changes(bone);
  }
  if (!layer.is_reference()) {
    drawing_values_from_changes(layer.drawing);
  }
  return keyed ? -count : count;
}

int layer_action_bone_state(Layer &layer, const std::vector<std::string> &paths)
{
  for (const std::string &path : paths) {
    ChannelRef ref;
    if (layer_channel(layer, path, &ref) &&
        (ref.scalar ? ref.scalar->action_bone_live : ref.vector->action_bone_live))
    {
      return KEY_STATE_ACTION_BONE;
    }
  }
  return 0;
}

std::vector<ChannelSource> layer_channel_sources(Document &doc, Layer &layer, const std::string &path)
{
  std::vector<ChannelSource> sources;
  ChannelRef ref;
  if (!layer_channel(layer, path, &ref) || !(ref.scalar ? ref.scalar->action_bone_live : ref.vector->action_bone_live)) {
    return sources;
  }
  const void *target = ref.scalar ? static_cast<const void *>(ref.scalar) : static_cast<const void *>(ref.vector);
  for (const Layer *flat : document_layers_flat(doc)) {
    if (!flat->is_bone_layer() || flat->actions.empty()) {
      continue;
    }
    Layer &owner = *layer_find(doc, flat->id);
    /* What plays, as apply_action_bone_actions_playing has it. */
    std::vector<std::pair<std::string, float>> playing = action_bone_actions_playing(owner);
    ActionOwnLengths lengths;
    action_own_frames(owner, -1, lengths, playing);
    for (const BoneFix &fix : owner.bone_fixes) {
      if (!action_muted(owner, fix.name)) {
        playing.push_back({fix.name, 0.0f});
      }
    }
    std::set<const void *> action_bones;
    for (const std::string &name : owner.actions) {
      if (const Bone *b = action_bone_of(owner, name)) {
        action_bones.insert({&b->position_keys, &b->angle_keys, &b->scale_keys});
      }
    }
    for (const auto &[name, t] : playing) {
      if (name == doc.action && owner.id == doc.action_layer) {
        continue;
      }
      const BoneFix *fix = bone_fix_find(owner, name);
      const Bone *by = fix ? nullptr : action_bone_of(owner, name);
      const Bone *knob = fix ? nullptr : controller_of_action(owner, name, nullptr);
      ChannelSource source;
      source.owner = owner.id;
      source.action = name;
      if (fix) {
        const BoneFixPlay at = bone_fix_play(owner, *fix);
        if (at.strength <= 0.0f) {
          continue;
        }
        source.kind = ChannelSourceKind::Fix;
        source.amount = at.strength;
        const Bone *first = fix->follows.empty() ? nullptr : bone_find(owner, fix->follows.front());
        source.bone = first ? first->name : std::string();
      }
      else {
        const float length = action_length(owner, name);
        source.amount = length > 0.0f ? std::clamp(t / length, 0.0f, 1.0f) : 0.0f;
        source.kind = by ? (bone_is_controller(*by) ? ChannelSourceKind::Knob : ChannelSourceKind::ActionBone)
                         : ChannelSourceKind::Action;
        source.bone = by ? by->name : std::string();
      }
      bool moves = false;
      owner_for_each_channel_with(owner, name, [&](auto &ch, auto &value) {
        if (static_cast<const void *>(&ch) != target ||
            (by && target == static_cast<const void *>(&by->angle_keys)) ||
            (knob && target == static_cast<const void *>(&knob->position_keys)) ||
            (fix && (action_bones.count(target) || bone_fix_tracing(owner, *fix, target))))
        {
          return;
        }
        const auto it = ch.actions.find(name);
        if (it == ch.actions.end()) {
          return;
        }
        /* An action keys every bone, most held still: only one that takes it somewhere. */
        const auto setup = ch.animated() ? ch.evaluate(0) : value - ch.from_action_bones;
        for (const auto &k : it->second) {
          const auto off = k.value - setup;
          if constexpr (std::is_same_v<std::decay_t<decltype(off)>, float>) {
            moves = moves || std::abs(off) > 1e-6f;
          }
          else {
            moves = moves || std::abs(off.x) > 1e-6f || std::abs(off.y) > 1e-6f;
          }
        }
      });
      if (moves) {
        sources.push_back(std::move(source));
      }
    }
  }
  return sources;
}

bool layer_channel_own_value(Layer &layer, const std::string &path, float2 *r_own, float2 *r_shown, bool *r_vector)
{
  ChannelRef ref;
  if (!layer_channel(layer, path, &ref)) {
    return false;
  }
  *r_vector = ref.vector != nullptr;
  if (ref.scalar) {
    *r_shown = float2{*ref.scalar_value, 0.0f};
    *r_own = float2{*ref.scalar_value - ref.scalar->from_action_bones, 0.0f};
  }
  else {
    *r_shown = *ref.vector_value;
    *r_own = *ref.vector_value - ref.vector->from_action_bones;
  }
  return true;
}

int layer_key_state(Layer &layer, const std::vector<std::string> &paths, int frame)
{
  int state = 0;
  for (const std::string &path : paths) {
    ChannelRef ref;
    if (!layer_channel(layer, path, &ref)) {
      continue;
    }
    const bool animated = ref.scalar ? ref.scalar->animated() : ref.vector->animated();
    const bool here = ref.scalar ? ref.scalar->key_at(frame) != nullptr : ref.vector->key_at(frame) != nullptr;
    state = std::max(state, here ? 2 : animated ? 1 : 0);
  }
  return state;
}

int layer_delete_keys(Layer &layer, int frame)
{
  int count = 0;
  layer_for_each_channel(layer, [&](auto &ch, auto &value) { count += delete_key(ch, value, frame) ? 1 : 0; });
  return count;
}

std::vector<int> layer_key_frames(const Layer &layer)
{
  std::set<int> frames;
  layer_for_each_channel(const_cast<Layer &>(layer), [&](auto &ch, auto & /*value*/) {
    for (const auto &key : ch.keys) {
      frames.insert(key.frame);
    }
  });
  return {frames.begin(), frames.end()};
}

bool layer_has_keys(const Layer &layer)
{
  bool any = false;
  layer_for_each_channel<false>(const_cast<Layer &>(layer), [&](auto &ch, auto & /*value*/) { any |= !ch.keys.empty(); });
  return any;
}

bool layer_channel_pinned(Layer &layer, const std::string &path)
{
  ChannelRef ref;
  return layer_channel(layer, path, &ref) && (ref.scalar ? ref.scalar->pinned : ref.vector->pinned);
}

int layer_pin_channels(Layer &layer, const std::vector<std::string> &paths, bool pinned)
{
  int changed = 0;
  for (const std::string &path : paths) {
    ChannelRef ref;
    if (!layer_channel(layer, path, &ref)) {
      continue;
    }
    bool &flag = ref.scalar ? ref.scalar->pinned : ref.vector->pinned;
    changed += flag != pinned ? 1 : 0;
    flag = pinned;
  }
  return changed;
}

int document_clear_pins(Document &doc)
{
  int cleared = 0;
  const auto unpin = [&](Layer &layer) {
    layer_for_each_channel(layer, [&](auto &ch, auto & /*value*/) {
      cleared += ch.pinned ? 1 : 0;
      ch.pinned = false;
    });
  };
  for (const Layer *layer : document_layers_flat(doc)) {
    unpin(*layer_find(doc, layer->id));
  }
  unpin(doc.simulation);
  unpin(doc.camera);
  return cleared;
}

std::string channel_label(Layer &layer, const std::string &path, bool owner)
{
  static const std::pair<const char *, const char *> NAMES[] = {
      {"position", "Position"},
      {"rotation", "Rotation"},
      {"scale", "Scale"},
      {"shear", "Shear"},
      {"depth", "Depth"},
      {"curve_turn", "Curve Joint Turn"},
      {"curve_lined", "Curve Joint Lined Up"},
      {"curve_head_angle", "Curve Head Angle"},
      {"curve_parent_angle", "Curve Parent Angle"},
      {"curve_head_reach", "Curve Head Reach"},
      {"curve_parent_reach", "Curve Parent Reach"},
      {"curve_tail_turn", "Curve Tail Turn"},
      {"curve_tail_lined", "Curve Tail Lined Up"},
      {"curve_tail_angle", "Curve Tail Angle"},
      {"curve_tail_reach", "Curve Tail Reach"},
      {"opacity", "Opacity"},
      {"visible", "Visibility"},
      {"draw_order", "Draw Order"},
      {"switch", "Switch"},
      {"angle", "Angle"},
      {"influence", "Influence"},
      {"gravity", "Gravity"},
      {"wind", "Wind"},
      {"wind_catch", "Wind Catch"},
      {"wind_direction", "Wind Direction"},
      {"wind_gusts", "Gusts"},
      {"wind_gust_speed", "Gust Speed"},
      {"wind_turbulence", "Turbulence"},
      {"settle_speed", "Settle Speed"},
      {"bounce", "Bounce"},
      {"weight", "Weight"},
      {"inertia", "Inertia"},
      {"stretch", "Stretch"},
      {"zoom", "Zoom"},
  };
  const auto name_of = [](const std::string &id) -> std::string {
    for (const auto &[key, name] : NAMES) {
      if (id == key) {
        return name;
      }
    }
    return id;
  };
  if (path.rfind("masks[", 0) == 0) {
    /* "Mask 1: Reach". */
    const std::string name = "Mask " + std::to_string(std::atoi(path.c_str() + 6) + 1) + ": Reach";
    return owner ? layer.name + ": " + name : name;
  }
  if (path.rfind("bones[\"", 0) != 0) {
    /* The camera turns about its centre: its Roll. */
    const std::string name = layer.id == CAMERA_LAYER_ID && path == "rotation" ? std::string("Roll") : name_of(path);
    return owner ? layer.name + ": " + name : name;
  }
  const size_t end = path.find("\"]");
  if (end == std::string::npos) {
    return path;
  }
  const std::string bone_name = path.substr(7, end - 7);
  std::string rest = path.substr(std::min(end + 3, path.size()));
  std::string label;
  if (rest.rfind("constraints[", 0) == 0) {
    /* "IK: Influence", "Dynamics: Angle Bounce", "Dynamics: Max Swing". */
    const int i = std::atoi(rest.c_str() + 12);
    const Bone *bone = bone_find_by_name(layer, bone_name);
    const std::string constraint = bone && i >= 0 && i < int(bone->constraints.size()) ? bone->constraints[i].name
                                                                                        : "Constraint";
    rest = rest.substr(std::min(rest.find('.') + 1, rest.size()));
    std::string setting;
    for (const auto &[prefix, channel, limit] :
         {std::tuple{"angle_spring.", "Angle", "Max Swing"}, std::tuple{"position_spring.", "Position", "Max Distance"},
          std::tuple{"scale_spring.", "Squash & Stretch", "Max Stretch"}})
    {
      if (rest.rfind(prefix, 0) == 0) {
        const std::string what = rest.substr(std::string(prefix).size());
        setting = what == "limit"          ? std::string(limit)
                  : what == "squash_limit" ? std::string("Max Squash")
                                           : std::string(channel) + " " + name_of(what);
      }
    }
    label = constraint + ": " + (setting.empty() ? name_of(rest) : setting);
  }
  else {
    /* A bone's position is its Transform, as the Bone panel names it (the change from setup). */
    label = rest == "position" ? std::string("Transform") : name_of(rest);
  }
  return owner ? bone_name + ": " + label : label;
}

KeyKind channel_kind(const std::string &path)
{
  if (simulation_path(path)) {
    return KEY_SIMULATION;
  }
  if (path.rfind("bones[", 0) == 0 && path.find(".constraints[") != std::string::npos) {
    return KEY_CONSTRAINTS;
  }
  if (path.rfind("points[", 0) == 0 || path.rfind("curves[", 0) == 0) {
    return KEY_POINTS;
  }
  if (path.rfind("bones[", 0) == 0) {
    return path.size() > 6 && path.compare(path.size() - 6, 6, ".angle") == 0 ? KEY_BONE_ANGLE : KEY_BONE_TRANSFORM;
  }
  if (path == "rotation") {
    return KEY_LAYER_ANGLE;
  }
  if (path == "opacity") {
    return KEY_OPACITY;
  }
  if (path == "visible") {
    return KEY_VISIBILITY;
  }
  if (path == "switch") {
    return KEY_SWITCH;
  }
  if (path == "draw_order") {
    return KEY_DRAW_ORDER;
  }
  return KEY_LAYER_TRANSFORM;
}

/* Whether the thing a channel animates is selected: the point (or the curve point's point), or
 * the bone; every channel of the camera while it is picked. Other layer channels have no thing of
 * their own. */
static bool channel_thing_selected(const Layer &layer, const std::string &path, const KeyFilter &filter)
{
  if (layer.id == CAMERA_LAYER_ID) {
    return layer.selected;
  }
  if ((path.rfind("points[", 0) == 0 || path.rfind("curves[", 0) == 0) && filter.point_layers &&
      !filter.point_layers->contains(layer.id))
  {
    return false;
  }
  const auto number_after = [&](size_t at) { return std::atoi(path.c_str() + at); };
  if (path.rfind("points[", 0) == 0) {
    const int i = number_after(7);
    return i >= 0 && i < int(layer.drawing.points.size()) && layer.drawing.points[i].selected;
  }
  if (path.rfind("curves[", 0) == 0) {
    const int c = number_after(7);
    const size_t at = path.find("points[");
    if (c < 0 || c >= int(layer.drawing.curves.size()) || at == std::string::npos) {
      return false;
    }
    const int k = number_after(at + 7);
    const Curve &curve = layer.drawing.curves[c];
    return k >= 0 && k < int(curve.points.size()) && layer.drawing.points[curve.points[k].point].selected;
  }
  if (path.rfind("bones[\"", 0) == 0) {
    const size_t end = path.find("\"]");
    const Bone *bone = end == std::string::npos ? nullptr : bone_find_by_name(layer, path.substr(7, end - 7));
    return bone && (bone->selected || bone->select_head || bone->select_tail);
  }
  return false;
}

bool key_filter_path_matches(const KeyFilter &filter, const std::string &path)
{
  if (filter.path.empty()) {
    return true;
  }
  if (filter.path.back() == '.') {
    return path.rfind(filter.path, 0) == 0;
  }
  return path == filter.path;
}

static std::vector<ChannelRef> layer_filtered_channels_all(Layer &layer, const KeyFilter &filter);

std::vector<ChannelRef> layer_filtered_channels(Layer &layer, const KeyFilter &filter)
{
  std::vector<ChannelRef> refs = layer_filtered_channels_all(layer, filter);
  if (filter.channels) {
    std::erase_if(refs, [&](const ChannelRef &r) {
      return !filter.channels->count(r.scalar ? static_cast<const void *>(r.scalar) : r.vector);
    });
  }
  return refs;
}

static std::vector<ChannelRef> layer_filtered_channels_all(Layer &layer, const KeyFilter &filter)
{
  std::vector<ChannelRef> refs;
  /* Pinned ones are asked of every layer every frame (the timeline's Pinned row): most have none. */
  if (filter.pinned_only) {
    bool any = false;
    layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) { any |= ch.pinned; });
    if (!any) {
      return refs;
    }
  }
  /* A drawing's points and curves are only needed when their kind is asked for. */
  const bool drawing = (filter.kinds & KEY_POINTS) &&
                       (filter.path.empty() || filter.path.rfind("points[", 0) == 0 ||
                        filter.path.rfind("curves[", 0) == 0);
  const std::vector<ChannelRef> channels = layer_channels(layer, drawing);
  for (const ChannelRef &ref : channels) {
    const KeyKind kind = channel_kind(ref.path);
    if (!(filter.kinds & kind) || !key_filter_path_matches(filter, ref.path)) {
      continue;
    }
    if (filter.pinned_only && !(ref.scalar ? ref.scalar->pinned : ref.vector->pinned)) {
      continue;
    }
    if (filter.selected_only && !channel_thing_selected(layer, ref.path, filter)) {
      continue;
    }
    if (filter.picked_bones_only && ref.path.rfind("bones[\"", 0) == 0 && !channel_thing_selected(layer, ref.path, filter)) {
      continue;
    }
    refs.push_back(ref);
  }
  if (filter.pinned_only) {
    return refs;
  }
  return refs;
}

/* Calls f(channel) for every channel of `layers` that passes the filter. */
template<typename F> static void filtered_for_each(const std::vector<Layer *> &layers, const KeyFilter &filter, F &&f);

bool layers_channel_among(const std::vector<Layer *> &layers, const KeyFilter &filter,
                          const std::set<const void *> &channels)
{
  bool found = false;
  if (!channels.empty()) {
    filtered_for_each(layers, filter, [&](auto &ch) { found = found || channels.count(&ch) > 0; });
  }
  return found;
}

template<typename F>
static void filtered_for_each_all(const std::vector<Layer *> &layers, const KeyFilter &filter, F &&f);

template<typename F> static void filtered_for_each(const std::vector<Layer *> &layers, const KeyFilter &filter, F &&f)
{
  if (!filter.channels) {
    filtered_for_each_all(layers, filter, f);
    return;
  }
  KeyFilter rest = filter;
  rest.channels.reset();
  filtered_for_each_all(layers, rest, [&](auto &ch) {
    if (filter.channels->count(&ch)) {
      f(ch);
    }
  });
}

template<typename F>
static void filtered_for_each_all(const std::vector<Layer *> &layers, const KeyFilter &filter, F &&f)
{
  for (Layer *layer : layers) {
    if (filter.everything()) {
      layer_for_each_channel<false>(*layer, [&](auto &ch, auto & /*value*/) { f(ch); });
      continue;
    }
    /* A drawing's channels are all points' (KEY_POINTS), so without a path they are gone through as they
     * are, not named one by one: the timeline asks this of every row each frame, and a big rig has
     * hundreds of thousands. The layer's own channels (a few) go by name. */
    if (filter.path.empty() && !filter.pinned_only && !layer->is_reference() && layer->id != CAMERA_LAYER_ID) {
      KeyFilter own = filter;
      own.kinds &= ~uint32_t(KEY_POINTS);
      if (own.kinds != 0) {
        for (const ChannelRef &ref : layer_filtered_channels(*layer, own)) {
          if (ref.scalar) {
            f(*ref.scalar);
          }
          else {
            f(*ref.vector);
          }
        }
      }
      if (!(filter.kinds & KEY_POINTS) ||
          (filter.selected_only && filter.point_layers && !filter.point_layers->contains(layer->id)))
      {
        continue;
      }
      VectorDrawing &drawing = layer->drawing;
      for (MeshPoint &p : drawing.points) {
        if (!filter.selected_only || p.selected) {
          f(p.pos_keys);
          f(p.radius_keys);
        }
      }
      for (Curve &curve : drawing.curves) {
        for (CurvePoint &cp : curve.points) {
          if (!filter.selected_only ||
              (cp.point >= 0 && cp.point < int(drawing.points.size()) && drawing.points[cp.point].selected))
          {
            f(cp.curvature_keys);
            f(cp.handle_in_keys);
            f(cp.handle_out_keys);
          }
        }
      }
      continue;
    }
    for (const ChannelRef &ref : layer_filtered_channels(*layer, filter)) {
      if (ref.scalar) {
        f(*ref.scalar);
      }
      else {
        f(*ref.vector);
      }
    }
  }
}

KeyShape interp_key_shape(Interp interp)
{
  switch (interp) {
    case Interp::Smooth:
      return KEY_SHAPE_SMOOTH;
    case Interp::Linear:
      return KEY_SHAPE_LINEAR;
    case Interp::Step:
      return KEY_SHAPE_STEP;
    case Interp::EaseIn:
    case Interp::EaseOut:
    case Interp::EaseInOut:
    case Interp::Bezier:
      return KEY_SHAPE_EASE;
    case Interp::Back:
    case Interp::Bounce:
    case Interp::Elastic:
      return KEY_SHAPE_BOUNCY;
    case Interp::Noisy:
    case Interp::Cycle:
    case Interp::Pose:
    case Interp::Custom:
      break;
  }
  return KEY_SHAPE_SPECIAL;
}

std::map<int, KeyFrameSummary> layers_key_summary(const std::vector<Layer *> &layers, const KeyFilter &filter)
{
  std::map<int, KeyFrameSummary> summary;
  filtered_for_each(layers, filter, [&](auto &ch) {
    for (const auto &key : ch.keys) {
      KeyFrameSummary &s = summary[key.frame];
      s.keys++;
      s.selected += key.selected ? 1 : 0;
      s.breakdowns += key.type == KeyType::Breakdown ? 1 : 0;
      s.fillers += key.filler ? 1 : 0;
      if (!ch.constant) {
        const KeyShape shape = interp_key_shape(key.interp);
        s.shape = s.shape_set && s.shape != shape ? KEY_SHAPE_MIXED : shape;
        s.shape_set = true;
      }
    }
  });
  return summary;
}

SelectedKeys layers_selected_keys(const std::vector<Layer *> &layers)
{
  SelectedKeys r;
  bool any_constant = false;
  KeySettings constant;
  for (Layer *layer : layers) {
    layer_for_each_channel<false>(*layer, [&](auto &ch, auto & /*value*/) {
      for (const auto &key : ch.keys) {
        if (!key.selected) {
          continue;
        }
        if (ch.constant) {
          /* Visibility: always Step; it only speaks when nothing else is selected. */
          any_constant = true;
          constant = key_settings(key);
          continue;
        }
        const KeySettings s = key_settings(key);
        if (r.count == 0) {
          r.first = s;
          r.first_timing = key.interp == Interp::Custom ? key.timing : TimingCurve{};
          /* The stretch arriving at it, after the key before's hold. */
          const size_t i = size_t(&key - ch.keys.data());
          if (i > 0) {
            const auto &before = ch.keys[i - 1];
            r.first_span = std::max(key.frame - std::min(before.frame + std::max(before.hold, 0), key.frame), 0);
          }
        }
        else {
          r.mixed |= s.interp != r.first.interp;
          r.mixed_ease |= s.ease != r.first.ease;
          r.mixed_type |= s.type != r.first.type;
          /* A few of the other curves, for the settings graph to draw behind the first's. */
          const auto curve_same = [&](const KeySettings &o) {
            return o.interp == s.interp && o.ease == s.ease && o.bezier == s.bezier && o.overshoot == s.overshoot;
          };
          if (!curve_same(r.first) && r.others.size() < 6 &&
              std::none_of(r.others.begin(), r.others.end(), curve_same))
          {
            r.others.push_back(s);
          }
        }
        r.count++;
      }
    });
  }
  if (r.count == 0 && any_constant) {
    r.first = constant;
    r.count = 1;
  }
  return r;
}

int layers_change_selected_keys(const std::vector<Layer *> &layers, const std::function<void(KeySettings &)> &change,
                                const TimingCurve *custom)
{
  int count = 0;
  for (Layer *layer : layers) {
    layer_for_each_channel(*layer, [&](auto &ch, auto & /*value*/) {
      for (auto &key : ch.keys) {
        if (!key.selected) {
          continue;
        }
        KeySettings s = key_settings(key);
        change(s);
        s.hold = std::max(0, s.hold);
        s.interval = std::max(1, s.interval);
        s.cycle_back = std::max(0, s.cycle_back);
        s.elastic_period = std::max(0.02f, s.elastic_period);
        if (ch.constant) {
          s.interp = Interp::Step;
        }
        key_settings_apply(key, s);
        if (custom && key.interp == Interp::Custom) {
          key.timing = *custom;
        }
        count++;
      }
    });
    /* An aligned point's partner handle key on the frame takes the same, or the two would turn apart. */
    for (Curve &c : layer->drawing.curves) {
      for (CurvePoint &p : c.points) {
        if (p.aligned) {
          aligned_handle_keys_match(p, [](const Key<float2> &ki, const Key<float2> &ko) {
            return ki.selected == ko.selected ? 0 : ki.selected ? 1 : -1;
          });
        }
      }
    }
  }
  return count;
}

InterpClipboard &interp_clipboard()
{
  static InterpClipboard clipboard;
  return clipboard;
}

std::string interp_clipboard_text()
{
  const InterpClipboard &c = interp_clipboard();
  if (!c.copied) {
    return {};
  }
  const Interp interp = c.settings.interp;
  if (interp == Interp::Custom) {
    return c.timing.points.empty() ? "Custom, even"
                                   : "Custom curve, " + std::to_string(c.timing.points.size()) + " points";
  }
  std::string text = interp_name(interp);
  if (interp == Interp::EaseInOut || interp == Interp::EaseIn || interp == Interp::EaseOut) {
    text += std::string(" (") + ease_name(c.settings.ease) + ")";
  }
  return text;
}

std::vector<bool *> layers_key_selected_flags(const std::vector<Layer *> &layers, int frame, const KeyFilter &filter)
{
  std::vector<bool *> out;
  filtered_for_each(layers, filter, [&](auto &ch) {
    for (auto &key : ch.keys) {
      if (key.frame == frame) {
        out.push_back(&key.selected);
      }
    }
  });
  return out;
}

std::set<int> layers_filtered_key_frames(const std::vector<Layer *> &layers, const KeyFilter &filter)
{
  std::set<int> out;
  filtered_for_each(layers, filter, [&](auto &ch) {
    for (const auto &key : ch.keys) {
      out.insert(key.frame);
    }
  });
  return out;
}

std::set<const void *> layers_filtered_channel_set(const std::vector<Layer *> &layers, const KeyFilter &filter)
{
  std::set<const void *> out;
  filtered_for_each(layers, filter, [&](auto &ch) { out.insert(&ch); });
  return out;
}

void layers_select_keys(const std::vector<Layer *> &layers, int first, int last, bool select, const KeyFilter &filter)
{
  filtered_for_each(layers, filter, [&](auto &ch) {
    for (auto &key : ch.keys) {
      if (key.frame >= first && key.frame <= last) {
        key.selected = select;
      }
    }
  });
}


bool layers_key_selected_outside(const std::vector<Layer *> &layers, const std::set<const void *> &channels)
{
  bool any = false;
  for (Layer *layer : layers) {
    layer_for_each_channel<false>(*layer, [&](auto &ch, auto & /*value*/) {
      if (any || ch.constant) {
        return;
      }
      const bool among = channels.count(&ch) > 0;
      for (const auto &key : ch.keys) {
        if (key.selected && (!among || key.frame == 0)) {
          any = true;
          return;
        }
      }
    });
    if (any) {
      break;
    }
  }
  return any;
}

void layers_deselect_keys(const std::vector<Layer *> &layers)
{
  for (Layer *layer : layers) {
    layer_for_each_channel(*layer, [&](auto &ch, auto & /*value*/) {
      for (auto &key : ch.keys) {
        key.selected = false;
      }
    });
  }
}

bool layers_any_key_selected(const std::vector<Layer *> &layers)
{
  for (const auto &[frame, s] : layers_key_summary(layers)) {
    if (s.selected > 0) {
      return true;
    }
  }
  return false;
}

void layers_move_selected_keys(const std::vector<Layer *> &layers, const std::function<int(int)> &to, bool ripple)
{
  for (Layer *layer : layers) {
    layer_for_each_channel(*layer, [&](auto &ch, auto & /*value*/) {
      using KeyT = std::decay_t<decltype(ch.keys.front())>;
      /* Ripple: the keys after the last one moved go along by as much, so the rest keeps its timing. */
      if (ripple) {
        int last = -1, shift = 0;
        for (const KeyT &key : ch.keys) {
          if (key.selected && key.frame != 0) {
            last = key.frame;
            shift = std::max(1, to(key.frame)) - key.frame;
          }
        }
        if (last >= 0 && shift != 0) {
          for (KeyT &key : ch.keys) {
            if (!key.selected && key.frame > last) {
              key.frame += shift;
            }
          }
        }
      }
      std::vector<KeyT> moved, kept;
      const auto dest = [&](const KeyT &key) {
        return key.selected && key.frame != 0 ? std::max(1, to(key.frame)) : key.frame;
      };
      for (size_t i = 0; i < ch.keys.size(); i++) {
        const KeyT &key = ch.keys[i];
        if (key.selected && key.frame != 0) {
          KeyT k = key;
          k.frame = dest(key);
          moved.push_back(k);
        }
        else {
          kept.push_back(key);
        }
      }
      if (moved.empty()) {
        return;
      }
      /* Keys moved onto the same frame: the last one wins; then they replace what was there. */
      std::map<int, KeyT> landed;
      for (const KeyT &k : moved) {
        landed[k.frame] = k;
      }
      std::erase_if(kept, [&](const KeyT &other) { return landed.count(other.frame) > 0; });
      for (const auto &[frame, k] : landed) {
        kept.push_back(k);
      }
      std::sort(kept.begin(), kept.end(), [](const KeyT &a, const KeyT &b) { return a.frame < b.frame; });
      ch.keys = std::move(kept);
    });
  }
}

/* --- Time Together ------------------------------------------------------------------------ */

namespace {

/* A channel of either kind. */
struct AnyChannel {
  Channel<float> *s = nullptr;
  Channel<float2> *v = nullptr;
  const void *id() const { return s ? static_cast<const void *>(s) : static_cast<const void *>(v); }
};

template<typename F> void any_visit(const AnyChannel &c, F &&f)
{
  if (c.s) {
    f(*c.s);
  }
  else {
    f(*c.v);
  }
}

template<typename T> void any_add(std::vector<AnyChannel> &out, Channel<T> &ch)
{
  if constexpr (std::is_same_v<T, float>) {
    out.push_back({&ch, nullptr});
  }
  else {
    out.push_back({nullptr, &ch});
  }
}

void layers_walk(std::vector<Layer> &layers, const std::function<void(Layer &)> &f)
{
  for (Layer &l : layers) {
    f(l);
    layers_walk(l.children, f);
  }
}

/* An edited stretch of a channel and how its frames go: from `lo` to `hi` (old frames), through `map` (old frame to
 * new, in order, the ends included); past `hi`, keys move by `after` when `open` (Ripple, or the channel's last key
 * moved). */
struct Stretch {
  int lo = 0, hi = 0;
  std::vector<std::pair<int, int>> map;
  bool open = false;
  int after = 0;
  bool operator==(const Stretch &) const = default;
  float to(int f) const
  {
    if (f > hi) {
      return float(f + (open ? after : 0));
    }
    for (size_t i = 1; i < map.size(); i++) {
      const auto [a, na] = map[i - 1];
      const auto [b, nb] = map[i];
      if (f <= b) {
        return b == a ? float(nb) : float(na) + float(nb - na) * float(f - a) / float(b - a);
      }
    }
    return float(map.back().second);
  }
};

/* The stretches a channel's selected keys edit when they move to `to(frame)`: from the unmoved key before each run of
 * selected keys to the unmoved key after it (or the run's own end key where there is none, or with Ripple on the
 * last run). */
template<typename KeyT>
std::vector<Stretch> edited_stretches(const std::vector<KeyT> &keys, const std::function<int(int)> &to, bool ripple)
{
  std::vector<Stretch> out;
  const auto moves = [&](const KeyT &k) { return k.selected && k.frame != 0; };
  const auto dest = [&](const KeyT &k) { return moves(k) ? std::max(1, to(k.frame)) : k.frame; };
  size_t last_moved = keys.size();
  for (size_t i = 0; i < keys.size(); i++) {
    if (moves(keys[i])) {
      last_moved = i;
    }
  }
  for (size_t i = 0; i < keys.size();) {
    if (!moves(keys[i])) {
      i++;
      continue;
    }
    size_t j = i;
    while (j + 1 < keys.size() && moves(keys[j + 1])) {
      j++;
    }
    Stretch st;
    if (i > 0) {
      st.lo = keys[i - 1].frame;
      st.map.push_back({st.lo, st.lo});
    }
    else {
      st.lo = keys[i].frame;
    }
    for (size_t k = i; k <= j; k++) {
      st.map.push_back({keys[k].frame, dest(keys[k])});
    }
    const bool rippled = ripple && j == last_moved;
    if (j + 1 < keys.size() && !rippled) {
      st.hi = keys[j + 1].frame;
      st.map.push_back({st.hi, st.hi});
    }
    else {
      st.hi = keys[j].frame;
      st.open = true;
      st.after = dest(keys[j]) - keys[j].frame;
    }
    if (st.hi > st.lo) {
      out.push_back(std::move(st));
    }
    i = j + 1;
  }
  return out;
}

/* Whether the channel is keyed on both ends of the stretch: it is timed with it. */
template<typename Ch> bool stretch_linked(const Ch &ch, const Stretch &st)
{
  return ch.keys.size() >= 2 && ch.key_at(st.lo) && ch.key_at(st.hi);
}

/* Moves the channel's keys through the stretches (each key by the first it falls in), to whole frames, keeping each a
 * frame apart from the next (keys still landing together: the later wins). */
template<typename Ch> void stretches_apply(Ch &ch, const std::vector<const Stretch *> &sts)
{
  using KeyT = std::decay_t<decltype(ch.keys.front())>;
  const size_t n = ch.keys.size();
  std::vector<int> to(n);
  std::vector<bool> mapped(n, false);
  for (size_t i = 0; i < n; i++) {
    const int f = ch.keys[i].frame;
    to[i] = f;
    if (f == 0) {
      continue;
    }
    for (const Stretch *st : sts) {
      if (f > st->lo && (f <= st->hi || st->open)) {
        to[i] = std::max(1, int(std::lround(st->to(f))));
        mapped[i] = true;
        break;
      }
    }
  }
  /* Rounding can land two on one frame: forward, then back from the unmoved keys. */
  for (size_t i = 1; i < n; i++) {
    if (mapped[i] && to[i] <= to[i - 1]) {
      to[i] = to[i - 1] + 1;
    }
  }
  for (size_t i = n - 1; i-- > 0;) {
    if (mapped[i] && to[i] >= to[i + 1] && to[i + 1] - 1 > (i > 0 ? to[i - 1] : -1)) {
      to[i] = to[i + 1] - 1;
    }
  }
  std::map<int, KeyT> landed;
  for (size_t i = 0; i < n; i++) {
    KeyT k = ch.keys[i];
    k.frame = to[i];
    landed[k.frame] = std::move(k);
  }
  ch.keys.clear();
  for (auto &[f, k] : landed) {
    ch.keys.push_back(std::move(k));
  }
}

bool any_selected(const AnyChannel &c)
{
  bool sel = false;
  any_visit(c, [&](auto &ch) {
    for (const auto &k : ch.keys) {
      sel = sel || (k.selected && k.frame != 0);
    }
  });
  return sel;
}

/* The channels Time Together can link (see time_together_candidates). */
std::vector<AnyChannel> together_candidates(Document &doc)
{
  std::vector<AnyChannel> out;
  layers_walk(doc.layers, [&](Layer &l) {
    if (!l.selected) {
      return;
    }
    any_add(out, l.position_keys);
    any_add(out, l.rotation_keys);
    any_add(out, l.scale_keys);
    any_add(out, l.shear_keys);
    any_add(out, l.opacity_keys);
    for (Bone &b : l.bones) {
      if (b.selected) {
        any_add(out, b.position_keys);
        any_add(out, b.angle_keys);
        any_add(out, b.scale_keys);
        any_add(out, b.depth_keys);
        bone_curve_channels(b, [&](std::string_view, float &, Channel<float> &keys) { any_add(out, keys); });
      }
    }
    if (l.has_drawing() && !l.is_reference()) {
      drawing_shape_channels(l.drawing, [&](auto &ch, auto & /*value*/) { any_add(out, ch); });
    }
  });
  return out;
}

}  // namespace

std::vector<const void *> time_together_candidates(Document &doc)
{
  std::vector<const void *> ids;
  for (const AnyChannel &c : together_candidates(doc)) {
    ids.push_back(c.id());
  }
  return ids;
}

/* The stretches the selected keys of `layers` edit, moved by `to`. */
static std::vector<Stretch> selected_stretches(const std::vector<Layer *> &layers, const std::function<int(int)> &to,
                                               bool ripple)
{
  std::vector<Stretch> all;
  for (Layer *layer : layers) {
    layer_for_each_channel<false>(*layer, [&](auto &ch, auto & /*value*/) {
      for (Stretch &st : edited_stretches(ch.keys, to, ripple)) {
        if (std::find(all.begin(), all.end(), st) == all.end()) {
          all.push_back(std::move(st));
        }
      }
    });
  }
  return all;
}

std::set<const void *> time_together_linked(Document &doc, const std::vector<Layer *> &layers)
{
  std::set<const void *> out;
  if (!doc.time_together) {
    return out;
  }
  const std::vector<Stretch> sts = selected_stretches(layers, [](int f) { return f; }, false);
  if (sts.empty()) {
    return out;
  }
  for (const AnyChannel &c : together_candidates(doc)) {
    if (any_selected(c)) {
      continue;
    }
    any_visit(c, [&](auto &ch) {
      for (const Stretch &st : sts) {
        if (stretch_linked(ch, st)) {
          out.insert(c.id());
          break;
        }
      }
    });
  }
  return out;
}

/* Key Together: a key moved alone takes its frame's keys on every layer of its group along (picked with it), the group
 * staying keyed as one as its folded row moves them; else keys_together_sync would read the frame it left as deleted
 * from them all. Returns `layers` and those groups' layers. */
static std::vector<Layer *> together_picks_widen(Document &doc, const std::vector<Layer *> &layers)
{
  std::vector<Layer *> out = layers;
  std::vector<Layer *> groups;
  for (Layer *layer : layers) {
    Layer *group = key_together_group(doc, layer->id);
    if (group && std::find(groups.begin(), groups.end(), group) == groups.end()) {
      groups.push_back(group);
    }
  }
  for (Layer *group : groups) {
    std::set<int> frames;
    together_channels(doc, *group, [&](auto &ch, auto & /*value*/, const void * /*unit*/) {
      for (const auto &k : ch.keys) {
        if (k.selected) {
          frames.insert(k.frame);
        }
      }
    });
    if (frames.empty()) {
      continue;
    }
    together_channels(doc, *group, [&](auto &ch, auto & /*value*/, const void * /*unit*/) {
      for (auto &k : ch.keys) {
        k.selected = k.selected || frames.count(k.frame) > 0;
      }
    });
    for (Layer *l : key_together_layers(doc, *group)) {
      if (std::find(out.begin(), out.end(), l) == out.end()) {
        out.push_back(l);
      }
    }
  }
  return out;
}

/* How far a move must go back the other way for no selected key to land on or before the setup frame: the keys
 * then stop there together, their spacing kept. (Each held at frame 1 on its own, two landed on one frame and one
 * was lost.) `setup`: the setup frame's own selected keys count (copies of them move; the keys themselves never). */
static int keys_lift(const std::vector<Layer *> &layers, const std::function<int(int)> &to, bool setup)
{
  int lift = 0;
  for (Layer *layer : layers) {
    layer_for_each_channel<false>(*layer, [&](auto &ch, auto & /*value*/) {
      for (const auto &k : ch.keys) {
        if (k.selected && (setup || k.frame != 0)) {
          lift = std::max(lift, 1 - to(k.frame));
        }
      }
    });
  }
  return lift;
}

/* How far a move must go back for no selected key to land past the last frame there is (1048574, the playhead's
 * last): the keys stop there together, as at frame 1. */
static int keys_drop(const std::vector<Layer *> &layers, const std::function<int(int)> &to, bool setup)
{
  int drop = 0;
  for (Layer *layer : layers) {
    layer_for_each_channel<false>(*layer, [&](auto &ch, auto & /*value*/) {
      for (const auto &k : ch.keys) {
        if (k.selected && (setup || k.frame != 0)) {
          drop = std::max(drop, to(k.frame) - KEY_FRAME_LAST);
        }
      }
    });
  }
  return drop;
}

int keys_duplicate_offset(const std::vector<Layer *> &layers, int offset_asked)
{
  /* An offset past every frame there is would wrap round the int (INT_MAX put the copies on the left). */
  const int offset = std::clamp(offset_asked, -KEY_FRAME_LAST, KEY_FRAME_LAST);
  const int lifted = offset + keys_lift(layers, [offset](int f) { return f + offset; }, true);
  return lifted - keys_drop(layers, [lifted](int f) { return f + lifted; }, true);
}

int keys_move_selected(Document &doc, const std::vector<Layer *> &layers_picked, const std::function<int(int)> &to_asked,
                       bool ripple, bool together)
{
  const std::vector<Layer *> layers = together_picks_widen(doc, layers_picked);
  const int lift = keys_lift(layers, to_asked, false);
  const std::function<int(int)> lifted = lift == 0 ? to_asked : [&to_asked, lift](int f) { return to_asked(f) + lift; };
  const int drop = keys_drop(layers, lifted, false);
  /* Spread past every frame there is (scaled by a million): they'd pile up on the ends, keys lost. */
  if (drop > 0 && lift > 0) {
    return 0;
  }
  const std::function<int(int)> to = drop == 0 ? lifted : [&lifted, drop](int f) { return lifted(f) - drop; };
  std::vector<Stretch> sts;
  std::vector<AnyChannel> linked;
  if (together && doc.time_together) {
    sts = selected_stretches(layers, to, ripple);
    if (!sts.empty()) {
      for (const AnyChannel &c : together_candidates(doc)) {
        if (!any_selected(c)) {
          linked.push_back(c);
        }
      }
    }
  }
  layers_move_selected_keys(layers, to, ripple);
  int followed = 0;
  for (const AnyChannel &c : linked) {
    any_visit(c, [&](auto &ch) {
      std::vector<const Stretch *> mine;
      for (const Stretch &st : sts) {
        if (stretch_linked(ch, st)) {
          mine.push_back(&st);
        }
      }
      if (!mine.empty()) {
        stretches_apply(ch, mine);
        followed++;
      }
    });
  }
  return followed;
}

std::pair<int, int> keys_span_frames_add(Document &doc, Layer &layer, int frame, int amount, bool together)
{
  if (amount > 0) {
    /* The keys after the stretch go later by as much: never past the last frame there is (they stop there together, as
     * moved keys do). */
    int last = 0;
    const auto latest = [&](auto &ch) {
      for (const auto &k : ch.keys) {
        last = std::max(last, k.frame);
      }
    };
    layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) { latest(ch); });
    if (together && doc.time_together) {
      for (const AnyChannel &c : together_candidates(doc)) {
        any_visit(c, latest);
      }
    }
    amount = std::min(amount, KEY_FRAME_LAST - last);
  }
  if (amount == 0) {
    return {0, 0};
  }
  std::vector<Stretch> sts;
  std::set<const void *> done;
  int changed = 0;
  layer_for_each_channel<false>(layer, [&](auto &ch, auto & /*value*/) {
    const auto &keys = ch.keys;
    for (size_t i = 0; i + 1 < keys.size(); i++) {
      const int a = keys[i].frame, b = keys[i + 1].frame;
      if (a <= frame && frame < b) {
        if (b - a + amount < 1) {
          return;
        }
        Stretch st;
        st.lo = a;
        st.hi = b;
        st.map = {{a, a}, {b, b + amount}};
        st.open = true;
        st.after = amount;
        stretches_apply(ch, {&st});
        done.insert(static_cast<const void *>(&ch));
        changed++;
        if (std::find(sts.begin(), sts.end(), st) == sts.end()) {
          sts.push_back(std::move(st));
        }
        return;
      }
    }
  });
  int followed = 0;
  if (together && doc.time_together && !sts.empty()) {
    for (const AnyChannel &c : together_candidates(doc)) {
      if (done.count(c.id())) {
        continue;
      }
      any_visit(c, [&](auto &ch) {
        for (const Stretch &st : sts) {
          if (stretch_linked(ch, st)) {
            stretches_apply(ch, {&st});
            followed++;
            return;
          }
        }
      });
    }
  }
  return {changed, followed};
}

std::pair<int, int> keys_match_timing(Document &doc, Layer &source)
{
  std::set<int> frames;
  std::set<const void *> own;
  layer_for_each_channel<false>(source, [&](auto &ch, auto & /*value*/) {
    own.insert(static_cast<const void *>(&ch));
    for (const auto &k : ch.keys) {
      frames.insert(k.frame);
    }
  });
  if (frames.size() < 2) {
    return {0, 0};
  }
  const std::vector<int> from(frames.begin(), frames.end());
  const float f0 = float(from.front()), span = float(from.back() - from.front());
  int matched = 0, merged = 0;
  for (const AnyChannel &c : together_candidates(doc)) {
    if (own.count(c.id())) {
      continue;
    }
    any_visit(c, [&](auto &ch) {
      using KeyT = std::decay_t<decltype(ch.keys.front())>;
      if (ch.keys.size() < 2) {
        return;
      }
      /* The source's frames stretched over this channel's first to last key. */
      const int t0 = ch.keys.front().frame, t1 = ch.keys.back().frame;
      std::vector<int> to;
      for (const int f : from) {
        const int g = int(std::lround(float(t0) + (float(f) - f0) / span * float(t1 - t0)));
        if (to.empty() || g != to.back()) {
          to.push_back(g);
        }
      }
      std::vector<int> now;
      for (const auto &k : ch.keys) {
        now.push_back(k.frame);
      }
      if (now == to) {
        return;
      }
      const auto old = ch;
      std::map<int, KeyT> placed;
      std::map<int, int> distance;
      if (ch.keys.size() == to.size()) {
        /* As many keys as frames: each goes to its frame, pose and timing kept. */
        for (size_t i = 0; i < to.size(); i++) {
          KeyT k = ch.keys[i];
          k.frame = to[i];
          placed[k.frame] = k;
        }
      }
      else {
        /* Each key to the nearest frame (the nearest key wins a frame two reach)... */
        for (const KeyT &k : ch.keys) {
          int best = to.front();
          for (const int g : to) {
            if (std::abs(g - k.frame) < std::abs(best - k.frame)) {
              best = g;
            }
          }
          const int d = std::abs(best - k.frame);
          if (placed.count(best) && distance[best] <= d) {
            merged++;
            continue;
          }
          if (placed.count(best)) {
            merged++;
          }
          KeyT moved = k;
          moved.frame = best;
          placed[best] = moved;
          distance[best] = d;
        }
        /* ...and the frames no key reached keyed with what the channel held there. */
        for (const int g : to) {
          if (!placed.count(g)) {
            KeyT k = ch.keys.front();
            k.frame = g;
            k.value = old.evaluate(g);
            k.selected = false;
            k.filler = false;
            k.filler_inside = false;
            placed[g] = k;
          }
        }
      }
      ch.keys.clear();
      for (auto &[f, k] : placed) {
        ch.keys.push_back(k);
      }
      matched++;
    });
  }
  return {matched, merged};
}

int keys_offset_clamp(const std::vector<Layer *> &layers, int offset, bool ripple)
{
  int lo = INT32_MIN, hi = INT32_MAX;
  for (Layer *layer : layers) {
    layer_for_each_channel<false>(*layer, [&](auto &ch, auto & /*value*/) {
      const auto &keys = ch.keys;
      size_t last = keys.size();
      for (size_t i = 0; i < keys.size(); i++) {
        if (keys[i].selected && keys[i].frame != 0) {
          last = i;
        }
      }
      for (size_t i = 0; i < keys.size(); i++) {
        if (!keys[i].selected || keys[i].frame == 0) {
          continue;
        }
        /* Never onto frame 0 or past the unselected key before; the one after too, unless it goes along. */
        const int before = i > 0 && !keys[i - 1].selected ? keys[i - 1].frame : (i == 0 ? 0 : INT32_MIN);
        if (before != INT32_MIN) {
          lo = std::max(lo, before + 1 - keys[i].frame);
        }
        lo = std::max(lo, 1 - keys[i].frame);
        if (i + 1 < keys.size() && !keys[i + 1].selected && !(ripple && i == last)) {
          hi = std::min(hi, keys[i + 1].frame - 1 - keys[i].frame);
        }
      }
    });
  }
  if (lo > hi) {
    return 0;
  }
  return std::clamp(offset, lo, hi);
}

TimingSnapshot time_together_timing_snapshot(Document &doc)
{
  TimingSnapshot snap;
  layers_walk(doc.layers, [&](Layer &l) {
    layer_for_each_channel<false>(l, [&](auto &ch, auto & /*value*/) {
      if (ch.keys.empty()) {
        return;
      }
      auto &keys = snap.keys[static_cast<const void *>(&ch)];
      for (const auto &k : ch.keys) {
        keys.push_back({k.frame, key_sig(k, false)});
      }
    });
  });
  return snap;
}

void TimeTogetherEdit::start(Document &doc)
{
  on = doc.time_together;
  if (on) {
    before = time_together_timing_snapshot(doc);
  }
}

int TimeTogetherEdit::finish(Document &doc)
{
  const int followed = on ? time_together_timing_follow(doc, before) : 0;
  if (followed > 0) {
    /* The channels retimed show their new places on the frame shown, not only once the frame changes. */
    animation_evaluate(doc, doc.frame_current);
  }
  on = false;
  before = TimingSnapshot();
  return followed;
}

/* A channel's key whose timing changed since `before`, with the frames of the keys either side (-1: none). */
struct TimingEdit {
  int frame, prev, next;
  AnyChannel from;
};

int time_together_timing_follow(Document &doc, const TimingSnapshot &before)
{
  std::vector<TimingEdit> edits;
  std::set<const void *> edited;
  layers_walk(doc.layers, [&](Layer &l) {
    layer_for_each_channel<false>(l, [&](auto &ch, auto & /*value*/) {
      const auto it = before.keys.find(static_cast<const void *>(&ch));
      if (it == before.keys.end()) {
        return;
      }
      for (size_t i = 0; i < ch.keys.size(); i++) {
        const auto &k = ch.keys[i];
        const auto was = std::find_if(it->second.begin(), it->second.end(),
                                      [&](const auto &p) { return p.first == k.frame; });
        if (was == it->second.end() || was->second == key_sig(k, false)) {
          continue;
        }
        AnyChannel from;
        if constexpr (std::is_same_v<std::decay_t<decltype(ch)>, Channel<float>>) {
          from.s = &ch;
        }
        else {
          from.v = &ch;
        }
        edits.push_back({k.frame, i > 0 ? ch.keys[i - 1].frame : -1,
                         i + 1 < ch.keys.size() ? ch.keys[i + 1].frame : -1, from});
        edited.insert(static_cast<const void *>(&ch));
      }
    });
  });
  if (edits.empty()) {
    return 0;
  }
  int followed = 0;
  for (const AnyChannel &c : together_candidates(doc)) {
    if (edited.count(c.id())) {
      continue;
    }
    bool changed = false;
    any_visit(c, [&](auto &ch) {
      for (const TimingEdit &e : edits) {
        auto *k = ch.key_at(e.frame);
        /* Keyed on the same frames around it, and nothing between: the same stretches, timed alike. */
        if (!k || (e.prev >= 0 && !ch.key_at(e.prev)) || (e.next >= 0 && !ch.key_at(e.next))) {
          continue;
        }
        const int lo = e.prev >= 0 ? e.prev : e.frame, hi = e.next >= 0 ? e.next : e.frame;
        if (std::any_of(ch.keys.begin(), ch.keys.end(),
                        [&](const auto &o) { return o.frame > lo && o.frame < hi && o.frame != e.frame; }))
        {
          continue;
        }
        KeyTiming t;
        any_visit(e.from, [&](auto &src) { t = key_timing(*src.key_at(e.frame)); });
        if (key_timing(*k) != t) {
          if constexpr (std::is_same_v<std::decay_t<decltype(ch)>, Channel<float2>>) {
            /* A straight stretch keeps its shape as Custom (which runs along Smooth's curve while Auto), as the lead's
             * did when it became Custom (stretch_make_custom): only the timing follows. */
            if (t.interp == Interp::Custom && !interp_path_smooth(k->interp)) {
              const size_t i = size_t(k - ch.keys.data());
              if (i > 0) {
                key_path_handles_freeze(ch.keys, i - 1);
              }
              key_path_handles_freeze(ch.keys, i);
              k = ch.key_at(e.frame);
            }
          }
          key_timing_set(*k, t);
          changed = true;
        }
      }
    });
    followed += changed ? 1 : 0;
  }
  return followed;
}

/* Each channel of the timeline being edited: in an action its bone layer's, on the mainline every layer's, the
 * Simulation's and the camera's. */
template<typename F> static void timeline_for_each_channel(Document &doc, F &&f)
{
  if (!doc.action.empty()) {
    if (Layer *owner = layer_find(doc, doc.action_layer)) {
      owner_for_each_channel(*owner, f);
    }
    return;
  }
  layers_for_each_channel(doc.layers, f);
  layer_for_each_channel(doc.simulation, f);
  layer_for_each_channel(document_camera(doc), f);
}

int timeline_clear(Document &doc, bool count_only)
{
  int count = 0;
  const auto clear = [&](auto &ch, auto &value) {
    const size_t before = ch.keys.size();
    if (count_only) {
      count += int(std::count_if(ch.keys.begin(), ch.keys.end(), [](const auto &k) { return k.frame != 0; }));
      return;
    }
    std::erase_if(ch.keys, [](const auto &key) { return key.frame != 0; });
    count += int(before - ch.keys.size());
    if (ch.keys.size() != before) {
      drop_lone_setup_key(ch, value);
    }
  };
  timeline_for_each_channel(doc, clear);
  return count;
}

std::string timeline_edited_name(const Document &doc)
{
  return doc.action.empty() ? std::string("Mainline") : doc.action;
}

int layers_delete_selected_keys(const std::vector<Layer *> &layers)
{
  int removed = 0;
  for (Layer *layer : layers) {
    layer_for_each_channel(*layer, [&](auto &ch, auto &value) {
      const size_t before = ch.keys.size();
      const KeyEnds ends = key_ends(ch);
      std::erase_if(ch.keys, [](const auto &key) { return key.selected && key.frame != 0; });
      removed += int(before - ch.keys.size());
      if (ch.keys.size() != before) {
        keys_ends_release(ch, ends);
        drop_lone_setup_key(ch, value);
      }
    });
  }
  return removed;
}

void layers_duplicate_selected_keys(const std::vector<Layer *> &layers, int offset_asked)
{
  const int offset = keys_duplicate_offset(layers, offset_asked);
  for (Layer *layer : layers) {
    layer_for_each_channel(*layer, [&](auto &ch, auto & /*value*/) {
      using KeyT = std::decay_t<decltype(ch.keys.front())>;
      std::vector<KeyT> copies;
      for (KeyT &key : ch.keys) {
        if (key.selected) {
          KeyT copy = key;
          copy.frame = std::max(1, key.frame + offset);
          copies.push_back(copy);
          key.selected = false;
        }
      }
      for (const KeyT &copy : copies) {
        std::erase_if(ch.keys, [&](const KeyT &k) { return k.frame == copy.frame; });
      }
      for (const KeyT &copy : copies) {
        if (!ch.key_at(copy.frame)) {
          ch.keys.push_back(copy);
        }
      }
      std::sort(ch.keys.begin(), ch.keys.end(), [](const KeyT &a, const KeyT &b) { return a.frame < b.frame; });
    });
  }
}

std::vector<std::pair<int, int>> layers_hold_spans(const std::vector<Layer *> &layers, const KeyFilter &filter)
{
  std::vector<int> frames;
  std::map<int, size_t> index;
  for (const auto &[frame, s] : layers_key_summary(layers, filter)) {
    index[frame] = frames.size();
    frames.push_back(frame);
  }
  if (frames.size() < 2) {
    return {};
  }
  /* For each gap between neighbouring keyed frames: whether every channel keyed on either side has the
   * same value on both (`holds`), and whether any does (`any`). Each channel's keys are gone through
   * once (a recording keys every frame, and the timeline asks for every row on every redraw). */
  std::vector<char> holds(frames.size() - 1, 1), any(frames.size() - 1, 0);
  filtered_for_each(layers, filter, [&](auto &ch) {
    const auto &keys = ch.keys;
    for (size_t j = 0; j < keys.size(); j++) {
      const auto it = index.find(keys[j].frame);
      if (it == index.end()) {
        continue;
      }
      const size_t at = it->second;
      /* The gap after it: the channel's next key must be on the next keyed frame, holding the value. */
      if (at + 1 < frames.size()) {
        if (j + 1 < keys.size() && keys[j + 1].frame == frames[at + 1]) {
          if (keys[j + 1].value == keys[j].value) {
            any[at] = 1;
          }
          else {
            holds[at] = 0;
          }
        }
        else {
          holds[at] = 0;
        }
      }
      /* The gap before it, unless the key before already spoke for it. */
      if (at > 0 && !(j > 0 && keys[j - 1].frame == frames[at - 1])) {
        holds[at - 1] = 0;
      }
    }
  });
  std::vector<std::pair<int, int>> spans;
  for (size_t i = 0; i + 1 < frames.size(); i++) {
    if (holds[i] && any[i]) {
      spans.push_back({frames[i], frames[i + 1]});
    }
  }
  return spans;
}

/* --- Ignore Bones ------------------------------------------------------------------------------ */

bool layer_bones_move_points(const Document &doc, const Layer &layer)
{
  (void)doc;
  if (!layer.has_drawing() || layer.is_reference()) {
    return false;
  }
  return layer.points_follow_bone() ||
         std::any_of(layer.modifiers.begin(), layer.modifiers.end(),
                     [](const Modifier &m) { return m.type == ModifierType::Armature; });
}

int keys_ignore_bones(Document &doc, const Document &source, const std::vector<std::pair<uint64_t, uint64_t>> &layers,
                      const std::vector<std::pair<int, int>> &frames)
{
  int changed = 0;
  /* Each frame worked out on a copy (the document keeps the frame it shows). */
  std::map<int, Document> sources, results;
  const auto at = [](std::map<int, Document> &cache, const Document &from, int frame) -> Document & {
    auto it = cache.find(frame);
    if (it == cache.end()) {
      it = cache.emplace(frame, from).first;
      it->second.frame_current = frame;
      animation_evaluate(it->second, frame);
    }
    return it->second;
  };
  for (const auto &[from, to] : frames) {
    if (to <= 0 || from < 0) {
      continue;
    }
    for (const auto &[id, source_id] : layers) {
      Layer *layer = layer_find(doc, id);
      if (!layer || !layer_bones_move_points(doc, *layer)) {
        continue;
      }
      const Document &was = at(sources, source, from);
      const Document &now = at(results, doc, to);
      const Layer *before = layer_find(was, source_id);
      const Layer *after = layer_find(now, id);
      if (!before || !after || before->is_reference() ||
          before->drawing.points.size() != layer->drawing.points.size() ||
          before->drawing.curves.size() != layer->drawing.curves.size())
      {
        continue;
      }
      std::vector<Transform2D> skins_before = layer_point_skins(was, *before);
      std::vector<Transform2D> skins_after = layer_point_skins(now, *after);
      skins_before.resize(layer->drawing.points.size());
      skins_after.resize(layer->drawing.points.size());
      /* From where a point is stored on the new frame to where it showed on the source frame, through
       * the bones of each: null where the new frame's bones flatten it. */
      const auto back = [&](int point, Transform2D *r) {
        const Transform2D &t = skins_after[size_t(point)];
        if (std::fabs(t.a * t.d - t.b * t.c) < 1e-8f) {
          return false;
        }
        *r = t.inverted() * skins_before[size_t(point)];
        return true;
      };
      for (size_t i = 0; i < layer->drawing.points.size(); i++) {
        MeshPoint &p = layer->drawing.points[i];
        Key<float2> *key = p.pos_keys.key_at(to);
        Transform2D t;
        if (!key || !key->selected || p.detail.level > 0 || !back(int(i), &t)) {
          continue;
        }
        const MeshPoint &shown = after->drawing.points[i];
        const float2 pos = t.apply(before->drawing.points[i].pos);
        key->value = pos - shown.setup_pos - shown.pos_keys.from_action_bones;
        changed++;
      }
      for (size_t c = 0; c < layer->drawing.curves.size(); c++) {
        Curve &curve = layer->drawing.curves[c];
        const Curve &curve_before = before->drawing.curves[c];
        const Curve &curve_after = after->drawing.curves[c];
        if (curve.points.size() != curve_before.points.size() || curve.points.size() != curve_after.points.size()) {
          continue;
        }
        for (size_t j = 0; j < curve.points.size(); j++) {
          CurvePoint &cp = curve.points[j];
          Transform2D t;
          /* A handle the curve works out for itself follows the points it is worked out from. */
          if (!curve_before.points[j].handles_set || layer->drawing.points[size_t(cp.point)].detail.level > 0 ||
              !back(cp.point, &t))
          {
            continue;
          }
          for (const bool in : {true, false}) {
            Key<float2> *key = (in ? cp.handle_in_keys : cp.handle_out_keys).key_at(to);
            if (!key || !key->selected) {
              continue;
            }
            const CurvePoint &shown = curve_after.points[j];
            const float2 handle = t.apply_vector(in ? curve_before.points[j].handle_in : curve_before.points[j].handle_out);
            /* A handle's key is its turn and stretch from the setup (data/vector.hh). */
            key->value = handle_change(in ? shown.setup_in : shown.setup_out, handle, key->value.x, in) -
                         (in ? shown.handle_in_keys.from_action_bones : shown.handle_out_keys.from_action_bones);
            changed++;
          }
        }
      }
    }
  }
  return changed;
}

int keys_keep_place(Document &doc, const Document &before, const std::vector<uint64_t> &layers,
                    const std::vector<std::pair<int, int>> &frames)
{
  int changed = 0;
  std::set<int> done;
  for (const auto &[from, to] : frames) {
    (void)from;
    if (to <= 0 || !done.insert(to).second) {
      continue;
    }
    Document was = before, now = doc;
    was.frame_current = now.frame_current = to;
    animation_evaluate(was, to);
    animation_evaluate(now, to);
    /* The copied points, where each shows now and showed before (document space). */
    struct Copied {
      Layer *layer;
      size_t point;
      Transform2D to_shown;
    };
    std::vector<Copied> copied;
    float2 centre_was, centre_now;
    for (const uint64_t id : layers) {
      Layer *layer = layer_find(doc, id);
      const Layer *layer_was = layer_find(was, id);
      const Layer *layer_now = layer_find(now, id);
      if (!layer || !layer_was || !layer_now || layer->is_reference() ||
          layer_was->drawing.points.size() != layer->drawing.points.size())
      {
        continue;
      }
      std::vector<Transform2D> skins_was = layer_point_skins(was, *layer_was);
      std::vector<Transform2D> skins_now = layer_point_skins(now, *layer_now);
      skins_was.resize(layer->drawing.points.size());
      skins_now.resize(layer->drawing.points.size());
      const Transform2D world_was = layer_world_transform(was, id), world_now = layer_world_transform(now, id);
      for (size_t i = 0; i < layer->drawing.points.size(); i++) {
        const MeshPoint &p = layer->drawing.points[i];
        const Key<float2> *key = p.pos_keys.key_at(to);
        if (!key || !key->selected || p.detail.level > 0) {
          continue;
        }
        const Transform2D to_shown = world_now * skins_now[i];
        centre_was += (world_was * skins_was[i]).apply(layer_was->drawing.points[i].pos);
        centre_now += to_shown.apply(layer_now->drawing.points[i].pos);
        copied.push_back({layer, i, to_shown});
      }
    }
    if (copied.empty()) {
      continue;
    }
    const float2 shift = (centre_was - centre_now) / float(copied.size());
    for (const Copied &c : copied) {
      const MeshPoint &shown = layer_find(now, c.layer->id)->drawing.points[c.point];
      const float2 at = c.to_shown.apply(shown.pos) + shift;
      const Transform2D back = c.to_shown.inverted();
      Key<float2> *key = c.layer->drawing.points[c.point].pos_keys.key_at(to);
      key->value = back.apply(at) - shown.setup_pos - shown.pos_keys.from_action_bones;
      changed++;
    }
  }
  return changed;
}

/* --- Copy and paste keys ----------------------------------------------------------------------- */

namespace {

/* The number in `path` after `prefix` (which starts it, at `at`), up to a ']'; -1 if there isn't one. */
static int path_index(const std::string &path, const std::string &prefix, size_t at = 0)
{
  if (path.compare(at, prefix.size(), prefix) != 0) {
    return -1;
  }
  int n = -1;
  const char *begin = path.data() + at + prefix.size(), *end = path.data() + path.size();
  const auto [ptr, ec] = std::from_chars(begin, end, n);
  return ec == std::errc() && ptr < end && *ptr == ']' ? n : -1;
}

/* The setup a channel's keys are changes from, as Paste Keys on the setup frame takes them (see clipboard_paste): a
 * point's place, a curve point's handle, a bone's place (and angle, its changes being along it) or angle. */
struct ChangeSetup {
  enum Kind { None, Point, HandleIn, HandleOut, BonePosition, BoneAngle } kind = None;
  float2 place;
  float angle = 0.0f;
};

static ChangeSetup change_setup(const Layer &layer, const std::string &path)
{
  ChangeSetup s;
  const auto ends = [&](std::string_view tail) {
    return path.size() > tail.size() && path.compare(path.size() - tail.size(), tail.size(), tail) == 0;
  };
  const VectorDrawing &d = layer.drawing;
  if (path.rfind("bones[\"", 0) == 0) {
    const size_t close = path.find("\"]");
    const Bone *b = close == std::string::npos ? nullptr : bone_find_by_name(layer, path.substr(7, close - 7));
    if (b && !bone_is_controller(*b) && (ends(".position") || ends(".angle"))) {
      s.kind = ends(".position") ? ChangeSetup::BonePosition : ChangeSetup::BoneAngle;
      s.place = b->setup_position;
      s.angle = b->setup_angle;
    }
  }
  else if (const int curve = path_index(path, "curves["); curve >= 0) {
    const size_t dot = path.find("].points[");
    const int index = dot == std::string::npos ? -1 : path_index(path, "points[", dot + 2);
    if (size_t(curve) < d.curves.size() && index >= 0 && size_t(index) < d.curves[size_t(curve)].points.size()) {
      const CurvePoint &cp = d.curves[size_t(curve)].points[size_t(index)];
      if (d.points[cp.point].detail.level == 0 && (ends(".handle_in") || ends(".handle_out"))) {
        s.kind = ends(".handle_in") ? ChangeSetup::HandleIn : ChangeSetup::HandleOut;
        s.place = s.kind == ChangeSetup::HandleIn ? cp.setup_in : cp.setup_out;
      }
    }
  }
  else if (const int index = path_index(path, "points["); index >= 0 && size_t(index) < d.points.size() && ends(".pos")) {
    if (d.points[size_t(index)].detail.level == 0) {
      s.kind = ChangeSetup::Point;
      s.place = d.points[size_t(index)].setup_pos;
    }
  }
  return s;
}

/* A change from setup `from` as the change from setup `to` that shows the same. */
static float2 change_rebased(const ChangeSetup &from, const ChangeSetup &to, float2 change)
{
  switch (to.kind) {
    case ChangeSetup::Point:
      return from.place + change - to.place;
    case ChangeSetup::HandleIn:
    case ChangeSetup::HandleOut: {
      const bool in = to.kind == ChangeSetup::HandleIn;
      return handle_change(to.place, handle_from_change(from.place, change, in), change.x, in);
    }
    case ChangeSetup::BonePosition:
      return rotate(from.place + rotate(change, from.angle) - to.place, -to.angle);
    default:
      return change;
  }
}

static float change_rebased(const ChangeSetup &from, const ChangeSetup &to, float change)
{
  return to.kind == ChangeSetup::BoneAngle ? from.angle + change - to.angle : change;
}

struct ClipboardChannel {
  uint64_t layer = 0;
  std::string layer_name;
  std::string path;
  std::vector<Key<float>> scalar;
  std::vector<Key<float2>> vector;
  /* Its setup when copied: pasted on its own layer's setup frame, the pose copied becomes the setup, so a second paste
   * there changes nothing (taken as a change from the setup now, each paste moved it by as much again). */
  ChangeSetup setup;
  /* A point's or curve point's channel: the point's id, and the curve it was on (paths name points by their place,
   * which changes as points are added or deleted). */
  uint64_t point = 0;
  int curve = -1;
  /* A 2 Axis Controller's knob position copied in one of its sides' own actions: the action. Those keys are the
   * side's timing there (how far out each frame plays), never a move of the knob, so they paste only into that
   * action. Elsewhere they would play the action on top of the
   * pose pasted with them. */
  std::string knob_timing;
};

/* The point a drawing channel's path names (its id, and the curve for a curve point's), or none. */
static void clipboard_point_of(const Layer &layer, ClipboardChannel &c)
{
  const VectorDrawing &d = layer.drawing;
  const int curve = path_index(c.path, "curves[");
  const size_t dot = c.path.find("].points[");
  const int index = curve >= 0 && dot != std::string::npos ? path_index(c.path, "points[", dot + 2) :
                                                              path_index(c.path, "points[");
  if (curve >= 0) {
    if (curve >= 0 && size_t(curve) < d.curves.size() && index >= 0 &&
        size_t(index) < d.curves[size_t(curve)].points.size())
    {
      c.point = d.points[d.curves[size_t(curve)].points[size_t(index)].point].id;
      c.curve = curve;
    }
  }
  else if (index >= 0 && size_t(index) < d.points.size()) {
    c.point = d.points[size_t(index)].id;
  }
}

/* `c`'s path on its own layer as that layer is now: by its point's id where the point's place has changed; empty
 * when the point is gone. */
static std::string clipboard_path_now(const Layer &layer, const ClipboardChannel &c)
{
  if (c.point == 0) {
    return c.path;
  }
  const VectorDrawing &d = layer.drawing;
  const std::string rest = c.path.substr(c.path.find(']', c.path.rfind("points[")) + 1);
  if (c.curve < 0) {
    for (size_t i = 0; i < d.points.size(); i++) {
      if (d.points[i].id == c.point) {
        return "points[" + std::to_string(i) + "]" + rest;
      }
    }
    return "";
  }
  /* Its own curve first, then any curve through the point. */
  std::string other;
  for (size_t k = 0; k < d.curves.size(); k++) {
    for (size_t i = 0; i < d.curves[k].points.size(); i++) {
      if (d.points[d.curves[k].points[i].point].id == c.point) {
        const std::string path = "curves[" + std::to_string(k) + "].points[" + std::to_string(i) + "]" + rest;
        if (int(k) == c.curve) {
          return path;
        }
        other = other.empty() ? path : other;
      }
    }
  }
  return other;
}

struct KeyClipboard {
  std::vector<ClipboardChannel> channels;
  int first_frame = 0;
  std::shared_ptr<const Document> source;
};

}  // namespace

static KeyClipboard &key_clipboard()
{
  static KeyClipboard clipboard;
  return clipboard;
}

bool key_clipboard_empty()
{
  return key_clipboard().channels.empty();
}

void key_clipboard_set_source(const Document &doc)
{
  key_clipboard().source = std::make_shared<const Document>(doc);
}

const Document *key_clipboard_source()
{
  return key_clipboard().source.get();
}

/* The keys of `layers` that `wanted` takes, as a clipboard; `r_count` how many. */
template<typename Wanted>
static KeyClipboard clipboard_take(const Document &doc, const std::vector<Layer *> &layers, Wanted &&wanted, int &r_count)
{
  KeyClipboard copied;
  int count = 0;
  int first = INT32_MAX;
  for (Layer *layer : layers) {
    /* In a side's own action, the knob's position keys are its timing there. */
    const Bone *timed = !doc.action.empty() && doc.action_layer == layer->id ? controller_of_action(*layer, doc.action, nullptr)
                                                                             : nullptr;
    for (const ChannelRef &ref : layer_channels(*layer)) {
      ClipboardChannel c{layer->id, layer->name, ref.path, {}, {}};
      if (timed && ref.vector == &timed->position_keys) {
        c.knob_timing = doc.action;
      }
      const auto take = [&](const auto &channel, auto &into) {
        for (const auto &key : channel.keys) {
          if (wanted(key)) {
            into.push_back(key);
            first = std::min(first, key.frame);
            count++;
          }
        }
      };
      if (ref.scalar) {
        take(*ref.scalar, c.scalar);
      }
      else {
        take(*ref.vector, c.vector);
      }
      if (!c.scalar.empty() || !c.vector.empty()) {
        clipboard_point_of(*layer, c);
        c.setup = change_setup(*layer, ref.path);
        copied.channels.push_back(std::move(c));
      }
    }
  }
  copied.first_frame = count > 0 ? first : 0;
  r_count = count;
  return copied;
}

int layers_copy_selected_keys(const Document &doc, const std::vector<Layer *> &layers)
{
  int count = 0;
  KeyClipboard copied = clipboard_take(doc, layers, [](const auto &key) { return key.selected; }, count);
  if (count > 0) {
    key_clipboard() = std::move(copied);
  }
  return count;
}

/* Pastes `clipboard` onto `layers`: its first key that pastes on `frame`, or each on its own frame with `same_frames`
 * (see layers_paste_keys). */
static int clipboard_paste(const KeyClipboard &clipboard, const Document &doc, const std::vector<Layer *> &layers,
                           int frame, bool same_frames, std::vector<std::pair<uint64_t, uint64_t>> *r_layers,
                           std::vector<std::pair<int, int>> *r_frames)
{
  if (clipboard.channels.empty() || layers.empty()) {
    return 0;
  }
  std::set<uint64_t> sources;
  for (const ClipboardChannel &c : clipboard.channels) {
    sources.insert(c.layer);
  }
  /* Where a copied channel goes: the same layer, else one with the same name, else (keys copied
   * from a single layer, Copy Keys' only: a timeline pastes onto its own layers) the first layer that has the channel. */
  Layer *found = nullptr;
  const auto target = [&](const ClipboardChannel &c, ChannelRef *r_ref) -> bool {
    for (Layer *layer : layers) {
      if (layer->id == c.layer) {
        /* Its own layer: the same point, wherever it is now (none if it was deleted). */
        const std::string path = clipboard_path_now(*layer, c);
        if (path.empty()) {
          return false;
        }
        if (layer_channel(*layer, path, r_ref)) {
          found = layer;
          return true;
        }
      }
    }
    for (Layer *layer : layers) {
      if (layer->name == c.layer_name && layer_channel(*layer, c.path, r_ref)) {
        found = layer;
        return true;
      }
    }
    if (sources.size() == 1 && !same_frames) {
      for (Layer *layer : layers) {
        if (layer_channel(*layer, c.path, r_ref)) {
          found = layer;
          return true;
        }
      }
    }
    return false;
  };
  /* A knob's timing in a side's own action means nothing anywhere else: on the mainline it would move the knob. The
   * first key that pastes lands on `frame`. */
  const auto pastes = [&](const ClipboardChannel &c) { return c.knob_timing.empty() || c.knob_timing == doc.action; };
  int first_frame = INT32_MAX, last_frame = 0;
  for (const ClipboardChannel &c : clipboard.channels) {
    for (const auto &k : c.scalar) {
      first_frame = pastes(c) ? std::min(first_frame, k.frame) : first_frame;
      last_frame = pastes(c) ? std::max(last_frame, k.frame) : last_frame;
    }
    for (const auto &k : c.vector) {
      first_frame = pastes(c) ? std::min(first_frame, k.frame) : first_frame;
      last_frame = pastes(c) ? std::max(last_frame, k.frame) : last_frame;
    }
  }
  if (first_frame == INT32_MAX) {
    return 0;
  }
  layers_deselect_keys(layers);
  /* Never past the last frame there is: pasted near it, the keys stop there together, as moved keys do. */
  const int offset = same_frames ? 0 : std::min(frame - first_frame, KEY_FRAME_LAST - last_frame);
  int count = 0;
  /* The layers whose points or bones took a pose on the setup frame: their values follow the changes. */
  std::set<Layer *> posed_setup;
  /* Written once every channel is found: finding one works every point's change out from its value
   * again, which would undo a change written before it. */
  std::vector<std::pair<float *, float>> setup_scalars;
  std::vector<std::pair<float2 *, float2>> setup_vectors;
  for (const ClipboardChannel &c : clipboard.channels) {
    if (!pastes(c)) {
      continue;
    }
    ChannelRef ref;
    if (!target(c, &ref)) {
      continue;
    }
    if (r_layers && std::find(r_layers->begin(), r_layers->end(), std::pair{found->id, c.layer}) == r_layers->end()) {
      r_layers->push_back({found->id, c.layer});
    }
    if (r_frames) {
      const auto note = [&](int from) {
        const std::pair<int, int> p{from, from + offset};
        if (std::find(r_frames->begin(), r_frames->end(), p) == r_frames->end()) {
          r_frames->push_back(p);
        }
      };
      for (const auto &k : c.scalar) {
        note(k.frame);
      }
      for (const auto &k : c.vector) {
        note(k.frame);
      }
    }
    /* A point's, handle's or bone's keys hold the change from the setup pose, so on the setup frame
     * (where the change is nothing) a key pasted is a pose to take: its change goes into the value, as
     * a move there would (animation_record makes it the setup; Keep Poses keeps the other frames). */
    /* A 2 Axis Controller's position holds the knob (in frames): on the setup frame, where controllers rest, it pastes
     * nothing (taken as a pose there, its box jumped by the knob's frames). */
    const auto controller_position = [&] {
      const size_t open = ref.path.find("[\""), close = ref.path.find("\"]");
      if (open == std::string::npos || close == std::string::npos || close < open + 2) {
        return false;
      }
      const Bone *b = bone_find_by_name(*found, ref.path.substr(open + 2, close - open - 2));
      return b && bone_is_controller(*b);
    };
    const bool knob = ref.path.rfind("bones[", 0) == 0 && ref.path.size() > 9 &&
                      ref.path.compare(ref.path.size() - 9, 9, ".position") == 0 && controller_position();
    const bool change = ref.path.rfind("bones[", 0) == 0
                            ? (ref.path.size() > 9 && ref.path.compare(ref.path.size() - 9, 9, ".position") == 0 &&
                               !knob) ||
                                  (ref.path.size() > 6 && ref.path.compare(ref.path.size() - 6, 6, ".angle") == 0)
                            : (ref.path.rfind("points[", 0) == 0 && ref.path.size() > 4 &&
                               ref.path.compare(ref.path.size() - 4, 4, ".pos") == 0) ||
                                  (ref.path.rfind("curves[", 0) == 0 && (ref.path.find(".handle_in") != std::string::npos ||
                                                                         ref.path.find(".handle_out") != std::string::npos));
    Layer *owner = nullptr;
    for (Layer *layer : layers) {
      ChannelRef probe;
      if (change && layer_channel(*layer, ref.path, &probe) &&
          (probe.scalar ? (void *)probe.scalar : (void *)probe.vector) == (ref.scalar ? (void *)ref.scalar : (void *)ref.vector))
      {
        owner = layer;
      }
    }
    const auto put = [&](auto &channel, const auto &keys, auto *value) {
      for (const auto &key : keys) {
        const int at = key.frame + offset;
        if (at < 0 || (at == 0 && knob)) {
          continue;
        }
        if (at == 0 && change && owner && value) {
          const ChangeSetup now = found->id == c.layer ? change_setup(*found, ref.path) : ChangeSetup{};
          const auto pose = now.kind != ChangeSetup::None && now.kind == c.setup.kind ?
                                change_rebased(c.setup, now, key.value) :
                                key.value;
          if constexpr (std::is_same_v<std::decay_t<decltype(*value)>, float>) {
            setup_scalars.push_back({value, pose});
          }
          else {
            setup_vectors.push_back({value, pose});
          }
          posed_setup.insert(owner);
          /* Its frame 0 key (if it has one) is picked, as a pasted key would be. */
          if (auto *k = channel.key_at(0)) {
            k->selected = true;
          }
          count++;
          continue;
        }
        /* Not keyed yet, its setup is keyed first, as keying it by hand does: a lone key holds on every frame,
         * frame 0's setup pose too. */
        if (!channel.animated() && at != 0 && value) {
          channel.set_key(0, (channel.has_last ? channel.last : *value) - channel.from_action_bones);
        }
        auto &placed = channel.set_key(at, key.value);
        placed = key;
        placed.frame = at;
        placed.selected = true;
        count++;
      }
    };
    if (ref.scalar && !c.scalar.empty()) {
      put(*ref.scalar, c.scalar, ref.scalar_value);
    }
    else if (ref.vector && !c.vector.empty()) {
      put(*ref.vector, c.vector, ref.vector_value);
    }
  }
  for (const auto &[at, v] : setup_scalars) {
    *at = v;
  }
  for (const auto &[at, v] : setup_vectors) {
    *at = v;
  }
  for (Layer *layer : posed_setup) {
    drawing_values_from_changes(layer->drawing);
    for (Bone &bone : layer->bones) {
      bone_values_from_changes(bone);
    }
  }
  return count;
}

int layers_paste_keys(const Document &doc, const std::vector<Layer *> &layers, int frame,
                      std::vector<std::pair<uint64_t, uint64_t>> *r_layers, std::vector<std::pair<int, int>> *r_frames)
{
  return clipboard_paste(key_clipboard(), doc, layers, frame, false, r_layers, r_frames);
}

/* What Copy Timeline copied, apart from Copy Keys' clipboard: a whole timeline, pasted on its own frames. */
static struct {
  KeyClipboard keys;
  std::string name;
  int count = 0;
} g_timeline_clipboard;

/* The layers the timeline being edited keys (as Clear Timeline clears): in an action its bone layer and what is inside
 * it; on the mainline every layer, the Simulation and the camera. */
static std::vector<Layer *> timeline_edited_layers(Document &doc)
{
  std::vector<Layer *> out;
  const auto add = [&](auto &self, Layer &l) -> void {
    out.push_back(&l);
    for (Layer &child : l.children) {
      self(self, child);
    }
  };
  if (!doc.action.empty()) {
    if (Layer *owner = layer_find(doc, doc.action_layer)) {
      add(add, *owner);
    }
    return out;
  }
  for (Layer &l : doc.layers) {
    add(add, l);
  }
  out.push_back(&doc.simulation);
  out.push_back(&document_camera(doc));
  return out;
}

int timeline_copy(Document &doc)
{
  int count = 0;
  KeyClipboard copied = clipboard_take(doc, timeline_edited_layers(doc), [](const auto &key) { return key.frame != 0; },
                                       count);
  if (count > 0) {
    g_timeline_clipboard.keys = std::move(copied);
    g_timeline_clipboard.name = timeline_edited_name(doc);
    g_timeline_clipboard.count = count;
  }
  return count;
}

bool timeline_clipboard_empty()
{
  return g_timeline_clipboard.count == 0;
}

std::string timeline_clipboard_name()
{
  return g_timeline_clipboard.name;
}

int timeline_clipboard_count()
{
  return g_timeline_clipboard.count;
}

int timeline_paste(Document &doc)
{
  if (timeline_clipboard_empty()) {
    return 0;
  }
  /* Cleared, but frame 0's keys stay as they are (their interpolation, path handles), so what pastes after them goes on
   * from the same setup key; one left alone goes as Clear Timeline's would, if nothing pastes into its channel. */
  std::set<const void *> lone;
  timeline_for_each_channel(doc, [&](auto &ch, auto & /*value*/) {
    const size_t before = ch.keys.size();
    std::erase_if(ch.keys, [](const auto &key) { return key.frame != 0; });
    if (ch.keys.size() != before && ch.keys.size() == 1) {
      lone.insert(static_cast<const void *>(&ch));
    }
  });
  const int count = clipboard_paste(g_timeline_clipboard.keys, doc, timeline_edited_layers(doc), 0, true, nullptr, nullptr);
  timeline_for_each_channel(doc, [&](auto &ch, auto &value) {
    if (lone.count(static_cast<const void *>(&ch))) {
      drop_lone_setup_key(ch, value);
    }
  });
  return count;
}

}  // namespace oanim
