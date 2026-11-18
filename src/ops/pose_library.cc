/* The pose library: poses kept in the file and shown on the Asset Shelf's Poses (editors/asset_shelf.cc), as Blender's
 * pose library keeps them on its asset shelf. A pose is Copy Pose's record (ops/pose_clipboard.cc) of the bones and
 * points selected when it was saved, filed under one of the document's collections: the shelf shows it while anything
 * in that collection is selected. Applying it is Paste Pose as Keys onto the bones and points it was saved from,
 * wherever they are in the file and whatever is active; Auto Keying keys it. */

#include "ops/pose_library.hh"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <set>

#include <nlohmann/json.hpp>

#include "anim/animation.hh"
#include "anim/controller_preview.hh"
#include "anim/deform.hh"
#include "core/log.hh"
#include "data/bones.hh"
#include "data/document.hh"
#include "ops/operator.hh"
#include "ops/pose_apply.hh"
#include "wm/context.hh"

namespace oanim {

using json = nlohmann::ordered_json;

PoseAsset *pose_asset_find(Document &doc, uint64_t id)
{
  for (PoseAsset &p : doc.poses) {
    if (p.id == id) {
      return &p;
    }
  }
  return nullptr;
}

const PoseAsset *pose_asset_find(const Document &doc, uint64_t id)
{
  return pose_asset_find(const_cast<Document &>(doc), id);
}

namespace {

std::string trimmed(const std::string &s)
{
  const auto first = s.find_first_not_of(" \t\r\n");
  if (first == std::string::npos) {
    return {};
  }
  return s.substr(first, s.find_last_not_of(" \t\r\n") - first + 1);
}

std::string lower(std::string s)
{
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return char(std::tolower(c)); });
  return s;
}

/* What saving a pose takes, as Copy Pose: the selected bones of the bone layer and its sub bone groups (each with its
 * bone layer), and the drawings with points selected. */
void selection(Context &C, std::vector<std::pair<Layer *, Bone *>> &r_bones, std::vector<Layer *> &r_drawings)
{
  for (Layer *rig : pose_rigs(C)) {
    for (Bone &b : rig->bones) {
      if (b.selected) {
        r_bones.push_back({rig, &b});
      }
    }
  }
  for (Layer *l : pose_drawings(C)) {
    if (std::any_of(l->drawing.points.begin(), l->drawing.points.end(),
                    [](const MeshPoint &p) { return p.selected && p.detail.level == 0; }))
    {
      r_drawings.push_back(l);
    }
  }
}

/* `name`, or with .001, .002... after it while another pose in the same collection has it. */
std::string unique_pose_name(const Document &doc, uint64_t collection, const std::string &name, uint64_t skip)
{
  const auto taken = [&](const std::string &n) {
    return std::any_of(doc.poses.begin(), doc.poses.end(),
                       [&](const PoseAsset &p) { return p.id != skip && p.collection == collection && p.name == n; });
  };
  if (!taken(name)) {
    return name;
  }
  for (int i = 1;; i++) {
    char suffix[16];
    std::snprintf(suffix, sizeof(suffix), ".%03d", i);
    if (!taken(name + suffix)) {
      return name + suffix;
    }
  }
}

/* The pose the operator's `pose` argument names (its id), warning when there is none. */
PoseAsset *pose_arg(Context &C)
{
  const std::string text = op_arg(C, "pose");
  PoseAsset *pose = text.empty() ? nullptr : pose_asset_find(*C.document, std::strtoull(text.c_str(), nullptr, 10));
  if (!pose) {
    report(ReportType::Warning, text.empty() ? "Which pose? (pose=<its id>)" : "No pose " + text);
  }
  return pose;
}

json pose_json(const PoseAsset &pose)
{
  json j = json::parse(pose.pose, nullptr, false);
  return j.is_object() ? j : json();
}

/* A collection by name ("" none, 0), else false (warned). */
bool collection_arg(Context &C, const char *name, uint64_t *r_id)
{
  const std::string text = trimmed(op_arg(C, name));
  *r_id = 0;
  if (text.empty()) {
    return true;
  }
  const Collection *c = collection_find_by_name(*C.document, text);
  if (!c) {
    report(ReportType::Warning, "No collection named " + text);
    return false;
  }
  *r_id = c->id;
  return true;
}

std::string what_text(int bones, int points)
{
  std::string what;
  if (bones > 0) {
    what = std::to_string(bones) + (bones == 1 ? " bone" : " bones");
  }
  if (points > 0) {
    what += (what.empty() ? "" : " and ") + std::to_string(points) + (points == 1 ? " point" : " points");
  }
  return what;
}

/* A copy of `doc` posed off frame 0 (frame 1 for frame 0, where poses don't go), and a Context on it. */
void off_setup_copy(const Document &doc, Document &r_copy)
{
  r_copy = doc;
  if (r_copy.frame_current == 0) {
    r_copy.frame_current = 1;
    animation_evaluate(r_copy, 1);
  }
}

/* Puts `pose` on a copy (flipped or not) and records exactly what it posed there: the pose, flipped. */
json pose_flipped_record(const Document &doc, const json &pose, int *r_bones, int *r_points)
{
  Document copy;
  off_setup_copy(doc, copy);
  Context C;
  C.document = &copy;
  std::vector<std::pair<uint64_t, uint64_t>> bones;
  std::vector<std::pair<uint64_t, size_t>> points;
  PoseApplyOptions options;
  options.anywhere = true;
  options.quiet = true;
  options.r_bones = &bones;
  options.r_points = &points;
  *r_bones = *r_points = 0;
  if (pose_apply(C, pose, true, options) != OpStatus::Finished) {
    return json();
  }
  /* Selected there: just what it posed. */
  std::vector<Layer *> rigs;
  for (const auto &[layer, bone] : bones) {
    Layer *rig = layer_find(copy, layer);
    if (std::find(rigs.begin(), rigs.end(), rig) == rigs.end()) {
      rigs.push_back(rig);
    }
  }
  for (Layer *rig : rigs) {
    for (Bone &b : rig->bones) {
      b.selected = std::find(bones.begin(), bones.end(), std::pair{rig->id, b.id}) != bones.end();
    }
  }
  std::vector<Layer *> drawings;
  for (const auto &[layer, i] : points) {
    Layer *l = layer_find(copy, layer);
    if (std::find(drawings.begin(), drawings.end(), l) == drawings.end()) {
      for (MeshPoint &p : l->drawing.points) {
        p.selected = false;
      }
      drawings.push_back(l);
    }
  }
  for (const auto &[layer, i] : points) {
    layer_find(copy, layer)->drawing.points[i].selected = true;
  }
  return pose_record(copy, rigs, drawings, r_bones, r_points);
}

/* Registers an undoable poselib operator. */
void poselib_operator(const char *idname, const char *name, const char *description, bool (*poll)(Context &),
                      OpStatus (*exec)(Context &), std::vector<OpProperty> props = {})
{
  OperatorType ot;
  ot.idname = idname;
  ot.name = name;
  ot.description = description;
  ot.flag = OPTYPE_REGISTER | OPTYPE_UNDO;
  ot.poll = poll;
  ot.exec = exec;
  ot.props = std::move(props);
  operators().add(std::move(ot));
}

bool has_document(Context &C)
{
  return C.document != nullptr;
}

bool has_selection(Context &C)
{
  return C.document && pose_anything_selected(C);
}

}  // namespace

std::vector<uint64_t> pose_selection_collections(Context &C)
{
  std::vector<uint64_t> out;
  if (!C.document) {
    return out;
  }
  std::vector<std::pair<Layer *, Bone *>> bones;
  std::vector<Layer *> drawings;
  selection(C, bones, drawings);
  std::set<uint64_t> held;
  for (const auto &[rig, b] : bones) {
    held.insert(b->collections.begin(), b->collections.end());
  }
  for (const Layer *l : drawings) {
    held.insert(l->collections.begin(), l->collections.end());
  }
  for (const Collection &c : C.document->collections) {
    if (held.count(c.id)) {
      out.push_back(c.id);
    }
  }
  return out;
}

std::vector<PoseShelfRow> pose_shelf_rows(Context &C, const std::string &search,
                                          const std::vector<uint64_t> *collections)
{
  std::vector<PoseShelfRow> rows;
  if (!C.document) {
    return rows;
  }
  const Document &doc = *C.document;
  const std::string needle = lower(search);
  const auto poses_in = [&](uint64_t collection, bool unsorted) {
    std::vector<uint64_t> ids;
    for (const PoseAsset &p : doc.poses) {
      const bool in = unsorted ? !collection_find(doc, p.collection) : p.collection == collection;
      if (in && (needle.empty() || lower(p.name).find(needle) != std::string::npos)) {
        ids.push_back(p.id);
      }
    }
    return ids;
  };
  if (collections) {
    for (const uint64_t id : *collections) {
      const bool unsorted = id == 0 || !collection_find(doc, id);
      PoseShelfRow row{unsorted ? 0 : id, unsorted ? "Unsorted" : collection_name(doc, id), poses_in(id, unsorted)};
      if (needle.empty() || !row.poses.empty()) {
        rows.push_back(std::move(row));
      }
    }
    return rows;
  }
  if (pose_anything_selected(C)) {
    /* The selection's collections that have poses (a tag with none, such as the rig's bones', is no row: Save Pose
     * in the header saves into one). */
    for (const uint64_t id : pose_selection_collections(C)) {
      PoseShelfRow row{id, collection_name(doc, id), poses_in(id, false)};
      if (!row.poses.empty()) {
        rows.push_back(std::move(row));
      }
    }
    return rows;
  }
  for (const Collection &c : doc.collections) {
    PoseShelfRow row{c.id, c.name, poses_in(c.id, false)};
    if (!row.poses.empty()) {
      rows.push_back(std::move(row));
    }
  }
  if (PoseShelfRow row{0, "Unsorted", poses_in(0, true)}; !row.poses.empty()) {
    rows.push_back(std::move(row));
  }
  return rows;
}

/* Where every drawing's points show (document space), by layer. */
static std::map<uint64_t, std::vector<float2>> points_shown(const Document &doc)
{
  std::map<uint64_t, std::vector<float2>> out;
  for (const Layer *l : document_layers_flat(doc)) {
    if (l->type != LayerType::Vector || l->is_reference() || !l->visible) {
      continue;
    }
    std::vector<Transform2D> skins = layer_point_skins(doc, *l);
    skins.resize(l->drawing.points.size());
    const Transform2D world = layer_world_transform(doc, l->id);
    std::vector<float2> &shown = out[l->id];
    for (size_t i = 0; i < l->drawing.points.size(); i++) {
      shown.push_back((world * skins[i]).apply(l->drawing.points[i].pos));
    }
  }
  return out;
}

bool pose_posed_copy(const Document &doc, const PoseAsset &pose, Document &r_copy, float2 *r_lo, float2 *r_hi,
                     std::vector<uint64_t> *r_layers)
{
  controller_document_generation();
  off_setup_copy(doc, r_copy);
  const json j = pose_json(pose);
  Context C;
  C.document = &r_copy;
  std::vector<std::pair<uint64_t, uint64_t>> bones;
  std::vector<std::pair<uint64_t, size_t>> points;
  PoseApplyOptions options;
  options.anywhere = true;
  options.quiet = true;
  options.warn = false;
  options.r_bones = &bones;
  options.r_points = &points;
  /* Framed on what the pose moves from the setup pose (whatever frame it is shown on): the same bones and points at
   * their setup places (no change from setup), against the pose. */
  std::map<uint64_t, std::vector<float2>> before;
  if (j.is_object() && j.contains("layers") && j["layers"].is_array()) {
    json rest_pose = j;
    for (json &lj : rest_pose["layers"]) {
      if (lj.contains("bones")) {
        for (json &bj : lj["bones"]) {
          bj["transform"] = json::array({0.0f, 0.0f});
          bj["turn"] = 0.0f;
        }
      }
      if (lj.contains("points")) {
        for (json &pj : lj["points"]) {
          pj["key"] = json::array({0.0f, 0.0f});
        }
      }
    }
    Document rest = r_copy;
    Context R;
    R.document = &rest;
    PoseApplyOptions quiet;
    quiet.anywhere = true;
    quiet.quiet = true;
    quiet.warn = false;
    if (pose_apply(R, rest_pose, false, quiet) == OpStatus::Finished) {
      animation_refresh_action_bones(rest);
    }
    before = points_shown(rest);
  }
  const bool posed = j.is_object() && pose_apply(C, j, false, options) == OpStatus::Finished;
  r_layers->clear();
  bool any = false;
  const auto add = [&](float2 q) {
    *r_lo = any ? float2(std::min(r_lo->x, q.x), std::min(r_lo->y, q.y)) : q;
    *r_hi = any ? float2(std::max(r_hi->x, q.x), std::max(r_hi->y, q.y)) : q;
    any = true;
  };
  const auto show = [&](uint64_t layer) {
    /* Shown inside the bone layer it is in (all of it, the pose seen on the character), or on its own. */
    const Layer *owner = layer_armature(r_copy, layer);
    const uint64_t id = owner ? owner->id : layer;
    if (std::find(r_layers->begin(), r_layers->end(), id) == r_layers->end()) {
      r_layers->push_back(id);
    }
  };
  if (posed) {
    /* What the bones it moved drive (a knob's actions) plays as they are now. */
    animation_refresh_action_bones(r_copy);
    for (const auto &[layer, bone] : bones) {
      if (std::find(r_layers->begin(), r_layers->end(), layer) == r_layers->end()) {
        r_layers->push_back(layer);
      }
    }
    /* Framed on what it moves (a bone's drawing, say, not the bone, which may sit anywhere). */
    const std::map<uint64_t, std::vector<float2>> after = points_shown(r_copy);
    for (const auto &[layer, now] : after) {
      const auto was = before.find(layer);
      if (was == before.end() || was->second.size() != now.size()) {
        continue;
      }
      bool moved = false;
      for (size_t i = 0; i < now.size(); i++) {
        if (distance(now[i], was->second[i]) > 1e-5f) {
          add(now[i]);
          moved = true;
        }
      }
      if (moved) {
        show(layer);
      }
    }
    /* Nothing it moves shows (the setup pose, a controller's box turned): the whole character. */
    if (!any) {
      for (const auto &[layer, shown] : after) {
        const Layer *owner = layer_armature(r_copy, layer);
        const bool in_rig = owner && std::find(r_layers->begin(), r_layers->end(), owner->id) != r_layers->end();
        const bool posed_drawing = std::any_of(points.begin(), points.end(), [&](const auto &p) { return p.first == layer; });
        if (in_rig || posed_drawing) {
          for (const float2 q : shown) {
            add(q);
          }
          show(layer);
        }
      }
    }
  }
  controller_document_generation_settle();
  return any;
}

void pose_frame_round(float2 lo, float2 hi, float2 *r_center, float *r_size)
{
  *r_center = (lo + hi) * 0.5f;
  *r_size = std::max(std::max(hi.x - lo.x, hi.y - lo.y) * 1.4f, 0.05f);
}

void pose_frame_choose(const PoseAsset &pose, float2 lo, float2 hi, float2 *r_center, float *r_size)
{
  if (pose.frame_size > 0.0f) {
    *r_center = pose.frame_center;
    *r_size = pose.frame_size;
  }
  else {
    pose_frame_round(lo, hi, r_center, r_size);
  }
}

bool pose_thumbnail_frame(const Document &doc, const PoseAsset &pose, float2 *r_center, float *r_size)
{
  Document posed;
  float2 lo, hi;
  std::vector<uint64_t> layers;
  if (!pose_posed_copy(doc, pose, posed, &lo, &hi, &layers)) {
    return false;
  }
  pose_frame_choose(pose, lo, hi, r_center, r_size);
  return true;
}

bool pose_frame_auto(const Document &doc, const PoseAsset &pose, float2 *r_center, float *r_size)
{
  Document posed;
  float2 lo, hi;
  std::vector<uint64_t> layers;
  if (!pose_posed_copy(doc, pose, posed, &lo, &hi, &layers)) {
    return false;
  }
  pose_frame_round(lo, hi, r_center, r_size);
  return true;
}

bool pose_frame_of_selection(Context &C, float2 *r_center, float *r_size)
{
  int bones = 0, points = 0;
  PoseAsset pose;
  pose.pose = pose_copy_json(C, &bones, &points).dump();
  return bones + points > 0 && pose_frame_auto(*C.document, pose, r_center, r_size);
}

/* A thumbnail's frame given to an operator: frame_x, frame_y (its middle, document space) and frame_size (its side);
 * false when none is (or it is no square). */
static bool frame_args(Context &C, float2 *r_center, float *r_size)
{
  const float2 center(op_arg_float(C, "frame_x", NAN), op_arg_float(C, "frame_y", NAN));
  const float size = op_arg_float(C, "frame_size", 0.0f);
  if (!std::isfinite(center.x) || !std::isfinite(center.y) || !std::isfinite(size) || size <= 0.0f) {
    return false;
  }
  *r_center = center;
  *r_size = size;
  return true;
}

void pose_library_operators_register()
{
  poselib_operator(
      "poselib.pose_new", "Save Pose",
      "Save the selected bones' and points' pose on this frame in the file, named `name`, under the collection "
      "`collection` (a name; none if empty) or a new one, `new_collection`, which the selection is put in. It shows "
      "on the Asset Shelf's Poses while anything in its collection is selected. frame_x, frame_y and frame_size: its "
      "thumbnail's frame (a square, its middle and side in document space); without them it is framed on what it "
      "moves",
      has_selection, [](Context &C) {
        Document &doc = *C.document;
        const std::string name = trimmed(op_arg(C, "name"));
        if (name.empty()) {
          report(ReportType::Warning, "Enter a name");
          return OpStatus::Cancelled;
        }
        int bones = 0, points = 0;
        const json pose = pose_copy_json(C, &bones, &points);
        if (bones + points == 0) {
          report(ReportType::Warning, "Select bones or points to save a pose");
          return OpStatus::Cancelled;
        }
        uint64_t collection = 0;
        if (op_has_arg(C, "new_collection")) {
          const std::string text = trimmed(op_arg(C, "new_collection"));
          if (text.empty()) {
            report(ReportType::Warning, "Name the new collection");
            return OpStatus::Cancelled;
          }
          collection = collection_new(doc, text).id;
          /* The selection put in it, so the pose shows while any of it is selected; on the panel of the bone layer
           * it is in. */
          std::vector<std::pair<Layer *, Bone *>> picked_bones;
          std::vector<Layer *> picked_drawings;
          selection(C, picked_bones, picked_drawings);
          std::set<uint64_t> panels;
          for (auto &[rig, b] : picked_bones) {
            b->collections.push_back(collection);
            panels.insert(rig->id);
          }
          for (Layer *d : picked_drawings) {
            d->collections.push_back(collection);
            if (const Layer *owner = layer_armature(doc, d->id)) {
              panels.insert(owner->id);
            }
          }
          for (const uint64_t id : panels) {
            bone_collection_ensure(*layer_find(doc, id), collection);
          }
        }
        else if (!collection_arg(C, "collection", &collection)) {
          return OpStatus::Cancelled;
        }
        PoseAsset asset;
        asset.id = doc.next_pose_id++;
        asset.name = unique_pose_name(doc, collection, name, 0);
        asset.collection = collection;
        asset.pose = pose.dump();
        frame_args(C, &asset.frame_center, &asset.frame_size);
        doc.poses.push_back(asset);
        report(ReportType::Info, "Saved the pose " + asset.name + " (" + what_text(bones, points) + ")");
        return OpStatus::Finished;
      });

  poselib_operator(
      "poselib.apply", "Apply Pose",
      "Put pose `pose` (its id) back on the bones and points it was saved from, on this frame; Auto Keying keys it. "
      "flipped=1: mirrored left to right (each _L bone's or drawing's pose on its _R partner). selected_only=1: only "
      "onto those of them selected now",
      has_document,
      [](Context &C) {
        PoseAsset *asset = pose_arg(C);
        if (!asset) {
          return OpStatus::Cancelled;
        }
        const json pose = pose_json(*asset);
        if (pose.is_null()) {
          report(ReportType::Warning, "The pose " + asset->name + " can't be read");
          return OpStatus::Cancelled;
        }
        const std::string name = asset->name;
        const bool flipped = op_arg_bool(C, "flipped");
        std::vector<std::pair<uint64_t, uint64_t>> bones;
        std::vector<std::pair<uint64_t, size_t>> points;
        PoseApplyOptions options;
        options.anywhere = true;
        options.quiet = true;
        options.selected_only = op_arg_bool(C, "selected_only");
        options.r_bones = &bones;
        options.r_points = &points;
        const OpStatus status = pose_apply(C, pose, flipped, options);
        if (status == OpStatus::Finished) {
          const std::string what = "Applied " + name + (flipped ? " flipped" : "") + " to " +
                                   what_text(int(bones.size()), int(points.size()));
          op_note(what);
          report(ReportType::Info, what);
          C.undo_name = "Apply Pose " + name;
        }
        return status;
      },
      {op_bool_property("flipped", "Flipped", "Mirrored left to right", "0"),
       op_bool_property("selected_only", "Selected Only",
                        "Only onto the pose's bones and points selected now (all of them when none is)", "0")});

  poselib_operator(
      "poselib.replace", "Replace with Current Pose",
      "Save the selected bones' and points' pose on this frame over pose `pose`, keeping its name and collection",
      has_selection, [](Context &C) {
        PoseAsset *asset = pose_arg(C);
        if (!asset) {
          return OpStatus::Cancelled;
        }
        int bones = 0, points = 0;
        const json pose = pose_copy_json(C, &bones, &points);
        if (bones + points == 0) {
          report(ReportType::Warning, "Select bones or points to save a pose");
          return OpStatus::Cancelled;
        }
        asset->pose = pose.dump();
        report(ReportType::Info, "Replaced " + asset->name + " with the pose of " + what_text(bones, points));
        return OpStatus::Finished;
      });

  poselib_operator("poselib.frame_set", "Edit Frame",
                   "Frame pose `pose`'s thumbnail on the square frame_x, frame_y (its middle, document space), "
                   "frame_size (its side); frame_size=0 frames it on what it moves again",
                   has_document, [](Context &C) {
                     PoseAsset *asset = pose_arg(C);
                     if (!asset) {
                       return OpStatus::Cancelled;
                     }
                     float2 center;
                     float size = 0.0f;
                     if (!frame_args(C, &center, &size) && op_arg_float(C, "frame_size", -1.0f) != 0.0f) {
                       report(ReportType::Warning, "frame_x, frame_y and frame_size (more than 0) give the frame");
                       return OpStatus::Cancelled;
                     }
                     if (center == asset->frame_center && size == asset->frame_size) {
                       return OpStatus::Cancelled;
                     }
                     asset->frame_center = center;
                     asset->frame_size = size;
                     return OpStatus::Finished;
                   });

  poselib_operator("poselib.rename", "Rename Pose", "Rename pose `pose` to `name`", has_document, [](Context &C) {
    PoseAsset *asset = pose_arg(C);
    if (!asset) {
      return OpStatus::Cancelled;
    }
    const std::string name = trimmed(op_arg(C, "name"));
    if (name.empty()) {
      report(ReportType::Warning, "Enter a name");
      return OpStatus::Cancelled;
    }
    const std::string unique = unique_pose_name(*C.document, asset->collection, name, asset->id);
    if (unique == asset->name) {
      return OpStatus::Cancelled;
    }
    asset->name = unique;
    return OpStatus::Finished;
  });

  poselib_operator("poselib.move", "Move to Collection",
                   "File pose `pose` under the collection `collection` (a name; none if empty)", has_document,
                   [](Context &C) {
                     PoseAsset *asset = pose_arg(C);
                     uint64_t collection = 0;
                     if (!asset || !collection_arg(C, "collection", &collection)) {
                       return OpStatus::Cancelled;
                     }
                     if (collection == asset->collection) {
                       return OpStatus::Cancelled;
                     }
                     asset->name = unique_pose_name(*C.document, collection, asset->name, asset->id);
                     asset->collection = collection;
                     report(ReportType::Info, "Moved " + asset->name + " to " +
                                                  (collection ? collection_name(*C.document, collection) : "no collection"));
                     return OpStatus::Finished;
                   });

  poselib_operator("poselib.duplicate", "Duplicate Pose", "A copy of pose `pose` beside it, in the same collection",
                   has_document, [](Context &C) {
                     Document &doc = *C.document;
                     PoseAsset *asset = pose_arg(C);
                     if (!asset) {
                       return OpStatus::Cancelled;
                     }
                     PoseAsset copy = *asset;
                     copy.id = doc.next_pose_id++;
                     copy.name = unique_pose_name(doc, copy.collection, copy.name, 0);
                     const auto at = std::find_if(doc.poses.begin(), doc.poses.end(),
                                                  [&](const PoseAsset &p) { return p.id == asset->id; });
                     doc.poses.insert(at + 1, copy);
                     report(ReportType::Info, "Duplicated as " + copy.name);
                     return OpStatus::Finished;
                   });

  poselib_operator(
      "poselib.flip_copy", "Save Flipped Copy",
      "A copy of pose `pose` mirrored left to right (its _L bones' and drawings' pose on their _R partners), named "
      "after the other side (Wave_L: Wave_R) or with Flipped, in the other side's collection if there is one",
      has_document, [](Context &C) {
        Document &doc = *C.document;
        PoseAsset *asset = pose_arg(C);
        if (!asset) {
          return OpStatus::Cancelled;
        }
        int bones = 0, points = 0;
        const json pose = pose_json(*asset);
        const json flipped = pose.is_null() ? json() : pose_flipped_record(doc, pose, &bones, &points);
        if (bones + points == 0) {
          report(ReportType::Warning, "None of the pose's bones and points is here to flip");
          return OpStatus::Cancelled;
        }
        PoseAsset copy;
        copy.id = doc.next_pose_id++;
        copy.collection = asset->collection;
        if (const std::string other = bone_mirror_name(collection_name(doc, asset->collection));
            asset->collection && other != collection_name(doc, asset->collection))
        {
          if (const Collection *c = collection_find_by_name(doc, other)) {
            copy.collection = c->id;
          }
        }
        const std::string mirrored = bone_mirror_name(asset->name);
        copy.name = unique_pose_name(doc, copy.collection, mirrored != asset->name ? mirrored : asset->name + " Flipped",
                                     0);
        copy.pose = flipped.dump();
        /* Its bones and drawings put in its collection, so it shows while they are selected (Ears made from Ear_L
         * then holds Ear_R too). */
        if (copy.collection) {
          for (const json &lj : flipped["layers"]) {
            Layer *l = layer_find(doc, lj.value("id", uint64_t(0)));
            if (!l) {
              continue;
            }
            const auto join = [&](std::vector<uint64_t> &ids) {
              if (std::find(ids.begin(), ids.end(), copy.collection) == ids.end()) {
                ids.push_back(copy.collection);
              }
            };
            if (lj.contains("bones")) {
              for (const json &bj : lj["bones"]) {
                for (Bone &b : l->bones) {
                  if (b.name == bj.value("name", std::string())) {
                    join(b.collections);
                  }
                }
              }
              bone_collection_ensure(*l, copy.collection);
            }
            if (lj.contains("points")) {
              join(l->collections);
              if (const Layer *owner = layer_armature(doc, l->id)) {
                bone_collection_ensure(*layer_find(doc, owner->id), copy.collection);
              }
            }
          }
        }
        const auto at = std::find_if(doc.poses.begin(), doc.poses.end(),
                                     [&](const PoseAsset &p) { return p.id == asset->id; });
        doc.poses.insert(at + 1, copy);
        report(ReportType::Info, "Saved " + copy.name + ", flipped (" + what_text(bones, points) + ")");
        return OpStatus::Finished;
      });

  poselib_operator("poselib.delete", "Delete Pose", "Delete pose `pose` from the file", has_document, [](Context &C) {
    PoseAsset *asset = pose_arg(C);
    if (!asset) {
      return OpStatus::Cancelled;
    }
    const std::string name = asset->name;
    const uint64_t id = asset->id;
    std::erase_if(C.document->poses, [&](const PoseAsset &p) { return p.id == id; });
    report(ReportType::Info, "Deleted the pose " + name);
    return OpStatus::Finished;
  });
}

}  // namespace oanim
