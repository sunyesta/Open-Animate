/* Copy Pose and Paste Pose, as Blender's pose mode has them: Ctrl C over the viewport off the setup frame, Ctrl V on any
 * (frame 0 is where the drawing and the rig are made, as Edit Mode; every other frame poses, as Pose Mode). The
 * selected bones' and points' pose on the frame shown goes back on the same bones (by name) and points (by id, or by
 * their order in a drawing with as many points) on another frame, in another action or in another file.
 *
 * What is copied is what their keys hold: each value's change from the setup, less what action bone actions add;
 * beside it what those actions added, and where each point and handle showed through the bones. Paste As picks what
 * a paste gives: Keys (the keys; the actions playing where it is pasted add theirs on top), Same Look (as it looked,
 * moving with the bones here: what the actions added where it was copied kept, what they add here taken out) or Same
 * Place (where it showed, whatever the bones and actions do here). The pose travels on the system clipboard, as copied layers do. A paste is an
 * edit like any other: Auto Keying keys it, as Blender's does. */

#include <algorithm>
#include <cmath>
#include <map>
#include <set>

#include <nlohmann/json.hpp>

#include "anim/animation.hh"
#include "anim/bone_family.hh"
#include "anim/controller.hh"
#include "anim/deform.hh"
#include "anim/keep_poses.hh"
#include "core/log.hh"
#include "data/bones.hh"
#include "data/document.hh"
#include "data/layer_mirror.hh"
#include "data/vector.hh"
#include "ops/edit_ops.hh"
#include "ops/operator.hh"
#include "ops/pose_apply.hh"
#include "wm/context.hh"

namespace oanim {

using json = nlohmann::ordered_json;

static json json_of(float2 v)
{
  return json::array({v.x, v.y});
}

static float2 float2_of(const json &j)
{
  if (!j.is_array() || j.size() != 2 || !j[0].is_number() || !j[1].is_number()) {
    return {};
  }
  return {j[0].get<float>(), j[1].get<float>()};
}

static float float_of(const json &j, const char *name)
{
  const auto it = j.find(name);
  return it != j.end() && it->is_number() ? it->get<float>() : 0.0f;
}

static bool invertible(const Transform2D &t)
{
  return std::fabs(t.a * t.d - t.b * t.c) > 1e-8f;
}

/* The points curve `c`'s point `j` reaches for, its in handle toward the one before and its out handle toward the one
 * after (-1 at an open end). */
static void curve_neighbours(const Curve &curve, size_t j, int &before, int &after)
{
  const size_t n = curve.points.size();
  before = j > 0 ? curve.points[j - 1].point : (curve.closed && n > 1 ? curve.points[n - 1].point : -1);
  after = j + 1 < n ? curve.points[j + 1].point : (curve.closed && n > 1 ? curve.points[0].point : -1);
}

/* The drawings whose points are being edited, and the bone layer whose bones are (the active layer, a bone layer). */
std::vector<Layer *> pose_drawings(Context &C)
{
  std::vector<Layer *> out;
  for (Layer *l : editable_layers(C)) {
    if (l->type == LayerType::Vector && !l->is_reference()) {
      out.push_back(l);
    }
  }
  return out;
}

Layer *pose_rig(Context &C)
{
  Layer *active = document_active_layer(*C.document);
  return active && active->is_bone_layer() ? active : nullptr;
}

std::vector<Layer *> pose_rigs(Context &C)
{
  Layer *rig = pose_rig(C);
  return rig ? armature_family(*C.document, rig->id) : std::vector<Layer *>();
}

static Bone *bone_named(Layer &rig, const std::string &name)
{
  for (Bone &b : rig.bones) {
    if (b.name == name) {
      return &b;
    }
  }
  return nullptr;
}

/* What Ctrl C finds to copy: the selected bones and points (a detail point follows its parent, so goes with it). */
bool pose_anything_selected(Context &C)
{
  for (const Layer *rig : pose_rigs(C)) {
    if (std::any_of(rig->bones.begin(), rig->bones.end(), [](const Bone &b) { return b.selected; })) {
      return true;
    }
  }
  for (const Layer *l : pose_drawings(C)) {
    for (const MeshPoint &p : l->drawing.points) {
      if (p.selected && p.detail.level == 0) {
        return true;
      }
    }
  }
  return false;
}

json pose_record(Document &doc, const std::vector<Layer *> &rigs, const std::vector<Layer *> &drawings, int *r_bones,
                 int *r_points)
{
  json layers = json::array();
  *r_bones = *r_points = 0;
  for (Layer *rig : rigs) {
    json bones = json::array();
    for (Bone b : rig->bones) {
      if (!b.selected) {
        continue;
      }
      bone_changes_from_values(b);
      json bj = {{"name", b.name},
                 {"transform", json_of(b.transform - b.position_keys.from_action_bones)},
                 {"turn", b.turn - b.angle_keys.from_action_bones},
                 {"scale", json_of(b.scale - b.scale_keys.from_action_bones)},
                 {"transform_add", json_of(b.position_keys.from_action_bones)},
                 {"turn_add", b.angle_keys.from_action_bones},
                 {"scale_add", json_of(b.scale_keys.from_action_bones)},
                 /* The setup its change is from: pasted back on its own bone layer's setup frame the pose becomes the
                  * setup, so a second paste there changes nothing. */
                 {"setup_position", json_of(b.setup_position)},
                 {"setup_angle", b.setup_angle}};
      /* A knob's place is a distance, its frames times its box's size: kept with it, so it goes back on the same
       * frames of a knob whose size is another (its other side's, or its own after the box is zoomed). */
      if (bone_is_controller(b)) {
        bj["frame_size"] = controller_unit(b);
      }
      bones.push_back(std::move(bj));
    }
    if (!bones.empty()) {
      *r_bones += int(bones.size());
      layers.push_back({{"id", rig->id}, {"name", rig->name}, {"bones", std::move(bones)}});
    }
  }
  for (Layer *l : drawings) {
    VectorDrawing d = l->drawing;
    drawing_changes_from_values(d);
    std::vector<Transform2D> skins = layer_point_skins(doc, *l);
    skins.resize(d.points.size());
    json points = json::array(), curve_points = json::array();
    std::set<int> picked;
    for (size_t i = 0; i < d.points.size(); i++) {
      const MeshPoint &p = d.points[i];
      if (!p.selected || p.detail.level > 0) {
        continue;
      }
      picked.insert(int(i));
      points.push_back({{"id", p.id},
                        {"index", i},
                        {"key", json_of(p.transform - p.pos_keys.from_action_bones)},
                        {"radius", p.radius - p.radius_keys.from_action_bones},
                        {"shown", json_of(skins[i].apply(p.pos))},
                        {"key_add", json_of(p.pos_keys.from_action_bones)},
                        {"radius_add", p.radius_keys.from_action_bones},
                        {"setup", json_of(p.setup_pos)}});
    }
    for (size_t c = 0; c < d.curves.size(); c++) {
      for (size_t j = 0; j < d.curves[c].points.size(); j++) {
        const CurvePoint &cp = d.curves[c].points[j];
        if (!picked.count(cp.point)) {
          continue;
        }
        json h = {{"curve", c},
                  {"index", j},
                  {"point", d.points[size_t(cp.point)].id},
                  {"curvature", cp.curvature - cp.curvature_keys.from_action_bones},
                  {"curvature_add", cp.curvature_keys.from_action_bones}};
        /* What each handle reaches for, so a flipped paste finds the mirror image's handle that reaches for its image. */
        int before = -1, after = -1;
        curve_neighbours(d.curves[c], j, before, after);
        if (before >= 0) {
          h["in_to"] = d.points[size_t(before)].id;
        }
        if (after >= 0) {
          h["out_to"] = d.points[size_t(after)].id;
        }
        /* A handle the curve works out for itself follows the points it is worked out from. */
        if (cp.handles_set) {
          const Transform2D &skin = skins[size_t(cp.point)];
          h["in"] = json_of(cp.change_in - cp.handle_in_keys.from_action_bones);
          h["out"] = json_of(cp.change_out - cp.handle_out_keys.from_action_bones);
          h["in_add"] = json_of(cp.handle_in_keys.from_action_bones);
          h["out_add"] = json_of(cp.handle_out_keys.from_action_bones);
          h["setup_in"] = json_of(cp.setup_in);
          h["setup_out"] = json_of(cp.setup_out);
          h["in_shown"] = json_of(skin.apply_vector(cp.handle_in));
          h["out_shown"] = json_of(skin.apply_vector(cp.handle_out));
        }
        curve_points.push_back(std::move(h));
      }
    }
    if (!points.empty()) {
      *r_points += int(points.size());
      layers.push_back({{"id", l->id},
                        {"name", l->name},
                        {"count", d.points.size()},
                        {"points", std::move(points)},
                        {"curve_points", std::move(curve_points)}});
    }
  }
  return {{"frame", doc.frame_current}, {"layers", std::move(layers)}};
}

json pose_copy_json(Context &C, int *r_bones, int *r_points)
{
  return pose_record(*C.document, pose_rigs(C), pose_drawings(C), r_bones, r_points);
}

/* Every drawing a pose kept in the file can go back on, being edited or not. */
static std::vector<Layer *> pose_all_drawings(Document &doc)
{
  std::vector<Layer *> out;
  for (const Layer *l : document_layers_flat(doc)) {
    if (l->type == LayerType::Vector && !l->is_reference()) {
      out.push_back(layer_find(doc, l->id));
    }
  }
  return out;
}

/* Paste As (a pick-one) and Keep Place, kept from the last time they were set, as the timeline's Paste Keys keeps
 * them. */
/* Same Place: a point or handle showing this close to where it was copied is already there. */
static constexpr float SAME_PLACE_HAIR = 1e-5f;
static PasteAs g_paste_as = PasteAs::Keys;
static bool g_pose_keep_place = false;
static bool g_pose_keep_poses = false;

static const char *paste_as_id(PasteAs as)
{
  return as == PasteAs::Look ? "LOOK" : as == PasteAs::Place ? "PLACE" : "KEYS";
}

/* Paste As from the operator's arguments, kept for the next paste; ignore_bones=1 (Ignore Bones, its old name) is Same
 * Place, 0 Keys. */
static PasteAs paste_as_take(Context &C)
{
  if (op_has_arg(C, "paste_as")) {
    const std::string as = op_arg(C, "paste_as");
    g_paste_as = as == "LOOK" ? PasteAs::Look : as == "PLACE" ? PasteAs::Place : PasteAs::Keys;
  }
  else if (op_has_arg(C, "ignore_bones")) {
    g_paste_as = op_arg_bool(C, "ignore_bones") ? PasteAs::Place : PasteAs::Keys;
  }
  op_arg_used(C, "paste_as", paste_as_id(g_paste_as));
  return g_paste_as;
}

static const char *paste_as_name(PasteAs as)
{
  return as == PasteAs::Look ? "Same Look" : as == PasteAs::Place ? "Same Place" : "Keys";
}

/* A copied value: its keys' change, with what the actions added where it was copied when `look` (Same Look, Same
 * Place). */
static float2 copied2(const json &j, const char *key, const char *add, bool look)
{
  return float2_of(j[key]) + (look && j.contains(add) ? float2_of(j[add]) : float2());
}

static float copied1(const json &j, const char *key, const char *add, bool look)
{
  return float_of(j, key) + (look ? float_of(j, add) : 0.0f);
}

/* What the actions add here, put back into the value pasted (Keys), or not (Same Look: the value is how it looked, and
 * recording takes what they add here out of its key). */
template<typename T> static T added_here(const Channel<T> &ch, bool look)
{
  return look ? T{} : ch.from_action_bones;
}

static bool remembered_arg(Context &C, const char *name, bool &kept)
{
  if (op_has_arg(C, name)) {
    kept = op_arg_bool(C, name);
  }
  op_arg_used(C, name, kept ? "1" : "0");
  return kept;
}

/* Each copied drawing's points matched with a drawing being edited here: by id, else by order in one with as many
 * points. */
struct PoseTarget {
  Layer *layer;
  const json *copied;
  std::map<uint64_t, size_t> points;
  /* Flipped: the drawing the pose was copied from (the target is its partner, _L for _R, or itself), every one of its
   * points' image in the target (by id; -1 for none), and its space reflected into the target's. */
  Layer *source = nullptr;
  std::map<uint64_t, int> image;
  Transform2D to;
};

/* Flipped: a copied drawing's pose goes on its partner (by _L and _R name, else itself), each point on its mirror image
 * (where it is in the setup pose reflected, as mirror editing pairs them). The copied drawing must be in this file. */
static bool pose_target_flipped(Document &doc, const std::vector<Layer *> &drawings, const json &lj, PoseTarget &t)
{
  const uint64_t id = lj.value("id", uint64_t(0));
  const std::string name = lj.value("name", std::string());
  Layer *source = layer_find(doc, id);
  if (!source || source->name != name) {
    source = nullptr;
    for (const Layer *l : document_layers_flat(doc)) {
      if (l->name == name && l->type == LayerType::Vector && !l->is_reference()) {
        source = layer_find(doc, l->id);
        break;
      }
    }
  }
  if (!source || source->type != LayerType::Vector) {
    return false;
  }
  Layer *partner = source;
  if (const std::string other = bone_mirror_name(source->name); other != source->name) {
    for (const Layer *l : document_layers_flat(doc)) {
      if (l->name == other && l->type == LayerType::Vector && !l->is_reference()) {
        partner = layer_find(doc, l->id);
        break;
      }
    }
  }
  /* Itself, it must be one being edited; a partner is the other side of one that is. */
  if (partner == source && std::find(drawings.begin(), drawings.end(), source) == drawings.end()) {
    return false;
  }
  t.layer = partner;
  t.source = source;
  t.to = layer_mirror_to_partner(doc, source->id, partner->id);
  std::vector<int> all(source->drawing.points.size());
  for (size_t i = 0; i < all.size(); i++) {
    all[i] = int(i);
  }
  const std::vector<int> images = layer_mirror_images(doc, *source, *partner, all);
  for (size_t i = 0; i < all.size() && i < images.size(); i++) {
    t.image[source->drawing.points[i].id] = images[i];
  }
  for (const json &pj : lj["points"]) {
    const auto it = t.image.find(pj.value("id", uint64_t(0)));
    if (it != t.image.end() && it->second >= 0) {
      t.points[it->first] = size_t(it->second);
    }
  }
  return true;
}

static std::vector<PoseTarget> pose_targets(Document &doc, const std::vector<Layer *> &drawings, const json &copied,
                                            bool flipped = false)
{
  std::vector<PoseTarget> targets;
  for (const json &lj : copied) {
    if (!lj.contains("points")) {
      continue;
    }
    if (flipped) {
      PoseTarget t{nullptr, &lj, {}};
      if (!pose_target_flipped(doc, drawings, lj, t)) {
        continue;
      }
      if (!t.points.empty()) {
        targets.push_back(std::move(t));
      }
      continue;
    }
    const uint64_t id = lj.value("id", uint64_t(0));
    const std::string name = lj.value("name", std::string());
    auto it = std::find_if(drawings.begin(), drawings.end(), [&](const Layer *l) { return l->id == id; });
    if (it == drawings.end()) {
      it = std::find_if(drawings.begin(), drawings.end(), [&](const Layer *l) { return l->name == name; });
    }
    if (it == drawings.end()) {
      continue;
    }
    PoseTarget t{*it, &lj, {}};
    std::map<uint64_t, size_t> here;
    for (size_t i = 0; i < t.layer->drawing.points.size(); i++) {
      here[t.layer->drawing.points[i].id] = i;
    }
    for (const json &pj : lj["points"]) {
      const auto found = here.find(pj.value("id", uint64_t(0)));
      if (found != here.end()) {
        t.points[pj.value("id", uint64_t(0))] = found->second;
      }
    }
    if (t.points.empty() && lj.value("count", size_t(0)) == t.layer->drawing.points.size()) {
      for (const json &pj : lj["points"]) {
        t.points[pj.value("id", uint64_t(0))] = pj.value("index", size_t(0));
      }
    }
    if (!t.points.empty()) {
      targets.push_back(std::move(t));
    }
  }
  return targets;
}

/* The bone layer a copied one's bones paste onto: among the active one and its sub bone groups the one copied from (by
 * id, else name), else the active one (a pose copied from another character); `anywhere`, the one it was copied from
 * found anywhere (by id, else name). */
static Layer *pose_rig_for(Context &C, const json &lj, bool anywhere)
{
  Layer *active_rig = pose_rig(C);
  if (!anywhere && active_rig) {
    const std::vector<Layer *> family = pose_rigs(C);
    const auto same = [&](auto pred) { return std::find_if(family.begin(), family.end(), pred); };
    auto it = same([&](const Layer *l) { return l->id == lj.value("id", uint64_t(0)); });
    if (it == family.end()) {
      it = same([&](const Layer *l) { return l->name == lj.value("name", std::string()); });
    }
    if (it != family.end()) {
      active_rig = *it;
    }
  }
  if (anywhere) {
    Document &doc = *C.document;
    Layer *by_id = layer_find(doc, lj.value("id", uint64_t(0)));
    active_rig = by_id && by_id->is_bone_layer() ? by_id : nullptr;
    const std::string name = lj.value("name", std::string());
    for (const Layer *l : document_layers_flat(doc)) {
      if (!active_rig && l->is_bone_layer() && l->name == name) {
        active_rig = layer_find(doc, l->id);
      }
    }
  }
  if (!active_rig) {
    return nullptr;
  }
  for (const json &bj : lj["bones"]) {
    if (bone_named(*active_rig, bj.value("name", std::string()))) {
      return active_rig;
    }
  }
  return nullptr;
}

/* Whether a copied pose has bones or points here to paste onto: else Ctrl V pastes the shapes copied with it. */
static bool pose_has_target(Context &C, const json &pose, bool flipped)
{
  const json &copied = pose["layers"];
  if (!copied.is_array()) {
    return false;
  }
  if (!pose_targets(*C.document, pose_drawings(C), copied, flipped).empty()) {
    return true;
  }
  return std::any_of(copied.begin(), copied.end(),
                     [&](const json &lj) { return lj.contains("bones") && pose_rig_for(C, lj, false); });
}

/* A flipped paste's handles and curvature: each copied handle goes on its point's image's handle that reaches for the
 * image of what it reached for (mirrored, a curve can run the other way), reflected. */
static void pose_paste_handles_flipped(PoseTarget &t, const VectorDrawing &from, const VectorDrawing &to_was,
                                       const std::vector<Transform2D> &skins, bool ignore, bool look, float factor)
{
  VectorDrawing &d = t.layer->drawing;
  const auto image_of = [&](const json &cj, const char *name) {
    if (!cj.contains(name)) {
      return -1;
    }
    const auto it = t.image.find(cj.value(name, uint64_t(0)));
    return it == t.image.end() ? -1 : it->second;
  };
  for (const json &cj : (*t.copied)["curve_points"]) {
    const auto m = t.points.find(cj.value("point", uint64_t(0)));
    const size_t c = cj.value("curve", size_t(0)), j = cj.value("index", size_t(0));
    if (m == t.points.end() || c >= from.curves.size() || j >= from.curves[c].points.size()) {
      continue;
    }
    const CurvePoint &was = from.curves[c].points[j];
    const int reach_in = image_of(cj, "in_to"), reach_out = image_of(cj, "out_to");
    bool curvature_done = false;
    for (size_t ci = 0; ci < d.curves.size(); ci++) {
      Curve &curve = d.curves[ci];
      for (size_t k = 0; k < curve.points.size(); k++) {
        CurvePoint &cp = curve.points[k];
        const CurvePoint &cp_was = k < to_was.curves[ci].points.size() ? to_was.curves[ci].points[k] : cp;
        if (size_t(cp.point) != m->second) {
          continue;
        }
        int before = -1, after = -1;
        curve_neighbours(curve, k, before, after);
        /* Which copied handle each of this one's goes from: the one reaching for the image of its neighbour. */
        const auto source_side = [&](int neighbour) -> int {
          if (neighbour < 0) {
            return -1;
          }
          return neighbour == reach_in ? 1 : neighbour == reach_out ? 0 : -1;
        };
        const int for_in = source_side(before), for_out = source_side(after);
        if (for_in < 0 && for_out < 0) {
          continue;
        }
        if (!curvature_done) {
          const float curvature = copied1(cj, "curvature", "curvature_add", look) + added_here(cp.curvature_keys, look);
          cp.curvature = cp.curvature + (curvature - cp.curvature) * factor;
          curvature_done = true;
        }
        if (!cj.contains("in") || !cp.handles_set) {
          continue;
        }
        const Transform2D &skin = skins[m->second];
        for (const bool in : {true, false}) {
          const int side = in ? for_in : for_out;
          if (side < 0) {
            continue;
          }
          const bool from_in = side == 1;
          float2 handle;
          if (ignore && invertible(skin)) {
            handle = skin.inverted().apply_vector(t.to.apply_vector(float2_of(cj[from_in ? "in_shown" : "out_shown"])));
          }
          else {
            const float2 reflected = t.to.apply_vector(
                handle_from_change(from_in ? was.setup_in : was.setup_out,
                                   copied2(cj, from_in ? "in" : "out", from_in ? "in_add" : "out_add", look), from_in));
            const float2 setup = in ? cp_was.setup_in : cp_was.setup_out;
            const Channel<float2> &ch = in ? cp.handle_in_keys : cp.handle_out_keys;
            const float2 change = handle_change(setup, reflected, (in ? cp.change_in : cp.change_out).x, in);
            handle = handle_from_change(setup, change + added_here(ch, look), in);
          }
          float2 &h = in ? cp.handle_in : cp.handle_out;
          h = h + (handle - h) * factor;
        }
      }
    }
  }
}

OpStatus pose_apply(Context &C, const json &pose, bool flipped, const PoseApplyOptions &options)
{
  Document &doc = *C.document;
  if (doc.frame_current == 0 && !options.setup_frame) {
    report(ReportType::Warning, options.anywhere ? "Poses go on frames other than the setup frame (frame 0)"
                                                 : "Paste Pose poses: go to a frame other than the setup frame (frame 0)");
    return OpStatus::Cancelled;
  }
  const bool selected_only = options.selected_only;
  const float factor = options.factor;
  const bool ignore = options.as == PasteAs::Place;
  const bool look = options.as != PasteAs::Keys;
  /* Same Place puts each point where it was: there is no place of its own to keep. */
  const bool keep_place = options.keep_place && !ignore;
  const auto copied_it = pose.find("layers");
  if (copied_it == pose.end() || !copied_it->is_array()) {
    return OpStatus::Cancelled;
  }
  const json &copied = *copied_it;
  /* A second pass on the setup frame keeps the first's targets: the first moved the setup, by which a flipped paste
   * finds each point's mirror image. */
  std::vector<PoseTarget> targets;
  if (options.targets_kept && *options.targets_kept) {
    targets = *std::static_pointer_cast<std::vector<PoseTarget>>(*options.targets_kept);
  }
  else {
    targets = pose_targets(doc, options.anywhere ? pose_all_drawings(doc) : pose_drawings(C), copied, flipped);
    if (options.targets_kept) {
      *options.targets_kept = std::make_shared<std::vector<PoseTarget>>(targets);
    }
  }
  /* What it pastes against: each bone's and point's setup as it was before a first pass on the setup frame (which
   * moved it), else as it is. */
  const auto was_layer = [&](const Layer &l) -> const Layer & {
    if (options.setup_was) {
      const auto it = options.setup_was->find(l.id);
      if (it != options.setup_was->end()) {
        return it->second;
      }
    }
    return l;
  };
  /* On its own layer's setup frame the copied pose becomes the setup: its changes from the setup they were copied
   * from (so a second paste there changes nothing; Paste Keys does the same). */
  const bool own_setup = options.setup_frame && doc.frame_current == 0 && !flipped;
  const auto own = [&](const Layer &l, const json &lj) { return own_setup && l.id == lj.value("id", uint64_t(0)); };
  const auto was_drawing = [&](const Layer &l) -> const VectorDrawing & {
    const VectorDrawing &d = was_layer(l).drawing;
    return d.points.size() == l.drawing.points.size() && d.curves.size() == l.drawing.curves.size() ? d : l.drawing;
  };

  /* The bones each copied bone layer's go onto. */
  struct Onto {
    Layer *rig;
    const json *copied;
    std::vector<std::pair<Bone *, const json *>> bones;
  };
  std::vector<Onto> ontos;
  for (const json &lj : copied) {
    if (!lj.contains("bones")) {
      continue;
    }
    Layer *rig = pose_rig_for(C, lj, options.anywhere);
    if (!rig) {
      continue;
    }
    Onto o{rig, &lj, {}};
    for (const json &bj : lj["bones"]) {
      const std::string name = bj.value("name", std::string());
      Bone *b = flipped ? bone_named(*rig, bone_mirror_name(name)) : nullptr;
      if (Bone *same = bone_named(*rig, name); !b) {
        b = same;
      }
      if (b) {
        o.bones.push_back({b, &bj});
      }
    }
    ontos.push_back(std::move(o));
  }
  /* On Selected Only: onto the copied bones and points selected now, or all of them if none is (as Blender's), the
   * selection counted across every bone layer and drawing (the teeth's sub bone group with the face's), not one at a
   * time. */
  if (selected_only) {
    bool any = false;
    for (const Onto &o : ontos) {
      any = any || std::any_of(o.bones.begin(), o.bones.end(), [](const auto &b) { return b.first->selected; });
    }
    for (const PoseTarget &t : targets) {
      any = any || std::any_of(t.points.begin(), t.points.end(),
                               [&](const auto &m) { return t.layer->drawing.points[m.second].selected; });
    }
    if (any) {
      for (Onto &o : ontos) {
        std::erase_if(o.bones, [](const auto &b) { return !b.first->selected; });
      }
      for (PoseTarget &t : targets) {
        std::erase_if(t.points, [&](const auto &m) { return !t.layer->drawing.points[m.second].selected; });
      }
      std::erase_if(targets, [](const PoseTarget &t) { return t.points.empty(); });
    }
  }

  /* Keep Place: where the pasted points' centre shows now, before anything moves (the bones pasted too). */
  float2 centre_was;
  int centre_count = 0;
  if (keep_place) {
    for (PoseTarget &t : targets) {
      std::vector<Transform2D> skins = layer_point_skins(doc, *t.layer);
      skins.resize(t.layer->drawing.points.size());
      const Transform2D world = layer_world_transform(doc, t.layer->id);
      for (const auto &[pid, i] : t.points) {
        centre_was += (world * skins[i]).apply(t.layer->drawing.points[i].pos);
        centre_count++;
      }
    }
  }

  /* The bones first: the points' skins, for Ignore Bones and Keep Place, are the pasted pose's. */
  int bones_pasted = 0;
  for (Onto &o : ontos) {
    Layer *rig = o.rig;
    const Layer &rig_was = was_layer(*rig);
    /* Flipped: each copied bone's pose goes on its other side (by _L and _R name, else itself), reflected across the
     * bone layer's vertical axis: its Transform through both bones' setups, its turn the other way. */
    /* (Posed: each pose's `setup` is then its setup pose, not this frame's pose shown as one.) */
    const std::vector<BonePose> setups = flipped ? armature_pose(rig_was, false) : std::vector<BonePose>();
    const Transform2D flip{-1.0f, 0.0f, 0.0f, 1.0f, 0.0f, 0.0f};
    for (auto &[b, bj] : o.bones) {
      bone_changes_from_values(*b);
      float2 copied_transform = copied2(*bj, "transform", "transform_add", look);
      float copied_turn = copied1(*bj, "turn", "turn_add", look);
      if (bone_is_controller(*b) && float_of(*bj, "frame_size") > 0.0f) {
        copied_transform = copied_transform * (controller_unit(*b) / float_of(*bj, "frame_size"));
      }
      if (flipped) {
        const Bone *from_bone = bone_named(*rig, bj->value("name", std::string()));
        const BonePose *from = from_bone ? bone_pose_find(setups, from_bone->id) : nullptr;
        const BonePose *to = bone_pose_find(setups, b->id);
        /* A knob's box mirrors with Left and Right swapped (as Symmetrize's). */
        if (bone_is_controller(*b) && from_bone && bone_is_controller(*from_bone)) {
          copied_transform.x = -copied_transform.x;
        }
        else if (from && to) {
          copied_transform = (to->setup.inverted() * flip * from->setup).apply_vector(copied_transform);
        }
        copied_turn = -copied_turn;
      }
      float2 transform = copied_transform + added_here(b->position_keys, look);
      float turn = copied_turn + added_here(b->angle_keys, look);
      /* Against the setup as it was (its change put on once), worked into the setup as it is now. */
      const Bone *was = bone_find(rig_was, b->id);
      Bone copied_setup;
      if (own(*rig, *o.copied) && bj->contains("setup_angle")) {
        copied_setup = *b;
        copied_setup.setup_position = float2_of((*bj)["setup_position"]);
        copied_setup.setup_angle = float_of(*bj, "setup_angle");
        was = &copied_setup;
      }
      if (was && was != b) {
        transform = bone_transform_from_position(*b, bone_position_from_transform(*was, transform));
        turn += was->setup_angle - b->setup_angle;
      }
      const float2 scale = copied2(*bj, "scale", "scale_add", look) + added_here(b->scale_keys, look);
      b->transform = b->transform + (transform - b->transform) * factor;
      b->turn = b->turn + (turn - b->turn) * factor;
      b->scale = b->scale + (scale - b->scale) * factor;
      bone_values_from_changes(*b);
      bones_pasted++;
      if (options.r_bones) {
        options.r_bones->push_back({rig->id, b->id});
      }
    }
  }

  /* Then the points: each where its key puts it here, or with Ignore Bones where it showed when copied. */
  struct Placed {
    Layer *layer;
    size_t point;
    float2 pos;
  };
  std::vector<Placed> placed;
  std::map<Layer *, std::vector<Transform2D>> skins_of;
  for (PoseTarget &t : targets) {
    VectorDrawing &d = t.layer->drawing;
    drawing_changes_from_values(d);
    std::vector<Transform2D> &skins = skins_of[t.layer];
    skins = layer_point_skins(doc, *t.layer);
    skins.resize(d.points.size());
    for (const json &pj : (*t.copied)["points"]) {
      const auto m = t.points.find(pj.value("id", uint64_t(0)));
      if (m == t.points.end()) {
        continue;
      }
      MeshPoint &p = d.points[m->second];
      const Transform2D &skin = skins[m->second];
      /* Flipped: the change and where it showed reflected into the target (`to` is the identity otherwise). */
      const float2 shown = t.to.apply(float2_of(pj["shown"]));
      const float2 key = t.to.apply_vector(copied2(pj, "key", "key_add", look));
      /* Same Place, already showing there (pasted on the frame it was copied on), stays as it is: worked back through
       * its skin it came out a hair off, and recording took the hair for an edit (keys on what never moved). */
      const float2 pos = ignore && invertible(skin) ?
                             (distance(skin.apply(p.pos), shown) < SAME_PLACE_HAIR ? p.pos : skin.inverted().apply(shown)) :
                             (own(*t.layer, *t.copied) && pj.contains("setup") ?
                                  float2_of(pj["setup"]) :
                                  was_drawing(*t.layer).points[m->second].setup_pos) +
                                 key + added_here(p.pos_keys, look);
      placed.push_back({t.layer, m->second, pos});
      const float radius = copied1(pj, "radius", "radius_add", look) + added_here(p.radius_keys, look);
      p.radius = p.radius + (radius - p.radius) * factor;
    }
    if (t.source) {
      pose_paste_handles_flipped(t, was_drawing(*t.source), was_drawing(*t.layer), skins, ignore, look, factor);
      continue;
    }
    for (const json &cj : (*t.copied)["curve_points"]) {
      const auto m = t.points.find(cj.value("point", uint64_t(0)));
      const size_t c = cj.value("curve", size_t(0)), j = cj.value("index", size_t(0));
      if (m == t.points.end() || c >= d.curves.size() || j >= d.curves[c].points.size() ||
          size_t(d.curves[c].points[j].point) != m->second)
      {
        continue;
      }
      CurvePoint &cp = d.curves[c].points[j];
      const CurvePoint &cp_was = was_drawing(*t.layer).curves[c].points[j];
      const float curvature = copied1(cj, "curvature", "curvature_add", look) + added_here(cp.curvature_keys, look);
      cp.curvature = cp.curvature + (curvature - cp.curvature) * factor;
      if (!cj.contains("in") || !cp.handles_set) {
        continue;
      }
      const Transform2D &skin = skins[m->second];
      for (const bool in : {true, false}) {
        float2 handle;
        if (ignore && invertible(skin)) {
          const float2 shown = float2_of(cj[in ? "in_shown" : "out_shown"]);
          const float2 now = in ? cp.handle_in : cp.handle_out;
          handle = distance(skin.apply_vector(now), shown) < SAME_PLACE_HAIR ? now : skin.inverted().apply_vector(shown);
        }
        else {
          const Channel<float2> &ch = in ? cp.handle_in_keys : cp.handle_out_keys;
          const char *setup_key = in ? "setup_in" : "setup_out";
          handle = handle_from_change(own(*t.layer, *t.copied) && cj.contains(setup_key) ? float2_of(cj[setup_key]) :
                                      in                                                  ? cp_was.setup_in :
                                                                                            cp_was.setup_out,
                                      copied2(cj, in ? "in" : "out", in ? "in_add" : "out_add", look) + added_here(ch, look),
                                      in);
        }
        float2 &h = in ? cp.handle_in : cp.handle_out;
        h = h + (handle - h) * factor;
      }
    }
  }
  /* Keep Place: the pasted shape moved as one, its centre showing where the points' centre did. */
  if (keep_place && centre_count > 0 && !placed.empty()) {
    float2 centre_now;
    for (const Placed &p : placed) {
      centre_now += (layer_world_transform(doc, p.layer->id) * skins_of[p.layer][p.point]).apply(p.pos);
    }
    const float2 shift = centre_was / float(centre_count) - centre_now / float(placed.size());
    for (Placed &p : placed) {
      const Transform2D to_shown = layer_world_transform(doc, p.layer->id) * skins_of[p.layer][p.point];
      if (invertible(to_shown)) {
        p.pos = to_shown.inverted().apply(to_shown.apply(p.pos) + shift);
      }
    }
  }
  for (const Placed &p : placed) {
    MeshPoint &mp = p.layer->drawing.points[p.point];
    mp.pos = mp.pos + (p.pos - mp.pos) * factor;
    if (options.r_points) {
      options.r_points->push_back({p.layer->id, p.point});
    }
  }
  for (PoseTarget &t : targets) {
    drawing_changes_from_values(t.layer->drawing);
  }
  const int points_pasted = int(placed.size());
  if (bones_pasted + points_pasted == 0) {
    if (options.warn) {
      report(ReportType::Warning, options.anywhere ? "None of the pose's bones and points is here"
                                                   : "The copied pose's bones and points aren't being edited here");
    }
    return OpStatus::Cancelled;
  }
  std::string note;
  if (bones_pasted > 0) {
    note = std::to_string(bones_pasted) + (bones_pasted == 1 ? " bone" : " bones");
  }
  if (points_pasted > 0) {
    note += (note.empty() ? "" : ", ") + std::to_string(points_pasted) + (points_pasted == 1 ? " point" : " points");
  }
  if (!options.quiet) {
    op_note("Pasted onto " + note + " as " + paste_as_name(options.as));
    report(ReportType::Info, "Pasted onto " + note + " as " + paste_as_name(options.as));
  }
  return OpStatus::Finished;
}

static OpStatus pose_paste(Context &C, const json &pose, bool flipped)
{
  /* Same Look and Same Place take out of each value what the action bone actions add here, and the paste moves the
   * bones that drive them (a knob): worked out again with what they add once it is pasted, one press gives the look
   * (it took two). With a factor below 1 a second pass would blend twice: one, as before. */
  PoseApplyOptions options;
  options.as = paste_as_take(C);
  options.selected_only = op_arg_bool(C, "selected_mask");
  options.factor = op_arg_float(C, "factor", 1.0f);
  options.keep_place = remembered_arg(C, "keep_place", g_pose_keep_place);
  /* On the setup frame the pose becomes the setup pose, as a move there does; Keep Poses as a move's: the other frames'
   * keyed poses stay where they are, the change taken off their keys. */
  Document &doc = *C.document;
  options.setup_frame = true;
  const bool setup = doc.frame_current == 0;
  op_arg_used(C, "setup", setup ? "1" : "0");
  const bool keep = remembered_arg(C, "keep_poses", g_pose_keep_poses) && setup;
  SetupSnapshot before;
  if (keep) {
    std::vector<uint64_t> ids;
    for (const Layer *l : pose_rigs(C)) {
      ids.push_back(l->id);
    }
    for (const Layer *l : pose_drawings(C)) {
      ids.push_back(l->id);
    }
    before = setup_snapshot(doc, ids);
  }
  const auto kept = [&](OpStatus status) {
    if (status == OpStatus::Finished && !before.empty()) {
      animation_record(doc);
      keep_poses(doc, before);
    }
    return status;
  };
  const bool again = options.as != PasteAs::Keys && options.factor >= 1.0f;
  options.quiet = again;
  /* On the setup frame the first pass's recording moves the setup: the second pastes against the setup as it was
   * (its change put on once, not twice) onto the first's targets. */
  std::map<uint64_t, Layer> setup_was;
  std::shared_ptr<void> targets_kept;
  if (again && setup) {
    for (Layer *l : pose_rigs(C)) {
      setup_was.emplace(l->id, *l);
    }
    /* Flipped, the drawings copied from and their partners anywhere. */
    for (const Layer *l : document_layers_flat(doc)) {
      if (l->type == LayerType::Vector && !l->is_reference()) {
        setup_was.emplace(l->id, *l);
      }
    }
    options.targets_kept = &targets_kept;
  }
  const OpStatus status = pose_apply(C, pose, flipped, options);
  if (status != OpStatus::Finished || !again) {
    return kept(status);
  }
  animation_record(doc);
  animation_evaluate(doc, doc.frame_current);
  options.quiet = false;
  if (setup) {
    options.setup_was = &setup_was;
  }
  return kept(pose_apply(C, pose, flipped, options));
}

/* The pose on the clipboard (null json if none). */
static json clipboard_pose()
{
  const std::string text = clipboard_text();
  if (text.find(POSE_CLIPBOARD_KEY) == std::string::npos) {
    return json();
  }
  json root = json::parse(text, nullptr, false);
  if (root.is_discarded() || !root.is_object() || !root.contains("pose")) {
    return json();
  }
  return std::move(root["pose"]);
}

/* Paste As: what a paste gives, one of three (Keys, Same Look, Same Place), kept for the next paste. */
static OpProperty paste_as_property()
{
  OpProperty p;
  p.name = "paste_as";
  p.label = "Paste As";
  p.description = "What the paste gives: the keys copied, the look, or the place it had";
  p.items = {{"KEYS", "Keys"}, {"LOOK", "Same Look"}, {"PLACE", "Same Place"}};
  p.item_descriptions = {
      "Keys: the keys you copied. What actions add here still comes on top, as they move it here",
      "Same Look: it looks just as it did when copied, and moves with the bones here",
      "Same Place: it stays exactly where it was on screen when copied, wherever the bones are now"};
  p.fallback = "KEYS";
  p.expand = true;
  return p;
}

/* Keep Poses, shown for a paste on the setup frame (setup=1): as a move's there. */
static OpProperty keep_poses_property()
{
  OpProperty p = op_bool_property("keep_poses", "Keep Poses",
                                  "On the setup frame: other frames' keyed poses stay where they are, the paste "
                                  "changing only the setup pose (its change taken off every key on another frame)",
                                  "0");
  p.visible = [](const OpArgs &args) {
    const auto it = args.find("setup");
    return it != args.end() && it->second == "1";
  };
  return p;
}

static OpProperty keep_place_property()
{
  OpProperty p = op_bool_property("keep_place", "Keep Place",
                                  "Paste the shape only: the pasted points keep the place their centre has on this "
                                  "frame (not with Same Place, which puts them where they were)",
                                  "0");
  p.active = [](const OpArgs &args) {
    const auto it = args.find("paste_as");
    return it == args.end() || it->second != "PLACE";
  };
  return p;
}

void pose_clipboard_operators_register()
{
  {
    OperatorType ot;
    ot.idname = "pose.copy";
    ot.name = "Copy Pose";
    ot.description = "Copy the selected bones' and points' pose on this frame to the clipboard (Ctrl C over the "
                     "viewport off the setup frame), to paste on another frame, in another action or file";
    ot.flag = OPTYPE_REGISTER;
    ot.poll = [](Context &C) { return C.document && C.document->frame_current != 0 && pose_anything_selected(C); };
    ot.exec = [](Context &C) {
      int bones = 0, points = 0;
      const json pose = pose_copy_json(C, &bones, &points);
      if (bones + points == 0) {
        report(ReportType::Warning, "Select bones or points to copy their pose");
        return OpStatus::Cancelled;
      }
      /* With it the shapes, as Copy Shapes would copy them, for Ctrl V where these bones and points aren't. */
      json root;
      if (shapes_copy_to_clipboard(C) > 0) {
        root = json::parse(clipboard_text(), nullptr, false);
      }
      if (!root.is_object()) {
        root = json::object();
      }
      root[POSE_CLIPBOARD_KEY] = 1;
      root["pose"] = pose;
      clipboard_text_set(root.dump());
      std::string what;
      if (bones > 0) {
        what = std::to_string(bones) + (bones == 1 ? " bone" : " bones");
      }
      if (points > 0) {
        what += (what.empty() ? "" : " and ") + std::to_string(points) + (points == 1 ? " point" : " points");
      }
      report(ReportType::Info, "Copied the pose of " + what);
      return OpStatus::Finished;
    };
    operators().add(std::move(ot));
  }
  /* Paste Pose, and Paste Pose Flipped (Ctrl Shift V): the same with Flipped on, as Blender's. */
  for (const bool flipped : {false, true}) {
    OperatorType ot;
    ot.idname = flipped ? "pose.paste_flipped" : "pose.paste";
    ot.name = flipped ? "Paste Pose Flipped" : "Paste Pose";
    ot.description =
        flipped ? "Paste the copied pose mirrored left to right (Ctrl Shift V over the viewport): each _L bone's or "
                  "drawing's pose on its _R partner and the other way, the rest on themselves, each point on its "
                  "mirror image"
                : "Paste the copied pose onto the same bones (by name) and points on this frame (Ctrl V over the "
                  "viewport); Auto Keying keys it. On the setup frame (frame 0) it becomes the setup pose, as a move "
                  "there does: keep_poses=1 leaves the other frames' keyed poses where they are. paste_as=KEYS: the keys copied, what the actions "
                  "here add coming on top; LOOK: as it looked, moving with the bones here; PLACE: where it showed, "
                  "whatever the bones and actions do here (ignore_bones=1, its old name). Kept for the next paste. "
                  "keep_place=1: the shape only, its centre staying where it is here. flipped=1: mirrored left to "
                  "right, as Paste Pose Flipped";
    ot.flag = OPTYPE_REGISTER | OPTYPE_UNDO;
    /* Only where the copied bones or points are (else Ctrl V pastes the shapes copied with them). On the setup frame
     * too: the pose becomes the setup pose. */
    ot.poll = [flipped](Context &C) {
      if (!C.document) {
        return false;
      }
      const json pose = clipboard_pose();
      return pose.is_object() && pose_has_target(C, pose, flipped);
    };
    ot.props = {
        op_bool_property("flipped", "Flipped on X-Axis",
                         "Mirrored left to right: _L and _R bones and drawings swap poses, each point onto its mirror "
                         "image",
                         flipped ? "1" : "0"),
        op_bool_property("selected_mask", "On Selected Only",
                         "Only paste onto the bones and points selected now (all of them when none is)", "0"),
        op_float_property("factor", "Factor", "How far from the pose shown to the copied one (0.5: halfway)", "1",
                          0.0f, 1.0f, 0.01f),
        paste_as_property(),
        keep_place_property(),
        keep_poses_property(),
    };
    ot.exec = [flipped](Context &C) {
      const json pose = clipboard_pose();
      if (!pose.is_object()) {
        report(ReportType::Warning, "Copy a pose first (Ctrl C over the viewport off the setup frame)");
        return OpStatus::Cancelled;
      }
      const bool flip = op_has_arg(C, "flipped") ? op_arg_bool(C, "flipped") : flipped;
      return pose_paste(C, pose, flip);
    };
    operators().add(std::move(ot));
  }
}

}  // namespace oanim
