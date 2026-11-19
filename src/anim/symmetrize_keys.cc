#include "anim/bone_curve.hh"
#include "anim/symmetrize_keys.hh"

#include <algorithm>
#include <functional>
#include <limits>
#include <set>

#include "anim/animation.hh"
#include "anim/controller.hh"
#include "data/bones.hh"
#include "data/document.hh"
#include "data/layer.hh"
#include "data/vector.hh"

namespace oanim {

namespace {

float2 across(float2 v)
{
  return float2(-v.x, v.y);
}

/* A handle's keys (Angle and Length: the change from its setup) as the mirror image's, from `from_setup` to
 * `to_setup`: the handle each key makes goes across, then becomes a change from the other setup. */
void handle_keys_mirror(Channel<float2> &ch, float2 from_setup, float2 to_setup, bool in)
{
  const auto map = [&](float2 change) {
    const float2 shown = handle_from_change(from_setup, change, in);
    /* Turned the other way round: the turn nearest minus this one, so whole turns carry on. */
    return handle_change(to_setup, across(shown), -change.x, in);
  };
  const auto keys = [&](std::vector<Key<float2>> &list) {
    for (Key<float2> &k : list) {
      k.value = map(k.value);
      k.selected = false;
    }
  };
  keys(ch.keys);
  for (auto &[name, list] : ch.actions) {
    keys(list);
  }
  if (ch.has_last) {
    ch.last = map(ch.last);
  }
}

template<typename T> void keys_unpicked(Channel<T> &ch)
{
  channel_values_map(ch, [](T v) { return v; });
}

void layer_walk(const Layer &l, const std::function<void(const Layer &)> &fn)
{
  fn(l);
  for (const Layer &child : l.children) {
    layer_walk(child, fn);
  }
}

void layer_walk(Layer &l, const std::function<void(Layer &)> &fn)
{
  fn(l);
  for (Layer &child : l.children) {
    layer_walk(child, fn);
  }
}

bool has_action(const Layer &owner, const std::string &name)
{
  return !name.empty() && std::find(owner.actions.begin(), owner.actions.end(), name) != owner.actions.end();
}

/* Which way a bone turns by the end of its own action `name`: +1, -1, or 0 (no keys, or no turn). */
float end_turn(const Bone &bone, const std::string &name)
{
  const auto it = bone.angle_keys.actions.find(name);
  if (it == bone.angle_keys.actions.end() || it->second.empty()) {
    return 0.0f;
  }
  const auto last = std::max_element(it->second.begin(), it->second.end(),
                                     [](const Key<float> &a, const Key<float> &b) { return a.frame < b.frame; });
  return last->value > 1e-6f ? 1.0f : last->value < -1e-6f ? -1.0f : 0.0f;
}

/* A bone layer inside what's mirrored: its action `name`'s other side's name. A bone's own action takes the bone's other
 * side's ("Ear_L" and "Ear_L 2" to "Ear_R" and "Ear_R 2"; a bone with no side keeps it, its keys turning the other way);
 * a knob's side its knob's ("Pupil_L Left" to "Pupil_R Right"); any other its other side's (Blink_L to Blink_R). */
std::string inside_name(const Layer &owner, const std::string &name)
{
  if (const Bone *bone = controller_dial_of_action(owner, name)) {
    return action_mirror_name(name, bone->name);
  }
  if (const Bone *knob = controller_of_action(owner, name)) {
    return action_mirror_name(name, knob->name);
  }
  return bone_mirror_name(name);
}

/* A bone layer around what's mirrored: where the keys of its action `name` go on the other side, or none. */
std::optional<std::string> around_name(const Layer &owner, const std::string &name)
{
  /* A fix: the one that follows the other side's bones (itself, following bones with no side). */
  for (const BoneFix &fix : owner.bone_fixes) {
    if (fix.name != name) {
      continue;
    }
    std::vector<uint64_t> own = fix.follows, other;
    for (const uint64_t id : fix.follows) {
      other.push_back(bone_mirror_id(owner, id));
    }
    std::sort(own.begin(), own.end());
    std::sort(other.begin(), other.end());
    if (own == other) {
      return name;
    }
    for (const BoneFix &f : owner.bone_fixes) {
      std::vector<uint64_t> its = f.follows;
      std::sort(its.begin(), its.end());
      if (its == other) {
        return f.name;
      }
    }
    return std::nullopt;
  }
  /* A knob's side: the other side's knob's, Left and Right swapped (a mirrored knob goes the other way across). */
  int side = -1;
  if (const Bone *knob = controller_of_action(owner, name, &side)) {
    const Bone *other = bone_find(owner, bone_mirror_id(owner, knob->id));
    const int to = controller_side_axis(side) == 0 ? controller_side_opposite(side) : side;
    if (other && has_action(owner, other->controller_actions[size_t(to)])) {
      return other->controller_actions[size_t(to)];
    }
    return std::nullopt;
  }
  /* A bone's own action: the other side's bone's (this one, with no side) that turns it the other way, as its mirror
   * image does (Head into Head 2). */
  if (const Bone *bone = controller_dial_of_action(owner, name)) {
    const Bone *other = bone_find(owner, bone_mirror_id(owner, bone->id));
    if (!other) {
      return std::nullopt;
    }
    const float turn = end_turn(*bone, name);
    for (const std::string &candidate : owner.actions) {
      if (controller_dial_of_action(owner, candidate) == other && turn != 0.0f &&
          end_turn(*other, candidate) * turn < 0.0f)
      {
        return candidate;
      }
    }
    const std::string named = action_mirror_name(name, bone->name);
    if (has_action(owner, named) && controller_dial_of_action(owner, named) == other && named != name) {
      return named;
    }
    return std::nullopt;
  }
  /* Any other: its other side's (Blink_L into Blink_R), one with no side its own. */
  const std::string other = bone_mirror_name(name);
  if (other == name) {
    return name;
  }
  if (has_action(owner, other)) {
    return other;
  }
  return std::nullopt;
}

/* --- Keep Partner's ------------------------------------------------------------------------------------------- */

template<typename T, typename F> void keys_taken(Channel<T> &now, const Channel<T> &old, F &&shift)
{
  now = old;
  channel_values_map(now, shift);
}

void constraint_keys_taken(BoneConstraint &now, const BoneConstraint &old)
{
  now.influence_keys = old.influence_keys;
  now.follow_shift_keys = old.follow_shift_keys;
  now.follow_shift2_keys = old.follow_shift2_keys;
  now.follow_shift3_keys = old.follow_shift3_keys;
  now.weight_keys = old.weight_keys;
  now.wind_catch_keys = old.wind_catch_keys;
  now.gravity_keys = old.gravity_keys;
  now.wind_keys = old.wind_keys;
  now.wind_direction_keys = old.wind_direction_keys;
  now.wind_gusts_keys = old.wind_gusts_keys;
  now.wind_gust_speed_keys = old.wind_gust_speed_keys;
  now.wind_turbulence_keys = old.wind_turbulence_keys;
  const BoneSpring *from[] = {&old.angle_spring, &old.position_spring, &old.scale_spring};
  BoneSpring *to[] = {&now.angle_spring, &now.position_spring, &now.scale_spring};
  for (int i = 0; i < 3; i++) {
    to[i]->settle_speed_keys = from[i]->settle_speed_keys;
    to[i]->bounce_keys = from[i]->bounce_keys;
    to[i]->inertia_keys = from[i]->inertia_keys;
    to[i]->stretch_keys = from[i]->stretch_keys;
    to[i]->limit_keys = from[i]->limit_keys;
    to[i]->squash_limit_keys = from[i]->squash_limit_keys;
  }
}

bool same_curves(const VectorDrawing &a, const VectorDrawing &b)
{
  if (a.points.size() != b.points.size() || a.curves.size() != b.curves.size()) {
    return false;
  }
  for (size_t c = 0; c < a.curves.size(); c++) {
    const Curve &x = a.curves[c], &y = b.curves[c];
    if (x.closed != y.closed || x.points.size() != y.points.size()) {
      return false;
    }
    for (size_t i = 0; i < x.points.size(); i++) {
      if (x.points[i].point != y.points[i].point) {
        return false;
      }
    }
  }
  return true;
}

/* Where the handle of curve point `cp` reaching for point `next` is in `drawing`: the curve point at point `at` whose
 * in or out handle reaches `next`. */
struct HandleAt {
  const CurvePoint *cp = nullptr;
  bool in = false;
};
HandleAt handle_reaching(const VectorDrawing &drawing, int at, int next)
{
  for (const Curve &curve : drawing.curves) {
    const int n = int(curve.points.size());
    for (int i = 0; i < n; i++) {
      if (curve.points[size_t(i)].point != at) {
        continue;
      }
      if ((i > 0 || curve.closed) && curve.points[size_t((i + n - 1) % n)].point == next) {
        return {&curve.points[size_t(i)], true};
      }
      if ((i + 1 < n || curve.closed) && curve.points[size_t((i + 1) % n)].point == next) {
        return {&curve.points[size_t(i)], false};
      }
    }
  }
  return {};
}

void keep_drawing(VectorDrawing &now, const VectorDrawing &old, const Transform2D &now_space, const Transform2D &old_space)
{
  const int n = int(now.points.size()), o = int(old.points.size());
  std::vector<int> pair(static_cast<size_t>(n), -1);
  const bool same = same_curves(now, old);
  if (same) {
    for (int i = 0; i < n; i++) {
      pair[size_t(i)] = i;
    }
  }
  else if (n > 0 && o > 0) {
    /* Each new point the old one nearest it in the setup pose, where it is the nearest the other way too. */
    std::vector<float2> at_now(static_cast<size_t>(n)), at_old(static_cast<size_t>(o));
    const float big = std::numeric_limits<float>::max();
    float2 lo(big, big), hi(-big, -big);
    for (int i = 0; i < n; i++) {
      at_now[size_t(i)] = now_space.apply(point_setup_pos(now.points[size_t(i)]));
      lo = float2(std::min(lo.x, at_now[size_t(i)].x), std::min(lo.y, at_now[size_t(i)].y));
      hi = float2(std::max(hi.x, at_now[size_t(i)].x), std::max(hi.y, at_now[size_t(i)].y));
    }
    for (int j = 0; j < o; j++) {
      at_old[size_t(j)] = old_space.apply(point_setup_pos(old.points[size_t(j)]));
    }
    const float reach = std::max(0.1f * length(hi - lo), 1e-4f);
    const auto nearest = [](const std::vector<float2> &from, float2 p) {
      int best = -1;
      float d = std::numeric_limits<float>::max();
      for (size_t k = 0; k < from.size(); k++) {
        if (const float e = distance(from[k], p); e < d) {
          d = e;
          best = int(k);
        }
      }
      return best;
    };
    for (int i = 0; i < n; i++) {
      const int j = nearest(at_old, at_now[size_t(i)]);
      if (j >= 0 && nearest(at_now, at_old[size_t(j)]) == i && distance(at_now[size_t(i)], at_old[size_t(j)]) <= reach) {
        pair[size_t(i)] = j;
      }
    }
  }
  for (int i = 0; i < n; i++) {
    if (const int j = pair[size_t(i)]; j >= 0) {
      now.points[size_t(i)].pos_keys = old.points[size_t(j)].pos_keys;
      now.points[size_t(i)].radius_keys = old.points[size_t(j)].radius_keys;
    }
  }
  for (size_t c = 0; c < now.curves.size(); c++) {
    Curve &curve = now.curves[c];
    const int m = int(curve.points.size());
    for (int k = 0; k < m; k++) {
      CurvePoint &cp = curve.points[size_t(k)];
      if (same) {
        const CurvePoint &was = old.curves[c].points[size_t(k)];
        cp.curvature_keys = was.curvature_keys;
        cp.handle_in_keys = was.handle_in_keys;
        cp.handle_out_keys = was.handle_out_keys;
        continue;
      }
      const int j = pair[size_t(cp.point)];
      if (j < 0) {
        continue;
      }
      /* Each handle by what it reaches for: the old point paired with the one it reaches. */
      const auto take = [&](bool in, int neighbour) {
        const int to = pair[size_t(neighbour)];
        if (to < 0) {
          return;
        }
        const HandleAt h = handle_reaching(old, j, to);
        if (!h.cp) {
          return;
        }
        (in ? cp.handle_in_keys : cp.handle_out_keys) = h.in ? h.cp->handle_in_keys : h.cp->handle_out_keys;
        cp.curvature_keys = h.cp->curvature_keys;
      };
      if (k > 0 || curve.closed) {
        take(true, curve.points[size_t((k + m - 1) % m)].point);
      }
      if (k + 1 < m || curve.closed) {
        take(false, curve.points[size_t((k + 1) % m)].point);
      }
    }
  }
}

void keep_layer(Layer &now, const Layer &old)
{
  for (CustomChannel &c : now.custom_channels) {
    for (const CustomChannel &d : old.custom_channels) {
      if (d.path == c.path) {
        c.keys = d.keys;
      }
    }
  }
  now.visible_keys = old.visible_keys;
  now.draw_order_keys = old.draw_order_keys;
  if (now.is_switch() && old.is_switch()) {
    now.switch_keys = old.switch_keys;
  }
  now.opacity_keys = old.opacity_keys;
  /* Its transform's keys as changes from the setup: onto the new one's. */
  const float2 moved = now.position - old.position, sheared = now.shear - old.shear;
  const float turned = now.rotation - old.rotation;
  keys_taken(now.position_keys, old.position_keys, [&](float2 v) { return v + moved; });
  keys_taken(now.rotation_keys, old.rotation_keys, [&](float v) { return v + turned; });
  keys_taken(now.shear_keys, old.shear_keys, [&](float2 v) { return v + sheared; });
  const float2 now_scale = now.scale, old_scale = old.scale;
  keys_taken(now.scale_keys, old.scale_keys, [&](float2 v) {
    const auto by = [](float v1, float n, float o) { return std::fabs(o) > 1e-9f ? v1 * n / o : v1 + n - o; };
    return float2(by(v.x, now_scale.x, old_scale.x), by(v.y, now_scale.y, old_scale.y));
  });
  if (now.masks.size() == old.masks.size()) {
    for (size_t i = 0; i < now.masks.size(); i++) {
      now.masks[i].line_reach_keys = old.masks[i].line_reach_keys;
    }
  }
  if (now.modifiers.size() == old.modifiers.size()) {
    for (size_t i = 0; i < now.modifiers.size(); i++) {
      Modifier &m = now.modifiers[i];
      const Modifier &w = old.modifiers[i];
      if (m.type == w.type) {
        m.merge_smoothing_keys = w.merge_smoothing_keys;
        m.bevel_amount_keys = w.bevel_amount_keys;
        m.deform_strength_keys = w.deform_strength_keys;
      }
    }
  }
  if (now.has_drawing() && old.has_drawing() && !now.is_reference() && !old.is_reference()) {
    keep_drawing(now.drawing, old.drawing, now.local_transform(), old.local_transform());
  }
  if (now.is_bone_layer() && old.is_bone_layer()) {
    /* Bones by name: their keys are changes from their setup, so they come as they are. */
    std::map<uint64_t, uint64_t> bone_of;
    for (Bone &b : now.bones) {
      const Bone *was = bone_find_by_name(old, b.name);
      if (!was) {
        continue;
      }
      bone_of[was->id] = b.id;
      b.position_keys = was->position_keys;
      if (bone_is_controller(b) && bone_is_controller(*was)) {
        /* Its keys are distances at the partner's box size: rescaled to this box's, as zooming it does. */
        const float size = b.controller_frame_size;
        const float2 position = b.position, transform = b.transform;
        b.controller_frame_size = was->controller_frame_size;
        controller_frame_size_set(b, size);
        b.position = position;
        b.transform = transform;
      }
      b.angle_keys = was->angle_keys;
      b.scale_keys = was->scale_keys;
      b.depth_keys = was->depth_keys;
      {
        std::vector<const Channel<float> *> theirs;
        bone_curve_channels(*was, [&](std::string_view, const auto &, const auto &keys) { theirs.push_back(&keys); });
        size_t k = 0;
        bone_curve_channels(b, [&](std::string_view, float &, Channel<float> &keys) { keys = *theirs[k++]; });
      }
      b.controller_actions = was->controller_actions;
      if (b.constraints.size() == was->constraints.size()) {
        for (size_t i = 0; i < b.constraints.size(); i++) {
          if (b.constraints[i].type == was->constraints[i].type) {
            constraint_keys_taken(b.constraints[i], was->constraints[i]);
          }
        }
      }
    }
    now.actions = old.actions;
    now.action_plays = old.action_plays;
    now.bone_fixes.clear();
    for (BoneFix fix : old.bone_fixes) {
      std::vector<uint64_t> follows;
      for (const uint64_t id : fix.follows) {
        if (const auto it = bone_of.find(id); it != bone_of.end()) {
          follows.push_back(it->second);
        }
      }
      fix.follows = std::move(follows);
      now.bone_fixes.push_back(std::move(fix));
    }
  }
  for (Layer &child : now.children) {
    for (const Layer &was : old.children) {
      if (was.id == child.id) {
        keep_layer(child, was);
      }
    }
  }
}

}  // namespace

void drawing_mirror_setup_x_keeping_keys(VectorDrawing &drawing)
{
  const VectorDrawing was = drawing;
  drawing_mirror_setup_x(drawing);
  for (size_t i = 0; i < drawing.points.size(); i++) {
    MeshPoint &p = drawing.points[i];
    const MeshPoint &w = was.points[i];
    p.pos_keys = w.pos_keys;
    /* A detail point's keys are along and across its segment, which changes side. */
    if (w.detail.level > 0) {
      channel_values_map(p.pos_keys, [](float2 v) { return float2(v.x, -v.y); });
    }
    else {
      channel_values_map(p.pos_keys, across);
    }
    p.radius_keys = w.radius_keys;
    keys_unpicked(p.radius_keys);
  }
  for (size_t c = 0; c < drawing.curves.size(); c++) {
    for (size_t k = 0; k < drawing.curves[c].points.size(); k++) {
      CurvePoint &cp = drawing.curves[c].points[k];
      const CurvePoint &w = was.curves[c].points[k];
      cp.curvature_keys = w.curvature_keys;
      keys_unpicked(cp.curvature_keys);
      for (const bool in : {true, false}) {
        const float2 from = handle_setup(w, in);
        /* A handle not stored follows its neighbours: its setup is the flipped one. */
        const float2 to = w.handles_set ? handle_setup(cp, in) : across(from);
        Channel<float2> &keys = in ? cp.handle_in_keys : cp.handle_out_keys;
        keys = in ? w.handle_in_keys : w.handle_out_keys;
        handle_keys_mirror(keys, from, to, in);
      }
    }
  }
}

std::string SymmetrizeNames::rename(const std::string &name, bool *r_dropped) const
{
  const auto it = to.find(name);
  if (it == to.end()) {
    return name;
  }
  if (!it->second) {
    if (r_dropped) {
      *r_dropped = true;
    }
    return std::string();
  }
  return *it->second;
}

SymmetrizeNames symmetrize_action_names(Document &doc, const Layer &source)
{
  SymmetrizeNames names;
  /* The bone layers inside: their actions go across with them, each under its other side's name, where that is no other
   * action's of theirs (a name taken stays as it was). */
  layer_walk(source, [&](const Layer &l) {
    if (!l.is_bone_layer()) {
      return;
    }
    names.inside_owners.push_back(l.id);
    std::map<std::string, std::string> mine;
    for (const std::string &a : l.actions) {
      mine[a] = inside_name(l, a);
    }
    for (const auto &[from, to] : mine) {
      const auto back = mine.find(to);
      const bool taken = to != from && (back != mine.end() ? back->second != from : false);
      if (!names.to.count(from)) {
        names.to[from] = taken ? from : to;
      }
    }
  });
  /* The bone layers around it, nearest first: their actions stay, the keys go to their mirror's. */
  for (const Layer *owner : action_owners(doc, source.id)) {
    for (const std::string &a : owner->actions) {
      if (!names.to.count(a)) {
        names.to[a] = around_name(*owner, a);
      }
    }
  }
  return names;
}

std::vector<std::string> symmetrize_actions_apply(Layer &copy, const SymmetrizeNames &names)
{
  std::set<std::string> dropped;
  const auto renamed = [&](const std::string &name) -> std::optional<std::string> {
    bool gone = false;
    std::string to = names.rename(name, &gone);
    if (gone) {
      dropped.insert(name);
      return std::nullopt;
    }
    return to;
  };
  layer_walk(copy, [&](Layer &l) {
    layer_actions_rename(l, renamed);
    if (!l.is_bone_layer()) {
      return;
    }
    for (std::string &a : l.actions) {
      a = names.rename(a, nullptr);
    }
    for (ActionPlay &play : l.action_plays) {
      play.name = names.rename(play.name, nullptr);
    }
    for (BoneFix &fix : l.bone_fixes) {
      fix.name = names.rename(fix.name, nullptr);
    }
    for (Bone &b : l.bones) {
      for (std::string &a : b.controller_actions) {
        if (!a.empty()) {
          a = names.rename(a, nullptr);
        }
      }
      if (bone_is_controller(b)) {
        /* Mirrored, the knob goes the other way across: Right's action is Left's now, the spots too. */
        std::swap(b.controller_actions[0], b.controller_actions[1]);
        for (ControllerSpot &spot : b.controller_spots) {
          spot.at.x = -spot.at.x;
        }
      }
    }
  });
  return std::vector<std::string>(dropped.begin(), dropped.end());
}

void symmetrize_keep_partner(Layer &now, const Layer &old)
{
  layer_strip_keys(now, false, false);
  keep_layer(now, old);
}

}  // namespace oanim
